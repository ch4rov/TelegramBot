import sys
import asyncio
from aiogram import Router, types, F
from aiogram.filters import Command

# Импортируем наши настройки и сервисы
import settings
# ИСПРАВЛЕННЫЕ ИМПОРТЫ (из core, а не services)
from core.logger_system import send_log
from core.queue_manager import queue_manager
from services.database_service import clear_file_cache, set_system_value

router = Router()

# Простая проверка админа внутри файла (так надежнее)
def is_admin(user_id: int) -> bool:
    return user_id in settings.ADMIN_IDS

# --- UPDATE (HARD RESET) ---
@router.message(Command("update"))
async def cmd_update(message: types.Message):
    if not is_admin(message.from_user.id): return

    msg = await message.answer("🔄 <b>Принудительное обновление (Hard Reset)...</b>", parse_mode="HTML")
    
    try:
        # 1. Скачиваем изменения (fetch)
        proc_fetch = await asyncio.create_subprocess_shell(
            "git fetch origin", 
            stdout=asyncio.subprocess.PIPE, 
            stderr=asyncio.subprocess.PIPE
        )
        await proc_fetch.communicate()

        # 2. Жестко сбрасываем локальные файлы до состояния origin/main
        # Это удалит локальные правки (кроме .env и того, что в .gitignore)
        proc_reset = await asyncio.create_subprocess_shell(
            "git reset --hard origin/main", 
            stdout=asyncio.subprocess.PIPE, 
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc_reset.communicate()
        
        if proc_reset.returncode != 0:
            await msg.edit_text(f"❌ <b>Ошибка Git:</b>\n<pre>{stderr.decode()}</pre>", parse_mode="HTML")
            return

        # 3. Получаем инфо о последнем коммите для логов
        proc_log = await asyncio.create_subprocess_shell(
            "git log -1 --pretty=%B", 
            stdout=asyncio.subprocess.PIPE
        )
        log_out, _ = await proc_log.communicate()
        commit_msg = log_out.decode().strip()
        
        await msg.edit_text(f"✅ <b>Обновлено!</b>\n📝 <i>{commit_msg}</i>\n\n♻️ Перезапуск системы...", parse_mode="HTML")
        
        # Логируем действие
        await send_log("ADMIN", f"Force Update executed: {commit_msg}", admin=message.from_user)
        
        # 4. Выход с кодом 65 (Команда для раннера перезапустить процесс)
        sys.exit(65) 

    except Exception as e:
        await msg.edit_text(f"❌ <b>Critical Error:</b> {str(e)}", parse_mode="HTML")

# --- CLEAR CACHE (SMART) ---
@router.message(Command("clearcache"))
async def cmd_clearcache(message: types.Message):
    if not is_admin(message.from_user.id): return
    
    args = message.text.split()
    minutes = 0
    
    # Парсинг аргументов (10m, 1h, 1d)
    if len(args) > 1:
        param = args[1].lower()
        try:
            if param.endswith('m'): minutes = int(param[:-1])
            elif param.endswith('h'): minutes = int(param[:-1]) * 60
            elif param.endswith('d'): minutes = int(param[:-1]) * 60 * 24
            else: minutes = int(param) # Если просто число, считаем минутами
        except:
            await message.answer("❌ Формат: <code>/clearcache 10m</code> (или 1h, 1d)", parse_mode="HTML")
            return

    if minutes > 0:
        try:
            from services.database_service import clear_cache_older_than
            await clear_cache_older_than(minutes)
            await message.answer(f"🗑️ Кэш за последние <b>{args[1]}</b> очищен.", parse_mode="HTML")
            await send_log("ADMIN", f"Cache cleared (> {args[1]})", admin=message.from_user)
        except ImportError:
            await message.answer("⚠️ Функция выборочной очистки недоступна в базе данных.")
    else:
        # Полная очистка
        await clear_file_cache()
        await message.answer("🗑️ <b>Весь кэш файлов полностью очищен!</b>", parse_mode="HTML")
        await send_log("ADMIN", "Full cache cleared", admin=message.from_user)

# --- LIMIT MANAGER ---
@router.message(Command("limit"))
async def cmd_limit(message: types.Message):
    if not is_admin(message.from_user.id): return
    
    args = message.text.split()
    
    # Если просто /limit - показываем статус
    if len(args) == 1:
        mode = queue_manager.limit_mode
        try:
            active = sum(len(tasks) for tasks in queue_manager.user_tasks.values())
        except:
            active = 0
        
        text = (
            f"🚦 <b>Limit Status:</b>\n"
            f"Mode: <b>{mode.upper()}</b>\n"
            f"Active tasks: {active}\n\n"
            f"🔹 <code>/limit on</code> - Общий лимит (все ждут)\n"
            f"🔹 <code>/limit user</code> - Лимит на юзера (Админы безлимит)\n"
            f"🔹 <code>/limit off</code> - Без лимитов (Опасно)"
        )
        await message.answer(text, parse_mode="HTML")
        return

    # Установка режима
    new_mode = args[1].lower()
    if new_mode not in ['on', 'off', 'user']:
        await message.answer("❌ Invalid mode. Use: <b>on / off / user</b>", parse_mode="HTML")
        return

    queue_manager.set_mode(new_mode)
    await set_system_value("limit_mode", new_mode)
    
    await message.answer(f"✅ Limit mode set to: <b>{new_mode.upper()}</b>", parse_mode="HTML")
    await send_log("ADMIN", f"Limit mode changed -> {new_mode}", admin=message.from_user)