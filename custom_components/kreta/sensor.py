from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from . import KretaRuntimeData
from .api.models import MergedCalendarEvent
from .const import DOMAIN
from .entity import KretaEntity
from .queries import grades_payload


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    runtime: KretaRuntimeData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            KretaLessonSensor(entry, runtime, "current_lesson", "Current lesson", _current_lesson),
            KretaLessonSensor(entry, runtime, "next_lesson", "Next lesson", _next_lesson),
            KretaCountSensor(
                entry,
                runtime,
                "lessons_today",
                "Lessons today",
                lambda data: _lessons_on(data.events, 0),
            ),
            KretaCountSensor(
                entry,
                runtime,
                "lessons_tomorrow",
                "Lessons tomorrow",
                lambda data: _lessons_on(data.events, 1),
            ),
            KretaLatestGradeSensor(entry, runtime),
            KretaPreviousGradeSensor(entry, runtime),
            KretaGradeAverageSensor(entry, runtime),
            KretaCountSensor(
                entry, runtime, "grades_count", "Grades count", lambda data: len(data.grades)
            ),
            KretaCountSensor(entry, runtime, "grades_this_week", "Grades this week", _grades_week),
            KretaCountSensor(
                entry, runtime, "grades_this_month", "Grades this month", _grades_month
            ),
            KretaCountSensor(
                entry,
                runtime,
                "new_grades",
                "New grades",
                lambda data: data.new_counts.get("grades", 0),
            ),
            KretaCountSensor(
                entry,
                runtime,
                "upcoming_homework",
                "Upcoming homework",
                lambda data: len(data.homework),
            ),
            KretaNextTestSensor(entry, runtime),
            KretaCountSensor(
                entry, runtime, "tests_today", "Tests today", lambda data: _tests_on(data, 0)
            ),
            KretaCountSensor(
                entry, runtime, "tests_tomorrow", "Tests tomorrow", lambda data: _tests_on(data, 1)
            ),
            KretaCountSensor(
                entry, runtime, "upcoming_tests", "Upcoming tests", lambda data: len(data.tests)
            ),
            KretaCountSensor(
                entry, runtime, "tests_this_week", "Tests this week", _tests_this_week
            ),
            KretaCountSensor(
                entry,
                runtime,
                "unread_messages",
                "Unread messages",
                lambda data: sum(not item.is_read for item in data.messages),
            ),
            KretaLatestMessageSensor(entry, runtime),
            KretaCountSensor(
                entry, runtime, "messages_this_week", "Messages this week", _messages_week
            ),
            KretaCountSensor(
                entry,
                runtime,
                "absences",
                "Absences",
                lambda data: sum(item.minutes is None for item in data.absences),
            ),
            KretaCountSensor(
                entry,
                runtime,
                "late_arrivals",
                "Late arrivals",
                lambda data: sum(item.minutes is not None for item in data.absences),
            ),
            KretaCountSensor(
                entry,
                runtime,
                "total_late_minutes",
                "Total late minutes",
                lambda data: sum(item.minutes or 0 for item in data.absences),
            ),
            KretaCountSensor(
                entry, runtime, "absences_this_month", "Absences this month", _absences_month
            ),
            KretaAbsenceStatusSensor(
                entry, runtime, "justified_absences", "Justified absences", "igazolt"
            ),
            KretaAbsenceStatusSensor(
                entry, runtime, "unjustified_absences", "Unjustified absences", "igazolatlan"
            ),
            KretaAbsenceStatusSensor(
                entry, runtime, "pending_absences", "Pending absences", "pending"
            ),
            KretaSchoolStatusSensor(entry, runtime),
            KretaBriefSensor(entry, runtime, 0),
            KretaBriefSensor(entry, runtime, 1),
            KretaWeekSummarySensor(entry, runtime),
            KretaNextMilestoneSensor(entry, runtime),
            KretaLastRefreshSensor(entry, runtime),
            KretaUpdateStatusSensor(entry, runtime),
        ]
    )


def _lesson_events(events: list[MergedCalendarEvent]) -> list[MergedCalendarEvent]:
    return [event for event in events if event.source != "exam_only"]


def _current_lesson(events: list[MergedCalendarEvent]) -> MergedCalendarEvent | None:
    now = dt_util.now()
    return next(
        (
            event
            for event in _lesson_events(events)
            if not event.is_cancelled and event.start <= now < event.end
        ),
        None,
    )


def _next_lesson(events: list[MergedCalendarEvent]) -> MergedCalendarEvent | None:
    now = dt_util.now()
    return next(
        (event for event in _lesson_events(events) if not event.is_cancelled and event.start > now),
        None,
    )


def _lessons_on(events: list[MergedCalendarEvent], offset: int) -> int:
    target = dt_util.now().date() + timedelta(days=offset)
    return sum(event.start.date() == target for event in _lesson_events(events))


def _tests_this_week(data: Any) -> int:
    today = dt_util.now().date()
    end = today + timedelta(days=6 - today.weekday())
    return sum(today <= item.test_date <= end for item in data.tests)


def _tests_on(data: Any, offset: int) -> int:
    target = dt_util.now().date() + timedelta(days=offset)
    return sum(item.test_date == target for item in data.tests)


def _grades_week(data: Any) -> int:
    today = dt_util.now().date()
    start = today - timedelta(days=today.weekday())
    return sum(start <= item.grade_date <= today for item in data.grades)


def _grades_month(data: Any) -> int:
    today = dt_util.now().date()
    return sum(
        item.grade_date.year == today.year and item.grade_date.month == today.month
        for item in data.grades
    )


def _messages_week(data: Any) -> int:
    start = dt_util.now() - timedelta(days=7)
    return sum(item.received_at >= start for item in data.messages)


def _absences_month(data: Any) -> int:
    today = dt_util.now().date()
    return sum(
        item.absence_date.year == today.year and item.absence_date.month == today.month
        for item in data.absences
    )


class KretaCountSensor(KretaEntity, SensorEntity):
    _attr_native_unit_of_measurement = "items"

    def __init__(
        self,
        entry: ConfigEntry,
        runtime: KretaRuntimeData,
        key: str,
        name: str,
        value_fn: Callable[[Any], int],
    ) -> None:
        super().__init__(entry, runtime)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._value_fn = value_fn

    @property
    def native_value(self) -> int | None:
        return self._value_fn(self.coordinator.data) if self.coordinator.data else None


class KretaLessonSensor(KretaEntity, SensorEntity):
    _attr_icon = "mdi:book-open-variant"

    def __init__(
        self,
        entry: ConfigEntry,
        runtime: KretaRuntimeData,
        key: str,
        name: str,
        selector: Callable[[list[MergedCalendarEvent]], MergedCalendarEvent | None],
    ) -> None:
        super().__init__(entry, runtime)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._selector = selector

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_interval(
                self.hass, lambda _now: self.async_write_ha_state(), timedelta(minutes=1)
            )
        )

    def _event(self) -> MergedCalendarEvent | None:
        return self._selector(self.coordinator.data.events) if self.coordinator.data else None

    @property
    def native_value(self) -> str | None:
        event = self._event()
        return event.subject_name if event else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        event = self._event()
        if not event:
            return {}
        now = dt_util.now()
        return {
            "start": event.start.isoformat(),
            "end": event.end.isoformat(),
            "room": event.location,
            "teacher": event.teacher_name,
            "lesson_index": event.lesson_index,
            "topic": event.topic,
            "progress_percent": max(
                0,
                min(
                    100,
                    round(
                        (now - event.start).total_seconds()
                        / max(1, (event.end - event.start).total_seconds())
                        * 100
                    ),
                ),
            )
            if event.start <= now < event.end
            else 0,
            "minutes_elapsed": max(0, int((now - event.start).total_seconds() // 60))
            if event.start <= now
            else 0,
            "minutes_remaining": max(0, int((event.end - now).total_seconds() // 60))
            if event.start <= now
            else max(0, int((event.start - now).total_seconds() // 60)),
            "is_substitution": event.is_substitution,
            "substitute_teacher": event.substitute_teacher_name,
            "is_cancelled": event.is_cancelled,
            "next_lesson": self.coordinator.data.next_lesson(now).subject_name
            if self.coordinator.data and self.coordinator.data.next_lesson(now)
            else None,
            "next_lesson_start": self.coordinator.data.next_lesson(now).start.isoformat()
            if self.coordinator.data and self.coordinator.data.next_lesson(now)
            else None,
        }


class KretaLatestGradeSensor(KretaEntity, SensorEntity):
    _attr_translation_key = "latest_grade"
    _attr_icon = "mdi:school"

    def __init__(self, entry: ConfigEntry, runtime: KretaRuntimeData) -> None:
        super().__init__(entry, runtime)
        self._attr_unique_id = f"{entry.entry_id}_latest_grade"

    @property
    def native_value(self) -> str | None:
        return (
            self.coordinator.data.grades[-1].value
            if self.coordinator.data and self.coordinator.data.grades
            else None
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data or not self.coordinator.data.grades:
            return {}
        grade = self.coordinator.data.grades[-1]
        return {
            "subject": grade.subject_name,
            "type": grade.grade_type,
            "date": grade.grade_date.isoformat(),
            "numeric_grade": grade.numeric_value,
            "weight": grade.weight_percentage,
            "topic": grade.topic,
            "teacher": grade.teacher_name,
        }


class KretaPreviousGradeSensor(KretaLatestGradeSensor):
    _attr_translation_key = "previous_grade"

    def __init__(self, entry: ConfigEntry, runtime: KretaRuntimeData) -> None:
        super().__init__(entry, runtime)
        self._attr_unique_id = f"{entry.entry_id}_previous_grade"
        self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> str | None:
        return (
            self.coordinator.data.grades[-2].value
            if self.coordinator.data and len(self.coordinator.data.grades) > 1
            else None
        )


class KretaGradeAverageSensor(KretaEntity, SensorEntity):
    _attr_translation_key = "grade_average"
    _attr_icon = "mdi:chart-line"

    def __init__(self, entry: ConfigEntry, runtime: KretaRuntimeData) -> None:
        super().__init__(entry, runtime)
        self._attr_unique_id = f"{entry.entry_id}_grade_average"

    @property
    def native_value(self) -> float | None:
        return (
            grades_payload(self.coordinator.data, 1)["average"] if self.coordinator.data else None
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        result = grades_payload(self.coordinator.data, 1)
        return {"weighted": result["weighted"], "subject_averages": result["subject_averages"]}


class KretaAbsenceStatusSensor(KretaCountSensor):
    def __init__(self, entry, runtime, key, name, status):
        super().__init__(
            entry,
            runtime,
            key,
            name,
            lambda data: sum(status in item.status.casefold() for item in data.absences),
        )
        self._attr_entity_registry_enabled_default = False


class KretaNextTestSensor(KretaEntity, SensorEntity):
    _attr_translation_key = "next_test"
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, entry: ConfigEntry, runtime: KretaRuntimeData) -> None:
        super().__init__(entry, runtime)
        self._attr_unique_id = f"{entry.entry_id}_next_test"

    def _test(self):
        today = dt_util.now().date()
        return (
            next((item for item in self.coordinator.data.tests if item.test_date >= today), None)
            if self.coordinator.data
            else None
        )

    @property
    def native_value(self) -> date | None:
        test = self._test()
        return test.test_date if test else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        test = self._test()
        return {"subject": test.subject_name, "type": test.mode} if test else {}


class KretaLatestMessageSensor(KretaEntity, SensorEntity):
    _attr_translation_key = "latest_message"
    _attr_icon = "mdi:email-outline"

    def __init__(self, entry: ConfigEntry, runtime: KretaRuntimeData) -> None:
        super().__init__(entry, runtime)
        self._attr_unique_id = f"{entry.entry_id}_latest_message"

    @property
    def native_value(self) -> str | None:
        return (
            self.coordinator.data.messages[0].subject
            if self.coordinator.data and self.coordinator.data.messages
            else None
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data or not self.coordinator.data.messages:
            return {}
        message = self.coordinator.data.messages[0]
        return {
            "sender": message.sender,
            "received_at": message.received_at.isoformat(),
            "is_read": message.is_read,
        }


class KretaSchoolStatusSensor(KretaEntity, SensorEntity):
    _attr_translation_key = "school_status"
    _attr_icon = "mdi:school-outline"

    def __init__(self, entry: ConfigEntry, runtime: KretaRuntimeData) -> None:
        super().__init__(entry, runtime)
        self._attr_unique_id = f"{entry.entry_id}_school_status"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_interval(
                self.hass, lambda _now: self.async_write_ha_state(), timedelta(minutes=1)
            )
        )

    @property
    def native_value(self) -> str:
        if not self.coordinator.data:
            return "no_school"
        now = dt_util.now()
        today = [
            event
            for event in _lesson_events(self.coordinator.data.events)
            if event.start.date() == now.date()
        ]
        if not today:
            return "no_school"
        if now < today[0].start:
            return "before_school"
        if now >= today[-1].end:
            return "after_school"
        return "lesson" if _current_lesson(today) else "break"


class KretaBriefSensor(KretaEntity, SensorEntity):
    _attr_icon = "mdi:calendar-today"

    def __init__(self, entry: ConfigEntry, runtime: KretaRuntimeData, offset: int) -> None:
        super().__init__(entry, runtime)
        self._offset = offset
        key = "today_summary" if offset == 0 else "tomorrow_summary"
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key

    @property
    def native_value(self) -> int | None:
        return (
            _lessons_on(self.coordinator.data.events, self._offset)
            if self.coordinator.data
            else None
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        target = dt_util.now().date() + timedelta(days=self._offset)
        lessons = [
            event
            for event in _lesson_events(self.coordinator.data.events)
            if event.start.date() == target
        ]
        return {
            "lesson_count": len(lessons),
            "first_lesson": lessons[0].subject_name if lessons else None,
            "last_lesson": lessons[-1].subject_name if lessons else None,
            "tests": sum(item.test_date == target for item in self.coordinator.data.tests),
            "homework_due": sum(item.due_date == target for item in self.coordinator.data.homework),
            "schedule_changes": self.coordinator.data.new_counts.get("timetable", 0),
            "substitutions": sum(item.is_substitution for item in lessons),
            "cancelled_lessons": sum(item.is_cancelled for item in lessons),
            "start_time": lessons[0].start.isoformat() if lessons else None,
            "end_time": lessons[-1].end.isoformat() if lessons else None,
        }


class KretaWeekSummarySensor(KretaEntity, SensorEntity):
    _attr_translation_key = "week_summary"
    _attr_icon = "mdi:calendar-week"

    def __init__(self, entry: ConfigEntry, runtime: KretaRuntimeData) -> None:
        super().__init__(entry, runtime)
        self._attr_unique_id = f"{entry.entry_id}_week_summary"

    @property
    def native_value(self) -> int | None:
        return len(self._lessons()) if self.coordinator.data else None

    def _lessons(self) -> list[MergedCalendarEvent]:
        today = dt_util.now().date()
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        return [
            item
            for item in _lesson_events(self.coordinator.data.events)
            if monday <= item.start.date() <= sunday
        ]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        lessons = self._lessons()
        days = sorted({item.start.date() for item in lessons})
        return {
            "school_days": len(days),
            "lesson_count": len(lessons),
            "test_count": _tests_this_week(self.coordinator.data),
            "substitutions": sum(item.is_substitution for item in lessons),
            "first_school_day": days[0].isoformat() if days else None,
            "last_school_day": days[-1].isoformat() if days else None,
        }


class KretaNextMilestoneSensor(KretaEntity, SensorEntity):
    _attr_translation_key = "next_school_year_event"
    _attr_device_class = SensorDeviceClass.DATE
    _attr_icon = "mdi:calendar-star"

    def __init__(self, entry: ConfigEntry, runtime: KretaRuntimeData) -> None:
        super().__init__(entry, runtime)
        self._attr_unique_id = f"{entry.entry_id}_next_school_year_event"

    def _milestone(self):
        today = dt_util.now().date()
        return (
            next(
                (
                    item
                    for item in self.coordinator.data.school_year_calendar
                    if item.event_date >= today
                ),
                None,
            )
            if self.coordinator.data
            else None
        )

    @property
    def native_value(self) -> date | None:
        item = self._milestone()
        return item.event_date if item else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        item = self._milestone()
        return {"type": item.day_type, "description": item.description} if item else {}


class KretaLastRefreshSensor(KretaEntity, SensorEntity):
    _attr_translation_key = "last_refresh"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry, runtime: KretaRuntimeData) -> None:
        super().__init__(entry, runtime)
        self._attr_unique_id = f"{entry.entry_id}_last_refresh"

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.data.last_success if self.coordinator.data else None


class KretaUpdateStatusSensor(KretaEntity, SensorEntity):
    _attr_translation_key = "connection_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [
        "ok",
        "authentication_required",
        "temporarily_unavailable",
        "rate_limited",
        "partial_data",
        "error",
    ]
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry, runtime: KretaRuntimeData) -> None:
        super().__init__(entry, runtime)
        self._attr_unique_id = f"{entry.entry_id}_connection_status"

    @property
    def native_value(self) -> str:
        if self.coordinator.last_error_message:
            return self.coordinator.last_error_message
        return "ok" if self.coordinator.last_update_success else "error"
