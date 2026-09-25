"""Privacy-safe Home Assistant diagnostics for KRÉTA Secure."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import KretaRuntimeData
from .const import DOMAIN, FEATURE_KEYS


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return operational metadata without account or school data."""
    runtime: KretaRuntimeData = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime.coordinator
    data = coordinator.data
    return {
        "integration": "KRÉTA kliens",
        "config_entry_version": entry.version,
        "enabled_features": {
            feature: bool(entry.options.get(feature, True)) for feature in FEATURE_KEYS
        },
        "last_update_success": coordinator.last_update_success,
        "last_status": coordinator.last_error_message or "ok",
        "unavailable_operations": sorted(coordinator.degraded_operations),
        "last_success": data.last_success.isoformat() if data else None,
        "entity_source_counts": {
            "lessons": data.lessons_count if data else 0,
            "tests": data.tests_count if data else 0,
            "grades": len(data.grades) if data else 0,
            "homework": len(data.homework) if data else 0,
            "messages": len(data.messages) if data else 0,
            "absences": len(data.absences) if data else 0,
        },
        "cache_version": 1,
    }
