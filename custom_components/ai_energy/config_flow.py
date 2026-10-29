"""Sprievodca nastavením AI Energy (UI)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
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
                return self.async_create_entry(title="AI Energy", data=self._data)
        return self.async_show_form(step_id="bateria", data_schema=_battery_schema(self.hass, user_input or {}), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return AiEnergyOptionsFlow()


class AiEnergyOptionsFlow(OptionsFlow):
    """Zmena nastavení po inštalácii (Nastavenia → Integrácie → AI Energy → Konfigurovať)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        cfg = {**self.config_entry.data, **self.config_entry.options}
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = {**_check_prices(self.hass, user_input), **_check_tariff(user_input), **_check_battery(self.hass, user_input)}
            if not errors:
                return self.async_create_entry(data=user_input)
            cfg.update(user_input)
        schema = vol.Schema({**_prices_schema(self.hass, cfg).schema, **_tariff_schema(cfg).schema, **_battery_schema(self.hass, cfg).schema})
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
