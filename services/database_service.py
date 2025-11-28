import aiosqlite
from datetime import datetime
import settings

# УБРАЛИ ИМПОРТ verbose_logger

DB_NAME = "users.db"

async def init_db():
    # print(f"Инициализация БД: {DB_NAME}") # Можно убрать, чтобы не спамило
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_seen TEXT,
                last_seen TEXT,
                is_banned BOOLEAN DEFAULT 0,
                ban_reason TEXT DEFAULT NULL,
                is_active BOOLEAN DEFAULT 1,
                lastfm_username TEXT DEFAULT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS file_cache (
                url TEXT PRIMARY KEY,
                file_id TEXT,
                media_type TEXT,
                created_at TEXT,
                title TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_cookies (
                user_id INTEGER PRIMARY KEY,
                cookie_data TEXT,
                updated_at TEXT
            )
        """)
        await db.execute("CREATE TABLE IF NOT EXISTS system_config (key TEXT PRIMARY KEY, value TEXT)")
        
        # Миграции
        try: await db.execute("ALTER TABLE users ADD COLUMN ban_reason TEXT DEFAULT NULL")
        except: pass
        try: await db.execute("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1")
        except: pass
        try: await db.execute("ALTER TABLE users ADD COLUMN lastfm_username TEXT DEFAULT NULL")
        except: pass
        try: await db.execute("ALTER TABLE file_cache ADD COLUMN title TEXT DEFAULT NULL")
        except: pass
        
        await db.commit()

async def add_or_update_user(user_id, username):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT is_banned, ban_reason FROM users WHERE user_id = ?", (user_id,))
        data = await cursor.fetchone()
        
        if data:
            is_banned, ban_reason = data[0], data[1]
            await db.execute("UPDATE users SET last_seen = ?, username = ?, is_active = 1 WHERE user_id = ?", (now, username, user_id))
            await db.commit()
            return False, bool(is_banned), ban_reason
        else:
            await db.execute(
                "INSERT INTO users (user_id, username, first_seen, last_seen, is_banned, ban_reason, is_active) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, username, now, now, False, None, 1)
            )
            await db.commit()
            print(f"➕ Новый юзер: {user_id} ({username})")
            return True, False, None

async def set_lastfm_username(user_id, lfm_user):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET lastfm_username = ? WHERE user_id = ?", (lfm_user, int(user_id)))
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row 
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (int(user_id),))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def get_all_users():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users ORDER BY first_seen DESC")
        return await cursor.fetchall()

async def set_ban_status(user_id, is_banned: bool, reason: str = None):
    async with aiosqlite.connect(DB_NAME) as db:
        if is_banned:
            await db.execute("UPDATE users SET is_banned = ?, ban_reason = ? WHERE user_id = ?", (1, reason, user_id))
        else:
            await db.execute("UPDATE users SET is_banned = ?, ban_reason = NULL WHERE user_id = ?", (0, user_id))
        await db.commit()

async def set_user_active(user_id: int, is_active: bool):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET is_active = ? WHERE user_id = ?", (1 if is_active else 0, user_id))
        await db.commit()

# --- КЭШ ---
async def get_cached_file(url):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT file_id, media_type, title FROM file_cache WHERE url = ?", (url,))
        row = await cursor.fetchone()
        if row:
            print(f"♻️ Кэш найден: {url}")
            return dict(row)
        return None

async def save_cached_file(url, file_id, media_type, title=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO file_cache (url, file_id, media_type, created_at, title) VALUES (?, ?, ?, ?, ?)", (url, file_id, media_type, now, title))
        await db.commit()

# --- COOKIES ---
async def save_user_cookie(user_id, cookie_content):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO user_cookies (user_id, cookie_data, updated_at) VALUES (?, ?, ?)", (user_id, cookie_content, now))
        await db.commit()

async def get_user_cookie(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT cookie_data FROM user_cookies WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else None

# --- SYSTEM CONFIG ---
async def get_system_value(key):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT value FROM system_config WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return row[0] if row else None

async def set_system_value(key, value):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES (?, ?)", (key, value))
        await db.commit()
        
async def clear_file_cache():
    """Удаляет все записи из таблицы file_cache"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM file_cache")
        await db.commit()