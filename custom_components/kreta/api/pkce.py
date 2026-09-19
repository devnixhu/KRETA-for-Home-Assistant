"""Ephemeral PKCE material for KRÉTA OAuth."""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass, field


def derive_code_challenge(code_verifier: str) -> str:
    """Derive an RFC 7636 S256 code challenge."""
    digest = hashlib.sha256(code_verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


@dataclass(frozen=True, slots=True)
class PkceAttempt:
    """One non-persistent OAuth authorization attempt."""

    code_verifier: str = field(repr=False)
    code_challenge: str
    state: str = field(repr=False)
    nonce: str = field(repr=False)

    @classmethod
    def create(cls) -> PkceAttempt:
        """Generate independent cryptographically secure values."""
        verifier = secrets.token_urlsafe(64)
        return cls(
            code_verifier=verifier,
            code_challenge=derive_code_challenge(verifier),
            state=secrets.token_urlsafe(32),
            nonce=secrets.token_urlsafe(32),
        )
