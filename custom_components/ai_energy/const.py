"""Konštanty integrácie AI Energy."""

from __future__ import annotations

DOMAIN = "ai_energy"
PLATFORMS = ["sensor", "binary_sensor", "number"]

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

# --- konfigurácia: batéria a FVE (v0.2) ---
CONF_SOC_ENTITY = "soc_entity"
CONF_CAPACITY = "capacity_kwh"
CONF_EXPORT_KW = "export_kw"
CONF_HOUSE_KW = "house_kw"
CONF_CHARGE_KW = "charge_kw"
CONF_PV_TODAY = "pv_forecast_today"
CONF_PV_TOMORROW = "pv_forecast_tomorrow"
CONF_PV_POWER = "pv_power_entity"
CONF_HOUSE_POWER = "house_power_entity"

DEFAULT_CAPACITY = 10.0  # kWh
DEFAULT_EXPORT_KW = 5.0  # kW – výkon predaja z batérie (menič)
DEFAULT_HOUSE_KW = 0.8  # kW – priemerná spotreba domu
DEFAULT_PV_TODAY = "sensor.solcast_pv_forecast_forecast_today"
DEFAULT_PV_TOMORROW = "sensor.solcast_pv_forecast_forecast_tomorrow"

# --- nastavenia ako entity (number) – kľúče a predvoľby ---
SET_THRESHOLD = "prah_predaja"
SET_MIN_SOC = "min_soc"
SET_MAX_SOC = "max_soc"
SET_CHARGE_KW = "nabijaci_vykon"
SET_PV_CORRECTION = "korekcia_fve"

DEFAULT_MIN_SOC = 15.0
DEFAULT_MAX_SOC = 95.0
DEFAULT_CHARGE_KW = 3.0
DEFAULT_PV_CORRECTION = 80.0  # %
WEAR_EUR_MWH = 45.0  # opotrebenie batérie €/MWh (predvoľba pre prah)
MARGIN_EUR_MWH = 40.0  # požadovaný zisk €/MWh (predvoľba pre prah)
CHARGE_EFFICIENCY = 0.9


def default_threshold(price_nt: float, sell_fee: float) -> float:
    """Predvolený prah predaja: energia nabitá v NT (so stratami) + opotrebenie + marža + poplatok."""
    return round(sell_fee + price_nt / CHARGE_EFFICIENCY + WEAR_EUR_MWH + MARGIN_EUR_MWH)


CARD_URL = "/ai_energy/home-price-card.js"
