"""Testy plánovača (bez Home Assistant)."""

from datetime import datetime, timedelta
import importlib.util
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import pytest

_path = Path(__file__).parents[1] / "custom_components" / "ai_energy" / "planner.py"
_spec = importlib.util.spec_from_file_location("ai_energy_planner", _path)
P = importlib.util.module_from_spec(_spec)
sys.modules["ai_energy_planner"] = P
_spec.loader.exec_module(P)

TZ = ZoneInfo("Europe/Bratislava")
D0 = datetime(2026, 10, 28, tzinfo=TZ)


def ts(day: int, h: int, m: int = 0) -> int:
    return int(datetime(2026, 10, day, h, m, tzinfo=TZ).timestamp())


def prices(fn, days=(28, 29)):
    """Ceny po 15 min; fn(hodina_float) -> €/MWh."""
    out = []
    for d in days:
        start = datetime(2026, 10, d, tzinfo=TZ)
        for i in range(96):
            t = start + timedelta(minutes=15 * i)
            out.append({"t": int(t.timestamp()), "p": float(fn(t.hour + t.minute / 60))})
    return out


def sun(peak):
    """Predpoveď FVE po 30 min (sínus 7–16 h)."""
    import math

    out = []
    for d in (28, 29):
        start = datetime(2026, 10, d, tzinfo=TZ)
        for i in range(48):
            h = i / 2
            kw = peak * math.sin(math.pi * (h - 7) / 9) if 7 < h < 16 else 0.0
            out.append((int((start + timedelta(minutes=30 * i)).timestamp()), kw))
    return out


def evening_peak(h):
    if 16 <= h < 22:
        return 340
    if 6.5 <= h < 9:
        return 290
    return 200


CFG = P.PlanConfig(capacity_kwh=34, min_soc=20, max_soc=100, charge_kw=9.5, threshold=250, sell_fee=15, pv_correction=0.8)


def run(now, soc, price_fn=evening_peak, pv=(), mode=None, cfg=CFG):
    sl = P.build_slots(prices(price_fn), list(pv), int(now - now % 900), cfg)
    return sl, P.plan(sl, now, soc, TZ, cfg, mode)


def test_windows_zse():
    w = P.make_windows(ts(28, 12), TZ, CFG)
    vecer = next(x for x in w if x.od == ts(28, 13, 45))
    assert vecer.nt_od == ts(28, 13, 45) and vecer.nt_do == ts(28, 15, 45)
    assert vecer.nt2 == ts(28, 23, 45)  # nočné NT leží vo večernom okne -> nočná arbitráž
    rano = next(x for x in w if x.nt_od == ts(28, 23, 45))
    # dlhé nočné NT: okno začína, keď sa z min stihne nabiť na max (80 % z 34 kWh pri 9,5 kW ≈ 2,9 h)
    assert ts(29, 2, 40) < rano.od < ts(29, 2, 55)
    assert vecer.do == rano.od


def test_sells_down_to_min_soc_in_evening():
    # poobede je SOC 63 %, poobedné NT dobije, večer celé nad prahom -> predá až po min
    _, p = run(ts(28, 12, 50), 63)
    predaje = [s for s in p.sloty if ts(28, 16) <= s[0] < ts(28, 23, 45) and s[2] == "P"]
    assert len(predaje) >= 10
    # po poslednom predaji je batéria na min SOC (dom potom ide z batérie – to min SOC nestráži)
    assert predaje[-1][1] == pytest.approx(CFG.min_soc, abs=1)


def test_never_sells_below_min():
    _, p = run(ts(28, 6), 30)
    for _, soc, a in p.sloty:
        if a == "P":
            assert soc >= CFG.min_soc - 0.01


def test_export_now_when_battery_at_min_and_sun():
    sl, p = run(ts(28, 7, 30), 19, pv=sun(12))
    rano = [a for t, _, a in p.sloty if ts(28, 8) <= t < ts(28, 9)]
    assert "E" in rano and "P" not in rano
    r = P.recommend(p, sl, ts(28, 8, 5), 19, CFG, TZ, P.MODE_SELL, pv_kw=4.0, house_kw=0.8)
    assert r.rezim == P.MODE_SELL_PV


def test_no_sale_without_energy_even_if_in_plan():
    # 20,5 % pri min 20 % = 0,17 kWh nad minimom -> predaj končí
    sl, p = run(ts(28, 18, 20), 20.5)
    r = P.recommend(p, sl, ts(28, 18, 20), 20.5, CFG, TZ, P.MODE_SELL)
    assert r.rezim != P.MODE_SELL


def test_charges_in_nt_to_target():
    sl, p = run(ts(28, 23, 50), 22)
    r = P.recommend(p, sl, ts(28, 23, 50), 22, CFG, TZ)
    assert r.rezim == P.MODE_CHARGE
    rano = next(w for w in p.okna if w.nt_od == ts(28, 23, 45))
    nt = [s for s in p.sloty if ts(28, 23, 45) <= s[0] < ts(29, 5, 45)]
    assert rano.ciel > 80
    assert max(soc for _, soc, _ in nt) == pytest.approx(rano.ciel, abs=1)


def test_grid_only_when_charged_in_nt():
    sl, p = run(ts(29, 4, 50), 100)
    r = P.recommend(p, sl, ts(29, 4, 50), 100, CFG, TZ, P.MODE_GRID)
    assert r.rezim == P.MODE_GRID


def test_night_sale_only_at_slot_start():
    # v NT sa nový predaj začína len na začiatku slotu (proti kmitaniu)
    hi = lambda h: 340 if h < 1 or 16 <= h < 22 or 6.5 <= h < 9 else 200  # noqa: E731
    sl, p = run(ts(29, 0, 1), 60, price_fn=hi)
    assert P.recommend(p, sl, ts(29, 0, 1), 60, CFG, TZ).rezim == P.MODE_SELL
    sl, p = run(ts(29, 0, 7), 60, price_fn=hi)
    assert P.recommend(p, sl, ts(29, 0, 7), 60, CFG, TZ).rezim != P.MODE_SELL


def test_zero_export_on_negative_price():
    neg = lambda h: -20 if 11 <= h < 14 else 150  # noqa: E731
    sl, p = run(ts(28, 12), 100, price_fn=neg, pv=sun(10))
    r = P.recommend(p, sl, ts(28, 12), 100, CFG, TZ, pv_kw=6)
    assert r.rezim == P.MODE_NO_EXPORT


def test_custom_tariff_single_nt():
    cfg = P.PlanConfig(capacity_kwh=20, min_soc=10, max_soc=90, charge_kw=5, threshold=200, nt_intervals=((1320, 360),))
    w = P.make_windows(ts(28, 12), TZ, cfg)
    assert all(x.do > x.od for x in w)
    sl, p = run(ts(28, 12), 50, cfg=cfg)
    assert p.sloty and all(cfg.min_soc - 0.01 <= s or a != "P" for _, s, a in p.sloty)


def _cfg(**kw):
    from dataclasses import replace

    return replace(CFG, **kw)


def test_no_sell_mode_never_sells():
    cfg = _cfg(sell_mode="none")
    sl, p = run(ts(28, 12, 50), 63, cfg=cfg)
    assert not any(a in ("P", "E") for _, _, a in p.sloty)
    assert all(x["s"] < 0 for x in sl)
    rec = P.recommend(p, sl, ts(28, 17), 63, cfg, TZ, pv_kw=2.0)
    assert rec.rezim == P.MODE_NO_EXPORT


def test_fixed_sell_price_uses_bands():
    # pevný výkup 100 €/MWh, večer 18–21 h 300 €/MWh → predáva sa len v pásme
    cfg = _cfg(sell_mode="fixed", sell_fee=0, sell_fixed=100, sell_bands=((18 * 60, 21 * 60),), sell_band_price=300, threshold=250)
    sl = P.build_slots(prices(evening_peak), [], ts(28, 12, 45), cfg, TZ)
    assert next(x for x in sl if x["t"] == ts(28, 19))["s"] == 300
    assert next(x for x in sl if x["t"] == ts(28, 17))["s"] == 100
    p = P.plan(sl, ts(28, 12, 50), 63, TZ, cfg)
    predaje = [t for t, _, a in p.sloty if a == "P"]
    assert predaje and all(ts(28, 18) <= t < ts(28, 21) or t >= ts(29, 18) for t in predaje)


def test_spot_sell_price_is_spot_minus_fee():
    sl = P.build_slots(prices(evening_peak), [], ts(28, 12), CFG, TZ)
    assert next(x for x in sl if x["t"] == ts(28, 17))["s"] == 340 - 15


def test_single_tariff_plans_without_grid_charging():
    cfg = _cfg(nt_intervals=())
    _, p = run(ts(28, 12, 50), 80, cfg=cfg)
    assert p.sloty and not any(a in ("N", "G") for _, _, a in p.sloty)
    assert any(a == "P" for _, _, a in p.sloty)  # večer predá to, čo v batérii je


def test_nt_charges_for_house_when_cheaper_than_vt():
    # nič na predaj (ceny pod prahom) – v noci sa batéria nabije na spotrebu domu do poobedňajšej NT
    flat = lambda h: 150
    cfg = _cfg(house_kw=0.8)
    _, p = run(ts(28, 22), 20, price_fn=flat, cfg=cfg)
    rano = next(w for w in p.okna if w.nt_od == ts(28, 23, 45))
    need = 0.8 * 8 / 34 * 100  # 05:45–13:45 VT, 0,8 kW, bez slnka
    assert rano.ciel == pytest.approx(cfg.min_soc + need, abs=1.5)
    assert any(a == "N" for t, _, a in p.sloty if ts(28, 23, 45) <= t < ts(29, 5, 45))
    assert not any(a == "P" for _, _, a in p.sloty)


def test_no_house_charging_when_vt_is_cheap():
    cfg = _cfg(house_kw=0.8, price_vt=150)  # 120/0,9 + 45 = 178 > 150 → neoplatí sa
    _, p = run(ts(28, 22), 20, price_fn=lambda h: 150, cfg=cfg)
    rano = next(w for w in p.okna if w.nt_od == ts(28, 23, 45))
    assert rano.ciel == pytest.approx(cfg.min_soc, abs=0.5)
