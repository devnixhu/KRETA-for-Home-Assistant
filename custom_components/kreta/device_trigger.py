"""Device automation triggers for KRÉTA events."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import device_automation, event
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo

from .const import (
    DOMAIN,
    EVENT_LESSON_FINISHED,
    EVENT_LESSON_STARTED,
    EVENT_NEW_GRADE,
    EVENT_NEW_HOMEWORK,
    EVENT_NEW_TEST,
    EVENT_SCHOOL_FINISHED,
    EVENT_SUBSTITUTION,
    EVENT_TIMETABLE_CHANGE,
)

EVENTS = {
    "new_grade": EVENT_NEW_GRADE,
    "new_homework": EVENT_NEW_HOMEWORK,
    "new_test": EVENT_NEW_TEST,
    "timetable_changed": EVENT_TIMETABLE_CHANGE,
    "substitution": EVENT_SUBSTITUTION,
    "lesson_started": EVENT_LESSON_STARTED,
    "lesson_finished": EVENT_LESSON_FINISHED,
    "school_finished": EVENT_SCHOOL_FINISHED,
}

TRIGGER_SCHEMA = device_automation.DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(EVENTS),
        vol.Required("entry_id"): cv.string,
    }
)


async def async_get_triggers(hass: HomeAssistant, device_id: str) -> list[dict[str, Any]]:
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return []
    entries = [identifier[1] for identifier in device.identifiers if identifier[0] == DOMAIN]
    return [
        {
            CONF_PLATFORM: "device",
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: device_id,
            CONF_TYPE: trigger_type,
            "entry_id": entry_id,
        }
        for entry_id in entries
        for trigger_type in EVENTS
    ]


async def async_attach_trigger(
    hass: HomeAssistant,
    config: dict[str, Any],
    action: TriggerActionType,
    trigger_info: TriggerInfo,
):
    event_config = {
        "platform": "event",
        "event_type": EVENTS[config[CONF_TYPE]],
        "event_data": {"entry_id": config["entry_id"]},
    }
    return await event.async_attach_trigger(
        hass, event_config, action, trigger_info, platform_type="device"
    )


async def async_get_trigger_capabilities(
    hass: HomeAssistant, config: ConfigEntry
) -> dict[str, vol.Schema]:
    return {"extra_fields": vol.Schema({})}
