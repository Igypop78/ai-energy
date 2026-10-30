"""Testy ovládania meniča (bez Home Assistant)."""

from datetime import datetime
import importlib.util
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

_path = Path(__file__).parents[1] / "custom_components" / "ai_energy" / "inverter.py"
_spec = importlib.util.spec_from_file_location("ai_energy_inverter", _path)
I = importlib.util.module_from_spec(_spec)
sys.modules["ai_energy_inverter"] = I
_spec.loader.exec_module(I)

TZ = ZoneInfo("Europe/Bratislava")
NT = [(1425, 345), (825, 945)]


def ts(h, m=0, d=30):
    return datetime(2026, 10, d, h, m, tzinfo=TZ).timestamp()


def test_override_durations():
    now = ts(10)
    assert I.override_until(now, "2h", TZ, NT) == now + 7200
    assert I.override_until(now, "trvalo", TZ, NT) is None
    assert I.override_until(now, "nt", TZ, NT) == ts(13, 45)
    assert I.override_until(ts(16), "nt", TZ, NT) == ts(23, 45)
    assert I.override_until(ts(23, 50), "nt", TZ, NT) == ts(13, 45, 31)


def test_target_mode():
    assert I.target_mode("predaj", "auto", None, 0) == ("predaj", False)
    assert I.target_mode("predaj", "nabijanie", 100, 50) == ("nabijanie", True)
    assert I.target_mode("predaj", "nabijanie", 100, 150) == ("predaj", False)
    assert I.target_mode("predaj", "siet", None, 1e12) == ("siet", True)


def test_grid_current_cable_and_breaker():
    assert I.grid_current(charging=False, charge_kw=10, voltage=51) is None
    assert I.grid_current(charging=True, charge_kw=10, voltage=51) == 196
    assert I.grid_current(charging=True, charge_kw=15, voltage=51, cable_kw=12) == 235
    # odber 17 kW pri limite 15,5 kW, batéria berie 10 kW, auto nenabíja → batéria zníži na 8,5 kW
    a = I.grid_current(charging=True, charge_kw=10, voltage=50, grid_limit_kw=15.5, grid_import_kw=17, current_a=200)
    assert a == 170
    # keď nabíja auto, istič rieši auto – batéria drží
    assert I.grid_current(charging=True, charge_kw=10, voltage=50, grid_limit_kw=15.5, grid_import_kw=17, current_a=200, ev_charging=True) == 200


def test_write_hysteresis():
    st = I.InverterState(last_current_ts=100)
    assert I.should_write_current(st, 150, 200, 110)  # zníženie hneď
    assert not I.should_write_current(st, 205, 200, 500)  # malé zvýšenie nie
    assert not I.should_write_current(st, 220, 200, 150)  # do 2 min nie
    assert I.should_write_current(st, 220, 200, 230)
