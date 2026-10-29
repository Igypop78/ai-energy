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
    CONF_GRID_INVERT,
    CONF_GRID_POWER,
    CONF_NT_INTERVALS,
    CONF_PRICE_NT,
    CONF_PRICE_VT,
    CONF_PV_POWER,
    CONF_PV_TODAY,
    CONF_PV_TOMORROW,
    CONF_SELL_BAND_PRICE,
    CONF_SELL_BANDS,
    CONF_SELL_FIXED,
    CONF_SOC_ENTITY,
    DEFAULT_CAPACITY,
    DEFAULT_EXPORT_KW,
    DEFAULT_NT_INTERVALS,
    DEFAULT_PRICE_NT,
    DEFAULT_PRICE_VT,
    DOMAIN,
    SET_CHARGE_KW,
    SET_MAX_SOC,
    SET_MIN_SOC,
    SET_PV_CORRECTION,
    SET_THRESHOLD,
    effective_sell_fee,
    house_kw_estimate,
    house_sensor,
    sell_mode,
)
from .coordinator import PriceCoordinator
from .planner import PlanConfig, build_slots, plan, recommend
from .prices import parse_intervals, parse_pv

_LOGGER = logging.getLogger(__name__)

HOUSE_STATS_DAYS = 7
HOUSE_STATS_REFRESH = timedelta(hours=1)
ENERGY_UNITS = {"kwh": 1.0, "wh": 0.001, "mwh": 1000.0}


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


def _intervals(text: str | None) -> list[tuple[int, int]]:
    try:
        return parse_intervals(text or "")
    except ValueError:
        return []


class PlanCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, prices: PriceCoordinator, settings: dict[str, float]) -> None:
        super().__init__(hass, _LOGGER, name=f"{DOMAIN}_plan", update_interval=timedelta(minutes=1), config_entry=entry)
        self.entry = entry
        self.prices = prices
        self.settings = settings
        self._last_mode: str | None = None
        self._house_hist: float | None = None  # priemerná spotreba domu z histórie (kW)
        self._house_hist_at = None

    @property
    def cfg(self) -> dict[str, Any]:
        return {**self.entry.data, **self.entry.options}

    @property
    def house_kw(self) -> float:
        """Priemerná spotreba domu (kW): z histórie senzora, inak z odhadu kWh/deň."""
        return self._house_hist if self._house_hist is not None else house_kw_estimate(self.cfg)

    @property
    def house_source(self) -> str:
        return "história senzora (7 dní)" if self._house_hist is not None else "odhad kWh/deň"

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
            house_kw=self.house_kw,
            threshold=s[SET_THRESHOLD],
            sell_fee=effective_sell_fee(c),
            price_nt=float(c.get(CONF_PRICE_NT, DEFAULT_PRICE_NT)),
            price_vt=float(c.get(CONF_PRICE_VT, DEFAULT_PRICE_VT)),
            nt_intervals=_intervals(c.get(CONF_NT_INTERVALS, DEFAULT_NT_INTERVALS)),
            pv_correction=s[SET_PV_CORRECTION] / 100,
            sell_mode=sell_mode(c),
            sell_fixed=float(c.get(CONF_SELL_FIXED) or 0),
            sell_bands=_intervals(c.get(CONF_SELL_BANDS)),
            sell_band_price=float(c.get(CONF_SELL_BAND_PRICE) or 0),
        )

    async def _async_update_house(self) -> None:
        """Raz za hodinu: priemerná spotreba domu za posledných 7 dní zo štatistík senzora."""
        eid = house_sensor(self.cfg)
        now = dt_util.utcnow()
        if not eid:
            self._house_hist = None
            return
        if self._house_hist_at and now - self._house_hist_at < HOUSE_STATS_REFRESH:
            return
        self._house_hist_at = now
        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.statistics import statistics_during_period

            st = self.hass.states.get(eid)
            unit = ((st.attributes.get("unit_of_measurement") if st else "") or "").lower()
            energy = unit in ENERGY_UNITS
            start = now - timedelta(days=HOUSE_STATS_DAYS)
            types = {"change"} if energy else {"mean"}
            rows = await get_instance(self.hass).async_add_executor_job(
                statistics_during_period, self.hass, start, now, {eid}, "hour", None, types
            )
            data = rows.get(eid, [])
            if energy:
                vals = [r["change"] for r in data if r.get("change") is not None]
                kw = sum(vals) * ENERGY_UNITS[unit] / len(vals) if len(vals) >= 24 else None
            else:
                vals = [r["mean"] for r in data if r.get("mean") is not None]
                kw = (sum(vals) / len(vals)) / (1000 if unit == "w" else 1) if len(vals) >= 24 else None
            self._house_hist = round(kw, 3) if kw is not None and kw > 0 else None
        except Exception as err:  # noqa: BLE001 – bez histórie sa použije odhad
            _LOGGER.debug("Spotreba domu z histórie nedostupná: %s", err)
            self._house_hist = None

    def house_now_kw(self) -> float | None:
        eid = house_sensor(self.cfg)
        st = self.hass.states.get(eid or "")
        if st is None or (st.attributes.get("unit_of_measurement") or "").lower() not in ("w", "kw"):
            return None
        return _kw(self.hass, eid)

    def surplus_kw(self) -> float | None:
        """Prebytok, ktorý práve ide do siete (kW): z merania na elektromere, inak FVE − spotreba domu."""
        c = self.cfg
        grid = _kw(self.hass, c.get(CONF_GRID_POWER))
        if grid is not None:
            return grid if c.get(CONF_GRID_INVERT) else -grid
        pv, house = _kw(self.hass, c.get(CONF_PV_POWER)), self.house_now_kw()
        return pv - house if pv is not None and house is not None else None

    async def _async_update_data(self) -> dict[str, Any]:
        await self._async_update_house()
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

        slots = build_slots(prices, pv, int(now - now % 900), cfg, tz)
        p = plan(slots, now, soc, tz, cfg, self._last_mode)

        pv_kw = _kw(self.hass, c.get(CONF_PV_POWER))
        if pv_kw is None:  # bez merania výkonu FVE použi predpoveď aktuálneho slotu
            cur = next((x for x in slots if x["t"] == int(now - now % 900)), None)
            pv_kw = cur["pv"] * 4 if cur else 0.0
        house_kw = self.house_now_kw()  # okamžitá spotreba domu, ak je senzor domu výkonový
        rec = recommend(p, slots, now, soc, cfg, tz, self._last_mode, pv_kw=pv_kw, house_kw=house_kw)
        self._last_mode = rec.rezim
        return {"plan": p, "rec": rec, "dovod": rec.dovod, "cfg": cfg, "soc": soc}
