"""The Kreta integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_change

from .api.client import KretaApiClient
from .api.storage import KretaTokenStore, entry_storage_key
from .const import (
    CONF_FUTURE_WEEKS,
    CONF_HISTORY_WEEKS,
    CONF_LESSON_EVENTS,
    CONF_LOOKAHEAD_WEEKS,
    DEFAULT_FUTURE_WEEKS,
    DEFAULT_HISTORY_WEEKS,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import KretaDataUpdateCoordinator
from .oauth_start import OAUTH_STARTS, ensure_oauth_start_view
from .schedule import KretaTransitionScheduler

type KretaConfigEntry = ConfigEntry

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class KretaRuntimeData:
    """Runtime data for a config entry."""

    client: KretaApiClient
    coordinator: KretaDataUpdateCoordinator
    scheduler: KretaTransitionScheduler | None = None


async def async_setup(hass: HomeAssistant, _config: dict) -> bool:
    """Set up the Kreta integration."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data.setdefault(OAUTH_STARTS, {})
    ensure_oauth_start_view(hass)
    from . import services, websocket

    websocket.async_register(hass)
    await services.async_register(hass)
    frontend_path = Path(__file__).parent / "frontend"
    await hass.http.async_register_static_paths(
        [StaticPathConfig("/kreta_static", str(frontend_path), cache_headers=True)]
    )
    add_extra_js_url(hass, "/kreta_static/kreta-dashboard-card.js?v=2.0.0")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: KretaConfigEntry) -> bool:
    """Set up Kreta from a config entry."""
    _LOGGER.info("Setting up KRÉTA Secure entry")
    session = async_get_clientsession(hass)
    token_store = KretaTokenStore(hass, entry_storage_key(dict(entry.data)))
    client = KretaApiClient(
        session=session,
        klik_id=entry.data["klik_id"],
        token_store=token_store,
    )
    coordinator = KretaDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    _LOGGER.info("KRÉTA Secure entry is ready")

    scheduler = KretaTransitionScheduler(
        hass,
        entry.entry_id,
        coordinator,
        emit_events=entry.options.get(CONF_LESSON_EVENTS, True),
    )
    hass.data[DOMAIN][entry.entry_id] = KretaRuntimeData(
        client=client,
        coordinator=coordinator,
        scheduler=scheduler,
    )
    scheduler.async_reschedule()
    entry.async_on_unload(coordinator.async_add_listener(scheduler.async_reschedule))
    entry.async_on_unload(scheduler.async_cancel)

    async def _midnight_refresh(_now: datetime) -> None:
        """Update local states and transition timers after midnight."""
        coordinator.async_update_listeners()
        if coordinator.update_interval is not None:
            await coordinator.async_request_refresh()

    entry.async_on_unload(
        async_track_time_change(hass, _midnight_refresh, hour=0, minute=0, second=30)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KretaConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading KRÉTA Secure entry")
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def async_migrate_entry(hass: HomeAssistant, entry: KretaConfigEntry) -> bool:
    """Remove legacy passwords while retaining usable refresh-token identity data."""
    data = {key: value for key, value in entry.data.items() if key != "password"}
    legacy_future = data.get(CONF_LOOKAHEAD_WEEKS, DEFAULT_FUTURE_WEEKS)
    data.setdefault(CONF_FUTURE_WEEKS, legacy_future)
    data.setdefault(CONF_HISTORY_WEEKS, DEFAULT_HISTORY_WEEKS)
    options = dict(entry.options)
    if CONF_LOOKAHEAD_WEEKS in options:
        options.setdefault(CONF_FUTURE_WEEKS, options[CONF_LOOKAHEAD_WEEKS])
    options.setdefault(CONF_HISTORY_WEEKS, DEFAULT_HISTORY_WEEKS)
    hass.config_entries.async_update_entry(entry, data=data, options=options, version=3)
    return True


async def async_reload_entry(hass: HomeAssistant, entry: KretaConfigEntry) -> None:
    """Reload a config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
