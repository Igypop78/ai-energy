"""Testy rozhodovania o nabíjaní auta (bez Home Assistant)."""

import importlib.util
from pathlib import Path
import sys

_path = Path(__file__).parents[1] / "custom_components" / "ai_energy" / "ev.py"
_spec = importlib.util.spec_from_file_location("ai_energy_ev", _path)
E = importlib.util.module_from_spec(_spec)
sys.modules["ai_energy_ev"] = E
_spec.loader.exec_module(E)

CFG = E.EvConfig(phases=3, min_a=6, max_a=16, grid_limit_kw=14.5, cable_kw=12, house_kw=0.8, battery_charge_kw=10)


def inp(**kw):
    base = dict(now=1000.0, mode=E.MODE_AI, manual_a=16)
    base.update(kw)
    return E.EvInputs(**base)


def test_off_and_now():
    st = E.EvState()
    assert E.decide(CFG, inp(mode=E.MODE_OFF), st).on is False
    d = E.decide(CFG, inp(mode=E.MODE_NOW, manual_a=10), st)
    assert d.on and d.amps == 10


def test_manual_current_clamped():
    d = E.decide(CFG, inp(mode=E.MODE_NOW, manual_a=40), E.EvState())
    assert d.amps == 16


def test_nt_full_current_without_battery():
    d = E.decide(CFG, inp(in_nt=True, grid_w=800), E.EvState())
    assert d.on and d.amps == 16 and d.zdroj == "nt"


def test_nt_battery_has_priority_on_cable():
    # batéria nabíja 10 kW → na kábli 12 kW ostáva 2 kW < 6 A → auto čaká
    d = E.decide(CFG, inp(in_nt=True, plan_action="N", grid_w=10800), E.EvState())
    assert d.on is False and "kábel" in d.dovod


def test_nt_grid_limit_measured():
    # odber 12 kW bez auta → rezerva 2,5 kW → 3 A < 6 → čaká; pri 9 kW rezerva 5,5 kW → 7 A
    assert E.decide(CFG, inp(in_nt=True, grid_w=12000), E.EvState()).on is False
    d = E.decide(CFG, inp(in_nt=True, grid_w=9000), E.EvState())
    assert d.on and d.amps == 7


def test_grid_limit_counts_own_ev_power():
    # auto berie 16 A (11 kW), celkový odber 12 kW → dom 1 kW → rezerva 13,5 kW → 16 A ostáva
    d = E.decide(CFG, inp(in_nt=True, grid_w=12040, is_on=True, current_a=16), E.EvState())
    assert d.amps == 16


def test_not_connected():
    d = E.decide(CFG, inp(in_nt=True, connected=False), E.EvState())
    assert d.on is False


def test_pv_surplus_start_delay_and_run():
    st = E.EvState()
    d = E.decide(CFG, inp(now=0, grid_w=-6000), st)
    assert d.on is False and "čakám" in d.dovod
    d = E.decide(CFG, inp(now=60, grid_w=-6000), st)
    assert d.on is False
    d = E.decide(CFG, inp(now=130, grid_w=-6000), st)
    assert d.on and d.amps == 8 and d.zdroj == "fve"
    # auto už berie 8 A (5,52 kW), do siete ide ešte 0,5 kW → 8 A
    d = E.decide(CFG, inp(now=190, grid_w=-500, is_on=True, current_a=8, ev_w=5520), st)
    assert d.on and d.amps == 8


def test_pv_surplus_drop_holds_min_then_stops():
    st = E.EvState(pv_on=True, last_ts=0)
    d = E.decide(CFG, inp(now=60, grid_w=2000, is_on=True, current_a=6, ev_w=4140), st)
    assert d.on and d.amps == 6
    d = E.decide(CFG, inp(now=200, grid_w=2000, is_on=True, current_a=6, ev_w=4140), st)
    assert d.on
    d = E.decide(CFG, inp(now=250, grid_w=2000, is_on=True, current_a=6, ev_w=4140), st)
    assert d.on is False


def test_pv_not_used_while_selling():
    st = E.EvState()
    d = E.decide(CFG, inp(now=0, grid_w=-8000, rec_mode="predaj"), st)
    assert d.on is False and "predaj" in d.dovod


def test_cheap_spot():
    d = E.decide(CFG, inp(use_spot=True, spot=-5, spot_limit=0, grid_w=500), E.EvState())
    assert d.on and d.zdroj == "spot"
    d = E.decide(CFG, inp(use_spot=True, spot=50, spot_limit=0, grid_w=500), E.EvState())
    assert d.on is False


def test_nt_disabled():
    d = E.decide(CFG, inp(in_nt=True, use_nt=False, use_pv=False), E.EvState())
    assert d.on is False


def test_time_mode_waits_starts_and_finishes():
    st = E.EvState()
    t = 10_000
    base = dict(mode=E.MODE_TIME, manual_a=12, time_ts=t)
    assert E.decide(CFG, inp(now=t - 120, **base), st).on is False
    assert E.decide(CFG, inp(now=t - 60, charging=False, **base), st).on is False
    d = E.decide(CFG, inp(now=t + 5, charging=False, **base), st)
    assert d.on and d.amps == 12
    assert E.decide(CFG, inp(now=t + 60, charging=True, **base), st).on
    assert E.decide(CFG, inp(now=t + 3600, charging=False, **base), st).on  # práve dobilo
    d = E.decide(CFG, inp(now=t + 3600 + 600, charging=False, **base), st)
    assert d.on is False and "dobité" in d.dovod
    # ďalšie volania už nezapnú (čas štartu prešiel)
    assert E.decide(CFG, inp(now=t + 5000, charging=False, **base), st).on is False


def test_time_mode_continues_past_midnight():
    # čas štartu 23:00 → o polnoci time_ts ukazuje na „dnešok“ v budúcnosti, ale nabíjanie pokračuje
    st = E.EvState()
    t = 10_000
    E.decide(CFG, inp(now=t - 60, mode=E.MODE_TIME, manual_a=16, time_ts=t), st)
    E.decide(CFG, inp(now=t + 60, mode=E.MODE_TIME, manual_a=16, time_ts=t), st)
    d = E.decide(CFG, inp(now=t + 3600, mode=E.MODE_TIME, manual_a=16, time_ts=t + 86400 - 3600), st)
    assert d.on


def test_time_mode_unplug_stops():
    st = E.EvState(time_active=True, last_ts=0)
    d = E.decide(CFG, inp(now=60, mode=E.MODE_TIME, manual_a=16, connected=False), st)
    assert d.on is False and st.time_active is False


def test_time_mode_resumes_after_restart():
    st = E.EvState()
    d = E.decide(CFG, inp(now=60, mode=E.MODE_TIME, manual_a=16, is_on=True, connected=True), st)
    assert d.on
