"""Riadenie nabíjačky auta: každú minútu (a pri zmenách) rozhodne a nastaví nabíjačku."""

from __future__ import annotations

from datetime import datetime, time, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CABLE_KW,
    CONF_EV_CHARGING,
    CONF_EV_CURRENT,
    CONF_EV_MAX_A,
    CONF_EV_MIN_A,
    CONF_EV_OFF_OPTION,
    CONF_EV_ON_OPTION,
    CONF_EV_PHASES,
    CONF_EV_PLUG,
    CONF_EV_POWER,
    CONF_EV_SWITCH,
    CONF_GRID_INVERT,
    CONF_GRID_POWER,
    CONF_NT_INTERVALS,
    DEFAULT_CABLE_KW,
    DEFAULT_EV_MAX_A,
    DEFAULT_EV_MIN_A,
    DEFAULT_EV_PHASES,
    DEFAULT_NT_INTERVALS,
    DOMAIN,
    EV_CONTROL,
    EV_MANUAL_A,
    EV_MODE,
    EV_SPOT_LIMIT,
    EV_TIME,
    EV_USE_NT,
    EV_USE_PV,
    EV_USE_SPOT,
    SET_CHARGE_KW,
    grid_limit_kw,
    has_ev,
)
from .ev import MODE_OFF, EvConfig, EvDecision, EvInputs, EvState, decide
from .plan_coordinator import PlanCoordinator, _kw
from .prices import is_in_intervals, parse_intervals, price_at

_LOGGER = logging.getLogger(__name__)

ON_STATES = {"on", "true", "connected", "plugged", "plugged in", "charging", "home"}


def ev_enabled(cfg: dict[str, Any]) -> bool:
    return has_ev(cfg)


def default_ev_settings(cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        EV_MODE: MODE_OFF,
        EV_TIME: time(23, 45),
        EV_MANUAL_A: float(cfg.get(CONF_EV_MAX_A, DEFAULT_EV_MAX_A)),
        EV_SPOT_LIMIT: 0.0,
        EV_USE_NT: True,
        EV_USE_PV: True,
        EV_USE_SPOT: False,
        EV_CONTROL: False,
    }


def _truthy(state: str | None) -> bool | None:
    """Stav entity → áno/nie (binary_sensor, alebo text ako Connected / Charging)."""
    if state is None or state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return None
    s = state.strip().lower()
    if s in ON_STATES:
        return True
    if s.startswith("charging") and "stop" not in s:
        return True
    if "connect" in s and "disconnect" not in s and "not" not in s:
        return True
    return False


class EvController(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, plan: PlanCoordinator, settings: dict[str, Any]) -> None:
        super().__init__(hass, _LOGGER, name=f"{DOMAIN}_auto", update_interval=timedelta(minutes=1), config_entry=entry)
        self.entry = entry
        self.plan = plan
        self.settings = settings
        self.state = EvState()

    @property
    def cfg(self) -> dict[str, Any]:
        return {**self.entry.data, **self.entry.options}

    def ev_config(self) -> EvConfig:
        c = self.cfg
        return EvConfig(
            phases=int(c.get(CONF_EV_PHASES, DEFAULT_EV_PHASES)),
            min_a=int(c.get(CONF_EV_MIN_A, DEFAULT_EV_MIN_A)),
            max_a=int(c.get(CONF_EV_MAX_A, DEFAULT_EV_MAX_A)),
            grid_limit_kw=grid_limit_kw(c),
            cable_kw=float(c.get(CONF_CABLE_KW, DEFAULT_CABLE_KW) or 0),
            house_kw=self.plan.house_kw,
            battery_charge_kw=float(self.plan.settings.get(SET_CHARGE_KW, 0)),
        )

    @callback
    def async_track_inputs(self) -> None:
        c = self.cfg
        ids = [c.get(k) for k in (CONF_EV_PLUG, CONF_EV_CHARGING, CONF_EV_SWITCH)]

        @callback
        def _changed(_event: Event[EventStateChangedData]) -> None:
            self.hass.async_create_task(self.async_request_refresh())

        self.entry.async_on_unload(async_track_state_change_event(self.hass, [i for i in ids if i], _changed))

        # odber zo siete: prepočítať hneď len pri prekročení limitu ističa (inak stačí raz za minútu)
        grid = c.get(CONF_GRID_POWER)
        limit = grid_limit_kw(c)
        if grid and limit > 0:

            @callback
            def _grid(_event: Event[EventStateChangedData]) -> None:
                w = self._grid_w()
                if w is not None and w > limit * 1000:
                    self.hass.async_create_task(self.async_request_refresh())

            self.entry.async_on_unload(async_track_state_change_event(self.hass, [grid], _grid))

    # ------------------------------------------------------------ vstupy

    def _state(self, key: str) -> str | None:
        eid = self.cfg.get(key)
        st = self.hass.states.get(eid) if eid else None
        return st.state if st else None

    def _grid_w(self) -> float | None:
        kw = _kw(self.hass, self.cfg.get(CONF_GRID_POWER))
        if kw is None:
            return None
        return -kw * 1000 if self.cfg.get(CONF_GRID_INVERT) else kw * 1000

    def _is_on(self) -> bool:
        c = self.cfg
        st = self._state(CONF_EV_SWITCH)
        if st is None:
            return False
        if (c.get(CONF_EV_SWITCH) or "").split(".")[0] in ("select", "input_select"):
            return st == c.get(CONF_EV_ON_OPTION)
        return st == "on"

    def _current_a(self) -> float | None:
        try:
            return float(self._state(CONF_EV_CURRENT))
        except (TypeError, ValueError):
            return None

    def _inputs(self) -> EvInputs:
        c, s = self.cfg, self.settings
        now = dt_util.now()
        ts = now.timestamp()
        t: time = s[EV_TIME]
        time_ts = datetime.combine(now.date(), t, tzinfo=now.tzinfo).timestamp()

        connected = _truthy(self._state(CONF_EV_PLUG)) if c.get(CONF_EV_PLUG) else True
        ev_kw = _kw(self.hass, c.get(CONF_EV_POWER))
        if ev_kw is not None:
            charging: bool | None = ev_kw > 0.5
        elif c.get(CONF_EV_CHARGING):
            charging = _truthy(self._state(CONF_EV_CHARGING))
        else:
            charging = None

        sk = self.plan.surplus_kw() if c.get(CONF_GRID_POWER) is None else None  # bez elektromera: FVE − dom
        surplus = sk * 1000 if sk is not None else None

        pd = self.plan.data or {}
        p, rec = pd.get("plan"), pd.get("rec")
        prices = (self.plan.prices.data or {}).get("ceny", [])
        intervals = parse_intervals(c.get(CONF_NT_INTERVALS, DEFAULT_NT_INTERVALS))

        return EvInputs(
            now=ts,
            mode=s[EV_MODE],
            manual_a=int(s[EV_MANUAL_A]),
            time_ts=time_ts,
            connected=connected is not False,
            charging=charging,
            ev_w=ev_kw * 1000 if ev_kw is not None else None,
            grid_w=self._grid_w(),
            pv_surplus_w=surplus,
            in_nt=is_in_intervals(now.hour * 60 + now.minute, intervals),
            spot=price_at(prices, ts),
            plan_action=p.sloty[0][2] if p and p.sloty else None,
            rec_mode=rec.rezim if rec else None,
            use_nt=s[EV_USE_NT],
            use_pv=s[EV_USE_PV],
            use_spot=s[EV_USE_SPOT],
            spot_limit=float(s[EV_SPOT_LIMIT]),
            is_on=self._is_on(),
            current_a=self._current_a(),
        )

    # ------------------------------------------------------------ výstup

    async def _apply(self, d: EvDecision) -> list[str]:
        """Nastaví nabíjačku. Vráti zoznam toho, čo sa zmenilo (pre záznam)."""
        c, done = self.cfg, []
        cur_id, sw_id = c.get(CONF_EV_CURRENT), c.get(CONF_EV_SWITCH)

        if d.on and d.amps is not None and cur_id:
            cur = self._current_a()
            if cur is not None and abs(cur - d.amps) >= 0.5:
                domain = cur_id.split(".")[0]
                await self.hass.services.async_call(domain, "set_value", {"entity_id": cur_id, "value": d.amps}, blocking=True)
                done.append(f"prúd {d.amps} A")

        if sw_id and self._state(CONF_EV_SWITCH) not in (None, STATE_UNAVAILABLE, STATE_UNKNOWN) and self._is_on() != d.on:
            domain = sw_id.split(".")[0]
            if domain in ("select", "input_select"):
                opt = c.get(CONF_EV_ON_OPTION) if d.on else c.get(CONF_EV_OFF_OPTION)
                if opt:
                    await self.hass.services.async_call(domain, "select_option", {"entity_id": sw_id, "option": opt}, blocking=True)
                    done.append(opt)
            else:
                await self.hass.services.async_call(domain, "turn_on" if d.on else "turn_off", {"entity_id": sw_id}, blocking=True)
                done.append("zapnuté" if d.on else "vypnuté")
        return done

    async def _async_update_data(self) -> dict[str, Any]:
        inp = self._inputs()
        d = decide(self.ev_config(), inp, self.state)
        control = bool(self.settings[EV_CONTROL])
        dovod, chyba = d.dovod, None
        if control:
            try:
                zmeny = await self._apply(d)
                if zmeny:
                    _LOGGER.info("AI Energy auto: %s (%s)", ", ".join(zmeny), d.dovod)
            except Exception as err:  # noqa: BLE001 – nabíjačka môže byť nedostupná, skúsi sa o minútu znova
                chyba = str(err)
                dovod = f"{d.dovod} – chyba nabíjačky: {err}"
                _LOGGER.warning("AI Energy auto: nepodarilo sa nastaviť nabíjačku: %s", err)
        else:
            dovod = f"Len odporúčanie (Riadenie vypnuté) – {d.dovod}"
        return {
            "on": d.on,
            "amps": d.amps,
            "zdroj": d.zdroj,
            "dovod": dovod,
            "chyba": chyba,
            "pripojene": inp.connected,
            "nabija": inp.charging,
            "riadenie": control,
        }
