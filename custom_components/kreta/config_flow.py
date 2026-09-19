"""Config flow for browser-based KRÉTA OAuth."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api.client import KretaApiClient
from .api.exceptions import (
    CannotConnectError,
    InvalidAuthError,
    KretaApiError,
    KretaSecurityError,
    OAuthCallbackError,
    OAuthCodeMissingError,
    OAuthStateMismatchError,
)
from .api.oauth import build_authorization_url, extract_callback_code
from .api.pkce import PkceAttempt
from .api.storage import KretaTokenStore, MemoryTokenStore, entry_storage_key
from .const import (
    CONF_ABSENCES,
    CONF_ACCOUNT_KEY,
    CONF_GRADES,
    CONF_HOMEWORK,
    CONF_KLIK_ID,
    CONF_LOOKAHEAD_WEEKS,
    CONF_MESSAGES,
    CONF_OAUTH_REDIRECT_URL,
    CONF_REFRESH_MINUTES,
    CONF_TESTS,
    CONF_TIMETABLE,
    DEFAULT_LOOKAHEAD_WEEKS,
    DEFAULT_REFRESH_MINUTES,
    DOMAIN,
    MAX_LOOKAHEAD_WEEKS,
    MAX_REFRESH_MINUTES,
    MIN_LOOKAHEAD_WEEKS,
    MIN_REFRESH_MINUTES,
)

_LOGGER = logging.getLogger(__name__)


def _build_user_schema(data: Mapping[str, Any] | None = None) -> vol.Schema:
    """Build the institution and scheduling form."""
    values = data or {}
    return vol.Schema(
        {
            vol.Required(CONF_KLIK_ID, default=values.get(CONF_KLIK_ID, "")): str,
            vol.Required(
                CONF_REFRESH_MINUTES,
                default=values.get(CONF_REFRESH_MINUTES, DEFAULT_REFRESH_MINUTES),
            ): vol.All(
                vol.Coerce(int), vol.Range(min=MIN_REFRESH_MINUTES, max=MAX_REFRESH_MINUTES)
            ),
            vol.Required(
                CONF_LOOKAHEAD_WEEKS,
                default=values.get(CONF_LOOKAHEAD_WEEKS, DEFAULT_LOOKAHEAD_WEEKS),
            ): vol.All(
                vol.Coerce(int),
                vol.Range(min=MIN_LOOKAHEAD_WEEKS, max=MAX_LOOKAHEAD_WEEKS),
            ),
        }
    )


def _build_callback_schema() -> vol.Schema:
    """Build the one-time OAuth redirect URL form."""
    return vol.Schema({vol.Required(CONF_OAUTH_REDIRECT_URL): str})


def _build_options_schema(config_entry: config_entries.ConfigEntry) -> vol.Schema:
    """Build the runtime options form."""
    options = config_entry.options
    return vol.Schema(
        {
            vol.Required(
                CONF_REFRESH_MINUTES,
                default=options.get(
                    CONF_REFRESH_MINUTES,
                    config_entry.data.get(CONF_REFRESH_MINUTES, DEFAULT_REFRESH_MINUTES),
                ),
            ): vol.All(
                vol.Coerce(int), vol.Range(min=MIN_REFRESH_MINUTES, max=MAX_REFRESH_MINUTES)
            ),
            vol.Required(
                CONF_LOOKAHEAD_WEEKS,
                default=options.get(
                    CONF_LOOKAHEAD_WEEKS,
                    config_entry.data.get(CONF_LOOKAHEAD_WEEKS, DEFAULT_LOOKAHEAD_WEEKS),
                ),
            ): vol.All(
                vol.Coerce(int),
                vol.Range(min=MIN_LOOKAHEAD_WEEKS, max=MAX_LOOKAHEAD_WEEKS),
            ),
            vol.Required(CONF_TIMETABLE, default=options.get(CONF_TIMETABLE, True)): bool,
            vol.Required(CONF_GRADES, default=options.get(CONF_GRADES, True)): bool,
            vol.Required(CONF_HOMEWORK, default=options.get(CONF_HOMEWORK, True)): bool,
            vol.Required(CONF_TESTS, default=options.get(CONF_TESTS, True)): bool,
            vol.Required(CONF_MESSAGES, default=options.get(CONF_MESSAGES, True)): bool,
            vol.Required(CONF_ABSENCES, default=options.get(CONF_ABSENCES, True)): bool,
        }
    )


class KretaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle browser-based KRÉTA OAuth setup and reauthentication."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize ephemeral authorization state."""
        self._attempt: PkceAttempt | None = None
        self._authorization_url: str | None = None
        self._pending_data: dict[str, Any] = {}
        self._pending_mode = "user"

    def _log_oauth_failure(self, stage: str) -> None:
        """Log only a privacy-safe OAuth stage marker."""
        _LOGGER.warning("KRÉTA OAuth stage failed: %s", stage)

    def _begin_oauth(
        self, data: Mapping[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Create a new in-memory PKCE attempt and show the callback form."""
        institution = str(data[CONF_KLIK_ID]).strip().lower()
        self._pending_data = dict(data)
        self._pending_data[CONF_KLIK_ID] = institution
        self._attempt = PkceAttempt.create()
        self._authorization_url = build_authorization_url(institution, self._attempt)
        return self._show_oauth_callback()

    def _show_oauth_callback(
        self, errors: dict[str, str] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Show the safe fixed-redirect fallback form."""
        return self.async_show_form(
            step_id="oauth_callback",
            data_schema=_build_callback_schema(),
            description_placeholders={"authorization_url": self._authorization_url or ""},
            errors=errors or {},
        )

    async def _async_finish_oauth(
        self, account_key: str, refresh_token: str, title: str
    ) -> config_entries.ConfigFlowResult:
        """Persist only the refresh token and finalize the config entry."""
        institution = self._pending_data[CONF_KLIK_ID]
        unique_id = f"{institution}:{account_key}"
        await self.async_set_unique_id(unique_id)
        target_entry: config_entries.ConfigEntry | None = None
        if self._pending_mode == "reauth":
            target_entry = self._get_reauth_entry()
        elif self._pending_mode == "reconfigure":
            target_entry = self._get_reconfigure_entry()
        if target_entry is None:
            self._abort_if_unique_id_configured()
        elif CONF_ACCOUNT_KEY in target_entry.data:
            self._abort_if_unique_id_mismatch()
        old_storage_key = entry_storage_key(dict(target_entry.data)) if target_entry else None
        token_store = KretaTokenStore(self.hass, account_key)
        await token_store.async_set_refresh_token(refresh_token)
        if old_storage_key and old_storage_key != account_key:
            await KretaTokenStore(self.hass, old_storage_key).async_set_refresh_token(None)
        data = {
            CONF_KLIK_ID: institution,
            CONF_ACCOUNT_KEY: account_key,
            CONF_REFRESH_MINUTES: self._pending_data.get(
                CONF_REFRESH_MINUTES, DEFAULT_REFRESH_MINUTES
            ),
            CONF_LOOKAHEAD_WEEKS: self._pending_data.get(
                CONF_LOOKAHEAD_WEEKS, DEFAULT_LOOKAHEAD_WEEKS
            ),
        }
        self._attempt = None
        self._authorization_url = None
        if target_entry is None:
            return self.async_create_entry(title=title, data=data)
        if CONF_ACCOUNT_KEY not in target_entry.data:
            self.hass.config_entries.async_update_entry(target_entry, unique_id=unique_id)
        return self.async_update_reload_and_abort(target_entry, data=data)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Collect the institution and begin official KRÉTA login."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._pending_mode = "user"
            try:
                return self._begin_oauth(user_input)
            except KretaSecurityError:
                errors["base"] = "invalid_institution"
                self._log_oauth_failure("authorization_start")
        return self.async_show_form(
            step_id="user",
            data_schema=_build_user_schema(user_input),
            errors=errors,
        )

    async def async_step_oauth_callback(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Validate the pasted fixed mobile callback and exchange its code."""
        if self._attempt is None or self._authorization_url is None:
            return self.async_abort(reason="oauth_start_failed")
        if user_input is None:
            return self._show_oauth_callback()
        try:
            code = extract_callback_code(
                user_input[CONF_OAUTH_REDIRECT_URL],
                self._pending_data[CONF_KLIK_ID],
                self._attempt.state,
            )
        except OAuthStateMismatchError:
            self._log_oauth_failure("callback_validation")
            return self._show_oauth_callback({"base": "oauth_state_mismatch"})
        except OAuthCodeMissingError:
            self._log_oauth_failure("callback_validation")
            return self._show_oauth_callback({"base": "oauth_code_missing"})
        except (OAuthCallbackError, KretaSecurityError):
            self._log_oauth_failure("callback_validation")
            return self._show_oauth_callback({"base": "oauth_callback_invalid"})
        memory_store = MemoryTokenStore()
        client = KretaApiClient(
            session=async_get_clientsession(self.hass),
            klik_id=self._pending_data[CONF_KLIK_ID],
            token_store=memory_store,
        )
        try:
            account_key = await client.async_exchange_authorization_code(
                code, self._attempt.code_verifier
            )
            profile = await client.async_get_student_profile()
        except CannotConnectError:
            self._log_oauth_failure("token_exchange")
            return self._show_oauth_callback({"base": "cannot_connect"})
        except (InvalidAuthError, KretaApiError):
            self._log_oauth_failure("token_exchange")
            return self._show_oauth_callback({"base": "token_exchange_failed"})
        refresh_token = await memory_store.async_get_refresh_token()
        if refresh_token is None:
            self._log_oauth_failure("token_exchange")
            return self._show_oauth_callback({"base": "token_exchange_failed"})
        return await self._async_finish_oauth(
            account_key,
            refresh_token,
            profile.school_name or "KRÉTA fiók",
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Start browser-based reauthentication."""
        self._pending_mode = "reauth"
        self._pending_data = dict(entry_data)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Confirm and launch browser-based reauthentication."""
        entry = self._get_reauth_entry()
        if user_input is not None:
            self._pending_mode = "reauth"
            return self._begin_oauth(dict(entry.data))
        return self.async_show_form(step_id="reauth_confirm", data_schema=vol.Schema({}))

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Reconfigure the institution through a fresh official login."""
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            self._pending_mode = "reconfigure"
            return self._begin_oauth(user_input)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_build_user_schema(dict(entry.data)),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> KretaOptionsFlowHandler:
        """Return the options flow."""
        return KretaOptionsFlowHandler(config_entry)


class KretaOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle KRÉTA runtime options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize the options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage runtime options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=_build_options_schema(self._config_entry),
        )
