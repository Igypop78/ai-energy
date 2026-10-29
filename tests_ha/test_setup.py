"""Načítanie integrácie: entity sa vytvoria, plán a auto (len odporúča) bežia."""

from unittest.mock import patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ai_energy.const import DOMAIN


async def test_setup_with_ev(hass):
    hass.states.async_set("sensor.okte_prices_today", "unknown")
    hass.states.async_set("sensor.battery_soc", "50", {"unit_of_measurement": "%"})
    hass.states.async_set("select.smartevse_mode", "Off", {"options": ["Off", "Normal"]})
    hass.states.async_set("number.smartevse_charge_current_override", "16")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "price_today": "sensor.okte_prices_today",
            "soc_entity": "sensor.battery_soc",
            "capacity_kwh": 10,
            "house_kwh_day": 12,
            "has_ev": True,
            "ev_switch_entity": "select.smartevse_mode",
            "ev_on_option": "Normal",
            "ev_off_option": "Off",
            "ev_current_entity": "number.smartevse_charge_current_override",
            "breaker_a": 25,
        },
    )
    entry.add_to_hass(hass)
    with patch("custom_components.ai_energy.async_setup", return_value=True):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert hass.states.get("sensor.ai_energy_plan") is not None
    assert hass.states.get("select.ai_energy_auto_rezim").state == "off"
    assert hass.states.get("switch.ai_energy_auto_riadenie").state == "off"
    assert "Len odporúčanie" in hass.states.get("sensor.ai_energy_auto_dovod").state
    await hass.services.async_call("select", "select_option", {"entity_id": "select.ai_energy_auto_rezim", "option": "now"}, blocking=True)
    await hass.async_block_till_done()
    assert "Nabíjať hneď" in hass.states.get("sensor.ai_energy_auto_dovod").state
