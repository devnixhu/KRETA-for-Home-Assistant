"""Security, authentication, privacy and baseline regression tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.kreta.api.auth import (
    extract_authorization_code,
    extract_request_verification_token,
    extract_two_factor_form,
)
from custom_components.kreta.api.client import KretaApiClient
from custom_components.kreta.api.diagnostics import (
    sanitize_form_data,
    sanitize_redirect_url,
    sanitize_response_body,
)
from custom_components.kreta.api.exceptions import (
    InvalidAuthError,
    KretaSecurityError,
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
from custom_components.kreta.const import CONF_MESSAGES
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
    html = '<input name="__RequestVerificationToken" type="hidden" value="csrf-value">'
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
