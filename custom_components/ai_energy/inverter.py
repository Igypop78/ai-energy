"""Ovládanie meniča – čistá logika bez Home Assistant (testuje sa pytestom).

Integrácia zapisuje režim do selectu (napr. input_select.deye_operation_mode) podľa mapovania
režim AI Energy → možnosť selectu. Samotné nastavenie meniča robí používateľova automatizácia.
Navyše vie strážiť nabíjací prúd batérie zo siete (spoločný kábel s autom, istič).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
import math
from typing import Sequence

AUTO = "auto"
DUR_OPTIONS = ["1h", "2h", "4h", "nt", "trvalo"]
CURRENT_UP_DELAY = 120  # s – zvýšenie prúdu najskôr 2 min po poslednej zmene
CURRENT_MIN_STEP = 10  # A – menšie zvýšenie sa nezapisuje (šetrí zápisy do meniča)


def override_until(now: float, dur: str, tz: tzinfo, nt_intervals: Sequence[tuple[int, int]]) -> float | None:
    """Do kedy platí ručný režim. None = natrvalo."""
    if dur.endswith("h") and dur[:-1].isdigit():
        return now + int(dur[:-1]) * 3600
    if dur == "nt" and nt_intervals:
        d0 = datetime.fromtimestamp(now, tz)
        best = None
        for day in range(0, 3):
            base = (d0 + timedelta(days=day)).replace(hour=0, minute=0, second=0, microsecond=0)
            for start, _end in nt_intervals:
                t = (base + timedelta(minutes=start)).timestamp()
                if t > now and (best is None or t < best):
                    best = t
        return best
    if dur == "nt":
        return now + 4 * 3600
    return None


@dataclass
class InverterState:
    last_current: float | None = None
    last_current_ts: float | None = None


def target_mode(ai_mode: str, override: str, until: float | None, now: float) -> tuple[str, bool]:
    """Režim, ktorý sa má poslať, a či ešte platí ručný režim."""
    if override and override != AUTO and (until is None or now < until):
        return override, True
    return ai_mode, False


def grid_current(
    *,
    charging: bool,
    charge_kw: float,
    voltage: float,
    cable_kw: float = 0.0,
    grid_limit_kw: float = 0.0,
    grid_import_kw: float | None = None,
    ev_charging: bool = False,
    current_a: float | None = None,
    max_a: float = 1e9,
) -> int | None:
    """Nabíjací prúd batérie zo siete (A). None = nemeniť (batéria nenabíja zo siete)."""
    if not charging:
        return None
    kw = charge_kw
    if cable_kw > 0:
        kw = min(kw, cable_kw)  # batéria má na spoločnom kábli prednosť pred autom
    if grid_limit_kw > 0 and grid_import_kw is not None and not ev_charging:
        # istič: auto už uberá samo; keď nenabíja, uberie batéria o to, o čo je odber nad limitom
        now_kw = (current_a or 0) * voltage / 1000
        over = grid_import_kw - grid_limit_kw
        if over > 0:
            kw = min(kw, max(0.0, now_kw - over))
    return int(max(0, min(max_a, math.floor(kw * 1000 / max(voltage, 1)))))


def should_write_current(st: InverterState, want: int, have: float | None, now: float) -> bool:
    """Zníženie hneď; zvýšenie o ≥ 10 A a najskôr 2 min po poslednej zmene."""
    if have is None:
        return True
    if want < have:
        return True
    if want - have < CURRENT_MIN_STEP:
        return False
    return st.last_current_ts is None or now - st.last_current_ts >= CURRENT_UP_DELAY
