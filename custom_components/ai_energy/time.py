"""Čas štartu pre režim „Nabíjať od času“."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import AiEnergyConfigEntry
from .const import DOMAIN, EV_TIME
from .entity import device_info


async def async_setup_entry(hass: HomeAssistant, entry: AiEnergyConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    if entry.runtime_data.ev:
        async_add_entities([EvStartTime(entry)])


class EvStartTime(TimeEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_translation_key = EV_TIME
    _attr_icon = "mdi:clock-start"

    def __init__(self, entry: AiEnergyConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{EV_TIME}"
        self._attr_device_info = device_info(entry)
        self.entity_id = f"time.{DOMAIN}_{EV_TIME}"

    @property
    def native_value(self) -> time:
        return self._entry.runtime_data.ev_settings[EV_TIME]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last:
            try:
                self._entry.runtime_data.ev_settings[EV_TIME] = time.fromisoformat(last.state)
            except ValueError:
                pass

    async def async_set_value(self, value: time) -> None:
        self._entry.runtime_data.ev_settings[EV_TIME] = value
        self.async_write_ha_state()
        await self._entry.runtime_data.ev.async_request_refresh()
