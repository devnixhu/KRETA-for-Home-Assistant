
from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import KretaRuntimeData
from .api.models import MergedCalendarEvent
from .const import DOMAIN
from .entity import KretaEntity


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
            KretaSchoolStatusSensor(entry, runtime),
            KretaBriefSensor(entry, runtime, 0),
            KretaBriefSensor(entry, runtime, 1),
            KretaLastRefreshSensor(entry, runtime),
            KretaUpdateStatusSensor(entry, runtime),
        ]
    )


def _lesson_events(events: list[MergedCalendarEvent]) -> list[MergedCalendarEvent]:
    return [event for event in events if event.source != "exam_only"]


def _current_lesson(events: list[MergedCalendarEvent]) -> MergedCalendarEvent | None:
    now = dt_util.now()
    return next((event for event in _lesson_events(events) if event.start <= now < event.end), None)


def _next_lesson(events: list[MergedCalendarEvent]) -> MergedCalendarEvent | None:
    now = dt_util.now()
    return next((event for event in _lesson_events(events) if event.start > now), None)


def _lessons_on(events: list[MergedCalendarEvent], offset: int) -> int:
    target = dt_util.now().date() + timedelta(days=offset)
    return sum(event.start.date() == target for event in _lesson_events(events))


def _tests_this_week(data: Any) -> int:
    today = dt_util.now().date()
    end = today + timedelta(days=6 - today.weekday())
    return sum(today <= item.test_date <= end for item in data.tests)


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
        self._attr_name = name
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
        self._attr_name = name
        self._selector = selector

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
            "minutes_until": max(
                0,
                int(
                    ((event.end if event.start <= now else event.start) - now).total_seconds() // 60
                ),
            ),
        }


class KretaLatestGradeSensor(KretaEntity, SensorEntity):
    _attr_name = "Latest grade"
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
            "weight": None,
        }


class KretaNextTestSensor(KretaEntity, SensorEntity):
    _attr_name = "Next test"
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
    _attr_name = "Latest message"
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
    _attr_name = "School status"
    _attr_icon = "mdi:school-outline"

    def __init__(self, entry: ConfigEntry, runtime: KretaRuntimeData) -> None:
        super().__init__(entry, runtime)
        self._attr_unique_id = f"{entry.entry_id}_school_status"

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
        self._attr_name = "Today summary" if offset == 0 else "Tomorrow summary"

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
        }


class KretaLastRefreshSensor(KretaEntity, SensorEntity):
    _attr_name = "Last refresh"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry, runtime: KretaRuntimeData) -> None:
        super().__init__(entry, runtime)
        self._attr_unique_id = f"{entry.entry_id}_last_refresh"

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.data.last_success if self.coordinator.data else None


class KretaUpdateStatusSensor(KretaEntity, SensorEntity):
    _attr_name = "Connection status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [
        "ok",
        "authentication_required",
        "temporarily_unavailable",
        "rate_limited",
        "error",
    ]
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry: ConfigEntry, runtime: KretaRuntimeData) -> None:
        super().__init__(entry, runtime)
        self._attr_unique_id = f"{entry.entry_id}_connection_status"

    @property
    def native_value(self) -> str:
        if self.coordinator.last_update_success:
            return "ok"
        return self.coordinator.last_error_message or "error"
