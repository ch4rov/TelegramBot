# -*- coding: utf-8 -*-
import logging
import html
import settings
from aiogram import types, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from handlers.user.router import user_router
from core.tg_safe import safe_reply, safe_reply_html
from services.database.repo import (
    is_user_banned,
    increment_request_count,
    set_lastfm_username,
    get_lastfm_username,
    set_user_language,
    get_user_language,
    get_user_oauth_token,
    delete_user_oauth_token,
    create_oauth_state,
)
from services.lastfm_service import get_user_recent_track
from core.config import config
from services.oauth_server import build_spotify_authorize_url
from services.database.repo import get_user_pref_bool, set_user_pref_bool
from services.spotify_service import spotify_get_json

logger = logging.getLogger(__name__)


def _h(s: object) -> str:
    return html.escape("" if s is None else str(s))


async def _spotify_profile_label(user_id: int) -> str | None:
    tok = None
    try:
        tok = await get_user_oauth_token(user_id, "spotify")
    except Exception:
        tok = None
    if not tok:
        return None
    try:
        me = await spotify_get_json(user_id, "https://api.spotify.com/v1/me")
        data = me.get("data") if isinstance(me, dict) else None
        if isinstance(data, dict):
            return (data.get("display_name") or data.get("id") or "").strip() or None
    except Exception:
        return "connected"
    return "connected"


async def _login_kb(user_id: int, lang: str) -> InlineKeyboardMarkup:
    lf = None
    try:
        lf = await get_lastfm_username(user_id)
    except Exception:
        lf = None

    sp_label = await _spotify_profile_label(user_id)

    try:
        if isinstance(sp_label, str) and len(sp_label) > 22:
            sp_label = sp_label[:22] + "…"
    except Exception:
        pass
    try:
        if isinstance(lf, str) and len(lf) > 22:
            lf = lf[:22] + "…"
    except Exception:
        pass

    if lang == "ru":
        sp_text = "🎧 Spotify" + (f": {sp_label}" if sp_label else ": —")
        lf_text = "🎵 Last.fm" + (f": {lf}" if lf else ": —")
    else:
        sp_text = "🎧 Spotify" + (f": {sp_label}" if sp_label else ": —")
        lf_text = "🎵 Last.fm" + (f": {lf}" if lf else ": —")

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=sp_text, callback_data="login:spotify")],
            [InlineKeyboardButton(text=lf_text, callback_data="login:lastfm")],
        ]
    )

@user_router.message(Command("login"))
async def cmd_login(message: types.Message, command: CommandObject):
    """Login menu: Last.fm username + Spotify connect."""
    try:
        user = message.from_user
        is_banned = await is_user_banned(user.id)
        
        if is_banned:
            await safe_reply(message, "You are banned from using this bot.", disable_notification=True)
            return
        
        # Получаем язык пользователя
        from services.database.repo import get_user_language
        from services.localization import i18n
        lang = await get_user_language(user.id)
        
        if not command.args:
            text = []
            if lang == "ru":
                text.append("<b>Подключение аккаунтов</b>")
                text.append("")
                text.append("Здесь ты подключаешь Spotify и Last.fm, чтобы бот мог показывать/отправлять музыку в inline.")
                text.append("")
                text.append("Как использовать Spotify: открой inline, просто упомяни бота без текста.")
                text.append("Last.fm: отправь <code>/login USERNAME</code>.")
            else:
                text.append("<b>Connect accounts</b>")
                text.append("")
                text.append("Connect Spotify and/or Last.fm so the bot can show/share music in inline mode.")
                text.append("")
                text.append("Spotify usage: open inline and mention the bot with empty query.")
                text.append("Last.fm: send <code>/login USERNAME</code>.")

            kb = await _login_kb(user.id, lang)
            await safe_reply_html(message, "\n".join(text), reply_markup=kb, disable_notification=True)
            return
        
        lastfm_username = command.args.strip()
        await set_lastfm_username(user.id, lastfm_username)
        
        text = i18n.get("login_success", lang, username=lastfm_username)
        await safe_reply(message, text, disable_notification=True)
        logger.info(f"User {user.id} linked Last.fm account: {lastfm_username}")
        await increment_request_count(user.id)
    except Exception as e:
        logger.error(f"Error in /login: {e}")
        await safe_reply(message, "Error processing command", disable_notification=True)


@user_router.callback_query(F.data.startswith("login:"))
async def cb_login(call: types.CallbackQuery):
    user = call.from_user
    from services.database.repo import get_user_language

    lang = await get_user_language(user.id)
    action = (call.data or "").split(":", 1)[1]

    if action == "lastfm":
        lf = await get_lastfm_username(user.id)
        await call.answer("OK")
        if lf:
            await safe_reply_html(call.message, (f"✅ Last.fm подключен: <code>{_h(lf)}</code>" if lang == "ru" else f"✅ Last.fm connected: <code>{_h(lf)}</code>"), disable_notification=True)
        else:
            await safe_reply_html(call.message, ("Отправь <code>/login USERNAME</code>, чтобы подключить Last.fm." if lang == "ru" else "Send <code>/login USERNAME</code> to connect Last.fm."), disable_notification=True)
        return

    if action in ("spotify",):
        # If connected: show profile and quick usage hint.
        tok = await get_user_oauth_token(user.id, "spotify")
        if tok:
            label = await _spotify_profile_label(user.id)
            await call.answer("OK")
            await safe_reply_html(
                call.message,
                (
                    f"✅ Spotify подключен: <code>{_h(label or 'connected')}</code>\n\nИспользование: открой inline и упомяни бота без текста."
                    if lang == "ru"
                    else f"✅ Spotify connected: <code>{_h(label or 'connected')}</code>\n\nUsage: open inline and mention the bot with empty query."
                ),
                disable_notification=True,
            )
            return

        if not config.PUBLIC_BASE_URL:
            await call.answer("OK")
            await safe_reply(
                (
                    "Не задан PUBLIC_BASE_URL/TEST_PUBLIC_BASE_URL (адрес туннеля).\n"
                    "Сначала подними Cloudflare Tunnel/ngrok и запиши URL в .env.\n"
                    "См: docs/api_tokens.md"
                    if lang == "ru"
                    else "PUBLIC_BASE_URL/TEST_PUBLIC_BASE_URL is empty (tunnel URL). Set it in .env first. See docs/api_tokens.md"
                ),
                disable_notification=True,
            )
            return

        svc = action

        if svc == "spotify":
            if not config.SPOTIFY_CLIENT_ID or not config.SPOTIFY_CLIENT_SECRET:
                await call.answer("OK")
                await safe_reply(
                    ("Не заданы SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET (или TEST_* в тесте)." if lang == "ru" else "Missing SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET (or TEST_* in test mode)."),
                    disable_notification=True,
                )
                return
            state = await create_oauth_state(user.id, "spotify")
            url = build_spotify_authorize_url(state)
            await call.answer("OK")
            await safe_reply(
                (
                    "Открой ссылку и разреши доступ:\n" + url + "\n\n"
                    f"Redirect URI в Spotify должен быть: {config.PUBLIC_BASE_URL}/oauth/spotify/callback"
                    if lang == "ru"
                    else "Open this URL to connect Spotify:\n" + url + f"\n\nRedirect URI must be: {config.PUBLIC_BASE_URL}/oauth/spotify/callback"
                ),
                disable_notification=True,
            )
            return


@user_router.message(Command("links"))
async def cmd_links(message: types.Message):
    """Toggle per-user links in inline-audio captions."""
    user = message.from_user
    if await is_user_banned(user.id):
        await message.reply("You are banned from using this bot.", disable_notification=True)
        return

    from services.database.repo import get_user_language
    lang = await get_user_language(user.id)

    parts = (message.text or "").strip().split(maxsplit=1)
    arg = parts[1].strip().lower() if len(parts) > 1 else ""

    current = await get_user_pref_bool(user.id, "links", default=True)
    if not arg:
        new_value = not current
    elif arg in ("on", "1", "true", "yes", "y"):
        new_value = True
    elif arg in ("off", "0", "false", "no", "n"):
        new_value = False
    else:
        await message.reply(
            ("Использование: /links [on|off]" if lang == "ru" else "Usage: /links [on|off]"),
            disable_notification=True,
        )
        return

    await set_user_pref_bool(user.id, "links", new_value)
    await message.reply(
        ("🔗 Ссылки: включены" if new_value else "🔗 Ссылки: выключены") if lang == "ru" else ("🔗 Links: ON" if new_value else "🔗 Links: OFF"),
        disable_notification=True,
    )


@user_router.message(Command("language"))
async def cmd_language(message: types.Message):
    """Toggle language: /language"""
    try:
        user = message.from_user
        is_banned = await is_user_banned(user.id)
        
        if is_banned:
            await safe_reply(message, "You are banned from using this bot.", disable_notification=True)
            return
        
        from services.localization import i18n
        
        # Get current language
        current_lang = await get_user_language(user.id)
        
        # Toggle language
        new_lang = "ru" if current_lang == "en" else "en"
        await set_user_language(user.id, new_lang)
        
        # Prepare confirmation message
        if new_lang == "en":
            text = "✅ Language set to English"
        else:
            text = "✅ Язык установлен на русский"
        
        await safe_reply(message, text, disable_notification=True)
        logger.info(f"User {user.id} switched language from {current_lang} to {new_lang}")
        await increment_request_count(user.id)
    except Exception as e:
        logger.error(f"Error in /language: {e}")
        await safe_reply(message, "Error processing command", disable_notification=True)