"""Nastavenia plánovača ako entity – menia sa priamo z dashboardu a hneď prepočítajú plán."""

from __future__ import annotations

from homeassistant.components.number import NumberEntityDescription, NumberMode, RestoreNumber
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AiEnergyConfigEntry
from .const import DOMAIN, SET_CHARGE_KW, SET_MAX_SOC, SET_MIN_SOC, SET_PV_CORRECTION, SET_THRESHOLD
from .entity import device_info


SETTINGS = (
    NumberEntityDescription(key=SET_THRESHOLD, translation_key=SET_THRESHOLD, icon="mdi:cash-lock", native_min_value=0, native_max_value=1000, native_step=5, native_unit_of_measurement="€/MWh", mode=NumberMode.BOX),
    NumberEntityDescription(key=SET_MIN_SOC, translation_key=SET_MIN_SOC, icon="mdi:battery-10", native_min_value=5, native_max_value=80, native_step=1, native_unit_of_measurement=PERCENTAGE, mode=NumberMode.SLIDER),
    NumberEntityDescription(key=SET_MAX_SOC, translation_key=SET_MAX_SOC, icon="mdi:battery-90", native_min_value=30, native_max_value=100, native_step=1, native_unit_of_measurement=PERCENTAGE, mode=NumberMode.SLIDER),
    NumberEntityDescription(key=SET_CHARGE_KW, translation_key=SET_CHARGE_KW, icon="mdi:transmission-tower-import", native_min_value=0.5, native_max_value=30, native_step=0.5, native_unit_of_measurement=UnitOfPower.KILO_WATT, mode=NumberMode.BOX),
    NumberEntityDescription(key=SET_PV_CORRECTION, translation_key=SET_PV_CORRECTION, icon="mdi:solar-power-variant", native_min_value=20, native_max_value=150, native_step=5, native_unit_of_measurement=PERCENTAGE, mode=NumberMode.SLIDER),
)


async def async_setup_entry(hass: HomeAssistant, entry: AiEnergyConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities(SettingNumber(entry, d) for d in SETTINGS)


class SettingNumber(RestoreNumber):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: AiEnergyConfigEntry, description: NumberEntityDescription) -> None:
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = device_info(entry)
        self.entity_id = f"number.{DOMAIN}_{description.key}"
        self._attr_native_value = entry.runtime_data.settings[description.key]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            await self._apply(float(last.native_value), refresh=True)

    async def async_set_native_value(self, value: float) -> None:
        await self._apply(value, refresh=True)

    async def _apply(self, value: float, refresh: bool) -> None:
        self._attr_native_value = value
        self._entry.runtime_data.settings[self.entity_description.key] = value
        self.async_write_ha_state()
        if refresh:
            await self._entry.runtime_data.plan.async_request_refresh()
