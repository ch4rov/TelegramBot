# -*- coding: utf-8 -*-
import base64
import logging
from datetime import datetime, timedelta

import aiohttp

from core.config import config
from services.database.repo import get_user_oauth_token, upsert_user_oauth_token

logger = logging.getLogger(__name__)


async def _refresh_spotify_token(user_id: int) -> str | None:
    tok = await get_user_oauth_token(user_id, "spotify")
    if not tok or not tok.refresh_token:
        return None

    if not config.SPOTIFY_CLIENT_ID or not config.SPOTIFY_CLIENT_SECRET:
        return None

    token_url = "https://accounts.spotify.com/api/token"
    basic = base64.b64encode(f"{config.SPOTIFY_CLIENT_ID}:{config.SPOTIFY_CLIENT_SECRET}".encode("utf-8")).decode("ascii")
    headers = {
        "Authorization": f"Basic {basic}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "refresh_token",
        "refresh_token": tok.refresh_token,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(token_url, data=data, headers=headers, timeout=20) as resp:
            payload = await resp.json(content_type=None)
            if resp.status >= 400:
                logger.error("Spotify refresh failed: %s %s", resp.status, payload)
                return None

    access_token = (payload.get("access_token") or "").strip()
    if not access_token:
        return None

    expires_at = None
    try:
        expires_in = payload.get("expires_in")
        if expires_in is not None:
            expires_at = datetime.now() + timedelta(seconds=int(expires_in))
    except Exception:
        expires_at = None

    scope = payload.get("scope") or tok.scope
    refresh_token = payload.get("refresh_token") or tok.refresh_token

    await upsert_user_oauth_token(
        user_id=user_id,
        service="spotify",
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        scope=scope,
    )
    return access_token


async def get_spotify_access_token(user_id: int) -> str | None:
    tok = await get_user_oauth_token(user_id, "spotify")
    if not tok:
        return None

    # Refresh if expired/near expiry
    try:
        if tok.expires_at and tok.expires_at <= datetime.now() + timedelta(seconds=30):
            return await _refresh_spotify_token(user_id)
    except Exception:
        pass

    return (tok.access_token or "").strip() or None


async def spotify_get_json(user_id: int, url: str, params: dict | None = None) -> dict:
    access_token = await get_spotify_access_token(user_id)
    if not access_token:
        return {"error": "spotify_not_connected"}

    headers = {"Authorization": f"Bearer {access_token}"}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params, timeout=20) as resp:
            if resp.status == 204:
                return {"status": 204, "data": None}
            try:
                payload = await resp.json(content_type=None)
            except Exception:
                payload = {"status": resp.status, "text": await resp.text()}

            return {"status": resp.status, "data": payload}


async def spotify_dump_all(user_id: int) -> dict:
    """Return a bundle of useful raw Spotify API responses (no tokens)."""
    me = await spotify_get_json(user_id, "https://api.spotify.com/v1/me")
    now = await spotify_get_json(user_id, "https://api.spotify.com/v1/me/player/currently-playing")
    recent = await spotify_get_json(user_id, "https://api.spotify.com/v1/me/player/recently-played", params={"limit": 3})

    return {
        "me": me,
        "currently_playing": now,
        "recently_played": recent,
    }
