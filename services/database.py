import aiosqlite
from datetime import datetime

DB_NAME = "users.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # 1. Создаем таблицу пользователей (если нет)
        # Добавили is_active по умолчанию
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
        
        # 2. Создаем таблицу для кэша File ID (для Inline режима)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS file_cache (
                url TEXT PRIMARY KEY,
                file_id TEXT,
                media_type TEXT,
                created_at TEXT
            )
        """)
        
        # 3. МИГРАЦИИ (обновляем старые базы без потери данных)
        
        # Миграция 1: ban_reason
        try:
            await db.execute("ALTER TABLE users ADD COLUMN ban_reason TEXT DEFAULT NULL")
        except Exception:
            pass # Колонка уже есть
            
        # Миграция 2: is_active
        try:
            await db.execute("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1")
        except Exception:
            pass # Колонка уже есть
            
        await db.commit()

async def add_or_update_user(user_id, username):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT is_banned, ban_reason FROM users WHERE user_id = ?", (user_id,))
        data = await cursor.fetchone()
        
        if data:
            is_banned = data[0]
            ban_reason = data[1]
            # Обновляем last_seen и ставим is_active = 1 (раз юзер пишет, значит он активен)
            await db.execute("""
                UPDATE users 
                SET last_seen = ?, username = ?, is_active = 1 
                WHERE user_id = ?
            """, (now, username, user_id))
            await db.commit()
            return False, bool(is_banned), ban_reason
        else:
            # Новый юзер
            await db.execute(
                "INSERT INTO users (user_id, username, first_seen, last_seen, is_banned, ban_reason, is_active) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, username, now, now, False, None, 1)
            )
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
        # Сортируем: сначала новые
        cursor = await db.execute("SELECT * FROM users ORDER BY first_seen DESC")
        return await cursor.fetchall()

async def set_ban_status(user_id, is_banned: bool, reason: str = None):
    async with aiosqlite.connect(DB_NAME) as db:
        if is_banned:
            await db.execute("UPDATE users SET is_banned = ?, ban_reason = ? WHERE user_id = ?", (1, reason, user_id))
        else:
            # При разбане очищаем причину
            await db.execute("UPDATE users SET is_banned = ?, ban_reason = NULL WHERE user_id = ?", (0, user_id))
        await db.commit()

# --- ФУНКЦИИ ДЛЯ INLINE КЭША ---

async def get_cached_file(url):
    """Ищет файл в базе по URL"""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT file_id, media_type FROM file_cache WHERE url = ?", (url,))
        return await cursor.fetchone()

async def save_cached_file(url, file_id, media_type):
    """Сохраняет file_id в базу"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_NAME) as db:
        # INSERT OR REPLACE обновит запись, если такой URL уже был
        await db.execute(
            "INSERT OR REPLACE INTO file_cache (url, file_id, media_type, created_at) VALUES (?, ?, ?, ?)",
            (url, file_id, media_type, now)
        )
        await db.commit()

async def set_user_active(user_id: int, is_active: bool):
    """Меняет статус активности пользователя (заблокировал бота или нет)"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE users SET is_active = ? WHERE user_id = ?", 
            (1 if is_active else 0, user_id)
        )
        await db.commit()

