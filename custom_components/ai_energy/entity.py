"""Spoločný základ entít – všetky patria pod jedno zariadenie „AI Energy“."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import DOMAIN


def device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="AI Energy",
        manufacturer="AI Energy",
        model="Plánovač batérie",
        entry_type=DeviceEntryType.SERVICE,
        configuration_url="https://github.com/Igypop78/ai-energy",
    )
