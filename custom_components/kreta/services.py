"""Home Assistant actions backed by the coordinator cache."""

from __future__ import annotations

from datetime import date

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError

from . import KretaRuntimeData
from .const import DOMAIN
from .queries import day_payload, grades_payload, list_payload, week_payload

ENTRY_SCHEMA = {vol.Optional("entry_id"): str}
LIMIT_SCHEMA = {
    vol.Optional("limit", default=20): vol.All(vol.Coerce(int), vol.Range(min=1, max=200))
}
SUBJECT_SCHEMA = {vol.Optional("subject"): vol.All(str, vol.Length(max=100))}


def _runtime(hass: HomeAssistant, call: ServiceCall) -> KretaRuntimeData:
    domain_data = hass.data.get(DOMAIN, {})
    entry_id = call.data.get("entry_id")
    if entry_id:
        value = domain_data.get(entry_id)
    else:
        values = [item for item in domain_data.values() if isinstance(item, KretaRuntimeData)]
        value = values[0] if len(values) == 1 else None
    if not isinstance(value, KretaRuntimeData):
        raise HomeAssistantError("Select exactly one available KRÉTA config entry")
    return value


def _data(hass: HomeAssistant, call: ServiceCall):
    data = _runtime(hass, call).coordinator.data
    if data is None:
        raise HomeAssistantError("KRÉTA data is not available yet")
    return data


def _date(call: ServiceCall) -> date:
    try:
        return date.fromisoformat(call.data["date"])
    except ValueError as err:
        raise HomeAssistantError("Date must use YYYY-MM-DD") from err


async def async_register(hass: HomeAssistant) -> None:
    async def refresh(call: ServiceCall) -> None:
        await _runtime(hass, call).coordinator.async_request_refresh()

    async def get_day(call: ServiceCall) -> ServiceResponse:
        return day_payload(_data(hass, call), _date(call))

    async def get_week(call: ServiceCall) -> ServiceResponse:
        return week_payload(_data(hass, call), _date(call))

    async def get_grades(call: ServiceCall) -> ServiceResponse:
        return grades_payload(_data(hass, call), call.data["limit"], call.data.get("subject"))

    async def get_tests(call: ServiceCall) -> ServiceResponse:
        return list_payload(_data(hass, call).tests, call.data["limit"], call.data.get("subject"))

    async def get_homework(call: ServiceCall) -> ServiceResponse:
        return list_payload(
            _data(hass, call).homework, call.data["limit"], call.data.get("subject")
        )

    hass.services.async_register(DOMAIN, "refresh", refresh, schema=vol.Schema(ENTRY_SCHEMA))
    response_schema = vol.Schema({**ENTRY_SCHEMA, **LIMIT_SCHEMA, **SUBJECT_SCHEMA})
    for name, handler in (
        ("get_grades", get_grades),
        ("get_tests", get_tests),
        ("get_homework", get_homework),
    ):
        hass.services.async_register(
            DOMAIN,
            name,
            handler,
            schema=response_schema,
            supports_response=SupportsResponse.ONLY,
        )
    date_schema = vol.Schema({**ENTRY_SCHEMA, vol.Required("date"): str})
    hass.services.async_register(
        DOMAIN,
        "get_day",
        get_day,
        schema=date_schema,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        "get_week",
        get_week,
        schema=date_schema,
        supports_response=SupportsResponse.ONLY,
    )
