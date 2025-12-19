# -*- coding: utf-8 -*-
import base64
import logging
from datetime import datetime, timedelta
from urllib.parse import urlencode

from aiohttp import web, ClientSession

from core.config import config
from services.database.repo import consume_oauth_state, upsert_user_oauth_token

logger = logging.getLogger(__name__)


def _html_page(title: str, body: str, status: int = 200) -> web.Response:
    html = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{title}</title>
</head>
<body>
  <h3>{title}</h3>
  <p>{body}</p>
  <p>You can now return to Telegram.</p>
</body>
</html>"""
    return web.Response(text=html, status=status, content_type="text/html")


class OAuthServer:
    def __init__(self, bot):
        self._bot = bot
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    async def start(self) -> None:
        if not config.PUBLIC_BASE_URL:
            logger.warning("OAuthServer not started: PUBLIC_BASE_URL is empty")
            return

        host = config.OAUTH_HTTP_HOST
        port = int(config.OAUTH_HTTP_PORT)

        app = web.Application()
        app.router.add_get("/health", self._health)
        app.router.add_get("/oauth/spotify/callback", self._spotify_callback)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host=host, port=port)
        await site.start()

        self._app = app
        self._runner = runner
        self._site = site

        logger.info("OAuth callback server listening on http://%s:%s", host, port)

    async def stop(self) -> None:
        if self._runner:
            try:
                await self._runner.cleanup()
            except Exception:
                logger.exception("Failed stopping OAuthServer")
        self._app = None
        self._runner = None
        self._site = None

    async def _health(self, request: web.Request) -> web.Response:
        return web.Response(text="OK")

    def _redirect_uri(self, service: str) -> str:
        return f"{config.PUBLIC_BASE_URL}/oauth/{service}/callback"

    async def _spotify_callback(self, request: web.Request) -> web.Response:
        code = (request.query.get("code") or "").strip()
        state = (request.query.get("state") or "").strip()
        if not code or not state:
            return _html_page("Spotify OAuth", "Missing code/state", status=400)

        user_id = await consume_oauth_state(state, "spotify")
        if not user_id:
            return _html_page("Spotify OAuth", "State is invalid or expired", status=400)

        if not config.SPOTIFY_CLIENT_ID or not config.SPOTIFY_CLIENT_SECRET:
            return _html_page("Spotify OAuth", "Server is missing SPOTIFY_CLIENT_ID/SECRET", status=500)

        redirect_uri = self._redirect_uri("spotify")
        token_url = "https://accounts.spotify.com/api/token"

        basic = base64.b64encode(f"{config.SPOTIFY_CLIENT_ID}:{config.SPOTIFY_CLIENT_SECRET}".encode("utf-8")).decode("ascii")
        headers = {
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }

        try:
            async with ClientSession() as session:
                async with session.post(token_url, data=data, headers=headers, timeout=20) as resp:
                    payload = await resp.json(content_type=None)
                    if resp.status >= 400:
                        logger.error("Spotify token exchange failed: %s %s", resp.status, payload)
                        return _html_page("Spotify OAuth", "Token exchange failed", status=500)
        except Exception:
            logger.exception("Spotify token exchange exception")
            return _html_page("Spotify OAuth", "Token exchange exception", status=500)

        access_token = (payload.get("access_token") or "").strip()
        refresh_token = (payload.get("refresh_token") or None)
        scope = (payload.get("scope") or None)
        expires_in = payload.get("expires_in")
        expires_at = None
        try:
            if expires_in is not None:
                expires_at = datetime.now() + timedelta(seconds=int(expires_in))
        except Exception:
            expires_at = None

        if not access_token:
            return _html_page("Spotify OAuth", "No access_token returned", status=500)

        await upsert_user_oauth_token(
            user_id=user_id,
            service="spotify",
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            scope=scope,
        )

        try:
            await self._bot.send_message(user_id, "✅ Spotify connected", disable_notification=True)
        except Exception:
            logger.exception("Failed to notify user about Spotify connect")

        return _html_page("Spotify OAuth", "Connected successfully")


def build_spotify_authorize_url(state: str) -> str:
    redirect_uri = f"{config.PUBLIC_BASE_URL}/oauth/spotify/callback"
    params = {
        "client_id": config.SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": config.SPOTIFY_SCOPES or "",
        "state": state,
        "show_dialog": "true",
    }
    return "https://accounts.spotify.com/authorize?" + urlencode(params)
