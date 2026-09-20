"""KRÉTA OAuth authorization helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from urllib.parse import parse_qs, urlencode, urlsplit

from .endpoints import IDP_BASE
from .exceptions import OAuthCallbackError, OAuthCodeMissingError, OAuthStateMismatchError
from .network_policy import normalize_institution, validate_url
from .pkce import PkceAttempt

OAUTH_CLIENT_ID = "kreta-ellenorzo-student-mobile-ios"
OAUTH_REDIRECT_URI = "https://mobil.e-kreta.hu/ellenorzo-student/prod/oauthredirect"
OAUTH_REDIRECT_PATH = "/ellenorzo-student/prod/oauthredirect"
OAUTH_SCOPES = (
    "openid",
    "email",
    "offline_access",
    "kreta-ellenorzo-webapi.public",
    "kreta-eugyintezes-webapi.public",
    "kreta-fileservice-webapi.public",
    "kreta-mobile-global-webapi.public",
    "kreta-dkt-webapi.public",
    "kreta-ier-webapi.public",
)


def build_authorization_url(institution: str, attempt: PkceAttempt) -> str:
    """Build the official KRÉTA login URL for one PKCE attempt."""
    institute_code = normalize_institution(institution)
    authorize_query = urlencode(
        {
            "redirect_uri": OAUTH_REDIRECT_URI,
            "client_id": OAUTH_CLIENT_ID,
            "response_type": "code",
            "prompt": "login",
            "state": attempt.state,
            "nonce": attempt.nonce,
            "scope": " ".join(OAUTH_SCOPES),
            "code_challenge": attempt.code_challenge,
            "code_challenge_method": "S256",
            "institute_code": institute_code,
            "suppressed_prompt": "login",
        }
    )
    return_url = f"/connect/authorize/callback?{authorize_query}"
    return f"{IDP_BASE}/Account/Login?{urlencode({'ReturnUrl': return_url})}"


def extract_callback_code(callback_url: str, institution: str, expected_state: str) -> str:
    """Validate a pasted mobile redirect and return its transient code."""
    validated = validate_url(callback_url.strip(), institution)
    parsed = urlsplit(validated)
    if parsed.path != OAUTH_REDIRECT_PATH:
        raise OAuthCallbackError("Unexpected KRÉTA OAuth callback path")
    query = parse_qs(parsed.query, keep_blank_values=True)
    states = query.get("state", [])
    if len(states) != 1 or not hmac.compare_digest(states[0], expected_state):
        raise OAuthStateMismatchError("KRÉTA OAuth state mismatch")
    codes = query.get("code", [])
    if len(codes) != 1 or not codes[0]:
        raise OAuthCodeMissingError("KRÉTA OAuth callback omitted the code")
    return codes[0]


def account_key_from_id_token(id_token: str, institution: str) -> str:
    """Create a non-identifying stable account key from a trusted token response."""
    try:
        payload_segment = id_token.split(".")[1]
        padding = "=" * (-len(payload_segment) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_segment + padding))
    except (IndexError, ValueError, TypeError, json.JSONDecodeError) as err:
        raise OAuthCallbackError("KRÉTA returned an invalid identity token") from err
    token_institution = str(payload.get("kreta:institute_code", "")).casefold()
    expected_institution = normalize_institution(institution)
    if token_institution and token_institution != expected_institution:
        raise OAuthCallbackError("KRÉTA identity token institution mismatch")
    subject = payload.get("kreta:institute_user_id") or payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise OAuthCallbackError("KRÉTA identity token omitted the account subject")
    return hashlib.sha256(f"{expected_institution}:{subject}".encode()).hexdigest()
