"""Privacy-minimized coordinator for KRÉTA Secure."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any
from urllib.parse import urlsplit

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api.cache import KretaCacheSnapshot, KretaDataCache
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
    TimetableChange,
)
from .api.storage import KretaBaselineStore, entry_storage_key
from .const import (
    CONF_ABSENCES,
    CONF_AUTOMATION_EVENTS,
    CONF_FUTURE_WEEKS,
    CONF_GRADES,
    CONF_HISTORY_WEEKS,
    CONF_HOMEWORK,
    CONF_LOOKAHEAD_WEEKS,
    CONF_MESSAGES,
    CONF_REFRESH_HOURS,
    CONF_REFRESH_MINUTES,
    CONF_SCHOOL_YEAR,
    CONF_TESTS,
    CONF_TIMETABLE,
    DEFAULT_HISTORY_WEEKS,
    DEFAULT_LOOKAHEAD_WEEKS,
    DEFAULT_REFRESH_HOURS,
    DEFAULT_REFRESH_MINUTES,
    DOMAIN,
    EVENT_LESSON_CANCELLED,
    EVENT_NEW_ABSENCE,
    EVENT_NEW_GRADE,
    EVENT_NEW_HOMEWORK,
    EVENT_NEW_MESSAGE,
    EVENT_NEW_TEST,
    EVENT_ROOM_CHANGED,
    EVENT_SUBSTITUTION,
    EVENT_TEACHER_CHANGED,
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
    changes: list[TimetableChange]
    range_start: datetime
    range_end: datetime
    last_success: datetime
    lessons_count: int = 0
    tests_count: int = 0
    new_counts: dict[str, int] = field(default_factory=dict)

    def lessons_between(self, start: datetime, end: datetime) -> list[MergedCalendarEvent]:
        """Return lesson events overlapping a bounded interval."""
        return [
            event
            for event in self.events
            if event.source != "exam_only" and event.end > start and event.start < end
        ]

    def lessons_for_date(self, target: date) -> list[MergedCalendarEvent]:
        """Return all lessons for one local date."""
        return [
            event
            for event in self.events
            if event.source != "exam_only" and event.start.date() == target
        ]

    def lessons_for_week(self, target: date) -> dict[str, list[MergedCalendarEvent]]:
        """Return Monday through Sunday lesson groups."""
        monday = target - timedelta(days=target.weekday())
        return {
            (monday + timedelta(days=offset)).isoformat(): self.lessons_for_date(
                monday + timedelta(days=offset)
            )
            for offset in range(7)
        }

    def current_lesson(self, now: datetime) -> MergedCalendarEvent | None:
        """Return the active lesson at a local time."""
        return next(
            (
                event
                for event in self.events
                if event.source != "exam_only"
                and not event.is_cancelled
                and event.start <= now < event.end
            ),
            None,
        )

    def next_lesson(self, now: datetime) -> MergedCalendarEvent | None:
        """Return the next non-cancelled lesson."""
        return next(
            (
                event
                for event in self.events
                if event.source != "exam_only" and not event.is_cancelled and event.start > now
            ),
            None,
        )


def _start_of_current_week() -> date:
    today = dt_util.now().date()
    return today - timedelta(days=today.weekday())


def _stable(parts: tuple[object, ...]) -> str:
    return "|".join("" if part is None else str(part) for part in parts)


def _record_id(kind: str, record: object) -> str:
    uid = getattr(record, "uid", "")
    if uid:
        return f"{kind}:{uid}"
    if isinstance(record, MergedCalendarEvent):
        return _stable((kind, record.start, record.lesson_index, record.subject_name))
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


def _record_date(record: object) -> date:
    """Return the primary local date for a normalized record."""
    if isinstance(record, MergedCalendarEvent):
        return record.start.date()
    if isinstance(record, Grade):
        return record.grade_date
    if isinstance(record, HomeworkItem):
        return record.due_date
    if isinstance(record, AnnouncedTest):
        return record.test_date
    if isinstance(record, Absence):
        return record.absence_date
    if isinstance(record, MessageSummary):
        return record.received_at.date()
    raise TypeError(f"Unsupported dated record: {type(record).__name__}")


def _merge_window(
    category: str,
    existing: list[Any],
    fresh: list[Any],
    refreshed_start: date,
    refreshed_end: date,
    retained_start: date,
    retained_end: date,
) -> list[Any]:
    """Replace one fetched window while retaining cached records outside it."""
    combined = [
        item
        for item in existing
        if retained_start <= _record_date(item) <= retained_end
        and not refreshed_start <= _record_date(item) <= refreshed_end
    ]
    combined.extend(fresh)
    deduplicated = {_record_id(category, item): item for item in combined}
    return sorted(
        deduplicated.values(), key=lambda item: (_record_date(item), _record_id(category, item))
    )


def _future_windows(
    start: date,
    end: date,
    covered_until: date | None,
    near_end: date,
) -> list[tuple[date, date]]:
    if covered_until is None:
        return [(start, end)]
    windows = [(start, min(end, near_end))]
    if end > covered_until:
        tail_start = max(covered_until + timedelta(days=1), near_end + timedelta(days=1))
        if tail_start <= end:
            windows.append((tail_start, end))
    return windows


def _merge_fetched_windows(
    category: str,
    existing: list[Any],
    fetched: list[tuple[date, date, list[Any]]],
    retained_start: date,
    retained_end: date,
) -> list[Any]:
    merged = existing
    for start, end, records in fetched:
        merged = _merge_window(category, merged, records, start, end, retained_start, retained_end)
    return [item for item in merged if retained_start <= _record_date(item) <= retained_end]


def detect_timetable_changes(
    previous: list[MergedCalendarEvent], current: list[MergedCalendarEvent]
) -> list[TimetableChange]:
    """Compare only matching stable UIDs and never infer disappearance as cancellation."""
    old_by_uid = {item.uid: item for item in previous if item.uid}
    changes: list[TimetableChange] = []
    for lesson in current:
        old = old_by_uid.get(lesson.uid)
        if old is None:
            continue
        candidates = (
            (
                "time_changed",
                old.start.isoformat(),
                lesson.start.isoformat(),
                old.start != lesson.start or old.end != lesson.end,
            ),
            ("room_changed", old.location, lesson.location, old.location != lesson.location),
            (
                "teacher_changed",
                old.teacher_name,
                lesson.teacher_name,
                old.teacher_name != lesson.teacher_name,
            ),
            (
                "substitution",
                old.substitute_teacher_name,
                lesson.substitute_teacher_name,
                not old.is_substitution and lesson.is_substitution,
            ),
            (
                "lesson_cancelled",
                old.state,
                lesson.state,
                not old.is_cancelled and lesson.is_cancelled,
            ),
        )
        for change_type, old_value, new_value, changed in candidates:
            if changed:
                changes.append(
                    TimetableChange(
                        change_type=change_type,
                        lesson_uid=lesson.uid,
                        subject_name=lesson.subject_name,
                        lesson_index=lesson.lesson_index,
                        start=lesson.start,
                        old_value=old_value,
                        new_value=new_value,
                    )
                )
    return changes


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
                teacher_name=lesson.teacher_name,
                substitute_teacher_name=lesson.substitute_teacher_name,
                topic=lesson.topic,
                lesson_type=lesson.lesson_type,
                state=lesson.state,
                annual_index=lesson.annual_index,
                is_cancelled=lesson.is_cancelled,
                is_substitution=lesson.is_substitution,
                is_digital=lesson.is_digital,
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
        self.degraded_operations: set[str] = set()
        minutes = config_entry.options.get(
            CONF_REFRESH_MINUTES, config_entry.data.get(CONF_REFRESH_MINUTES)
        )
        if minutes is None:
            legacy_hours = config_entry.options.get(
                CONF_REFRESH_HOURS, config_entry.data.get(CONF_REFRESH_HOURS, DEFAULT_REFRESH_HOURS)
            )
            minutes = (
                DEFAULT_REFRESH_MINUTES
                if legacy_hours == DEFAULT_REFRESH_HOURS
                else min(60, legacy_hours * 60)
            )
        self._baseline = KretaBaselineStore(hass, entry_storage_key(dict(config_entry.data)))
        self._cache = KretaDataCache(hass, entry_storage_key(dict(config_entry.data)))
        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"{DOMAIN}_{config_entry.entry_id}",
            update_interval=timedelta(minutes=minutes) if minutes > 0 else None,
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

    async def _async_optional_api_operation(
        self,
        operation: str,
        method: str,
        endpoint: str,
        request: Awaitable[Any],
    ) -> Any:
        """Run an independently available KRÉTA feature operation."""
        try:
            return await self._async_api_operation(operation, method, endpoint, request)
        except (InvalidAuthError, KretaRateLimitError, KretaSecurityError):
            raise
        except (CannotConnectError, KretaApiError):
            self.degraded_operations.add(operation)
            return []

    async def _async_fetch_windows(
        self,
        operation: str,
        endpoint: str,
        windows: list[tuple[date, date]],
        fetch: Callable[[date, date], Awaitable[list[Any]]],
    ) -> list[tuple[date, date, list[Any]]]:
        results: list[tuple[date, date, list[Any]]] = []
        for start, end in windows:
            if start > end:
                continue
            records = await self._async_optional_api_operation(
                operation, "GET", endpoint, fetch(start, end)
            )
            if operation in self.degraded_operations:
                return []
            results.append((start, end, records))
        return results

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
                    numeric_grade=record.numeric_value,
                    type=record.grade_type,
                    topic=record.topic,
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

    async def _emit_timetable_changes(self, changes: list[TimetableChange]) -> int:
        """Emit reliable field-level timetable changes."""
        event_types = {
            "room_changed": EVENT_ROOM_CHANGED,
            "teacher_changed": EVENT_TEACHER_CHANGED,
            "substitution": EVENT_SUBSTITUTION,
            "lesson_cancelled": EVENT_LESSON_CANCELLED,
        }
        for change in changes:
            payload = {
                "entry_id": self.config_entry.entry_id,
                "change_type": change.change_type,
                "subject": change.subject_name,
                "lesson_index": change.lesson_index,
                "start": change.start.isoformat(),
                "old_value": change.old_value,
                "new_value": change.new_value,
            }
            self.hass.bus.async_fire(EVENT_TIMETABLE_CHANGE, payload)
            if event_type := event_types.get(change.change_type):
                self.hass.bus.async_fire(event_type, payload)
        return len(changes)

    async def _async_update_data(self) -> KretaCoordinatorData:
        legacy_lookahead = self.config_entry.options.get(
            CONF_LOOKAHEAD_WEEKS,
            self.config_entry.data.get(CONF_LOOKAHEAD_WEEKS, DEFAULT_LOOKAHEAD_WEEKS),
        )
        future_weeks = int(
            self.config_entry.options.get(
                CONF_FUTURE_WEEKS,
                self.config_entry.data.get(CONF_FUTURE_WEEKS, legacy_lookahead),
            )
        )
        history_weeks = int(
            self.config_entry.options.get(
                CONF_HISTORY_WEEKS,
                self.config_entry.data.get(CONF_HISTORY_WEEKS, DEFAULT_HISTORY_WEEKS),
            )
        )
        today = dt_util.now().date()
        week_start = _start_of_current_week()
        week_end = week_start + timedelta(weeks=future_weeks) - timedelta(days=1)
        history_start = today - timedelta(weeks=history_weeks)
        range_start = datetime.combine(history_start, time.min, tzinfo=dt_util.DEFAULT_TIME_ZONE)
        range_end = datetime.combine(week_end, time.max, tzinfo=dt_util.DEFAULT_TIME_ZONE)
        institution = self.config_entry.data["klik_id"]
        self.degraded_operations = set()
        cache_store = getattr(self, "_cache", None)
        cache = await cache_store.async_load() if cache_store else KretaCacheSnapshot()
        lessons_fetch_start = (
            history_start
            if cache.lessons_covered_from is None or history_start < cache.lessons_covered_from
            else max(history_start, today - timedelta(days=7))
        )
        grades_fetch_start = (
            history_start
            if cache.grades_covered_from is None or history_start < cache.grades_covered_from
            else max(history_start, today - timedelta(days=14))
        )
        absences_fetch_start = (
            history_start
            if cache.absences_covered_from is None or history_start < cache.absences_covered_from
            else max(history_start, today - timedelta(days=14))
        )
        lesson_windows = _future_windows(
            lessons_fetch_start,
            week_end,
            cache.lessons_covered_until,
            today + timedelta(days=14),
        )
        test_windows = _future_windows(
            today, week_end, cache.tests_covered_until, today + timedelta(days=14)
        )
        homework_windows = _future_windows(
            today, week_end, cache.homework_covered_until, today + timedelta(days=14)
        )
        school_year_due = (
            cache.school_year_updated_at is None
            or dt_util.utcnow() - cache.school_year_updated_at >= timedelta(hours=24)
        )
        try:
            profile = await self._async_api_operation(
                "student_profile",
                "GET",
                api_url(institution, "Sajat/TanuloAdatlap"),
                self.client.async_get_student_profile(),
            )
            fresh_lessons = (
                await self._async_fetch_windows(
                    "lessons",
                    api_url(institution, "Sajat/OrarendElemek"),
                    lesson_windows,
                    self.client.async_get_lessons,
                )
                if self._enabled(CONF_TIMETABLE)
                else []
            )
            fresh_tests = (
                await self._async_fetch_windows(
                    "announced_tests",
                    api_url(institution, "Sajat/BejelentettSzamonkeresek"),
                    test_windows,
                    self.client.async_get_announced_tests,
                )
                if self._enabled(CONF_TESTS)
                else []
            )
            fresh_grades = (
                await self._async_optional_api_operation(
                    "grades",
                    "GET",
                    api_url(institution, "Sajat/Ertekelesek"),
                    self.client.async_get_grades(grades_fetch_start, today),
                )
                if self._enabled(CONF_GRADES)
                else []
            )
            fresh_homework = (
                await self._async_fetch_windows(
                    "homework",
                    api_url(institution, "Sajat/HaziFeladatok"),
                    homework_windows,
                    self.client.async_get_homework,
                )
                if self._enabled(CONF_HOMEWORK)
                else []
            )
            fresh_absences = (
                await self._async_optional_api_operation(
                    "absences",
                    "GET",
                    api_url(institution, "Sajat/Mulasztasok"),
                    self.client.async_get_absences(absences_fetch_start, today),
                )
                if self._enabled(CONF_ABSENCES)
                else []
            )
            fresh_messages = (
                await self._async_optional_api_operation(
                    "messages",
                    "GET",
                    MESSAGES_URL,
                    self.client.async_get_messages(),
                )
                if self._enabled(CONF_MESSAGES)
                else []
            )
            fresh_school_year = (
                await self._async_optional_api_operation(
                    "school_year_calendar",
                    "GET",
                    api_url(institution, "Sajat/Intezmenyek/TanevRendjeElemek"),
                    self.client.async_get_school_year_calendar(),
                )
                if self._enabled(CONF_SCHOOL_YEAR) and school_year_due
                else cache.school_year
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

        lessons = (
            (
                cache.lessons
                if "lessons" in self.degraded_operations
                else _merge_fetched_windows(
                    "lessons",
                    cache.lessons,
                    fresh_lessons,
                    history_start,
                    week_end,
                )
            )
            if self._enabled(CONF_TIMETABLE)
            else []
        )
        tests = (
            (
                cache.tests
                if "announced_tests" in self.degraded_operations
                else _merge_fetched_windows("tests", cache.tests, fresh_tests, today, week_end)
            )
            if self._enabled(CONF_TESTS)
            else []
        )
        grades = (
            (
                cache.grades
                if "grades" in self.degraded_operations
                else _merge_window(
                    "grades",
                    cache.grades,
                    fresh_grades,
                    grades_fetch_start,
                    today,
                    history_start,
                    today,
                )
            )
            if self._enabled(CONF_GRADES)
            else []
        )
        homework = (
            (
                cache.homework
                if "homework" in self.degraded_operations
                else _merge_fetched_windows(
                    "homework",
                    cache.homework,
                    fresh_homework,
                    today,
                    week_end,
                )
            )
            if self._enabled(CONF_HOMEWORK)
            else []
        )
        absences = (
            (
                cache.absences
                if "absences" in self.degraded_operations
                else _merge_window(
                    "absences",
                    cache.absences,
                    fresh_absences,
                    absences_fetch_start,
                    today,
                    history_start,
                    today,
                )
            )
            if self._enabled(CONF_ABSENCES)
            else []
        )
        messages = (
            (cache.messages if "messages" in self.degraded_operations else fresh_messages)
            if self._enabled(CONF_MESSAGES)
            else []
        )
        school_year = (
            (
                cache.school_year
                if "school_year_calendar" in self.degraded_operations
                else fresh_school_year
            )
            if self._enabled(CONF_SCHOOL_YEAR)
            else []
        )
        current_fresh_lessons = (
            [item for _start, _end, records in fresh_lessons for item in records]
            if "lessons" not in self.degraded_operations
            else []
        )
        detected_changes = detect_timetable_changes(cache.lessons, current_fresh_lessons)
        retained_changes = [
            item for item in cache.changes if item.start.date() >= today - timedelta(days=30)
        ]
        change_keys = {
            (item.lesson_uid, item.change_type, item.start, item.old_value, item.new_value)
            for item in retained_changes
        }
        for change in detected_changes:
            key = (
                change.lesson_uid,
                change.change_type,
                change.start,
                change.old_value,
                change.new_value,
            )
            if key not in change_keys:
                retained_changes.append(change)
                change_keys.add(key)
        changes = retained_changes[-200:]
        events = merge_lessons_and_tests(lessons, tests)
        if self.config_entry.options.get(CONF_AUTOMATION_EVENTS, True):
            new_counts = {
                "grades": await self._emit_new("grades", grades, EVENT_NEW_GRADE),
                "homework": await self._emit_new("homework", homework, EVENT_NEW_HOMEWORK),
                "tests": await self._emit_new("tests", tests, EVENT_NEW_TEST),
                "absences": await self._emit_new("absences", absences, EVENT_NEW_ABSENCE),
                "messages": await self._emit_new("messages", messages, EVENT_NEW_MESSAGE),
                "timetable": await self._emit_timetable_changes(detected_changes),
            }
        else:
            new_counts = {
                key: 0
                for key in ("grades", "homework", "tests", "absences", "messages", "timetable")
            }
        new_counts["degraded"] = len(self.degraded_operations)
        snapshot = KretaCacheSnapshot(
            lessons=lessons,
            grades=grades,
            homework=homework,
            tests=tests,
            absences=absences,
            messages=messages,
            school_year=school_year,
            changes=changes,
            school_year_updated_at=(
                dt_util.utcnow()
                if self._enabled(CONF_SCHOOL_YEAR)
                and school_year_due
                and "school_year_calendar" not in self.degraded_operations
                else cache.school_year_updated_at
                if self._enabled(CONF_SCHOOL_YEAR)
                else None
            ),
            lessons_covered_from=(
                history_start
                if self._enabled(CONF_TIMETABLE) and "lessons" not in self.degraded_operations
                else cache.lessons_covered_from
                if self._enabled(CONF_TIMETABLE)
                else None
            ),
            lessons_covered_until=(
                week_end
                if self._enabled(CONF_TIMETABLE) and "lessons" not in self.degraded_operations
                else cache.lessons_covered_until
                if self._enabled(CONF_TIMETABLE)
                else None
            ),
            grades_covered_from=(
                history_start
                if self._enabled(CONF_GRADES) and "grades" not in self.degraded_operations
                else cache.grades_covered_from
                if self._enabled(CONF_GRADES)
                else None
            ),
            absences_covered_from=(
                history_start
                if self._enabled(CONF_ABSENCES) and "absences" not in self.degraded_operations
                else cache.absences_covered_from
                if self._enabled(CONF_ABSENCES)
                else None
            ),
            tests_covered_until=(
                week_end
                if self._enabled(CONF_TESTS) and "announced_tests" not in self.degraded_operations
                else cache.tests_covered_until
                if self._enabled(CONF_TESTS)
                else None
            ),
            homework_covered_until=(
                week_end
                if self._enabled(CONF_HOMEWORK) and "homework" not in self.degraded_operations
                else cache.homework_covered_until
                if self._enabled(CONF_HOMEWORK)
                else None
            ),
        )
        if cache_store:
            await cache_store.async_save(snapshot)
        if self.degraded_operations:
            self.last_error_message = "partial_data"
            self.last_error_time = dt_util.utcnow()
        else:
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
            changes=changes,
            range_start=range_start,
            range_end=range_end,
            last_success=dt_util.utcnow(),
            lessons_count=len(lessons),
            tests_count=len(tests),
            new_counts=new_counts,
        )
