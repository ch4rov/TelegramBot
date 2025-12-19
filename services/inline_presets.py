# -*- coding: utf-8 -*-
import secrets
import time
from typing import Any


# token -> {user_id: int, items: list[dict], expires_at: float}
_PRESETS: dict[str, dict[str, Any]] = {}


def _cleanup(now: float | None = None) -> None:
    if now is None:
        now = time.time()
    expired = [k for k, v in _PRESETS.items() if float(v.get("expires_at") or 0) <= now]
    for k in expired:
        _PRESETS.pop(k, None)


def store_inline_preset(user_id: int, items: list[dict], ttl_seconds: int = 180) -> str:
    """Store a short-lived per-user preset and return a token."""
    _cleanup()

    token = secrets.token_urlsafe(16)
    _PRESETS[token] = {
        "user_id": int(user_id),
        "items": list(items or []),
        "expires_at": time.time() + max(30, int(ttl_seconds)),
    }
    return token


def get_inline_preset(user_id: int, token: str) -> list[dict] | None:
    _cleanup()

    token = (token or "").strip()
    if not token:
        return None

    row = _PRESETS.get(token)
    if not row:
        return None

    if int(row.get("user_id") or 0) != int(user_id):
        return None

    items = row.get("items")
    return list(items) if isinstance(items, list) else None


def get_inline_preset_item(user_id: int, token: str, index: int) -> dict | None:
    items = get_inline_preset(user_id, token)
    if not items:
        return None
    try:
        return items[int(index)]
    except Exception:
        return None
