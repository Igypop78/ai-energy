"""Koordinátor: zbiera ceny zo zdrojových senzorov a drží ich lokálnu zálohu."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_PRICE_TODAY,
    CONF_PRICE_TOMORROW,
    DOMAIN,
    STORAGE_KEY,
    STORAGE_VERSION,
    UPDATE_MINUTES,
)
from .prices import merge_slots, parse_slots

_LOGGER = logging.getLogger(__name__)


class PriceCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Ceny dnes + zajtra so zálohou.

    - Pri každej zmene zdrojových senzorov a každých 15 min zoberie platné ceny.
    - Zlúči ich s uloženými (nové majú prednosť), zahodí včerajšok.
    - Keď je zdroj nedostupný, ostanú posledné uložené ceny – aj po reštarte HA.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_ceny",
            update_interval=timedelta(minutes=UPDATE_MINUTES),
            config_entry=entry,
        )
        self.entry = entry
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}")
        self._stored: dict[str, Any] = {"ceny": [], "posledna_aktualizacia": None}

    @property
    def source_entities(self) -> list[str]:
        cfg = {**self.entry.data, **self.entry.options}
        return [e for e in (cfg.get(CONF_PRICE_TODAY), cfg.get(CONF_PRICE_TOMORROW)) if e]

    async def async_load(self) -> None:
        """Načíta zálohu z disku (pred prvým refreshom)."""
        data = await self._store.async_load()
        if isinstance(data, dict) and isinstance(data.get("ceny"), list):
            self._stored = data

    @callback
    def async_track_sources(self) -> None:
        """Prepočet hneď pri zmene zdrojových senzorov."""

        @callback
        def _changed(event: Event[EventStateChangedData]) -> None:
            self.hass.async_create_task(self.async_request_refresh())

        self.entry.async_on_unload(async_track_state_change_event(self.hass, self.source_entities, _changed))

    async def _async_update_data(self) -> dict[str, Any]:
        midnight = int(dt_util.start_of_local_day().timestamp())
        new: list[dict[str, float]] = []
        for entity_id in self.source_entities:
            state = self.hass.states.get(entity_id)
            if state is None or state.state in ("unavailable", "unknown"):
                continue
            new.extend(parse_slots(state.attributes))

        merged = merge_slots(self._stored.get("ceny", []), new, midnight)
        live = len([s for s in new if s["t"] >= midnight])
        last = dt_util.now().isoformat() if live else self._stored.get("posledna_aktualizacia")

        if merged != self._stored.get("ceny") or last != self._stored.get("posledna_aktualizacia"):
            self._stored = {"ceny": merged, "posledna_aktualizacia": last}
            await self._store.async_save(self._stored)

        return {"ceny": merged, "zive_sloty": live, "posledna_aktualizacia": last}
