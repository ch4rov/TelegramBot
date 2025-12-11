import aiosqlite
from datetime import datetime
import settings

DB_NAME = "users.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT, -- <--- НОВАЯ КОЛОНКА
                first_seen TEXT,
                last_seen TEXT,
                is_banned BOOLEAN DEFAULT 0,
                ban_reason TEXT DEFAULT NULL,
                is_active BOOLEAN DEFAULT 1,
                lastfm_username TEXT DEFAULT NULL,
                language TEXT DEFAULT 'en'
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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS modules_config (
                module_name TEXT PRIMARY KEY,
                is_enabled BOOLEAN DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                action TEXT, -- USER_REQ, SUCCESS, FAIL
                details TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Миграции
        try: await db.execute("ALTER TABLE users ADD COLUMN full_name TEXT DEFAULT NULL")
        except: pass
        try: await db.execute("ALTER TABLE users ADD COLUMN ban_reason TEXT DEFAULT NULL")
        except: pass
        try: await db.execute("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1")
        except: pass
        try: await db.execute("ALTER TABLE users ADD COLUMN lastfm_username TEXT DEFAULT NULL")
        except: pass
        try: await db.execute("ALTER TABLE file_cache ADD COLUMN title TEXT DEFAULT NULL")
        except: pass
        try: await db.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'en'")
        except: pass
        
        await db.commit()
async def log_activity(user_id, username, action, details):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO activity_logs (user_id, username, action, details) VALUES (?, ?, ?, ?)",
            (user_id, username, action, details)
        )
        await db.commit()

async def get_stats_period(period_sql):
    """
    period_sql: '-1 hour', '-1 day', '-7 days', '-1 month'
    """
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(f"""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN action = 'SUCCESS' THEN 1 ELSE 0 END) as success
            FROM activity_logs 
            WHERE timestamp >= datetime('now', '{period_sql}')
        """)
        row = await cursor.fetchone()
        total = row[0] or 0
        success = row[1] or 0
        return total, success

async def get_user_logs(user_id, limit=None):
    """
    Возвращает логи. 
    Берет из БД последние N записей (DESC), но возвращает их 
    в хронологическом порядке (ASC) для правильного отображения в чате.
    """
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        
        query = "SELECT * FROM activity_logs WHERE user_id = ? ORDER BY id DESC"
        params = (user_id,)
        
        if limit:
            query += " LIMIT ?"
            params = (user_id, limit)
            
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        
        # Разворачиваем список, чтобы старые были сверху, новые снизу
        return list(reversed(rows))

async def clear_cache_older_than(minutes):
    async with aiosqlite.connect(DB_NAME) as db:
        # SQLite modifier: '-X minutes'
        await db.execute(f"DELETE FROM file_cache WHERE created_at < datetime('now', '-{minutes} minutes')")
        await db.commit()

async def add_or_update_user(user_id, username, full_name=None): # <--- full_name
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT is_banned, ban_reason, language FROM users WHERE user_id = ?", (user_id,))
        data = await cursor.fetchone()
        
        if data:
            is_banned, ban_reason, lang = data[0], data[1], data[2]
            # Обновляем имя и полное имя
            await db.execute("UPDATE users SET last_seen = ?, username = ?, full_name = ?, is_active = 1 WHERE user_id = ?", (now, username, full_name, user_id))
            await db.commit()
            return False, bool(is_banned), ban_reason, lang or 'en'
        else:
            await db.execute(
                "INSERT INTO users (user_id, username, full_name, first_seen, last_seen, is_banned, ban_reason, is_active, language) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, username, full_name, now, now, False, None, 1, 'en')
            )
            await db.commit()
            log_prefix = "👥 [DB] Новая группа" if user_id < 0 else "➕ [DB] Новый юзер"
            print(f"{log_prefix}: {user_id} ({username})")
            return True, False, None, 'en'

async def set_user_language(user_id, lang):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))
        await db.commit()

async def get_user_language(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT language FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else 'en'

# ... (Остальные функции set_lastfm, get_user, set_ban и т.д. остаются без изменений) ...
# Вставьте сюда остальные функции из вашего файла, я их не трогал
async def set_lastfm_username(user_id, lfm_user):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET lastfm_username = ? WHERE user_id = ?", (lfm_user, int(user_id)))
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row; cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (int(user_id),)); row = await cursor.fetchone()
        return dict(row) if row else None

async def get_all_users():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row; cursor = await db.execute("SELECT * FROM users ORDER BY first_seen DESC"); return await cursor.fetchall()

async def set_ban_status(user_id, is_banned: bool, reason: str = None):
    async with aiosqlite.connect(DB_NAME) as db:
        if is_banned: await db.execute("UPDATE users SET is_banned = ?, ban_reason = ? WHERE user_id = ?", (1, reason, user_id))
        else: await db.execute("UPDATE users SET is_banned = ?, ban_reason = NULL WHERE user_id = ?", (0, user_id))
        await db.commit()

async def set_user_active(user_id: int, is_active: bool):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET is_active = ? WHERE user_id = ?", (1 if is_active else 0, user_id))
        await db.commit()

async def get_cached_file(url):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row; cursor = await db.execute("SELECT file_id, media_type, title FROM file_cache WHERE url = ?", (url,)); row = await cursor.fetchone()
        return dict(row) if row else None

async def save_cached_file(url, file_id, media_type, title=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO file_cache (url, file_id, media_type, created_at, title) VALUES (?, ?, ?, ?, ?)", (url, file_id, media_type, now, title)); await db.commit()

async def save_user_cookie(user_id, cookie_content):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO user_cookies (user_id, cookie_data, updated_at) VALUES (?, ?, ?)", (user_id, cookie_content, now)); await db.commit()

async def get_user_cookie(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT cookie_data FROM user_cookies WHERE user_id = ?", (user_id,)); row = await cursor.fetchone(); return row[0] if row else None

async def get_system_value(key):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT value FROM system_config WHERE key = ?", (key,)); row = await cursor.fetchone(); return row[0] if row else None

async def set_system_value(key, value):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO system_config (key, value) VALUES (?, ?)", (key, value)); await db.commit()
        
async def clear_file_cache():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM file_cache"); await db.commit()

async def set_module_status(module_name: str, is_enabled: bool):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO modules_config (module_name, is_enabled) VALUES (?, ?)", (module_name, 1 if is_enabled else 0)); await db.commit()

async def get_module_status(module_name: str) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT is_enabled FROM modules_config WHERE module_name = ?", (module_name,)); row = await cursor.fetchone()
        if row is None: return True
        return bool(row[0])
    
async def get_global_stats():
    """Возвращает общую статистику по логам"""
    async with aiosqlite.connect(DB_NAME) as db:
        # Всего запросов
        c1 = await db.execute("SELECT COUNT(*) FROM activity_logs WHERE action IN ('USER_REQ', 'SUCCESS')")
        total_reqs = (await c1.fetchone())[0]
        
        # Успешных
        c2 = await db.execute("SELECT COUNT(*) FROM activity_logs WHERE action = 'SUCCESS'")
        success_reqs = (await c2.fetchone())[0]
        
        return total_reqs, success_reqs

async def get_users_with_stats(sort_by='last_seen'):
    """
    Возвращает список пользователей + количество их запросов.
    sort_by: 'first_seen', 'last_seen', 'requests'
    """
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        
        # Сложный запрос: соединяем юзеров и подсчет их логов
        # user_id < 0 = Группы, user_id > 0 = Люди
        query = """
            SELECT u.*, 
            (SELECT COUNT(*) FROM activity_logs l WHERE l.user_id = u.user_id) as req_count 
            FROM users u
        """
        
        rows = await db.execute(query)
        users = await rows.fetchall()
        
        # Превращаем в список словарей для сортировки в Python (проще и надежнее для SQLite)
        result = [dict(u) for u in users]
        
        # Сортировка
        reverse = True # По убыванию (сначала новые/активные)
        
        if sort_by == 'first_seen':
            key = lambda x: x['first_seen'] or ""
        elif sort_by == 'requests':
            key = lambda x: x['req_count']
        else: # last_seen
            key = lambda x: x['last_seen'] or ""
            
        return sorted(result, key=key, reverse=reverse)
    
async def web_ban_user(user_id, reason):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET is_banned = 1, ban_reason = ? WHERE user_id = ?", (reason, user_id))
        await db.commit()

async def web_unban_user(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET is_banned = 0, ban_reason = NULL WHERE user_id = ?", (user_id,))
        await db.commit()

# --- ЛОГИРОВАНИЕ ---
async def log_activity(user_id, username, action, details):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO activity_logs (user_id, username, action, details) VALUES (?, ?, ?, ?)",
            (user_id, username, action, str(details))
        )
        await db.commit()

async def get_user_logs(user_id, limit=None):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM activity_logs WHERE user_id = ? ORDER BY id DESC"
        params = (user_id,)
        if limit:
            query += " LIMIT ?"
            params = (user_id, limit)
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return list(reversed(rows)) # Для чата (старые сверху)

# --- СТАТИСТИКА (ФИКС) ---
async def get_global_stats():
    """Возвращает (Всего, Успешно)"""
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            # Считаем общее количество любых действий
            c1 = await db.execute("SELECT COUNT(*) FROM activity_logs")
            row1 = await c1.fetchone()
            total = row1[0] if row1 else 0
            
            # Считаем успешные загрузки
            c2 = await db.execute("SELECT COUNT(*) FROM activity_logs WHERE action = 'SUCCESS'")
            row2 = await c2.fetchone()
            success = row2[0] if row2 else 0
            
            return total, success
        except:
            return 0, 0

async def get_stats_period(period_sql):
    """period_sql: '-1 day', '-1 hour'"""
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            cursor = await db.execute(f"""
                SELECT COUNT(*) FROM activity_logs 
                WHERE timestamp >= datetime('now', '{period_sql}')
            """)
            row = await cursor.fetchone()
            return row[0] if row else 0, 0 # Возвращаем tuple
        except:
            return 0, 0
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO activity_logs (user_id, username, action, details) VALUES (?, ?, ?, ?)",
            (user_id, username, action, details)
        )
        await db.commit()