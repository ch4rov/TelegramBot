import aiosqlite
import os
import re
import json
from datetime import datetime
import settings

DB_NAME = "users.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await init_logs_table()
        # Таблица пользователей
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT,
            first_seen TEXT, last_seen TEXT, is_banned BOOLEAN DEFAULT 0,
            ban_reason TEXT DEFAULT NULL, is_active BOOLEAN DEFAULT 1,
            lastfm_username TEXT DEFAULT NULL, language TEXT DEFAULT 'en'
        )""")
        
        # Таблица полных логов сообщений
        await db.execute("""CREATE TABLE IF NOT EXISTS message_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT,
            event_type TEXT, content TEXT, message_id INTEGER, raw_data TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        
        # Старая таблица логов (для совместимости, если нужна)
        await db.execute("""CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT,
            action TEXT, details TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")

        await db.execute("""CREATE TABLE IF NOT EXISTS file_cache (
            url TEXT PRIMARY KEY, file_id TEXT, media_type TEXT, created_at TEXT, title TEXT
        )""")
        
        # Таблица куки с поддержкой сервисов
        await db.execute("""CREATE TABLE IF NOT EXISTS user_cookies (
            user_id INTEGER, service_name TEXT, cookie_data TEXT, updated_at TEXT,
            PRIMARY KEY (user_id, service_name)
        )""")
        
        await db.execute("CREATE TABLE IF NOT EXISTS system_config (key TEXT PRIMARY KEY, value TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS modules_config (module_name TEXT PRIMARY KEY, is_enabled BOOLEAN DEFAULT 1)")
        
        # Миграции
        try: await db.execute("ALTER TABLE users ADD COLUMN full_name TEXT DEFAULT NULL")
        except: pass
        try: await db.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'en'")
        except: pass
        try: await db.execute("ALTER TABLE user_cookies ADD COLUMN service_name TEXT DEFAULT 'default'")
        except: pass
        
        await db.commit()

# --- ЛОГИРОВАНИЕ (ИСПРАВЛЕНО ИМЯ) ---

async def add_message_log(user_id, username, event_type, content, message_id=None, raw_data=None):
    """Основная функция записи лога (вызывается из logger_system)"""
    try:
        raw_str = json.dumps(raw_data, default=str) if raw_data else "{}"
        async with aiosqlite.connect(DB_NAME) as db:
            # Пишем в основную таблицу
            await db.execute(
                "INSERT INTO message_logs (user_id, username, event_type, content, message_id, raw_data) VALUES (?, ?, ?, ?, ?, ?)", 
                (user_id, username, event_type, content, message_id, raw_str)
            )
            # Дублируем в activity_logs для старой статистики (пока веб-панель её использует)
            await db.execute(
                "INSERT INTO activity_logs (user_id, username, action, details) VALUES (?, ?, ?, ?)", 
                (user_id, username, event_type, content)
            )
            await db.commit()
    except Exception as e: print(f"DB Log Error: {e}")

async def log_activity(user_id, username, action, details):
    """Алиас для старых вызовов (например, из веб-панели)"""
    await add_message_log(user_id, username, action, details, None, None)

# --- USERS ---

async def add_or_update_user(user_id, username, full_name=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT is_banned, ban_reason, language FROM users WHERE user_id = ?", (user_id,))
        data = await cursor.fetchone()
        if data:
            await db.execute("UPDATE users SET last_seen = ?, username = ?, full_name = ?, is_active = 1 WHERE user_id = ?", (now, username, full_name, user_id))
            await db.commit()
            return False, bool(data[0]), data[1], data[2] or 'en'
        else:
            await db.execute("INSERT INTO users (user_id, username, full_name, first_seen, last_seen, is_banned, language) VALUES (?, ?, ?, ?, ?, 0, 'en')", (user_id, username, full_name, now, now))
            await db.commit()
            return True, False, None, 'en'

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
        sql = "SELECT u.*, (SELECT COUNT(*) FROM message_logs l WHERE l.user_id = u.user_id) as req_count FROM users u"
        args = []
        if query:
            sql += " WHERE u.username LIKE ? OR u.full_name LIKE ? OR u.user_id LIKE ?"
            q = f"%{query}%"
            args = [q, q, q]
        cursor = await db.execute(sql, args)
        return [dict(u) for u in await cursor.fetchall()]

async def get_users_with_stats(sort_by='last_seen'):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        # Считаем по message_logs
        query = "SELECT u.*, (SELECT COUNT(*) FROM message_logs l WHERE l.user_id = u.user_id) as req_count FROM users u"
        rows = await (await db.execute(query)).fetchall()
        users = [dict(u) for u in rows]
        reverse = True
        key = lambda x: x['last_seen'] or ""
        if sort_by == 'first_seen': key = lambda x: x['first_seen'] or ""
        elif sort_by == 'requests': key = lambda x: x['req_count']
        return sorted(users, key=key, reverse=reverse)

# --- GET LOGS (Используем message_logs для админки) ---

async def get_user_logs(user_id, limit=None, search=None, action_filter=None):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        # Мапим новые поля (event_type -> action, content -> details) для совместимости с шаблоном
        sql = "SELECT id, user_id, username, event_type as action, content as details, timestamp FROM message_logs WHERE user_id = ?"
        args = [user_id]
        if search:
            sql += " AND content LIKE ?"
            args.append(f"%{search}%")
        if action_filter and action_filter != 'ALL':
            sql += " AND event_type = ?"
            args.append(action_filter)
        sql += " ORDER BY id DESC"
        if limit:
            sql += " LIMIT ?"
            args.append(limit)
        cursor = await db.execute(sql, tuple(args))
        rows = await cursor.fetchall()
        return list(reversed(rows))

async def delete_user_logs(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM message_logs WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM activity_logs WHERE user_id = ?", (user_id,))
        await db.commit()

async def get_global_stats():
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            r1 = await db.execute("SELECT COUNT(*) FROM message_logs")
            t = (await r1.fetchone())[0] or 0
            r2 = await db.execute("SELECT COUNT(*) FROM message_logs WHERE event_type = 'MSG_SENT'")
            s = (await r2.fetchone())[0] or 0
            return t, s
        except: return 0, 0

async def get_stats_period(period_sql): return 0,0
async def import_legacy_logs(): return 0

# --- OTHER ---

async def set_ban_status(user_id, is_banned, reason=None):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET is_banned = ?, ban_reason = ? WHERE user_id = ?", (1 if is_banned else 0, reason, user_id)); await db.commit()
async def web_ban_user(u, r): await set_ban_status(u, True, r)
async def web_unban_user(u): await set_ban_status(u, False)

async def get_module_status(m):
    async with aiosqlite.connect(DB_NAME) as db:
        r = await (await db.execute("SELECT is_enabled FROM modules_config WHERE module_name=?", (m,))).fetchone(); return bool(r[0]) if r else True
async def set_module_status(m, s):
    async with aiosqlite.connect(DB_NAME) as db: await db.execute("INSERT OR REPLACE INTO modules_config (module_name, is_enabled) VALUES (?, ?)", (m, 1 if s else 0)); await db.commit()

async def get_system_value(k):
    async with aiosqlite.connect(DB_NAME) as db: r = await (await db.execute("SELECT value FROM system_config WHERE key=?", (k,))).fetchone(); return r[0] if r else None
async def set_system_value(k, v):
    async with aiosqlite.connect(DB_NAME) as db: await db.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES (?, ?)", (k, v)); await db.commit()
        
async def clear_file_cache():
    async with aiosqlite.connect(DB_NAME) as db: await db.execute("DELETE FROM file_cache"); await db.commit()
async def clear_cache_older_than(minutes):
    async with aiosqlite.connect(DB_NAME) as db: await db.execute(f"DELETE FROM file_cache WHERE created_at < datetime('now', '-{minutes} minutes')"); await db.commit()

async def get_cached_file(url):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row; r = await (await db.execute("SELECT * FROM file_cache WHERE url=?", (url,))).fetchone(); return dict(r) if r else None
async def save_cached_file(url, file_id, media_type, title=None):
    async with aiosqlite.connect(DB_NAME) as db: await db.execute("INSERT OR REPLACE INTO file_cache (url, file_id, media_type, created_at, title) VALUES (?, ?, ?, datetime('now'), ?)", (url, file_id, media_type, title)); await db.commit()

# --- COOKIES (С SERVICE_NAME) ---

async def save_user_cookie(user_id, cookie_content, service_name='default'):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO user_cookies (user_id, service_name, cookie_data, updated_at) VALUES (?, ?, ?, ?)", (user_id, service_name, cookie_content, now)); await db.commit()

async def get_user_cookie(user_id, service_name='default'):
    async with aiosqlite.connect(DB_NAME) as db:
        # Пробуем найти конкретный сервис, если нет - дефолт
        r = await (await db.execute("SELECT cookie_data FROM user_cookies WHERE user_id=? AND service_name=?", (user_id, service_name))).fetchone()
        if r: return r[0]
        # Fallback
        r = await (await db.execute("SELECT cookie_data FROM user_cookies WHERE user_id=? AND service_name='default'", (user_id,))).fetchone()
        return r[0] if r else None

async def set_lastfm_username(u, n):
    async with aiosqlite.connect(DB_NAME) as db: await db.execute("UPDATE users SET lastfm_username=? WHERE user_id=?", (n, u)); await db.commit()
async def get_user_language(u):
    async with aiosqlite.connect(DB_NAME) as db:
        r = await (await db.execute("SELECT language FROM users WHERE user_id=?", (u,))).fetchone(); return r[0] if r else 'en'
async def set_user_language(u, l):
    async with aiosqlite.connect(DB_NAME) as db: await db.execute("UPDATE users SET language=? WHERE user_id=?", (l, u)); await db.commit()

async def init_logs_table():
    async with aiosqlite.connect('users.db') as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS message_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                username TEXT,
                content TEXT,
                event_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Миграция: Добавляем content и event_type
        columns_to_check = [
            ("chat_id", "INTEGER"),
            ("content", "TEXT"),       # <--- Исправлено
            ("event_type", "TEXT"),
            ("username", "TEXT"),
            ("message_text", "TEXT")   # Оставляем для совместимости со старыми записями
        ]

        for col_name, col_type in columns_to_check:
            try:
                await db.execute(f"ALTER TABLE message_logs ADD COLUMN {col_name} {col_type}")
            except Exception:
                pass 

        await db.commit()

async def log_message_to_db(user_id, chat_id, username, text, msg_type="TEXT"):
    try:
        async with aiosqlite.connect('users.db') as db:
            # Пишем и в content (новое), и в message_text (старое, на всякий случай), или просто используем content
            await db.execute("""
                INSERT INTO message_logs (user_id, chat_id, username, content, event_type)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, chat_id, username, text, msg_type))
            await db.commit()
    except Exception as e:
        print(f"DB Log Error: {e}")