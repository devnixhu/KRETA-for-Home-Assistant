"""Persistent token storage for Kreta."""

from __future__ import annotations

import hashlib
from typing import Any, Protocol

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from ..const import (
    BASELINE_STORAGE_KEY,
    CONF_ACCOUNT_KEY,
    CONF_KLIK_ID,
    CONF_USER_ID,
    STORAGE_KEY,
    STORAGE_VERSION,
)


def credential_key(institution: str, user_id: str) -> str:
    """Return a non-identifying stable key for one KRÉTA account."""
    normalized = f"{institution.strip().lower()}:{user_id.strip().lower()}"
    return hashlib.sha256(normalized.encode()).hexdigest()


def entry_storage_key(data: dict[str, Any]) -> str:
    """Return the new opaque account key or the legacy credential key."""
    account_key = data.get(CONF_ACCOUNT_KEY)
    if isinstance(account_key, str) and len(account_key) == 64:
        return account_key
    institution = data.get(CONF_KLIK_ID)
    user_id = data.get(CONF_USER_ID)
    if isinstance(institution, str) and isinstance(user_id, str):
        return credential_key(institution, user_id)
    raise ValueError("Config entry has no usable KRÉTA account key")


class TokenStore(Protocol):
    """Protocol for refresh-token storage backends."""

    async def async_get_refresh_token(self) -> str | None:
        """Return the stored refresh token, if any."""

    async def async_set_refresh_token(self, refresh_token: str | None) -> None:
        """Persist the refresh token."""


class KretaTokenStore:
    """Home Assistant-backed token storage per config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize storage."""
        self._entry_id = entry_id
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)

    async def async_get_refresh_token(self) -> str | None:
        """Return the stored refresh token."""
        data = await self._store.async_load() or {}
        entry_data = data.get(self._entry_id, {})
        return entry_data.get("refresh_token")

    async def async_set_refresh_token(self, refresh_token: str | None) -> None:
        """Persist the refresh token."""
        data = await self._store.async_load() or {}
        if refresh_token is None:
            data.pop(self._entry_id, None)
        else:
            data[self._entry_id] = {"refresh_token": refresh_token}
        await self._store.async_save(data)


class MemoryTokenStore:
    """In-memory token storage for config-flow validation."""

    def __init__(self) -> None:
        """Initialize the memory token store."""
        self._refresh_token: str | None = None

    async def async_get_refresh_token(self) -> str | None:
        """Return the current refresh token."""
        return self._refresh_token

    async def async_set_refresh_token(self, refresh_token: str | None) -> None:
        """Set the current refresh token."""
        self._refresh_token = refresh_token


class KretaBaselineStore:
    """Persist only hashed/stable identifiers needed to suppress replay."""

    def __init__(self, hass: HomeAssistant, account_key: str) -> None:
        self._account_key = account_key
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, BASELINE_STORAGE_KEY)

    async def async_update(self, category: str, identifiers: set[str]) -> tuple[bool, set[str]]:
        """Save identifiers and return `(had_baseline, newly_seen)`.

        Values are hashed before persistence to avoid building a shadow school
        database in Home Assistant storage.
        """
        hashed = {hashlib.sha256(identifier.encode()).hexdigest() for identifier in identifiers}
        data = await self._store.async_load() or {}
        account = data.setdefault(self._account_key, {})
        had_baseline = category in account
        previous = set(account.get(category, []))
        account[category] = sorted(hashed)[-500:]
        await self._store.async_save(data)
        return had_baseline, hashed - previous
