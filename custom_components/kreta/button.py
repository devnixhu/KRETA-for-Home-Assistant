"""Button platform for Kreta."""

from __future__ import annotations

from time import monotonic

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import KretaRuntimeData
from .const import DOMAIN
from .entity import KretaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kreta button entities."""
    runtime_data: KretaRuntimeData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([KretaRefreshButton(entry, runtime_data)])


class KretaRefreshButton(KretaEntity, ButtonEntity):
    """A button that triggers an immediate data refresh."""

    _attr_icon = "mdi:refresh"
    _attr_translation_key = "refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry, runtime_data: KretaRuntimeData) -> None:
        """Initialize the button."""
        super().__init__(entry, runtime_data)
        self._attr_unique_id = f"{entry.entry_id}_refresh"
        self._last_press = 0.0

    async def async_press(self) -> None:
        """Trigger an immediate coordinator refresh."""
        now = monotonic()
        if now - self._last_press < 60:
            raise HomeAssistantError("Manual KRÉTA refresh is limited to once per minute")
        self._last_press = now
        await self.coordinator.async_request_refresh()
