"""Sprievodca nastavením AI Energy (UI)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    CONF_CABLE_KW,
    CONF_EV_CHARGING,
    CONF_EV_CURRENT,
    CONF_EV_MAX_A,
    CONF_EV_MIN_A,
    CONF_EV_OFF_OPTION,
    CONF_EV_ON_OPTION,
    CONF_EV_PHASES,
    CONF_EV_PLUG,
    CONF_EV_POWER,
    CONF_EV_SWITCH,
    CONF_GRID_INVERT,
    CONF_GRID_LIMIT_KW,
    CONF_GRID_POWER,
    DEFAULT_CABLE_KW,
    DEFAULT_EV_MAX_A,
    DEFAULT_EV_MIN_A,
    DEFAULT_EV_PHASES,
    DEFAULT_GRID_LIMIT_KW,
    CONF_CAPACITY,
    CONF_CHARGE_KW,
    CONF_EXPORT_KW,
    CONF_HOUSE_KW,
    CONF_HOUSE_POWER,
    CONF_PV_POWER,
    CONF_PV_TODAY,
    CONF_PV_TOMORROW,
    CONF_SOC_ENTITY,
    DEFAULT_CAPACITY,
    DEFAULT_CHARGE_KW,
    DEFAULT_EXPORT_KW,
    DEFAULT_HOUSE_KW,
    DEFAULT_PV_TODAY,
    DEFAULT_PV_TOMORROW,
    CONF_NT_INTERVALS,
    CONF_PRICE_NT,
    CONF_PRICE_TODAY,
    CONF_PRICE_TOMORROW,
    CONF_PRICE_VT,
    CONF_SELL_FEE,
    DEFAULT_NT_INTERVALS,
    DEFAULT_PRICE_NT,
    DEFAULT_PRICE_TODAY,
    DEFAULT_PRICE_TOMORROW,
    DEFAULT_PRICE_VT,
    DEFAULT_SELL_FEE,
    DOMAIN,
)
from .prices import parse_intervals, parse_slots

PRICE_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(min=-500, max=2000, step=0.1, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="€/MWh")
)
SENSOR_SELECTOR = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
SOC_SELECTOR = selector.EntitySelector(selector.EntitySelectorConfig(domain=["sensor", "input_number", "number"]))
POWER_SELECTOR = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="power"))


def _num(min_v: float, max_v: float, step: float, unit: str) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(min=min_v, max=max_v, step=step, mode=selector.NumberSelectorMode.BOX, unit_of_measurement=unit)
    )


def _guess_soc(hass: HomeAssistant) -> str | None:
    """Senzor SOC batérie: device_class battery s 'soc' v názve, inak prvý s 'soc'."""
    ids = sorted(hass.states.async_entity_ids("sensor"))
    batt = [e for e in ids if (hass.states.get(e).attributes.get("device_class") == "battery")]
    for pool in (batt, ids):
        hit = next((e for e in pool if "soc" in e), None)
        if hit:
            return hit
    return None


def _opt(key: str, value: Any) -> vol.Optional:
    """Voliteľné pole – predvyplní sa, len ak máme hodnotu."""
    return vol.Optional(key, description={"suggested_value": value}) if value else vol.Optional(key)


def _battery_schema(hass: HomeAssistant, cfg: dict[str, Any]) -> vol.Schema:
    soc = cfg.get(CONF_SOC_ENTITY) or _guess_soc(hass)
    pv_today = cfg.get(CONF_PV_TODAY) or _guess(hass, DEFAULT_PV_TODAY, "")
    pv_tom = cfg.get(CONF_PV_TOMORROW) or _guess(hass, DEFAULT_PV_TOMORROW, "")
    return vol.Schema(
        {
            vol.Required(CONF_SOC_ENTITY, **({"default": soc} if soc else {})): SOC_SELECTOR,
            vol.Required(CONF_CAPACITY, default=cfg.get(CONF_CAPACITY, DEFAULT_CAPACITY)): _num(1, 500, 0.5, "kWh"),
            vol.Required(CONF_CHARGE_KW, default=cfg.get(CONF_CHARGE_KW, DEFAULT_CHARGE_KW)): _num(0.5, 50, 0.5, "kW"),
            vol.Required(CONF_EXPORT_KW, default=cfg.get(CONF_EXPORT_KW, DEFAULT_EXPORT_KW)): _num(0.5, 50, 0.5, "kW"),
            vol.Required(CONF_HOUSE_KW, default=cfg.get(CONF_HOUSE_KW, DEFAULT_HOUSE_KW)): _num(0, 20, 0.1, "kW"),
            _opt(CONF_PV_TODAY, pv_today): SENSOR_SELECTOR,
            _opt(CONF_PV_TOMORROW, pv_tom): SENSOR_SELECTOR,
            _opt(CONF_PV_POWER, cfg.get(CONF_PV_POWER)): POWER_SELECTOR,
            _opt(CONF_HOUSE_POWER, cfg.get(CONF_HOUSE_POWER)): POWER_SELECTOR,
        }
    )


def _check_battery(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, str]:
    if hass.states.get(data.get(CONF_SOC_ENTITY, "")) is None:
        return {CONF_SOC_ENTITY: "entity_not_found"}
    return {}


def _guess(hass: HomeAssistant, prefix: str, fallback: str) -> str:
    """Nájde existujúci senzor podľa začiatku entity_id (napr. sensor.okte_prices_tomorrow_2)."""
    ids = sorted(e for e in hass.states.async_entity_ids("sensor") if e.startswith(prefix))
    return ids[0] if ids else fallback


def _prices_schema(hass: HomeAssistant, cfg: dict[str, Any]) -> vol.Schema:
    today = cfg.get(CONF_PRICE_TODAY) or _guess(hass, DEFAULT_PRICE_TODAY, DEFAULT_PRICE_TODAY)
    tomorrow = cfg.get(CONF_PRICE_TOMORROW) or _guess(hass, DEFAULT_PRICE_TOMORROW, "")
    return vol.Schema(
        {
            vol.Required(CONF_PRICE_TODAY, default=today): SENSOR_SELECTOR,
            vol.Optional(CONF_PRICE_TOMORROW, **({"default": tomorrow} if tomorrow else {})): SENSOR_SELECTOR,
        }
    )


def _tariff_schema(cfg: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_NT_INTERVALS, default=cfg.get(CONF_NT_INTERVALS, DEFAULT_NT_INTERVALS)): selector.TextSelector(),
            vol.Required(CONF_PRICE_NT, default=cfg.get(CONF_PRICE_NT, DEFAULT_PRICE_NT)): PRICE_SELECTOR,
            vol.Required(CONF_PRICE_VT, default=cfg.get(CONF_PRICE_VT, DEFAULT_PRICE_VT)): PRICE_SELECTOR,
            vol.Required(CONF_SELL_FEE, default=cfg.get(CONF_SELL_FEE, DEFAULT_SELL_FEE)): PRICE_SELECTOR,
        }
    )


def _check_prices(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, str]:
    """Ak je zdroj dostupný, musí obsahovať ceny v známom formáte."""
    errors: dict[str, str] = {}
    for key in (CONF_PRICE_TODAY, CONF_PRICE_TOMORROW):
        entity_id = data.get(key)
        if not entity_id:
            continue
        state = hass.states.get(entity_id)
        if state is None:
            errors[key] = "entity_not_found"
        elif key == CONF_PRICE_TODAY and state.state not in ("unavailable", "unknown") and not parse_slots(state.attributes):
            errors[key] = "no_prices"
    return errors


def _check_tariff(data: dict[str, Any]) -> dict[str, str]:
    try:
        if not parse_intervals(data[CONF_NT_INTERVALS]):
            return {CONF_NT_INTERVALS: "invalid_intervals"}
    except ValueError:
        return {CONF_NT_INTERVALS: "invalid_intervals"}
    return {}

EV_CURRENT_SELECTOR = selector.EntitySelector(selector.EntitySelectorConfig(domain=["number", "input_number"]))
EV_SWITCH_SELECTOR = selector.EntitySelector(selector.EntitySelectorConfig(domain=["switch", "input_boolean", "select", "input_select"]))
EV_STATE_SELECTOR = selector.EntitySelector(selector.EntitySelectorConfig(domain=["sensor", "binary_sensor"]))
PHASES_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(options=["1", "3"], mode=selector.SelectSelectorMode.LIST, translation_key="ev_phases")
)


def _find(hass: HomeAssistant, domains: tuple[str, ...], *words: str) -> str | None:
    """Prvá entita v doméne, ktorej entity_id obsahuje všetky slová (napr. smartevse + mode)."""
    for eid in sorted(hass.states.async_entity_ids(list(domains))):
        if all(w in eid for w in words):
            return eid
    return None


def _guess_ev(hass: HomeAssistant) -> dict[str, str | None]:
    """Predvyplnenie pre známe nabíjačky (SmartEVSE)."""
    return {
        CONF_EV_CURRENT: _find(hass, ("number",), "smartevse", "current_override") or _find(hass, ("number",), "smartevse", "chargecurrent"),
        CONF_EV_SWITCH: _find(hass, ("select",), "smartevse", "mode"),
        CONF_EV_PLUG: _find(hass, ("sensor",), "smartevse", "plug"),
        CONF_EV_CHARGING: _find(hass, ("sensor",), "smartevse", "_state"),
    }


def _ev_schema(hass: HomeAssistant, cfg: dict[str, Any], guess: bool) -> vol.Schema:
    g = _guess_ev(hass) if guess and not cfg.get(CONF_EV_SWITCH) else {}
    v = lambda k: cfg.get(k) or g.get(k)  # noqa: E731
    return vol.Schema(
        {
            _opt(CONF_EV_SWITCH, v(CONF_EV_SWITCH)): EV_SWITCH_SELECTOR,
            _opt(CONF_EV_ON_OPTION, cfg.get(CONF_EV_ON_OPTION)): selector.TextSelector(),
            _opt(CONF_EV_OFF_OPTION, cfg.get(CONF_EV_OFF_OPTION)): selector.TextSelector(),
            _opt(CONF_EV_CURRENT, v(CONF_EV_CURRENT)): EV_CURRENT_SELECTOR,
            vol.Required(CONF_EV_PHASES, default=str(cfg.get(CONF_EV_PHASES, DEFAULT_EV_PHASES))): PHASES_SELECTOR,
            vol.Required(CONF_EV_MIN_A, default=cfg.get(CONF_EV_MIN_A, DEFAULT_EV_MIN_A)): _num(1, 32, 1, "A"),
            vol.Required(CONF_EV_MAX_A, default=cfg.get(CONF_EV_MAX_A, DEFAULT_EV_MAX_A)): _num(1, 80, 1, "A"),
            _opt(CONF_EV_PLUG, v(CONF_EV_PLUG)): EV_STATE_SELECTOR,
            _opt(CONF_EV_CHARGING, v(CONF_EV_CHARGING)): EV_STATE_SELECTOR,
            _opt(CONF_EV_POWER, cfg.get(CONF_EV_POWER)): POWER_SELECTOR,
            _opt(CONF_GRID_POWER, cfg.get(CONF_GRID_POWER)): POWER_SELECTOR,
            vol.Required(CONF_GRID_INVERT, default=bool(cfg.get(CONF_GRID_INVERT, False))): selector.BooleanSelector(),
            vol.Required(CONF_GRID_LIMIT_KW, default=cfg.get(CONF_GRID_LIMIT_KW, DEFAULT_GRID_LIMIT_KW)): _num(0, 200, 0.5, "kW"),
            vol.Required(CONF_CABLE_KW, default=cfg.get(CONF_CABLE_KW, DEFAULT_CABLE_KW)): _num(0, 200, 0.5, "kW"),
        }
    )


def _select_options(hass: HomeAssistant, entity_id: str) -> list[str]:
    st = hass.states.get(entity_id)
    return list(st.attributes.get("options", [])) if st else []


def _check_ev(hass: HomeAssistant, data: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    """Kontrola a doplnenie možností pre select. Vráti (chyby, placeholdery)."""
    sw = data.get(CONF_EV_SWITCH)
    if not sw:
        if data.get(CONF_EV_CURRENT):
            return {CONF_EV_SWITCH: "ev_switch_required"}, {}
        return {}, {}
    for key in (CONF_EV_SWITCH, CONF_EV_CURRENT, CONF_EV_PLUG, CONF_EV_CHARGING):
        if data.get(key) and hass.states.get(data[key]) is None:
            return {key: "entity_not_found"}, {}
    if int(data.get(CONF_EV_MIN_A, 6)) > int(data.get(CONF_EV_MAX_A, 16)):
        return {CONF_EV_MAX_A: "ev_min_max"}, {}
    if sw.split(".")[0] in ("select", "input_select"):
        opts = _select_options(hass, sw)
        low = {o.lower(): o for o in opts}
        if not data.get(CONF_EV_OFF_OPTION):
            data[CONF_EV_OFF_OPTION] = next((o for o in opts if o.lower() in ("off", "vypnuté", "vypnute", "stop", "disabled")), "")
        if not data.get(CONF_EV_ON_OPTION):
            data[CONF_EV_ON_OPTION] = low.get("normal") or next(
                (o for o in opts if o.lower() in ("on", "charge", "charging", "start", "enabled", "zapnuté", "now")), ""
            )
        bad = [k for k in (CONF_EV_ON_OPTION, CONF_EV_OFF_OPTION) if data.get(k) not in opts]
        if bad:
            return {bad[0]: "ev_option"}, {"options": "\n\n`" + "`, `".join(opts) + "`"}
    return {}, {}



def _clean(prev: dict[str, Any], schema: vol.Schema, user_input: dict[str, Any]) -> dict[str, Any]:
    """Nové options = staré + krok; voliteľné polia, ktoré používateľ vymazal, sa odstránia."""
    out = {k: v for k, v in prev.items() if k not in schema.schema}
    out.update({k: v for k, v in user_input.items() if v not in (None, "")})
    return out


class AiEnergyConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Krok 1: odkiaľ brať spotové ceny."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _check_prices(self.hass, user_input)
            if not errors:
                self._data.update(user_input)
                return await self.async_step_tarifa()
        return self.async_show_form(
            step_id="user", data_schema=_prices_schema(self.hass, user_input or {}), errors=errors
        )

    async def async_step_tarifa(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Krok 2: tarifa nákupu a poplatok za predaj."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _check_tariff(user_input)
            if not errors:
                self._data.update(user_input)
                return await self.async_step_bateria()
        return self.async_show_form(step_id="tarifa", data_schema=_tariff_schema(user_input or {}), errors=errors)

    async def async_step_bateria(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Krok 3: batéria a (voliteľne) FVE."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _check_battery(self.hass, user_input)
            if not errors:
                self._data.update(user_input)
                return await self.async_step_auto()
        return self.async_show_form(step_id="bateria", data_schema=_battery_schema(self.hass, user_input or {}), errors=errors)

    async def async_step_auto(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Krok 4: nabíjanie auta (voliteľné – prázdne = bez auta)."""
        errors: dict[str, str] = {}
        ph: dict[str, str] = {"options": ""}
        if user_input is not None:
            errors, extra = _check_ev(self.hass, user_input)
            ph.update(extra)
            if not errors:
                self._data.update({k: v for k, v in user_input.items() if v not in (None, "")})
                return self.async_create_entry(title="AI Energy", data=self._data)
        return self.async_show_form(
            step_id="auto", data_schema=_ev_schema(self.hass, user_input or {}, user_input is None), errors=errors, description_placeholders=ph
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return AiEnergyOptionsFlow()


class AiEnergyOptionsFlow(OptionsFlow):
    """Zmena nastavení po inštalácii (Nastavenia → Integrácie → AI Energy → Konfigurovať)."""

    def _cfg(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    def _save(self, schema: vol.Schema, user_input: dict[str, Any]) -> ConfigFlowResult:
        return self.async_create_entry(data=_clean(self._cfg(), schema, user_input))

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["ceny", "bateria", "auto"])

    async def async_step_ceny(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        cfg = self._cfg()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = {**_check_prices(self.hass, user_input), **_check_tariff(user_input)}
            cfg.update(user_input)
        schema = vol.Schema({**_prices_schema(self.hass, cfg).schema, **_tariff_schema(cfg).schema})
        if user_input is not None and not errors:
            return self._save(schema, user_input)
        return self.async_show_form(step_id="ceny", data_schema=schema, errors=errors)

    async def async_step_bateria(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        cfg = self._cfg()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _check_battery(self.hass, user_input)
            cfg.update(user_input)
        schema = _battery_schema(self.hass, cfg)
        if user_input is not None and not errors:
            return self._save(schema, user_input)
        return self.async_show_form(step_id="bateria", data_schema=schema, errors=errors)

    async def async_step_auto(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        cfg = self._cfg()
        errors: dict[str, str] = {}
        ph: dict[str, str] = {"options": ""}
        if user_input is not None:
            errors, extra = _check_ev(self.hass, user_input)
            ph.update(extra)
            cfg = {**{k: v for k, v in cfg.items()}, **user_input}
        schema = _ev_schema(self.hass, cfg, user_input is None)
        if user_input is not None and not errors:
            return self._save(schema, user_input)
        return self.async_show_form(step_id="auto", data_schema=schema, errors=errors, description_placeholders=ph)
