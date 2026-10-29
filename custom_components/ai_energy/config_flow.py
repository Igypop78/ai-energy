"""Sprievodca nastavením AI Energy (UI).

Kroky: Vitaj (čo mám doma) → Ceny → Nákup → Predaj (→ detail) → Batéria a spotreba → FVE → Auto (→ možnosti)
→ Istič a elektromer → Hotovo. Kroky FVE a auta sa zobrazia len tomu, kto ich má.
Ceny sa v sprievodcovi zadávajú v €/kWh, ukladajú sa v €/MWh (ako spotové ceny).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector

from .const import (
    CONF_BREAKER_A,
    CONF_BREAKER_PHASES,
    CONF_BREAKER_RESERVE,
    CONF_CABLE_KW,
    CONF_CAPACITY,
    CONF_CHARGE_KW,
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
    CONF_EXPORT_KW,
    CONF_GRID_INVERT,
    CONF_GRID_POWER,
    CONF_HAS_EV,
    CONF_HAS_PV,
    CONF_HOUSE_KWH,
    CONF_HOUSE_SENSOR,
    CONF_NT_INTERVALS,
    CONF_PRICE_NT,
    CONF_PRICE_TODAY,
    CONF_PRICE_TOMORROW,
    CONF_PRICE_VT,
    CONF_PV_POWER,
    CONF_PV_TODAY,
    CONF_PV_TOMORROW,
    CONF_SELL_BAND_PRICE,
    CONF_SELL_BANDS,
    CONF_SELL_FEE,
    CONF_SELL_FIXED,
    CONF_SELL_MODE,
    CONF_SOC_ENTITY,
    DEFAULT_BREAKER_RESERVE,
    DEFAULT_CABLE_KW,
    DEFAULT_CAPACITY,
    DEFAULT_CHARGE_KW,
    DEFAULT_EV_MAX_A,
    DEFAULT_EV_MIN_A,
    DEFAULT_EV_PHASES,
    DEFAULT_EXPORT_KW,
    DEFAULT_HOUSE_KWH,
    DEFAULT_NT_INTERVALS,
    DEFAULT_PRICE_NT,
    DEFAULT_PRICE_TODAY,
    DEFAULT_PRICE_TOMORROW,
    DEFAULT_PRICE_VT,
    DEFAULT_PV_TODAY,
    DEFAULT_PV_TOMORROW,
    DEFAULT_SELL_FEE,
    DOMAIN,
    SELL_FIXED,
    SELL_NONE,
    SELL_SPOT,
    grid_limit_kw,
    has_ev,
    has_pv,
    house_kw_estimate,
    house_sensor,
    sell_mode,
)
from .prices import parse_intervals, parse_slots

ADV = "pokrocile"  # zbalená sekcia „Pokročilé“
EUR_KWH = (CONF_PRICE_NT, CONF_PRICE_VT, CONF_SELL_FEE, CONF_SELL_FIXED, CONF_SELL_BAND_PRICE)  # v UI €/kWh

SENSOR = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
SOC = selector.EntitySelector(selector.EntitySelectorConfig(domain=["sensor", "input_number", "number"]))
POWER = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="power"))
HOUSE = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class=["energy", "power"]))
EV_CURRENT = selector.EntitySelector(selector.EntitySelectorConfig(domain=["number", "input_number"]))
EV_SWITCH = selector.EntitySelector(selector.EntitySelectorConfig(domain=["switch", "input_boolean", "select", "input_select"]))
EV_STATE = selector.EntitySelector(selector.EntitySelectorConfig(domain=["sensor", "binary_sensor"]))
BOOL = selector.BooleanSelector()
TEXT = selector.TextSelector()


def _num(min_v: float, max_v: float, step: float, unit: str) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(min=min_v, max=max_v, step=step, mode=selector.NumberSelectorMode.BOX, unit_of_measurement=unit)
    )


def _choice(key: str, options: list[str]) -> selector.SelectSelector:
    return selector.SelectSelector(selector.SelectSelectorConfig(options=options, mode=selector.SelectSelectorMode.LIST, translation_key=key))


PRICE = _num(-1, 5, 0.001, "€/kWh")
PHASES = lambda key: _choice(key, ["1", "3"])  # noqa: E731


def _opt(key: str, value: Any) -> vol.Optional:
    """Voliteľné pole – predvyplní sa, len ak máme hodnotu."""
    return vol.Optional(key, description={"suggested_value": value}) if value not in (None, "") else vol.Optional(key)


def _req(key: str, value: Any) -> vol.Required:
    return vol.Required(key, default=value) if value not in (None, "") else vol.Required(key)


def _kwh(cfg: dict[str, Any], key: str, default: float | None) -> float | None:
    v = cfg.get(key, default)
    return None if v in (None, "") else round(float(v) / 1000, 4)


def _adv(fields: dict[Any, Any]) -> dict[Any, Any]:
    return {vol.Required(ADV): section(vol.Schema(fields), {"collapsed": True})}


# ---------------------------------------------------------------- odhady (predvyplnenie)


def _guess(hass: HomeAssistant, prefix: str) -> str | None:
    """Existujúci senzor podľa začiatku entity_id (napr. sensor.okte_prices_tomorrow_2)."""
    ids = sorted(e for e in hass.states.async_entity_ids("sensor") if e.startswith(prefix))
    return ids[0] if ids else None


def _guess_soc(hass: HomeAssistant) -> str | None:
    ids = sorted(hass.states.async_entity_ids("sensor"))
    batt = [e for e in ids if hass.states.get(e).attributes.get("device_class") == "battery"]
    for pool in (batt, ids):
        hit = next((e for e in pool if "soc" in e), None)
        if hit:
            return hit
    return None


def _find(hass: HomeAssistant, domain: str, *words: str) -> str | None:
    for eid in sorted(hass.states.async_entity_ids(domain)):
        if all(w in eid for w in words):
            return eid
    return None


def _guess_ev(hass: HomeAssistant) -> dict[str, str | None]:
    """Predvyplnenie pre SmartEVSE."""
    return {
        CONF_EV_SWITCH: _find(hass, "select", "smartevse", "mode"),
        CONF_EV_CURRENT: _find(hass, "number", "smartevse", "current_override") or _find(hass, "number", "smartevse", "chargecurrent"),
        CONF_EV_PLUG: _find(hass, "sensor", "smartevse", "plug"),
        CONF_EV_CHARGING: _find(hass, "sensor", "smartevse", "_state"),
    }


def _select_options(hass: HomeAssistant, entity_id: str | None) -> list[str]:
    st = hass.states.get(entity_id) if entity_id else None
    return [str(o) for o in st.attributes.get("options", [])] if st else []


def _is_select(entity_id: str | None) -> bool:
    return (entity_id or "").split(".")[0] in ("select", "input_select")


def _guess_options(opts: list[str]) -> tuple[str | None, str | None]:
    """Možnosti selectu pre „nabíjaj“ a „vypni“ (SmartEVSE: Normal / Off)."""
    low = {o.lower(): o for o in opts}
    off = next((o for o in opts if o.lower() in ("off", "vypnuté", "vypnute", "stop", "disabled")), None)
    on = low.get("normal") or next((o for o in opts if o.lower() in ("on", "charge", "charging", "start", "enabled", "zapnuté", "now")), None)
    return on, off


# ---------------------------------------------------------------- schémy krokov


def _s_vitaj(hass: HomeAssistant, c: dict[str, Any]) -> vol.Schema:
    return vol.Schema({vol.Required(CONF_HAS_PV, default=has_pv(c) if c else True): BOOL, vol.Required(CONF_HAS_EV, default=has_ev(c) or bool(c.get(CONF_HAS_EV))): BOOL})


def _s_ceny(hass: HomeAssistant, c: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            _req(CONF_PRICE_TODAY, c.get(CONF_PRICE_TODAY) or _guess(hass, DEFAULT_PRICE_TODAY)): SENSOR,
            _opt(CONF_PRICE_TOMORROW, c.get(CONF_PRICE_TOMORROW) or _guess(hass, DEFAULT_PRICE_TOMORROW)): SENSOR,
        }
    )


def _s_nakup(hass: HomeAssistant, c: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            _opt(CONF_NT_INTERVALS, c.get(CONF_NT_INTERVALS, DEFAULT_NT_INTERVALS)): TEXT,
            vol.Required(CONF_PRICE_NT, default=_kwh(c, CONF_PRICE_NT, DEFAULT_PRICE_NT)): PRICE,
            vol.Required(CONF_PRICE_VT, default=_kwh(c, CONF_PRICE_VT, DEFAULT_PRICE_VT)): PRICE,
        }
    )


def _s_predaj(hass: HomeAssistant, c: dict[str, Any]) -> vol.Schema:
    return vol.Schema({vol.Required(CONF_SELL_MODE, default=sell_mode(c)): _choice(CONF_SELL_MODE, [SELL_SPOT, SELL_FIXED, SELL_NONE])})


def _s_predaj_spot(hass: HomeAssistant, c: dict[str, Any]) -> vol.Schema:
    return vol.Schema({vol.Required(CONF_SELL_FEE, default=_kwh(c, CONF_SELL_FEE, DEFAULT_SELL_FEE)): PRICE})


def _s_predaj_pevna(hass: HomeAssistant, c: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            _req(CONF_SELL_FIXED, _kwh(c, CONF_SELL_FIXED, None)): PRICE,
            _opt(CONF_SELL_BANDS, c.get(CONF_SELL_BANDS)): TEXT,
            _opt(CONF_SELL_BAND_PRICE, _kwh(c, CONF_SELL_BAND_PRICE, None)): PRICE,
        }
    )


def _s_bateria(hass: HomeAssistant, c: dict[str, Any]) -> vol.Schema:
    kwh_day = c.get(CONF_HOUSE_KWH)
    if kwh_day is None:
        kwh_day = round(house_kw_estimate(c) * 24, 1) if c else DEFAULT_HOUSE_KWH
    return vol.Schema(
        {
            _req(CONF_SOC_ENTITY, c.get(CONF_SOC_ENTITY) or _guess_soc(hass)): SOC,
            vol.Required(CONF_CAPACITY, default=c.get(CONF_CAPACITY, DEFAULT_CAPACITY)): _num(1, 500, 0.5, "kWh"),
            vol.Required(CONF_CHARGE_KW, default=c.get(CONF_CHARGE_KW, DEFAULT_CHARGE_KW)): _num(0.5, 50, 0.5, "kW"),
            vol.Required(CONF_EXPORT_KW, default=c.get(CONF_EXPORT_KW, DEFAULT_EXPORT_KW)): _num(0.5, 50, 0.5, "kW"),
            vol.Required(CONF_HOUSE_KWH, default=kwh_day): _num(0, 500, 0.5, "kWh"),
            _opt(CONF_HOUSE_SENSOR, house_sensor(c)): HOUSE,
        }
    )


def _s_fve(hass: HomeAssistant, c: dict[str, Any]) -> vol.Schema:
    first = CONF_PV_TODAY not in c and CONF_HAS_PV not in c
    return vol.Schema(
        {
            _opt(CONF_PV_TODAY, c.get(CONF_PV_TODAY) or (_guess(hass, DEFAULT_PV_TODAY) if first else None)): SENSOR,
            _opt(CONF_PV_TOMORROW, c.get(CONF_PV_TOMORROW) or (_guess(hass, DEFAULT_PV_TOMORROW) if first else None)): SENSOR,
            _opt(CONF_PV_POWER, c.get(CONF_PV_POWER)): POWER,
        }
    )


def _s_auto(hass: HomeAssistant, c: dict[str, Any]) -> vol.Schema:
    g = _guess_ev(hass) if not c.get(CONF_EV_SWITCH) else {}
    v = lambda k: c.get(k) or g.get(k)  # noqa: E731
    return vol.Schema(
        {
            _req(CONF_EV_SWITCH, v(CONF_EV_SWITCH)): EV_SWITCH,
            _opt(CONF_EV_CURRENT, v(CONF_EV_CURRENT)): EV_CURRENT,
            vol.Required(CONF_EV_PHASES, default=str(c.get(CONF_EV_PHASES, DEFAULT_EV_PHASES))): PHASES(CONF_EV_PHASES),
            _opt(CONF_EV_PLUG, v(CONF_EV_PLUG)): EV_STATE,
            _opt(CONF_EV_CHARGING, v(CONF_EV_CHARGING)): EV_STATE,
            _opt(CONF_EV_POWER, c.get(CONF_EV_POWER)): POWER,
            **_adv(
                {
                    vol.Required(CONF_EV_MIN_A, default=c.get(CONF_EV_MIN_A, DEFAULT_EV_MIN_A)): _num(1, 32, 1, "A"),
                    vol.Required(CONF_EV_MAX_A, default=c.get(CONF_EV_MAX_A, DEFAULT_EV_MAX_A)): _num(1, 80, 1, "A"),
                }
            ),
        }
    )


def _s_auto_moznosti(hass: HomeAssistant, c: dict[str, Any]) -> vol.Schema:
    opts = _select_options(hass, c.get(CONF_EV_SWITCH))
    on, off = _guess_options(opts)
    on = c.get(CONF_EV_ON_OPTION) if c.get(CONF_EV_ON_OPTION) in opts else on
    off = c.get(CONF_EV_OFF_OPTION) if c.get(CONF_EV_OFF_OPTION) in opts else off
    sel = selector.SelectSelector(selector.SelectSelectorConfig(options=opts, mode=selector.SelectSelectorMode.DROPDOWN))
    return vol.Schema({_req(CONF_EV_ON_OPTION, on): sel, _req(CONF_EV_OFF_OPTION, off): sel})


def _s_istic(hass: HomeAssistant, c: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_BREAKER_A, default=c.get(CONF_BREAKER_A, 25)): _num(6, 200, 1, "A"),
            vol.Required(CONF_BREAKER_PHASES, default=str(c.get(CONF_BREAKER_PHASES, 3))): PHASES(CONF_BREAKER_PHASES),
            _opt(CONF_GRID_POWER, c.get(CONF_GRID_POWER)): POWER,
            **_adv(
                {
                    vol.Required(CONF_GRID_INVERT, default=bool(c.get(CONF_GRID_INVERT, False))): BOOL,
                    vol.Required(CONF_BREAKER_RESERVE, default=c.get(CONF_BREAKER_RESERVE, DEFAULT_BREAKER_RESERVE)): _num(0, 50, 1, "%"),
                    _opt(CONF_CABLE_KW, c.get(CONF_CABLE_KW) or None): _num(0, 200, 0.5, "kW"),
                }
            ),
        }
    )


# ---------------------------------------------------------------- kontroly


def _check_ceny(hass: HomeAssistant, d: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    for key in (CONF_PRICE_TODAY, CONF_PRICE_TOMORROW):
        eid = d.get(key)
        if not eid:
            continue
        st = hass.states.get(eid)
        if st is None:
            errors[key] = "entity_not_found"
        elif key == CONF_PRICE_TODAY and st.state not in ("unavailable", "unknown") and not parse_slots(st.attributes):
            errors[key] = "no_prices"
    return errors


def _bad_intervals(text: str | None) -> bool:
    try:
        parse_intervals(text or "")
    except ValueError:
        return True
    return False


def _check_nakup(hass: HomeAssistant, d: dict[str, Any]) -> dict[str, str]:
    return {CONF_NT_INTERVALS: "invalid_intervals"} if _bad_intervals(d.get(CONF_NT_INTERVALS)) else {}


def _check_predaj_pevna(hass: HomeAssistant, d: dict[str, Any]) -> dict[str, str]:
    if _bad_intervals(d.get(CONF_SELL_BANDS)):
        return {CONF_SELL_BANDS: "invalid_intervals"}
    if d.get(CONF_SELL_BANDS) and d.get(CONF_SELL_BAND_PRICE) in (None, ""):
        return {CONF_SELL_BAND_PRICE: "band_price_required"}
    return {}


def _check_entities(*keys: str) -> Callable[[HomeAssistant, dict[str, Any]], dict[str, str]]:
    def check(hass: HomeAssistant, d: dict[str, Any]) -> dict[str, str]:
        for k in keys:
            if d.get(k) and hass.states.get(d[k]) is None:
                return {k: "entity_not_found"}
        return {}

    return check


def _check_auto(hass: HomeAssistant, d: dict[str, Any]) -> dict[str, str]:
    err = _check_entities(CONF_EV_SWITCH, CONF_EV_CURRENT, CONF_EV_PLUG, CONF_EV_CHARGING)(hass, d)
    if err:
        return err
    if _is_select(d.get(CONF_EV_SWITCH)) and len(_select_options(hass, d[CONF_EV_SWITCH])) < 2:
        return {CONF_EV_SWITCH: "no_options"}
    if int(d.get(CONF_EV_MIN_A, 6)) > int(d.get(CONF_EV_MAX_A, 16)):
        return {"base": "ev_min_max"}
    return {}


def _check_moznosti(hass: HomeAssistant, d: dict[str, Any]) -> dict[str, str]:
    return {CONF_EV_OFF_OPTION: "same_option"} if d.get(CONF_EV_ON_OPTION) == d.get(CONF_EV_OFF_OPTION) else {}


STEPS: dict[str, tuple[Callable[[HomeAssistant, dict[str, Any]], vol.Schema], Callable | None]] = {
    "vitaj": (_s_vitaj, None),
    "ceny": (_s_ceny, _check_ceny),
    "nakup": (_s_nakup, _check_nakup),
    "predaj": (_s_predaj, None),
    "predaj_spot": (_s_predaj_spot, None),
    "predaj_pevna": (_s_predaj_pevna, _check_predaj_pevna),
    "bateria": (_s_bateria, _check_entities(CONF_SOC_ENTITY, CONF_HOUSE_SENSOR)),
    "fve": (_s_fve, _check_entities(CONF_PV_TODAY, CONF_PV_TOMORROW, CONF_PV_POWER)),
    "auto": (_s_auto, _check_auto),
    "auto_moznosti": (_s_auto_moznosti, _check_moznosti),
    "istic": (_s_istic, _check_entities(CONF_GRID_POWER)),
}


# staršie kľúče, ktoré nové kroky nahrádzajú
LEGACY = {"bateria": ["house_kw", "house_power_entity"], "istic": ["grid_limit_kw"], "auto": [CONF_EV_ON_OPTION, CONF_EV_OFF_OPTION]}


def _keys(schema: vol.Schema) -> list[str]:
    out: list[str] = []
    for k, v in schema.schema.items():
        if isinstance(v, section):
            out += [str(x) for x in v.schema.schema]
        else:
            out.append(str(k))
    return out


def _flatten(user_input: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in user_input.items():
        if k == ADV and isinstance(v, dict):
            out.update(v)
        else:
            out[k] = v
    for k in EUR_KWH:
        if out.get(k) not in (None, ""):
            out[k] = round(float(out[k]) * 1000, 3)
    return out


def _chain(step: str, d: dict[str, Any]) -> str | None:
    """Podkrok, ktorý patrí k danému kroku (aj pri úprave v Konfigurovať)."""
    if step == "predaj":
        return {SELL_SPOT: "predaj_spot", SELL_FIXED: "predaj_pevna"}.get(sell_mode(d))
    if step == "auto" and _is_select(d.get(CONF_EV_SWITCH)):
        return "auto_moznosti"
    return None


class _StepsMixin:
    """Spoločné kroky pre prvé nastavenie aj pre Konfigurovať."""

    hass: HomeAssistant
    _data: dict[str, Any]

    async def _next(self, step: str) -> ConfigFlowResult:  # pragma: no cover – prepisuje potomok
        raise NotImplementedError

    async def _step(self, step: str, user_input: dict[str, Any] | None) -> ConfigFlowResult:
        build, check = STEPS[step]
        errors: dict[str, str] = {}
        shown = self._data
        if user_input is not None:
            flat = _flatten(user_input)
            errors = check(self.hass, flat) if check else {}
            if not errors:
                for k in _keys(build(self.hass, self._data)) + LEGACY.get(step, []):
                    self._data.pop(k, None)
                self._data.update({k: v for k, v in flat.items() if v not in (None, "") or k == CONF_NT_INTERVALS})
                return await self._next(step)
            shown = {**self._data, **flat}
        return self.async_show_form(step_id=step, data_schema=build(self.hass, shown), errors=errors)  # type: ignore[attr-defined]

    async def async_step_vitaj(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._step("vitaj", user_input)

    async def async_step_ceny(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._step("ceny", user_input)

    async def async_step_nakup(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._step("nakup", user_input)

    async def async_step_predaj(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._step("predaj", user_input)

    async def async_step_predaj_spot(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._step("predaj_spot", user_input)

    async def async_step_predaj_pevna(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._step("predaj_pevna", user_input)

    async def async_step_bateria(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._step("bateria", user_input)

    async def async_step_fve(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._step("fve", user_input)

    async def async_step_auto(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._step("auto", user_input)

    async def async_step_auto_moznosti(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._step("auto_moznosti", user_input)

    async def async_step_istic(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._step("istic", user_input)


def _summary(d: dict[str, Any]) -> dict[str, str]:
    m = sell_mode(d)
    if m == SELL_SPOT:
        predaj = f"spot − {float(d.get(CONF_SELL_FEE, DEFAULT_SELL_FEE)) / 1000:.3f} €/kWh"
    elif m == SELL_FIXED:
        predaj = f"{float(d.get(CONF_SELL_FIXED, 0)) / 1000:.3f} €/kWh"
        if d.get(CONF_SELL_BANDS):
            predaj += f" ({d[CONF_SELL_BANDS]}: {float(d.get(CONF_SELL_BAND_PRICE, 0)) / 1000:.3f} €/kWh)"
    else:
        predaj = "–"
    nt = d.get(CONF_NT_INTERVALS) or "–"
    limit = grid_limit_kw(d)
    return {
        "nakup": f"NT {float(d.get(CONF_PRICE_NT, 0)) / 1000:.3f} €/kWh ({nt}), VT {float(d.get(CONF_PRICE_VT, 0)) / 1000:.3f} €/kWh",
        "predaj": predaj,
        "bateria": f"{d.get(CONF_SOC_ENTITY)}, {d.get(CONF_CAPACITY)} kWh",
        "spotreba": f"{d.get(CONF_HOUSE_KWH)} kWh/deň" + (f" + {d[CONF_HOUSE_SENSOR]}" if d.get(CONF_HOUSE_SENSOR) else ""),
        "fve": d.get(CONF_PV_TODAY) or "–" if d.get(CONF_HAS_PV) else "–",
        "auto": d.get(CONF_EV_SWITCH) or "–" if d.get(CONF_HAS_EV) else "–",
        "limit": f"{limit:.1f} kW" if d.get(CONF_HAS_EV) and limit else "–",
    }


class AiEnergyConfigFlow(_StepsMixin, ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN, raise_on_progress=False)  # nedokončený sprievodca neblokuje nový
        self._abort_if_unique_id_configured()
        return await self.async_step_vitaj()

    async def _next(self, step: str) -> ConfigFlowResult:
        d = self._data
        nxt = _chain(step, d)
        if nxt is None:
            order = ["vitaj", "ceny", "nakup", "predaj", "bateria", "fve", "auto", "istic", "hotovo"]
            base = {"predaj_spot": "predaj", "predaj_pevna": "predaj", "auto_moznosti": "auto"}.get(step, step)
            nxt = order[order.index(base) + 1]
            if nxt == "fve" and not d.get(CONF_HAS_PV):
                nxt = "auto"
            if nxt == "auto" and not d.get(CONF_HAS_EV):
                nxt = "hotovo"
        return await getattr(self, f"async_step_{nxt}")()

    async def async_step_hotovo(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="AI Energy", data=self._data)
        return self.async_show_form(step_id="hotovo", data_schema=vol.Schema({}), description_placeholders=_summary(self._data))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return AiEnergyOptionsFlow()


class AiEnergyOptionsFlow(_StepsMixin, OptionsFlow):
    """Zmena nastavení po inštalácii (Nastavenia → Zariadenia a služby → AI Energy → Konfigurovať)."""

    _data: dict[str, Any]

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        self._data = {**self.config_entry.data, **self.config_entry.options}
        menu = ["vitaj", "ceny", "nakup", "predaj", "bateria"]
        if has_pv(self._data):
            menu.append("fve")
        if self._data.get(CONF_HAS_EV) or has_ev(self._data):
            menu += ["auto", "istic"]
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def _next(self, step: str) -> ConfigFlowResult:
        nxt = _chain(step, self._data)
        if nxt is None and step == "vitaj" and self._data.get(CONF_HAS_EV) and not self._data.get(CONF_EV_SWITCH):
            nxt = "auto"  # práve zapnuté auto → rovno nastaviť nabíjačku
        if nxt is None and step == "auto" and not self._data.get(CONF_BREAKER_A):
            nxt = "istic"
        if nxt is None and step == "auto_moznosti" and not self._data.get(CONF_BREAKER_A):
            nxt = "istic"
        if nxt:
            return await getattr(self, f"async_step_{nxt}")()
        return self.async_create_entry(data=self._data)
