"""Koordinátor plánu: každú minútu (a pri zmene vstupov) prepočíta plán a odporúčaný režim."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CAPACITY,
    CONF_EXPORT_KW,
    CONF_HOUSE_KW,
    CONF_HOUSE_POWER,
    CONF_NT_INTERVALS,
    CONF_PRICE_NT,
    CONF_PRICE_VT,
    CONF_PV_POWER,
    CONF_PV_TODAY,
    CONF_PV_TOMORROW,
    CONF_SELL_FEE,
    CONF_SOC_ENTITY,
    DEFAULT_CAPACITY,
    DEFAULT_EXPORT_KW,
    DEFAULT_HOUSE_KW,
    DEFAULT_NT_INTERVALS,
    DEFAULT_PRICE_NT,
    DEFAULT_PRICE_VT,
    DEFAULT_SELL_FEE,
    DOMAIN,
    SET_CHARGE_KW,
    SET_MAX_SOC,
    SET_MIN_SOC,
    SET_PV_CORRECTION,
    SET_THRESHOLD,
)
from .coordinator import PriceCoordinator
from .planner import PlanConfig, build_slots, plan, recommend
from .prices import parse_intervals, parse_pv

_LOGGER = logging.getLogger(__name__)


def _kw(hass: HomeAssistant, entity_id: str | None) -> float | None:
    """Výkon zo senzora v kW (W sa prepočíta podľa jednotky)."""
    if not entity_id:
        return None
    st = hass.states.get(entity_id)
    if st is None:
        return None
    try:
        v = float(st.state)
    except ValueError:
        return None
    unit = (st.attributes.get("unit_of_measurement") or "").lower()
    return v / 1000 if unit == "w" else v


class PlanCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, prices: PriceCoordinator, settings: dict[str, float]) -> None:
        super().__init__(hass, _LOGGER, name=f"{DOMAIN}_plan", update_interval=timedelta(minutes=1), config_entry=entry)
        self.entry = entry
        self.prices = prices
        self.settings = settings
        self._last_mode: str | None = None

    @property
    def cfg(self) -> dict[str, Any]:
        return {**self.entry.data, **self.entry.options}

    @callback
    def async_track_inputs(self) -> None:
        """Prepočet pri zmene cien, SOC alebo predpovede FVE."""
        ids = [self.cfg.get(k) for k in (CONF_SOC_ENTITY, CONF_PV_TODAY, CONF_PV_TOMORROW)]

        @callback
        def _changed(_event: Event[EventStateChangedData]) -> None:
            self.hass.async_create_task(self.async_request_refresh())

        self.entry.async_on_unload(async_track_state_change_event(self.hass, [i for i in ids if i], _changed))
        self.entry.async_on_unload(self.prices.async_add_listener(lambda: self.hass.async_create_task(self.async_request_refresh())))

    def plan_config(self) -> PlanConfig:
        c, s = self.cfg, self.settings
        return PlanConfig(
            capacity_kwh=float(c.get(CONF_CAPACITY, DEFAULT_CAPACITY)),
            min_soc=s[SET_MIN_SOC],
            max_soc=s[SET_MAX_SOC],
            charge_kw=s[SET_CHARGE_KW],
            export_kw=float(c.get(CONF_EXPORT_KW, DEFAULT_EXPORT_KW)),
            house_kw=float(c.get(CONF_HOUSE_KW, DEFAULT_HOUSE_KW)),
            threshold=s[SET_THRESHOLD],
            sell_fee=float(c.get(CONF_SELL_FEE, DEFAULT_SELL_FEE)),
            price_nt=float(c.get(CONF_PRICE_NT, DEFAULT_PRICE_NT)),
            price_vt=float(c.get(CONF_PRICE_VT, DEFAULT_PRICE_VT)),
            nt_intervals=parse_intervals(c.get(CONF_NT_INTERVALS, DEFAULT_NT_INTERVALS)),
            pv_correction=s[SET_PV_CORRECTION] / 100,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        cfg = self.plan_config()
        c = self.cfg
        now = dt_util.utcnow().timestamp()
        tz = dt_util.get_default_time_zone()

        soc_state = self.hass.states.get(c.get(CONF_SOC_ENTITY, ""))
        try:
            soc = float(soc_state.state) if soc_state else None
        except ValueError:
            soc = None
        prices = (self.prices.data or {}).get("ceny", [])
        if soc is None or not prices:
            dovod = "Chýba SOC batérie" if soc is None else "Chýbajú ceny"
            return {"plan": None, "rec": None, "dovod": dovod, "cfg": cfg, "soc": soc}

        pv: list[tuple[int, float]] = []
        for key in (CONF_PV_TODAY, CONF_PV_TOMORROW):
            st = self.hass.states.get(c.get(key) or "")
            if st is not None:
                pv.extend(parse_pv(st.attributes))

        slots = build_slots(prices, pv, int(now - now % 900), cfg)
        p = plan(slots, now, soc, tz, cfg, self._last_mode)
        pv_kw = _kw(self.hass, c.get(CONF_PV_POWER))
        house_kw = _kw(self.hass, c.get(CONF_HOUSE_POWER))
        if pv_kw is None:  # bez merania výkonu FVE použi predpoveď aktuálneho slotu
            cur = next((x for x in slots if x["t"] == int(now - now % 900)), None)
            pv_kw = cur["pv"] * 4 if cur else 0.0
        rec = recommend(p, slots, now, soc, cfg, tz, self._last_mode, pv_kw=pv_kw, house_kw=house_kw)
        self._last_mode = rec.rezim
        return {"plan": p, "rec": rec, "dovod": rec.dovod, "cfg": cfg, "soc": soc}
