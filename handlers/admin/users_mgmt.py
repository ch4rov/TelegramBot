# -*- coding: utf-8 -*-
import os
import logging
from aiogram import Router, types
from aiogram.filters import Command, CommandObject
from aiogram.types import FSInputFile
from handlers.admin.filters import AdminFilter
from services.database.repo import (
    get_all_users, ban_user, unban_user, 
    get_lastfm_username, increment_request_count
)

router = Router()
router.message.filter(AdminFilter())
logger = logging.getLogger(__name__)

@router.message(Command("users"))
async def cmd_users(message: types.Message):
    """Список всех пользователей"""
    try:
        users = await get_all_users()
        await increment_request_count(message.from_user.id)
        
        if not users:
            await message.answer("No users found.", disable_notification=True)
            return

        groups = [u for u in users if u.id < 0 and u.id != 777000]
        users_list = [u for u in users if u.id > 0]

        total = len(users)
        groups_count = len(groups)
        users_count = len(users_list)
        
        text = f"📊 Database Report:\nВсего: {total} ("
        if groups:
            text += f"👥 {groups_count} | "
        text += f"👤 {users_count})\n\n"
        
        if groups:
            text += "👥 Группы:\n"
            for g in groups:
                status = "✅" if not g.is_banned else "❌"
                title = (g.full_name or "").strip()
                handle = (g.username or "").strip()
                label = title or (f"@{handle}" if handle else "(no title)")
                text += f"{status} {label} | {g.id}\n"
            text += "\n"
        
        if users_list:
            text += "👤 Пользователи:\n"
            for u in users_list:
                status = "❌" if u.is_banned else "✅"
                username = f"@{u.username}" if u.username else "@"
                text += f"{status} {u.id} {username}\n"
        
        if len(users) > 10:
            filename = "users_report.txt"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(text)
            
            await message.answer_document(FSInputFile(filename), caption=f"Total: {len(users)}", disable_notification=True)
            os.remove(filename)
        else:
            await message.answer(text, disable_notification=True)
        
        logger.info(f"ADMIN: User {message.from_user.id} used /users command")
    except Exception as e:
        logger.error(f"Error in /users: {e}")
        await message.answer("Error retrieving users.", disable_notification=True)

@router.message(Command("ban"))
async def cmd_ban(message: types.Message, command: CommandObject):
    """Банит пользователя: /ban ID [Reason]"""
    try:
        if not command.args:
            await message.answer("Use: /ban ID [Reason]", disable_notification=True)
            return
        
        args = command.args.split(" ", 1)
        user_id_str = args[0]
        reason = args[1] if len(args) > 1 else "Banned by admin"

        try:
            user_id = int(user_id_str)
        except Exception:
            await message.answer("Invalid ID", disable_notification=True)
            return
        success = await ban_user(user_id, reason)
        
        if success:
            from services.database.repo import get_user_language
            from services.localization import i18n
            user_lang = await get_user_language(user_id)
            
            from core.loader import bot
            # Always send with reason to user
            ban_msg = i18n.get("user_banned", user_lang, reason=reason)
            
            try:
                await bot.send_message(user_id, ban_msg, disable_notification=True)
            except Exception:
                pass
            
            if len(args) > 1:
                response = f"User {user_id} has been BANNED. Reason: {reason}"
            else:
                response = f"User {user_id} has been BANNED."
            
            await message.answer(response, disable_notification=True)
            logger.info(f"ADMIN: User {message.from_user.id} banned user {user_id}. Reason: {reason}")
        else:
            await message.answer(f"User {user_id} not found or already banned.", disable_notification=True)
    except Exception as e:
        logger.error(f"Error in /ban: {e}")
        await message.answer("Error banning user.", disable_notification=True)

@router.message(Command("unban"))
async def cmd_unban(message: types.Message, command: CommandObject):
    """Разбанивает пользователя: /unban ID"""
    try:
        if not command.args:
            await message.answer("Use: /unban ID", disable_notification=True)
            return
        
        user_id_str = command.args.split()[0]
        if not user_id_str.isdigit():
            await message.answer("Invalid user ID", disable_notification=True)
            return
        
        user_id = int(user_id_str)
        success = await unban_user(user_id)
        
        if success:
            from services.database.repo import get_user_language
            from services.localization import i18n
            user_lang = await get_user_language(user_id)
            
            from core.loader import bot
            unban_msg = i18n.get("user_unbanned", user_lang, user_id=user_id)
            
            try:
                await bot.send_message(user_id, unban_msg, disable_notification=True)
            except:
                pass
            
            await message.answer(f"User {user_id} has been UNBANNED.", disable_notification=True)
            logger.info(f"ADMIN: User {message.from_user.id} unbanned user {user_id}")
        else:
            await message.answer(f"User {user_id} not found.", disable_notification=True)
    except Exception as e:
        logger.error(f"Error in /unban: {e}")
        await message.answer("Error unbanning user.", disable_notification=True)

@router.message(Command("answer"))
async def cmd_answer(message: types.Message, command: CommandObject):
    """Отправляет сообщение пользователю: /answer ID MESSAGE"""
    try:
        if not command.args:
            await message.answer("Use: /answer ID MESSAGE", disable_notification=True)
            return
        
        args = command.args.split(" ", 1)
        if len(args) < 2:
            await message.answer("Use: /answer ID MESSAGE", disable_notification=True)
            return
        
        user_id_str = args[0]
        text = args[1]
        
        if not user_id_str.isdigit():
            await message.answer("Invalid user ID", disable_notification=True)
            return
        
        user_id = int(user_id_str)
        
        from core.loader import bot
        try:
            await bot.send_message(user_id, f"📩 <b>Admin:</b>\n{text}", parse_mode="HTML", disable_notification=True)
            await message.answer(f"Message sent to user {user_id}", disable_notification=True)
            logger.info(f"ADMIN: User {message.from_user.id} sent message to user {user_id}")
        except Exception as send_error:
            await message.answer(f"Failed to send message: {send_error}", disable_notification=True)
            logger.error(f"Error sending message to {user_id}: {send_error}")
            
    except Exception as e:
        logger.error(f"Error in /answer: {e}")
        await message.answer("Error sending message.", disable_notification=True)
