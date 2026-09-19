"""Fail-closed outbound network policy for KRÉTA Secure."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urljoin, urlsplit

from .exceptions import KretaSecurityError

IDP_HOST = "idp.e-kreta.hu"
MESSAGES_HOST = "eugyintezes.e-kreta.hu"
MOBILE_REDIRECT_HOST = "mobil.e-kreta.hu"
_INSTITUTION_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", re.ASCII)


def normalize_institution(value: str) -> str:
    """Return a validated institution identifier."""
    normalized = value.strip().lower()
    if not _INSTITUTION_RE.fullmatch(normalized):
        raise KretaSecurityError("Invalid KRÉTA institution identifier")
    return normalized


def allowed_hosts(institution: str, *, include_messages: bool = False) -> frozenset[str]:
    """Return the complete allowlist for an account."""
    hosts = {
        IDP_HOST,
        MOBILE_REDIRECT_HOST,
        f"{normalize_institution(institution)}.e-kreta.hu",
    }
    if include_messages:
        hosts.add(MESSAGES_HOST)
    return frozenset(hosts)


def validate_url(
    url: str,
    institution: str,
    *,
    include_messages: bool = False,
) -> str:
    """Validate and return a canonical HTTPS URL.

    Exact hostname comparison prevents suffix, user-info and query-string
    confusion. IP literals, non-default ports and fragments are rejected.
    """
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError as err:
        raise KretaSecurityError("Invalid KRÉTA URL") from err

    if parsed.scheme.lower() != "https" or not host:
        raise KretaSecurityError("KRÉTA requests require HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise KretaSecurityError("User information is forbidden in KRÉTA URLs")
    if port not in (None, 443) or parsed.fragment:
        raise KretaSecurityError("Unexpected port or fragment in KRÉTA URL")
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        pass
    else:
        raise KretaSecurityError("IP address destinations are forbidden")
    if host not in allowed_hosts(institution, include_messages=include_messages):
        raise KretaSecurityError("Blocked non-KRÉTA network destination")
    return parsed.geturl()


def validate_redirect(
    source_url: str,
    location: str,
    institution: str,
    *,
    include_messages: bool = False,
) -> str:
    """Resolve and validate a redirect target using the same policy."""
    return validate_url(
        urljoin(source_url, location),
        institution,
        include_messages=include_messages,
    )
