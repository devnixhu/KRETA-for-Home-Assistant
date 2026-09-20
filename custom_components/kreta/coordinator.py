"""Privacy-minimized coordinator for KRÉTA Secure."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any
from urllib.parse import urlsplit

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api.client import KretaApiClient
from .api.endpoints import MESSAGES_URL, api_url
from .api.exceptions import (
    ApiResponseError,
    CannotConnectError,
    InvalidAuthError,
    KretaApiError,
    KretaRateLimitError,
    KretaSecurityError,
)
from .api.models import (
    Absence,
    AnnouncedTest,
    Grade,
    HomeworkItem,
    MergedCalendarEvent,
    MessageSummary,
    SchoolYearMilestone,
    StudentProfile,
)
from .api.storage import KretaBaselineStore, entry_storage_key
from .const import (
    CONF_ABSENCES,
    CONF_GRADES,
    CONF_HOMEWORK,
    CONF_LOOKAHEAD_WEEKS,
    CONF_MESSAGES,
    CONF_REFRESH_HOURS,
    CONF_REFRESH_MINUTES,
    CONF_TESTS,
    CONF_TIMETABLE,
    DEFAULT_LOOKAHEAD_WEEKS,
    DEFAULT_REFRESH_HOURS,
    DEFAULT_REFRESH_MINUTES,
    DOMAIN,
    EVENT_NEW_ABSENCE,
    EVENT_NEW_GRADE,
    EVENT_NEW_HOMEWORK,
    EVENT_NEW_MESSAGE,
    EVENT_NEW_TEST,
    EVENT_TIMETABLE_CHANGE,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class KretaCoordinatorData:
    """Normalized, bounded coordinator payload."""

    profile: StudentProfile
    events: list[MergedCalendarEvent]
    grades: list[Grade]
    homework: list[HomeworkItem]
    tests: list[AnnouncedTest]
    absences: list[Absence]
    messages: list[MessageSummary]
    school_year_calendar: list[SchoolYearMilestone]
    range_start: datetime
    range_end: datetime
    last_success: datetime
    lessons_count: int = 0
    tests_count: int = 0
    new_counts: dict[str, int] = field(default_factory=dict)


def _start_of_current_week() -> date:
    today = dt_util.now().date()
    return today - timedelta(days=today.weekday())


def _stable(parts: tuple[object, ...]) -> str:
    return "|".join("" if part is None else str(part) for part in parts)


def _record_id(kind: str, record: object) -> str:
    uid = getattr(record, "uid", "")
    if uid:
        return f"{kind}:{uid}"
    if isinstance(record, Grade):
        return _stable((kind, record.grade_date, record.subject_name, record.value, record.topic))
    if isinstance(record, HomeworkItem):
        return _stable((kind, record.due_date, record.subject_name, record.description))
    if isinstance(record, AnnouncedTest):
        return _stable(
            (kind, record.test_date, record.lesson_index, record.subject_name, record.theme)
        )
    if isinstance(record, Absence):
        return _stable(
            (kind, record.absence_date, record.absence_type, record.status, record.minutes)
        )
    if isinstance(record, MessageSummary):
        return _stable((kind, record.received_at, record.sender, record.subject))
    raise TypeError(f"Unsupported baseline record: {type(record).__name__}")


def _safe_endpoint_label(endpoint: str) -> str:
    """Return a query-free hostname and path for diagnostics."""
    parsed = urlsplit(endpoint)
    if parsed.hostname:
        return f"{parsed.hostname}{parsed.path or '/'}"
    return endpoint.split("?", 1)[0].split("#", 1)[0][:240]


def _safe_error_description(err: Exception) -> str:
    """Return a bounded category without exception text or response data."""
    if isinstance(err, KretaApiError) and err.safe_description:
        return err.safe_description
    if isinstance(err, InvalidAuthError):
        return "authentication_required"
    if isinstance(err, KretaRateLimitError):
        return "rate_limited"
    if isinstance(err, CannotConnectError):
        return "network_connection_failed"
    if isinstance(err, ApiResponseError):
        return "invalid_api_response"
    if isinstance(err, KretaSecurityError):
        return "network_policy_rejected_request"
    if isinstance(err, KretaApiError):
        return "api_request_failed"
    return "unexpected_operation_failure"


def merge_lessons_and_tests(
    lessons: list[MergedCalendarEvent], tests: list[AnnouncedTest]
) -> list[MergedCalendarEvent]:
    """Merge tests into matching lessons without extra requests."""
    result: list[MergedCalendarEvent] = []
    used: set[int] = set()
    for lesson in lessons:
        match: AnnouncedTest | None = None
        for index, test in enumerate(tests):
            if index in used or test.test_date != lesson.start.date():
                continue
            if test.lesson_index is not None and lesson.lesson_index != test.lesson_index:
                continue
            if (
                test.subject_name
                and lesson.subject_name
                and test.subject_name.casefold() != lesson.subject_name.casefold()
            ):
                continue
            match = test
            used.add(index)
            break
        result.append(
            MergedCalendarEvent(
                uid=lesson.uid,
                start=lesson.start,
                end=lesson.end,
                summary=lesson.summary,
                description=lesson.description,
                location=lesson.location,
                lesson_index=lesson.lesson_index,
                subject_name=lesson.subject_name,
                exam=match,
                source="lesson_with_exam" if match else "lesson",
            )
        )
    for index, test in enumerate(tests):
        if index in used:
            continue
        start = datetime.combine(test.test_date, time.min, tzinfo=dt_util.DEFAULT_TIME_ZONE)
        result.append(
            MergedCalendarEvent(
                uid=_record_id("test", test),
                start=start,
                end=start + timedelta(days=1),
                summary=f"Számonkérés – {test.subject_name}",
                description=test.theme,
                location=None,
                lesson_index=test.lesson_index,
                subject_name=test.subject_name,
                exam=test,
                source="exam_only",
            )
        )
    return sorted(result, key=lambda event: (event.start, event.end, event.uid))


class KretaDataUpdateCoordinator(DataUpdateCoordinator[KretaCoordinatorData]):
    """Fetch enabled feature groups once per update."""

    config_entry: ConfigEntry

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, client: KretaApiClient
    ) -> None:
        self.client = client
        self.config_entry = config_entry
        self.last_error_message: str | None = None
        self.last_error_time: datetime | None = None
        minutes = config_entry.options.get(CONF_REFRESH_MINUTES)
        if minutes is None:
            legacy_hours = config_entry.options.get(
                CONF_REFRESH_HOURS, config_entry.data.get(CONF_REFRESH_HOURS, DEFAULT_REFRESH_HOURS)
            )
            minutes = (
                DEFAULT_REFRESH_MINUTES
                if legacy_hours == DEFAULT_REFRESH_HOURS
                else min(60, legacy_hours * 60)
            )
        self._baseline = KretaBaselineStore(
            hass, entry_storage_key(dict(config_entry.data))
        )
        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"{DOMAIN}_{config_entry.entry_id}",
            update_interval=timedelta(minutes=minutes),
            config_entry=config_entry,
        )

    def _enabled(self, key: str) -> bool:
        return bool(self.config_entry.options.get(key, True))

    async def _async_api_operation(
        self,
        operation: str,
        method: str,
        endpoint: str,
        request: Awaitable[Any],
    ) -> Any:
        """Run one API operation with privacy-safe stage diagnostics."""
        fallback_endpoint = _safe_endpoint_label(endpoint)
        _LOGGER.debug(
            "KRÉTA API operation started: operation=%s method=%s endpoint=%s",
            operation,
            method,
            fallback_endpoint,
        )
        try:
            result = await request
        except Exception as err:
            error_endpoint = getattr(err, "endpoint", None) or fallback_endpoint
            status = getattr(err, "status", None)
            _LOGGER.error(
                "KRÉTA API operation failed: operation=%s method=%s endpoint=%s "
                "status=%s exception=%s description=%s",
                operation,
                getattr(err, "method", None) or method,
                _safe_endpoint_label(error_endpoint),
                status if status is not None else "unknown",
                type(err).__name__,
                _safe_error_description(err),
            )
            raise
        _LOGGER.debug(
            "KRÉTA API operation completed: operation=%s method=%s endpoint=%s",
            operation,
            method,
            fallback_endpoint,
        )
        return result

    async def _emit_new(self, category: str, records: list[object], event_type: str) -> int:
        identities = {_record_id(category, record) for record in records}
        had_baseline, new_hashes = await self._baseline.async_update(category, identities)
        if not had_baseline:
            return 0
        count = 0
        for record in records:
            if hashlib.sha256(_record_id(category, record).encode()).hexdigest() not in new_hashes:
                continue
            payload: dict[str, object] = {"entry_id": self.config_entry.entry_id}
            if isinstance(record, Grade):
                payload.update(
                    subject=record.subject_name,
                    grade=record.value,
                    type=record.grade_type,
                    date=record.grade_date.isoformat(),
                )
            elif isinstance(record, HomeworkItem):
                payload.update(subject=record.subject_name, deadline=record.due_date.isoformat())
            elif isinstance(record, AnnouncedTest):
                payload.update(
                    subject=record.subject_name, date=record.test_date.isoformat(), type=record.mode
                )
            elif isinstance(record, MessageSummary):
                payload.update(
                    sender=record.sender,
                    subject=record.subject,
                    received_at=record.received_at.isoformat(),
                )
            elif isinstance(record, Absence):
                payload.update(
                    date=record.absence_date.isoformat(),
                    status=record.status,
                    type=record.absence_type,
                )
            self.hass.bus.async_fire(event_type, payload)
            count += 1
        return count

    async def _emit_timetable_changes(self, events: list[MergedCalendarEvent]) -> int:
        signatures = {
            _stable(
                (
                    event.start.date(),
                    event.lesson_index,
                    event.start.time(),
                    event.end.time(),
                    event.subject_name,
                    event.location,
                )
            )
            for event in events
            if event.source != "exam_only"
        }
        had_baseline, new_hashes = await self._baseline.async_update("timetable", signatures)
        if not had_baseline:
            return 0
        count = 0
        for event in events:
            signature = _stable(
                (
                    event.start.date(),
                    event.lesson_index,
                    event.start.time(),
                    event.end.time(),
                    event.subject_name,
                    event.location,
                )
            )
            if hashlib.sha256(signature.encode()).hexdigest() not in new_hashes:
                continue
            self.hass.bus.async_fire(
                EVENT_TIMETABLE_CHANGE,
                {
                    "entry_id": self.config_entry.entry_id,
                    "change_type": "new_or_changed_lesson",
                    "subject": event.subject_name,
                    "room": event.location,
                    "start": event.start.isoformat(),
                },
            )
            count += 1
        return count

    async def _async_update_data(self) -> KretaCoordinatorData:
        lookahead = self.config_entry.options.get(
            CONF_LOOKAHEAD_WEEKS,
            self.config_entry.data.get(CONF_LOOKAHEAD_WEEKS, DEFAULT_LOOKAHEAD_WEEKS),
        )
        week_start = _start_of_current_week()
        week_end = week_start + timedelta(weeks=lookahead) - timedelta(days=1)
        range_start = datetime.combine(week_start, time.min, tzinfo=dt_util.DEFAULT_TIME_ZONE)
        range_end = datetime.combine(week_end, time.max, tzinfo=dt_util.DEFAULT_TIME_ZONE)
        history_start = week_start - timedelta(weeks=lookahead)
        institution = self.config_entry.data["klik_id"]
        try:
            profile = await self._async_api_operation(
                "student_profile",
                "GET",
                api_url(institution, "Sajat/TanuloAdatlap"),
                self.client.async_get_student_profile(),
            )
            lessons = (
                await self._async_api_operation(
                    "lessons",
                    "GET",
                    api_url(institution, "Sajat/OrarendElemek"),
                    self.client.async_get_lessons(week_start, week_end),
                )
                if self._enabled(CONF_TIMETABLE)
                else []
            )
            tests = (
                await self._async_api_operation(
                    "announced_tests",
                    "GET",
                    api_url(institution, "Sajat/BejelentettSzamonkeresek"),
                    self.client.async_get_announced_tests(week_start, week_end),
                )
                if self._enabled(CONF_TESTS)
                else []
            )
            grades = (
                await self._async_api_operation(
                    "grades",
                    "GET",
                    api_url(institution, "Sajat/Ertekelesek"),
                    self.client.async_get_grades(history_start, week_end),
                )
                if self._enabled(CONF_GRADES)
                else []
            )
            homework = (
                await self._async_api_operation(
                    "homework",
                    "GET",
                    api_url(institution, "Sajat/HaziFeladatok"),
                    self.client.async_get_homework(week_start, week_end),
                )
                if self._enabled(CONF_HOMEWORK)
                else []
            )
            absences = (
                await self._async_api_operation(
                    "absences",
                    "GET",
                    api_url(institution, "Sajat/Mulasztasok"),
                    self.client.async_get_absences(history_start, week_end),
                )
                if self._enabled(CONF_ABSENCES)
                else []
            )
            messages = (
                await self._async_api_operation(
                    "messages",
                    "GET",
                    MESSAGES_URL,
                    self.client.async_get_messages(),
                )
                if self._enabled(CONF_MESSAGES)
                else []
            )
            school_year = (
                await self._async_api_operation(
                    "school_year_calendar",
                    "GET",
                    api_url(institution, "Sajat/Intezmenyek/TanevRendjeElemek"),
                    self.client.async_get_school_year_calendar(),
                )
                if self._enabled(CONF_TIMETABLE)
                else []
            )
        except InvalidAuthError as err:
            self.last_error_message = "authentication_required"
            self.last_error_time = dt_util.utcnow()
            raise ConfigEntryAuthFailed("KRÉTA authentication is required") from err
        except KretaRateLimitError as err:
            self.last_error_message = "rate_limited"
            self.last_error_time = dt_util.utcnow()
            raise UpdateFailed("KRÉTA temporarily rate-limited the integration") from err
        except (CannotConnectError, KretaApiError) as err:
            self.last_error_message = "temporarily_unavailable"
            self.last_error_time = dt_util.utcnow()
            raise UpdateFailed("KRÉTA data update failed") from err

        events = merge_lessons_and_tests(lessons, tests)
        new_counts = {
            "grades": await self._emit_new("grades", grades, EVENT_NEW_GRADE),
            "homework": await self._emit_new("homework", homework, EVENT_NEW_HOMEWORK),
            "tests": await self._emit_new("tests", tests, EVENT_NEW_TEST),
            "absences": await self._emit_new("absences", absences, EVENT_NEW_ABSENCE),
            "messages": await self._emit_new("messages", messages, EVENT_NEW_MESSAGE),
            "timetable": await self._emit_timetable_changes(events),
        }
        self.last_error_message = None
        self.last_error_time = None
        return KretaCoordinatorData(
            profile=profile,
            events=events,
            grades=grades,
            homework=homework,
            tests=tests,
            absences=absences,
            messages=messages,
            school_year_calendar=school_year,
            range_start=range_start,
            range_end=range_end,
            last_success=dt_util.utcnow(),
            lessons_count=len(lessons),
            tests_count=len(tests),
            new_counts=new_counts,
        )
