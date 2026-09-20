"""Versioned non-secret KRÉTA data cache."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from ..const import DATA_CACHE_STORAGE_KEY, DATA_CACHE_STORAGE_VERSION
from .models import (
    Absence,
    AnnouncedTest,
    Grade,
    HomeworkItem,
    MergedCalendarEvent,
    MessageSummary,
    SchoolYearMilestone,
)


@dataclass(slots=True)
class KretaCacheSnapshot:
    """Typed cache payload without authentication or profile secrets."""

    lessons: list[MergedCalendarEvent] = field(default_factory=list)
    grades: list[Grade] = field(default_factory=list)
    homework: list[HomeworkItem] = field(default_factory=list)
    tests: list[AnnouncedTest] = field(default_factory=list)
    absences: list[Absence] = field(default_factory=list)
    messages: list[MessageSummary] = field(default_factory=list)
    school_year: list[SchoolYearMilestone] = field(default_factory=list)
    school_year_updated_at: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a bounded JSON-serializable storage payload."""
        return {
            "lessons": [item.as_dict() for item in self.lessons[-5000:]],
            "grades": [item.as_dict() for item in self.grades[-2000:]],
            "homework": [item.as_dict() for item in self.homework[-2000:]],
            "tests": [item.as_dict() for item in self.tests[-1000:]],
            "absences": [item.as_dict() for item in self.absences[-3000:]],
            "messages": [item.as_dict() for item in self.messages[:200]],
            "school_year": [item.as_dict() for item in self.school_year[-1000:]],
            "school_year_updated_at": (
                self.school_year_updated_at.isoformat() if self.school_year_updated_at else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KretaCacheSnapshot:
        """Restore valid cached records and ignore malformed rows."""

        def restore(name: str, factory: Any, limit: int) -> list[Any]:
            result: list[Any] = []
            rows = data.get(name, [])
            if not isinstance(rows, list):
                return result
            for row in rows[:limit]:
                if not isinstance(row, dict):
                    continue
                try:
                    result.append(factory(row))
                except (KeyError, TypeError, ValueError):
                    continue
            return result

        updated_at = data.get("school_year_updated_at")
        return cls(
            lessons=restore("lessons", MergedCalendarEvent.from_dict, 5000),
            grades=restore("grades", Grade.from_dict, 2000),
            homework=restore("homework", HomeworkItem.from_dict, 2000),
            tests=restore("tests", AnnouncedTest.from_dict, 1000),
            absences=restore("absences", Absence.from_dict, 3000),
            messages=restore("messages", MessageSummary.from_dict, 200),
            school_year=restore("school_year", SchoolYearMilestone.from_dict, 1000),
            school_year_updated_at=(
                datetime.fromisoformat(updated_at) if isinstance(updated_at, str) else None
            ),
        )


class KretaDataCache:
    """Persist one privacy-bounded cache per opaque account key."""

    def __init__(self, hass: HomeAssistant, account_key: str) -> None:
        self._account_key = account_key
        self._store: Store[dict[str, Any]] = Store(
            hass, DATA_CACHE_STORAGE_VERSION, DATA_CACHE_STORAGE_KEY
        )

    async def async_load(self) -> KretaCacheSnapshot:
        """Load the account cache."""
        data = await self._store.async_load() or {}
        account = data.get(self._account_key)
        return (
            KretaCacheSnapshot.from_dict(account)
            if isinstance(account, dict)
            else KretaCacheSnapshot()
        )

    async def async_save(self, snapshot: KretaCacheSnapshot) -> None:
        """Persist the account cache without secrets."""
        data = await self._store.async_load() or {}
        data[self._account_key] = snapshot.as_dict()
        await self._store.async_save(data)
