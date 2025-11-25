"""Admin handler - admin commands and management"""
import os
import sys
from aiogram import Router, types, exceptions
from aiogram.filters import Command
from aiogram.types import FSInputFile

from core.access_manager import AccessManager
from services.database_service import get_all_users, set_ban_status, get_user
from services.logger_service import send_log, toggle_debug_mode, clear_debug_log
from services.downloads import download_content

router = Router()


# --- RESTART ---
@router.message(Command("restart"))
async def cmd_restart(message: types.Message):
    if not AccessManager.is_admin(message.from_user.id):
        return

    try:
        await message.answer("♻️ Перезагрузка системы...")
    except Exception:
        pass
    
    await send_log("ADMIN", "Инициировал перезагрузку (Restart)", admin=message.from_user)
    
    # Create restart flag
    restart_flag_path = ".restart_flag"
    try:
        with open(restart_flag_path, "w") as f:
            f.write("")
    except Exception:
        pass
    
    # Close bot session before exit
    try:
        await message.bot.session.close()
    except Exception:
        pass
    
    os._exit(65)


# --- STATUS ---
@router.message(Command("status"))
async def cmd_status(message: types.Message):
    if not AccessManager.is_admin(message.from_user.id):
        return
    
    # Read version
    try:
        with open("VERSION", "r") as f:
            version = f.read().strip()
    except Exception:
        version = "unknown"
    
    await message.answer(f"✅ Система работает штатно.\n📦 Версия: {version}")
    await send_log("ADMIN", "> /status", admin=message.from_user)


# --- USERS LIST ---
@router.message(Command("users"))
async def cmd_users(message: types.Message):
    if not AccessManager.is_admin(message.from_user.id):
        return

    users = await get_all_users()
    if not users:
        await message.answer("📂 База данных пуста.")
        return

    text = f"📋 <b>Всего пользователей: {len(users)}</b>\n\n"
    count = 0
    
    for u in users:
        if count >= 20:
            text += "\n<i>...(и еще много)...</i>"
            break

        is_active = u['is_active'] 
        is_banned = u['is_banned']
        
        is_dead = False
        
        if is_banned:
            status_icon = "⛔ (БАН)"
            is_dead = True
        elif not is_active:
            status_icon = "💀 (Блок)"
            is_dead = True
        else:
            status_icon = "✅"

        raw_name = str(u['username']) if u['username'] else "NoName"
        clean_name = raw_name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        
        reason_txt = ""
        if is_banned and u['ban_reason']:
            reason_clean = str(u['ban_reason']).replace("<", "&lt;").replace(">", "&gt;")
            reason_txt = f"\n   Reason: <i>{reason_clean}</i>"
        
        user_line = f"{status_icon} <code>{u['user_id']}</code> | @{clean_name}{reason_txt}\n🕒 {u['last_seen']}\n\n"
        
        if is_dead:
            user_line = f"<s>{user_line}</s>"
            
        text += user_line
        count += 1
        
    await message.answer(text, parse_mode="HTML")


# --- BAN LOGIC ---
@router.message(Command("ban"))
async def cmd_ban(message: types.Message):
    if not AccessManager.is_admin(message.from_user.id):
        return
    
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("⚠️ Использование: <code>/ban ID [Причина]</code>", parse_mode="HTML")
        return
        
    try:
        target_id = int(parts[1])
        new_reason = parts[2] if len(parts) > 2 else "Нарушение правил"
        
        user_data = await get_user(target_id)
        if not user_data:
            await message.answer("❌ Пользователь не найден.")
            return

        await set_ban_status(target_id, True, new_reason)
        await message.answer(f"⛔ Пользователь <code>{target_id}</code> забанен.", parse_mode="HTML")
        await send_log("ADMIN", f"Забанил {target_id} ({new_reason})", admin=message.from_user)
        
        try:
            await message.bot.send_message(target_id, f"⛔ Вы заблокированы администратором.\nПричина: {new_reason}\nСвязь: @ch4rov")
        except:
            pass 

    except ValueError:
        await message.answer("ID должен быть числом.")


# --- UNBAN LOGIC ---
@router.message(Command("unban"))
async def cmd_unban(message: types.Message):
    if not AccessManager.is_admin(message.from_user.id):
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            return
        
        target_id = int(parts[1])
        
        await set_ban_status(target_id, False)
        await message.answer(f"✅ Пользователь <code>{target_id}</code> разбанен.", parse_mode="HTML")
        await send_log("ADMIN", f"Разбанил {target_id}", admin=message.from_user)
        
        try:
            await message.bot.send_message(target_id, "✅ Ваш аккаунт разблокирован.")
        except:
            pass
    except:
        pass


# --- ANSWER ---
@router.message(Command("answer"))
async def cmd_answer(message: types.Message):
    if not AccessManager.is_admin(message.from_user.id):
        return

    rest = message.text.partition(' ')[2].strip()
    target_id = None
    text_to_send = None

    if message.reply_to_message and getattr(message.reply_to_message, 'from_user', None):
        if not rest:
            await message.answer("⚠️ Использование: <code>/answer ТЕКСТ</code> (ответом)", parse_mode="HTML")
            return
        target_id = message.reply_to_message.from_user.id
        text_to_send = rest
    else:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            await message.answer("⚠️ Использование: <code>/answer ID ТЕКСТ</code>", parse_mode="HTML")
            return
        try:
            target_id = int(parts[1])
        except ValueError:
            await message.answer("ID должен быть числом.")
            return
        text_to_send = parts[2]

    if not text_to_send or not target_id:
        return

    send_text = f"📩 <b>Сообщение от администратора:</b>\n\n{text_to_send}"
    try:
        await message.bot.send_message(target_id, send_text, parse_mode="HTML")
        await message.answer("✅ Сообщение отправлено.")
        await send_log("ADMIN", f"Написал {target_id}: {text_to_send}", admin=message.from_user)
    except exceptions.TelegramAPIError as e:
        await message.answer(f"❌ Ошибка: {e}")
        await send_log("FAIL", f"Send Error to {target_id}: {e}", admin=message.from_user)


# --- DEBUG ---
@router.message(Command("debug"))
async def cmd_debug(message: types.Message):
    if not AccessManager.is_admin(message.from_user.id):
        return
    
    # Toggle debug mode
    debug_enabled = toggle_debug_mode()
    
    if debug_enabled:
        await clear_debug_log()
        await message.answer("🔍 DEBUG режим включен ✅\n\n- Все логи будут печатать в консоль\n- Создан файл debug.log в logs/files/")
        await send_log("ADMIN", "Включил DEBUG режим", admin=message.from_user)
    else:
        await message.answer("🔍 DEBUG режим выключен ❌")
        await send_log("ADMIN", "Выключил DEBUG режим", admin=message.from_user)



