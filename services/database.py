import aiosqlite
from datetime import datetime

DB_NAME = "users.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_seen TEXT,
                last_seen TEXT,
                is_banned BOOLEAN DEFAULT 0
            )
        """)
        await db.commit()

async def add_or_update_user(user_id, username):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_NAME) as db:
        # Проверяем, есть ли такой юзер
        cursor = await db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        data = await cursor.fetchone()
        
        if not data:
            # Новый пользователь
            await db.execute(
                "INSERT INTO users (user_id, username, first_seen, last_seen, is_banned) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, now, now, False)
            )
            return True # Вернем True, если это новичок
        else:
            # Старый пользователь - обновляем время последнего входа
            await db.execute("UPDATE users SET last_seen = ?, username = ? WHERE user_id = ?", (now, username, user_id))
            return False

async def get_all_users():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users ORDER BY first_seen ASC")
        return await cursor.fetchall()

async def check_ban(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
        result = await cursor.fetchone()
        return result[0] if result else False # Возвращает 1 (True) или 0 (False)

async def set_ban_status(user_id, is_banned: bool):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (is_banned, user_id))
        await db.commit()