"""Authenticated WebSocket queries for the bundled dashboard."""

from __future__ import annotations

from datetime import date
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from . import KretaRuntimeData
from .const import DOMAIN
from .queries import day_payload, grades_payload, list_payload, overview_payload, week_payload

ENTRY_SCHEMA = {vol.Required("entry_id"): str}
LIMIT_SCHEMA = {
    vol.Optional("limit", default=20): vol.All(vol.Coerce(int), vol.Range(min=1, max=200))
}
SUBJECT_SCHEMA = {vol.Optional("subject"): vol.All(str, vol.Length(max=100))}


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
        vol.Optional("oldest_first", default=False): bool,
    }
)
def websocket_get_grades(hass, connection, message):
    data = _data_or_error(hass, connection, message)
    if data is not None:
        connection.send_result(
            message["id"],
            grades_payload(data, message["limit"], message.get("subject"), message["oldest_first"]),
        )


def _list_command(kind: str):
    @callback
    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"kreta/get_{kind}",
            **ENTRY_SCHEMA,
            **LIMIT_SCHEMA,
            **SUBJECT_SCHEMA,
        }
    )
    def handler(hass, connection, message):
        data = _data_or_error(hass, connection, message)
        if data is None:
            return
        items = getattr(data, kind)
        connection.send_result(
            message["id"], list_payload(items, message["limit"], message.get("subject"))
        )

    return handler


websocket_get_tests = _list_command("tests")
websocket_get_homework = _list_command("homework")
websocket_get_absences = _list_command("absences")
websocket_get_messages = _list_command("messages")


@callback
@websocket_api.websocket_command({vol.Required("type"): "kreta/get_school_year", **ENTRY_SCHEMA})
def websocket_get_school_year(hass, connection, message):
    data = _data_or_error(hass, connection, message)
    if data is not None:
        connection.send_result(message["id"], list_payload(data.school_year_calendar, 200))


@callback
@websocket_api.websocket_command({vol.Required("type"): "kreta/get_changes", **ENTRY_SCHEMA})
def websocket_get_changes(hass, connection, message):
    data = _data_or_error(hass, connection, message)
    if data is not None:
        connection.send_result(message["id"], list_payload(data.changes, 200))


@callback
def async_register(hass: HomeAssistant) -> None:
    for command in (
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
