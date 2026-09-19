"""Exceptions for the Kreta client."""

from __future__ import annotations


class KretaApiError(Exception):
    """Base Kreta API exception."""


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
