# -*- coding: utf-8 -*-
import logging
from datetime import datetime
from html import escape

from aiogram import Router, types, F
from aiogram.filters import Command, CommandObject, BaseFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from handlers.admin.filters import AdminFilter
from core.loader import bot
from services.database.repo import (
    get_user,
    ensure_user_exists,
    ban_user,
    unban_user,
    delete_user,
)

logger = logging.getLogger(__name__)
router = Router()
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())

# admin_id -> {"kind": "ban"|"msg", "target_id": int, "chat_id": int, "card_message_id": int}
_PENDING: dict[int, dict] = {}


class _HasPendingInput(BaseFilter):
    async def __call__(self, message: types.Message) -> bool:
        try:
            pending = _PENDING.get(message.from_user.id)
            return bool(pending and pending.get("kind"))
        except Exception:
            return False


def _fmt_dt(dt: datetime | None) -> str:
    if not dt:
        return "—"
    try:
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(dt)


def _kb_for_entity(entity_id: int, exists: bool, is_banned: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    if exists:
        row1 = []
        if is_banned:
            row1.append(InlineKeyboardButton(text="✅ Разбан", callback_data=f"eu:unban:{entity_id}"))
        else:
            row1.append(InlineKeyboardButton(text="⛔ Бан", callback_data=f"eu:ban:{entity_id}"))
        row1.append(InlineKeyboardButton(text="✉️ Написать", callback_data=f"eu:msg:{entity_id}"))
        rows.append(row1)

        rows.append([
            InlineKeyboardButton(text="🗑️ Удалить данные", callback_data=f"eu:del1:{entity_id}"),
        ])
    else:
        rows.append([
            InlineKeyboardButton(text="➕ Добавить в БД", callback_data=f"eu:add:{entity_id}"),
        ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _safe_int(s: str) -> int | None:
    try:
        return int(s)
    except Exception:
        return None


def _render_card(entity_id: int, db_user, api_chat: types.Chat | None, api_error: str | None) -> str:
    is_group = entity_id < 0
    kind = "Group/Chat" if is_group else "User"

    lines = []
    lines.append(f"<b>🧾 {kind} card</b>")
    lines.append(f"<b>ID:</b> <code>{entity_id}</code>")

    # API info
    lines.append("\n<b>🌐 Telegram API</b>")
    if api_chat is None:
        lines.append(f"<b>Status:</b> ❌ {api_error or 'No access'}")
    else:
        lines.append(f"<b>Type:</b> {api_chat.type}")
        if getattr(api_chat, "title", None):
            lines.append(f"<b>Title:</b> {escape(api_chat.title)}")
        if getattr(api_chat, "username", None):
            lines.append(f"<b>Username:</b> @{escape(api_chat.username)}")
        if getattr(api_chat, "first_name", None) or getattr(api_chat, "last_name", None):
            fn = getattr(api_chat, "first_name", None) or ""
            ln = getattr(api_chat, "last_name", None) or ""
            name = (fn + " " + ln).strip()
            if name:
                lines.append(f"<b>Name:</b> {escape(name)}")
        if getattr(api_chat, "bio", None):
            bio = str(api_chat.bio)
            if len(bio) > 300:
                bio = bio[:300] + "…"
            lines.append(f"<b>Bio:</b> {escape(bio)}")

    # DB info
    lines.append("\n<b>🗄️ Database</b>")
    if not db_user:
        lines.append("<b>Status:</b> ⚠️ Not found")
        return "\n".join(lines)

    uname = f"@{db_user.username}" if db_user.username else "—"
    lines.append(f"<b>Username:</b> {escape(uname)}")
    lines.append(f"<b>Full name:</b> {escape(db_user.full_name or '—')}")
    lines.append(f"<b>Tag:</b> {escape(db_user.user_tag or '—')}")
    lines.append(f"<b>Language:</b> {escape(db_user.language or 'en')}")
    lines.append(f"<b>Active:</b> {'✅' if db_user.is_active else '❌'}")
    # Under a "Banned:" label, use ✅ to mean "yes, banned" (avoid ambiguity)
    lines.append(f"<b>Banned:</b> {'✅' if db_user.is_banned else '❌'}")
    if db_user.is_banned and db_user.ban_reason:
        lines.append(f"<b>Ban reason:</b> {escape(db_user.ban_reason)}")
    lines.append(f"<b>First seen:</b> {_fmt_dt(db_user.first_seen)}")
    lines.append(f"<b>Last seen:</b> {_fmt_dt(db_user.last_seen)}")
    lines.append(f"<b>Interactions:</b> {db_user.request_count}")
    lines.append(f"<b>Last.fm:</b> {escape(db_user.lastfm_username or '—')}")

    lines.append("\n<i>Note: message history (first/last message text) is not stored in current DB schema.</i>")
    return "\n".join(lines)


async def _get_chat_safe(entity_id: int) -> tuple[types.Chat | None, str | None]:
    try:
        chat = await bot.get_chat(entity_id)
        return chat, None
    except Exception as e:
        return None, str(e)


async def _send_or_edit_card(chat_id: int, message_id: int | None, entity_id: int):
    db_user = await get_user(entity_id)
    api_chat, api_err = await _get_chat_safe(entity_id)

    text = _render_card(entity_id, db_user, api_chat, api_err)
    kb = _kb_for_entity(entity_id, exists=bool(db_user), is_banned=bool(db_user and db_user.is_banned))

    if message_id:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=kb, disable_web_page_preview=True)
            return
        except Exception:
            pass

    await bot.send_message(chat_id, text, reply_markup=kb, disable_web_page_preview=True)


@router.message(Command("edituser"))
async def cmd_edituser(message: types.Message, command: CommandObject):
    if not command.args:
        await message.answer("Use: <code>/edituser ID</code>")
        return

    entity_id = _safe_int(command.args.strip())
    if entity_id is None:
        await message.answer("Invalid ID. Use: <code>/edituser ID</code>")
        return

    db_user = await get_user(entity_id)
    api_chat, api_err = await _get_chat_safe(entity_id)

    text = _render_card(entity_id, db_user, api_chat, api_err)
    kb = _kb_for_entity(entity_id, exists=bool(db_user), is_banned=bool(db_user and db_user.is_banned))
    sent = await message.answer(text, reply_markup=kb, disable_web_page_preview=True)

    # Remember last card message for follow-up inputs
    _PENDING.pop(message.from_user.id, None)
    _PENDING[message.from_user.id] = {
        "kind": None,
        "target_id": entity_id,
        "chat_id": sent.chat.id,
        "card_message_id": sent.message_id,
    }


@router.callback_query(F.data.startswith("eu:"))
async def cb_edituser(call: types.CallbackQuery):
    try:
        _, action, raw_id = call.data.split(":", 2)
    except Exception:
        await call.answer("Bad action", show_alert=True)
        return

    entity_id = _safe_int(raw_id)
    if entity_id is None:
        await call.answer("Bad id", show_alert=True)
        return

    admin_id = call.from_user.id
    card_chat_id = call.message.chat.id if call.message else admin_id
    card_msg_id = call.message.message_id if call.message else None

    if action == "add":
        api_chat, _ = await _get_chat_safe(entity_id)
        username = None
        full_name = "Unknown"
        tag = None
        lang = (call.from_user.language_code or "en")

        if api_chat is not None:
            username = getattr(api_chat, "username", None)
            if entity_id < 0:
                full_name = getattr(api_chat, "title", None) or full_name
                tag = getattr(api_chat, "type", None) or "group"
            else:
                fn = getattr(api_chat, "first_name", None) or ""
                ln = getattr(api_chat, "last_name", None) or ""
                name = (fn + " " + ln).strip()
                full_name = name or full_name

        await ensure_user_exists(entity_id, username, full_name, tag=tag, language=lang)
        await call.answer("Added")
        await _send_or_edit_card(card_chat_id, card_msg_id, entity_id)
        return

    if action == "ban":
        _PENDING[admin_id] = {
            "kind": "ban",
            "target_id": entity_id,
            "chat_id": card_chat_id,
            "card_message_id": card_msg_id,
        }
        await call.answer("Reason?")
        await bot.send_message(card_chat_id, "Введите причину бана (или <code>-</code> чтобы без причины). /cancel — отмена")
        return

    if action == "unban":
        await unban_user(entity_id)
        await call.answer("Unbanned")
        await _send_or_edit_card(card_chat_id, card_msg_id, entity_id)
        return

    if action == "msg":
        _PENDING[admin_id] = {
            "kind": "msg",
            "target_id": entity_id,
            "chat_id": card_chat_id,
            "card_message_id": card_msg_id,
        }
        await call.answer("Write message")
        await bot.send_message(card_chat_id, "Текст сообщения пользователю/группе? /cancel — отмена")
        return

    if action == "del1":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"eu:del2:{entity_id}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data=f"eu:refresh:{entity_id}"),
            ]
        ])
        await call.answer("Confirm")
        try:
            await bot.edit_message_reply_markup(chat_id=card_chat_id, message_id=card_msg_id, reply_markup=kb)
        except Exception:
            await bot.send_message(card_chat_id, "Подтверди удаление", reply_markup=kb)
        return

    if action == "del2":
        deleted = await delete_user(entity_id)
        await call.answer("Deleted" if deleted else "Not found")
        await _send_or_edit_card(card_chat_id, card_msg_id, entity_id)
        return

    if action == "refresh":
        await call.answer("OK")
        await _send_or_edit_card(card_chat_id, card_msg_id, entity_id)
        return

    await call.answer("Unknown action", show_alert=True)


@router.message(F.text, _HasPendingInput())
async def admin_pending_input(message: types.Message):
    admin_id = message.from_user.id
    pending = _PENDING.get(admin_id)
    if not pending or not pending.get("kind"):
        return

    text = (message.text or "").strip()
    if text.lower() in ("/cancel", "cancel", "отмена"):
        _PENDING.pop(admin_id, None)
        await message.answer("Cancelled")
        return

    kind = pending.get("kind")
    target_id = int(pending.get("target_id"))
    chat_id = int(pending.get("chat_id"))
    card_msg_id = pending.get("card_message_id")

    if kind == "ban":
        reason = None if text == "-" else text
        await ban_user(target_id, reason or "Banned by admin")
        _PENDING.pop(admin_id, None)
        await message.answer("Banned")
        await _send_or_edit_card(chat_id, card_msg_id, target_id)
        return

    if kind == "msg":
        try:
            await bot.send_message(target_id, f"📩 <b>Admin:</b>\n{text}")
            await message.answer("✅ Sent")
        except Exception as e:
            await message.answer(f"❌ Failed: {e}")
        _PENDING.pop(admin_id, None)
        await _send_or_edit_card(chat_id, card_msg_id, target_id)
        return
