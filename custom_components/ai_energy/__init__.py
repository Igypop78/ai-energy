"""AI Energy – plánovanie batérie a predaja elektriny podľa spotových cien."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import PLATFORMS
from .coordinator import PriceCoordinator

type AiEnergyConfigEntry = ConfigEntry[PriceCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: AiEnergyConfigEntry) -> bool:
    """Nastavenie z UI."""
    coordinator = PriceCoordinator(hass, entry)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()
    coordinator.async_track_sources()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AiEnergyConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: AiEnergyConfigEntry) -> None:
    """Po zmene nastavení (options) integráciu znovu načítaj."""
    await hass.config_entries.async_reload(entry.entry_id)
