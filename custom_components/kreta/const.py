"""Constants for the Kreta integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "kreta"

CONF_KLIK_ID = "klik_id"
CONF_USER_ID = "user_id"
CONF_ACCOUNT_KEY = "account_key"
CONF_OAUTH_REDIRECT_URL = "oauth_redirect_url"
CONF_REFRESH_HOURS = "refresh_hours"
CONF_REFRESH_MINUTES = "refresh_minutes"
CONF_LOOKAHEAD_WEEKS = "lookahead_weeks"
CONF_FUTURE_WEEKS = "future_weeks"
CONF_HISTORY_WEEKS = "history_weeks"
CONF_TIMETABLE = "timetable"
CONF_GRADES = "grades"
CONF_HOMEWORK = "homework"
CONF_TESTS = "tests"
CONF_MESSAGES = "messages"
CONF_ABSENCES = "absences"
CONF_SCHOOL_YEAR = "school_year"
CONF_AUTOMATION_EVENTS = "automation_events"
CONF_LESSON_EVENTS = "lesson_events"
FEATURE_KEYS = (
    CONF_TIMETABLE,
    CONF_GRADES,
    CONF_HOMEWORK,
    CONF_TESTS,
    CONF_MESSAGES,
    CONF_ABSENCES,
    CONF_SCHOOL_YEAR,
)

DEFAULT_REFRESH_HOURS = 12
DEFAULT_REFRESH_MINUTES = 10
DEFAULT_LOOKAHEAD_WEEKS = 2
DEFAULT_FUTURE_WEEKS = 8
DEFAULT_HISTORY_WEEKS = 16

MIN_REFRESH_HOURS = 1
MAX_REFRESH_HOURS = 24
MIN_REFRESH_MINUTES = 0
MAX_REFRESH_MINUTES = 1440
MIN_LOOKAHEAD_WEEKS = 1
MAX_LOOKAHEAD_WEEKS = 52
MIN_HISTORY_WEEKS = 0
MAX_HISTORY_WEEKS = 52

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.CALENDAR,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_tokens"
BASELINE_STORAGE_KEY = f"{DOMAIN}_baselines"
DATA_CACHE_STORAGE_KEY = f"{DOMAIN}_data_cache"
DATA_CACHE_STORAGE_VERSION = 1

ATTR_EVENTS = "events"
ATTR_EVENTS_JSON = "events_json"
ATTR_COMPACT_EVENTS_JSON = "compact_events_json"
ATTR_LESSONS = "lessons"
ATTR_TESTS = "tests"
ATTR_RANGE_START = "range_start"
ATTR_RANGE_END = "range_end"
ATTR_LAST_SUCCESS = "last_success"
ATTR_LAST_ERROR = "last_error"
ATTR_LAST_ERROR_TIME = "last_error_time"
ATTR_GRADES_JSON = "grades_json"
ATTR_HOMEWORK_JSON = "homework_json"
ATTR_SCHOOL_YEAR_JSON = "school_year_json"

DEFAULT_TIMEOUT_SECONDS = 30

EVENT_NEW_GRADE = f"{DOMAIN}_new_grade"
EVENT_NEW_HOMEWORK = f"{DOMAIN}_new_homework"
EVENT_NEW_MESSAGE = f"{DOMAIN}_new_message"
EVENT_NEW_ABSENCE = f"{DOMAIN}_new_absence"
EVENT_NEW_TEST = f"{DOMAIN}_new_test"
EVENT_TIMETABLE_CHANGE = f"{DOMAIN}_timetable_change"
EVENT_SUBSTITUTION = f"{DOMAIN}_substitution"
EVENT_LESSON_CANCELLED = f"{DOMAIN}_lesson_cancelled"
EVENT_ROOM_CHANGED = f"{DOMAIN}_room_changed"
EVENT_TEACHER_CHANGED = f"{DOMAIN}_teacher_changed"
EVENT_LESSON_STARTED = f"{DOMAIN}_lesson_started"
EVENT_LESSON_FINISHED = f"{DOMAIN}_lesson_finished"
EVENT_BREAK_STARTED = f"{DOMAIN}_break_started"
EVENT_SCHOOL_STARTED = f"{DOMAIN}_school_started"
EVENT_SCHOOL_FINISHED = f"{DOMAIN}_school_finished"
