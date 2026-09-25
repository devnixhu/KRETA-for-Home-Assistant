"""Binary sensor platform for Kreta."""

from __future__ import annotations

from datetime import date, timedelta

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import KretaRuntimeData
from .api.models import MergedCalendarEvent
from .const import DOMAIN
from .entity import KretaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kreta binary sensors."""
    runtime_data: KretaRuntimeData = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            KretaDayBinarySensor(entry, runtime_data, "school_day", "Is School Day"),
            KretaDayBinarySensor(
                entry,
                runtime_data,
                "school_day_tomorrow",
                "Is School Day Tomorrow",
                day_offset=1,
            ),
            KretaDayBinarySensor(
                entry,
                runtime_data,
                "exam_day",
                "Is Exam Day",
                event_kind="exam",
            ),
            KretaDayBinarySensor(
                entry,
                runtime_data,
                "exam_day_tomorrow",
                "Is Exam Day Tomorrow",
                day_offset=1,
                event_kind="exam",
            ),
            KretaConditionBinarySensor(entry, runtime_data, "in_lesson", "In lesson", _in_lesson),
            KretaConditionBinarySensor(entry, runtime_data, "on_break", "On break", _on_break),
            KretaConditionBinarySensor(
                entry, runtime_data, "school_finished", "School finished", _school_finished
            ),
            KretaConditionBinarySensor(
                entry,
                runtime_data,
                "homework_due_today",
                "Homework due today",
                lambda data: any(item.due_date == dt_util.now().date() for item in data.homework),
            ),
            KretaConditionBinarySensor(
                entry,
                runtime_data,
                "test_today",
                "Test today",
                lambda data: any(item.test_date == dt_util.now().date() for item in data.tests),
            ),
            KretaConditionBinarySensor(
                entry,
                runtime_data,
                "test_tomorrow",
                "Test tomorrow",
                lambda data: any(
                    item.test_date == dt_util.now().date() + timedelta(days=1)
                    for item in data.tests
                ),
            ),
            KretaConditionBinarySensor(
                entry,
                runtime_data,
                "schedule_changed",
                "Schedule changed",
                lambda data: bool(data.changes),
            ),
            KretaConditionBinarySensor(
                entry,
                runtime_data,
                "substitution_today",
                "Substitution today",
                lambda data: any(
                    item.is_substitution and item.start.date() == dt_util.now().date()
                    for item in data.events
                ),
            ),
            KretaConditionBinarySensor(
                entry,
                runtime_data,
                "substitution_tomorrow",
                "Substitution tomorrow",
                lambda data: any(
                    item.is_substitution
                    and item.start.date() == dt_util.now().date() + timedelta(days=1)
                    for item in data.events
                ),
            ),
        ]
    )


def _today_lessons(data):
    today = dt_util.now().date()
    return [
        item
        for item in data.events
        if item.source != "exam_only" and not item.is_cancelled and item.start.date() == today
    ]


def _in_lesson(data) -> bool:
    now = dt_util.now()
    return any(item.start <= now < item.end for item in _today_lessons(data))


def _on_break(data) -> bool:
    now = dt_util.now()
    lessons = _today_lessons(data)
    return bool(lessons and lessons[0].start <= now < lessons[-1].end and not _in_lesson(data))


def _school_finished(data) -> bool:
    lessons = _today_lessons(data)
    return bool(lessons and dt_util.now() >= lessons[-1].end)


class KretaConditionBinarySensor(KretaEntity, BinarySensorEntity):
    def __init__(self, entry, runtime_data, key, name, condition) -> None:
        super().__init__(entry, runtime_data)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._condition = condition
        self._attr_entity_registry_enabled_default = key in {
            "in_lesson",
            "homework_due_today",
            "test_today",
        }

    @property
    def is_on(self) -> bool | None:
        return self._condition(self.coordinator.data) if self.coordinator.data else None


class KretaDayBinarySensor(KretaEntity, BinarySensorEntity):
    """Binary sensor derived from timetable and exam events."""

    def __init__(
        self,
        entry: ConfigEntry,
        runtime_data: KretaRuntimeData,
        key: str,
        name: str,
        *,
        day_offset: int = 0,
        event_kind: str = "lesson",
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(entry, runtime_data)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._day_offset = day_offset
        self._event_kind = event_kind
        self._attr_icon = "mdi:school" if event_kind == "lesson" else "mdi:clipboard-text"

    @property
    def is_on(self) -> bool | None:
        """Return whether the target condition is true for the selected day."""
        if self.coordinator.data is None:
            return None

        target_date = dt_util.now().date() + timedelta(days=self._day_offset)
        return any(
            self._event_matches(event, target_date) for event in self.coordinator.data.events
        )

    def _event_matches(self, event: MergedCalendarEvent, target_date: date) -> bool:
        """Return whether an event contributes to the sensor state."""
        if self._event_kind == "lesson":
            return (
                event.source != "exam_only"
                and not event.is_cancelled
                and event.start.date() == target_date
            )

        return event.exam is not None and event.exam.test_date == target_date
