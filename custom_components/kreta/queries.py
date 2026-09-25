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
    *,
    offset: int = 0,
    search: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    selected = data.grades
    if subject:
        selected = [item for item in selected if item.subject_name.casefold() == subject.casefold()]
    if search:
        needle = search.casefold()
        selected = [
            item
            for item in selected
            if needle in item.subject_name.casefold()
            or needle in (item.topic or "").casefold()
            or needle in (item.value or "").casefold()
        ]
    if date_from:
        selected = [item for item in selected if item.grade_date >= date_from]
    if date_to:
        selected = [item for item in selected if item.grade_date <= date_to]
    selected = sorted(selected, key=lambda item: item.grade_date, reverse=not oldest_first)
    filtered_total = len(selected)
    selected = selected[offset : offset + _bounded_limit(limit)]
    numeric = [
        item
        for item in data.grades
        if item.numeric_value is not None and 1 <= item.numeric_value <= 5
    ]
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
    distribution = Counter(
        str(int(item.numeric_value))
        for item in numeric
        if item.numeric_value == int(item.numeric_value)
    )
    by_subject: dict[str, list[float]] = defaultdict(list)
    for grade in numeric:
        by_subject[grade.subject_name].append(float(grade.numeric_value))
    return {
        "items": [item.as_dict() for item in selected],
        "total": len(data.grades),
        "filtered_total": filtered_total,
        "has_more": offset + len(selected) < filtered_total,
        "subjects": sorted({item.subject_name for item in data.grades})[:100],
        "average": round(average, 2) if average is not None else None,
        "weighted": weighted,
        "distribution": dict(distribution),
        "subject_averages": {
            key: round(sum(values) / len(values), 2) for key, values in by_subject.items()
        },
    }


def list_payload(
    items: list[Any],
    limit: int | None = None,
    subject: str | None = None,
    *,
    offset: int = 0,
) -> dict[str, Any]:
    selected = items
    if subject:
        selected = [
            item
            for item in selected
            if str(getattr(item, "subject_name", "")).casefold() == subject.casefold()
        ]
    filtered_total = len(selected)
    selected = selected[offset : offset + _bounded_limit(limit)]
    return {
        "items": [item.as_dict() for item in selected],
        "total": len(items),
        "filtered_total": filtered_total,
        "has_more": offset + len(selected) < filtered_total,
    }


def absences_payload(
    data: KretaCoordinatorData,
    limit: int | None = None,
    *,
    offset: int = 0,
) -> dict[str, Any]:
    payload = list_payload(data.absences, limit, offset=offset)
    current_month = dt_util.now().date().replace(day=1)

    def normalized(value: str | None) -> str:
        return (value or "").casefold()

    def has_any(value: str | None, terms: tuple[str, ...]) -> bool:
        text = normalized(value)
        return any(term in text for term in terms)

    late = [
        item
        for item in data.absences
        if has_any(item.absence_type, ("kés", "late", "delay")) or bool(item.minutes)
    ]
    payload["summary"] = {
        "total": len(data.absences),
        "justified": sum(
            has_any(item.status, ("igazolt", "justified", "accepted"))
            and not has_any(item.status, ("igazolatlan", "unjustified"))
            for item in data.absences
        ),
        "unjustified": sum(
            has_any(item.status, ("igazolatlan", "unjustified")) for item in data.absences
        ),
        "pending": sum(
            has_any(item.status, ("függ", "pending", "waiting")) for item in data.absences
        ),
        "late_arrivals": len(late),
        "late_minutes": sum(item.minutes or 0 for item in late),
        "this_month": sum(item.absence_date >= current_month for item in data.absences),
    }
    return payload


def overview_payload(data: KretaCoordinatorData) -> dict[str, Any]:
    now = dt_util.now()
    today = now.date()
    current = data.current_lesson(now)
    next_lesson = data.next_lesson(now)
    next_milestone = next(
        (item for item in data.school_year_calendar if item.event_date >= today), None
    )
    return {
        "profile": data.profile.as_dict(),
        "status": "partial_data" if data.new_counts.get("degraded") else "ok",
        "last_update": data.last_success.isoformat(),
        "current_lesson": current.as_dict() if current else None,
        "next_lesson": next_lesson.as_dict() if next_lesson else None,
        "today": day_payload(data, today),
        "tomorrow": day_payload(data, today + timedelta(days=1)),
        "recent_grades": [item.as_dict() for item in data.grades[-5:][::-1]],
        "upcoming_tests": [item.as_dict() for item in data.tests if item.test_date >= today][:5],
        "upcoming_homework": [
            item.as_dict()
            for item in data.homework
            if item.due_date >= today and item.is_done is not True
        ][:5],
        "recent_changes": [item.as_dict() for item in data.changes[-5:][::-1]],
        "next_school_year_event": next_milestone.as_dict() if next_milestone else None,
        "unread_messages": sum(not item.is_read for item in data.messages),
        "counts": {
            "grades": len(data.grades),
            "tests": len(data.tests),
            "homework": len(data.homework),
            "absences": len(data.absences),
            "messages": len(data.messages),
            "changes": len(data.changes),
        },
    }
