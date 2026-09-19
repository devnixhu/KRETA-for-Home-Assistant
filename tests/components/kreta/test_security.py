"""Security, authentication, privacy and baseline regression tests."""

from __future__ import annotations

import logging
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.const import CONF_PASSWORD

from custom_components.kreta.api.auth import (
    extract_authorization_code,
    extract_request_verification_token,
    extract_two_factor_form,
    is_two_factor_route,
)
from custom_components.kreta.api.client import (
    AUTHORIZE_URL,
    CALLBACK_URL,
    KretaApiClient,
)
from custom_components.kreta.api.diagnostics import (
    sanitize_form_data,
    sanitize_redirect_url,
    sanitize_response_body,
)
from custom_components.kreta.api.endpoints import LOGIN_URL, TOKEN_URL
from custom_components.kreta.api.exceptions import (
    InvalidAuthError,
    KretaSecurityError,
    KretaTwoFactorRequired,
)
from custom_components.kreta.api.models import OAuthTokens
from custom_components.kreta.api.network_policy import (
    normalize_institution,
    validate_redirect,
    validate_url,
)
from custom_components.kreta.api.storage import (
    KretaBaselineStore,
    MemoryTokenStore,
    credential_key,
)
from custom_components.kreta.config_flow import KretaConfigFlow
from custom_components.kreta.const import (
    CONF_KLIK_ID,
    CONF_LOOKAHEAD_WEEKS,
    CONF_MESSAGES,
    CONF_REFRESH_MINUTES,
    CONF_USER_ID,
)
from custom_components.kreta.coordinator import KretaDataUpdateCoordinator


@pytest.mark.parametrize(
    "url",
    [
        "http://idp.e-kreta.hu",
        "https://evil.example",
        "https://e-kreta.hu.evil.example",
        "https://idp.e-kreta.hu@evil.example",
        "https://localhost",
        "https://127.0.0.1",
        "https://192.168.1.1",
        "file:///etc/passwd",
        "ftp://example.com",
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
        "https://mobil.e-kreta.hu/oauthredirect",
        "https://school01.e-kreta.hu/ellenorzo/v3/Sajat/Ertekelesek",
    ],
)
def test_network_policy_allows_only_expected_hosts(url: str) -> None:
    assert validate_url(url, "school01") == url


def test_messages_host_requires_explicit_feature_permission() -> None:
    url = "https://eugyintezes.e-kreta.hu/api/v1/kommunikacio/postaladaelemek/beerkezett"
    with pytest.raises(KretaSecurityError):
        validate_url(url, "school01")
    assert validate_url(url, "school01", include_messages=True) == url


@pytest.mark.parametrize("value", ["", "school.example", "../x", "a/b", "árvíz", "-school"])
def test_institution_identifier_is_strict(value: str) -> None:
    with pytest.raises(KretaSecurityError):
        normalize_institution(value)


def test_institution_identifier_is_normalized() -> None:
    assert normalize_institution("  SCHOOL-01 ") == "school-01"


def test_redirect_to_untrusted_host_is_blocked() -> None:
    with pytest.raises(KretaSecurityError):
        validate_redirect("https://idp.e-kreta.hu/start", "https://evil.example/x", "school01")


def test_relative_redirect_is_validated_and_resolved() -> None:
    assert (
        validate_redirect("https://idp.e-kreta.hu/start", "/Account/Login", "school01")
        == "https://idp.e-kreta.hu/Account/Login"
    )


def test_auth_html_extractors() -> None:
    html = (
        '<form><input name="__RequestVerificationToken" '
        'type="hidden" value="csrf-value"></form>'
    )
    assert extract_request_verification_token(html) == "csrf-value"
    assert extract_authorization_code("https://mobil.e-kreta.hu/cb?code=auth-code") == "auth-code"


def test_two_factor_form_detection() -> None:
    html = """
      <form action="/Account/LoginWith2fa">
        <input name="__RequestVerificationToken" value="csrf">
        <input name="Input.TwoFactorCode" value="">
      </form>
    """
    action, fields, code_field = extract_two_factor_form(html) or (None, None, None)
    assert action == "/Account/LoginWith2fa"
    assert fields == {"__RequestVerificationToken": "csrf", "Input.TwoFactorCode": ""}
    assert code_field == "Input.TwoFactorCode"


def test_non_2fa_form_is_not_misclassified() -> None:
    assert extract_two_factor_form('<form><input name="UserName"></form>') is None


@pytest.mark.parametrize(
    "url",
    [
        "https://idp.e-kreta.hu/Account/LoginWithTwoFactor",
        "https://idp.e-kreta.hu/account/loginwith2fa",
        "https://idp.e-kreta.hu/Account/LoginWith-TwoFactor",
    ],
)
def test_known_two_factor_route_variants(url: str) -> None:
    assert is_two_factor_route(url)


def test_all_auth_secrets_are_redacted() -> None:
    secrets = {
        "Password": "password-value",
        "refresh_token": "refresh-value",
        "code": "auth-code",
        "Input.TwoFactorCode": "123456",
        "otp": "654321",
    }
    sanitized = sanitize_form_data(secrets)
    assert set(sanitized.values()) == {"***"}
    assert not any(value in str(sanitized) for value in secrets.values())


def test_response_values_are_never_logged() -> None:
    body = '{"access_token":"secret","student_name":"Private Person","error":"bad"}'
    result = sanitize_response_body(body)
    assert "secret" not in result
    assert "Private Person" not in result
    assert "access_token" in result


def test_redirect_authorization_code_is_redacted() -> None:
    result = sanitize_redirect_url("https://mobil.e-kreta.hu/cb?code=secret&state=ok")
    assert "secret" not in result
    assert "state=ok" in result


def test_token_repr_does_not_expose_secrets() -> None:
    tokens = OAuthTokens("access-secret", "refresh-secret")
    assert "access-secret" not in repr(tokens)
    assert "refresh-secret" not in repr(tokens)


def test_credential_key_is_stable_and_non_identifying() -> None:
    key = credential_key("School01", "Student01")
    assert key == credential_key(" school01 ", " student01 ")
    assert "school" not in key
    assert "student" not in key
    assert len(key) == 64


async def test_client_without_password_requires_reauth() -> None:
    client = KretaApiClient(
        session=AsyncMock(),
        klik_id="school01",
        user_id="student01",
        password=None,
        token_store=MemoryTokenStore(),
    )
    with pytest.raises(InvalidAuthError, match="reauthentication"):
        await client.async_authenticate()


def test_password_can_be_discarded_from_memory() -> None:
    client = KretaApiClient(
        session=AsyncMock(),
        klik_id="school01",
        user_id="student01",
        password="temporary-password",
        token_store=MemoryTokenStore(),
    )
    client.discard_password()
    assert client._password is None


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
        assert self.responses, f"Unexpected request: {method} {url}"
        return self.responses.popleft()


_LOGIN_PAGE = """
<form action="/account/login">
  <input type="hidden" name="__RequestVerificationToken" value="login-csrf">
</form>
"""
_TWO_FACTOR_PAGE = """
<form action="/Account/LoginWithTwoFactor">
  <input type="hidden" name="__RequestVerificationToken" value="two-factor-csrf">
  <input name="Input.TwoFactorCode" value="">
</form>
"""
_OAUTH_REDIRECT = (
    "https://mobil.e-kreta.hu/ellenorzo-student/prod/oauthredirect?"
    "code=authorization-secret&state=kreten_student_mobile"
)


def _client_with_responses(
    responses: list[_FakeResponse], *, user_id: str = "student01", password: str = "password-secret"
) -> tuple[KretaApiClient, _FakeSession, MemoryTokenStore]:
    session = _FakeSession(responses)
    store = MemoryTokenStore()
    return (
        KretaApiClient(
            session=session,
            klik_id="school01",
            user_id=user_id,
            password=password,
            token_store=store,
        ),
        session,
        store,
    )


async def test_password_login_without_two_factor_still_works() -> None:
    client, session, store = _client_with_responses(
        [
            _FakeResponse(200, body=_LOGIN_PAGE),
            _FakeResponse(200),
            _FakeResponse(302, headers={"Location": _OAUTH_REDIRECT}),
            _FakeResponse(
                200,
                payload={"access_token": "access-secret", "refresh_token": "refresh-secret"},
            ),
        ]
    )

    await client.async_authenticate(force_login=True)

    assert [url for _method, url, _kwargs in session.requests] == [
        AUTHORIZE_URL,
        LOGIN_URL,
        CALLBACK_URL,
        TOKEN_URL,
    ]
    assert client._access_token == "access-secret"
    assert client._password is None
    assert await store.async_get_refresh_token() == "refresh-secret"


async def test_password_redirect_loads_and_parses_two_factor_page() -> None:
    client, session, _store = _client_with_responses(
        [
            _FakeResponse(200, body=_LOGIN_PAGE),
            _FakeResponse(
                302,
                headers={"Location": "/Account/LoginWithTwoFactor?returnUrl=%2Fconnect"},
            ),
            _FakeResponse(200, body=_TWO_FACTOR_PAGE),
        ]
    )

    with pytest.raises(KretaTwoFactorRequired):
        await client.async_authenticate(force_login=True)

    assert session.requests[-1][1].startswith(
        "https://idp.e-kreta.hu/Account/LoginWithTwoFactor"
    )
    assert client._two_factor_action == (
        "https://idp.e-kreta.hu/Account/LoginWithTwoFactor"
    )
    assert client._two_factor_fields == {
        "__RequestVerificationToken": "two-factor-csrf",
        "Input.TwoFactorCode": "",
    }
    assert client._two_factor_code_field == "Input.TwoFactorCode"


async def test_two_factor_form_in_password_response_body_is_preserved() -> None:
    client, session, _store = _client_with_responses(
        [
            _FakeResponse(200, body=_LOGIN_PAGE),
            _FakeResponse(200, body=_TWO_FACTOR_PAGE),
        ]
    )

    with pytest.raises(KretaTwoFactorRequired):
        await client.async_authenticate(force_login=True)

    assert len(session.requests) == 2
    assert client._two_factor_code_field == "Input.TwoFactorCode"


async def test_correct_two_factor_code_continues_oauth_without_following_post_redirect() -> None:
    client, session, store = _client_with_responses(
        [
            _FakeResponse(200, body=_LOGIN_PAGE),
            _FakeResponse(302, headers={"Location": "/Account/LoginWith2fa"}),
            _FakeResponse(200, body=_TWO_FACTOR_PAGE.replace("LoginWithTwoFactor", "LoginWith2fa")),
            _FakeResponse(303, headers={"Location": "/connect/authorize/callback"}),
            _FakeResponse(302, headers={"Location": _OAUTH_REDIRECT}),
            _FakeResponse(
                200,
                payload={"access_token": "access-secret", "refresh_token": "refresh-secret"},
            ),
        ]
    )
    with pytest.raises(KretaTwoFactorRequired):
        await client.async_authenticate(force_login=True)

    await client.async_submit_two_factor("123456")

    post = session.requests[3]
    assert post[0] == "post"
    assert post[2]["allow_redirects"] is False
    assert post[2]["data"]["Input.TwoFactorCode"] == "123456"
    assert session.requests[4][1] == CALLBACK_URL
    assert await store.async_get_refresh_token() == "refresh-secret"


async def test_incorrect_two_factor_code_is_rejected_and_challenge_remains() -> None:
    client, _session, _store = _client_with_responses(
        [_FakeResponse(200, body=_TWO_FACTOR_PAGE)]
    )
    client._remember_two_factor_form(
        "https://idp.e-kreta.hu/Account/LoginWithTwoFactor", _TWO_FACTOR_PAGE
    )

    with pytest.raises(InvalidAuthError, match="rejected"):
        await client.async_submit_two_factor("654321")

    assert client._two_factor_fields is not None


async def test_external_two_factor_redirect_is_blocked() -> None:
    client, _session, _store = _client_with_responses(
        [
            _FakeResponse(200, body=_LOGIN_PAGE),
            _FakeResponse(
                302,
                headers={"Location": "https://evil.example/Account/LoginWithTwoFactor"},
            ),
        ]
    )

    with pytest.raises(KretaSecurityError):
        await client.async_authenticate(force_login=True)


async def test_config_flow_moves_to_two_factor_step() -> None:
    flow = KretaConfigFlow()
    flow._async_authenticate = AsyncMock(
        side_effect=KretaTwoFactorRequired("2FA required")
    )
    result = await flow.async_step_user(
        {
            CONF_KLIK_ID: "school01",
            CONF_USER_ID: "Árvíztűrő.Tükörfúrógép",
            CONF_PASSWORD: "password-secret",
            CONF_REFRESH_MINUTES: 10,
            CONF_LOOKAHEAD_WEEKS: 4,
        }
    )

    assert result["type"] == "form"
    assert result["step_id"] == "two_factor"


async def test_config_flow_reports_invalid_two_factor() -> None:
    flow = KretaConfigFlow()
    flow._pending_client = AsyncMock()
    flow._pending_client.async_submit_two_factor.side_effect = InvalidAuthError("bad code")

    result = await flow.async_step_two_factor({"two_factor_code": "000000"})

    assert result["step_id"] == "two_factor"
    assert result["errors"] == {"base": "invalid_two_factor"}


async def test_unicode_username_is_posted_without_normalization() -> None:
    username = "Árvíztűrő.Tükörfúrógép"
    client, session, _store = _client_with_responses(
        [
            _FakeResponse(200, body=_LOGIN_PAGE),
            _FakeResponse(302, headers={"Location": "/Account/LoginWithTwoFactor"}),
            _FakeResponse(200, body=_TWO_FACTOR_PAGE),
        ],
        user_id=username,
    )
    with pytest.raises(KretaTwoFactorRequired):
        await client.async_authenticate(force_login=True)

    assert session.requests[1][2]["data"]["UserName"] == username


async def test_auth_failure_log_contains_stage_but_no_secrets(caplog) -> None:
    password = "password-secret-unique"
    code = "987654"
    client, _session, _store = _client_with_responses(
        [_FakeResponse(200, body=_TWO_FACTOR_PAGE)], password=password
    )
    client._remember_two_factor_form(
        "https://idp.e-kreta.hu/Account/LoginWithTwoFactor", _TWO_FACTOR_PAGE
    )

    with caplog.at_level(logging.WARNING), pytest.raises(InvalidAuthError):
        await client.async_submit_two_factor(code)

    log_text = caplog.text
    assert "KRÉTA auth stage failed: two_factor_submit" in log_text
    assert password not in log_text
    assert code not in log_text
    assert "access-secret" not in log_text
    assert "refresh-secret" not in log_text
    assert "authorization-secret" not in log_text


def test_config_entry_data_excludes_password_and_2fa() -> None:
    flow = KretaConfigFlow()
    flow._pending_input = {
        "klik_id": "school01",
        "user_id": "student01",
        "password": "temporary-password",
        "two_factor_code": "123456",
        "refresh_minutes": 10,
    }
    assert flow._entry_data_without_secrets() == {
        "klik_id": "school01",
        "user_id": "student01",
        "refresh_minutes": 10,
    }


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

    had_baseline, new = await restarted.async_update("grades", {"grade-1", "grade-2"})
    assert had_baseline is True
    assert len(new) == 1
