# -*- coding: utf-8 -*-
import os
import shutil
import uuid
import asyncio
import html
import logging
from aiogram import Router, types
from aiogram.types import (
    InlineQueryResultCachedVideo, 
    InlineQueryResultCachedAudio, 
    InlineQueryResultArticle,
    InputTextMessageContent,
    InputMediaVideo, 
    InputMediaAudio, 
    FSInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

# --- V3.0 IMPORTS ---
from core.loader import bot
from core.config import config
from services.platforms.platform_manager import download_content, is_valid_url 
from services.placeholder_service import get_placeholder 
from services.database.repo import (
    get_user,
    get_module_status,
    get_cached_media,
    upsert_cached_media,
    log_user_request,
    get_user_pref_bool,
)
from services.lastfm_service import get_user_recent_track
from services.spotify_service import spotify_get_json
from services.search_service import search_music
from services.odesli_service import get_links_by_url
from services.inline_presets import get_inline_preset, get_inline_preset_item, store_inline_preset
from services.placeholder_service import upload_temp_audio_placeholder

router = Router()

logger = logging.getLogger(__name__)

INLINE_SEARCH_CACHE = {}
INLINE_LINK_MODE_CACHE = {}
# Лимиты (Telegram Bot API)
LIMIT_PUBLIC = 49 * 1024 * 1024       # 50 MB
LIMIT_LOCAL = 1990 * 1024 * 1024      # 2 GB (Local Server)

def clean_cache():
    """Очистка старого кэша поиска"""
    if len(INLINE_SEARCH_CACHE) > 1000:
        INLINE_SEARCH_CACHE.clear()

def get_clip_keyboard(url: str):
    """Клавиатура для видео, если доступно"""
    if "music.youtube.com" in url or "youtu" in url:
        video_id = None
        if "v=" in url: 
            try: video_id = url.split("v=")[1].split("&")[0]
            except: pass
        elif "youtu.be/" in url: 
            try: video_id = url.split("youtu.be/")[1].split("?")[0]
            except: pass
        
        if video_id:
            return InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🎬 Video / Clip", callback_data=f"get_clip:{video_id}")
            ]])
    return None


def _is_music_like_url(url: str) -> bool:
    u = (url or "").lower()
    return (
        "music.youtube.com" in u
        or "open.spotify.com" in u
        or "soundcloud.com" in u
    )


def _platform_label(url: str) -> str:
    u = (url or "").lower()
    if "open.spotify.com" in u:
        return "Spotify"
    if "music.yandex" in u:
        return "Yandex Music"
    if "music.apple.com" in u or "itunes.apple.com" in u:
        return "Apple Music"
    if "soundcloud.com" in u:
        return "SoundCloud"
    if "music.youtube.com" in u:
        return "YouTube Music"
    if "youtu" in u:
        return "YouTube"
    return "Link"


async def _build_inline_audio_caption(user_id: int, source_url: str) -> tuple[str | None, str | None]:
    """Return (caption, parse_mode). When links are disabled, caption is None."""
    try:
        enabled = await get_user_pref_bool(user_id, "links", default=True)
    except Exception:
        enabled = False

    if not enabled:
        return None, None

    platform = _platform_label(source_url)
    page_url = None
    try:
        info = await get_links_by_url(source_url)
        if isinstance(info, dict):
            page_url = info.get("page")
    except Exception:
        page_url = None

    if page_url:
        return f"{platform} | <a href=\"{html.escape(page_url)}\">Other (song.link)</a>", "HTML"
    return f"{platform} | Other (song.link)", None

@router.inline_query()
async def inline_query_handler(query: types.InlineQuery):
    text = query.query.strip()
    user_id = query.from_user.id
    results = []
    clean_cache()

    user_db = None
    try:
        user_db = await get_user(user_id)
    except Exception:
        user_db = None
    user_lang = (getattr(user_db, "language", None) or query.from_user.language_code or "en").lower()
    is_ru = user_lang.startswith("ru")

    # Получаем placeholder'ы (file_id уже загруженных заглушек)
    video_ph = await get_placeholder('video')
    audio_ph = await get_placeholder('audio_ru' if is_ru else 'audio_en')
    if not audio_ph:
        audio_ph = await get_placeholder('audio')
    
    # Inline-video and inline-audio both rely on placeholders.
    # If video placeholder is missing, we still allow audio-only mode.
    if not audio_ph:
        results.append(InlineQueryResultArticle(
            id="inline_not_ready",
            title="⚠️ Inline is not ready",
            description="Placeholders are not configured yet",
            input_message_content=InputTextMessageContent(
                message_text="⚠️ Inline mode is initializing. Try again in a few seconds."
            )
        ))
        try:
            await query.answer(results, cache_time=1, is_personal=True)
        except Exception:
            pass
        return

    # 0. Presets (internal tokens)
    if text.lower().startswith("sp:"):
        token = text.split(":", 1)[1].strip()
        items = get_inline_preset(user_id, token)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏳", callback_data="processing")]])

        if items:
            for idx, it in enumerate(items[:3]):
                file_id = (it or {}).get("file_id") if isinstance(it, dict) else None
                if not file_id:
                    continue
                results.append(
                    InlineQueryResultCachedAudio(
                        id=f"preset:{token}:{idx}",
                        audio_file_id=file_id,
                        caption="⏳",
                        reply_markup=keyboard,
                    )
                )

        if not results:
            results.append(
                InlineQueryResultArticle(
                    id="preset_expired",
                    title=("⏱ Истекло" if is_ru else "⏱ Expired"),
                    description=("Открой inline заново" if is_ru else "Open inline again"),
                    input_message_content=InputTextMessageContent(
                        message_text=("Открой inline заново" if is_ru else "Open inline again")
                    ),
                )
            )

        try:
            await query.answer(results, cache_time=1, is_personal=True)
        except Exception:
            pass
        return

    # 1. Режим скачивания по ссылке
    if text and is_valid_url(text):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏳", callback_data="processing")]])

        # Inline-video: only in link mode, only for allowed links, only if module enabled.
        if video_ph and await get_module_status("InlineVideo"):
            qid = str(uuid.uuid4())
            INLINE_LINK_MODE_CACHE[qid] = "video"
            title = "Скачать видео" if is_ru else "Download a video.."
            results.append(
                InlineQueryResultCachedVideo(
                    id=f"link:video:{qid}",
                    video_file_id=video_ph,
                    title=title,
                    description=text,
                    caption="⏳",
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
            )

        # Audio option is shown only for music-like links.
        if _is_music_like_url(text) and await get_module_status("InlineAudio"):
            qid = str(uuid.uuid4())
            INLINE_LINK_MODE_CACHE[qid] = "audio"
            # CachedAudio doesn't support title/description; we localize via placeholder audio metadata.
            results.append(InlineQueryResultCachedAudio(
                id=f"link:audio:{qid}",
                audio_file_id=audio_ph,
                caption="⏳",
                reply_markup=keyboard,
            ))

        if not results:
            results.append(
                InlineQueryResultArticle(
                    id="inline_disabled",
                    title="⚠️ Inline disabled",
                    description="Inline modules are disabled",
                    input_message_content=InputTextMessageContent(message_text="Inline modules are disabled"),
                )
            )

    # 2. Режим поиска музыки (или Last.fm)
    else:
        if not await get_module_status("InlineAudio"):
            results.append(InlineQueryResultArticle(
                id="inline_audio_disabled",
                title="⚠️ Inline audio disabled",
                description="Module InlineAudio is disabled",
                input_message_content=InputTextMessageContent(message_text="InlineAudio is disabled")
            ))
            try:
                await query.answer(results, cache_time=1, is_personal=True)
            except Exception:
                logger.exception("Inline answer failed (audio disabled)")
            return
            
        search_query = text

        # If empty query: offer Spotify now/recent directly via inline (no /now,/recent commands).
        if not search_query:
            try:
                now = await spotify_get_json(user_id, "https://api.spotify.com/v1/me/player/currently-playing")
                recent = await spotify_get_json(user_id, "https://api.spotify.com/v1/me/player/recently-played", params={"limit": 3})
            except Exception:
                now = None
                recent = None

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

            tracks: list[dict] = []
            try:
                if isinstance(now, dict) and now.get("status") == 200 and isinstance(now.get("data"), dict):
                    t = _track_from_item(now["data"].get("item"), "▶️")
                    if t:
                        tracks.append(t)
            except Exception:
                pass

            try:
                if isinstance(recent, dict) and recent.get("status") == 200 and isinstance(recent.get("data"), dict):
                    items = recent["data"].get("items")
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
                    msg_id = None
                    chat_id = None
                    try:
                        file_id, msg_id, chat_id = await upload_temp_audio_placeholder(
                            title=(f"{t.get('emoji', '🎧')} {t.get('title', '')}".strip() if t.get('title') else "🎧"),
                            performer=t.get("artist"),
                        )
                        if file_id:
                            preset_items.append({"url": t.get("url"), "file_id": file_id})
                    finally:
                        if chat_id and msg_id:
                            try:
                                await bot.delete_message(chat_id, msg_id)
                            except Exception:
                                pass

                if preset_items:
                    token = store_inline_preset(user_id, preset_items, ttl_seconds=180)
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏳", callback_data="processing")]])
                    for idx, it in enumerate(preset_items[:3]):
                        results.append(
                            InlineQueryResultCachedAudio(
                                id=f"preset:{token}:{idx}",
                                audio_file_id=it["file_id"],
                                caption="⏳",
                                reply_markup=keyboard,
                            )
                        )

                    try:
                        await query.answer(results, cache_time=1, is_personal=True)
                    except Exception:
                        pass
                    return
        
        # Если пусто — пробуем взять из Last.fm
        if not search_query:
            lfm = getattr(user_db, 'lastfm_username', None) if user_db else None
            if lfm:
                try:
                    t = await get_user_recent_track(lfm)
                    if t: search_query = t['query']
                except:
                    pass

        if search_query:
            query_id = str(uuid.uuid4())
            INLINE_SEARCH_CACHE[query_id] = search_query
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=f"🔎 {search_query[:25]}...", callback_data="processing")
            ]])
            
            results.append(InlineQueryResultCachedAudio(
                id=f"music:{query_id}", 
                audio_file_id=audio_ph,
                caption=f"🔎 Ищу: {search_query}...", 
                reply_markup=keyboard
            ))
        else:
            # Подсказка про логин
            results.append(InlineQueryResultArticle(
                id="login_hint", 
                title="🔗 Подключить Last.fm", 
                description="Показывает текущий трек в пустом поиске",
                input_message_content=InputTextMessageContent(message_text="Подключить Last.fm: /login")
            ))

    try:
        await query.answer(results, cache_time=2, is_personal=True)
    except Exception:
        logger.exception("Inline answer failed")
        # Fallback: try to answer with a minimal safe result
        try:
            await query.answer([
                InlineQueryResultArticle(
                    id="inline_error",
                    title="⚠️ Inline error",
                    description="Failed to build inline results",
                    input_message_content=InputTextMessageContent(message_text="⚠️ Inline error")
                )
            ], cache_time=1, is_personal=True)
        except Exception:
            pass


@router.chosen_inline_result()
async def chosen_handler(chosen_result: types.ChosenInlineResult):
    result_id = chosen_result.result_id
    inline_msg_id = chosen_result.inline_message_id
    user = chosen_result.from_user
    
    if not inline_msg_id: 
        return

    is_music_mode = result_id.startswith("music:")
    is_link_audio = result_id.startswith("link:audio:")
    is_link_video = result_id.startswith("link:video:")
    is_preset = result_id.startswith("preset:")
    url = None
    
    # === ПОЛУЧЕНИЕ ССЫЛКИ ===
    if is_preset:
        try:
            _, token, idx = result_id.split(":", 2)
            it = get_inline_preset_item(user.id, token, int(idx))
            url = (it or {}).get("url") if isinstance(it, dict) else None
            is_link_audio = True
        except Exception:
            url = None

    elif is_music_mode:
        try:
            query_uuid = result_id.split(":", 1)[1]
            query_text = INLINE_SEARCH_CACHE.get(query_uuid) or chosen_result.query or "Unknown"
            print(f"[INLINE] {user.username}: Audio Search ({query_text})")
            
            # Реальный поиск
            res = await search_music(query_text, limit=1)
            if not res:
                await bot.edit_message_caption(inline_message_id=inline_msg_id, caption=f"❌ Не найдено: {query_text}")
                return
            
            url = res[0]['url']
            # Keep placeholder caption strictly as "⏳"; no intermediate edits.
        except Exception as e:
            print(f"Search Error: {e}")
            return
    else:
        # Это прямая ссылка
        url = chosen_result.query.strip()

    if not url: return

    desired_cache_type = "audio" if (is_music_mode or is_link_audio) else "video"

    # Cache hit: edit inline message without re-downloading.
    try:
        cached = await get_cached_media(user.id, url, desired_cache_type)
    except Exception:
        cached = None

    if cached and cached.file_id:
        try:
            title = (cached.title or "Media").strip()
            caption_text = f'<a href="{url}">{html.escape(title)}</a>'
            caption_mode = "HTML"

            if desired_cache_type == "audio":
                caption_text, caption_mode = await _build_inline_audio_caption(user.id, url)

            if desired_cache_type == "audio":
                new_media = InputMediaAudio(media=cached.file_id, caption=caption_text or "", parse_mode=caption_mode)
            else:
                new_media = InputMediaVideo(media=cached.file_id, caption=caption_text, parse_mode="HTML", supports_streaming=True)

            await bot.edit_message_media(inline_message_id=inline_msg_id, media=new_media)
            try:
                await log_user_request(
                    user.id,
                    kind="inline",
                    input_text=chosen_result.query or "",
                    url=url,
                    media_type=desired_cache_type,
                    title=cached.title,
                    cache_hit=True,
                    cache_id=cached.id,
                )
            except Exception:
                pass
            return
        except Exception:
            # Fall through to download
            pass

    # === НАСТРОЙКИ ЗАГРУЗЧИКА ===
    is_local = config.USE_LOCAL_SERVER
    current_limit = LIMIT_LOCAL if is_local else LIMIT_PUBLIC

    custom_opts = {}
    
    if is_music_mode or is_link_audio:
        custom_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'postprocessors': [],
            'writethumbnail': True,
            'keepvideo': False
        }
    else:
        # Логика качества для видео
        if is_local:
            format_str = 'bestvideo+bestaudio/best' 
        else:
            # Пытаемся уложиться в лимит телеграма
            format_str = 'best[filesize<50M]/bestvideo[filesize<40M]+bestaudio/best[height<=480]/worst'
        
        custom_opts = {
            'format': format_str,
            'merge_output_format': 'mp4'
        }

    # === ЗАГРУЗКА ===
    files, folder_path, error, meta = await download_content(url, custom_opts, user_id=user.id)

    if error:
        try: await bot.edit_message_caption(inline_message_id=inline_msg_id, caption=f"❌ {error}")
        except: pass
        if folder_path: shutil.rmtree(folder_path, ignore_errors=True)
        return

    try:
        # Фильтрация файлов
        media_files = []
        thumb_file = None
        
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.webp']: 
                thumb_file = f
            elif ext in ['.mp4', '.mov', '.mp3', '.m4a', '.ogg', '.wav', '.flac', '.webm']: 
                media_files.append(f)

        if not media_files: 
            raise Exception("No media files found")

        # Если музыка, предпочитаем mp3
        if is_music_mode:
            media_files.sort(key=lambda x: 0 if x.endswith('.mp3') else 1)
        
        target_file = media_files[0]
        ext = os.path.splitext(target_file)[1].lower()
        
        # Проверка размера
        file_size = os.path.getsize(target_file)
        if file_size > current_limit:
            msg = f"⚠️ File too big ({file_size / (1024*1024):.1f} MB)."
            await bot.edit_message_caption(inline_message_id=inline_msg_id, caption=msg)
            return

        # Определение типа отправки
        media_type = 'document'
        if is_music_mode:
            media_type = 'audio'
            # Конвертация в MP3 если странный формат
            if ext not in ['.mp3', '.m4a', '.flac', '.wav', '.ogg']:
                new_path = os.path.splitext(target_file)[0] + ".mp3"
                shutil.move(target_file, new_path)
                target_file = new_path
        else:
            if ext in ['.mp3', '.m4a', '.ogg', '.opus', '.wav', '.flac']:
                media_type = 'audio'
            elif ext in ['.mp4', '.mov', '.mkv', '.webm']:
                media_type = 'video'

        # Метаданные
        filename = os.path.basename(target_file)
        media_obj = FSInputFile(target_file, filename=filename)
        
        meta_title = meta.get('title') if meta else os.path.splitext(filename)[0]
        meta_artist = meta.get('artist') or meta.get('uploader')
        
        caption_text = f'<a href="{url}">{html.escape(meta_title)}</a>'
        caption_mode = "HTML"

        if media_type == 'audio':
            caption_text, caption_mode = await _build_inline_audio_caption(user.id, url)

        # === ОТПРАВКА В ЛС (для получения file_id) ===
        # Inline-режим требует file_id уже загруженного на сервера Telegram файла
        # Поэтому мы отправляем файл самому себе (боту от юзера), получаем ID и удаляем.
        
        sent_msg = None
        telegram_file_id = None

        if media_type == 'audio':
            thumb = FSInputFile(thumb_file) if thumb_file else None
            performer = meta_artist or "@bot"
            sent_msg = await bot.send_audio(
                user.id, media_obj, caption=caption_text or "", parse_mode=caption_mode,
                thumbnail=thumb, performer=performer, title=meta_title,
                reply_markup=get_clip_keyboard(url)
            )
            telegram_file_id = sent_msg.audio.file_id
        
        elif media_type == 'video':
            sent_msg = await bot.send_video(
                user.id, media_obj, caption=caption_text, parse_mode="HTML",
                supports_streaming=True
            )
            telegram_file_id = sent_msg.video.file_id
        
        else:
            sent_msg = await bot.send_document(
                user.id, media_obj, caption=caption_text, parse_mode="HTML"
            )
            telegram_file_id = sent_msg.document.file_id

        # === ОБНОВЛЕНИЕ INLINE СООБЩЕНИЯ ===
        if telegram_file_id:
            new_media = None
            if media_type == 'audio': 
                new_media = InputMediaAudio(media=telegram_file_id, caption=caption_text or "", parse_mode=caption_mode)
            elif media_type == 'video': 
                new_media = InputMediaVideo(media=telegram_file_id, caption=caption_text, parse_mode="HTML", supports_streaming=True)
            
            # InputMediaDocument не поддерживается в editMessageMedia для inline messages в некоторых версиях,
            # поэтому для документов просто пишем "Ready" если нельзя заменить медиа.
            # Но Audio/Video работают отлично.
            
            if new_media:
                try: 
                    await bot.edit_message_media(inline_message_id=inline_msg_id, media=new_media)
                except Exception as e:
                    # Fallback
                    await bot.edit_message_caption(inline_message_id=inline_msg_id, caption=f"✅ Ready! (Error edit media: {e})")
            else:
                await bot.edit_message_caption(inline_message_id=inline_msg_id, caption="✅ Sent to chat.")
            
            # Удаляем временное сообщение из ЛС, чтобы не мусорить
            if sent_msg:
                await asyncio.sleep(0.5)
                try: await bot.delete_message(user.id, sent_msg.message_id)
                except: pass

            # Cache + history
            try:
                cache_title = meta_title
                cache = await upsert_cached_media(user.id, url, telegram_file_id, media_type if media_type in ("audio", "video") else desired_cache_type, title=str(cache_title) if cache_title else None)
                await log_user_request(
                    user.id,
                    kind="inline",
                    input_text=chosen_result.query or "",
                    url=url,
                    media_type=media_type if media_type in ("audio", "video") else desired_cache_type,
                    title=str(cache_title) if cache_title else None,
                    cache_hit=False,
                    cache_id=cache.id,
                )
            except Exception:
                pass

    except Exception as e:
        print(f"Inline Processing Error: {e}")
        try: await bot.edit_message_caption(inline_message_id=inline_msg_id, caption="⚠️ Error processing file.")
        except: pass
    finally:
        # Очистка временных файлов
        if folder_path and os.path.exists(folder_path): 
            shutil.rmtree(folder_path, ignore_errors=True)