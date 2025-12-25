from datetime import datetime

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse

from .config import ADMIN_IDS, BOT_TOKEN, PUBLIC_URL
from .db import session
from .initdata import InitDataError, user_id_from_init_data, validate_init_data, validate_init_data_admin
from .models import User, UserRequest


def _require_token() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN missing")


def _read_init_data(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    init_data: str | None = Query(default=None, alias="initData"),
) -> str:
    return (x_telegram_init_data or init_data or "").strip()


def require_admin(init_data: str = Depends(_read_init_data)) -> dict:
    _require_token()
    try:
        return validate_init_data_admin(init_data, BOT_TOKEN, ADMIN_IDS)
    except InitDataError as e:
        if str(e) == "forbidden":
            raise HTTPException(status_code=403, detail="forbidden")
        raise HTTPException(status_code=401, detail="bad_init_data")


def require_user(init_data: str = Depends(_read_init_data)) -> dict:
    _require_token()
    try:
        return validate_init_data(init_data, BOT_TOKEN)
    except InitDataError:
        raise HTTPException(status_code=401, detail="bad_init_data")


def _iso(dt: datetime | None) -> str | None:
    if not dt:
        return None
    try:
        return dt.isoformat()
    except Exception:
        return None


def create_app() -> FastAPI:
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    async def index():
        url = (PUBLIC_URL or "").strip().rstrip("/")
        base = url if url else ""
        return HTMLResponse(
            """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Mini App</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
</head>
<body style="font-family: system-ui; margin: 16px;">
    <h3>Mini App</h3>
    <div id="out" style="white-space: pre-wrap; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;"></div>
  <script>
    const out = document.getElementById('out');
    const tg = window.Telegram && window.Telegram.WebApp;
        if (tg) {
            try { tg.ready(); tg.expand(); } catch (e) {}
        }
        const initData = tg ? (tg.initData || '') : '';
    const base = """ + repr(base) + """;
    const apiBase = base ? base : '';
        const urlMe = (apiBase || '') + '/api/me';
        const urlAdmin = (apiBase || '') + '/api/admin/me';

        if (!initData) {
            out.textContent = 'No initData. Open this page inside Telegram as a Mini App.';
        } else {
            fetch(urlMe, { headers: { 'X-Telegram-Init-Data': initData } })
                .then(r => r.json().then(j => ({ ok: r.ok, status: r.status, j })))
                .then(async ({ ok, status, j }) => {
                    if (!ok) {
                        out.textContent = JSON.stringify({ ok, status, data: j, hint: 'If this is stable, ensure IS_TEST_ENV matches the bot token used by this bot.' }, null, 2);
                        return;
                    }
                    const isAdmin = !!(j && j.is_admin);
                    if (!isAdmin) {
                        out.textContent = JSON.stringify({ ok: true, mode: 'user', data: j }, null, 2);
                        return;
                    }
                    const r2 = await fetch(urlAdmin, { headers: { 'X-Telegram-Init-Data': initData } });
                    const j2 = await r2.json().catch(() => ({}));
                    out.textContent = JSON.stringify({ ok: r2.ok, status: r2.status, mode: 'admin', data: j2 }, null, 2);
                })
                .catch(err => { out.textContent = String(err); });
        }
  </script>
</body>
</html>"""
        )

        @app.get("/api/me")
        async def me(payload: dict = Depends(require_user)):
                uid = user_id_from_init_data(payload)
                return {"user_id": uid, "is_admin": bool(uid in set(ADMIN_IDS))}

    @app.get("/api/admin/me")
    async def admin_me(payload: dict = Depends(require_admin)):
        uid = user_id_from_init_data(payload)
        return {"user_id": uid, "is_admin": True}

    @app.get("/api/admin/profile")
    async def admin_profile(payload: dict = Depends(require_admin)):
        uid = user_id_from_init_data(payload)
        if uid is None:
            raise HTTPException(status_code=400, detail="no_user")

        db = session()
        try:
            user = db.get(User, uid)
            req_count = db.query(UserRequest).filter(UserRequest.user_id == uid).count()
        finally:
            db.close()

        user_json = None
        raw_user = payload.get("user")
        if raw_user:
            try:
                import json

                user_json = json.loads(raw_user)
            except Exception:
                user_json = None

        return {
            "user_id": uid,
            "username": (getattr(user, "username", None) if user else None),
            "full_name": (getattr(user, "full_name", None) if user else None) or (user_json.get("first_name") if isinstance(user_json, dict) else None),
            "photo_url": (user_json.get("photo_url") if isinstance(user_json, dict) else None),
            "first_seen": _iso(getattr(user, "first_seen", None) if user else None),
            "messages": int(req_count or 0),
        }

    @app.get("/api/admin/users")
    async def admin_users(
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        payload: dict = Depends(require_admin),
    ):
        db = session()
        try:
            rows = (
                db.query(User)
                .filter(User.id != 777000)
                .order_by(User.first_seen.desc())
                .limit(int(limit))
                .offset(int(offset))
                .all()
            )
            total = db.query(User).filter(User.id != 777000).count()
        finally:
            db.close()

        return {
            "total": int(total or 0),
            "limit": int(limit),
            "offset": int(offset),
            "items": [
                {
                    "id": int(u.id),
                    "username": u.username,
                    "full_name": u.full_name,
                    "is_banned": bool(u.is_banned),
                    "first_seen": _iso(u.first_seen),
                    "last_seen": _iso(u.last_seen),
                    "request_count": int(u.request_count or 0),
                }
                for u in rows
            ],
        }

    @app.post("/api/admin/users/{user_id}/ban")
    async def ban_user(user_id: int, payload: dict = Depends(require_admin)):
        db = session()
        try:
            user = db.get(User, int(user_id))
            if not user:
                raise HTTPException(status_code=404, detail="not_found")
            user.is_banned = True
            db.add(user)
            db.commit()
        finally:
            db.close()
        return {"ok": True}

    @app.post("/api/admin/users/{user_id}/unban")
    async def unban_user(user_id: int, payload: dict = Depends(require_admin)):
        db = session()
        try:
            user = db.get(User, int(user_id))
            if not user:
                raise HTTPException(status_code=404, detail="not_found")
            user.is_banned = False
            user.ban_reason = None
            db.add(user)
            db.commit()
        finally:
            db.close()
        return {"ok": True}

    @app.get("/api/debug/validate")
    async def debug_validate(
        init_data: str = Depends(_read_init_data),
    ):
        _require_token()
        try:
            data = validate_init_data(init_data, BOT_TOKEN)
            uid = user_id_from_init_data(data)
            return {"ok": True, "user_id": uid, "is_admin": bool(uid in set(ADMIN_IDS))}
        except InitDataError:
            raise HTTPException(status_code=401, detail="bad_init_data")

    return app
