from datetime import datetime
import os

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse

from .config import ADMIN_IDS, BOT_TOKEN, PUBLIC_URL
from .db import session
from .initdata import InitDataError, user_id_from_init_data, validate_init_data
from .models import User, UserRequest


def _require_token() -> None:
    if not BOT_TOKEN and not (os.getenv("BOT_TOKEN") or os.getenv("TEST_BOT_TOKEN")):
        raise RuntimeError("BOT_TOKEN missing")


def _candidate_tokens() -> list[str]:
    tokens: list[str] = []
    for raw in (
        (os.getenv("BOT_TOKEN") or "").strip(),
        (os.getenv("TEST_BOT_TOKEN") or "").strip(),
        (BOT_TOKEN or "").strip(),
    ):
        if raw and raw not in tokens:
            tokens.append(raw)
    return tokens


def _validate_any(init_data: str) -> dict:
    if not init_data:
        raise InitDataError("missing")
    last_err: Exception | None = None
    for tok in _candidate_tokens():
        try:
            return validate_init_data(init_data, tok)
        except Exception as e:
            last_err = e
            continue
    if isinstance(last_err, InitDataError):
        raise last_err
    raise InitDataError("bad_hash")


def _read_init_data(
    x_telegram_init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
    init_data: str | None = Query(default=None, alias="initData"),
) -> str:
    return (x_telegram_init_data or init_data or "").strip()


def require_admin(init_data: str = Depends(_read_init_data)) -> dict:
    _require_token()
    try:
        payload = _validate_any(init_data)
        uid = user_id_from_init_data(payload)
        if uid is None or int(uid) not in set(int(x) for x in (ADMIN_IDS or [])):
            raise HTTPException(status_code=403, detail="forbidden")
        return payload
    except HTTPException:
        raise
    except InitDataError:
        raise HTTPException(status_code=401, detail="bad_init_data")


def require_user(init_data: str = Depends(_read_init_data)) -> dict:
    _require_token()
    try:
        return _validate_any(init_data)
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

    fallback_url = (os.getenv("MINIAPP_FALLBACK_URL") or "https://ch4rov.pl/").strip() or "https://ch4rov.pl/"

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(
                        """<!doctype html>
<html lang="ru">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Mini App</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        :root { color-scheme: dark; }
        html, body { height: 100%; margin: 0; }
        body {
            background: #0b0b0c;
            color: #fff;
            font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
        }
        .wrap { max-width: 820px; margin: 0 auto; padding: 18px 16px 28px; }
        .title { font-size: 22px; font-weight: 800; margin: 4px 0 4px; }
        .sub { color: rgba(255,255,255,.7); font-size: 13px; margin: 0 0 14px; }
        .grid { display: grid; grid-template-columns: 1fr; gap: 12px; }
        .card {
            border: 1px solid rgba(255,255,255,.10);
            background: rgba(255,255,255,.04);
            border-radius: 14px;
            padding: 12px 12px;
        }
        .card h4 { margin: 0 0 8px; font-size: 14px; color: rgba(255,255,255,.85); }
        .kv { display: grid; grid-template-columns: 140px 1fr; gap: 8px 10px; font-size: 13px; }
        .k { color: rgba(255,255,255,.6); }
        .v { color: rgba(255,255,255,.92); word-break: break-word; }
        .pill { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; border: 1px solid rgba(255,255,255,.14); }
        .ok { background: rgba(0, 180, 90, .18); }
        .bad { background: rgba(220, 60, 60, .18); }
    </style>
</head>
<body>
    <div class="wrap">
        <div class="title" id="hello">привет</div>
        <div class="sub" id="sub">Загрузка…</div>

        <div class="grid">
            <div class="card">
                <h4>Telegram</h4>
                <div class="kv" id="tg"></div>
            </div>

            <div class="card">
                <h4>База данных</h4>
                <div class="kv" id="db"></div>
            </div>
        </div>
    </div>

    <script>
        const fallback = """ + repr(fallback_url) + """;
        const tgApp = window.Telegram && window.Telegram.WebApp;
        if (!tgApp) {
            try { window.location.replace(fallback); } catch (e) { window.location.href = fallback; }
        }

        try { tgApp.ready(); } catch (e) {}

        const initData = (tgApp && tgApp.initData) ? tgApp.initData : '';
        if (!initData) {
            try { window.location.replace(fallback); } catch (e) { window.location.href = fallback; }
        }

        const initUnsafe = (tgApp && tgApp.initDataUnsafe) ? tgApp.initDataUnsafe : {};
        const u = initUnsafe.user || {};
        const displayName = (u.first_name || u.username || '');
        document.getElementById('hello').textContent = displayName ? ('привет, ' + displayName) : 'привет';

        const tgEl = document.getElementById('tg');
        const dbEl = document.getElementById('db');
        const subEl = document.getElementById('sub');

        function row(k, v) {
            const kEl = document.createElement('div');
            kEl.className = 'k';
            kEl.textContent = k;
            const vEl = document.createElement('div');
            vEl.className = 'v';
            vEl.textContent = (v === null || v === undefined || v === '') ? '—' : String(v);
            return [kEl, vEl];
        }

        function setKv(target, obj) {
            target.innerHTML = '';
            const entries = Object.entries(obj);
            for (const [k, v] of entries) {
                const [kEl, vEl] = row(k, v);
                target.appendChild(kEl);
                target.appendChild(vEl);
            }
        }

        setKv(tgEl, {
            'id': u.id,
            'username': u.username ? '@' + u.username : '—',
            'name': [u.first_name, u.last_name].filter(Boolean).join(' '),
            'language': u.language_code,
            'premium': u.is_premium ? 'yes' : 'no'
        });

        fetch('/api/profile', { headers: { 'X-Telegram-Init-Data': initData } })
            .then(async r => ({ ok: r.ok, status: r.status, j: await r.json().catch(() => ({})) }))
            .then(({ ok, status, j }) => {
                if (!ok) {
                    subEl.innerHTML = '<span class="pill bad">ошибка</span> ' + status;
                    setKv(dbEl, { 'detail': (j && j.detail) ? j.detail : 'error' });
                    return;
                }
                subEl.innerHTML = '<span class="pill ok">ok</span>';
                setKv(dbEl, {
                    'full_name': j.db && j.db.full_name,
                    'first_seen': j.db && j.db.first_seen,
                    'last_seen': j.db && j.db.last_seen,
                    'requests': j.db && j.db.request_count,
                    'lastfm': j.db && j.db.lastfm_username,
                    'banned': j.db && j.db.is_banned ? 'yes' : 'no'
                });
            })
            .catch(err => {
                subEl.innerHTML = '<span class="pill bad">ошибка</span>';
                setKv(dbEl, { 'error': String(err) });
            });
    </script>
</body>
</html>"""
        )

    @app.get("/api/me")
    async def me(payload: dict = Depends(require_user)):
        uid = user_id_from_init_data(payload)
        return {"user_id": uid, "is_admin": bool(uid in set(ADMIN_IDS))}

    @app.get("/api/profile")
    async def profile(payload: dict = Depends(require_user)):
        uid = user_id_from_init_data(payload)
        if uid is None:
            raise HTTPException(status_code=400, detail="no_user")

        tg_user = None
        raw_user = payload.get("user")
        if raw_user:
            try:
                import json

                tg_user = json.loads(raw_user)
            except Exception:
                tg_user = None

        db = session()
        try:
            user = db.get(User, int(uid))
        finally:
            db.close()

        return {
            "user_id": int(uid),
            "telegram": tg_user if isinstance(tg_user, dict) else None,
            "db": {
                "username": getattr(user, "username", None) if user else None,
                "full_name": getattr(user, "full_name", None) if user else None,
                "language": getattr(user, "language", None) if user else None,
                "first_seen": _iso(getattr(user, "first_seen", None) if user else None),
                "last_seen": _iso(getattr(user, "last_seen", None) if user else None),
                "request_count": int(getattr(user, "request_count", 0) or 0) if user else 0,
                "lastfm_username": getattr(user, "lastfm_username", None) if user else None,
                "is_banned": bool(getattr(user, "is_banned", False)) if user else False,
            },
        }

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
