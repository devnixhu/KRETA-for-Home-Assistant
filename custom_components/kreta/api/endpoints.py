"""Auditable KRÉTA endpoint catalogue."""

from __future__ import annotations

from .network_policy import normalize_institution

IDP_BASE = "https://idp.e-kreta.hu"
TOKEN_URL = f"{IDP_BASE}/connect/token"
LOGIN_URL = f"{IDP_BASE}/account/login"
MESSAGES_URL = "https://eugyintezes.e-kreta.hu/api/v1/kommunikacio/postaladaelemek/beerkezett"


def api_url(institution: str, path: str) -> str:
    """Build a read-only institution API URL from a fixed relative path."""
    if not path or path.startswith(("/", ".")) or "?" in path or "#" in path:
        raise ValueError("API path must be a fixed relative path")
    return f"https://{normalize_institution(institution)}.e-kreta.hu/ellenorzo/v3/{path}"
