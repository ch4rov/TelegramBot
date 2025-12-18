# -*- coding: utf-8 -*-
import sys
import os
import time
import logging
import re
import datetime
from aiogram import Router, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from handlers.admin.filters import AdminFilter
from services.database.repo import get_all_users

logger = logging.getLogger(__name__)
router = Router()
router.message.filter(AdminFilter())

# Время запуска бота
BOT_START_TIME = time.time()
BOT_COMMAND_COUNT = 0

@router.message(Command("status"))
async def cmd_status(message: types.Message):
    """Bot status and health check command"""
    try:
        global BOT_COMMAND_COUNT
        
        users = await get_all_users()
        count = len(users)
        active = sum(1 for u in users if u.is_active)
        banned = sum(1 for u in users if u.is_banned)
        
        # Calculate uptime
        uptime_seconds = time.time() - BOT_START_TIME
        uptime_hours = uptime_seconds / 3600
        uptime_days = uptime_hours / 24
        
        # Ping calculation
        start_ping = time.time()
        # Simulate a small operation
        await get_all_users()
        ping = (time.time() - start_ping) * 1000  # in milliseconds
        
        # Count temp files (cache)
        cache_count = 0
        if os.path.exists("tempfiles"):
            cache_count = len([f for f in os.listdir("tempfiles") if os.path.isfile(os.path.join("tempfiles", f))])
        
        # Format uptime
        if uptime_days >= 1:
            uptime_str = f"{int(uptime_days)}d {int(uptime_hours % 24)}h"
        else:
            uptime_str = f"{int(uptime_hours)}h {int((uptime_seconds % 3600) / 60)}m"

        text = (
            "🤖 Bot Status\n"
            "═" * 25 + "\n\n"
            f"⏱ Ping: {ping:.2f}ms\n"
            f"⏰ Uptime: {uptime_str}\n"
            f"📊 Commands processed: {BOT_COMMAND_COUNT}\n\n"
            f"👥 Users: {count}\n"
            f"✅ Active: {active}\n"
            f"🚫 Banned: {banned}\n\n"
            f"💾 Cache files: {cache_count}\n"
            f"🐍 Python: {sys.version.split()[0]}"
        )
        await message.answer(text, disable_notification=True)
        logger.info(f"Admin {message.from_user.id} used /status")
    except Exception as e:
        logger.error(f"Error in /status: {e}")
        await message.answer("Error getting bot status", disable_notification=True)

def parse_time_to_seconds(time_str: str) -> int:
    """Парсит строку времени типа '5m', '1h', '1d' в секунды"""
    match = re.match(r"^(\d+)([smhd])$", time_str.lower().strip())
    if not match:
        return None
    
    value, unit = match.groups()
    value = int(value)
    
    multipliers = {
        's': 1,
        'm': 60,
        'h': 3600,
        'd': 86400
    }
    
    return value * multipliers.get(unit, 1)

@router.message(Command("clearcache"))
async def cmd_clearcache(message: types.Message, command: CommandObject):
    """Clear cache with time argument: /clearcache [5m|1h|1d|all]"""
    try:
        if not command.args:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="5 минут", callback_data="cache_5m"),
                    InlineKeyboardButton(text="1 час", callback_data="cache_1h"),
                ],
                [
                    InlineKeyboardButton(text="1 день", callback_data="cache_1d"),
                    InlineKeyboardButton(text="Весь кеш", callback_data="cache_all"),
                ]
            ])
            await message.answer("Выберите время удаления кеша file_id:", reply_markup=kb, disable_notification=True)
            return
        
        time_arg = command.args.strip()
        
        if time_arg == "all":
            if os.path.exists("tempfiles"):
                import shutil
                shutil.rmtree("tempfiles")
                os.makedirs("tempfiles", exist_ok=True)
                await message.answer("✅ Весь file_id кеш удален", disable_notification=True)
                logger.info(f"Admin {message.from_user.id} cleared all cache")
            else:
                await message.answer("❌ Нет кеша для удаления", disable_notification=True)
        else:
            seconds = parse_time_to_seconds(time_arg)
            if not seconds:
                await message.answer("❌ Неверный формат времени. Используйте: 5m, 1h, 1d или all", disable_notification=True)
                return
            
            now = time.time()
            deleted_count = 0
            
            if os.path.exists("tempfiles"):
                for filename in os.listdir("tempfiles"):
                    filepath = os.path.join("tempfiles", filename)
                    if os.path.isfile(filepath):
                        file_age = now - os.path.getmtime(filepath)
                        if file_age > seconds:
                            try:
                                os.remove(filepath)
                                deleted_count += 1
                            except:
                                pass
            
            await message.answer(f"✅ Удалено файлов: {deleted_count}", disable_notification=True)
            logger.info(f"Admin {message.from_user.id} cleared cache older than {time_arg}")
    except Exception as e:
        logger.error(f"Error in /clearcache: {e}")
        await message.answer("❌ Ошибка при удалении кеша", disable_notification=True)

@router.callback_query(F.data.startswith("cache_"))
async def handle_cache_button(query: types.CallbackQuery):
    """Обработчик кнопок очистки кеша"""
    try:
        action = query.data.replace("cache_", "")
        
        if action == "all":
            if os.path.exists("tempfiles"):
                import shutil
                shutil.rmtree("tempfiles")
                os.makedirs("tempfiles", exist_ok=True)
                await query.answer("✅ Весь file_id кеш удален", show_alert=True)
                logger.info(f"Admin {query.from_user.id} cleared all cache via button")
            else:
                await query.answer("❌ Нет кеша", show_alert=True)
        else:
            seconds = parse_time_to_seconds(action)
            if seconds:
                now = time.time()
                deleted_count = 0
                
                if os.path.exists("tempfiles"):
                    for filename in os.listdir("tempfiles"):
                        filepath = os.path.join("tempfiles", filename)
                        if os.path.isfile(filepath):
                            file_age = now - os.path.getmtime(filepath)
                            if file_age > seconds:
                                try:
                                    os.remove(filepath)
                                    deleted_count += 1
                                except:
                                    pass
                
                await query.answer(f"✅ Удалено: {deleted_count} файлов", show_alert=True)
                logger.info(f"Admin {query.from_user.id} cleared cache older than {action} via button")
        
        await query.message.delete()
    except Exception as e:
        logger.error(f"Error in cache callback: {e}")
        await query.answer("❌ Ошибка", show_alert=True)
