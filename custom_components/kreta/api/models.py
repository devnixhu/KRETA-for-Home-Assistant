"""Typed normalized models for KRÉTA responses."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any

from homeassistant.components.calendar import CalendarEvent


@dataclass(slots=True)
class OAuthTokens:
    """Secret token pair with a safe representation."""

    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)


@dataclass(slots=True)
class StudentProfile:
    """Privacy-minimized student profile."""

    student_name: str | None
    school_name: str | None
    birth_name: str | None = None
    birth_place: str | None = None
    mother_name: str | None = None
    phone_number: str | None = None
    email: str | None = None
    birth_date: str | None = None
    education_id: str | None = None
    class_name: str | None = None
    class_master_name: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return only dashboard-safe profile fields."""
        return {"school_name": self.school_name, "class_name": self.class_name}


@dataclass(slots=True)
class AnnouncedTest:
    """A normalized announced test entry."""

    test_date: date
    announced_date: date | None
    subject_name: str
    teacher_name: str | None
    lesson_index: int | None
    theme: str | None
    mode: str | None
    uid: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping."""
        return {
            "uid": self.uid,
            "test_date": self.test_date.isoformat(),
            "announced_date": self.announced_date.isoformat() if self.announced_date else None,
            "subject_name": self.subject_name,
            "teacher_name": self.teacher_name,
            "lesson_index": self.lesson_index,
            "theme": self.theme,
            "mode": self.mode,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnnouncedTest:
        """Restore a normalized test from cache."""
        return cls(
            uid=str(data.get("uid") or ""),
            test_date=date.fromisoformat(data["test_date"]),
            announced_date=(
                date.fromisoformat(data["announced_date"]) if data.get("announced_date") else None
            ),
            subject_name=str(data.get("subject_name") or ""),
            teacher_name=data.get("teacher_name"),
            lesson_index=data.get("lesson_index"),
            theme=data.get("theme"),
            mode=data.get("mode"),
        )


@dataclass(slots=True)
class Grade:
    """A normalized grade or textual evaluation."""

    grade_date: date
    subject_name: str
    grade_type: str | None
    value: str | None
    topic: str | None
    uid: str = ""
    created_at: datetime | None = None
    numeric_value: float | None = None
    weight_percentage: int | None = None
    teacher_name: str | None = None
    mode: str | None = None
    value_type: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping."""
        return {
            "uid": self.uid,
            "grade_date": self.grade_date.isoformat(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "subject_name": self.subject_name,
            "grade_type": self.grade_type,
            "value": self.value,
            "numeric_value": self.numeric_value,
            "weight_percentage": self.weight_percentage,
            "teacher_name": self.teacher_name,
            "topic": self.topic,
            "mode": self.mode,
            "value_type": self.value_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Grade:
        """Restore a normalized grade from cache."""
        return cls(
            uid=str(data.get("uid") or ""),
            grade_date=date.fromisoformat(data["grade_date"]),
            created_at=(
                datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None
            ),
            subject_name=str(data.get("subject_name") or ""),
            grade_type=data.get("grade_type"),
            value=data.get("value"),
            numeric_value=data.get("numeric_value"),
            weight_percentage=data.get("weight_percentage"),
            teacher_name=data.get("teacher_name"),
            topic=data.get("topic"),
            mode=data.get("mode"),
            value_type=data.get("value_type"),
        )


@dataclass(slots=True)
class HomeworkItem:
    """A normalized homework entry."""

    subject_name: str
    description: str | None
    due_date: date
    assigned_date: date | None
    uid: str = ""
    teacher_name: str | None = None
    is_done: bool | None = None
    can_submit: bool | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping."""
        return {
            "uid": self.uid,
            "subject_name": self.subject_name,
            "description": self.description,
            "due_date": self.due_date.isoformat(),
            "assigned_date": self.assigned_date.isoformat() if self.assigned_date else None,
            "teacher_name": self.teacher_name,
            "is_done": self.is_done,
            "can_submit": self.can_submit,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HomeworkItem:
        """Restore normalized homework from cache."""
        return cls(
            uid=str(data.get("uid") or ""),
            subject_name=str(data.get("subject_name") or ""),
            description=data.get("description"),
            due_date=date.fromisoformat(data["due_date"]),
            assigned_date=(
                date.fromisoformat(data["assigned_date"]) if data.get("assigned_date") else None
            ),
            teacher_name=data.get("teacher_name"),
            is_done=data.get("is_done"),
            can_submit=data.get("can_submit"),
        )


@dataclass(slots=True)
class Absence:
    """A minimized absence or late-arrival record."""

    uid: str
    absence_date: date
    status: str
    absence_type: str
    minutes: int | None = None
    subject_name: str | None = None
    teacher_name: str | None = None
    lesson_index: int | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping."""
        data = asdict(self)
        data["absence_date"] = self.absence_date.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Absence:
        """Restore a normalized absence from cache."""
        return cls(
            uid=str(data.get("uid") or ""),
            absence_date=date.fromisoformat(data["absence_date"]),
            status=str(data.get("status") or "pending"),
            absence_type=str(data.get("absence_type") or "absence"),
            minutes=data.get("minutes"),
            subject_name=data.get("subject_name"),
            teacher_name=data.get("teacher_name"),
            lesson_index=data.get("lesson_index"),
        )


@dataclass(slots=True)
class MessageSummary:
    """A read-only message-list record without body or attachments."""

    uid: str
    received_at: datetime
    sender: str | None
    subject: str | None
    is_read: bool

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping."""
        return {
            "uid": self.uid,
            "received_at": self.received_at.isoformat(),
            "sender": self.sender,
            "subject": self.subject,
            "is_read": self.is_read,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MessageSummary:
        """Restore message metadata from cache."""
        return cls(
            uid=str(data.get("uid") or ""),
            received_at=datetime.fromisoformat(data["received_at"]),
            sender=data.get("sender"),
            subject=data.get("subject"),
            is_read=bool(data.get("is_read")),
        )


@dataclass(slots=True)
class SchoolYearMilestone:
    """A single school-year calendar entry."""

    event_date: date
    day_type: str | None
    description: str | None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping."""
        return {
            "event_date": self.event_date.isoformat(),
            "day_type": self.day_type,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SchoolYearMilestone:
        """Restore a school-year milestone from cache."""
        return cls(
            event_date=date.fromisoformat(data["event_date"]),
            day_type=data.get("day_type"),
            description=data.get("description"),
        )


@dataclass(slots=True)
class MergedCalendarEvent:
    """A normalized lesson or exam-only calendar event."""

    uid: str
    start: datetime
    end: datetime
    summary: str
    description: str | None
    location: str | None
    lesson_index: int | None
    subject_name: str | None
    exam: AnnouncedTest | None
    source: str
    teacher_name: str | None = None
    substitute_teacher_name: str | None = None
    topic: str | None = None
    lesson_type: str | None = None
    state: str | None = None
    annual_index: int | None = None
    is_cancelled: bool = False
    is_substitution: bool = False
    is_digital: bool = False

    def as_calendar_event(self) -> CalendarEvent:
        """Convert to a Home Assistant calendar event."""
        suffix = " ⚠️" if self.exam else ""
        return CalendarEvent(
            start=self.start,
            end=self.end,
            summary=f"{self.summary}{suffix}",
            description=self.description,
            location=self.location,
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping."""
        return {
            "uid": self.uid,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "summary": self.summary,
            "description": self.description,
            "location": self.location,
            "lesson_index": self.lesson_index,
            "subject_name": self.subject_name,
            "exam": self.exam.as_dict() if self.exam else None,
            "source": self.source,
            "teacher_name": self.teacher_name,
            "substitute_teacher_name": self.substitute_teacher_name,
            "topic": self.topic,
            "lesson_type": self.lesson_type,
            "state": self.state,
            "annual_index": self.annual_index,
            "is_cancelled": self.is_cancelled,
            "is_substitution": self.is_substitution,
            "is_digital": self.is_digital,
        }

    def as_compact_dict(self) -> dict[str, Any]:
        """Return a compact mapping for small consumers."""
        return {
            "start": self.start.strftime("%H:%M"),
            "end": self.end.strftime("%H:%M"),
            "summary": self.summary,
            "idx": self.lesson_index,
            "exam": self.exam is not None,
            "cancelled": self.is_cancelled,
            "substitution": self.is_substitution,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MergedCalendarEvent:
        """Restore a normalized event from cache."""
        exam = data.get("exam")
        return cls(
            uid=str(data.get("uid") or ""),
            start=datetime.fromisoformat(data["start"]),
            end=datetime.fromisoformat(data["end"]),
            summary=str(data.get("summary") or ""),
            description=data.get("description"),
            location=data.get("location"),
            lesson_index=data.get("lesson_index"),
            subject_name=data.get("subject_name"),
            exam=AnnouncedTest.from_dict(exam) if isinstance(exam, dict) else None,
            source=str(data.get("source") or "lesson"),
            teacher_name=data.get("teacher_name"),
            substitute_teacher_name=data.get("substitute_teacher_name"),
            topic=data.get("topic"),
            lesson_type=data.get("lesson_type"),
            state=data.get("state"),
            annual_index=data.get("annual_index"),
            is_cancelled=bool(data.get("is_cancelled")),
            is_substitution=bool(data.get("is_substitution")),
            is_digital=bool(data.get("is_digital")),
        )


@dataclass(slots=True)
class TimetableChange:
    """A reliable change between observations of the same lesson UID."""

    change_type: str
    lesson_uid: str
    subject_name: str | None
    lesson_index: int | None
    start: datetime
    old_value: str | None = None
    new_value: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping."""
        data = asdict(self)
        data["start"] = self.start.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TimetableChange:
        """Restore a normalized timetable change from cache."""
        return cls(
            change_type=str(data["change_type"]),
            lesson_uid=str(data["lesson_uid"]),
            subject_name=data.get("subject_name"),
            lesson_index=data.get("lesson_index"),
            start=datetime.fromisoformat(data["start"]),
            old_value=data.get("old_value"),
            new_value=data.get("new_value"),
        )
