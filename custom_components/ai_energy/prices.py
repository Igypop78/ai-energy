"""Čistá logika cien a tarify – bez závislosti na Home Assistant (testovateľné pytestom)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

# Kľúče, pod ktorými rôzne integrácie publikujú zoznam cien v atribútoch
LIST_KEYS = ("period_data", "data", "prices", "raw_today", "raw_tomorrow", "today", "tomorrow", "forecast")
TIME_KEYS = ("time", "start", "start_time", "period_start", "datetime", "from")
PRICE_KEYS = ("price", "value", "price_eur_mwh", "price_per_mwh")


def _to_ts(value: Any) -> int | None:
    """Prevedie čas (ISO text, datetime, unix s/ms) na unix sekundy."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    if isinstance(value, (int, float)):
        return int(value / 1000) if value > 1e12 else int(value)
    if isinstance(value, str):
        txt = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(txt)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    return None


def _to_price(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_slots(attributes: Mapping[str, Any] | None) -> list[dict[str, float]]:
    """Vytiahne z atribútov senzora zoznam {t: unix s, p: €/MWh}.

    Podporuje OKTE (period_data: [{time, price}]) a bežné formáty iných integrácií
    (napr. Nord Pool raw_today: [{start, value}]).
    """
    if not attributes:
        return []
    out: dict[int, float] = {}
    for key in LIST_KEYS:
        items = attributes.get(key)
        if not isinstance(items, (list, tuple)):
            continue
        for item in items:
            if not isinstance(item, Mapping):
                continue
            ts = next((_to_ts(item.get(k)) for k in TIME_KEYS if item.get(k) is not None), None)
            price = next((_to_price(item.get(k)) for k in PRICE_KEYS if item.get(k) is not None), None)
            if ts is not None and price is not None:
                out[ts] = price
    return [{"t": t, "p": p} for t, p in sorted(out.items())]


def merge_slots(
    stored: Iterable[Mapping[str, float]], new: Iterable[Mapping[str, float]], since_ts: int
) -> list[dict[str, float]]:
    """Zlúči uložené a nové ceny: nové majú prednosť, sloty pred `since_ts` sa zahodia."""
    merged: dict[int, float] = {}
    for src in (stored, new):
        for slot in src:
            t = int(slot["t"])
            if t >= since_ts:
                merged[t] = float(slot["p"])
    return [{"t": t, "p": p} for t, p in sorted(merged.items())]


def price_at(slots: Iterable[Mapping[str, float]], ts: float, slot_seconds: int = 900) -> float | None:
    """Cena slotu, do ktorého patrí čas `ts` (unix s)."""
    for slot in slots:
        if slot["t"] <= ts < slot["t"] + slot_seconds:
            return float(slot["p"])
    return None


def parse_intervals(text: str) -> list[tuple[int, int]]:
    """'23:45-05:45, 13:45-15:45' -> [(1425, 345), (825, 945)] v minútach od polnoci.

    Interval môže prechádzať cez polnoc (začiatok > koniec).
    """
    result: list[tuple[int, int]] = []
    for part in (text or "").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            start, end = (x.strip() for x in part.split("-"))
            sh, sm = (int(v) for v in start.split(":"))
            eh, em = (int(v) for v in end.split(":"))
        except ValueError as err:
            raise ValueError(f"Neplatný interval: '{part}' (očakávam HH:MM-HH:MM)") from err
        if not (0 <= sh <= 24 and 0 <= eh <= 24 and 0 <= sm < 60 and 0 <= em < 60):
            raise ValueError(f"Neplatný čas v intervale: '{part}'")
        result.append(((sh * 60 + sm) % 1440, (eh * 60 + em) % 1440))
    return result


def is_in_intervals(minute_of_day: int, intervals: Iterable[tuple[int, int]]) -> bool:
    """Je daná minúta dňa v niektorom intervale (aj cez polnoc)?"""
    for start, end in intervals:
        if start <= end:
            if start <= minute_of_day < end:
                return True
        elif minute_of_day >= start or minute_of_day < end:
            return True
    return False


PV_LIST_KEYS = ("detailedForecast", "detailed_forecast", "forecast")
PV_TIME_KEYS = ("period_start", "start", "datetime", "time")
PV_VALUE_KEYS = ("pv_estimate", "power", "value")


def parse_pv(attributes: Mapping[str, Any] | None) -> list[tuple[int, float]]:
    """Predpoveď FVE z atribútov (Solcast: detailedForecast [{period_start, pv_estimate}] v kW)."""
    if not attributes:
        return []
    out: dict[int, float] = {}
    for key in PV_LIST_KEYS:
        items = attributes.get(key)
        if not isinstance(items, (list, tuple)):
            continue
        for item in items:
            if not isinstance(item, Mapping):
                continue
            ts = next((_to_ts(item.get(k)) for k in PV_TIME_KEYS if item.get(k) is not None), None)
            kw = next((_to_price(item.get(k)) for k in PV_VALUE_KEYS if item.get(k) is not None), None)
            if ts is not None and kw is not None:
                out[ts] = kw
    return sorted(out.items())
