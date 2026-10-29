"""Režim nabíjania auta (Vypnuté / Nabíjať hneď / Nabíjať od času / AI)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import AiEnergyConfigEntry
from .const import DOMAIN, EV_MODE
from .entity import device_info
from .ev import EV_MODES


async def async_setup_entry(hass: HomeAssistant, entry: AiEnergyConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    if entry.runtime_data.ev:
        async_add_entities([EvModeSelect(entry)])


class EvModeSelect(SelectEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_translation_key = EV_MODE
    _attr_icon = "mdi:ev-station"
    _attr_options = EV_MODES

    def __init__(self, entry: AiEnergyConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{EV_MODE}"
        self._attr_device_info = device_info(entry)
        self.entity_id = f"select.{DOMAIN}_{EV_MODE}"

    @property
    def current_option(self) -> str:
        return self._entry.runtime_data.ev_settings[EV_MODE]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state in EV_MODES:
            self._entry.runtime_data.ev_settings[EV_MODE] = last.state

    async def async_select_option(self, option: str) -> None:
        self._entry.runtime_data.ev_settings[EV_MODE] = option
        self.async_write_ha_state()
        await self._entry.runtime_data.ev.async_request_refresh()
