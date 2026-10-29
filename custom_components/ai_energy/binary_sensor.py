"""Binárny senzor: práve platí nízka tarifa (NT)."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from . import AiEnergyConfigEntry
from .const import CONF_NT_INTERVALS, DEFAULT_NT_INTERVALS, DOMAIN
from .entity import device_info
from .prices import is_in_intervals, parse_intervals


async def async_setup_entry(
    hass: HomeAssistant, entry: AiEnergyConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([LowTariffSensor(entry)])


class LowTariffSensor(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "nizka_tarifa"
    _attr_icon = "mdi:clock-time-four-outline"

    def __init__(self, entry: AiEnergyConfigEntry) -> None:
        cfg = {**entry.data, **entry.options}
        self._text = cfg.get(CONF_NT_INTERVALS, DEFAULT_NT_INTERVALS)
        self._intervals = parse_intervals(self._text)
        self._attr_unique_id = f"{entry.entry_id}_nizka_tarifa"
        self.entity_id = f"binary_sensor.{DOMAIN}_nizka_tarifa"
        self._attr_device_info = device_info(entry)
        self._attr_extra_state_attributes = {"intervaly": self._text}

    async def async_added_to_hass(self) -> None:
        @callback
        def _tick(_now: datetime) -> None:
            self.async_write_ha_state()

        self.async_on_remove(async_track_time_change(self.hass, _tick, second=0))

    @property
    def is_on(self) -> bool:
        now = dt_util.now()
        return is_in_intervals(now.hour * 60 + now.minute, self._intervals)
