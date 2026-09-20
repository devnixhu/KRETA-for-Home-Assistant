"""Feature and cache behavior tests."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from custom_components.kreta.api.cache import KretaCacheSnapshot
from custom_components.kreta.api.client import KretaApiClient
from custom_components.kreta.api.models import Grade, MergedCalendarEvent, StudentProfile
from custom_components.kreta.api.storage import MemoryTokenStore
from custom_components.kreta.binary_sensor import _in_lesson, _on_break
from custom_components.kreta.coordinator import (
    KretaCoordinatorData,
    _merge_window,
    detect_timetable_changes,
)
from custom_components.kreta.queries import grades_payload, week_payload

BUDAPEST = ZoneInfo("Europe/Budapest")


def _lesson(
    uid: str,
    start: datetime,
    *,
    room: str = "101",
    teacher: str = "Tanár",
    substitute: str | None = None,
    cancelled: bool = False,
) -> MergedCalendarEvent:
    return MergedCalendarEvent(
        uid=uid,
        start=start,
        end=start + timedelta(minutes=45),
        summary="Matematika",
        description=None,
        location=room,
        lesson_index=1,
        subject_name="Matematika",
        exam=None,
        source="lesson",
        teacher_name=teacher,
        substitute_teacher_name=substitute,
        is_substitution=substitute is not None,
        is_cancelled=cancelled,
        state="Elmaradt" if cancelled else "Megtartva",
    )


def _data(events: list[MergedCalendarEvent], grades: list[Grade] | None = None):
    return KretaCoordinatorData(
        profile=StudentProfile(None, "Iskola"),
        events=events,
        grades=grades or [],
        homework=[],
        tests=[],
        absences=[],
        messages=[],
        school_year_calendar=[],
        changes=[],
        range_start=events[0].start if events else datetime.now(BUDAPEST),
        range_end=events[-1].end if events else datetime.now(BUDAPEST),
        last_success=datetime.now(BUDAPEST),
    )


async def test_large_lesson_range_is_chunked(monkeypatch) -> None:
    client = KretaApiClient(
        session=SimpleNamespace(), klik_id="school01", token_store=MemoryTokenStore()
    )
    calls = []

    async def get_json(path, params=None):
        calls.append((path, params))
        return []

    monkeypatch.setattr(client, "_async_get_json", get_json)
    await client.async_get_lessons(date(2026, 1, 1), date(2026, 3, 15))
    assert len(calls) == 3
    assert calls[0][1]["datumTol"] == "2026-01-01"
    assert calls[-1][1]["datumIg"] == "2026-03-15"


async def test_grade_parsing_preserves_numeric_weight_and_unicode(monkeypatch) -> None:
    client = KretaApiClient(
        session=SimpleNamespace(), klik_id="school01", token_store=MemoryTokenStore()
    )

    async def get_json(_path, params=None):
        return [
            {
                "Uid": "grade-1",
                "RogzitesDatuma": "2026-09-18T12:30:00",
                "Tantargy": {"Nev": "Magyar nyelv és irodalom"},
                "SzamErtek": 5,
                "SzovegesErtek": "Jeles (5)",
                "SulySzazalekErteke": 200,
                "ErtekeloTanarNeve": "Árvíztűrő Tükörfúrógép",
            }
        ]

    monkeypatch.setattr(client, "_async_get_json", get_json)
    grades = await client.async_get_grades(date(2026, 9, 1), date(2026, 9, 20))
    assert grades[0].numeric_value == 5
    assert grades[0].weight_percentage == 200
    assert grades[0].teacher_name == "Árvíztűrő Tükörfúrógép"


def test_cache_roundtrip_and_window_deduplication() -> None:
    old = _lesson("same", datetime(2026, 9, 18, 8, tzinfo=BUDAPEST), room="101")
    fresh = _lesson("same", datetime(2026, 9, 18, 8, tzinfo=BUDAPEST), room="202")
    snapshot = KretaCacheSnapshot(lessons=[old])
    restored = KretaCacheSnapshot.from_dict(snapshot.as_dict())
    merged = _merge_window(
        "lessons",
        restored.lessons,
        [fresh],
        date(2026, 9, 18),
        date(2026, 9, 18),
        date(2026, 9, 1),
        date(2026, 10, 1),
    )
    assert len(merged) == 1
    assert merged[0].location == "202"


def test_current_next_and_week_grouping_across_dst() -> None:
    first = _lesson("one", datetime(2026, 10, 23, 8, tzinfo=BUDAPEST))
    dst_day = _lesson("two", datetime(2026, 10, 25, 8, tzinfo=BUDAPEST))
    data = _data([first, dst_day])
    assert data.current_lesson(datetime(2026, 10, 23, 8, 15, tzinfo=BUDAPEST)) == first
    assert data.next_lesson(datetime(2026, 10, 23, 9, tzinfo=BUDAPEST)) == dst_day
    payload = week_payload(data, date(2026, 10, 23))
    assert sum(len(items) for items in payload["days"].values()) == 2
    assert dst_day.start.utcoffset() != first.start.utcoffset()


def test_weighted_and_unweighted_averages() -> None:
    weighted = [
        Grade(date(2026, 9, 1), "Matek", None, "5", None, numeric_value=5, weight_percentage=200),
        Grade(date(2026, 9, 2), "Matek", None, "3", None, numeric_value=3, weight_percentage=100),
    ]
    result = grades_payload(_data([], weighted), 20)
    assert result["weighted"] is True
    assert result["average"] == 4.33
    weighted[1].weight_percentage = None
    result = grades_payload(_data([], weighted), 20)
    assert result["weighted"] is False
    assert result["average"] == 4


def test_timetable_diff_is_field_specific_and_never_uses_disappearance() -> None:
    start = datetime(2026, 9, 18, 8, tzinfo=BUDAPEST)
    old = _lesson("stable", start, room="101", teacher="Első tanár")
    current = _lesson("stable", start, room="202", teacher="Második tanár", substitute="Helyettes")
    kinds = {item.change_type for item in detect_timetable_changes([old], [current])}
    assert kinds == {"room_changed", "teacher_changed", "substitution"}
    assert detect_timetable_changes([old], []) == []


def test_cancelled_lesson_change_is_detected_only_from_explicit_state() -> None:
    start = datetime(2026, 9, 18, 8, tzinfo=BUDAPEST)
    changes = detect_timetable_changes(
        [_lesson("stable", start)], [_lesson("stable", start, cancelled=True)]
    )
    assert [item.change_type for item in changes] == ["lesson_cancelled"]


def test_school_status_helpers(monkeypatch) -> None:
    lesson = _lesson("one", datetime(2026, 9, 18, 8, tzinfo=BUDAPEST))
    data = _data([lesson])
    monkeypatch.setattr(
        "custom_components.kreta.binary_sensor.dt_util.now",
        lambda: datetime(2026, 9, 18, 8, 15, tzinfo=BUDAPEST),
    )
    assert _in_lesson(data) is True
    assert _on_break(data) is False


def test_cache_rejects_malformed_rows() -> None:
    restored = KretaCacheSnapshot.from_dict(
        {"lessons": [{"uid": "broken"}], "grades": ["private raw data"]}
    )
    assert restored.lessons == []
    assert restored.grades == []
