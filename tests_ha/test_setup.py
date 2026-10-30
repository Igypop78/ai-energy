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


async def test_inverter_control(hass):
    from datetime import timedelta

    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_mock_service

    start = dt_util.start_of_local_day()
    period = [{"time": (start + timedelta(minutes=15 * i)).isoformat(), "price": 400 if i % 2 else 100} for i in range(96 * 2)]
    hass.states.async_set("sensor.okte_prices_today", "100", {"period_data": period})
    hass.states.async_set("sensor.battery_soc", "60", {"unit_of_measurement": "%"})
    opts = ["Normal", "Export Now", "Export from Battery", "Zero Export", "Charge from Grid", "Grid Only"]
    hass.states.async_set("input_select.deye_operation_mode", "Normal", {"options": opts})
    calls = async_mock_service(hass, "input_select", "select_option")
    mapping = dict(zip(["normal", "predaj_fve", "predaj", "bez_pretokov", "nabijanie", "siet"], opts))
    data = {"price_today": "sensor.okte_prices_today", "soc_entity": "sensor.battery_soc", "capacity_kwh": 10, "house_kwh_day": 12,
            "inverter_mode_entity": "input_select.deye_operation_mode", **{f"inverter_option_{k}": v for k, v in mapping.items()}}
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)
    with patch("custom_components.ai_energy.async_setup", return_value=True):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert hass.states.get("switch.ai_energy_bateria_riadenie").state == "off"
    assert hass.states.get("select.ai_energy_bateria_rezim").state == "auto"
    assert not calls  # riadenie vypnuté → nič sa neposiela
    assert "Len odporúčanie" in hass.states.get("sensor.ai_energy_dovod").state

    # ručný režim Nabíjanie + zapnuté riadenie → do selectu ide „Charge from Grid“
    await hass.services.async_call("select", "select_option", {"entity_id": "select.ai_energy_bateria_rezim", "option": "nabijanie"}, blocking=True)
    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.ai_energy_bateria_riadenie"}, blocking=True)
    await entry.runtime_data.plan.async_refresh()
    await hass.async_block_till_done()
    assert calls and calls[-1].data["option"] == "Charge from Grid"
    st = hass.states.get("sensor.ai_energy_odporucany_rezim")
    assert st.attributes["aplikovany_rezim"] == "nabijanie" and st.attributes["rucne"] is True
    assert hass.states.get("sensor.ai_energy_dovod").state.startswith("Ručne:")
