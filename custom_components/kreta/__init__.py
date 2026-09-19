"""The Kreta integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_change

from .api.client import KretaApiClient
from .api.storage import KretaTokenStore, entry_storage_key
from .const import DOMAIN, PLATFORMS
from .coordinator import KretaDataUpdateCoordinator

type KretaConfigEntry = ConfigEntry

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class KretaRuntimeData:
    """Runtime data for a config entry."""

    client: KretaApiClient
    coordinator: KretaDataUpdateCoordinator


async def async_setup(hass: HomeAssistant, _config: dict) -> bool:
    """Set up the Kreta integration."""
    hass.data.setdefault(DOMAIN, {})
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

    hass.data[DOMAIN][entry.entry_id] = KretaRuntimeData(
        client=client,
        coordinator=coordinator,
    )

    async def _midnight_refresh(_now: datetime) -> None:
        """Trigger a coordinator refresh after midnight to capture the new day's data."""
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
    hass.config_entries.async_update_entry(entry, data=data, version=2)
    return True


async def async_reload_entry(hass: HomeAssistant, entry: KretaConfigEntry) -> None:
    """Reload a config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
