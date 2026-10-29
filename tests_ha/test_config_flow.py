"""Sprievodca nastavením a Konfigurovať – celý priechod formulármi."""

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ai_energy.const import DOMAIN


def _states(hass):
    hass.states.async_set("sensor.okte_prices_today", "unknown")
    hass.states.async_set("sensor.okte_prices_tomorrow", "unknown")
    hass.states.async_set("sensor.battery_soc", "50", {"device_class": "battery", "unit_of_measurement": "%"})
    hass.states.async_set("sensor.solcast_pv_forecast_forecast_today", "20")
    hass.states.async_set("select.smartevse_mode", "Off", {"options": ["Off", "Normal", "Solar", "Smart"]})
    hass.states.async_set("number.smartevse_charge_current_override", "16")
    hass.states.async_set("sensor.smartevse_evplugstate", "Connected")
    hass.states.async_set("sensor.smartevse_state", "Ready to Charge")
    hass.states.async_set("sensor.grid_power", "500", {"device_class": "power", "unit_of_measurement": "W"})


def _patch():
    return (
        patch("custom_components.ai_energy.async_setup", return_value=True),
        patch("custom_components.ai_energy.async_setup_entry", return_value=True),
    )


async def test_full_wizard(hass):
    _states(hass)
    p1, p2 = _patch()
    with p1, p2:
        r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        assert r["type"] is FlowResultType.FORM and r["step_id"] == "vitaj"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"has_pv": True, "has_ev": True})
        assert r["step_id"] == "ceny"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"price_today": "sensor.okte_prices_today", "price_tomorrow": "sensor.okte_prices_tomorrow"})
        assert r["step_id"] == "nakup"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"nt_intervals": "23:45-05:45, 13:45-15:45", "price_nt": 0.12, "price_vt": 0.21})
        assert r["step_id"] == "predaj"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"sell_mode": "spot"})
        assert r["step_id"] == "predaj_spot"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"sell_fee": 0.015})
        assert r["step_id"] == "bateria"
        r = await hass.config_entries.flow.async_configure(
            r["flow_id"], {"soc_entity": "sensor.battery_soc", "capacity_kwh": 35, "charge_kw": 10, "export_kw": 10, "house_kwh_day": 18}
        )
        assert r["step_id"] == "fve"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"pv_forecast_today": "sensor.solcast_pv_forecast_forecast_today"})
        assert r["step_id"] == "auto"
        r = await hass.config_entries.flow.async_configure(
            r["flow_id"],
            {
                "ev_switch_entity": "select.smartevse_mode",
                "ev_current_entity": "number.smartevse_charge_current_override",
                "ev_phases": "3",
                "ev_plug_entity": "sensor.smartevse_evplugstate",
                "ev_charging_entity": "sensor.smartevse_state",
                "pokrocile": {"ev_min_a": 6, "ev_max_a": 16},
            },
        )
        assert r["step_id"] == "auto_moznosti"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"ev_on_option": "Normal", "ev_off_option": "Off"})
        assert r["step_id"] == "istic"
        r = await hass.config_entries.flow.async_configure(
            r["flow_id"],
            {"breaker_a": 25, "breaker_phases": "3", "grid_power_entity": "sensor.grid_power", "pokrocile": {"grid_invert": False, "breaker_reserve": 10, "cable_kw": 12}},
        )
        assert r["step_id"] == "hotovo"
        assert "15.5 kW" in r["description_placeholders"]["limit"]
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {})
        assert r["type"] is FlowResultType.CREATE_ENTRY
    d = r["data"]
    assert d["price_nt"] == 120 and d["price_vt"] == 210 and d["sell_fee"] == 15
    assert d["ev_on_option"] == "Normal" and d["ev_off_option"] == "Off"
    assert d["cable_kw"] == 12 and d["breaker_a"] == 25 and d["house_kwh_day"] == 18


async def test_wizard_without_pv_and_ev_and_fixed_sell(hass):
    _states(hass)
    p1, p2 = _patch()
    with p1, p2:
        r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"has_pv": False, "has_ev": False})
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"price_today": "sensor.okte_prices_today"})
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"nt_intervals": "", "price_nt": 0.2, "price_vt": 0.2})
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"sell_mode": "fixed"})
        assert r["step_id"] == "predaj_pevna"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"sell_fixed_price": 0.08, "sell_band_intervals": "17:00-21:00"})
        assert r["errors"] == {"sell_band_price": "band_price_required"}
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"sell_fixed_price": 0.08, "sell_band_intervals": "17:00-21:00", "sell_band_price": 0.15})
        assert r["step_id"] == "bateria"
        r = await hass.config_entries.flow.async_configure(
            r["flow_id"], {"soc_entity": "sensor.battery_soc", "capacity_kwh": 10, "charge_kw": 3, "export_kw": 3, "house_kwh_day": 12}
        )
        assert r["step_id"] == "hotovo"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {})
    d = r["data"]
    assert d["nt_intervals"] == "" and d["sell_mode"] == "fixed" and d["sell_band_price"] == 150


async def test_options_menu_and_switch_ev(hass):
    _states(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"price_today": "sensor.okte_prices_today", "soc_entity": "sensor.battery_soc", "capacity_kwh": 10, "house_kw": 0.8, "house_power_entity": "sensor.grid_power"},
    )
    entry.add_to_hass(hass)
    p1, p2 = _patch()
    with p1, p2:
        r = await hass.config_entries.options.async_init(entry.entry_id)
        assert r["type"] is FlowResultType.MENU and "auto" not in r["menu_options"]
        r = await hass.config_entries.options.async_configure(r["flow_id"], {"next_step_id": "bateria"})
        assert r["step_id"] == "bateria"
        r = await hass.config_entries.options.async_configure(
            r["flow_id"], {"soc_entity": "sensor.battery_soc", "capacity_kwh": 12, "charge_kw": 3, "export_kw": 3, "house_kwh_day": 19.2}
        )
        assert r["type"] is FlowResultType.CREATE_ENTRY
        assert "house_power_entity" not in entry.options and entry.options["capacity_kwh"] == 12

        r = await hass.config_entries.options.async_init(entry.entry_id)
        r = await hass.config_entries.options.async_configure(r["flow_id"], {"next_step_id": "vitaj"})
        r = await hass.config_entries.options.async_configure(r["flow_id"], {"has_pv": False, "has_ev": True})
        assert r["step_id"] == "auto"
        r = await hass.config_entries.options.async_configure(
            r["flow_id"], {"ev_switch_entity": "select.smartevse_mode", "ev_phases": "3", "pokrocile": {"ev_min_a": 6, "ev_max_a": 16}}
        )
        assert r["step_id"] == "auto_moznosti"
        r = await hass.config_entries.options.async_configure(r["flow_id"], {"ev_on_option": "Normal", "ev_off_option": "Off"})
        assert r["step_id"] == "istic"
        r = await hass.config_entries.options.async_configure(r["flow_id"], {"breaker_a": 32, "breaker_phases": "3", "pokrocile": {"grid_invert": True, "breaker_reserve": 10}})
        assert r["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["has_ev"] is True and entry.options["breaker_a"] == 32
