"""Exceptions for the Kreta client."""

from __future__ import annotations


class KretaApiError(Exception):
    """Base Kreta API exception."""

    def __init__(
        self,
        message: str = "KRÉTA API error",
        *,
        method: str | None = None,
        endpoint: str | None = None,
        status: int | None = None,
        safe_description: str | None = None,
    ) -> None:
        super().__init__(message)
        self.method = method
        self.endpoint = endpoint
        self.status = status
        self.safe_description = safe_description

    def add_http_context(
        self,
        *,
        method: str | None = None,
        endpoint: str | None = None,
        status: int | None = None,
        safe_description: str | None = None,
    ) -> KretaApiError:
        """Add missing privacy-safe request metadata."""
        self.method = self.method or method
        self.endpoint = self.endpoint or endpoint
        self.status = self.status if self.status is not None else status
        self.safe_description = self.safe_description or safe_description
        return self


class CannotConnectError(KretaApiError):
    """Raised when the API cannot be reached."""


class InvalidAuthError(KretaApiError):
    """Raised when authentication fails."""


class ApiResponseError(KretaApiError):
    """Raised when the API returns an unexpected response."""


class KretaSecurityError(KretaApiError):
    """Raised when a request violates the outbound security policy."""


class KretaRateLimitError(KretaApiError):
    """Raised when KRÉTA rate-limits a request."""


class OAuthCallbackError(InvalidAuthError):
    """Raised when the OAuth callback is invalid."""


class OAuthStateMismatchError(OAuthCallbackError):
    """Raised when OAuth state validation fails."""


class OAuthCodeMissingError(OAuthCallbackError):
    """Raised when an OAuth callback has no authorization code."""
