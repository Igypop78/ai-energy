"""Konštanty integrácie AI Energy."""

from __future__ import annotations

DOMAIN = "ai_energy"
PLATFORMS = ["sensor", "binary_sensor"]

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.ceny"

# --- konfigurácia: zdroj cien ---
CONF_PRICE_TODAY = "price_today"
CONF_PRICE_TOMORROW = "price_tomorrow"

# --- konfigurácia: tarifa nákupu ---
CONF_NT_INTERVALS = "nt_intervals"
CONF_PRICE_NT = "price_nt"
CONF_PRICE_VT = "price_vt"
CONF_SELL_FEE = "sell_fee"

# Predvolené hodnoty = ZSE DD3 s dodatkom pre elektromobily (ceny vrátane distribúcie)
DEFAULT_PRICE_TODAY = "sensor.okte_prices_today"
DEFAULT_PRICE_TOMORROW = "sensor.okte_prices_tomorrow"
DEFAULT_NT_INTERVALS = "23:45-05:45, 13:45-15:45"
DEFAULT_PRICE_NT = 120.0  # €/MWh
DEFAULT_PRICE_VT = 210.0  # €/MWh
DEFAULT_SELL_FEE = 15.0  # €/MWh – výkupca strháva zo spotovej ceny

SLOT_SECONDS = 900  # 15-minútové intervaly
UPDATE_MINUTES = 15
