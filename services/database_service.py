import aiosqlite
from datetime import datetime

DB_NAME = "users.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # 1. Таблица пользователей
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_seen TEXT,
                last_seen TEXT,
                is_banned BOOLEAN DEFAULT 0,
                ban_reason TEXT DEFAULT NULL,
                is_active BOOLEAN DEFAULT 1
            )
        """)
        
        # 2. Таблица кэша (Обновленная структура)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS file_cache (
                url TEXT PRIMARY KEY,
                file_id TEXT,
                media_type TEXT,
                created_at TEXT,
                title TEXT  -- Новая колонка для названия
            )
        """)
        
        # --- МИГРАЦИИ ---
        try: await db.execute("ALTER TABLE users ADD COLUMN ban_reason TEXT DEFAULT NULL")
        except: pass
        try: await db.execute("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1")
        except: pass
        
        # Миграция для кэша: добавляем title, если его нет
        try: 
            await db.execute("ALTER TABLE file_cache ADD COLUMN title TEXT DEFAULT NULL")
        except: pass
            
        await db.commit()

# ... (функции пользователей add_or_update_user, get_user, get_all_users, set_ban_status остаются без изменений) ...
# ВСТАВЬ СЮДА СТАРЫЕ ФУНКЦИИ ПОЛЬЗОВАТЕЛЕЙ, ОНИ НЕ МЕНЯЛИСЬ
# Я их сократил для краткости ответа, но в файле они должны быть!

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
            await db.execute("INSERT INTO users (user_id, username, first_seen, last_seen, is_banned, ban_reason, is_active) VALUES (?, ?, ?, ?, ?, ?, ?)", (user_id, username, now, now, False, None, 1))
            await db.commit()
            return True, False, None

async def get_user(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return await cursor.fetchone()

async def get_all_users():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users ORDER BY first_seen DESC")
        return await cursor.fetchall()

async def set_ban_status(user_id, is_banned: bool, reason: str = None):
    async with aiosqlite.connect(DB_NAME) as db:
        if is_banned: await db.execute("UPDATE users SET is_banned = ?, ban_reason = ? WHERE user_id = ?", (1, reason, user_id))
        else: await db.execute("UPDATE users SET is_banned = ?, ban_reason = NULL WHERE user_id = ?", (0, user_id))
        await db.commit()

# --- ОБНОВЛЕННЫЕ ФУНКЦИИ КЭША ---

async def get_cached_file(url):
    """Возвращает file_id, media_type и title"""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        # Теперь забираем еще и title
        cursor = await db.execute("SELECT file_id, media_type, title FROM file_cache WHERE url = ?", (url,))
        return await cursor.fetchone()

async def save_cached_file(url, file_id, media_type, title=None):
    """Сохраняет файл вместе с названием"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR REPLACE INTO file_cache (url, file_id, media_type, created_at, title) VALUES (?, ?, ?, ?, ?)",
            (url, file_id, media_type, now, title)
        )
        await db.commit()