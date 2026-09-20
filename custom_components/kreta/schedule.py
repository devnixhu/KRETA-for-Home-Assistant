"""Local lesson transition scheduling from cached timetable data."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from .const import (
    EVENT_BREAK_STARTED,
    EVENT_LESSON_FINISHED,
    EVENT_LESSON_STARTED,
    EVENT_SCHOOL_FINISHED,
    EVENT_SCHOOL_STARTED,
)
from .coordinator import KretaDataUpdateCoordinator


class KretaTransitionScheduler:
    """Maintain local one-shot transition callbacks for one account."""

    def __init__(
        self, hass: HomeAssistant, entry_id: str, coordinator: KretaDataUpdateCoordinator
    ) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._coordinator = coordinator
        self._unsubscribers: list[Callable[[], None]] = []

    @callback
    def async_reschedule(self) -> None:
        self.async_cancel()
        data = self._coordinator.data
        if data is None:
            return
        now = dt_util.now()
        lessons = [
            item
            for item in data.events
            if item.source != "exam_only" and not item.is_cancelled and item.end > now
        ]
        days: dict[str, list] = {}
        for lesson in lessons:
            days.setdefault(lesson.start.date().isoformat(), []).append(lesson)
            self._schedule(lesson.start, EVENT_LESSON_STARTED, lesson)
            self._schedule(lesson.end, EVENT_LESSON_FINISHED, lesson)
        for day_lessons in days.values():
            ordered = sorted(day_lessons, key=lambda item: item.start)
            self._schedule(ordered[0].start, EVENT_SCHOOL_STARTED, ordered[0])
            self._schedule(ordered[-1].end, EVENT_SCHOOL_FINISHED, ordered[-1])
            for lesson in ordered[:-1]:
                self._schedule(lesson.end, EVENT_BREAK_STARTED, lesson)

    def _schedule(self, moment: datetime, event_type: str, lesson) -> None:
        if moment <= dt_util.now():
            return

        @callback
        def fire(_now: datetime) -> None:
            self._hass.bus.async_fire(
                event_type,
                {
                    "entry_id": self._entry_id,
                    "subject": lesson.subject_name,
                    "lesson_index": lesson.lesson_index,
                    "time": moment.isoformat(),
                },
            )

        self._unsubscribers.append(
            async_track_point_in_utc_time(self._hass, fire, dt_util.as_utc(moment))
        )

    @callback
    def async_cancel(self) -> None:
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
