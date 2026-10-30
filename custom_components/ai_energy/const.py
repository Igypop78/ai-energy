"""Konštanty integrácie AI Energy."""

from __future__ import annotations

DOMAIN = "ai_energy"
PLATFORMS = ["sensor", "binary_sensor", "number", "select", "switch", "time"]

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


# --- konfigurácia: nabíjanie auta (v0.3) ---
CONF_EV_CURRENT = "ev_current_entity"  # number – nabíjací prúd v A
CONF_EV_SWITCH = "ev_switch_entity"  # switch / input_boolean / select – zapnutie nabíjania
CONF_EV_ON_OPTION = "ev_on_option"  # pri select: možnosť „nabíjaj“
CONF_EV_OFF_OPTION = "ev_off_option"  # pri select: možnosť „nenabíjaj“
CONF_EV_PLUG = "ev_plug_entity"  # voliteľné – je auto pripojené
CONF_EV_CHARGING = "ev_charging_entity"  # voliteľné – nabíja práve teraz
CONF_EV_POWER = "ev_power_entity"  # voliteľné – výkon nabíjačky
CONF_EV_PHASES = "ev_phases"
CONF_EV_MIN_A = "ev_min_a"
CONF_EV_MAX_A = "ev_max_a"
CONF_GRID_POWER = "grid_power_entity"  # voliteľné – odber zo siete (+) / dodávka (−)
CONF_GRID_INVERT = "grid_invert"
CONF_GRID_LIMIT_KW = "grid_limit_kw"  # 0 = bez limitu
CONF_CABLE_KW = "cable_kw"  # spoločný limit batérie + auta, 0 = bez limitu

DEFAULT_EV_PHASES = 3
DEFAULT_EV_MIN_A = 6
DEFAULT_EV_MAX_A = 16
DEFAULT_GRID_LIMIT_KW = 0.0
DEFAULT_CABLE_KW = 0.0

# nastavenia auta ako entity
EV_MODE = "auto_rezim"  # select
EV_TIME = "auto_cas"  # time
EV_MANUAL_A = "auto_prud"  # number – prúd pre ručné režimy
EV_SPOT_LIMIT = "auto_spot_cena"  # number
EV_USE_NT = "auto_nt"  # switch
EV_USE_PV = "auto_fve"  # switch
EV_USE_SPOT = "auto_spot"  # switch
EV_CONTROL = "auto_riadenie"  # switch – vypnuté = len odporúča

# --- v0.4: výbava, predaj, spotreba, istič ---
CONF_HAS_PV = "has_pv"
CONF_HAS_EV = "has_ev"
CONF_SELL_MODE = "sell_mode"  # spot / fixed / none
CONF_SELL_FIXED = "sell_fixed_price"  # €/MWh
CONF_SELL_BANDS = "sell_band_intervals"
CONF_SELL_BAND_PRICE = "sell_band_price"  # €/MWh
CONF_HOUSE_KWH = "house_kwh_day"
CONF_HOUSE_SENSOR = "house_sensor"  # energia (kWh) alebo výkon (W) – priemer z histórie
CONF_BREAKER_A = "breaker_a"
CONF_BREAKER_PHASES = "breaker_phases"
CONF_BREAKER_RESERVE = "breaker_reserve"  # %

SELL_SPOT = "spot"
SELL_FIXED = "fixed"
SELL_NONE = "none"
DEFAULT_HOUSE_KWH = 15.0
DEFAULT_BREAKER_RESERVE = 10.0
VOLTAGE = 230.0


def house_kw_estimate(cfg: dict) -> float:
    """Priemerná spotreba domu v kW z odhadu kWh/deň (staršie nastavenie: priamo kW)."""
    if cfg.get(CONF_HOUSE_KWH) is not None:
        return float(cfg[CONF_HOUSE_KWH]) / 24
    return float(cfg.get(CONF_HOUSE_KW, DEFAULT_HOUSE_KW))


def house_sensor(cfg: dict) -> str | None:
    return cfg.get(CONF_HOUSE_SENSOR) or cfg.get(CONF_HOUSE_POWER)


def grid_limit_kw(cfg: dict) -> float:
    """Limit odberu zo siete: z ističa v A (s rezervou), inak staré nastavenie v kW, 0 = bez limitu."""
    a = float(cfg.get(CONF_BREAKER_A) or 0)
    if a > 0:
        ph = int(cfg.get(CONF_BREAKER_PHASES, 3))
        res = float(cfg.get(CONF_BREAKER_RESERVE, DEFAULT_BREAKER_RESERVE))
        return round(a * VOLTAGE * ph * (1 - res / 100) / 1000, 1)
    return float(cfg.get("grid_limit_kw") or 0)


def sell_mode(cfg: dict) -> str:
    return cfg.get(CONF_SELL_MODE, SELL_SPOT)


def effective_sell_fee(cfg: dict) -> float:
    return float(cfg.get(CONF_SELL_FEE, DEFAULT_SELL_FEE)) if sell_mode(cfg) == SELL_SPOT else 0.0


def has_pv(cfg: dict) -> bool:
    if CONF_HAS_PV in cfg:
        return bool(cfg[CONF_HAS_PV])
    return bool(cfg.get(CONF_PV_TODAY) or cfg.get(CONF_PV_POWER))


def has_ev(cfg: dict) -> bool:
    if CONF_HAS_EV in cfg:
        return bool(cfg[CONF_HAS_EV]) and bool(cfg.get(CONF_EV_SWITCH))
    return bool(cfg.get(CONF_EV_SWITCH))


# --- v0.6: ovládanie meniča cez select (mapovanie režimov) ---
CONF_INV_SELECT = "inverter_mode_entity"
CONF_INV_OPTION = "inverter_option_"  # + režim AI Energy (predaj, nabijanie, …)
CONF_INV_CURRENT = "inverter_current_entity"  # voliteľné – nabíjací prúd batérie zo siete (A)
CONF_BAT_VOLTAGE = "battery_voltage"
DEFAULT_BAT_VOLTAGE = 51.0
INV_MODES = ["predaj", "predaj_fve", "nabijanie", "siet", "bez_pretokov", "normal"]

BAT_CONTROL = "bateria_riadenie"  # switch
BAT_MODE = "bateria_rezim"  # select: auto / ručný režim
BAT_DUR = "bateria_rucne_na"  # select: 1h / 2h / 4h / nt / trvalo
BAT_UNTIL = "bateria_rucne_do"  # interné – koniec ručného režimu (unix s) alebo None


def inverter_enabled(cfg: dict) -> bool:
    return bool(cfg.get(CONF_INV_SELECT))


CARD_NAME = "igy-price-action-card"
CARD_URL = f"/ai_energy/{CARD_NAME}.js"
CONTROL_CARDS_URL = "/ai_energy/igy-action-cards.js"
