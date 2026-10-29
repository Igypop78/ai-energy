"""AI Energy – plánovanie batérie a predaja elektriny podľa spotových cien."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    CARD_NAME,
    CARD_URL,
    CONTROL_CARDS_URL,
    CONF_PRICE_NT,
    DEFAULT_MAX_SOC,
    DEFAULT_MIN_SOC,
    DEFAULT_PRICE_NT,
    DEFAULT_PV_CORRECTION,
    DOMAIN,
    PLATFORMS,
    SET_CHARGE_KW,
    SET_MAX_SOC,
    SET_MIN_SOC,
    SET_PV_CORRECTION,
    SET_THRESHOLD,
    CONF_CHARGE_KW,
    DEFAULT_CHARGE_KW,
    default_threshold,
    effective_sell_fee,
)
from .coordinator import PriceCoordinator
from .ev_controller import EvController, default_ev_settings, ev_enabled
from .plan_coordinator import PlanCoordinator


CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class AiEnergyData:
    prices: PriceCoordinator
    plan: PlanCoordinator
    settings: dict[str, float] = field(default_factory=dict)
    ev: EvController | None = None
    ev_settings: dict[str, Any] = field(default_factory=dict)


type AiEnergyConfigEntry = ConfigEntry[AiEnergyData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Zaregistruje karty (Igy Price / Battery / EV Action Card) – na dashboard ju stačí pridať, netreba kopírovať súbory."""
    base = Path(__file__).parent
    card = base / "www" / f"{CARD_NAME}.js"
    manifest = await hass.async_add_executor_job((base / "manifest.json").read_text)
    version = json.loads(manifest)["version"]
    cards = [(CARD_URL, card), (CONTROL_CARDS_URL, base / "www" / "igy-action-cards.js")]
    await hass.http.async_register_static_paths([StaticPathConfig(url, str(path), True) for url, path in cards])
    if "frontend" in hass.config.components:
        for url, _ in cards:
            add_extra_js_url(hass, f"{url}?v={version}")
    return True


def initial_settings(entry: ConfigEntry) -> dict[str, float]:
    cfg = {**entry.data, **entry.options}
    return {
        SET_THRESHOLD: float(default_threshold(float(cfg.get(CONF_PRICE_NT, DEFAULT_PRICE_NT)), effective_sell_fee(cfg))),
        SET_MIN_SOC: DEFAULT_MIN_SOC,
        SET_MAX_SOC: DEFAULT_MAX_SOC,
        SET_CHARGE_KW: float(cfg.get(CONF_CHARGE_KW, DEFAULT_CHARGE_KW)),
        SET_PV_CORRECTION: DEFAULT_PV_CORRECTION,
    }


async def async_setup_entry(hass: HomeAssistant, entry: AiEnergyConfigEntry) -> bool:
    """Nastavenie z UI."""
    prices = PriceCoordinator(hass, entry)
    await prices.async_load()
    await prices.async_config_entry_first_refresh()
    prices.async_track_sources()

    settings = initial_settings(entry)
    plan = PlanCoordinator(hass, entry, prices, settings)
    await plan.async_config_entry_first_refresh()
    plan.async_track_inputs()
    data = AiEnergyData(prices=prices, plan=plan, settings=settings)
    cfg = {**entry.data, **entry.options}
    if ev_enabled(cfg):
        data.ev_settings = default_ev_settings(cfg)
        data.ev = EvController(hass, entry, plan, data.ev_settings)
    entry.runtime_data = data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if data.ev:
        # až po obnovení nastavení auta z entít (select, switch…) – prvé rozhodnutie už s nimi
        await data.ev.async_refresh()
        data.ev.async_track_inputs()
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AiEnergyConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: AiEnergyConfigEntry) -> None:
    """Po zmene nastavení (options) integráciu znovu načítaj."""
    await hass.config_entries.async_reload(entry.entry_id)
