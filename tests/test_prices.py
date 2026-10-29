"""Testy čistej logiky cien a tarify (bez Home Assistant)."""

import importlib.util
from pathlib import Path

import pytest

# prices.py importujeme priamo, aby testy nepotrebovali nainštalovaný Home Assistant
_spec = importlib.util.spec_from_file_location(
    "prices", Path(__file__).parents[1] / "custom_components" / "ai_energy" / "prices.py"
)
prices = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prices)

# 2026-10-19 00:00 Europe/Bratislava = 2026-10-18 22:00 UTC
T0 = 1792360800


def test_parse_okte_period_data():
    attrs = {
        "period_data": [
            {"time": "2026-10-18T22:00:00Z", "time_local": "2026-10-19 00:00:00", "price": 198.38},
            {"time": "2026-10-18T22:15:00Z", "price": 186.09},
        ],
        "prices_list": "198.38, 186.09",
    }
    assert prices.parse_slots(attrs) == [{"t": T0, "p": 198.38}, {"t": T0 + 900, "p": 186.09}]


def test_parse_nordpool_raw_today():
    attrs = {"raw_today": [{"start": "2026-10-19T00:00:00+02:00", "end": "...", "value": 101.5}]}
    assert prices.parse_slots(attrs) == [{"t": T0, "p": 101.5}]


def test_parse_ignores_garbage():
    assert prices.parse_slots(None) == []
    assert prices.parse_slots({"period_data": "x", "data": [1, {"time": "nie"}, {"price": 5}]}) == []


def test_merge_new_wins_and_drops_yesterday():
    stored = [{"t": T0 - 900, "p": 1.0}, {"t": T0, "p": 2.0}, {"t": T0 + 900, "p": 3.0}]
    new = [{"t": T0, "p": 20.0}]
    assert prices.merge_slots(stored, new, T0) == [{"t": T0, "p": 20.0}, {"t": T0 + 900, "p": 3.0}]


def test_merge_keeps_backup_when_source_empty():
    stored = [{"t": T0, "p": 2.0}]
    assert prices.merge_slots(stored, [], T0) == stored


def test_price_at():
    slots = [{"t": T0, "p": 1.0}, {"t": T0 + 900, "p": 2.0}]
    assert prices.price_at(slots, T0 + 899) == 1.0
    assert prices.price_at(slots, T0 + 900) == 2.0
    assert prices.price_at(slots, T0 + 1800) is None


def test_intervals_zse():
    iv = prices.parse_intervals("23:45-05:45, 13:45-15:45")
    assert iv == [(1425, 345), (825, 945)]
    nt = lambda h, m: prices.is_in_intervals(h * 60 + m, iv)  # noqa: E731
    assert nt(23, 45) and nt(0, 0) and nt(5, 44) and not nt(5, 45)
    assert nt(13, 45) and nt(15, 44) and not nt(15, 45) and not nt(13, 44)
    assert not nt(12, 0) and not nt(23, 44)


@pytest.mark.parametrize("bad", ["23:45", "25:00-01:00", "a-b", "10:70-11:00"])
def test_intervals_invalid(bad):
    with pytest.raises(ValueError):
        prices.parse_intervals(bad)


def test_parse_solcast():
    attrs = {"detailedForecast": [{"period_start": "2026-10-19T00:00:00+02:00", "pv_estimate": 1.5, "pv_estimate10": 1.0}]}
    assert prices.parse_pv(attrs) == [(T0, 1.5)]
    assert prices.parse_pv({}) == []
