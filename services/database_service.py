import aiosqlite
import os
import json
from datetime import datetime
import settings

DB_NAME = "users.db"

# --- ИНИЦИАЛИЗАЦИЯ ---

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            first_seen TEXT,
            last_seen TEXT,
            is_banned BOOLEAN DEFAULT 0,
            ban_reason TEXT DEFAULT NULL,
            is_active BOOLEAN DEFAULT 1,
            lastfm_username TEXT DEFAULT NULL,
            language TEXT DEFAULT 'en',
            req_count INTEGER DEFAULT 0
        )""")
        
        await db.execute("""CREATE TABLE IF NOT EXISTS message_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            chat_id INTEGER,
            message_id INTEGER,
            username TEXT,
            event_type TEXT,
            content TEXT,
            raw_data TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        
        await db.execute("""CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            action TEXT,
            details TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")

        await db.execute("""CREATE TABLE IF NOT EXISTS file_cache (
            url TEXT PRIMARY KEY,
            file_id TEXT,
            media_type TEXT,
            created_at TEXT,
            title TEXT
        )""")
        
        await db.execute("""CREATE TABLE IF NOT EXISTS user_cookies (
            user_id INTEGER,
            service_name TEXT,
            cookie_data TEXT,
            updated_at TEXT,
            PRIMARY KEY (user_id, service_name)
        )""")
        
        await db.execute("CREATE TABLE IF NOT EXISTS system_config (key TEXT PRIMARY KEY, value TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS modules_config (module_name TEXT PRIMARY KEY, is_enabled BOOLEAN DEFAULT 1)")
        
        # --- МИГРАЦИИ (Добавление колонок, если их нет) ---
        columns_to_check = [
            ("users", "full_name", "TEXT DEFAULT NULL"),
            ("users", "language", "TEXT DEFAULT 'en'"),
            ("users", "req_count", "INTEGER DEFAULT 0"),
            ("message_logs", "chat_id", "INTEGER"),
            ("message_logs", "message_id", "INTEGER"),
            ("message_logs", "content", "TEXT"),
            ("message_logs", "event_type", "TEXT"),
            ("user_cookies", "service_name", "TEXT DEFAULT 'default'")
        ]

        for table, col, type_def in columns_to_check:
            try:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {type_def}")
            except Exception:
                pass

        await db.commit()

async def init_logs_table():
    # Эта функция теперь пустая, так как всё делается в init_db
    # Оставлена для совместимости, если где-то вызывается
    pass

# --- ЛОГИРОВАНИЕ ---

async def log_message_to_db(user_id, chat_id, message_id, username, text, msg_type="TEXT"):
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("""
                INSERT INTO message_logs (user_id, chat_id, message_id, username, content, event_type)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, chat_id, message_id, username, text, msg_type))
            await db.commit()
    except Exception as e:
        print(f"DB Log Error: {e}")

# АЛИАС: Для совместимости со старым logger_system.py
async def add_message_log(user_id, username, event_type, content, message_id=None, raw_data=None):
    await log_message_to_db(user_id, 0, message_id, username, content, event_type)

async def log_activity(user_id, username, action, details):
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                "INSERT INTO activity_logs (user_id, username, action, details) VALUES (?, ?, ?, ?)", 
                (user_id, username, action, details)
            )
            await db.commit()
    except Exception as e:
        print(f"Activity Log Error: {e}")

# --- ПОЛЬЗОВАТЕЛИ ---

async def add_or_update_user(user_id, username, full_name=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT is_banned, ban_reason, language FROM users WHERE user_id = ?", (user_id,))
        data = await cursor.fetchone()
        
        if data:
            await db.execute("""
                UPDATE users SET last_seen = ?, username = ?, full_name = ?, is_active = 1 
                WHERE user_id = ?
            """, (now, username, full_name, user_id))
            await db.execute("UPDATE users SET req_count = req_count + 1 WHERE user_id = ?", (user_id,))
            await db.commit()
            return False, bool(data[0]), data[1], data[2] or 'en'
        else:
            await db.execute("""
                INSERT INTO users (user_id, username, full_name, first_seen, last_seen, is_banned, language, req_count) 
                VALUES (?, ?, ?, ?, ?, 0, 'en', 1)
            """, (user_id, username, full_name, now, now))
            await db.commit()
            return True, False, None, 'en'

# АЛИАС
async def add_user(user_id, username, full_name):
    await add_or_update_user(user_id, username, full_name)

async def update_user_activity(user_id, username, full_name):
    await add_or_update_user(user_id, username, full_name)

async def get_user(uid):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        r = await (await db.execute("SELECT * FROM users WHERE user_id = ?", (uid,))).fetchone()
        return dict(r) if r else None

async def get_all_users():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        return [dict(r) for r in await (await db.execute("SELECT * FROM users ORDER BY first_seen DESC")).fetchall()]

async def get_users_filtered(query=None):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        sql = "SELECT * FROM users"
        args = []
        if query:
            sql += " WHERE username LIKE ? OR full_name LIKE ? OR user_id LIKE ?"
            q = f"%{query}%"
            args = [q, q, q]
        cursor = await db.execute(sql, args)
        return [dict(u) for u in await cursor.fetchall()]

# --- СТАТИСТИКА И ЛОГИ ---

async def get_user_logs(user_id, limit=None, search=None):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        sql = "SELECT event_type as action, content as details, timestamp FROM message_logs WHERE user_id = ?"
        args = [user_id]
        if search:
            sql += " AND content LIKE ?"
            args.append(f"%{search}%")
        sql += " ORDER BY id DESC"
        if limit:
            sql += " LIMIT ?"
            args.append(limit)
        
        cursor = await db.execute(sql, tuple(args))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

async def delete_user_logs(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM message_logs WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM activity_logs WHERE user_id = ?", (user_id,))
        await db.commit()

async def get_global_stats():
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            r1 = await db.execute("SELECT SUM(req_count) FROM users")
            total = (await r1.fetchone())[0] or 0
            return total, total
        except: return 0, 0

# ВОТ ЭТА ФУНКЦИЯ БЫЛА ПРОПУЩЕНА
async def get_stats_period(period_name):
    # Заглушка, возвращает 0,0, чтобы не ломать дашборд
    return 0, 0

async def import_legacy_logs():
    return 0 

# --- БАНЫ ---

async def set_ban_status(user_id, is_banned, reason=None):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET is_banned = ?, ban_reason = ? WHERE user_id = ?", (1 if is_banned else 0, reason, user_id))
        await db.commit()

async def web_ban_user(u, r): await set_ban_status(u, True, r)
async def web_unban_user(u): await set_ban_status(u, False)

# --- КОНФИГ ---

async def get_module_status(m):
    async with aiosqlite.connect(DB_NAME) as db:
        r = await (await db.execute("SELECT is_enabled FROM modules_config WHERE module_name=?", (m,))).fetchone()
        return bool(r[0]) if r else True

async def set_module_status(m, s):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO modules_config (module_name, is_enabled) VALUES (?, ?)", (m, 1 if s else 0))
        await db.commit()

async def get_system_value(k):
    async with aiosqlite.connect(DB_NAME) as db:
        r = await (await db.execute("SELECT value FROM system_config WHERE key=?", (k,))).fetchone()
        return r[0] if r else None

async def set_system_value(k, v):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES (?, ?)", (k, v))
        await db.commit()

# --- КЭШ ---

async def clear_file_cache():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM file_cache")
        await db.commit()

async def get_cached_file(url):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        r = await (await db.execute("SELECT * FROM file_cache WHERE url=?", (url,))).fetchone()
        return dict(r) if r else None

async def save_cached_file(url, file_id, media_type, title=None):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO file_cache (url, file_id, media_type, created_at, title) VALUES (?, ?, ?, datetime('now'), ?)", (url, file_id, media_type, title))
        await db.commit()

# --- КУКИ И ЯЗЫК ---

async def save_user_cookie(user_id, cookie_content, service_name='default'):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO user_cookies (user_id, service_name, cookie_data, updated_at) VALUES (?, ?, ?, ?)", (user_id, service_name, cookie_content, now))
        await db.commit()

async def get_user_cookie(user_id, service_name='default'):
    async with aiosqlite.connect(DB_NAME) as db:
        r = await (await db.execute("SELECT cookie_data FROM user_cookies WHERE user_id=? AND service_name=?", (user_id, service_name))).fetchone()
        if r: return r[0]
        r = await (await db.execute("SELECT cookie_data FROM user_cookies WHERE user_id=? AND service_name='default'", (user_id,))).fetchone()
        return r[0] if r else None

async def set_lastfm_username(u, n):
    async with aiosqlite.connect(DB_NAME) as db: await db.execute("UPDATE users SET lastfm_username=? WHERE user_id=?", (n, u)); await db.commit()

async def get_user_language(u):
    async with aiosqlite.connect(DB_NAME) as db:
        r = await (await db.execute("SELECT language FROM users WHERE user_id=?", (u,))).fetchone()
        return r[0] if r else 'en'

async def set_user_language(u, l):
    async with aiosqlite.connect(DB_NAME) as db: await db.execute("UPDATE users SET language=? WHERE user_id=?", (l, u)); await db.commit()