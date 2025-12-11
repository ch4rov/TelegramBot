import os
import shutil
import json 
import asyncio 
import re
import time
import html
from aiogram import F, types, Bot
from aiogram.types import FSInputFile, InputMediaPhoto, InputMediaVideo, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest

from .router import user_router, check_access_and_update, ACTIVE_DOWNLOADS
from services.database_service import get_cached_file, save_cached_file, get_user_cookie, get_module_status
from logs.logger import send_log_groupable as send_log, log_other_message
from services.platforms.platform_manager import download_content, is_valid_url
from services.platforms.SpotifyDownloader.spotify_strategy import SpotifyStrategy
from services.url_cleaner import clean_url
from services.search_service import search_youtube
from languages import t
import messages as msg 
import settings
from core.queue_manager import queue_manager

# Кэш плейлистов
from uuid import uuid4
import math
PLAYLIST_CACHE = {}

# --- ANTI-FLOOD ДЛЯ СТАТУСОВ ---
LAST_STATUS_TIME = {} 

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

async def safe_api_call(func, *args, **kwargs):
    """
    Выполняет функцию (которая возвращает корутину) с обработкой FloodWait.
    Принимает саму функцию (например message.answer), а не её результат.
    """
    try:
        return await func(*args, **kwargs)
    except TelegramRetryAfter as e:
        print(f"⏳ FloodWait: sleep {e.retry_after}s")
        await asyncio.sleep(e.retry_after)
        # Рекурсивный вызов - создаст новую корутину
        return await safe_api_call(func, *args, **kwargs)
    except Exception as e:
        raise e

def make_caption(title_text, url, override=None, is_audio=False, request_by=None):
    """
    Формирует подпись с поддержкой Odesli и тегом запросившего.
    """
    bot_name = settings.BOT_USERNAME or "ch4roff_bot"
    bot_link = f"@{bot_name}"
    
    platforms_link = ""
    if is_audio and url:
        clean_source = url.split("?")[0] if "?" in url else url
        odesli_url = f"https://song.link/{clean_source}"
        platforms_link = f" | <a href=\"{odesli_url}\">🌐 Links</a>"

    footer_parts = [bot_link, platforms_link]
    if request_by:
        footer_parts.append(f"\n{request_by}")
        
    footer = "".join(footer_parts)

    if override:
        return f"{html.escape(override)}\n\n{footer}"
    
    if not title_text:
        return footer
    
    safe_title = html.escape(title_text)
    return f'<a href="{url}">{safe_title}</a>\n\n{footer}'

def get_clip_keyboard(url: str, user_id: int):
    if "music.youtube.com" in url or "youtu" in url:
        video_id = None
        if "v=" in url: 
            try: video_id = url.split("v=")[1].split("&")[0]
            except: pass
        elif "youtu.be/" in url: 
            try: video_id = url.split("youtu.be/")[1].split("?")[0]
            except: pass
        if video_id:
            return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎬 Video / Clip", callback_data=f"get_clip:{video_id}")]])
    return None

async def send_action_loop(bot: Bot, chat_id: int, action: ChatAction, delay: int = 5):
    try:
        while True:
            try: await bot.send_chat_action(chat_id=chat_id, action=action)
            except: pass
            await asyncio.sleep(delay)
    except asyncio.CancelledError: pass

# --- ЛОГИКА ПЛЕЙЛИСТОВ ---
def generate_playlist_keyboard(playlist_id, page=0):
    data = PLAYLIST_CACHE.get(playlist_id)
    if not data: return None
    tracks = data['tracks']
    ITEMS_PER_PAGE = 5
    total_pages = math.ceil(len(tracks) / ITEMS_PER_PAGE)
    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    current_tracks = tracks[start:end]
    buttons = []
    for track_name in current_tracks:
        cb_data = f"sp_dl:{track_name[:40]}"
        buttons.append([InlineKeyboardButton(text=f"🎵 {track_name[:30]}", callback_data=cb_data)])
    nav_row = []
    if page > 0: nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"sp_nav:{playlist_id}:{page-1}"))
    nav_row.append(InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="ignore"))
    if page < total_pages - 1: nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"sp_nav:{playlist_id}:{page+1}"))
    buttons.append(nav_row)
    buttons.append([InlineKeyboardButton(text="❌ Close", callback_data="delete_msg")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@user_router.callback_query(F.data.startswith("sp_nav:"))
async def handle_playlist_nav(callback: types.CallbackQuery):
    try:
        _, playlist_id, page_str = callback.data.split(":")
        page = int(page_str)
        keyboard = generate_playlist_keyboard(playlist_id, page)
        if not keyboard:
            await callback.answer("⚠️ Menu expired", show_alert=True)
            return
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    except: await callback.answer()

@user_router.callback_query(F.data.startswith("sp_dl:"))
async def handle_playlist_download(callback: types.CallbackQuery):
    track_name = callback.data.split(":", 1)[1]
    await callback.answer(f"🔍 {track_name}")
    from handlers.search_handler import handle_music_selection
    from copy import copy
    results = await search_youtube(f"{track_name} audio", limit=1)
    if not results:
        await callback.message.answer("❌ Track not found.")
        return
    new_callback = copy(callback)
    new_callback.data = f"music:YT:{results[0]['id']}"
    await handle_music_selection(new_callback)

async def show_spotify_playlist_ui(message, url, reply_func):
    if not await get_module_status("Spotify"):
         await reply_func(msg.MSG_DISABLE_MODULE)
         return
    status_msg = await reply_func("⏳ Scanning playlist...")
    try:
        strategy = SpotifyStrategy(url)
        playlist_info = await strategy.get_playlist_tracks()
        if not playlist_info:
            await safe_api_call(status_msg.edit_text, "❌ Failed to read playlist (Private or Deleted).")
            return
        title, tracks = playlist_info
        if not tracks:
            await safe_api_call(status_msg.edit_text, "📂 Playlist is empty.")
            return
        p_id = str(uuid4())
        PLAYLIST_CACHE[p_id] = {'title': title, 'tracks': tracks}
        keyboard = generate_playlist_keyboard(p_id, 0)
        await safe_api_call(status_msg.edit_text, f"📂 <b>Spotify Playlist</b>\n🎶 <b>{title}</b>\n🔢 Tracks: {len(tracks)}\n", reply_markup=keyboard, parse_mode="HTML")
    except Exception as e: await safe_api_call(status_msg.edit_text, f"❌ Error: {e}")

# --- ОБРАБОТКА ССЫЛОК ---
@user_router.message(F.text.contains("http"))
async def handle_link(message: types.Message):
    user = message.from_user
    can, _, _, lang = await check_access_and_update(user, message)
    if not can: return
    
    url_raw = message.text.strip()
    caption_override = None
    if "|" in url_raw:
        parts = url_raw.split("|", 1)
        url_raw = parts[0].strip()
        caption_override = parts[1].strip()
    
    for c in [';', '\n', ' ', '$', '`', '|']: 
        if c in url_raw: url_raw = url_raw.split(c)[0]
    url = clean_url(url_raw)

    # --- УМНАЯ ОТПРАВКА (REPLY) ---
    async def smart_reply(text=None, **kwargs):
        """Отвечает на сообщение или ветку"""
        user_mention = f"<a href='tg://user?id={user.id}'>{html.escape(user.first_name)}</a>"
        method = message.bot.send_message
        
        async def try_send_impl(chat_id, reply_to, **k):
            if text:
                return await safe_api_call(message.bot.send_message, chat_id=chat_id, reply_to_message_id=reply_to, text=text, **k)
            return reply_to

        try:
            return await try_send_impl(message.chat.id, message.message_id, **kwargs)
        except Exception as e:
            err = str(e).lower()
            if "not found" in err or "deleted" in err:
                if text:
                    new_text = f"{text}\n• {await t(user.id, 'req_by', user=user_mention)}"
                    return await safe_api_call(message.bot.send_message, chat_id=message.chat.id, text=new_text, **kwargs)
            raise e
            
    async def smart_media_send(send_method, caption_base, **kwargs):
        user_mention = f"<a href='tg://user?id={user.id}'>{html.escape(user.first_name)}</a>"
        try:
            return await safe_api_call(send_method, chat_id=message.chat.id, reply_to_message_id=message.message_id, caption=caption_base, **kwargs)
        except Exception as e:
            err = str(e).lower()
            if "not found" in err or "deleted" in err:
                req_text = await t(user.id, 'req_by', user=user_mention)
                new_caption = f"{caption_base}\n{req_text}"
                if message.reply_to_message:
                    try:
                        return await safe_api_call(send_method, chat_id=message.chat.id, reply_to_message_id=message.reply_to_message.message_id, caption=new_caption, **kwargs)
                    except: pass
                return await safe_api_call(send_method, chat_id=message.chat.id, caption=new_caption, **kwargs)
            raise e
    # ---------------------------------

    if not is_valid_url(url):
        if message.chat.type != "private": return
        await smart_reply(await t(user.id, 'error_link'))
        return

    if "spotify" in url and ("/playlist/" in url or "/album/" in url):
        await show_spotify_playlist_ui(message, url, smart_reply)
        return

    # 1. SMART CACHE
    db_cache = await get_cached_file(url)
    if db_cache:
        try:
            is_audio_cache = db_cache['media_type'] == 'audio'
            caption = make_caption(db_cache['title'], url, caption_override, is_audio=is_audio_cache)
            reply_markup = None
            if is_audio_cache: reply_markup = get_clip_keyboard(url, user.id)

            if db_cache['media_type'] == 'video': 
                await smart_media_send(message.bot.send_video, caption_base=caption, video=db_cache['file_id'], parse_mode="HTML")
            elif db_cache['media_type'] == 'audio': 
                await smart_media_send(message.bot.send_audio, caption_base=caption, audio=db_cache['file_id'], parse_mode="HTML", reply_markup=reply_markup)
            elif db_cache['media_type'] == 'photo': 
                await smart_media_send(message.bot.send_photo, caption_base=caption, photo=db_cache['file_id'], parse_mode="HTML")
            await send_log("SUCCESS", f"Cache Hit: {url}", user=user)
            return
        except: pass

    # 2. ЗАГРУЗКА (ОЧЕРЕДЬ)
    status_msg = None
    now = time.time()
    last_status = LAST_STATUS_TIME.get(user.id, 0)
    
    if (now - last_status) > 2.0:
        try:
            status_msg = await smart_reply(await t(user.id, 'wait'))
            LAST_STATUS_TIME[user.id] = now
        except: pass

    async def download_task():
        await send_log("USER_REQ", f"URL: {url}", user=user)
        return await download_content(url)

    try:
        files, folder_path, error, meta = await queue_manager.process_task(user.id, download_task)
    except Exception as e:
        if status_msg: await safe_api_call(status_msg.edit_text, "⚠️ Queue full.")
        return

    # Обработка плейлиста
    if error and "IS_SPOTIFY_PLAYLIST" in str(error):
        if status_msg: await safe_api_call(status_msg.delete)
        if folder_path: shutil.rmtree(folder_path, ignore_errors=True)
        await show_spotify_playlist_ui(message, url, smart_reply)
        return

    # ОШИБКИ
    if error:
        err_str = str(error).lower()
        if any(m in err_str for m in ["sign in", "login", "private", "access", "blocked", "followers", "confirm", "captcha", "unsupported url"]):
            user_cookies = await get_user_cookie(user.id)
            if user_cookies:
                if status_msg: await safe_api_call(status_msg.edit_text, "🔐 Using cookies...")
                files, folder_path, error, meta = await download_content(url, {'user_cookie_content': user_cookies})
            else:
                txt = await t(user.id, 'auth_required')
                if status_msg: await safe_api_call(status_msg.delete)
                await smart_reply(txt, parse_mode="HTML")
                return

        if error and ("too large" in err_str or "larger than" in err_str) and not settings.USE_LOCAL_SERVER:
            if status_msg: await safe_api_call(status_msg.edit_text, "⚠️ >50 MB. Compressing...")
            low_opts = {'format': 'worst[ext=mp4]+bestaudio[ext=m4a]/worst[ext=mp4]/worst', 'user_cookie_content': await get_user_cookie(user.id)}
            files, folder_path, error, meta = await download_content(url, low_opts)
    
    if error:
        txt = await t(user.id, 'error', error=error)
        if status_msg: await safe_api_call(status_msg.edit_text, txt)
        else: await smart_reply(txt)
        await send_log("FAIL", f"Fail: {error}", user=user)
        return
        
    # МЕТАДАННЫЕ
    resolution_text = ""
    vid_width, vid_height = None, None
    meta_artist, meta_title = None, None

    if meta:
        h, w = meta.get('height'), meta.get('width')
        if h and w:
            vid_height, vid_width = h, w
            res_str = "1080p" if h >= 1080 else f"{h}p"
            resolution_text = f" ({res_str})"
        meta_artist = meta.get('artist') or meta.get('uploader')
        meta_title = meta.get('track') or meta.get('title')
    else:
        info_json_file = next((f for f in files if f.endswith(('.info.json'))), None)
        if info_json_file:
            try:
                with open(info_json_file, 'r', encoding='utf-8') as f:
                    info = json.load(f)
                    meta_artist = info.get('artist') or info.get('uploader')
                    meta_title = info.get('track') or info.get('title')
            except: pass

    # 3. ОТПРАВКА
    action_task = None
    try:
        video_exts = ['.mp4', '.mov', '.mkv', '.webm', '.ts']
        audio_exts = ['.mp3', '.ogg', '.wav', '.m4a', '.flac', '.webm']
        image_exts = ['.jpg', '.jpeg', '.png', '.webp']
        
        media_files = [f for f in files if f.endswith(tuple(video_exts + audio_exts + image_exts))]
        
        is_tiktok_photo = "tiktok" in url and "/photo/" in url
        is_video_url = any(x in url for x in ['youtube', 'youtu.be', 'vk.com', 'reel', '/video/', 'twitch'])
        is_music_url = "music.youtube.com" in url
        
        if is_video_url and not is_tiktok_photo and not is_music_url:
             video_only = [f for f in media_files if not f.endswith(tuple(image_exts))]
             if any(f.endswith(tuple(video_exts)) for f in video_only): media_files = video_only
        
        if not media_files: raise Exception("No media files found")

        target = media_files[0]
        ext = os.path.splitext(target)[1].lower()

        if not meta_title:
             fname = os.path.basename(target)
             raw = os.path.splitext(fname)[0]
             meta_title = re.sub(r'\[.*?\]', '', raw).strip().replace("_", " ")

        final_artist = meta_artist
        final_title = meta_title
        if not final_artist and " - " in final_title:
            parts = final_title.split(" - ", 1)
            final_artist, final_title = parts[0], parts[1]
        if not final_artist: final_artist = f"@{settings.BOT_USERNAME or 'ch4roff_bot'}"

        caption_header = final_title
        if meta_artist and meta_artist not in final_title:
            caption_header = f"{meta_artist} - {final_title}"
            
        is_audio_file = ext in audio_exts
        caption = make_caption(f"{caption_header}{resolution_text}", url, caption_override, is_audio=is_audio_file)
        
        sent_msg, m_type = None, None 

        if is_tiktok_photo and len([f for f in media_files if f.endswith(tuple(image_exts))]) > 1:
            if not await get_module_status("TikTokPhotos"):
                 await smart_reply(await t(user.id, 'module_disabled'))
                 if status_msg: await safe_api_call(status_msg.delete)
                 return
            try: await safe_api_call(message.bot.send_chat_action, chat_id=message.chat.id, action=ChatAction.UPLOAD_PHOTO)
            except: pass
            
            media_group = []
            images = [f for f in media_files if f.endswith(tuple(image_exts))]
            for i, img in enumerate(images[:10]):
                cap = caption if i == 0 else None
                media_group.append(InputMediaPhoto(media=FSInputFile(img), caption=cap, parse_mode="HTML"))
            
            try: await safe_api_call(message.reply_media_group, media=media_group)
            except: await safe_api_call(message.answer_media_group, media=media_group)

            audio_f = next((f for f in files if f.endswith(tuple(audio_exts))), None)
            bot_name = settings.BOT_USERNAME or "ch4roff_bot"
            if audio_f: await smart_media_send(message.bot.send_audio, caption="🎵 Sound", audio=FSInputFile(audio_f), performer=f"@{bot_name}")
            
            await send_log("SUCCESS", f"TikTok Carousel: {url}", user=user)
            if status_msg: await safe_api_call(status_msg.delete)
            return

        if ext in audio_exts:
            try: await safe_api_call(message.bot.send_chat_action, chat_id=message.chat.id, action=ChatAction.UPLOAD_VOICE)
            except: pass
            thumb = next((f for f in files if f.endswith(('.jpg', '.png'))), None)
            reply_markup = get_clip_keyboard(url, user.id)
            
            sent_msg = await smart_media_send(
                message.bot.send_audio,
                caption_base=caption,
                audio=FSInputFile(target), 
                parse_mode="HTML",
                thumbnail=FSInputFile(thumb) if thumb else None,
                performer=final_artist, title=final_title, reply_markup=reply_markup
            )
            m_type = "audio"

        elif ext in video_exts:
            action_task = asyncio.create_task(send_action_loop(message.bot, message.chat.id, ChatAction.UPLOAD_VIDEO))
            sent_msg = await smart_media_send(
                message.bot.send_video,
                caption_base=caption,
                video=FSInputFile(target), 
                parse_mode="HTML",
                thumbnail=None, supports_streaming=True,
                width=vid_width, height=vid_height
            )
            m_type = "video"
        
        else:
            sent_msg = await smart_media_send(
                message.bot.send_photo,
                caption_base=caption,
                photo=FSInputFile(target), parse_mode="HTML"
            )
            m_type = "photo"

        await send_log("SUCCESS", f"Success: {url}", user=user)
        
        if sent_msg and m_type:
            fid = None
            if m_type == "video": fid = sent_msg.video.file_id
            elif m_type == "audio": fid = sent_msg.audio.file_id
            elif m_type == "photo": fid = sent_msg.photo[-1].file_id
            if fid: await save_cached_file(url, fid, m_type, title=caption_header) 

        if status_msg: await safe_api_call(status_msg.delete)

    except Exception as e:
        if "Request timeout error" in str(e): await send_log("WARN", f"Timeout: {e}", user=user)
        else:
            try: await safe_api_call(message.answer, f"⚠️ Error: {e}")
            except: pass
            await send_log("FAIL", f"Send Error: {e}", user=user)
    finally:
        if action_task: action_task.cancel()
        if folder_path and os.path.exists(folder_path): shutil.rmtree(folder_path, ignore_errors=True)

@user_router.message(F.text & ~F.text.contains("http"))
async def handle_plain_text(message: types.Message):
    if message.chat.type != "private": return
    user = message.from_user
    if not message.text: return
    txt = message.text.strip()
    
    # 1. Анти-Спам (Длина)
    if len(txt) > 150 or txt.count('\n') > 5:
        return 

    can, _, _, lang = await check_access_and_update(user, message)
    if not can: return
    try: await log_other_message(txt, user=user)
    except: pass

    if not await get_module_status("TextFind"):
        await safe_api_call(message.answer, await t(user.id, 'module_disabled'))
        return

    await safe_api_call(message.bot.send_chat_action, chat_id=message.chat.id, action=ChatAction.TYPING)
    results = await search_youtube(txt, limit=5)
    
    if not results:
        await safe_api_call(message.answer, await t(user.id, 'nothing_found'))
        return

    buttons = []
    for res in results:
        uploader = res.get('uploader', '')
        title = res.get('title', '')
        full_title = f"{uploader} - {title}" if uploader else title
        full_title = f"{full_title} ({res['duration']})"
        source = res.get('source', 'YT')
        buttons.append([InlineKeyboardButton(text=full_title, callback_data=f"music:{source}:{res['id']}")])
    
    close_txt = await t(user.id, 'btn_close')
    buttons.append([InlineKeyboardButton(text=close_txt, callback_data="delete_msg")])
    
    search_txt = await t(user.id, 'search_title', query=txt)
    await safe_api_call(message.answer, search_txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")