from sqlalchemy import select, update, func
from sqlalchemy import delete
from sqlalchemy.dialects.sqlite import insert
from datetime import datetime, timedelta
from services.database.core import session_maker 
from services.database.models import User, SystemSettings, GlobalCookies

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