"""Async client for the Kreta API."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from aiohttp import ClientError, ClientResponse, ClientSession
from homeassistant.util import dt as dt_util

from ..const import DEFAULT_TIMEOUT_SECONDS
from .diagnostics import AuthDiagnosticsTrace
from .endpoints import MESSAGES_URL, TOKEN_URL, api_url
from .exceptions import (
    ApiResponseError,
    CannotConnectError,
    InvalidAuthError,
    KretaApiError,
    KretaRateLimitError,
    KretaSecurityError,
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
from .oauth import OAUTH_CLIENT_ID, OAUTH_REDIRECT_URI, account_key_from_id_token
from .storage import TokenStore

_LOGGER = logging.getLogger(__name__)
KRETA_TIMEZONE = ZoneInfo("Europe/Budapest")
_MAX_RESPONSE_BYTES = 2_000_000


def _endpoint_label(url: str) -> str:
    """Return only the hostname and path of a validated endpoint."""
    parsed = urlsplit(url)
    return f"{parsed.hostname or 'unknown'}{parsed.path or '/'}"


def _response_endpoint(response: ClientResponse, fallback_url: str) -> str:
    """Return a query-free endpoint label for a response."""
    response_url = getattr(response, "url", None)
    return _endpoint_label(str(response_url) if response_url else fallback_url)


class KretaApiClient:
    """Kreta API client with refresh-token persistence."""

    def __init__(
        self,
        *,
        session: ClientSession,
        klik_id: str,
        token_store: TokenStore,
    ) -> None:
        """Initialize the API client."""
        self._session = session
        self._klik_id = normalize_institution(klik_id)
        self._token_store = token_store
        self._access_token: str | None = None
        self._auth_lock = asyncio.Lock()

    @property
    def _api_base_url(self) -> str:
        """Return the Kreta API base URL for this institute."""
        return api_url(self._klik_id, "Sajat").removesuffix("/Sajat")

    async def async_authenticate(self) -> None:
        """Authenticate using only a stored refresh token."""
        async with self._auth_lock:
            if self._access_token:
                return
            refresh_token = await self._token_store.async_get_refresh_token()
            if not refresh_token:
                raise InvalidAuthError("KRÉTA reauthentication is required")
            await self._async_exchange_refresh_token(refresh_token)

    @staticmethod
    def _log_auth_stage_failure(stage: str) -> None:
        """Log a privacy-safe authentication stage marker."""
        _LOGGER.warning("KRÉTA auth stage failed: %s", stage)

    async def async_get_student_profile(self) -> StudentProfile:
        """Fetch and immediately minimize the pupil profile."""
        payload = await self._async_get_json("Sajat/TanuloAdatlap")
        if not isinstance(payload, dict):
            raise ApiResponseError("Student profile response has an invalid shape")
        profile = StudentProfile(
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
        endpoint = _response_endpoint(response, MESSAGES_URL)
        try:
            payload = await response.json()
        except (ClientError, ValueError) as err:
            raise ApiResponseError(
                "Message response is not valid JSON",
                method="GET",
                endpoint=endpoint,
                status=response.status,
                safe_description="invalid_json_response",
            ) from err
        if not isinstance(payload, list) or len(payload) > 2000:
            raise ApiResponseError(
                "Message response has an invalid shape or size",
                method="GET",
                endpoint=endpoint,
                status=response.status,
                safe_description="invalid_response_shape_or_size",
            )
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
        url = f"{self._api_base_url}/{path}"
        response = await self._async_request("get", url, params=params)
        endpoint = _response_endpoint(response, url)
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > _MAX_RESPONSE_BYTES:
            response.release()
            raise ApiResponseError(
                "KRÉTA response exceeded the size limit",
                method="GET",
                endpoint=endpoint,
                status=response.status,
                safe_description="response_size_limit_exceeded",
            )
        try:
            payload = await response.json()
        except (ClientError, ValueError) as err:
            raise ApiResponseError(
                f"Invalid JSON received from {path}",
                method="GET",
                endpoint=endpoint,
                status=response.status,
                safe_description="invalid_json_response",
            ) from err
        if isinstance(payload, list) and len(payload) > 5000:
            raise ApiResponseError(
                "KRÉTA response contained too many records",
                method="GET",
                endpoint=endpoint,
                status=response.status,
                safe_description="response_record_limit_exceeded",
            )
        if not isinstance(payload, (dict, list)):
            raise ApiResponseError(
                "KRÉTA response has an invalid shape",
                method="GET",
                endpoint=endpoint,
                status=response.status,
                safe_description="invalid_response_shape",
            )
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

        endpoint = _endpoint_label(url)
        _LOGGER.debug(
            "Starting validated KRÉTA request: method=%s endpoint=%s",
            method.upper(),
            endpoint,
        )
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
        except KretaSecurityError as err:
            err.add_http_context(
                method=method.upper(),
                endpoint=endpoint,
                safe_description="network_policy_rejected_request",
            )
            raise
        except ClientError as err:
            raise CannotConnectError(
                "Could not reach a KRÉTA endpoint",
                method=method.upper(),
                endpoint=endpoint,
                safe_description="network_connection_failed",
            ) from err

        response_endpoint = _response_endpoint(response, url)
        _LOGGER.debug(
            "KRÉTA request completed: method=%s endpoint=%s status=%d",
            method.upper(),
            response_endpoint,
            response.status,
        )
        if response.status == 401:
            response.release()
            if retry_on_auth_error:
                self._access_token = None
                await self.async_authenticate()
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
            raise InvalidAuthError(
                "KRÉTA rejected the authenticated request",
                method=method.upper(),
                endpoint=response_endpoint,
                status=response.status,
                safe_description="authenticated_request_rejected",
            )

        if response.status == 429:
            retry_after = response.headers.get("Retry-After", "")
            response.release()
            raise KretaRateLimitError(
                f"KRÉTA rate limit reached; retry after {retry_after or 'later'}",
                method=method.upper(),
                endpoint=response_endpoint,
                status=response.status,
                safe_description="rate_limited",
            )

        if response.status >= 400:
            response.release()
            raise KretaApiError(
                f"KRÉTA request failed with HTTP {response.status}",
                method=method.upper(),
                endpoint=response_endpoint,
                status=response.status,
                safe_description="http_error_response",
            )
        return response

    async def _async_exchange_refresh_token(self, refresh_token: str) -> None:
        """Refresh the access token from a stored refresh token."""
        trace = AuthDiagnosticsTrace()
        request_data = {
            "refresh_token": refresh_token,
            "institute_code": self._klik_id,
            "client_id": OAUTH_CLIENT_ID,
            "grant_type": "refresh_token",
        }
        try:
            response = await self._safe_session_request("post", TOKEN_URL, data=request_data)
        except KretaSecurityError as err:
            err.add_http_context(
                method="POST",
                endpoint=_endpoint_label(TOKEN_URL),
                safe_description="network_policy_rejected_request",
            )
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
            raise CannotConnectError(
                "Could not refresh the Kreta access token",
                method="POST",
                endpoint=_endpoint_label(TOKEN_URL),
                safe_description="network_connection_failed",
            ) from err

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
            await self._token_store.async_set_refresh_token(None)
            raise InvalidAuthError(
                "Stored refresh token is no longer valid",
                method="POST",
                endpoint=_response_endpoint(response, TOKEN_URL),
                status=response.status,
                safe_description="refresh_token_rejected",
            )
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
                f"Refresh-token exchange failed with HTTP {response.status}",
                method="POST",
                endpoint=_response_endpoint(response, TOKEN_URL),
                status=response.status,
                safe_description="token_endpoint_http_error",
            )

        try:
            payload = await response.json()
        except (ClientError, ValueError) as err:
            self._log_auth_stage_failure("token_exchange")
            raise InvalidAuthError(
                "Refresh-token endpoint returned invalid JSON",
                method="POST",
                endpoint=_response_endpoint(response, TOKEN_URL),
                status=response.status,
                safe_description="token_endpoint_invalid_json",
            ) from err
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
            raise InvalidAuthError(
                "Refresh-token exchange did not return an access token",
                method="POST",
                endpoint=_response_endpoint(response, TOKEN_URL),
                status=response.status,
                safe_description="token_endpoint_missing_access_token",
            )
        self._access_token = payload["access_token"]
        new_refresh = payload.get("refresh_token")
        if new_refresh is not None:
            await self._token_store.async_set_refresh_token(new_refresh)

    async def async_exchange_authorization_code(self, code: str, code_verifier: str) -> str:
        """Exchange a transient authorization code and return an account key."""
        trace = AuthDiagnosticsTrace()
        request_data: dict[str, Any] = {
            "code": code,
            "code_verifier": code_verifier,
            "redirect_uri": OAUTH_REDIRECT_URI,
            "client_id": OAUTH_CLIENT_ID,
            "grant_type": "authorization_code",
        }
        try:
            token_response = await self._safe_session_request(
                "post", TOKEN_URL, data=request_data, follow_redirects=False
            )
            if token_response.status >= 400:
                token_body = await token_response.text()
                trace.record_exchange(
                    label="POST token (auth code)",
                    method="POST",
                    url=TOKEN_URL,
                    request_data=request_data,
                    response_status=token_response.status,
                    response_body=token_body,
                )
                trace.log_failure(_LOGGER, "authentication")
                self._log_auth_stage_failure("token_exchange")
                raise InvalidAuthError(
                    f"Authorization-code exchange failed with {token_response.status}",
                    method="POST",
                    endpoint=_response_endpoint(token_response, TOKEN_URL),
                    status=token_response.status,
                    safe_description="authorization_code_rejected",
                )
            trace.record_exchange(
                label="POST token (auth code)",
                method="POST",
                url=TOKEN_URL,
                request_data=request_data,
                response_status=token_response.status,
            )
        except KretaSecurityError as err:
            err.add_http_context(
                method="POST",
                endpoint=_endpoint_label(TOKEN_URL),
                safe_description="network_policy_rejected_request",
            )
            self._log_auth_stage_failure("token_exchange")
            raise
        except ClientError as err:
            trace.record_exchange(
                label="Network error",
                method="?",
                url="?",
                network_error=str(err),
            )
            trace.log_failure(_LOGGER, "authentication")
            self._log_auth_stage_failure("token_exchange")
            raise CannotConnectError(
                "Could not reach the KRÉTA token endpoint",
                method="POST",
                endpoint=_endpoint_label(TOKEN_URL),
                safe_description="network_connection_failed",
            ) from err

        try:
            payload = await token_response.json()
        except (ClientError, ValueError) as err:
            self._log_auth_stage_failure("token_exchange")
            raise InvalidAuthError(
                "Token endpoint returned invalid JSON",
                method="POST",
                endpoint=_response_endpoint(token_response, TOKEN_URL),
                status=token_response.status,
                safe_description="token_endpoint_invalid_json",
            ) from err
        required = ("access_token", "refresh_token", "id_token")
        if any(not isinstance(payload.get(key), str) or not payload[key] for key in required):
            trace.record_exchange(
                label="POST token (auth code) — unexpected payload",
                method="POST",
                url=TOKEN_URL,
                request_data=request_data,
                response_status=token_response.status,
                response_body=json.dumps(payload),
            )
            trace.log_failure(_LOGGER, "authentication")
            self._log_auth_stage_failure("token_exchange")
            raise InvalidAuthError(
                "KRÉTA token response omitted a required token",
                method="POST",
                endpoint=_response_endpoint(token_response, TOKEN_URL),
                status=token_response.status,
                safe_description="token_endpoint_missing_required_token",
            )
        account_key = account_key_from_id_token(payload["id_token"], self._klik_id)
        self._access_token = payload["access_token"]
        await self._token_store.async_set_refresh_token(payload["refresh_token"])
        return account_key

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
