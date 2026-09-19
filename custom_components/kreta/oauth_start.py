"""Authenticated local launcher for the KRÉTA authorization page."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import timedelta

from aiohttp import web
from homeassistant import data_entry_flow
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.auth import async_sign_path
from homeassistant.core import HomeAssistant
from homeassistant.helpers.network import get_url

from .api.network_policy import validate_url
from .const import DOMAIN

OAUTH_STARTS = "_oauth_starts"
OAUTH_VIEW_REGISTERED = "_oauth_view_registered"


@dataclass(frozen=True, slots=True)
class OAuthStart:
    """One authenticated local browser launch."""

    flow_id: str
    institution: str
    authorization_url: str


def ensure_oauth_start_view(hass: HomeAssistant) -> None:
    """Register the launcher view before the first config entry exists."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(OAUTH_VIEW_REGISTERED):
        return
    hass.http.register_view(KretaOAuthStartView)
    domain_data[OAUTH_VIEW_REGISTERED] = True


def register_oauth_start(
    hass: HomeAssistant, flow_id: str, institution: str, authorization_url: str
) -> str:
    """Register a bounded one-time launcher and return its local URL."""
    ensure_oauth_start_view(hass)
    starts: dict[str, OAuthStart] = hass.data.setdefault(DOMAIN, {}).setdefault(
        OAUTH_STARTS, {}
    )
    while len(starts) >= 100:
        starts.pop(next(iter(starts)))
    handle = secrets.token_urlsafe(24)
    starts[handle] = OAuthStart(flow_id, institution, authorization_url)
    base_url = get_url(hass, prefer_external=True)
    path = KretaOAuthStartView.url.format(handle=handle)
    signed_path = async_sign_path(hass, path, timedelta(minutes=5), use_content_user=True)
    return f"{base_url}{signed_path}"


class KretaOAuthStartView(HomeAssistantView):
    """Advance the config flow and redirect a new tab to KRÉTA."""

    url = "/api/kreta/oauth/start/{handle}"
    name = "api:kreta:oauth:start"
    requires_auth = True

    async def get(self, request: web.Request, handle: str) -> web.StreamResponse:
        """Consume a launcher and redirect only to a validated KRÉTA URL."""
        hass: HomeAssistant = request.app["hass"]
        starts: dict[str, OAuthStart] = hass.data.setdefault(DOMAIN, {}).setdefault(
            OAUTH_STARTS, {}
        )
        start = starts.pop(handle, None)
        if start is None:
            raise web.HTTPNotFound()
        destination = validate_url(start.authorization_url, start.institution)
        result = await hass.config_entries.flow.async_configure(
            start.flow_id, {"opened": True}
        )
        if result["type"] != data_entry_flow.FlowResultType.EXTERNAL_STEP_DONE:
            raise web.HTTPConflict()
        raise web.HTTPFound(location=destination)
