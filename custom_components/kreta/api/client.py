"""Async client for the Kreta API."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from aiohttp import ClientError, ClientResponse, ClientSession
from homeassistant.util import dt as dt_util

from ..const import DEFAULT_TIMEOUT_SECONDS
from .auth import (
    extract_authorization_code,
    extract_request_verification_token,
    extract_two_factor_form,
    is_two_factor_route,
)
from .diagnostics import AuthDiagnosticsTrace
from .endpoints import LOGIN_URL, MESSAGES_URL, TOKEN_URL, api_url
from .exceptions import (
    ApiResponseError,
    CannotConnectError,
    InvalidAuthError,
    KretaApiError,
    KretaRateLimitError,
    KretaSecurityError,
    KretaTwoFactorRequired,
)
from .models import (
    Absence,
    AnnouncedTest,
    Grade,
    HomeworkItem,
    MergedCalendarEvent,
    MessageSummary,
    SchoolYearMilestone,
    StudentProfile,
)
from .network_policy import normalize_institution, validate_redirect, validate_url
from .storage import TokenStore

_LOGGER = logging.getLogger(__name__)
KRETA_TIMEZONE = ZoneInfo("Europe/Budapest")
_ERROR_BODY_MAX_LENGTH = 200
_MAX_RESPONSE_BYTES = 2_000_000


def _summarize_error_body(body: str) -> str:
    """Return a concise summary of an HTTP error response body.

    HTML pages (e.g. maintenance splash screens) are collapsed to a short
    label so they don't flood the HA UI with raw markup.  Plain-text bodies
    are kept verbatim up to _ERROR_BODY_MAX_LENGTH characters.
    """
    stripped = body.lstrip("\ufeff").lstrip()
    if stripped.lower().startswith(("<!doctype", "<html")):
        return "(HTML response)"
    if len(body) <= _ERROR_BODY_MAX_LENGTH:
        return body
    return body[:_ERROR_BODY_MAX_LENGTH] + "…"


AUTHORIZE_PATH = (
    "/Account/Login?ReturnUrl=%2Fconnect%2Fauthorize%2Fcallback%3Fprompt%3Dlogin"
    "%26nonce%3DwylCrqT4oN6PPgQn2yQB0euKei9nJeZ6_ffJ-VpSKZU%26response_type%3Dcode"
    "%26code_challenge_method%3DS256%26scope%3Dopenid%2520email%2520offline_access"
    "%2520kreta-ellenorzo-webapi.public%2520kreta-eugyintezes-webapi.public"
    "%2520kreta-fileservice-webapi.public%2520kreta-mobile-global-webapi.public"
    "%2520kreta-dkt-webapi.public%2520kreta-ier-webapi.public%26code_challenge"
    "%3DHByZRRnPGb-Ko_wTI7ibIba1HQ6lor0ws4bcgReuYSQ%26redirect_uri%3Dhttps%253A"
    "%252F%252Fmobil.e-kreta.hu%252Fellenorzo-student%252Fprod%252Foauthredirect"
    "%26client_id%3Dkreta-ellenorzo-student-mobile-ios%26state%3Dkreten_student_mobile"
    "%26suppressed_prompt%3Dlogin"
)
CALLBACK_QUERY = (
    "prompt=login&nonce=wylCrqT4oN6PPgQn2yQB0euKei9nJeZ6_ffJ-VpSKZU&response_type=code"
    "&code_challenge_method=S256&scope=openid%20email%20offline_access"
    "%20kreta-ellenorzo-webapi.public%20kreta-eugyintezes-webapi.public"
    "%20kreta-fileservice-webapi.public%20kreta-mobile-global-webapi.public"
    "%20kreta-dkt-webapi.public%20kreta-ier-webapi.public&code_challenge"
    "=HByZRRnPGb-Ko_wTI7ibIba1HQ6lor0ws4bcgReuYSQ&redirect_uri=https%3A%2F%2Fmobil.e-kreta.hu"
    "%2Fellenorzo-student%2Fprod%2Foauthredirect&client_id=kreta-ellenorzo-student-mobile-ios"
    "&state=kreten_student_mobile&suppressed_prompt=login"
)
LOGIN_RETURN_URL = (
    "/connect/authorize/callback?prompt=login&nonce=wylCrqT4oN6PPgQn2yQB0euKei9nJeZ6_ffJ-VpSKZU"
    "&response_type=code&code_challenge_method=S256&scope=openid%20email%20offline_access"
    "%20kreta-ellenorzo-webapi.public%20kreta-eugyintezes-webapi.public"
    "%20kreta-fileservice-webapi.public%20kreta-mobile-global-webapi.public"
    "%20kreta-dkt-webapi.public%20kreta-ier-webapi.public&code_challenge"
    "=HByZRRnPGb-Ko_wTI7ibIba1HQ6lor0ws4bcgReuYSQ&redirect_uri=https%3A%2F%2Fmobil.e-kreta.hu"
    "%2Fellenorzo-student%2Fprod%2Foauthredirect&client_id=kreta-ellenorzo-student-mobile-ios"
    "&state=kreten_student_mobile&suppressed_prompt=login"
)
AUTHORIZE_URL = f"https://idp.e-kreta.hu{AUTHORIZE_PATH}"
CALLBACK_URL = f"https://idp.e-kreta.hu/connect/authorize/callback?{CALLBACK_QUERY}"
CLIENT_ID = "kreta-ellenorzo-student-mobile-ios"
CODE_VERIFIER = "DSpuqj_HhDX4wzQIbtn8lr8NLE5wEi1iVLMtMK0jY6c"


class KretaApiClient:
    """Kreta API client with refresh-token persistence."""

    def __init__(
        self,
        *,
        session: ClientSession,
        klik_id: str,
        user_id: str,
        password: str | None,
        token_store: TokenStore,
    ) -> None:
        """Initialize the API client."""
        self._session = session
        self._klik_id = normalize_institution(klik_id)
        self._user_id = user_id
        # The password exists only while an interactive login is in progress.
        # It is discarded immediately after successful authentication.
        self._password = password
        self._token_store = token_store
        self._access_token: str | None = None
        self._auth_lock = asyncio.Lock()
        self._two_factor_action: str | None = None
        self._two_factor_fields: dict[str, str] | None = None
        self._two_factor_code_field: str | None = None

    @property
    def _api_base_url(self) -> str:
        """Return the Kreta API base URL for this institute."""
        return api_url(self._klik_id, "Sajat").removesuffix("/Sajat")

    async def async_authenticate(self, force_login: bool = False) -> None:
        """Authenticate using refresh token first, then interactive login if needed."""
        async with self._auth_lock:
            if self._access_token and not force_login:
                return

            refresh_token = await self._token_store.async_get_refresh_token()
            if refresh_token and not force_login:
                _LOGGER.info("Authenticating with Kreta using stored refresh token")
                try:
                    await self._async_exchange_refresh_token(refresh_token)
                    _LOGGER.info("Kreta authentication successful (refresh token)")
                    return
                except InvalidAuthError:
                    _LOGGER.warning("Stored refresh token was rejected")
            elif not force_login:
                _LOGGER.info("No stored refresh token; full login is required")

            if not self._password:
                raise InvalidAuthError("KRÉTA reauthentication is required")
            _LOGGER.info("Performing full KRÉTA login")
            await self._async_login()
            self.discard_password()
            _LOGGER.info("KRÉTA authentication successful")

    def discard_password(self) -> None:
        """Remove the password from memory after an initial login."""
        self._password = None

    async def async_submit_two_factor(self, code: str) -> None:
        """Continue an in-memory login challenge with a one-time 2FA code."""
        if not re.fullmatch(r"[A-Za-z0-9-]{4,32}", code.strip()):
            raise InvalidAuthError("Invalid two-factor code format")
        if not all((self._two_factor_action, self._two_factor_fields, self._two_factor_code_field)):
            raise InvalidAuthError("No active two-factor challenge")
        form = dict(self._two_factor_fields or {})
        form[self._two_factor_code_field or "TwoFactorCode"] = code.strip()
        form["RememberMachine"] = "false"
        try:
            response = await self._safe_session_request(
                "post",
                self._two_factor_action or "",
                data=form,
                follow_redirects=False,
            )
        except KretaSecurityError:
            self._log_auth_stage_failure("two_factor_submit")
            raise
        except ClientError as err:
            self._log_auth_stage_failure("two_factor_submit")
            raise CannotConnectError("Could not submit the KRÉTA 2FA challenge") from err

        body = await response.text()
        if response.status == 200 and extract_two_factor_form(body) is not None:
            self._log_auth_stage_failure("two_factor_submit")
            raise InvalidAuthError("The two-factor code was rejected")
        if response.status >= 400:
            self._log_auth_stage_failure("two_factor_submit")
            raise InvalidAuthError(
                f"Two-factor form submission failed with {response.status}"
            )
        if response.status not in {302, 303}:
            self._log_auth_stage_failure("two_factor_submit")
            raise InvalidAuthError(
                f"Unexpected two-factor response status {response.status}"
            )
        if response.headers.get("Location") is None:
            self._log_auth_stage_failure("two_factor_submit")
            raise InvalidAuthError("Two-factor response omitted its redirect URL")

        self._two_factor_action = None
        self._two_factor_fields = None
        self._two_factor_code_field = None
        await self._async_finish_login()
        self.discard_password()

    @staticmethod
    def _log_auth_stage_failure(stage: str) -> None:
        """Log a privacy-safe authentication stage marker."""
        _LOGGER.warning("KRÉTA auth stage failed: %s", stage)

    def _remember_two_factor_form(self, page_url: str, html: str) -> None:
        """Validate and retain a parsed 2FA form only for this login attempt."""
        two_factor = extract_two_factor_form(html)
        if two_factor is None:
            self._log_auth_stage_failure("two_factor_page")
            raise InvalidAuthError("KRÉTA two-factor page did not contain a 2FA form")
        action, fields, code_field = two_factor
        if not fields.get("__RequestVerificationToken"):
            self._log_auth_stage_failure("two_factor_page")
            raise InvalidAuthError("KRÉTA two-factor form omitted its CSRF token")
        self._two_factor_action = validate_redirect(
            page_url, action or page_url, self._klik_id
        )
        self._two_factor_fields = fields
        self._two_factor_code_field = code_field

    async def _async_load_two_factor_page(
        self, page_url: str, trace: AuthDiagnosticsTrace
    ) -> None:
        """GET and parse a validated KRÉTA two-factor page."""
        try:
            response = await self._safe_session_request(
                "get", page_url, follow_redirects=False
            )
        except (ClientError, KretaSecurityError):
            self._log_auth_stage_failure("two_factor_page")
            raise
        body = await response.text()
        trace.record_exchange(
            label="GET two-factor page",
            method="GET",
            url=page_url,
            response_status=response.status,
            response_body=body if response.status >= 400 else None,
        )
        if response.status != 200:
            self._log_auth_stage_failure("two_factor_page")
            raise InvalidAuthError(
                f"KRÉTA two-factor page returned {response.status}"
            )
        self._remember_two_factor_form(page_url, body)
        raise KretaTwoFactorRequired("A KRÉTA 2FA code is required")

    async def async_reauthenticate(self) -> None:
        """Reauthenticate explicitly after an auth failure.

        Clears the stale access token and re-runs the normal auth flow so the
        stored refresh token is tried before falling back to a full login.
        """
        async with self._auth_lock:
            self._access_token = None
        await self.async_authenticate()

    async def async_get_student_profile(self) -> StudentProfile:
        """Fetch and immediately minimize the pupil profile."""
        payload = await self._async_get_json("Sajat/TanuloAdatlap")
        if not isinstance(payload, dict):
            raise ApiResponseError("Student profile response has an invalid shape")
        profile = StudentProfile(
            # The response contains extensive personal data; retain only the
            # institution display name needed for setup UX.
            student_name=None,
            school_name=(payload.get("Intezmeny") or {}).get("TeljesNev")
            or payload.get("IntezmenyNev"),
        )
        return profile

    @classmethod
    def _pick_current_enrollment(cls, enrollments: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Return the enrollment with the latest start date, if any."""
        dated_enrollments = []
        for enrollment in enrollments:
            start_date = enrollment.get("Kezdete")
            if not start_date:
                continue
            try:
                parsed = cls._parse_local_date(start_date)
            except ValueError:
                continue
            dated_enrollments.append((parsed, enrollment))

        if dated_enrollments:
            return max(dated_enrollments, key=lambda item: item[0])[1]
        return enrollments[0] if enrollments else None

    async def async_get_lessons(
        self, start_date: date, end_date: date
    ) -> list[MergedCalendarEvent]:
        """Fetch timetable entries and normalize them to lesson events."""
        _LOGGER.info("Fetching lessons %s → %s", start_date, end_date)
        payload = await self._async_get_json(
            "Sajat/OrarendElemek",
            params={"datumTol": start_date.isoformat(), "datumIg": end_date.isoformat()},
        )
        lessons: list[MergedCalendarEvent] = []
        for item in payload:
            lesson_type = item.get("Tipus", {}).get("Nev")
            if lesson_type not in {"TanitasiOra", "OrarendiOra"}:
                continue
            start_raw = item.get("KezdetIdopont")
            end_raw = item.get("VegIdopont")
            if start_raw is None or end_raw is None:
                _LOGGER.warning("Skipping a lesson with missing time fields")
                continue
            start = self._parse_datetime(start_raw)
            end = self._parse_datetime(end_raw)
            subject = item.get("Nev") or item.get("Tantargy", {}).get("Nev") or "Ora"
            room = item.get("TeremNeve")
            lesson_index = item.get("Oraszam")
            description = "\n".join(
                part
                for part in (
                    f"Tantargy: {subject}",
                    f"Terem: {room}" if room else None,
                    f"Oraszam: {lesson_index}" if lesson_index is not None else None,
                )
                if part
            )
            lessons.append(
                MergedCalendarEvent(
                    uid=f"lesson-{start.isoformat()}-{lesson_index or 0}-{subject.casefold()}",
                    start=start,
                    end=end,
                    summary=subject,
                    description=description,
                    location=room,
                    lesson_index=lesson_index,
                    subject_name=subject,
                    exam=None,
                    source="lesson",
                )
            )
        lessons.sort(key=lambda lesson: (lesson.start, lesson.lesson_index or 0, lesson.uid))
        _LOGGER.info("Lessons fetched: %d entries", len(lessons))
        return lessons

    async def async_get_announced_tests(
        self, start_date: date, end_date: date
    ) -> list[AnnouncedTest]:
        """Fetch announced tests, splitting into month-sized chunks when needed."""
        _LOGGER.info("Fetching announced tests %s → %s", start_date, end_date)
        tests: list[AnnouncedTest] = []
        chunk_start = start_date
        while chunk_start <= end_date:
            month_later = (chunk_start.replace(day=1) + timedelta(days=32)).replace(day=1)
            chunk_end = min(month_later - timedelta(days=1), end_date)
            payload = await self._async_get_json(
                "Sajat/BejelentettSzamonkeresek",
                params={
                    "datumTol": chunk_start.isoformat(),
                    "datumIg": chunk_end.isoformat(),
                },
            )
            for item in payload:
                datum = item.get("Datum")
                if datum is None:
                    _LOGGER.warning("Skipping an announced test with a missing date")
                    continue
                announced_date = item.get("BejelentesDatuma")
                tests.append(
                    AnnouncedTest(
                        test_date=self._parse_local_date(datum),
                        announced_date=(
                            self._parse_local_date(announced_date) if announced_date else None
                        ),
                        subject_name=item.get("TantargyNeve") or "Ismeretlen tantargy",
                        teacher_name=item.get("RogzitoTanarNeve"),
                        lesson_index=item.get("OrarendiOraOraszama"),
                        theme=item.get("Temaja"),
                        mode=item.get("Modja", {}).get("Leiras"),
                    )
                )
            _LOGGER.debug(
                "Fetched %d announced tests for chunk %s → %s",
                len(payload),
                chunk_start,
                chunk_end,
            )
            chunk_start = chunk_end + timedelta(days=1)
        tests.sort(key=lambda item: (item.test_date, item.lesson_index or 0, item.subject_name))
        _LOGGER.info("Announced tests fetched: %d total", len(tests))
        return tests

    async def async_get_grades(self, start_date: date, end_date: date) -> list[Grade]:
        """Fetch grades recorded within the given date range."""
        _LOGGER.info("Fetching grades %s → %s", start_date, end_date)
        payload = await self._async_get_json(
            "Sajat/Ertekelesek",
            params={"datumTol": start_date.isoformat(), "datumIg": end_date.isoformat()},
        )
        grades: list[Grade] = []
        for item in payload:
            recorded = item.get("RogzitesDatuma")
            if recorded is None:
                _LOGGER.warning("Skipping a grade with a missing date")
                continue
            grades.append(
                Grade(
                    grade_date=self._parse_local_date(recorded),
                    subject_name=item.get("Tantargy", {}).get("Nev") or "Ismeretlen tantargy",
                    grade_type=item.get("Tipus", {}).get("Leiras"),
                    value=item.get("SzovegesErtek"),
                    topic=item.get("Tema"),
                    uid=str(item.get("Uid") or ""),
                )
            )
        grades.sort(key=lambda grade: (grade.grade_date, grade.subject_name))
        _LOGGER.info("Grades fetched: %d entries", len(grades))
        return grades

    async def async_get_homework(self, start_date: date, end_date: date) -> list[HomeworkItem]:
        """Fetch homework due within the given date range."""
        _LOGGER.info("Fetching homework %s → %s", start_date, end_date)
        payload = await self._async_get_json(
            "Sajat/HaziFeladatok",
            params={"datumTol": start_date.isoformat(), "datumIg": end_date.isoformat()},
        )
        homework: list[HomeworkItem] = []
        for item in payload:
            deadline = item.get("HataridoDatuma")
            if deadline is None:
                _LOGGER.warning("Skipping homework with a missing deadline")
                continue
            assigned = item.get("RogzitesIdopontja")
            homework.append(
                HomeworkItem(
                    subject_name=item.get("TantargyNeve") or "Ismeretlen tantargy",
                    description=item.get("Szoveg"),
                    due_date=self._parse_local_date(deadline),
                    assigned_date=self._parse_local_date(assigned) if assigned else None,
                    uid=str(item.get("Uid") or ""),
                )
            )
        homework.sort(key=lambda item: (item.due_date, item.subject_name))
        _LOGGER.info("Homework fetched: %d entries", len(homework))
        return homework

    async def async_get_school_year_calendar(self) -> list[SchoolYearMilestone]:
        """Fetch the whole school-year calendar (no date range; one call per year)."""
        _LOGGER.info("Fetching school-year calendar")
        payload = await self._async_get_json("Sajat/Intezmenyek/TanevRendjeElemek")
        milestones: list[SchoolYearMilestone] = []
        for item in payload:
            event_date = item.get("Datum")
            if event_date is None:
                _LOGGER.warning("Skipping a school-year item with a missing date")
                continue
            naptipus = item.get("Naptipus", {})
            milestones.append(
                SchoolYearMilestone(
                    event_date=self._parse_local_date(event_date),
                    day_type=naptipus.get("Nev"),
                    description=naptipus.get("Leiras"),
                )
            )
        milestones.sort(key=lambda milestone: milestone.event_date)
        _LOGGER.info("School-year calendar fetched: %d entries", len(milestones))
        return milestones

    async def async_get_absences(self, start_date: date, end_date: date) -> list[Absence]:
        """Fetch and minimize absence records."""
        payload = await self._async_get_json(
            "Sajat/Mulasztasok",
            params={"datumTol": start_date.isoformat(), "datumIg": end_date.isoformat()},
        )
        if not isinstance(payload, list) or len(payload) > 5000:
            raise ApiResponseError("Absence response has an invalid shape or size")
        result: list[Absence] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            raw_date = item.get("Datum") or item.get("KezdetDatum")
            if not isinstance(raw_date, str):
                continue
            result.append(
                Absence(
                    uid=str(item.get("Uid") or ""),
                    absence_date=self._parse_local_date(raw_date),
                    status=str((item.get("IgazolasAllapota") or {}).get("Nev") or "pending"),
                    absence_type=str((item.get("Tipus") or {}).get("Nev") or "absence"),
                    minutes=(
                        item.get("KesesPercben")
                        if isinstance(item.get("KesesPercben"), int)
                        else None
                    ),
                )
            )
        return result

    async def async_get_messages(self) -> list[MessageSummary]:
        """Fetch read-only inbox metadata; message bodies are never requested."""
        response = await self._async_request("get", MESSAGES_URL, include_messages=True)
        try:
            payload = await response.json()
        except (ClientError, ValueError) as err:
            raise ApiResponseError("Message response is not valid JSON") from err
        if not isinstance(payload, list) or len(payload) > 2000:
            raise ApiResponseError("Message response has an invalid shape or size")
        messages: list[MessageSummary] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            raw_date = item.get("uzenetKuldesDatum")
            if not isinstance(raw_date, str):
                continue
            messages.append(
                MessageSummary(
                    uid=str(item.get("azonosito") or item.get("uzenetAzonosito") or ""),
                    received_at=self._parse_datetime(raw_date),
                    sender=(
                        str(item.get("uzenetFeladoNev"))[:100]
                        if item.get("uzenetFeladoNev")
                        else None
                    ),
                    subject=(
                        str(item.get("uzenetTargy"))[:160] if item.get("uzenetTargy") else None
                    ),
                    is_read=bool(item.get("isElolvasva")),
                )
            )
        messages.sort(key=lambda item: item.received_at, reverse=True)
        return messages

    async def _async_get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Issue an authenticated GET request and return JSON."""
        response = await self._async_request("get", f"{self._api_base_url}/{path}", params=params)
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > _MAX_RESPONSE_BYTES:
            response.release()
            raise ApiResponseError("KRÉTA response exceeded the size limit")
        try:
            payload = await response.json()
        except (ClientError, ValueError) as err:
            raise ApiResponseError(f"Invalid JSON received from {path}") from err
        if isinstance(payload, list) and len(payload) > 5000:
            raise ApiResponseError("KRÉTA response contained too many records")
        if not isinstance(payload, (dict, list)):
            raise ApiResponseError("KRÉTA response has an invalid shape")
        return payload

    async def _async_request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        allow_redirects: bool = True,
        retry_on_auth_error: bool = True,
        require_auth: bool = True,
        include_messages: bool = False,
    ) -> ClientResponse:
        """Make an HTTP request with auth handling."""
        if require_auth:
            await self.async_authenticate()
        request_headers = dict(headers or {})
        if require_auth and self._access_token is not None:
            request_headers["Authorization"] = f"Bearer {self._access_token}"

        _LOGGER.debug("Starting validated KRÉTA %s request", method.upper())
        try:
            response = await self._safe_session_request(
                method,
                url,
                params=params,
                data=data,
                headers=request_headers,
                follow_redirects=allow_redirects,
                include_messages=include_messages,
            )
        except ClientError as err:
            raise CannotConnectError("Could not reach a KRÉTA endpoint") from err

        _LOGGER.debug("KRÉTA request completed with HTTP %d", response.status)
        if response.status in {401, 403}:
            response.release()
            if retry_on_auth_error:
                await self.async_reauthenticate()
                return await self._async_request(
                    method,
                    url,
                    params=params,
                    data=data,
                    headers=headers,
                    allow_redirects=allow_redirects,
                    retry_on_auth_error=False,
                    require_auth=require_auth,
                    include_messages=include_messages,
                )
            raise InvalidAuthError("KRÉTA rejected the authenticated request")

        if response.status == 429:
            retry_after = response.headers.get("Retry-After", "")
            response.release()
            raise KretaRateLimitError(
                f"KRÉTA rate limit reached; retry after {retry_after or 'later'}"
            )

        if response.status >= 400:
            body = await response.text()
            raise KretaApiError(
                f"KRÉTA request failed with HTTP {response.status}: {_summarize_error_body(body)}"
            )
        return response

    async def _async_exchange_refresh_token(self, refresh_token: str) -> None:
        """Refresh the access token from a stored refresh token."""
        trace = AuthDiagnosticsTrace()
        request_data = {
            "refresh_token": refresh_token,
            "institute_code": self._klik_id,
            "client_id": CLIENT_ID,
            "grant_type": "refresh_token",
        }
        try:
            response = await self._safe_session_request("post", TOKEN_URL, data=request_data)
        except KretaSecurityError:
            self._log_auth_stage_failure("token_exchange")
            raise
        except ClientError as err:
            trace.record_exchange(
                label="POST token (refresh)",
                method="POST",
                url=TOKEN_URL,
                request_data=request_data,
                network_error=str(err),
            )
            trace.log_failure(_LOGGER, "authentication")
            self._log_auth_stage_failure("token_exchange")
            raise CannotConnectError("Could not refresh the Kreta access token") from err

        if response.status in {400, 401, 403}:
            body = await response.text()
            trace.record_exchange(
                label="POST token (refresh)",
                method="POST",
                url=TOKEN_URL,
                request_data=request_data,
                response_status=response.status,
                response_body=body,
            )
            trace.log_failure(_LOGGER, "authentication")
            self._log_auth_stage_failure("token_exchange")
            # The server has explicitly rejected this refresh token — remove it from
            # persistent storage so it is not retried on the next auth cycle.
            await self._token_store.async_set_refresh_token(None)
            raise InvalidAuthError("Stored refresh token is no longer valid")
        if response.status >= 400:
            body = await response.text()
            trace.record_exchange(
                label="POST token (refresh)",
                method="POST",
                url=TOKEN_URL,
                request_data=request_data,
                response_status=response.status,
                response_body=body,
            )
            trace.log_failure(_LOGGER, "authentication")
            self._log_auth_stage_failure("token_exchange")
            raise KretaApiError(
                f"Refresh-token exchange failed ({response.status}): {_summarize_error_body(body)}"
            )

        try:
            payload = await response.json()
        except (ClientError, ValueError) as err:
            self._log_auth_stage_failure("token_exchange")
            raise InvalidAuthError("Refresh-token endpoint returned invalid JSON") from err
        if "access_token" not in payload:
            trace.record_exchange(
                label="POST token (refresh) — unexpected payload",
                method="POST",
                url=TOKEN_URL,
                request_data=request_data,
                response_status=response.status,
                response_body=json.dumps(payload),
            )
            trace.log_failure(_LOGGER, "authentication")
            self._log_auth_stage_failure("token_exchange")
            raise InvalidAuthError("Refresh-token exchange did not return an access token")
        self._access_token = payload["access_token"]
        new_refresh = payload.get("refresh_token")
        if new_refresh is not None:
            await self._token_store.async_set_refresh_token(new_refresh)

    async def _async_login(self) -> None:
        """Perform the interactive login flow to obtain a new refresh token."""
        trace = AuthDiagnosticsTrace()
        stage = "password_login"
        login_request_data: dict[str, Any] = {
            "ReturnUrl": LOGIN_RETURN_URL,
            "IsTemporaryLogin": False,
            "UserName": self._user_id,
            "Password": self._password,
            "InstituteCode": self._klik_id,
            "loginType": "InstituteLogin",
        }
        try:
            # Step 1: GET the authorize/login page to obtain the CSRF token.
            login_page = await self._safe_session_request("get", AUTHORIZE_URL)
            html = await login_page.text()
            trace.record_exchange(
                label="GET authorize page",
                method="GET",
                url=AUTHORIZE_URL,
                response_status=login_page.status,
                response_body=html if login_page.status >= 400 else None,
            )
            if login_page.status >= 400:
                trace.log_failure(_LOGGER, "authentication")
                self._log_auth_stage_failure(stage)
                raise InvalidAuthError(f"Login authorize page returned {login_page.status}")
            try:
                verification_token = extract_request_verification_token(html)
            except InvalidAuthError:
                self._log_auth_stage_failure(stage)
                raise

            # Step 2: POST the login form with credentials.
            full_login_data = {
                **login_request_data,
                "__RequestVerificationToken": verification_token,
            }
            response = await self._safe_session_request(
                "post",
                LOGIN_URL,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data=full_login_data,
                follow_redirects=False,
            )
            if response.status >= 400:
                login_body = await response.text()
                trace.record_exchange(
                    label="POST login form",
                    method="POST",
                    url=LOGIN_URL,
                    request_data=full_login_data,
                    response_status=response.status,
                    response_body=login_body,
                )
                trace.log_failure(_LOGGER, "authentication")
                self._log_auth_stage_failure(stage)
                raise InvalidAuthError(f"Login form submission failed with {response.status}")
            trace.record_exchange(
                label="POST login form",
                method="POST",
                url=LOGIN_URL,
                request_data=full_login_data,
                response_status=response.status,
            )

            login_body = await response.text()
            two_factor = extract_two_factor_form(login_body)
            if two_factor is not None:
                self._remember_two_factor_form(LOGIN_URL, login_body)
                raise KretaTwoFactorRequired("A KRÉTA 2FA code is required")

            if response.status in {302, 303}:
                location = response.headers.get("Location")
                if location is None:
                    self._log_auth_stage_failure(stage)
                    raise InvalidAuthError("Login response omitted its redirect URL")
                redirected = validate_redirect(LOGIN_URL, location, self._klik_id)
                if is_two_factor_route(redirected):
                    stage = "two_factor_page"
                    await self._async_load_two_factor_page(redirected, trace)
            elif response.status != 200:
                self._log_auth_stage_failure(stage)
                raise InvalidAuthError(
                    f"Unexpected login response status {response.status}"
                )

            await self._async_finish_login(trace)
        except KretaTwoFactorRequired:
            raise
        except KretaSecurityError:
            self._log_auth_stage_failure(stage)
            raise
        except ClientError as err:
            trace.record_exchange(
                label="Network error", method="?", url="?", network_error=str(err)
            )
            trace.log_failure(_LOGGER, "authentication")
            self._log_auth_stage_failure(stage)
            raise CannotConnectError("Could not complete KRÉTA login flow") from err

    async def _async_finish_login(self, trace: AuthDiagnosticsTrace | None = None) -> None:
        """Finish authorization after password or 2FA verification."""
        trace = trace or AuthDiagnosticsTrace()
        stage = "oauth_callback"
        try:
            callback = await self._safe_session_request("get", CALLBACK_URL, follow_redirects=False)
            location = callback.headers.get("location")
            if callback.status not in {302, 303}:
                callback_body = await callback.text()
                trace.record_exchange(
                    label="GET callback",
                    method="GET",
                    url=CALLBACK_URL,
                    response_status=callback.status,
                    response_body=callback_body,
                )
                trace.log_failure(_LOGGER, "authentication")
                self._log_auth_stage_failure(stage)
                raise InvalidAuthError(
                    f"Authorization callback did not redirect, got {callback.status}"
                )
            trace.record_exchange(
                label="GET callback",
                method="GET",
                url=CALLBACK_URL,
                response_status=callback.status,
                redirect_location=location,
            )
            if location is None:
                trace.log_failure(_LOGGER, "authentication")
                self._log_auth_stage_failure(stage)
                raise InvalidAuthError("Authorization callback did not return a redirect URL")

            try:
                code = extract_authorization_code(location)
            except InvalidAuthError:
                self._log_auth_stage_failure(stage)
                raise

            # Step 4: Exchange the auth code for tokens.
            stage = "token_exchange"
            token_request_data: dict[str, Any] = {
                "code": code,
                "code_verifier": CODE_VERIFIER,
                "redirect_uri": ("https://mobil.e-kreta.hu/ellenorzo-student/prod/oauthredirect"),
                "client_id": CLIENT_ID,
                "grant_type": "authorization_code",
            }
            token_response = await self._safe_session_request(
                "post", TOKEN_URL, data=token_request_data
            )
            if token_response.status >= 400:
                token_body = await token_response.text()
                trace.record_exchange(
                    label="POST token (auth code)",
                    method="POST",
                    url=TOKEN_URL,
                    request_data=token_request_data,
                    response_status=token_response.status,
                    response_body=token_body,
                )
                trace.log_failure(_LOGGER, "authentication")
                self._log_auth_stage_failure(stage)
                raise InvalidAuthError(
                    f"Authorization-code exchange failed with {token_response.status}"
                )
            trace.record_exchange(
                label="POST token (auth code)",
                method="POST",
                url=TOKEN_URL,
                request_data=token_request_data,
                response_status=token_response.status,
            )
        except KretaSecurityError:
            self._log_auth_stage_failure(stage)
            raise
        except ClientError as err:
            trace.record_exchange(
                label="Network error",
                method="?",
                url="?",
                network_error=str(err),
            )
            trace.log_failure(_LOGGER, "authentication")
            self._log_auth_stage_failure(stage)
            raise CannotConnectError("Could not complete KRÉTA login flow") from err

        try:
            payload = await token_response.json()
        except (ClientError, ValueError) as err:
            self._log_auth_stage_failure("token_exchange")
            raise InvalidAuthError("Token endpoint returned invalid JSON") from err
        if "access_token" not in payload:
            trace.record_exchange(
                label="POST token (auth code) — unexpected payload",
                method="POST",
                url=TOKEN_URL,
                request_data=token_request_data,
                response_status=token_response.status,
                response_body=json.dumps(payload),
            )
            trace.log_failure(_LOGGER, "authentication")
            self._log_auth_stage_failure("token_exchange")
            raise InvalidAuthError("Login response did not include an access token")
        self._access_token = payload["access_token"]
        new_refresh = payload.get("refresh_token")
        if new_refresh is not None:
            await self._token_store.async_set_refresh_token(new_refresh)
        else:
            _LOGGER.warning(
                "Full login did not return a refresh token",
            )

    async def _safe_session_request(
        self,
        method: str,
        url: str,
        *,
        follow_redirects: bool = True,
        include_messages: bool = False,
        **kwargs: Any,
    ) -> ClientResponse:
        """Perform one validated request without implicit redirects."""
        target = validate_url(url, self._klik_id, include_messages=include_messages)
        kwargs.pop("allow_redirects", None)
        response = await self._session.request(
            method,
            target,
            allow_redirects=False,
            timeout=DEFAULT_TIMEOUT_SECONDS,
            **kwargs,
        )
        if not follow_redirects:
            location = response.headers.get("Location")
            if location:
                validate_redirect(
                    target, location, self._klik_id, include_messages=include_messages
                )
            return response
        # Authentication redirects are followed explicitly and revalidated.
        for _attempt in range(4):
            if response.status not in {301, 302, 303, 307, 308}:
                return response
            location = response.headers.get("Location")
            if not location:
                raise KretaSecurityError("KRÉTA redirect omitted its destination")
            redirected = validate_redirect(
                target, location, self._klik_id, include_messages=include_messages
            )
            if kwargs.get("headers", {}).get("Authorization") and (
                urlsplit(redirected).hostname != urlsplit(target).hostname
            ):
                raise KretaSecurityError("Blocked cross-host credential redirect")
            response.release()
            target = redirected
            method = "get" if response.status in {301, 302, 303} else method
            response = await self._session.request(
                method,
                target,
                allow_redirects=False,
                timeout=DEFAULT_TIMEOUT_SECONDS,
                **({"headers": kwargs.get("headers", {})} if method == "get" else kwargs),
            )
        raise KretaSecurityError("Too many KRÉTA redirects")

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        """Parse a Kreta datetime string into a local timezone-aware datetime."""
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt_util.as_local(parsed)

    @staticmethod
    def _parse_local_date(value: str) -> date:
        """Parse a Kreta timestamp into the corresponding Hungary-local date."""
        if "T" not in value:
            return date.fromisoformat(value)
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(KRETA_TIMEZONE).date()
