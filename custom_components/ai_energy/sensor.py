"""Senzory: ceny (záloha dnes + zajtra) a aktuálna cena."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import AiEnergyConfigEntry
from .const import DOMAIN, SLOT_SECONDS
from .coordinator import PriceCoordinator
from .entity import device_info
from .prices import price_at

UNIT = "€/MWh"


async def async_setup_entry(
    hass: HomeAssistant, entry: AiEnergyConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([PricesSensor(coordinator, entry), CurrentPriceSensor(coordinator, entry)])


class _Base(CoordinatorEntity[PriceCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: PriceCoordinator, entry: AiEnergyConfigEntry, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = device_info(entry)
        # pevné entity_id nezávislé od jazyka HA (sensor.ai_energy_ceny, …)
        self.entity_id = f"sensor.{DOMAIN}_{key}"


class PricesSensor(_Base):
    """Stav = počet uložených 15-min slotov (96 = dnes, 192 = dnes + zajtra).

    Atribút `ceny` = [{t: unix s, p: €/MWh}, …] – formát, ktorý číta Home Price Card.
    """

    _attr_icon = "mdi:database-clock"
    # zoznam cien je veľký – do databázy histórie ho nezapisujeme
    _unrecorded_attributes = frozenset({"ceny"})

    def __init__(self, coordinator: PriceCoordinator, entry: AiEnergyConfigEntry) -> None:
        super().__init__(coordinator, entry, "ceny")

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.get("ceny", []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        ceny = data.get("ceny", [])
        do = (
            dt_util.as_local(dt_util.utc_from_timestamp(ceny[-1]["t"] + SLOT_SECONDS)).isoformat()
            if ceny
            else None
        )
        return {
            "ceny": ceny,
            "zive_sloty": data.get("zive_sloty", 0),
            "posledna_aktualizacia": data.get("posledna_aktualizacia"),
            "ceny_do": do,
        }


class CurrentPriceSensor(_Base):
    """Spotová cena aktuálneho 15-min slotu (zo zálohy, takže funguje aj pri výpadku zdroja)."""

    _attr_icon = "mdi:cash-clock"
    _attr_native_unit_of_measurement = UNIT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: PriceCoordinator, entry: AiEnergyConfigEntry) -> None:
        super().__init__(coordinator, entry, "aktualna_cena")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def _tick(_now: datetime) -> None:
            self.async_write_ha_state()

        # nový slot začína o :00, :15, :30, :45
        self.async_on_remove(async_track_time_change(self.hass, _tick, minute=[0, 15, 30, 45], second=1))

    @property
    def native_value(self) -> float | None:
        return price_at(self.coordinator.data.get("ceny", []), dt_util.utcnow().timestamp(), SLOT_SECONDS)
