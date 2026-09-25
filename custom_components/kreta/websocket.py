"""Authenticated WebSocket queries for the bundled dashboard."""

from __future__ import annotations

from datetime import date
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from . import KretaRuntimeData
from .const import DOMAIN
from .queries import (
    absences_payload,
    day_payload,
    grades_payload,
    list_payload,
    overview_payload,
    week_payload,
)

ENTRY_SCHEMA = {vol.Required("entry_id"): str}
LIMIT_SCHEMA = {
    vol.Optional("limit", default=20): vol.All(vol.Coerce(int), vol.Range(min=1, max=200))
}
SUBJECT_SCHEMA = {vol.Optional("subject"): vol.All(str, vol.Length(max=100))}
OFFSET_SCHEMA = {
    vol.Optional("offset", default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=5000))
}


@callback
@websocket_api.websocket_command({vol.Required("type"): "kreta/get_entries"})
def websocket_get_entries(hass, connection, message):
    entries = []
    for entry_id, runtime in hass.data.get(DOMAIN, {}).items():
        if not isinstance(runtime, KretaRuntimeData):
            continue
        entries.append({"entry_id": entry_id, "title": runtime.coordinator.config_entry.title})
    connection.send_result(message["id"], {"entries": entries})


def _runtime(hass: HomeAssistant, entry_id: str) -> KretaRuntimeData | None:
    value = hass.data.get(DOMAIN, {}).get(entry_id)
    return value if isinstance(value, KretaRuntimeData) else None


def _data_or_error(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    message: dict[str, Any],
):
    runtime = _runtime(hass, message["entry_id"])
    if runtime is None:
        connection.send_error(message["id"], "entry_not_found", "KRÉTA entry is unavailable")
        return None
    if runtime.coordinator.data is None:
        connection.send_error(message["id"], "data_unavailable", "KRÉTA data is unavailable")
        return None
    return runtime.coordinator.data


def _date_or_error(
    connection: websocket_api.ActiveConnection, message: dict[str, Any]
) -> date | None:
    try:
        return date.fromisoformat(message["date"])
    except ValueError:
        connection.send_error(message["id"], "invalid_date", "Date must use YYYY-MM-DD")
        return None


@callback
@websocket_api.websocket_command({vol.Required("type"): "kreta/get_overview", **ENTRY_SCHEMA})
def websocket_get_overview(hass, connection, message):
    data = _data_or_error(hass, connection, message)
    if data is not None:
        connection.send_result(message["id"], overview_payload(data))


@callback
@websocket_api.websocket_command(
    {vol.Required("type"): "kreta/get_day", **ENTRY_SCHEMA, vol.Required("date"): str}
)
def websocket_get_day(hass, connection, message):
    data = _data_or_error(hass, connection, message)
    target = _date_or_error(connection, message)
    if data is not None and target is not None:
        connection.send_result(message["id"], day_payload(data, target))


@callback
@websocket_api.websocket_command(
    {vol.Required("type"): "kreta/get_week", **ENTRY_SCHEMA, vol.Required("date"): str}
)
def websocket_get_week(hass, connection, message):
    data = _data_or_error(hass, connection, message)
    target = _date_or_error(connection, message)
    if data is not None and target is not None:
        connection.send_result(message["id"], week_payload(data, target))


@callback
@websocket_api.websocket_command(
    {
        vol.Required("type"): "kreta/get_grades",
        **ENTRY_SCHEMA,
        **LIMIT_SCHEMA,
        **SUBJECT_SCHEMA,
        **OFFSET_SCHEMA,
        vol.Optional("oldest_first", default=False): bool,
        vol.Optional("search"): vol.All(str, vol.Length(max=100)),
        vol.Optional("date_from"): str,
        vol.Optional("date_to"): str,
    }
)
def websocket_get_grades(hass, connection, message):
    data = _data_or_error(hass, connection, message)
    if data is None:
        return
    try:
        date_from = date.fromisoformat(message["date_from"]) if message.get("date_from") else None
        date_to = date.fromisoformat(message["date_to"]) if message.get("date_to") else None
    except ValueError:
        connection.send_error(message["id"], "invalid_date", "Date must use YYYY-MM-DD")
        return
    connection.send_result(
        message["id"],
        grades_payload(
            data,
            message["limit"],
            message.get("subject"),
            message["oldest_first"],
            offset=message["offset"],
            search=message.get("search"),
            date_from=date_from,
            date_to=date_to,
        ),
    )


def _list_command(kind: str):
    @callback
    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"kreta/get_{kind}",
            **ENTRY_SCHEMA,
            **LIMIT_SCHEMA,
            **SUBJECT_SCHEMA,
            **OFFSET_SCHEMA,
        }
    )
    def handler(hass, connection, message):
        data = _data_or_error(hass, connection, message)
        if data is None:
            return
        items = getattr(data, kind)
        connection.send_result(
            message["id"],
            list_payload(items, message["limit"], message.get("subject"), offset=message["offset"]),
        )

    return handler


websocket_get_tests = _list_command("tests")
websocket_get_homework = _list_command("homework")
websocket_get_messages = _list_command("messages")


@callback
@websocket_api.websocket_command(
    {
        vol.Required("type"): "kreta/get_absences",
        **ENTRY_SCHEMA,
        **LIMIT_SCHEMA,
        **OFFSET_SCHEMA,
    }
)
def websocket_get_absences(hass, connection, message):
    data = _data_or_error(hass, connection, message)
    if data is not None:
        connection.send_result(
            message["id"],
            absences_payload(data, message["limit"], offset=message["offset"]),
        )


@callback
@websocket_api.websocket_command({vol.Required("type"): "kreta/get_school_year", **ENTRY_SCHEMA})
def websocket_get_school_year(hass, connection, message):
    data = _data_or_error(hass, connection, message)
    if data is not None:
        future = [
            item for item in data.school_year_calendar if item.event_date >= dt_util.now().date()
        ]
        connection.send_result(message["id"], list_payload(future, 200))


@callback
@websocket_api.websocket_command({vol.Required("type"): "kreta/get_changes", **ENTRY_SCHEMA})
def websocket_get_changes(hass, connection, message):
    data = _data_or_error(hass, connection, message)
    if data is not None:
        connection.send_result(message["id"], list_payload(data.changes[::-1], 200))


@callback
def async_register(hass: HomeAssistant) -> None:
    for command in (
        websocket_get_entries,
        websocket_get_overview,
        websocket_get_day,
        websocket_get_week,
        websocket_get_grades,
        websocket_get_tests,
        websocket_get_homework,
        websocket_get_absences,
        websocket_get_messages,
        websocket_get_school_year,
        websocket_get_changes,
    ):
        websocket_api.async_register_command(hass, command)
