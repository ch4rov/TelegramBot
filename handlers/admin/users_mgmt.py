# -*- coding: utf-8 -*-
import os
import logging
from aiogram import Router, types
from aiogram import F
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from handlers.admin.filters import AdminFilter
from services.database.repo import (
    get_all_users, ban_user, unban_user, 
    get_lastfm_username, increment_request_count
)

router = Router()
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())
logger = logging.getLogger(__name__)


def _cap(s: str | None, n: int) -> str:
    if not s:
        return ""
    s = str(s).strip()
    if len(s) <= n:
        return s
    return s[: max(0, n - 1)] + "…"


def _users_kb(page: int, max_page: int) -> InlineKeyboardMarkup:
    page = max(0, min(page, max_page))
    prev_page = max(0, page - 1)
    next_page = min(max_page, page + 1)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️", callback_data=f"users:page:{prev_page}"),
                InlineKeyboardButton(text=f"{page + 1}/{max_page + 1}", callback_data=f"users:page:{page}"),
                InlineKeyboardButton(text="➡️", callback_data=f"users:page:{next_page}"),
            ]
        ]
    )


def _render_users_page(all_users: list, page: int, page_size: int = 20) -> tuple[str, InlineKeyboardMarkup]:
    groups = [u for u in all_users if getattr(u, "id", 0) < 0 and getattr(u, "id", 0) != 777000]
    users_list = [u for u in all_users if getattr(u, "id", 0) > 0]

    total = len(all_users)
    groups_count = len(groups)
    users_count = len(users_list)

    items: list[tuple[str, object]] = [("group", g) for g in groups] + [("user", u) for u in users_list]
    total_items = len(items)
    max_page = max(0, (total_items - 1) // page_size) if total_items else 0
    page = max(0, min(page, max_page))
    start = page * page_size
    end = start + page_size

    lines = []
    lines.append("📊 <b>Database Report</b>")
    lines.append(f"Всего: {total} (👥 {groups_count} | 👤 {users_count})")
    lines.append(f"Показано: {start + 1 if total_items else 0}-{min(end, total_items)} из {total_items}")
    lines.append("")

    if not items:
        lines.append("No users found.")
        return "\n".join(lines), _users_kb(0, 0)

    for kind, obj in items[start:end]:
        eid = getattr(obj, "id", 0)
        is_banned = bool(getattr(obj, "is_banned", False))
        status = "❌" if is_banned else "✅"
        username = (getattr(obj, "username", None) or "").strip()
        full_name = (getattr(obj, "full_name", None) or "").strip()

        if kind == "group":
            title = full_name
            label = _cap(title, 42) or (f"@{_cap(username, 32)}" if username else "(no title)")
            lines.append(f"👥 {status} {label} | <code>{eid}</code>")
        else:
            uname = f"@{username}" if username else "@"
            lines.append(f"👤 {status} <code>{eid}</code> {uname}")

    return "\n".join(lines), _users_kb(page, max_page)

@router.message(Command("users"))
async def cmd_users(message: types.Message):
    """Список всех пользователей"""
    try:
        users = await get_all_users()
        await increment_request_count(message.from_user.id)
        
        if not users:
            await message.answer("No users found.", disable_notification=True)
            return

        text, kb = _render_users_page(users, page=0, page_size=20)
        await message.answer(text, reply_markup=kb, disable_notification=True, disable_web_page_preview=True)
        
        logger.info(f"ADMIN: User {message.from_user.id} used /users command")
    except Exception as e:
        logger.error(f"Error in /users: {e}")
        await message.answer("Error retrieving users.", disable_notification=True)


@router.callback_query(F.data.startswith("users:page:"))
async def cb_users_page(call: types.CallbackQuery):
    try:
        page = int((call.data or "").split(":", 2)[2])
    except Exception:
        await call.answer("Bad page", show_alert=True)
        return

    users = await get_all_users()
    text, kb = _render_users_page(users, page=page, page_size=20)
    await call.answer("OK")
    try:
        await call.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
    except Exception:
        try:
            await call.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
        except Exception:
            pass

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
