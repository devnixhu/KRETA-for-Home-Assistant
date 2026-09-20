"""OAuth, security, storage and regression tests."""

from __future__ import annotations

import base64
import json
import logging
from collections import deque
from types import SimpleNamespace

import pytest
from aiohttp import web
from homeassistant import data_entry_flow
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.kreta.api.client import KretaApiClient
from custom_components.kreta.api.diagnostics import (
    sanitize_form_data,
    sanitize_redirect_url,
    sanitize_response_body,
)
from custom_components.kreta.api.endpoints import TOKEN_URL
from custom_components.kreta.api.exceptions import (
    InvalidAuthError,
    KretaApiError,
    KretaSecurityError,
    OAuthCallbackError,
    OAuthCodeMissingError,
    OAuthStateMismatchError,
)
from custom_components.kreta.api.models import OAuthTokens, StudentProfile
from custom_components.kreta.api.network_policy import (
    normalize_institution,
    validate_redirect,
    validate_url,
)
from custom_components.kreta.api.oauth import (
    OAUTH_CLIENT_ID,
    OAUTH_REDIRECT_URI,
    OAUTH_SCOPES,
    account_key_from_id_token,
    build_authorization_url,
    extract_callback_code,
)
from custom_components.kreta.api.pkce import PkceAttempt, derive_code_challenge
from custom_components.kreta.api.storage import (
    KretaBaselineStore,
    MemoryTokenStore,
    credential_key,
    entry_storage_key,
)
from custom_components.kreta.config_flow import KretaConfigFlow, _build_user_schema
from custom_components.kreta.const import (
    CONF_ACCOUNT_KEY,
    CONF_KLIK_ID,
    CONF_LOOKAHEAD_WEEKS,
    CONF_MESSAGES,
    CONF_OAUTH_REDIRECT_URL,
    CONF_REFRESH_MINUTES,
    DOMAIN,
)
from custom_components.kreta.coordinator import KretaDataUpdateCoordinator
from custom_components.kreta.oauth_start import (
    OAUTH_STARTS,
    OAUTH_VIEW_REGISTERED,
    KretaOAuthStartView,
    OAuthStart,
    ensure_oauth_start_view,
)


def _jwt(payload: dict[str, str]) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{header}.{body}.signature"


class _FakeResponse:
    def __init__(
        self,
        status: int,
        *,
        body: str = "",
        headers: dict[str, str] | None = None,
        payload: dict | None = None,
    ) -> None:
        self.status = status
        self.headers = {}
        for key, value in (headers or {}).items():
            self.headers[key] = value
            self.headers[key.lower()] = value
        self._body = body
        self._payload = payload

    async def text(self) -> str:
        return self._body

    async def json(self) -> dict:
        if self._payload is None:
            raise ValueError("No JSON payload")
        return self._payload

    def release(self) -> None:
        return None


class _FakeSession:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self.responses = deque(responses)
        self.requests: list[tuple[str, str, dict]] = []

    async def request(self, method: str, url: str, **kwargs):
        self.requests.append((method, url, kwargs))
        assert self.responses
        return self.responses.popleft()


@pytest.mark.parametrize(
    "url",
    [
        "http://idp.e-kreta.hu",
        "https://evil.example",
        "https://e-kreta.hu.evil.example",
        "https://idp.e-kreta.hu@evil.example",
        "https://localhost",
        "https://127.0.0.1",
        "file:///etc/passwd",
        "https://school01.e-kreta.hu:444/path",
        "https://school01.e-kreta.hu/path#fragment",
    ],
)
def test_network_policy_rejects_untrusted_destinations(url: str) -> None:
    with pytest.raises(KretaSecurityError):
        validate_url(url, "school01")


@pytest.mark.parametrize(
    "url",
    [
        "https://idp.e-kreta.hu/connect/token",
        OAUTH_REDIRECT_URI,
        "https://school01.e-kreta.hu/ellenorzo/v3/Sajat/Ertekelesek",
    ],
)
def test_network_policy_allows_expected_hosts(url: str) -> None:
    assert validate_url(url, "school01") == url


def test_external_redirect_is_blocked() -> None:
    with pytest.raises(KretaSecurityError):
        validate_redirect("https://idp.e-kreta.hu/start", "https://evil.example/x", "school01")


def test_institution_normalization_is_strict() -> None:
    assert normalize_institution(" SCHOOL-01 ") == "school-01"
    with pytest.raises(KretaSecurityError):
        normalize_institution("árvíz")


def test_pkce_attempt_uses_independent_secure_values() -> None:
    first = PkceAttempt.create()
    second = PkceAttempt.create()
    assert 43 <= len(first.code_verifier) <= 128
    assert first.code_challenge == derive_code_challenge(first.code_verifier)
    assert first.code_verifier != second.code_verifier
    assert first.state != second.state
    assert first.nonce != second.nonce
    assert first.state != first.nonce


def test_pkce_challenge_matches_rfc_vector() -> None:
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert derive_code_challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_authorization_url_has_verified_firka_parameters() -> None:
    from urllib.parse import parse_qs, urlsplit

    attempt = PkceAttempt("verifier", "challenge", "state-value", "nonce-value")
    outer = urlsplit(build_authorization_url("school01", attempt))
    assert outer.scheme == "https"
    assert outer.hostname == "idp.e-kreta.hu"
    assert outer.path == "/Account/Login"
    return_url = parse_qs(outer.query)["ReturnUrl"][0]
    inner = urlsplit(return_url)
    params = parse_qs(inner.query)
    assert inner.path == "/connect/authorize/callback"
    assert params["redirect_uri"] == [OAUTH_REDIRECT_URI]
    assert params["client_id"] == [OAUTH_CLIENT_ID]
    assert params["response_type"] == ["code"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["code_challenge"] == ["challenge"]
    assert params["state"] == ["state-value"]
    assert params["nonce"] == ["nonce-value"]
    assert params["scope"][0].split() == list(OAUTH_SCOPES)
    assert params["institute_code"] == ["school01"]


def test_callback_code_is_validated() -> None:
    url = f"{OAUTH_REDIRECT_URI}?code=one-time-code&state=expected-state"
    assert extract_callback_code(url, "school01", "expected-state") == "one-time-code"


def test_state_mismatch_is_rejected() -> None:
    url = f"{OAUTH_REDIRECT_URI}?code=one-time-code&state=wrong-state"
    with pytest.raises(OAuthStateMismatchError):
        extract_callback_code(url, "school01", "expected-state")


def test_missing_code_is_rejected() -> None:
    url = f"{OAUTH_REDIRECT_URI}?state=expected-state"
    with pytest.raises(OAuthCodeMissingError):
        extract_callback_code(url, "school01", "expected-state")


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/ellenorzo-student/prod/oauthredirect?code=x&state=s",
        "http://mobil.e-kreta.hu/ellenorzo-student/prod/oauthredirect?code=x&state=s",
        "https://mobil.e-kreta.hu/wrong?code=x&state=s",
    ],
)
def test_invalid_callback_is_rejected(url: str) -> None:
    with pytest.raises((KretaSecurityError, OAuthCallbackError)):
        extract_callback_code(url, "school01", "s")


def test_account_key_uses_opaque_identity() -> None:
    token = _jwt({"kreta:institute_code": "school01", "kreta:institute_user_id": "Árvíztűrő"})
    key = account_key_from_id_token(token, "school01")
    assert len(key) == 64
    assert "Árvíz" not in key
    assert key != account_key_from_id_token(
        _jwt({"kreta:institute_code": "school01", "kreta:institute_user_id": "másik"}),
        "school01",
    )


def test_identity_token_institution_mismatch_is_rejected() -> None:
    token = _jwt({"kreta:institute_code": "other", "sub": "student"})
    with pytest.raises(OAuthCallbackError):
        account_key_from_id_token(token, "school01")


def test_config_schema_has_no_local_credentials_or_two_factor() -> None:
    keys = {str(key.schema) for key in _build_user_schema().schema}
    assert keys == {CONF_KLIK_ID, CONF_REFRESH_MINUTES, CONF_LOOKAHEAD_WEEKS}
    assert "password" not in keys
    assert "user_id" not in keys
    assert "two_factor_code" not in keys


async def test_config_flow_starts_browser_oauth(hass, monkeypatch) -> None:
    registered_views = []
    monkeypatch.setattr(
        hass,
        "http",
        SimpleNamespace(register_view=lambda view: registered_views.append(view)),
    )
    monkeypatch.setattr(
        "custom_components.kreta.oauth_start.get_url", lambda *_args, **_kwargs: "https://ha.local"
    )
    monkeypatch.setattr(
        "custom_components.kreta.oauth_start.async_sign_path",
        lambda _hass, path, _expiration, **_kwargs: f"{path}?authSig=signed",
    )
    flow = KretaConfigFlow()
    flow.hass = hass
    flow._flow_id = "flow-start"
    result = await flow.async_step_user(
        {CONF_KLIK_ID: "school01", CONF_REFRESH_MINUTES: 10, CONF_LOOKAHEAD_WEEKS: 2}
    )
    assert result["type"] == "external"
    assert result["step_id"] == "browser"
    assert result["url"].startswith("https://ha.local/api/kreta/oauth/start/")
    assert "authSig=signed" in result["url"]
    assert flow._attempt is not None
    assert "idp.e-kreta.hu" not in result["url"]
    assert flow._attempt.code_verifier not in result["url"]
    assert flow._attempt.state not in result["url"]
    assert registered_views == [KretaOAuthStartView]
    finished = await flow.async_step_browser({"opened": True})
    assert finished["type"] == "external_done"
    assert finished["step_id"] == "oauth_callback"


async def test_oauth_launcher_is_one_time_and_validates_destination() -> None:
    class _FlowManager:
        def __init__(self) -> None:
            self.calls = []

        async def async_configure(self, flow_id, user_input):
            self.calls.append((flow_id, user_input))
            return {"type": data_entry_flow.FlowResultType.EXTERNAL_STEP_DONE}

    manager = _FlowManager()
    handle = "one-time-handle"
    destination = "https://idp.e-kreta.hu/Account/Login?ReturnUrl=%2Fconnect"
    hass = SimpleNamespace(
        data={DOMAIN: {OAUTH_STARTS: {handle: OAuthStart("flow-id", "school01", destination)}}},
        config_entries=SimpleNamespace(flow=manager),
    )
    request = SimpleNamespace(app={"hass": hass})
    view = KretaOAuthStartView()
    with pytest.raises(web.HTTPFound) as redirect:
        await view.get(request, handle)
    assert redirect.value.location == destination
    assert manager.calls == [("flow-id", {"opened": True})]
    with pytest.raises(web.HTTPNotFound):
        await view.get(request, handle)


def test_oauth_launcher_view_is_registered_once() -> None:
    registered_views = []
    hass = SimpleNamespace(
        data={}, http=SimpleNamespace(register_view=lambda view: registered_views.append(view))
    )
    ensure_oauth_start_view(hass)
    ensure_oauth_start_view(hass)
    assert registered_views == [KretaOAuthStartView]
    assert hass.data[DOMAIN][OAUTH_VIEW_REGISTERED] is True


async def test_oauth_launcher_blocks_external_destination() -> None:
    handle = "blocked-handle"
    hass = SimpleNamespace(
        data={
            DOMAIN: {
                OAUTH_STARTS: {
                    handle: OAuthStart("flow-id", "school01", "https://evil.example/login")
                }
            }
        }
    )
    request = SimpleNamespace(app={"hass": hass})
    with pytest.raises(KretaSecurityError):
        await KretaOAuthStartView().get(request, handle)


async def test_config_flow_rejects_callback_state_mismatch(hass, monkeypatch) -> None:
    monkeypatch.setattr(
        hass,
        "http",
        SimpleNamespace(register_view=lambda _view: None),
    )
    monkeypatch.setattr(
        "custom_components.kreta.oauth_start.get_url", lambda *_args, **_kwargs: "https://ha.local"
    )
    monkeypatch.setattr(
        "custom_components.kreta.oauth_start.async_sign_path",
        lambda _hass, path, _expiration, **_kwargs: f"{path}?authSig=signed",
    )
    flow = KretaConfigFlow()
    flow.hass = hass
    flow._flow_id = "flow-mismatch"
    await flow.async_step_user(
        {CONF_KLIK_ID: "school01", CONF_REFRESH_MINUTES: 10, CONF_LOOKAHEAD_WEEKS: 2}
    )
    result = await flow.async_step_oauth_callback(
        {CONF_OAUTH_REDIRECT_URL: f"{OAUTH_REDIRECT_URI}?code=x&state=wrong"}
    )
    assert result["step_id"] == "oauth_callback"
    assert result["errors"] == {"base": "oauth_state_mismatch"}


async def test_callback_failure_categories_are_safe(caplog) -> None:
    flow = KretaConfigFlow()
    flow._attempt = PkceAttempt.create()
    flow._authorization_url = "https://idp.e-kreta.hu/Account/Login"
    flow._pending_data = {CONF_KLIK_ID: "school01"}
    secret_state = flow._attempt.state
    cases = (
        (
            f"{OAUTH_REDIRECT_URI}?code=secret-code&state=wrong-secret-state",
            "callback_state_mismatch",
        ),
        (f"{OAUTH_REDIRECT_URI}?state={secret_state}", "callback_code_missing"),
        (
            f"https://evil.example/callback?code=secret-code&state={secret_state}",
            "callback_invalid_host_or_path",
        ),
    )
    with caplog.at_level(logging.WARNING):
        for callback_url, category in cases:
            caplog.clear()
            await flow.async_step_oauth_callback({CONF_OAUTH_REDIRECT_URL: callback_url})
            assert f"KRÉTA OAuth stage failed: {category}" in caplog.text
            assert "secret-code" not in caplog.text
            assert "wrong-secret-state" not in caplog.text
            assert secret_state not in caplog.text


async def test_reauthentication_launches_new_oauth_attempt(hass, monkeypatch) -> None:
    monkeypatch.setattr(
        hass,
        "http",
        SimpleNamespace(register_view=lambda _view: None),
    )
    monkeypatch.setattr(
        "custom_components.kreta.oauth_start.get_url", lambda *_args, **_kwargs: "https://ha.local"
    )
    monkeypatch.setattr(
        "custom_components.kreta.oauth_start.async_sign_path",
        lambda _hass, path, _expiration, **_kwargs: f"{path}?authSig=signed",
    )
    flow = KretaConfigFlow()
    flow.hass = hass
    flow._flow_id = "flow-reauth"
    entry = SimpleNamespace(data={CONF_KLIK_ID: "school01", CONF_ACCOUNT_KEY: "a" * 64})
    flow._get_reauth_entry = lambda: entry
    result = await flow.async_step_reauth_confirm({})
    assert result["step_id"] == "browser"
    assert flow._pending_mode == "reauth"


async def test_authorization_code_exchange_persists_only_refresh_token() -> None:
    id_token = _jwt({"kreta:institute_code": "school01", "kreta:institute_user_id": "student"})
    session = _FakeSession(
        [
            _FakeResponse(
                200,
                payload={
                    "access_token": "access-secret",
                    "refresh_token": "refresh-secret",
                    "id_token": id_token,
                },
            )
        ]
    )
    store = MemoryTokenStore()
    client = KretaApiClient(session=session, klik_id="school01", token_store=store)
    account_key = await client.async_exchange_authorization_code(
        "authorization-secret", "verifier-secret"
    )
    request = session.requests[0]
    assert request[0] == "post"
    assert request[1] == TOKEN_URL
    assert request[2]["allow_redirects"] is False
    assert request[2]["data"] == {
        "code": "authorization-secret",
        "code_verifier": "verifier-secret",
        "redirect_uri": OAUTH_REDIRECT_URI,
        "client_id": OAUTH_CLIENT_ID,
        "grant_type": "authorization_code",
    }
    assert len(account_key) == 64
    assert client._access_token == "access-secret"
    assert await store.async_get_refresh_token() == "refresh-secret"
    assert not hasattr(store, "access_token")


async def test_refresh_token_flow_works() -> None:
    session = _FakeSession(
        [_FakeResponse(200, payload={"access_token": "new-access", "refresh_token": "new-refresh"})]
    )
    store = MemoryTokenStore()
    await store.async_set_refresh_token("old-refresh")
    client = KretaApiClient(session=session, klik_id="school01", token_store=store)
    await client.async_authenticate()
    assert client._access_token == "new-access"
    assert await store.async_get_refresh_token() == "new-refresh"


async def test_invalid_refresh_token_is_removed_and_requires_reauth() -> None:
    session = _FakeSession([_FakeResponse(401, body='{"error":"invalid_grant"}')])
    store = MemoryTokenStore()
    await store.async_set_refresh_token("stale-refresh")
    client = KretaApiClient(session=session, klik_id="school01", token_store=store)
    with pytest.raises(InvalidAuthError):
        await client.async_authenticate()
    assert await store.async_get_refresh_token() is None


async def test_client_without_refresh_token_requires_reauth() -> None:
    client = KretaApiClient(
        session=_FakeSession([]), klik_id="school01", token_store=MemoryTokenStore()
    )
    with pytest.raises(InvalidAuthError, match="reauthentication"):
        await client.async_authenticate()


def test_auth_secrets_are_redacted() -> None:
    secrets = {
        "password": "password-value",
        "refresh_token": "refresh-value",
        "code": "auth-code",
        "code_verifier": "verifier-value",
    }
    sanitized = sanitize_form_data(secrets)
    assert set(sanitized.values()) == {"***"}
    assert not any(value in str(sanitized) for value in secrets.values())
    body = sanitize_response_body('{"access_token":"secret","name":"Private"}')
    assert "secret" not in body
    assert "Private" not in body
    redirect = sanitize_redirect_url(
        "https://mobil.e-kreta.hu/ellenorzo-student/prod/oauthredirect?code=secret&state=secret"
    )
    assert "code=secret" not in redirect
    assert "state=secret" not in redirect


async def test_failure_logs_contain_stage_but_no_oauth_secrets(caplog) -> None:
    session = _FakeSession([_FakeResponse(400, body='{"error":"invalid_grant"}')])
    client = KretaApiClient(session=session, klik_id="school01", token_store=MemoryTokenStore())
    with caplog.at_level(logging.WARNING), pytest.raises(InvalidAuthError):
        await client.async_exchange_authorization_code("code-secret", "verifier-secret")
    assert "KRÉTA auth stage failed: token_exchange" in caplog.text
    assert "code-secret" not in caplog.text
    assert "verifier-secret" not in caplog.text


async def test_http_error_preserves_safe_request_metadata() -> None:
    session = _FakeSession([_FakeResponse(500, body="private response details")])
    client = KretaApiClient(session=session, klik_id="school01", token_store=MemoryTokenStore())
    client._access_token = "access-secret"
    with pytest.raises(KretaApiError) as raised:
        await client._async_request(
            "get",
            "https://school01.e-kreta.hu/ellenorzo/v3/Sajat/Ertekelesek",
            retry_on_auth_error=False,
        )
    assert raised.value.method == "GET"
    assert raised.value.endpoint == "school01.e-kreta.hu/ellenorzo/v3/Sajat/Ertekelesek"
    assert raised.value.status == 500
    assert raised.value.safe_description == "http_error_response"


async def test_forbidden_feature_does_not_trigger_token_refresh() -> None:
    session = _FakeSession([_FakeResponse(403, body="private response details")])
    store = MemoryTokenStore()
    client = KretaApiClient(session=session, klik_id="school01", token_store=store)
    client._access_token = "access-secret"
    with pytest.raises(KretaApiError) as raised:
        await client._async_request(
            "get",
            "https://school01.e-kreta.hu/ellenorzo/v3/Sajat/Ertekelesek",
        )
    assert not isinstance(raised.value, InvalidAuthError)
    assert raised.value.status == 403
    assert "private response details" not in str(raised.value)
    assert len(session.requests) == 1


async def test_coordinator_logs_operation_and_preserves_exception_chain(caplog) -> None:
    underlying = KretaApiError(
        "private response containing student data",
        method="GET",
        endpoint="school01.e-kreta.hu/ellenorzo/v3/Sajat/TanuloAdatlap",
        status=403,
        safe_description="authenticated_request_rejected",
    )

    class _FailingClient:
        async def async_get_student_profile(self):
            raise underlying

    coordinator = object.__new__(KretaDataUpdateCoordinator)
    coordinator.client = _FailingClient()
    coordinator.config_entry = SimpleNamespace(
        options={},
        data={CONF_KLIK_ID: "school01", CONF_LOOKAHEAD_WEEKS: 2},
    )
    with caplog.at_level(logging.ERROR), pytest.raises(UpdateFailed) as raised:
        await coordinator._async_update_data()
    assert raised.value.__cause__ is underlying
    assert "operation=student_profile" in caplog.text
    assert "method=GET" in caplog.text
    assert "endpoint=school01.e-kreta.hu/ellenorzo/v3/Sajat/TanuloAdatlap" in caplog.text
    assert "status=403" in caplog.text
    assert "exception=KretaApiError" in caplog.text
    assert "description=authenticated_request_rejected" in caplog.text
    assert "private response containing student data" not in caplog.text


async def test_optional_endpoint_failure_keeps_coordinator_available(caplog, monkeypatch) -> None:
    class _PartiallyAvailableClient:
        async def async_get_student_profile(self):
            return StudentProfile(student_name=None, school_name="School")

        async def async_get_lessons(self, _start, _end):
            raise KretaApiError(
                "private response details",
                method="GET",
                endpoint="school01.e-kreta.hu/ellenorzo/v3/Sajat/OrarendElemek",
                status=404,
                safe_description="http_error_response",
            )

        async def async_get_announced_tests(self, _start, _end):
            return []

        async def async_get_grades(self, _start, _end):
            return []

        async def async_get_homework(self, _start, _end):
            return []

        async def async_get_absences(self, _start, _end):
            return []

        async def async_get_messages(self):
            return []

        async def async_get_school_year_calendar(self):
            return []

    async def _no_new_records(*_args):
        return 0

    monkeypatch.setattr(KretaDataUpdateCoordinator, "_emit_new", _no_new_records)
    monkeypatch.setattr(KretaDataUpdateCoordinator, "_emit_timetable_changes", _no_new_records)
    coordinator = object.__new__(KretaDataUpdateCoordinator)
    coordinator.client = _PartiallyAvailableClient()
    coordinator.config_entry = SimpleNamespace(
        options={},
        data={CONF_KLIK_ID: "school01", CONF_LOOKAHEAD_WEEKS: 2},
    )
    coordinator.last_error_message = None
    coordinator.last_error_time = None
    coordinator.degraded_operations = set()
    with caplog.at_level(logging.ERROR):
        data = await coordinator._async_update_data()
    assert data.profile.school_name == "School"
    assert data.events == []
    assert data.school_year_calendar == []
    assert coordinator.last_error_message == "partial_data"
    assert coordinator.degraded_operations == {"lessons"}
    assert "operation=lessons" in caplog.text
    assert "status=404" in caplog.text
    assert "private response details" not in caplog.text


def test_token_repr_does_not_expose_secrets() -> None:
    tokens = OAuthTokens("access-secret", "refresh-secret")
    assert "access-secret" not in repr(tokens)
    assert "refresh-secret" not in repr(tokens)


def test_legacy_and_new_storage_keys_are_supported() -> None:
    legacy = credential_key("School01", "Student01")
    assert legacy == entry_storage_key({CONF_KLIK_ID: "school01", "user_id": "student01"})
    opaque = "a" * 64
    assert entry_storage_key({CONF_KLIK_ID: "school01", CONF_ACCOUNT_KEY: opaque}) == opaque


def test_disabled_feature_is_not_enabled() -> None:
    coordinator = object.__new__(KretaDataUpdateCoordinator)
    coordinator.config_entry = SimpleNamespace(options={CONF_MESSAGES: False})
    assert coordinator._enabled(CONF_MESSAGES) is False


class _FakeStore:
    data: dict = {}

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    async def async_load(self):
        return self.data

    async def async_save(self, data):
        self.__class__.data = data


async def test_initial_baseline_and_restart_deduplication(monkeypatch) -> None:
    monkeypatch.setattr("custom_components.kreta.api.storage.Store", _FakeStore)
    _FakeStore.data = {}
    store = KretaBaselineStore(SimpleNamespace(), "account")
    had_baseline, new = await store.async_update("grades", {"grade-1"})
    assert had_baseline is False
    assert new
    restarted = KretaBaselineStore(SimpleNamespace(), "account")
    had_baseline, new = await restarted.async_update("grades", {"grade-1"})
    assert had_baseline is True
    assert new == set()
