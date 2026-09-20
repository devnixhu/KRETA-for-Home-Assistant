"""Bounded cached-data queries shared by services and the dashboard."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

from .coordinator import KretaCoordinatorData

MAX_QUERY_LIMIT = 200


def _bounded_limit(value: int | None, default: int = 20) -> int:
    return max(1, min(int(value or default), MAX_QUERY_LIMIT))


def day_payload(data: KretaCoordinatorData, target: date) -> dict[str, Any]:
    lessons = data.lessons_for_date(target)
    return {
        "date": target.isoformat(),
        "lessons": [item.as_dict() for item in lessons],
        "tests": [item.as_dict() for item in data.tests if item.test_date == target],
        "homework": [item.as_dict() for item in data.homework if item.due_date == target],
        "changes": [item.as_dict() for item in data.changes if item.start.date() == target],
    }


def week_payload(data: KretaCoordinatorData, target: date) -> dict[str, Any]:
    monday = target - timedelta(days=target.weekday())
    days = {
        key: [item.as_dict() for item in lessons]
        for key, lessons in data.lessons_for_week(target).items()
    }
    return {
        "start": monday.isoformat(),
        "end": (monday + timedelta(days=6)).isoformat(),
        "days": days,
    }


def grades_payload(
    data: KretaCoordinatorData,
    limit: int | None = None,
    subject: str | None = None,
    oldest_first: bool = False,
) -> dict[str, Any]:
    selected = data.grades
    if subject:
        selected = [item for item in selected if item.subject_name.casefold() == subject.casefold()]
    selected = sorted(selected, key=lambda item: item.grade_date, reverse=not oldest_first)
    selected = selected[: _bounded_limit(limit)]
    numeric = [item for item in data.grades if item.numeric_value is not None]
    weighted = bool(numeric) and all(
        item.weight_percentage is not None and item.weight_percentage > 0 for item in numeric
    )
    average = None
    if numeric:
        average = (
            sum(item.numeric_value * item.weight_percentage for item in numeric)
            / sum(item.weight_percentage for item in numeric)
            if weighted
            else sum(item.numeric_value for item in numeric) / len(numeric)
        )
    distribution = Counter(str(int(item.numeric_value)) for item in numeric)
    by_subject: dict[str, list[float]] = defaultdict(list)
    for grade in numeric:
        by_subject[grade.subject_name].append(float(grade.numeric_value))
    return {
        "items": [item.as_dict() for item in selected],
        "total": len(data.grades),
        "average": round(average, 2) if average is not None else None,
        "weighted": weighted,
        "distribution": dict(distribution),
        "subject_averages": {
            key: round(sum(values) / len(values), 2) for key, values in by_subject.items()
        },
    }


def list_payload(
    items: list[Any], limit: int | None = None, subject: str | None = None
) -> dict[str, Any]:
    selected = items
    if subject:
        selected = [
            item
            for item in selected
            if str(getattr(item, "subject_name", "")).casefold() == subject.casefold()
        ]
    selected = selected[: _bounded_limit(limit)]
    return {"items": [item.as_dict() for item in selected], "total": len(items)}


def overview_payload(data: KretaCoordinatorData) -> dict[str, Any]:
    now = dt_util.now()
    today = now.date()
    current = data.current_lesson(now)
    next_lesson = data.next_lesson(now)
    return {
        "profile": data.profile.as_dict(),
        "status": "partial_data" if data.new_counts.get("degraded") else "ok",
        "last_update": data.last_success.isoformat(),
        "current_lesson": current.as_dict() if current else None,
        "next_lesson": next_lesson.as_dict() if next_lesson else None,
        "today": day_payload(data, today),
        "tomorrow": day_payload(data, today + timedelta(days=1)),
        "counts": {
            "grades": len(data.grades),
            "tests": len(data.tests),
            "homework": len(data.homework),
            "absences": len(data.absences),
            "messages": len(data.messages),
            "changes": len(data.changes),
        },
    }
