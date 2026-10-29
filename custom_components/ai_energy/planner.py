"""Plánovač batérie – čistá logika bez závislosti na Home Assistant.

Prenos simulácie „AI plán“ (Jinja) do Pythonu, zovšeobecnený na ľubovoľné intervaly NT.

Princíp:
- Deň sa delí na **okná**. Každé okno začína pri jednom NT (keď sa batéria nabíja lacno)
  a končí, keď začína ďalšie. V okne sa batéria predá v najdrahších 15-min slotoch
  (top N podľa toho, koľko energie bude k dispozícii) – „predajná hranica“.
- **Cieľ NT** = koľko treba nabiť, aby pokrylo predaje v okne (mínus prebytok FVE, ktorý príde pred nimi).
- Energia, ktorá v okne ostane, sa prenáša do ďalšieho okna.
- V noci (NT pred ďalším oknom) sa môžu predať aj ďalšie sloty nad prahom, ak sa batéria
  stihne dobiť na ranný cieľ (nočná arbitráž).
- Predaj z batérie nikdy pod min SOC; keď je batéria na minime a svieti slnko,
  predáva sa len prebytok FVE (Export Now).

Akcie v pláne (1 písmeno – kompaktné pre atribúty a kartu):
  P predaj z batérie, E predaj len z FVE, N nabíjanie zo siete, G dom zo siete (batéria stojí),
  F FVE nabíja batériu, O batéria plná / prebytok do siete, D dom z batérie
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, tzinfo
import math
from typing import Any

SLOT = 900

# odporúčané režimy (stav senzora odporúčaného režimu)
MODE_SELL = "predaj"  # predaj z batérie (Export from Battery)
MODE_SELL_PV = "predaj_fve"  # predaj len z FVE (Export Now)
MODE_CHARGE = "nabijanie"  # nabíjanie zo siete (Charge from Grid)
MODE_GRID = "siet"  # dom zo siete, batéria stojí (Grid Only)
MODE_NO_EXPORT = "bez_pretokov"  # zakázať pretoky (Zero Export)
MODE_NORMAL = "normal"  # bežná prevádzka (Normal)


@dataclass
class PlanConfig:
    capacity_kwh: float = 34.0
    min_soc: float = 15.0
    max_soc: float = 95.0
    charge_kw: float = 8.0  # nabíjanie zo siete
    export_kw: float = 10.0  # predaj z batérie (výkon meniča)
    house_kw: float = 0.8  # priemerná spotreba domu
    threshold: float = 233.0  # min. predajná cena €/MWh
    sell_fee: float = 15.0  # výkupca strháva €/MWh
    price_nt: float = 120.0  # €/MWh
    price_vt: float = 210.0  # €/MWh
    nt_intervals: Sequence[tuple[int, int]] = ((1425, 345), (825, 945))  # minúty od polnoci
    pv_correction: float = 0.8
    hysteresis_soc: float = 3.0

    @property
    def kwh_slot(self) -> float:
        return self.export_kw * SLOT / 3600

    @property
    def house_slot(self) -> float:
        return self.house_kw * SLOT / 3600


@dataclass
class Window:
    od: int
    do: int
    nt_od: int
    nt_do: int
    nt2: int  # začiatok ďalšieho NT, ak leží vnútri okna (nočná arbitráž), inak 0
    typ: str = ""
    ciel: float = 0.0
    hranica: float = 0.0
    predaj: set[int] = field(default_factory=set)
    fve_kwh: float = 0.0


@dataclass
class Plan:
    sloty: list[list[Any]]  # [[t, soc, akcia], ...]
    okna: list[Window]
    predaj_kwh: float = 0.0
    trzba: float = 0.0
    nakup_kwh: float = 0.0
    nakup_eur: float = 0.0
    fve_kwh: float = 0.0
    koniec: int = 0


# ---------------------------------------------------------------- vstupy


def build_slots(
    prices: Iterable[Mapping[str, float]],
    pv_forecast: Iterable[tuple[int, float]],
    start_ts: int,
    cfg: PlanConfig,
) -> list[dict[str, float]]:
    """Ceny od aktuálneho slotu + predpoveď FVE (kWh za slot, s korekciou) a prebytok nad spotrebou domu."""
    pv = sorted(pv_forecast)
    out = []
    for slot in sorted(prices, key=lambda s: s["t"]):
        t = int(slot["t"])
        if t < start_ts:
            continue
        # predpoveď s periódou do 30 min: posledná perióda, ktorá začala najneskôr v t
        kw = 0.0
        for pt, pk in pv:
            if t - 1800 < pt <= t:
                kw = pk
        e_pv = kw * SLOT / 3600 * cfg.pv_correction
        out.append({"t": t, "p": float(slot["p"]), "pv": e_pv, "pb": max(0.0, e_pv - cfg.house_slot)})
    return out


def nt_windows(now_ts: int, tz: tzinfo, intervals: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """Absolútne NT okná (začiatok, koniec) od včera do pozajtra, zoradené."""
    day0 = datetime.fromtimestamp(now_ts, tz).date()
    out = []
    for d in range(-1, 3):
        day = day0 + timedelta(days=d)
        for start, end in intervals:
            s = datetime.combine(day, time(start // 60, start % 60), tz)
            e_day = day + timedelta(days=1) if end <= start else day
            e = datetime.combine(e_day, time(end // 60, end % 60), tz)
            out.append((int(s.timestamp()), int(e.timestamp())))
    return sorted(set(out))


def make_windows(now_ts: int, tz: tzinfo, cfg: PlanConfig) -> list[Window]:
    """Okná medzi NT. Okno začína pri NT – pri dlhom NT až v čase, keď sa z min stihne nabiť na max."""
    t_full = (cfg.max_soc - cfg.min_soc) / 100 * cfg.capacity_kwh / max(cfg.charge_kw, 0.1) * 3600
    nts = nt_windows(now_ts, tz, cfg.nt_intervals)
    starts = [max(s, e - t_full) for s, e in nts]
    wins = []
    for i in range(len(nts) - 1):
        s, e = nts[i]
        nxt_start = nts[i + 1][0]
        nt2 = nxt_start if nxt_start < starts[i + 1] else 0
        od = int(starts[i])
        hod = datetime.fromtimestamp(od, tz).hour
        wins.append(Window(od=od, do=int(starts[i + 1]), nt_od=s, nt_do=e, nt2=nt2, typ="ráno" if hod < 12 else "večer"))
    return wins


# ---------------------------------------------------------------- plán


def plan(
    slots: list[dict[str, float]],
    now_ts: float,
    soc: float,
    tz: tzinfo,
    cfg: PlanConfig,
    current_mode: str | None = None,
) -> Plan:
    """Naplánuje okná (predajné sloty, cieľ NT) a odsimuluje SOC slot po slote."""
    slot0 = int(now_ts - now_ts % SLOT)
    kwh_slot = cfg.kwh_slot
    kap = cfg.capacity_kwh
    windows = [w for w in make_windows(int(now_ts), tz, cfg) if w.do > now_ts]

    # 1) okná: cieľ NT, koľko energie bude na predaj, ktoré sloty predať
    carry = -1.0
    for w in windows:
        start = max(w.od, slot0)
        psl = [x for x in slots if start <= x["t"] < w.do]
        nad = [x for x in psl if x["p"] >= cfg.threshold]
        pb_spolu = sum(x["pb"] for x in psl)
        kum = maxk = 0.0
        for y in psl:
            kum = max(kum - y["pb"] + (kwh_slot if y["p"] >= cfg.threshold else 0.0), -(100 - cfg.min_soc) / 100 * kap)
            maxk = max(maxk, kum)
        w.ciel = min(cfg.max_soc, cfg.min_soc + maxk / kap * 100) if psl else cfg.max_soc
        e_ciel = (w.ciel - cfg.min_soc) / 100 * kap
        nt_h = max(0.0, (w.nt_do - max(w.nt_od, now_ts)) / 3600)
        if w.od <= now_ts:
            e_teraz = max(0.0, (soc - cfg.min_soc) / 100 * kap)
            # prebiehajúci predaj: energia už predaná v tomto slote sa zarátava späť
            kredit = kwh_slot * (now_ts - slot0) / SLOT if current_mode == MODE_SELL else 0.0
            e = e_teraz + kredit + max(0.0, min(e_ciel - e_teraz, nt_h * cfg.charge_kw)) + pb_spolu
        else:
            e0 = max(0.0, carry)
            e = max(e0, min(e_ciel, e0 + nt_h * cfg.charge_kw)) + pb_spolu
        n = math.ceil(e / kwh_slot - 1e-9) if e > 0 else 0
        top = sorted(nad, key=lambda x: -x["p"])[:n]
        top_t = {int(x["t"]) for x in top}
        extra = {int(x["t"]) for x in nad if w.nt2 and x["t"] >= w.nt2} - top_t
        w.predaj = top_t | extra
        w.hranica = top[-1]["p"] if top else 0.0
        w.fve_kwh = sum(x["pv"] for x in psl)
        vt_od = max(start, w.nt_do)
        vt_do = w.nt2 if w.nt2 else w.do
        vt_h = max(0.0, (vt_do - vt_od) / 3600)
        predane = min(e, len(top) * kwh_slot)
        carry = max(0.0, e - predane - cfg.house_kw * vt_h)

    # 2) simulácia slot po slote
    out = Plan(sloty=[], okna=windows)
    s = soc
    posledna = "predaj" if current_mode == MODE_SELL else ""
    hs = cfg.house_slot
    for x in slots:
        t = int(x["t"])
        pool = next((w for w in windows if w.od <= t < w.do), None)
        if pool is None:
            continue
        ntw = next((w for w in windows if w.nt_od <= t < w.nt_do), None)
        je_nt = ntw is not None
        ciel = ntw.ciel if ntw else 0.0
        avail = (s - cfg.min_soc) / 100 * kap
        out.fve_kwh += x["pv"]
        noc_ok = _night_ok(t, s, avail, pool, ntw, cfg)
        energia_ok = avail >= 0.3 if posledna == "predaj" else (avail >= 0.3 and avail + x["pb"] >= kwh_slot)

        if t in pool.predaj and energia_ok and noc_ok:
            akcia = "P"
            z_bat = min(max(0.0, avail), max(0.0, kwh_slot + hs - x["pv"]))
            export = min(kwh_slot, z_bat + x["pv"] - hs)
            s -= z_bat / kap * 100
            out.predaj_kwh += export
            out.trzba += (x["p"] - cfg.sell_fee) * export / 1000
        elif t in pool.predaj and not je_nt and x["pb"] >= 0.25:
            akcia = "E"
            out.predaj_kwh += x["pb"]
            out.trzba += (x["p"] - cfg.sell_fee) * x["pb"] / 1000
        elif je_nt and s < ciel:
            akcia = "N"
            kwh = min(cfg.charge_kw * SLOT / 3600 + x["pb"], (ciel - s) / 100 * kap)
            s += kwh / kap * 100
            out.nakup_kwh += max(0.0, kwh - x["pb"])
        elif je_nt:
            akcia = "G"
            s = min(100.0, s + x["pv"] / kap * 100)
        else:
            net = x["pv"] - hs
            if net > 0:
                nabite = min(net, (100 - s) / 100 * kap)
                pretok = net - nabite
                s += nabite / kap * 100
                out.predaj_kwh += pretok
                if x["p"] > cfg.sell_fee:
                    out.trzba += (x["p"] - cfg.sell_fee) * pretok / 1000
                akcia = "F" if nabite >= 0.1 else ("O" if pretok >= 0.1 else "D")
            else:
                akcia = "D"
                s = max(5.0, s + net / kap * 100)
        posledna = "predaj" if akcia == "P" else akcia
        out.sloty.append([t, round(s, 1), akcia])
        out.koniec = t + SLOT

    # nákup v NT vrátane strát nabíjania (~10 %)
    out.nakup_kwh = out.nakup_kwh / 0.9
    out.nakup_eur = out.nakup_kwh * cfg.price_nt / 1000
    return out


def _night_ok(t: int, s: float, avail: float, pool: Window, ntw: Window | None, cfg: PlanConfig) -> bool:
    """Predaj v NT, ktoré patrí ďalšiemu oknu: len ak sa batéria potom stihne dobiť na jeho cieľ."""
    if ntw is None or ntw is pool:
        return True
    termin = min([ntw.nt_do, *ntw.predaj])
    soc_po = s - min(cfg.kwh_slot, avail) / cfg.capacity_kwh * 100
    treba_s = max(0.0, ntw.ciel - soc_po) / 100 * cfg.capacity_kwh / max(cfg.charge_kw, 0.1) * 3600
    return t + SLOT + treba_s <= termin


# ---------------------------------------------------------------- odporúčanie pre aktuálnu chvíľu


@dataclass
class Recommendation:
    rezim: str
    dovod: str
    okno: Window | None = None


def recommend(
    p: Plan,
    slots: list[dict[str, float]],
    now_ts: float,
    soc: float,
    cfg: PlanConfig,
    tz: tzinfo,
    current_mode: str | None = None,
    pv_kw: float = 0.0,
    house_kw: float | None = None,
    price_now: float | None = None,
) -> Recommendation:
    """Čo robiť práve teraz – rovnaké pravidlá ako simulácia + hysterézia skutočného času."""
    slot0 = int(now_ts - now_ts % SLOT)
    pool = next((w for w in p.okna if w.od <= slot0 < w.do), None)
    ntw = next((w for w in p.okna if w.nt_od <= slot0 < w.nt_do), None)
    je_nt = ntw is not None
    cur = next((x for x in slots if x["t"] == slot0), None)
    cena = price_now if price_now is not None else (cur["p"] if cur else None)
    c = f"{cena:.0f}" if cena is not None else "?"
    s_txt = f"{soc:.0f} %"
    if pool is None:
        return Recommendation(MODE_NORMAL, "Bez cien – bežná prevádzka", None)

    avail = (soc - cfg.min_soc) / 100 * cfg.capacity_kwh
    pb_teraz = cur["pb"] if cur else 0.0
    v_plane = slot0 in pool.predaj
    noc_ok = _night_ok(slot0, soc, avail, pool, ntw, cfg)
    zvysok = cfg.kwh_slot * (slot0 + SLOT - now_ts) / SLOT
    if current_mode == MODE_SELL:
        energia_ok = avail >= 0.3
    elif je_nt:
        energia_ok = (now_ts - slot0) < 180 and avail >= 0.3 and avail + pb_teraz >= cfg.kwh_slot
    else:
        energia_ok = avail >= 0.3 and avail + pb_teraz >= max(1.0, zvysok) and (slot0 + SLOT - now_ts) >= 300
    predaj = v_plane and energia_ok and noc_ok

    dom = house_kw if house_kw is not None else cfg.house_kw
    prebytok = pv_kw - dom
    export_fve = v_plane and not predaj and not je_nt and (prebytok >= 1.0 or (current_mode == MODE_SELL_PV and prebytok >= 0.3))
    ciel = ntw.ciel if ntw else 0.0
    nabijat = je_nt and ((current_mode == MODE_CHARGE and soc < ciel) or soc < ciel - cfg.hysteresis_soc)
    okno = f"{pool.typ} do {datetime.fromtimestamp(pool.do, tz).strftime('%H:%M')}"

    if predaj:
        hr = pool.hranica if pool.hranica > 0 else cfg.threshold
        return Recommendation(MODE_SELL, f"Predaj {c} € ≥ hranica {hr:.0f} € ({okno}, SOC {s_txt} / min {cfg.min_soc:.0f} %)", pool)
    if export_fve:
        return Recommendation(MODE_SELL_PV, f"Predaj len z FVE {prebytok:.1f} kW za {c} € – batéria na minime ({s_txt}), nevybíja sa", pool)
    if nabijat:
        return Recommendation(MODE_CHARGE, f"NT nabíjanie: SOC {s_txt} → {ciel:.0f} %", pool)
    if cena is not None and cena <= cfg.sell_fee and pv_kw > 0.5:
        return Recommendation(MODE_NO_EXPORT, f"Cena {c} € ≤ {cfg.sell_fee:.0f} € – predaj by bol v strate, bez pretokov", pool)
    if je_nt:
        return Recommendation(MODE_GRID, f"NT: SOC {s_txt} ≥ cieľ {ciel:.0f} % – dom zo siete, batéria sa šetrí", pool)
    if v_plane and not noc_ok:
        return Recommendation(MODE_NORMAL, "Nočný predaj vynechaný – nestihlo by sa dobiť na ranný cieľ", pool)
    if pool.hranica > 0 and avail >= 1:
        return Recommendation(MODE_NORMAL, f"Čakám: {c} € < hranica {pool.hranica:.0f} € ({okno})", pool)
    return Recommendation(MODE_NORMAL, f"Dom z batérie, nič na predaj (SOC {s_txt})", pool)
