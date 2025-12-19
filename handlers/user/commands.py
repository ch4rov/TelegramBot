# -*- coding: utf-8 -*-
import logging
from aiogram import types, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from handlers.user.router import user_router
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
from services.oauth_server import build_spotify_authorize_url, build_yandex_authorize_url

logger = logging.getLogger(__name__)


def _login_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎧 Spotify", callback_data="login:spotify"),
                InlineKeyboardButton(text="🟡 Yandex", callback_data="login:yandex"),
            ],
            [
                InlineKeyboardButton(text="📎 Статус", callback_data="login:status"),
                InlineKeyboardButton(text="🔌 Отключить", callback_data="login:unlink"),
            ],
        ]
    )

@user_router.message(Command("login"))
async def cmd_login(message: types.Message, command: CommandObject):
    """Login menu: Last.fm username + Spotify/Yandex connect."""
    try:
        user = message.from_user
        is_banned = await is_user_banned(user.id)
        
        if is_banned:
            await message.answer("You are banned from using this bot.", disable_notification=True)
            return
        
        # Получаем язык пользователя
        from services.database.repo import get_user_language
        from services.localization import i18n
        lang = await get_user_language(user.id)
        
        if not command.args:
            lastfm_user = await get_lastfm_username(user.id)
            text = []
            if lang == "ru":
                text.append("<b>Подключения</b>")
                text.append("")
                text.append(f"Last.fm: <code>{lastfm_user or '—'}</code>")
                text.append("")
                text.append("Last.fm: <code>/login USERNAME</code>")
                text.append("Spotify/Yandex: кнопками ниже")
                text.append("")
                text.append("Команды: <code>/now</code> (сейчас играет), <code>/recent</code> (последние 3)")
            else:
                text.append("<b>Connections</b>")
                text.append("")
                text.append(f"Last.fm: <code>{lastfm_user or '—'}</code>")
                text.append("")
                text.append("Last.fm: <code>/login USERNAME</code>")
                text.append("Spotify/Yandex: use buttons")
                text.append("")
                text.append("Commands: <code>/now</code> (now playing), <code>/recent</code> (last 3)")

            await message.answer("\n".join(text), reply_markup=_login_kb(), disable_notification=True, parse_mode="HTML")
            return
        
        lastfm_username = command.args.strip()
        await set_lastfm_username(user.id, lastfm_username)
        
        text = i18n.get("login_success", lang, username=lastfm_username)
        await message.answer(text, disable_notification=True)
        logger.info(f"User {user.id} linked Last.fm account: {lastfm_username}")
        await increment_request_count(user.id)
    except Exception as e:
        logger.error(f"Error in /login: {e}")
        await message.answer("Error processing command", disable_notification=True)


@user_router.callback_query(F.data.startswith("login:"))
async def cb_login(call: types.CallbackQuery):
    user = call.from_user
    from services.database.repo import get_user_language
    from services.localization import i18n

    lang = await get_user_language(user.id)
    action = (call.data or "").split(":", 1)[1]

    if action == "status":
        sp = await get_user_oauth_token(user.id, "spotify")
        ya = await get_user_oauth_token(user.id, "yandex")
        lf = await get_lastfm_username(user.id)
        lines = []
        lines.append("<b>Статус</b>" if lang == "ru" else "<b>Status</b>")
        lines.append("")
        lines.append(f"Last.fm: <code>{lf or '—'}</code>")
        lines.append(f"Spotify: {'✅' if sp else '—'}")
        lines.append(f"Yandex: {'✅' if ya else '—'}")
        await call.answer("OK")
        await call.message.answer("\n".join(lines), disable_notification=True, parse_mode="HTML")
        return

    if action == "unlink":
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Spotify", callback_data="login:unlink:spotify"),
                    InlineKeyboardButton(text="Yandex", callback_data="login:unlink:yandex"),
                ]
            ]
        )
        await call.answer("OK")
        await call.message.answer("Что отключить?" if lang == "ru" else "What to unlink?", reply_markup=kb)
        return

    if action.startswith("unlink:"):
        svc = action.split(":", 1)[1]
        await delete_user_oauth_token(user.id, svc)
        await call.answer("OK")
        await call.message.answer(f"✅ Unlinked {svc}")
        return

    if action in ("spotify", "yandex"):
        if not config.PUBLIC_BASE_URL:
            await call.answer("OK")
            await call.message.answer(
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
                await call.message.answer(
                    ("Не заданы SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET (или TEST_* в тесте)." if lang == "ru" else "Missing SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET (or TEST_* in test mode)."),
                    disable_notification=True,
                )
                return
            state = await create_oauth_state(user.id, "spotify")
            url = build_spotify_authorize_url(state)
            await call.answer("OK")
            await call.message.answer(
                (
                    "Открой ссылку и разреши доступ:\n" + url + "\n\n"
                    f"Redirect URI в Spotify должен быть: {config.PUBLIC_BASE_URL}/oauth/spotify/callback"
                    if lang == "ru"
                    else "Open this URL to connect Spotify:\n" + url + f"\n\nRedirect URI must be: {config.PUBLIC_BASE_URL}/oauth/spotify/callback"
                ),
                disable_notification=True,
            )
            return

        if svc == "yandex":
            if not config.YANDEX_CLIENT_ID or not config.YANDEX_CLIENT_SECRET:
                await call.answer("OK")
                await call.message.answer(
                    ("Не заданы YANDEX_CLIENT_ID/YANDEX_CLIENT_SECRET (или TEST_* в тесте)." if lang == "ru" else "Missing YANDEX_CLIENT_ID/YANDEX_CLIENT_SECRET (or TEST_* in test mode)."),
                    disable_notification=True,
                )
                return
            state = await create_oauth_state(user.id, "yandex")
            url = build_yandex_authorize_url(state)
            await call.answer("OK")
            await call.message.answer(
                (
                    "Открой ссылку и разреши доступ:\n" + url + "\n\n"
                    f"Redirect URI в Yandex должен быть: {config.PUBLIC_BASE_URL}/oauth/yandex/callback"
                    if lang == "ru"
                    else "Open this URL to connect Yandex:\n" + url + f"\n\nRedirect URI must be: {config.PUBLIC_BASE_URL}/oauth/yandex/callback"
                ),
                disable_notification=True,
            )
            return


@user_router.message(Command("now"))
async def cmd_now(message: types.Message):
    """Now playing (best-effort): Spotify if connected, otherwise Last.fm recent."""
    user = message.from_user
    if await is_user_banned(user.id):
        await message.answer("You are banned from using this bot.", disable_notification=True)
        return

    from services.database.repo import get_user_language
    lang = await get_user_language(user.id)

    # Spotify support is gated behind OAuth; we fall back to Last.fm for now.
    lfm = await get_lastfm_username(user.id)
    if not lfm:
        await message.answer("Подключи Last.fm через /login" if lang == "ru" else "Connect Last.fm via /login")
        return

    try:
        t = await get_user_recent_track(lfm)
    except Exception:
        t = None

    if not t:
        await message.answer("Ничего не найдено" if lang == "ru" else "Nothing found")
        return

    title = t.get("query") or "Now playing"
    await message.answer(f"🎵 {title}", disable_notification=True)


@user_router.message(Command("recent"))
async def cmd_recent(message: types.Message):
    """Last 3 tracks (best-effort): currently uses Last.fm only."""
    user = message.from_user
    if await is_user_banned(user.id):
        await message.answer("You are banned from using this bot.", disable_notification=True)
        return

    from services.database.repo import get_user_language
    lang = await get_user_language(user.id)
    lfm = await get_lastfm_username(user.id)
    if not lfm:
        await message.answer("Подключи Last.fm через /login" if lang == "ru" else "Connect Last.fm via /login")
        return

    # Existing lastfm_service currently supports one recent track; show that as a minimal step.
    try:
        t = await get_user_recent_track(lfm)
    except Exception:
        t = None

    if not t:
        await message.answer("Ничего не найдено" if lang == "ru" else "Nothing found")
        return

    await message.answer(f"🎵 {t.get('query')}", disable_notification=True)

@user_router.message(Command("addcookies"))
async def cmd_addcookies(message: types.Message):
    """Add cookies command"""
    try:
        user = message.from_user
        is_banned = await is_user_banned(user.id)
        
        if is_banned:
            await message.answer("You are banned from using this bot.", disable_notification=True)
            return
        
        text = (
            "Cookies allow the bot to access restricted content.\n\n"
            "This feature is under construction.\n"
            "Supported platforms: YouTube, TikTok, VK, Instagram"
        )
        await message.answer(text, disable_notification=True)
        logger.info(f"User {user.id} used /addcookies")
        await increment_request_count(user.id)
    except Exception as e:
        logger.error(f"Error in /addcookies: {e}")

@user_router.message(Command("language"))
async def cmd_language(message: types.Message):
    """Toggle language: /language"""
    try:
        user = message.from_user
        is_banned = await is_user_banned(user.id)
        
        if is_banned:
            await message.answer("You are banned from using this bot.", disable_notification=True)
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
        
        await message.answer(text, disable_notification=True)
        logger.info(f"User {user.id} switched language from {current_lang} to {new_lang}")
        await increment_request_count(user.id)
    except Exception as e:
        logger.error(f"Error in /language: {e}")
        await message.answer("Error processing command", disable_notification=True)