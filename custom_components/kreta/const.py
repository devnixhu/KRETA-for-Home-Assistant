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
CONF_TIMETABLE = "timetable"
CONF_GRADES = "grades"
CONF_HOMEWORK = "homework"
CONF_TESTS = "tests"
CONF_MESSAGES = "messages"
CONF_ABSENCES = "absences"
FEATURE_KEYS = (
    CONF_TIMETABLE,
    CONF_GRADES,
    CONF_HOMEWORK,
    CONF_TESTS,
    CONF_MESSAGES,
    CONF_ABSENCES,
)

DEFAULT_REFRESH_HOURS = 12
DEFAULT_REFRESH_MINUTES = 10
DEFAULT_LOOKAHEAD_WEEKS = 2

MIN_REFRESH_HOURS = 1
MAX_REFRESH_HOURS = 24
MIN_REFRESH_MINUTES = 5
MAX_REFRESH_MINUTES = 60
MIN_LOOKAHEAD_WEEKS = 1
MAX_LOOKAHEAD_WEEKS = 4

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.CALENDAR,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_tokens"
BASELINE_STORAGE_KEY = f"{DOMAIN}_baselines"

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
