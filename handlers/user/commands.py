# -*- coding: utf-8 -*-
import logging
import json
import html
from aiogram import types, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import BufferedInputFile
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
from services.oauth_server import build_spotify_authorize_url
from services.spotify_service import spotify_dump_all, spotify_get_json
from services.database.repo import get_user_pref_bool, set_user_pref_bool
from services.placeholder_service import upload_temp_audio_placeholder
from services.inline_presets import store_inline_preset

logger = logging.getLogger(__name__)


def _h(s: object) -> str:
    return html.escape("" if s is None else str(s))


def _login_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎧 Spotify", callback_data="login:spotify"),
            ],
            [
                InlineKeyboardButton(text="📎 Статус", callback_data="login:status"),
                InlineKeyboardButton(text="🔌 Отключить", callback_data="login:unlink"),
            ],
        ]
    )

@user_router.message(Command("login"))
async def cmd_login(message: types.Message, command: CommandObject):
    """Login menu: Last.fm username + Spotify connect."""
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
                text.append("Spotify: кнопкой ниже")
                text.append("")
                text.append("Команды: <code>/now</code> (сейчас играет), <code>/recent</code> (последние 3)")
            else:
                text.append("<b>Connections</b>")
                text.append("")
                text.append(f"Last.fm: <code>{lastfm_user or '—'}</code>")
                text.append("")
                text.append("Last.fm: <code>/login USERNAME</code>")
                text.append("Spotify: use the button")
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
        lf = await get_lastfm_username(user.id)
        lines = []
        lines.append("<b>Статус</b>" if lang == "ru" else "<b>Status</b>")
        lines.append("")
        lines.append(f"Last.fm: <code>{lf or '—'}</code>")
        lines.append(f"Spotify: {'✅' if sp else '—'}")
        await call.answer("OK")
        await call.message.answer("\n".join(lines), disable_notification=True, parse_mode="HTML")
        return

    if action == "unlink":
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Spotify", callback_data="login:unlink:spotify"),
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

    if action in ("spotify",):
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



@user_router.message(Command("now"))
async def cmd_now(message: types.Message):
    """Now playing (best-effort): Spotify if connected, otherwise Last.fm recent."""
    user = message.from_user
    if await is_user_banned(user.id):
        await message.answer("You are banned from using this bot.", disable_notification=True)
        return

    from services.database.repo import get_user_language
    lang = await get_user_language(user.id)

    # Prefer Spotify if connected
    tracks: list[dict] = []
    try:
        tok = await get_user_oauth_token(user.id, "spotify")
    except Exception:
        tok = None

    if tok:
        now = await spotify_get_json(user.id, "https://api.spotify.com/v1/me/player/currently-playing")
        recent = await spotify_get_json(user.id, "https://api.spotify.com/v1/me/player/recently-played", params={"limit": 3})

        def _track_from_item(item: dict, emoji: str) -> dict | None:
            if not isinstance(item, dict):
                return None
            artists = item.get("artists")
            artist = " & ".join([a.get("name") for a in artists if isinstance(a, dict) and a.get("name")]) if isinstance(artists, list) else None
            name = item.get("name")
            url = (item.get("external_urls") or {}).get("spotify") if isinstance(item.get("external_urls"), dict) else None
            if not (name and url):
                return None
            return {"artist": artist or "Spotify", "title": str(name), "url": str(url), "emoji": emoji}

        # Now playing
        try:
            if isinstance(now, dict) and now.get("status") == 200 and isinstance(now.get("data"), dict):
                item = now["data"].get("item")
                t = _track_from_item(item, "▶️")
                if t:
                    tracks.append(t)
        except Exception:
            pass

        # Recent (fill up to 3)
        try:
            data = recent.get("data") if isinstance(recent, dict) else None
            items = data.get("items") if isinstance(data, dict) else None
            if isinstance(items, list):
                for it in items:
                    tr = it.get("track") if isinstance(it, dict) else None
                    t = _track_from_item(tr, "🎧")
                    if not t:
                        continue
                    if any(x.get("url") == t.get("url") for x in tracks):
                        continue
                    tracks.append(t)
                    if len(tracks) >= 3:
                        break
        except Exception:
            pass

    if tracks:
        preset_items: list[dict] = []
        for t in tracks[:3]:
            file_id = None
            msg_id = None
            chat_id = None
            try:
                file_id, msg_id, chat_id = await upload_temp_audio_placeholder(
                    title=(f"{t.get('emoji', '🎧')} {t.get('title', '')}".strip() if t.get('title') else None),
                    performer=t.get("artist"),
                )
                if file_id:
                    preset_items.append({"url": t.get("url"), "file_id": file_id})
            finally:
                if chat_id and msg_id:
                    try:
                        from core.loader import bot
                        await bot.delete_message(chat_id, msg_id)
                    except Exception:
                        pass

        if preset_items:
            token = store_inline_preset(user.id, preset_items, ttl_seconds=180)
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=("📤 Отправить трек" if lang == "ru" else "📤 Share track"),
                            switch_inline_query=f"sp:{token}",
                        )
                    ]
                ]
            )
            await message.answer(
                ("Выбери трек в inline-списке:" if lang == "ru" else "Pick a track in the inline list:"),
                reply_markup=kb,
                disable_notification=True,
            )
            return

    # Fallback to Last.fm (text only)
    lfm = await get_lastfm_username(user.id)
    if not lfm:
        await message.answer(
            ("Подключи Spotify или Last.fm через /login" if lang == "ru" else "Connect Spotify or Last.fm via /login"),
            disable_notification=True,
        )
        return

    try:
        t = await get_user_recent_track(lfm)
    except Exception:
        t = None

    if not t:
        await message.answer("Ничего не найдено" if lang == "ru" else "Nothing found", disable_notification=True)
        return

    title = t.get("query") or "Now playing"
    await message.answer(f"🎵 {title}", disable_notification=True)


@user_router.message(Command("links"))
async def cmd_links(message: types.Message):
    """Toggle per-user links in inline-audio captions."""
    user = message.from_user
    if await is_user_banned(user.id):
        await message.answer("You are banned from using this bot.", disable_notification=True)
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
        await message.answer(
            ("Использование: /links [on|off]" if lang == "ru" else "Usage: /links [on|off]"),
            disable_notification=True,
        )
        return

    await set_user_pref_bool(user.id, "links", new_value)
    await message.answer(
        ("🔗 Ссылки: включены" if new_value else "🔗 Ссылки: выключены") if lang == "ru" else ("🔗 Links: ON" if new_value else "🔗 Links: OFF"),
        disable_notification=True,
    )


@user_router.message(Command("recent"))
async def cmd_recent(message: types.Message):
    """Last 3 tracks (best-effort): Spotify if connected, otherwise Last.fm (single track)."""
    user = message.from_user
    if await is_user_banned(user.id):
        await message.answer("You are banned from using this bot.", disable_notification=True)
        return

    from services.database.repo import get_user_language
    lang = await get_user_language(user.id)
    # Prefer Spotify if connected
    tracks: list[dict] = []
    try:
        tok = await get_user_oauth_token(user.id, "spotify")
    except Exception:
        tok = None

    if tok:
        recent = await spotify_get_json(user.id, "https://api.spotify.com/v1/me/player/recently-played", params={"limit": 3})

        def _track_from_item(item: dict) -> dict | None:
            if not isinstance(item, dict):
                return None
            artists = item.get("artists")
            artist = " & ".join([a.get("name") for a in artists if isinstance(a, dict) and a.get("name")]) if isinstance(artists, list) else None
            name = item.get("name")
            url = (item.get("external_urls") or {}).get("spotify") if isinstance(item.get("external_urls"), dict) else None
            if not (name and url):
                return None
            return {"artist": artist or "Spotify", "title": str(name), "url": str(url), "emoji": "🎧"}

        try:
            data = recent.get("data") if isinstance(recent, dict) else None
            items = data.get("items") if isinstance(data, dict) else None
            if isinstance(items, list):
                for it in items:
                    tr = it.get("track") if isinstance(it, dict) else None
                    t = _track_from_item(tr)
                    if t:
                        tracks.append(t)
        except Exception:
            pass

    if tracks:
        preset_items: list[dict] = []
        for t in tracks[:3]:
            file_id = None
            msg_id = None
            chat_id = None
            try:
                file_id, msg_id, chat_id = await upload_temp_audio_placeholder(
                    title=(f"{t.get('emoji', '🎧')} {t.get('title', '')}".strip() if t.get('title') else None),
                    performer=t.get("artist"),
                )
                if file_id:
                    preset_items.append({"url": t.get("url"), "file_id": file_id})
            finally:
                if chat_id and msg_id:
                    try:
                        from core.loader import bot
                        await bot.delete_message(chat_id, msg_id)
                    except Exception:
                        pass

        if preset_items:
            token = store_inline_preset(user.id, preset_items, ttl_seconds=180)
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=("📤 Отправить (3)" if lang == "ru" else "📤 Share (3)"),
                            switch_inline_query=f"sp:{token}",
                        )
                    ]
                ]
            )
            await message.answer(
                ("Выбери трек в inline-списке:" if lang == "ru" else "Pick a track in the inline list:"),
                reply_markup=kb,
                disable_notification=True,
            )
            return

    # Fallback to Last.fm (text only)
    lfm = await get_lastfm_username(user.id)
    if not lfm:
        await message.answer(
            ("Подключи Spotify или Last.fm через /login" if lang == "ru" else "Connect Spotify or Last.fm via /login"),
            disable_notification=True,
        )
        return

    try:
        t = await get_user_recent_track(lfm)
    except Exception:
        t = None

    if not t:
        await message.answer("Ничего не найдено" if lang == "ru" else "Nothing found", disable_notification=True)
        return

    await message.answer(f"🎵 {t.get('query')}", disable_notification=True)


@user_router.message(Command("apis"))
async def cmd_apis(message: types.Message):
    """Dump raw API responses for Spotify/Last.fm (separately).

    Sends JSON as documents to avoid Telegram message length limits.
    """
    user = message.from_user
    if await is_user_banned(user.id):
        await message.answer("You are banned from using this bot.", disable_notification=True)
        return

    from services.database.repo import get_user_language
    lang = await get_user_language(user.id)

    await message.answer(
        "Собираю данные API (Spotify/Last.fm)…" if lang == "ru" else "Fetching API data (Spotify/Last.fm)…",
        disable_notification=True,
    )

    # Spotify
    try:
        sp = await spotify_dump_all(user.id)
    except Exception as e:
        logger.exception("/apis spotify failed")
        sp = {"error": "spotify_exception", "detail": str(e)}

    # Last.fm (raw)
    try:
        lfm_user = await get_lastfm_username(user.id)
        if not lfm_user:
            lf = {"error": "lastfm_not_connected"}
        else:
            # Existing helper returns parsed single track; keep it as-is for now.
            lf = {"user": lfm_user, "recent_track": await get_user_recent_track(lfm_user)}
    except Exception as e:
        logger.exception("/apis lastfm failed")
        lf = {"error": "lastfm_exception", "detail": str(e)}

    bundles = [
        ("spotify.json", sp),
        ("lastfm.json", lf),
    ]

    for filename, payload in bundles:
        try:
            data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            await message.answer_document(
                BufferedInputFile(data, filename=filename),
                caption=filename,
                disable_notification=True,
            )
        except Exception:
            logger.exception("Failed sending %s", filename)


@user_router.message(Command("api"))
async def cmd_api(message: types.Message):
    """Human-readable API status (RU only)."""
    user = message.from_user
    if await is_user_banned(user.id):
        await message.answer("Вы заблокированы.", disable_notification=True)
        return

    # Status flags
    sp_tok = await get_user_oauth_token(user.id, "spotify")
    lf_user = await get_lastfm_username(user.id)

    lines: list[str] = []
    lines.append("<b>API статус</b>")
    lines.append("")
    lines.append(f"Spotify: {'✅' if sp_tok else '—'}")
    lines.append(f"Last.fm: <code>{_h(lf_user or '—')}</code>")
    lines.append("")

    # Spotify details
    if sp_tok:
        try:
            sp = await spotify_dump_all(user.id)
        except Exception as e:
            sp = {"error": str(e)}

        me = (sp.get("me") or {}).get("data") if isinstance(sp, dict) else None
        if isinstance(me, dict) and me.get("id"):
            lines.append("<b>Spotify</b>")
            lines.append(f"Профиль: <code>{_h(me.get('display_name') or me.get('id'))}</code>")
        else:
            lines.append("<b>Spotify</b>")
            err = (sp.get("me") or {}).get("data") if isinstance(sp, dict) else None
            lines.append(f"Профиль: ошибка/нет доступа ({_h(err)})")

        now = (sp.get("currently_playing") or {}).get("data") if isinstance(sp, dict) else None
        if isinstance(now, dict) and now.get("item"):
            item = now.get("item") or {}
            artists = ", ".join([a.get("name", "") for a in (item.get("artists") or []) if isinstance(a, dict)])
            title = item.get("name")
            is_playing = now.get("is_playing")
            lines.append(f"Сейчас играет: <code>{_h(artists)} - {_h(title)}</code> {'▶️' if is_playing else ''}")
        elif isinstance((sp.get("currently_playing") or {}).get("status"), int) and (sp.get("currently_playing") or {}).get("status") == 204:
            lines.append("Сейчас играет: —")
        else:
            lines.append("Сейчас играет: —")

        recent = (sp.get("recently_played") or {}).get("data") if isinstance(sp, dict) else None
        if isinstance(recent, dict) and isinstance(recent.get("items"), list):
            items = recent.get("items")[:3]
            rec_lines = []
            for it in items:
                tr = (it or {}).get("track") or {}
                artists = ", ".join([a.get("name", "") for a in (tr.get("artists") or []) if isinstance(a, dict)])
                title = tr.get("name")
                if artists or title:
                    rec_lines.append(f"- {_h(artists)} - {_h(title)}")
            if rec_lines:
                lines.append("Последние 3:")
                lines.extend(rec_lines)

        lines.append("")

    # Last.fm details
    if lf_user:
        try:
            t = await get_user_recent_track(lf_user)
        except Exception:
            t = None

        lines.append("<b>Last.fm</b>")
        if t and t.get("query"):
            np = " (сейчас играет)" if t.get("now_playing") else ""
            lines.append(f"Последний трек: <code>{_h(t.get('query'))}</code>{np}")
        else:
            lines.append("Последний трек: —")

    lines.append("")
    lines.append("Сырые ответы: /apis")

    await message.answer("\n".join(lines), disable_notification=True, parse_mode="HTML")


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