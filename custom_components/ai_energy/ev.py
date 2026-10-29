"""Rozhodovanie o nabíjaní auta – čistá logika bez Home Assistant (testuje sa pytestom).

Režimy:
  off   – nenabíja
  now   – nabíja hneď ručne nastaveným prúdom
  time  – čaká na nastavený čas, potom nabíja ručným prúdom; po dobití (10 min bez nabíjania) alebo odpojení vypne
  ai    – nabíja v NT, z prebytku FVE a (voliteľne) pri lacnom spote; prúd drží pod limitom ističa / kábla
"""

from __future__ import annotations

from dataclasses import dataclass
import math

MODE_OFF = "off"
MODE_NOW = "now"
MODE_TIME = "time"
MODE_AI = "ai"
EV_MODES = [MODE_OFF, MODE_NOW, MODE_TIME, MODE_AI]

PV_START_S = 120  # prebytok musí vydržať 2 min, kým sa auto zapne
PV_STOP_S = 180  # nedostatok prebytku 3 min → auto sa vypne (dovtedy beží na minime)
DONE_S = 600  # režim „od času“: 10 min bez nabíjania po nabíjaní = dobité

SELL_MODES = ("predaj", "predaj_fve")  # vtedy ide do siete batéria / drahý predaj – FVE pre auto nepoužiť


@dataclass
class EvConfig:
    phases: int = 3
    min_a: int = 6
    max_a: int = 16
    voltage: float = 230.0
    grid_limit_kw: float = 0.0  # 0 = bez limitu
    cable_kw: float = 0.0  # spoločný limit nabíjania batérie + auta, 0 = bez limitu
    house_kw: float = 0.8  # odhad spotreby domu, ak nemáme meranie odberu
    battery_charge_kw: float = 0.0  # výkon nabíjania batérie zo siete (keď plán nabíja)

    @property
    def wpa(self) -> float:
        """Wattov na 1 A."""
        return self.phases * self.voltage


@dataclass
class EvInputs:
    now: float
    mode: str
    manual_a: int
    time_ts: float | None = None  # dnešný čas štartu (unix s) pre režim „od času“
    connected: bool = True
    charging: bool | None = None  # None = nevieme
    ev_w: float | None = None  # meraný výkon nabíjačky
    grid_w: float | None = None  # odber zo siete (+) / dodávka (−)
    pv_surplus_w: float | None = None  # odhad prebytku FVE, ak nemáme grid_w
    in_nt: bool = False
    spot: float | None = None  # spotová cena teraz €/MWh
    plan_action: str | None = None  # akcia batérie v pláne (N = nabíja zo siete)
    rec_mode: str | None = None  # odporúčaný režim batérie
    use_nt: bool = True
    use_pv: bool = True
    use_spot: bool = False
    spot_limit: float = 0.0
    is_on: bool = False  # nabíjačka je teraz zapnutá
    current_a: float | None = None  # prúd nastavený teraz v nabíjačke


@dataclass
class EvState:
    last_ts: float | None = None
    time_active: bool = False
    seen_charging: bool = False
    idle_since: float | None = None
    pv_ok_since: float | None = None
    pv_bad_since: float | None = None
    pv_on: bool = False


@dataclass
class EvDecision:
    on: bool
    amps: int | None  # None = prúd nemeniť
    dovod: str
    zdroj: str | None = None  # nt / fve / spot / rucne


def _ev_w_now(cfg: EvConfig, inp: EvInputs) -> float:
    if inp.ev_w is not None:
        return max(0.0, inp.ev_w)
    charging = inp.charging if inp.charging is not None else (inp.is_on and inp.connected)
    return (inp.current_a or 0) * cfg.wpa if charging else 0.0


def headroom_a(cfg: EvConfig, inp: EvInputs) -> tuple[int, str | None]:
    """Koľko A môže auto brať, aby sa neprekročil istič ani kábel. Vráti (A, čo obmedzuje)."""
    ev_w = _ev_w_now(cfg, inp)
    bat_w = cfg.battery_charge_kw * 1000 if inp.plan_action == "N" else 0.0
    limits: list[tuple[float, str]] = []
    if cfg.grid_limit_kw > 0:
        if inp.grid_w is not None:
            other = inp.grid_w - ev_w
        else:
            other = cfg.house_kw * 1000 + bat_w
        limits.append((cfg.grid_limit_kw * 1000 - other, "istič"))
    if cfg.cable_kw > 0:
        limits.append((cfg.cable_kw * 1000 - bat_w, "kábel (batéria má prednosť)" if bat_w else "kábel"))
    a, why = cfg.max_a, None
    for w, name in limits:
        x = math.floor(max(0.0, w) / cfg.wpa)
        if x < a:
            a, why = x, name
    return a, why


def _fmt(a: int, cfg: EvConfig) -> str:
    return f"{a} A ({a * cfg.wpa / 1000:.1f} kW)"


def decide(cfg: EvConfig, inp: EvInputs, st: EvState) -> EvDecision:
    """Rozhodne, či má auto nabíjať a akým prúdom. Mení `st` (pamäť medzi volaniami)."""
    first = st.last_ts is None
    prev = st.last_ts
    st.last_ts = inp.now
    manual = max(cfg.min_a, min(cfg.max_a, int(inp.manual_a)))

    if inp.mode != MODE_TIME:
        st.time_active = False
    if inp.mode != MODE_AI:
        st.pv_on = False
        st.pv_ok_since = st.pv_bad_since = None

    if inp.mode == MODE_OFF:
        return EvDecision(False, None, "Vypnuté")

    if inp.mode == MODE_NOW:
        return EvDecision(True, manual, f"Nabíjať hneď: {_fmt(manual, cfg)}", "rucne")

    if inp.mode == MODE_TIME:
        if first and inp.is_on and inp.connected:
            st.time_active = True  # po reštarte HA pokračuj v rozbehnutom nabíjaní
        if inp.time_ts is not None and prev is not None and prev < inp.time_ts <= inp.now:
            st.time_active, st.seen_charging, st.idle_since = True, False, None
        if st.time_active and not inp.connected:
            st.time_active = False
            return EvDecision(False, None, "Od času: auto odpojené – hotovo")
        if st.time_active and inp.charging is not None:
            if inp.charging:
                st.seen_charging, st.idle_since = True, None
            elif st.seen_charging:
                if st.idle_since is None:
                    st.idle_since = inp.now
                if inp.now - st.idle_since >= DONE_S:
                    st.time_active = False
                    return EvDecision(False, None, "Od času: dobité (10 min bez nabíjania)")
        if st.time_active:
            return EvDecision(True, manual, f"Od času: nabíja {_fmt(manual, cfg)}", "rucne")
        return EvDecision(False, None, "Od času: čaká na nastavený čas")

    # ----- AI -----
    if not inp.connected:
        st.pv_on = False
        st.pv_ok_since = st.pv_bad_since = None
        return EvDecision(False, None, "AI: auto nie je pripojené")

    cap, why = headroom_a(cfg, inp)
    limit_txt = f", obmedzuje {why}" if why and cap < cfg.max_a else ""

    grid_src = None
    if inp.use_nt and inp.in_nt:
        grid_src = ("nt", "nízka tarifa")
    elif inp.use_spot and inp.spot is not None and inp.spot <= inp.spot_limit:
        grid_src = ("spot", f"lacný spot {inp.spot:.0f} €/MWh")
    if grid_src:
        st.pv_on = False
        st.pv_ok_since = st.pv_bad_since = None
        if cap < cfg.min_a:
            return EvDecision(False, None, f"AI: {grid_src[1]}, ale nie je rezerva ({why}) – čaká")
        return EvDecision(True, cap, f"AI: {grid_src[1]} – {_fmt(cap, cfg)}{limit_txt}", grid_src[0])

    if not inp.use_pv:
        return EvDecision(False, None, "AI: mimo NT – čaká")
    if inp.rec_mode in SELL_MODES:
        st.pv_on = False
        st.pv_ok_since = st.pv_bad_since = None
        return EvDecision(False, None, "AI: drahá elektrina – predaj má prednosť pred autom")

    ev_w = _ev_w_now(cfg, inp)
    if inp.grid_w is not None:
        surplus = -inp.grid_w + ev_w  # čo by išlo do siete, keby auto nenabíjalo
    elif inp.pv_surplus_w is not None:
        surplus = inp.pv_surplus_w
    else:
        return EvDecision(False, None, "AI: mimo NT – na prebytky FVE chýba meranie odberu alebo FVE")
    pv_a = min(cap, math.floor(max(0.0, surplus) / cfg.wpa))
    kw = surplus / 1000

    if pv_a >= cfg.min_a:
        st.pv_bad_since = None
        if not st.pv_on:
            if st.pv_ok_since is None:
                st.pv_ok_since = inp.now
            if inp.now - st.pv_ok_since < PV_START_S:
                return EvDecision(False, None, f"AI: prebytok FVE {kw:.1f} kW – čakám, či vydrží")
            st.pv_on = True
        return EvDecision(True, pv_a, f"AI: prebytok FVE {kw:.1f} kW – {_fmt(pv_a, cfg)}", "fve")

    st.pv_ok_since = None
    if st.pv_on:
        if st.pv_bad_since is None:
            st.pv_bad_since = inp.now
        if inp.now - st.pv_bad_since < PV_STOP_S:
            return EvDecision(True, cfg.min_a, f"AI: prebytok klesol na {kw:.1f} kW – drží minimum {cfg.min_a} A", "fve")
        st.pv_on = False
        st.pv_bad_since = None
    need = cfg.min_a * cfg.wpa / 1000
    return EvDecision(False, None, f"AI: čaká na NT alebo prebytok FVE ≥ {need:.1f} kW (teraz {max(0.0, kw):.1f} kW)")
