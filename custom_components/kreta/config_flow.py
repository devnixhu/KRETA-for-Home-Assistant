"""Config flow for Kreta."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api.client import KretaApiClient
from .api.exceptions import (
    CannotConnectError,
    InvalidAuthError,
    KretaApiError,
    KretaSecurityError,
    KretaTwoFactorRequired,
)
from .api.storage import KretaTokenStore, MemoryTokenStore, credential_key
from .const import (
    CONF_ABSENCES,
    CONF_GRADES,
    CONF_HOMEWORK,
    CONF_KLIK_ID,
    CONF_LOOKAHEAD_WEEKS,
    CONF_MESSAGES,
    CONF_REFRESH_MINUTES,
    CONF_TESTS,
    CONF_TIMETABLE,
    CONF_USER_ID,
    DEFAULT_LOOKAHEAD_WEEKS,
    DEFAULT_REFRESH_MINUTES,
    DOMAIN,
    MAX_LOOKAHEAD_WEEKS,
    MAX_REFRESH_MINUTES,
    MIN_LOOKAHEAD_WEEKS,
    MIN_REFRESH_MINUTES,
)


def _build_user_schema(user_input: dict[str, Any] | None = None) -> vol.Schema:
    """Build the user step schema."""
    user_input = user_input or {}
    return vol.Schema(
        {
            vol.Required(CONF_KLIK_ID, default=user_input.get(CONF_KLIK_ID, "")): str,
            vol.Required(CONF_USER_ID, default=user_input.get(CONF_USER_ID, "")): str,
            vol.Required(CONF_PASSWORD, default=user_input.get(CONF_PASSWORD, "")): str,
            vol.Required(
                CONF_REFRESH_MINUTES,
                default=user_input.get(CONF_REFRESH_MINUTES, DEFAULT_REFRESH_MINUTES),
            ): vol.All(
                vol.Coerce(int), vol.Range(min=MIN_REFRESH_MINUTES, max=MAX_REFRESH_MINUTES)
            ),
            vol.Required(
                CONF_LOOKAHEAD_WEEKS,
                default=user_input.get(CONF_LOOKAHEAD_WEEKS, DEFAULT_LOOKAHEAD_WEEKS),
            ): vol.All(
                vol.Coerce(int),
                vol.Range(min=MIN_LOOKAHEAD_WEEKS, max=MAX_LOOKAHEAD_WEEKS),
            ),
        }
    )


def _build_reauth_schema() -> vol.Schema:
    """Build the re-authentication schema (password only)."""
    return vol.Schema({vol.Required(CONF_PASSWORD): str})


def _build_two_factor_schema() -> vol.Schema:
    """Build the transient KRÉTA 2FA code form."""
    return vol.Schema({vol.Required("two_factor_code"): str})


def _build_reconfigure_schema(data: dict[str, Any]) -> vol.Schema:
    """Build the reconfigure schema (credentials only, pre-filled)."""
    return vol.Schema(
        {
            vol.Required(CONF_KLIK_ID, default=data.get(CONF_KLIK_ID, "")): str,
            vol.Required(CONF_USER_ID, default=data.get(CONF_USER_ID, "")): str,
            vol.Required(CONF_PASSWORD): str,
        }
    )


def _build_options_schema(config_entry: config_entries.ConfigEntry) -> vol.Schema:
    """Build the options schema."""
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
                    config_entry.data[CONF_LOOKAHEAD_WEEKS],
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


async def async_validate_input(hass: HomeAssistant, user_input: dict[str, Any]) -> dict[str, str]:
    """Validate the user input allows us to connect."""
    session = async_get_clientsession(hass)
    client = KretaApiClient(
        session=session,
        klik_id=user_input[CONF_KLIK_ID],
        user_id=user_input[CONF_USER_ID],
        password=user_input[CONF_PASSWORD],
        token_store=MemoryTokenStore(),
    )
    await client.async_authenticate(force_login=True)
    profile = await client.async_get_student_profile()
    return {
        "title": profile.school_name or "KRÉTA Secure",
        "student_name": "KRÉTA fiók",
    }


class KretaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Kreta."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize transient authentication state."""
        self._pending_client: KretaApiClient | None = None
        self._pending_input: dict[str, Any] | None = None
        self._pending_mode = "user"

    async def _async_authenticate(self, user_input: dict[str, Any]) -> dict[str, str]:
        """Authenticate and retain only a refresh token after success."""
        normalized = dict(user_input)
        normalized[CONF_KLIK_ID] = normalized[CONF_KLIK_ID].strip().lower()
        normalized[CONF_USER_ID] = normalized[CONF_USER_ID].strip()
        client = KretaApiClient(
            session=async_get_clientsession(self.hass),
            klik_id=normalized[CONF_KLIK_ID],
            user_id=normalized[CONF_USER_ID],
            password=normalized[CONF_PASSWORD],
            token_store=KretaTokenStore(
                self.hass,
                credential_key(normalized[CONF_KLIK_ID], normalized[CONF_USER_ID]),
            ),
        )
        self._pending_client = client
        self._pending_input = normalized
        await client.async_authenticate(force_login=True)
        profile = await client.async_get_student_profile()
        client.discard_password()
        return {
            "title": profile.school_name or "KRÉTA Secure",
            "student_name": "KRÉTA fiók",
        }

    def _entry_data_without_secrets(self) -> dict[str, Any]:
        """Return pending config data without password or one-time codes."""
        assert self._pending_input is not None
        return {
            key: value
            for key, value in self._pending_input.items()
            if key not in {CONF_PASSWORD, "two_factor_code"}
        }

    async def _async_finish_pending(self, info: dict[str, str]) -> config_entries.ConfigFlowResult:
        """Create or update the entry after password/2FA authentication."""
        data = self._entry_data_without_secrets()
        unique_id = f"{data[CONF_KLIK_ID]}:{data[CONF_USER_ID].lower()}"
        await self.async_set_unique_id(unique_id)
        if self._pending_mode == "reauth":
            self._abort_if_unique_id_mismatch()
            return self.async_update_reload_and_abort(self._get_reauth_entry(), data=data)
        if self._pending_mode == "reconfigure":
            self._abort_if_unique_id_mismatch()
            return self.async_update_reload_and_abort(self._get_reconfigure_entry(), data=data)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=info["title"], data=data)

    async def async_step_two_factor(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Complete a KRÉTA authenticator/recovery-code challenge."""
        errors: dict[str, str] = {}
        if user_input is not None and self._pending_client is not None:
            try:
                await self._pending_client.async_submit_two_factor(user_input["two_factor_code"])
                profile = await self._pending_client.async_get_student_profile()
                self._pending_client.discard_password()
            except InvalidAuthError:
                errors["base"] = "invalid_two_factor"
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except KretaApiError:
                errors["base"] = "unknown"
            else:
                return await self._async_finish_pending(
                    {
                        "title": profile.school_name or "KRÉTA Secure",
                        "student_name": "KRÉTA fiók",
                    }
                )
        return self.async_show_form(
            step_id="two_factor",
            data_schema=_build_two_factor_schema(),
            errors=errors,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the user step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._pending_mode = "user"
            try:
                info = await self._async_authenticate(user_input)
            except KretaTwoFactorRequired:
                return await self.async_step_two_factor()
            except InvalidAuthError:
                errors["base"] = "invalid_auth"
            except KretaSecurityError:
                errors["base"] = "invalid_institution"
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except KretaApiError:
                errors["base"] = "unknown"
            else:
                return await self._async_finish_pending(info)

        return self.async_show_form(
            step_id="user",
            data_schema=_build_user_schema(user_input),
            errors=errors,
        )

    async def async_step_reauth(
        self,
        entry_data: Mapping[str, Any],  # noqa: ARG002
    ) -> config_entries.ConfigFlowResult:
        """Initiate re-authentication after a credential failure."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the re-authentication form (password only)."""
        reauth_entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            new_data = {**reauth_entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
            self._pending_mode = "reauth"
            try:
                info = await self._async_authenticate(new_data)
            except KretaTwoFactorRequired:
                return await self.async_step_two_factor()
            except InvalidAuthError:
                errors["base"] = "invalid_auth"
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except KretaApiError:
                errors["base"] = "unknown"
            else:
                return await self._async_finish_pending(info)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_build_reauth_schema(),
            description_placeholders={
                CONF_USER_ID: reauth_entry.data[CONF_USER_ID],
                CONF_KLIK_ID: reauth_entry.data[CONF_KLIK_ID],
            },
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle manual reconfiguration of credentials."""
        reconfigure_entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            new_data = {
                **reconfigure_entry.data,
                CONF_KLIK_ID: user_input[CONF_KLIK_ID].strip(),
                CONF_USER_ID: user_input[CONF_USER_ID].strip(),
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            }
            self._pending_mode = "reconfigure"
            try:
                info = await self._async_authenticate(new_data)
            except KretaTwoFactorRequired:
                return await self.async_step_two_factor()
            except InvalidAuthError:
                errors["base"] = "invalid_auth"
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except KretaApiError:
                errors["base"] = "unknown"
            else:
                return await self._async_finish_pending(info)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_build_reconfigure_schema(
                user_input if user_input is not None else dict(reconfigure_entry.data)
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> KretaOptionsFlowHandler:
        """Return the options flow."""
        return KretaOptionsFlowHandler(config_entry)


class KretaOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Kreta options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=_build_options_schema(self._config_entry),
        )
