from sqlalchemy import select, update, func
from sqlalchemy import delete
from sqlalchemy.dialects.sqlite import insert
from datetime import datetime, timedelta
from services.database.core import session_maker 
from services.database.models import User, SystemSettings, GlobalCookies, MediaCache, UserRequest, UserOAuthToken, OAuthState, UserPreference

# === РАБОТА С ПОЛЬЗОВАТЕЛЯМИ ===

async def add_or_update_user(user_id: int, username: str | None, full_name: str, tag: str | None = None, language: str = "en"):
    """Добавляет или обновляет пользователя. Username обновляется не чаще 1 раза в 24 часа."""
    async with session_maker() as session:
        async with session.begin():
            # Проверяем, есть ли уже такой пользователь
            existing = await session.execute(select(User).where(User.id == user_id))
            user = existing.scalar_one_or_none()
            
            if user:
                # Обновляем username только если прошло 24+ часа
                should_update_username = False
                if user.username_updated_at:
                    hours_passed = (datetime.now() - user.username_updated_at).total_seconds() / 3600
                    if hours_passed >= 24:
                        should_update_username = True
                else:
                    should_update_username = True
                
                # Обновляем поля
                update_data = {
                    "full_name": full_name,
                    "last_seen": datetime.now(),
                    "request_count": user.request_count + 1,
                    "is_active": True
                }
                
                if should_update_username and username:
                    update_data["username"] = username
                    update_data["username_updated_at"] = datetime.now()
                
                if tag:
                    update_data["user_tag"] = tag
                
                stmt = update(User).where(User.id == user_id).values(**update_data)
                await session.execute(stmt)
            else:
                # Создаем нового пользователя
                new_user = User(
                    id=user_id,
                    username=username,
                    full_name=full_name,
                    user_tag=tag or "",
                    language=language,
                    is_active=True
                )
                session.add(new_user)
            
            # Возвращаем пользователя
            result = await session.execute(select(User).where(User.id == user_id))
            return result.scalar_one()

async def get_user(user_id: int) -> User | None:
    """Получает пользователя по ID."""
    async with session_maker() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()


async def ensure_user_exists(
    user_id: int,
    username: str | None,
    full_name: str,
    tag: str | None = None,
    language: str = "en",
) -> User:
    """Create user/group record if missing. Does NOT increment request_count for existing users."""
    async with session_maker() as session:
        async with session.begin():
            existing = await session.execute(select(User).where(User.id == user_id))
            user = existing.scalar_one_or_none()
            if user:
                now = datetime.now()
                hours_passed = 9999.0
                try:
                    if user.username_updated_at:
                        hours_passed = (now - user.username_updated_at).total_seconds() / 3600
                except Exception:
                    hours_passed = 9999.0

                allow_profile_refresh = hours_passed >= 24
                bump_profile_ts = False

                update_data = {
                    "last_seen": now,
                    "is_active": True,
                }

                # Tag may change (e.g., group->supergroup)
                if tag:
                    update_data["user_tag"] = tag

                # Users: keep full_name reasonably fresh
                if user_id > 0:
                    if full_name and full_name != user.full_name:
                        update_data["full_name"] = full_name

                # Groups/chats: update title not more than once per 24h
                if user_id < 0:
                    desired_title = full_name
                    if desired_title:
                        if not user.full_name:
                            update_data["full_name"] = desired_title
                        elif allow_profile_refresh and desired_title != user.full_name:
                            update_data["full_name"] = desired_title
                            bump_profile_ts = True

                # Username: update not more than once per 24h (or if empty)
                if username:
                    if not user.username:
                        update_data["username"] = username
                    elif allow_profile_refresh and username != user.username:
                        update_data["username"] = username
                        bump_profile_ts = True

                if bump_profile_ts and allow_profile_refresh:
                    update_data["username_updated_at"] = now

                if update_data:
                    stmt = update(User).where(User.id == user_id).values(**update_data)
                    await session.execute(stmt)
            else:
                session.add(
                    User(
                        id=user_id,
                        username=username,
                        full_name=full_name,
                        user_tag=tag or "",
                        language=language or "en",
                        is_active=True,
                    )
                )

            result = await session.execute(select(User).where(User.id == user_id))
            return result.scalar_one()


async def delete_user(user_id: int) -> bool:
    """Delete user/group row from DB. Returns True if something was deleted."""
    async with session_maker() as session:
        async with session.begin():
            res = await session.execute(delete(User).where(User.id == user_id))
            try:
                return res.rowcount > 0
            except Exception:
                # Some drivers may not provide rowcount reliably
                return True

async def get_all_users():
    """Получает всех пользователей."""
    async with session_maker() as session:
        result = await session.execute(select(User))
        return result.scalars().all()


# === USER PREFERENCES (per-user key/value) ===

async def get_user_pref(user_id: int, key: str) -> str | None:
    key = (key or "").strip().lower()
    if not key:
        return None
    async with session_maker() as session:
        res = await session.execute(select(UserPreference).where(UserPreference.user_id == user_id, UserPreference.key == key))
        row = res.scalar_one_or_none()
        return (row.value if row else None)


async def set_user_pref(user_id: int, key: str, value: str) -> None:
    key = (key or "").strip().lower()
    if not key:
        return
    async with session_maker() as session:
        async with session.begin():
            stmt = insert(UserPreference).values(user_id=user_id, key=key, value=str(value))
            stmt = stmt.on_conflict_do_update(
                index_elements=[UserPreference.user_id, UserPreference.key],
                set_={"value": str(value), "updated_at": datetime.now()},
            )
            await session.execute(stmt)


async def get_user_pref_bool(user_id: int, key: str, default: bool = False) -> bool:
    raw = await get_user_pref(user_id, key)
    if raw is None:
        return bool(default)
    raw = str(raw).strip().lower()
    if raw in ("1", "true", "yes", "on", "y"):
        return True
    if raw in ("0", "false", "no", "off", "n"):
        return False
    return bool(default)


async def set_user_pref_bool(user_id: int, key: str, value: bool) -> None:
    await set_user_pref(user_id, key, "1" if bool(value) else "0")


# === OAUTH TOKENS (per-user) ===

async def create_oauth_state(user_id: int, service: str, ttl_minutes: int = 10) -> str:
    """Create a short-lived one-time OAuth state string bound to user_id+service."""
    import secrets

    service = (service or "").strip().lower()
    if not service:
        raise ValueError("service is required")

    state = secrets.token_urlsafe(32)
    now = datetime.now()
    expires_at = now + timedelta(minutes=max(1, int(ttl_minutes)))

    async with session_maker() as session:
        async with session.begin():
            # Best-effort cleanup
            try:
                await session.execute(delete(OAuthState).where(OAuthState.expires_at < now))
            except Exception:
                pass

            session.add(
                OAuthState(
                    state=state,
                    service=service,
                    user_id=user_id,
                    created_at=now,
                    expires_at=expires_at,
                )
            )
    return state


async def consume_oauth_state(state: str, service: str) -> int | None:
    """Consume state once and return user_id if valid (else None)."""
    service = (service or "").strip().lower()
    state = (state or "").strip()
    if not service or not state:
        return None

    now = datetime.now()
    async with session_maker() as session:
        async with session.begin():
            res = await session.execute(
                select(OAuthState).where(OAuthState.state == state, OAuthState.service == service)
            )
            row = res.scalar_one_or_none()
            if not row:
                return None
            if row.expires_at and row.expires_at < now:
                await session.execute(delete(OAuthState).where(OAuthState.id == row.id))
                return None
            user_id = int(row.user_id)
            await session.execute(delete(OAuthState).where(OAuthState.id == row.id))
            return user_id

async def get_user_oauth_token(user_id: int, service: str) -> UserOAuthToken | None:
    service = (service or "").strip().lower()
    if not service:
        return None
    async with session_maker() as session:
        res = await session.execute(
            select(UserOAuthToken).where(UserOAuthToken.user_id == user_id, UserOAuthToken.service == service)
        )
        return res.scalar_one_or_none()


async def upsert_user_oauth_token(
    user_id: int,
    service: str,
    access_token: str,
    refresh_token: str | None = None,
    expires_at: datetime | None = None,
    scope: str | None = None,
) -> UserOAuthToken:
    service = (service or "").strip().lower()
    async with session_maker() as session:
        async with session.begin():
            now = datetime.now()
            stmt = insert(UserOAuthToken).values(
                user_id=user_id,
                service=service,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
                scope=scope,
                created_at=now,
                updated_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[UserOAuthToken.user_id, UserOAuthToken.service],
                set_={
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "expires_at": expires_at,
                    "scope": scope,
                    "updated_at": now,
                },
            )
            await session.execute(stmt)
            res = await session.execute(
                select(UserOAuthToken).where(UserOAuthToken.user_id == user_id, UserOAuthToken.service == service)
            )
            return res.scalar_one()


async def delete_user_oauth_token(user_id: int, service: str) -> bool:
    service = (service or "").strip().lower()
    async with session_maker() as session:
        async with session.begin():
            res = await session.execute(
                delete(UserOAuthToken).where(UserOAuthToken.user_id == user_id, UserOAuthToken.service == service)
            )
            try:
                return res.rowcount > 0
            except Exception:
                return True


# === MEDIA CACHE (per-user) ===

async def get_cached_media(user_id: int, url: str, media_type: str) -> MediaCache | None:
    """Return cached media for this user+url+type (never cross-user)."""
    if not url:
        return None
    async with session_maker() as session:
        res = await session.execute(
            select(MediaCache).where(
                MediaCache.user_id == user_id,
                MediaCache.url == url,
                MediaCache.media_type == media_type,
            )
        )
        return res.scalar_one_or_none()


async def upsert_cached_media(
    user_id: int,
    url: str,
    file_id: str,
    media_type: str,
    title: str | None = None,
) -> MediaCache:
    """Insert/update cache row. Cache is strictly user-scoped."""
    async with session_maker() as session:
        async with session.begin():
            now = datetime.now()
            stmt = insert(MediaCache).values(
                user_id=user_id,
                url=url,
                file_id=file_id,
                media_type=media_type,
                title=title,
                created_at=now,
                last_used_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[MediaCache.user_id, MediaCache.url, MediaCache.media_type],
                set_={
                    "file_id": file_id,
                    "media_type": media_type,
                    "title": title,
                    "last_used_at": now,
                },
            )
            await session.execute(stmt)

            res = await session.execute(
                select(MediaCache).where(
                    MediaCache.user_id == user_id,
                    MediaCache.url == url,
                    MediaCache.media_type == media_type,
                )
            )
            return res.scalar_one()


async def get_cached_media_by_id(cache_id: int) -> MediaCache | None:
    async with session_maker() as session:
        res = await session.execute(select(MediaCache).where(MediaCache.id == cache_id))
        return res.scalar_one_or_none()


# === USER REQUEST HISTORY ===

async def log_user_request(
    user_id: int,
    kind: str = "message",
    input_text: str | None = None,
    url: str | None = None,
    media_type: str | None = None,
    title: str | None = None,
    cache_hit: bool = False,
    cache_id: int | None = None,
) -> None:
    async with session_maker() as session:
        async with session.begin():
            session.add(
                UserRequest(
                    user_id=user_id,
                    kind=kind,
                    input_text=input_text,
                    url=url,
                    media_type=media_type,
                    title=title,
                    cache_hit=cache_hit,
                    cache_id=cache_id,
                )
            )


async def get_user_requests(user_id: int, limit: int = 10, offset: int = 0) -> list[UserRequest]:
    async with session_maker() as session:
        res = await session.execute(
            select(UserRequest)
            .where(UserRequest.user_id == user_id)
            .order_by(UserRequest.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(res.scalars().all())


async def count_user_requests(user_id: int) -> int:
    async with session_maker() as session:
        res = await session.execute(select(func.count()).select_from(UserRequest).where(UserRequest.user_id == user_id))
        return int(res.scalar() or 0)


async def get_user_request_by_id(req_id: int) -> UserRequest | None:
    async with session_maker() as session:
        res = await session.execute(select(UserRequest).where(UserRequest.id == req_id))
        return res.scalar_one_or_none()

async def increment_request_count(user_id: int):
    """Увеличивает счетчик запросов пользователя."""
    async with session_maker() as session:
        async with session.begin():
            user = await session.execute(select(User).where(User.id == user_id))
            u = user.scalar_one_or_none()
            if u:
                u.request_count += 1
                u.last_seen = datetime.now()

# === УПРАВЛЕНИЕ БАНАМИ ===

async def ban_user(user_id: int, reason: str = "Admin ban") -> bool:
    """Банит пользователя."""
    async with session_maker() as session:
        async with session.begin():
            stmt = update(User).where(User.id == user_id).values(
                is_banned=True,
                ban_reason=reason,
                is_active=False
            )
            result = await session.execute(stmt)
            return result.rowcount > 0

async def unban_user(user_id: int) -> bool:
    """Разбанивает пользователя."""
    async with session_maker() as session:
        async with session.begin():
            stmt = update(User).where(User.id == user_id).values(
                is_banned=False,
                ban_reason=None,
                is_active=True
            )
            result = await session.execute(stmt)
            return result.rowcount > 0

async def is_user_banned(user_id: int) -> bool:
    """Проверяет, заблокирован ли пользователь."""
    user = await get_user(user_id)
    return user and user.is_banned

# === УПРАВЛЕНИЕ ЯЗЫКОМ ===

async def set_user_language(user_id: int, language_code: str):
    """Устанавливает язык пользователя."""
    async with session_maker() as session:
        async with session.begin():
            stmt = update(User).where(User.id == user_id).values(language=language_code)
            await session.execute(stmt)

async def get_user_language(user_id: int) -> str:
    """Получает язык пользователя."""
    user = await get_user(user_id)
    return user.language if user else "en"

# === УПРАВЛЕНИЕ КУКИ (Персональные) ===

async def save_user_cookie(user_id: int, platform: str, cookie_data: str):
    """Сохраняет куки пользователя для конкретной платформы."""
    async with session_maker() as session:
        async with session.begin():
            user = await session.execute(select(User).where(User.id == user_id))
            u = user.scalar_one_or_none()
            if u:
                if platform.lower() == "youtube":
                    u.cookies_youtube = cookie_data
                elif platform.lower() == "tiktok":
                    u.cookies_tiktok = cookie_data
                elif platform.lower() == "vk":
                    u.cookies_vk = cookie_data

async def get_user_cookie(user_id: int, platform: str) -> str | None:
    """Получает куки пользователя для конкретной платформы."""
    user = await get_user(user_id)
    if not user:
        return None
    
    if platform.lower() == "youtube":
        return user.cookies_youtube
    elif platform.lower() == "tiktok":
        return user.cookies_tiktok
    elif platform.lower() == "vk":
        return user.cookies_vk
    return None

# === УПРАВЛЕНИЕ ГЛОБАЛЬНЫМИ КУКИ ===

async def save_global_cookie(platform: str, cookie_data: str):
    """Сохраняет глобальные куки для платформы (для админов)."""
    async with session_maker() as session:
        async with session.begin():
            # Проверяем, есть ли уже куки для этой платформы
            existing = await session.execute(
                select(GlobalCookies).where(GlobalCookies.platform == platform.lower())
            )
            cookies = existing.scalar_one_or_none()
            
            if cookies:
                cookies.cookies_data = cookie_data
                cookies.updated_at = datetime.now()
            else:
                new_cookies = GlobalCookies(
                    platform=platform.lower(),
                    cookies_data=cookie_data
                )
                session.add(new_cookies)

async def get_global_cookie(platform: str) -> str | None:
    """Получает глобальные куки для платформы."""
    async with session_maker() as session:
        result = await session.execute(
            select(GlobalCookies).where(GlobalCookies.platform == platform.lower())
        )
        cookies = result.scalar_one_or_none()
        return cookies.cookies_data if cookies else None

# === СИСТЕМНЫЕ ПЕРЕМЕННЫЕ ===

async def get_system_value(key: str) -> str | None:
    """Получает системную переменную."""
    async with session_maker() as session:
        result = await session.execute(
            select(SystemSettings).where(SystemSettings.key == key)
        )
        setting = result.scalar_one_or_none()
        return setting.value if setting else None

async def set_system_value(key: str, value: str):
    """Устанавливает системную переменную."""
    async with session_maker() as session:
        async with session.begin():
            existing = await session.execute(
                select(SystemSettings).where(SystemSettings.key == key)
            )
            setting = existing.scalar_one_or_none()
            
            if setting:
                setting.value = value
                setting.updated_at = datetime.now()
            else:
                new_setting = SystemSettings(key=key, value=value)
                session.add(new_setting)

# ===LASTFM ===

async def set_lastfm_username(user_id: int, lastfm_username: str):
    """Привязывает Last.FM аккаунт к пользователю."""
    async with session_maker() as session:
        async with session.begin():
            stmt = update(User).where(User.id == user_id).values(lastfm_username=lastfm_username)
            await session.execute(stmt)

async def get_lastfm_username(user_id: int) -> str | None:
    """Получает привязанный Last.FM аккаунт."""
    user = await get_user(user_id)
    return user.lastfm_username if user else None

# === MODULE STATUS ===

async def get_module_status(module_name: str) -> bool:
    """Проверяет статус модуля (всегда возвращает True по умолчанию)"""
    value = await get_system_value(f"module_{module_name}")
    if value is None:
        return True  # Default is enabled
    return value.lower() in ("true", "1", "yes")

async def set_module_status(module_name: str, enabled: bool):
    """Устанавливает статус модуля"""
    await set_system_value(f"module_{module_name}", "true" if enabled else "false")