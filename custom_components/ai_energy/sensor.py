"""Senzory: ceny (záloha), aktuálna cena, plán, odporúčaný režim, dôvod, predajná hranica, cieľ NT."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import AiEnergyConfigEntry
from .const import CONF_SOC_ENTITY, DOMAIN, SLOT_SECONDS
from .coordinator import PriceCoordinator
from .entity import device_info
from .ev_controller import EvController
from .plan_coordinator import PlanCoordinator
from .planner import MODE_CHARGE, MODE_GRID, MODE_NO_EXPORT, MODE_NORMAL, MODE_SELL, MODE_SELL_PV
from .prices import price_at

UNIT = "€/MWh"


async def async_setup_entry(
    hass: HomeAssistant, entry: AiEnergyConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    d = entry.runtime_data
    async_add_entities(
        [
            PricesSensor(d.prices, entry),
            CurrentPriceSensor(d.prices, entry),
            PlanSensor(d.plan, entry),
            ModeSensor(d.plan, entry),
            ReasonSensor(d.plan, entry),
            ThresholdNowSensor(d.plan, entry),
            TargetSocSensor(d.plan, entry),
        ]
    )
    if d.ev:
        async_add_entities([EvReasonSensor(d.ev, entry)])


class _Base(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: AiEnergyConfigEntry, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = device_info(entry)
        # pevné entity_id nezávislé od jazyka HA (sensor.ai_energy_ceny, …)
        self.entity_id = f"sensor.{DOMAIN}_{key}"


# ------------------------------------------------------------------ ceny


class PricesSensor(_Base):
    """Stav = počet uložených 15-min slotov (96 = dnes, 192 = dnes + zajtra).

    Atribút `ceny` = [{t: unix s, p: €/MWh}, …] – formát, ktorý číta Igy Price Action Card.
    """

    coordinator: PriceCoordinator
    _attr_icon = "mdi:database-clock"
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
        do = dt_util.as_local(dt_util.utc_from_timestamp(ceny[-1]["t"] + SLOT_SECONDS)).isoformat() if ceny else None
        return {
            "ceny": ceny,
            "zive_sloty": data.get("zive_sloty", 0),
            "posledna_aktualizacia": data.get("posledna_aktualizacia"),
            "ceny_do": do,
        }


class CurrentPriceSensor(_Base):
    """Spotová cena aktuálneho 15-min slotu (zo zálohy, takže funguje aj pri výpadku zdroja)."""

    coordinator: PriceCoordinator
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

        self.async_on_remove(async_track_time_change(self.hass, _tick, minute=[0, 15, 30, 45], second=1))

    @property
    def native_value(self) -> float | None:
        return price_at(self.coordinator.data.get("ceny", []), dt_util.utcnow().timestamp(), SLOT_SECONDS)


# ------------------------------------------------------------------ plán


class PlanSensor(_Base):
    """Plán po 15 min. Stav = akcia aktuálneho slotu, atribút `sloty` = [[t, SOC, akcia], …]."""

    coordinator: PlanCoordinator
    _attr_icon = "mdi:robot-outline"
    _unrecorded_attributes = frozenset({"sloty", "okna"})

    def __init__(self, coordinator: PlanCoordinator, entry: AiEnergyConfigEntry) -> None:
        super().__init__(coordinator, entry, "plan")

    @property
    def native_value(self) -> str | None:
        p = self.coordinator.data.get("plan")
        return p.sloty[0][2] if p and p.sloty else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.coordinator.data
        p, cfg = d.get("plan"), d.get("cfg")
        if not p:
            return {"dovod": d.get("dovod")}
        return {
            "sloty": p.sloty,
            "okna": [
                {"od": w.od, "do": w.do, "typ": w.typ, "hranica": round(w.hranica, 1), "ciel_nt": round(w.ciel), "fve_kwh": round(w.fve_kwh, 1)}
                for w in p.okna
            ],
            "koniec": p.koniec,
            "predaj_kwh": round(p.predaj_kwh, 1),
            "trzba": round(p.trzba, 2),
            "nakup_kwh": round(p.nakup_kwh, 1),
            "nakup_eur": round(p.nakup_eur, 2),
            "fve_kwh": round(p.fve_kwh, 1),
            "prah": cfg.threshold,
            "min_soc": cfg.min_soc,
            "max_soc": cfg.max_soc,
            "soc": d.get("soc"),
            "soc_entity": self.coordinator.cfg.get(CONF_SOC_ENTITY),
        }


class ModeSensor(_Base):
    """Odporúčaný režim pre aktuálnu chvíľu (zatiaľ len odporúča, nič neprepína)."""

    coordinator: PlanCoordinator
    _attr_icon = "mdi:battery-sync"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [MODE_SELL, MODE_SELL_PV, MODE_CHARGE, MODE_GRID, MODE_NO_EXPORT, MODE_NORMAL]

    def __init__(self, coordinator: PlanCoordinator, entry: AiEnergyConfigEntry) -> None:
        super().__init__(coordinator, entry, "odporucany_rezim")

    @property
    def native_value(self) -> str | None:
        rec = self.coordinator.data.get("rec")
        return rec.rezim if rec else MODE_NORMAL

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"dovod": self.coordinator.data.get("dovod")}


class ReasonSensor(_Base):
    """Prečo – text, ktorý vysvetľuje odporúčaný režim."""

    coordinator: PlanCoordinator
    _attr_icon = "mdi:comment-question-outline"

    def __init__(self, coordinator: PlanCoordinator, entry: AiEnergyConfigEntry) -> None:
        super().__init__(coordinator, entry, "dovod")

    @property
    def native_value(self) -> str | None:
        d = self.coordinator.data.get("dovod")
        return d[:255] if d else None


class ThresholdNowSensor(_Base):
    """Predajná hranica aktuálneho okna – sloty s cenou nad ňou sa predajú."""

    coordinator: PlanCoordinator
    _attr_icon = "mdi:cash-check"
    _attr_native_unit_of_measurement = UNIT
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: PlanCoordinator, entry: AiEnergyConfigEntry) -> None:
        super().__init__(coordinator, entry, "predajna_hranica")

    @property
    def native_value(self) -> float | None:
        rec = self.coordinator.data.get("rec")
        return round(rec.okno.hranica, 1) if rec and rec.okno and rec.okno.hranica else None


class TargetSocSensor(_Base):
    """Na koľko % sa batéria nabije v najbližšej nízkej tarife."""

    coordinator: PlanCoordinator
    _attr_icon = "mdi:battery-arrow-up"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: PlanCoordinator, entry: AiEnergyConfigEntry) -> None:
        super().__init__(coordinator, entry, "ciel_nt")

    @property
    def native_value(self) -> float | None:
        p = self.coordinator.data.get("plan")
        if not p:
            return None
        now = dt_util.utcnow().timestamp()
        nxt = next((w for w in p.okna if w.nt_do > now), None)
        return round(nxt.ciel) if nxt else None


# ------------------------------------------------------------------ auto


class EvReasonSensor(_Base):
    """Čo robí nabíjanie auta a prečo. Atribúty: zapnúť, prúd, zdroj (nt/fve/spot/rucne), riadenie."""

    coordinator: EvController
    _attr_icon = "mdi:car-electric"

    def __init__(self, coordinator: EvController, entry: AiEnergyConfigEntry) -> None:
        super().__init__(coordinator, entry, "auto_dovod")

    @property
    def native_value(self) -> str | None:
        d = self.coordinator.data or {}
        return (d.get("dovod") or "")[:255] or None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.coordinator.data or {}
        return {
            "nabijat": d.get("on"),
            "prud": d.get("amps"),
            "zdroj": d.get("zdroj"),
            "riadenie": d.get("riadenie"),
            "pripojene": d.get("pripojene"),
            "nabija": d.get("nabija"),
            "chyba": d.get("chyba"),
            "fazy": self.coordinator.ev_config().phases,
        }
