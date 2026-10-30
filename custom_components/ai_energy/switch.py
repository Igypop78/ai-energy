"""Prepínače nabíjania auta: Riadenie (vypnuté = len odporúča) a zdroje pre režim AI."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import AiEnergyConfigEntry
from .const import BAT_CONTROL, DOMAIN, EV_CONTROL, EV_USE_NT, EV_USE_PV, EV_USE_SPOT, inverter_enabled
from .entity import device_info

SWITCHES = (
    SwitchEntityDescription(key=EV_CONTROL, translation_key=EV_CONTROL, icon="mdi:steering"),
    SwitchEntityDescription(key=EV_USE_NT, translation_key=EV_USE_NT, icon="mdi:clock-time-four-outline", entity_category=EntityCategory.CONFIG),
    SwitchEntityDescription(key=EV_USE_PV, translation_key=EV_USE_PV, icon="mdi:solar-power-variant", entity_category=EntityCategory.CONFIG),
    SwitchEntityDescription(key=EV_USE_SPOT, translation_key=EV_USE_SPOT, icon="mdi:cash-minus", entity_category=EntityCategory.CONFIG),
)


async def async_setup_entry(hass: HomeAssistant, entry: AiEnergyConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    if entry.runtime_data.ev:
        async_add_entities(EvSwitch(entry, d) for d in SWITCHES)
    if inverter_enabled({**entry.data, **entry.options}):
        async_add_entities([BatControlSwitch(entry, SwitchEntityDescription(key=BAT_CONTROL, translation_key=BAT_CONTROL, icon="mdi:steering"))])


class EvSwitch(SwitchEntity, RestoreEntity):
    _attr_has_entity_name = True

    def __init__(self, entry: AiEnergyConfigEntry, description: SwitchEntityDescription) -> None:
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = device_info(entry)
        self.entity_id = f"switch.{DOMAIN}_{description.key}"

    @property
    def is_on(self) -> bool:
        return bool(self._entry.runtime_data.ev_settings[self.entity_description.key])

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state in ("on", "off"):
            self._entry.runtime_data.ev_settings[self.entity_description.key] = last.state == "on"

    async def _set(self, value: bool) -> None:
        self._entry.runtime_data.ev_settings[self.entity_description.key] = value
        self.async_write_ha_state()
        await self._entry.runtime_data.ev.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)


class BatControlSwitch(EvSwitch):
    """Batéria – riadenie: vypnuté = AI Energy len odporúča, nič neposiela do meniča."""

    @property
    def _store(self) -> dict[str, Any]:
        return self._entry.runtime_data.plan.bat

    @property
    def is_on(self) -> bool:
        return bool(self._store[BAT_CONTROL])

    async def async_added_to_hass(self) -> None:
        await super(EvSwitch, self).async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state in ("on", "off"):
            self._store[BAT_CONTROL] = last.state == "on"

    async def _set(self, value: bool) -> None:
        self._store[BAT_CONTROL] = value
        self.async_write_ha_state()
        await self._entry.runtime_data.plan.async_request_refresh()
