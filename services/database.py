import aiosqlite
from datetime import datetime

DB_NAME = "users.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # 1. Создаем таблицу (если нет)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_seen TEXT,
                last_seen TEXT,
                is_banned BOOLEAN DEFAULT 0,
                ban_reason TEXT DEFAULT NULL
            )
        """)
        
        # 2. МИГРАЦИЯ: Пытаемся добавить колонку ban_reason, если её нет (для старых баз)
        try:
            await db.execute("ALTER TABLE users ADD COLUMN ban_reason TEXT DEFAULT NULL")
            await db.commit()
            print("🔧 База данных обновлена: добавлена колонка ban_reason")
        except Exception:
            # Если колонка уже есть, будет ошибка - игнорируем её
            pass
            
        await db.commit()

async def add_or_update_user(user_id, username):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT is_banned, ban_reason FROM users WHERE user_id = ?", (user_id,))
        data = await cursor.fetchone()
        
        if data:
            is_banned = data[0]
            ban_reason = data[1]
            await db.execute("UPDATE users SET last_seen = ?, username = ? WHERE user_id = ?", (now, username, user_id))
            await db.commit()
            return False, bool(is_banned), ban_reason
        else:
            await db.execute(
                "INSERT INTO users (user_id, username, first_seen, last_seen, is_banned, ban_reason) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, username, now, now, False, None)
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
        cursor = await db.execute("SELECT * FROM users ORDER BY first_seen ASC")
        return await cursor.fetchall()

async def set_ban_status(user_id, is_banned: bool, reason: str = None):
    async with aiosqlite.connect(DB_NAME) as db:
        if is_banned:
            await db.execute("UPDATE users SET is_banned = ?, ban_reason = ? WHERE user_id = ?", (1, reason, user_id))
        else:
            # При разбане очищаем причину
            await db.execute("UPDATE users SET is_banned = ?, ban_reason = NULL WHERE user_id = ?", (0, user_id))
        await db.commit()