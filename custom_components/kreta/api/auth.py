"""Authentication helpers for the Kreta API."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

from .exceptions import InvalidAuthError

TWO_FACTOR_FIELD_NAMES = frozenset(
    {"twofactorcode", "authenticatorcode", "otp", "code", "input.twofactorcode"}
)


class _FormParser(HTMLParser):
    """Collect form actions and input fields without executing untrusted HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.forms: list[tuple[str, dict[str, str]]] = []
        self._action: str | None = None
        self._fields: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "form":
            self._action = values.get("action", "")
            self._fields = {}
        elif tag.lower() == "input" and self._action is not None:
            name = values.get("name")
            if name:
                self._fields[name] = values.get("value", "")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "form" and self._action is not None:
            self.forms.append((self._action, dict(self._fields)))
            self._action = None
            self._fields = {}


def extract_two_factor_form(html: str) -> tuple[str, dict[str, str], str] | None:
    """Return `(action, hidden fields, code field)` for a detected 2FA form."""
    parser = _FormParser()
    parser.feed(html[:200_000])
    for action, fields in parser.forms:
        for field_name in fields:
            if field_name.casefold() in TWO_FACTOR_FIELD_NAMES:
                return action, fields, field_name
    return None


def is_two_factor_route(url: str) -> bool:
    """Return whether a validated URL looks like a KRÉTA 2FA login route.

    This is only a routing hint. Callers must validate the URL against the
    network policy first and must confirm the page by parsing an actual 2FA
    form before accepting it as a challenge.
    """
    leaf = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1].casefold()
    compact = leaf.replace("-", "").replace("_", "")
    has_factor_marker = "twofactor" in compact or "2fa" in compact
    has_auth_marker = any(marker in compact for marker in ("login", "auth", "verify"))
    return has_factor_marker and has_auth_marker


REQUEST_VERIFICATION_TOKEN_RE = re.compile(
    r'name="__RequestVerificationToken"\s+type="hidden"\s+value="([^"]+)"'
)


def extract_request_verification_token(html: str) -> str:
    """Extract the request verification token from the login page HTML."""
    parser = _FormParser()
    parser.feed(html[:200_000])

    for _action, fields in parser.forms:
        token = fields.get("__RequestVerificationToken")
        if token:
            return token

    raise InvalidAuthError(
        "Missing request verification token in login page"
    )


def extract_authorization_code(redirect_location: str) -> str:
    """Extract the authorization code from the callback redirect URL."""
    parsed = urlparse(redirect_location)
    code = parse_qs(parsed.query).get("code", [])
    if not code:
        raise InvalidAuthError("Missing authorization code in callback redirect")
    return code[0]
