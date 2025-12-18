import os
import shutil
import json 
import asyncio 
import re
import time
import html
from aiogram import F, types, Bot
from aiogram.types import FSInputFile, InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramRetryAfter

from .router import user_router, check_access_and_update
from services.database.core import get_cached_file, save_cached_file, get_user_cookie, get_module_status
from core.logger_system import logger
from services.platforms.platform_manager import download_content, is_valid_url
from services.platforms.SpotifyDownloader.spotify_strategy import SpotifyStrategy
from services.url_cleaner import clean_url
from services.search_service import search_youtube
from languages import t
import settings
from core.queue_manager import queue_manager
from uuid import uuid4
import math

PLAYLIST_CACHE = {}
LAST_STATUS_TIME = {} 

async def safe_api_call(func, *args, **kwargs):
    try:
        return await func(*args, **kwargs)
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
        return await safe_api_call(func, *args, **kwargs)
    except Exception as e:
        raise e

def make_caption(title_text, url, override=None, is_audio=False, request_by=None):
    bot_name = settings.BOT_USERNAME or "bot"
    footer = f"@{bot_name}"
    
    if is_audio and url:
        clean_source = url.split("?")[0] if "?" in url else url
        odesli_url = f"https://song.link/{clean_source}"
        footer += f" | <a href=\"{odesli_url}\">🌐 Links</a>"

    if request_by:
        footer += f"\n{request_by}"
    
    if override:
        return f"{html.escape(override)}\n\n{footer}"
    
    if not title_text:
        return footer
        
    safe_title = html.escape(title_text)
    return f'<a href="{url}">{safe_title}</a>\n\n{footer}'

def get_clip_keyboard(url: str):
    if "youtube.com" in url or "youtu.be" in url:
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

async def show_spotify_playlist_ui(message, url, reply_func, user_id):
    if not await get_module_status("Spotify"):
         await reply_func(text=await t(user_id, 'module_disabled'))
         return
    status_msg = await reply_func(text="⏳ Scanning playlist...")
    try:
        strategy = SpotifyStrategy(url)
        playlist_info = await strategy.get_playlist_tracks()
        if not playlist_info:
            await safe_api_call(status_msg.edit_text, "❌ Failed to read playlist.")
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

    async def smart_send(send_method, caption_base=None, text=None, **kwargs):
        user_mention = f"<a href='tg://user?id={user.id}'>{html.escape(user.first_name)}</a>"
        is_text_msg = (send_method.__name__ == 'send_message')
        final_kwargs = kwargs.copy()
        if is_text_msg:
            if text: final_kwargs['text'] = text
        else:
            if caption_base: final_kwargs['caption'] = caption_base

        async def try_send(reply_to_id, k):
            return await safe_api_call(send_method, chat_id=message.chat.id, reply_to_message_id=reply_to_id, **k)

        try:
            msg = await try_send(message.message_id, final_kwargs)
            await logger(user, "MSG_SENT", text if text else "File Sent", msg)
            return msg
        except Exception as e:
            msg = await safe_api_call(send_method, chat_id=message.chat.id, **final_kwargs)
            return msg

    if not is_valid_url(url):
        if message.chat.type != "private": return
        await smart_send(message.bot.send_message, text=await t(user.id, 'error_link'))
        return

    if "spotify" in url and ("/playlist/" in url or "/album/" in url):
        await show_spotify_playlist_ui(message, url, smart_send, user.id)
        return

    db_cache = await get_cached_file(url)
    if db_cache:
        try:
            is_audio_cache = db_cache['media_type'] == 'audio'
            caption = make_caption(db_cache['title'], url, caption_override, is_audio=is_audio_cache)
            reply_markup = None
            if is_audio_cache: reply_markup = get_clip_keyboard(url)
            
            if db_cache['media_type'] == 'video': 
                await smart_send(message.bot.send_video, caption_base=caption, video=db_cache['file_id'], parse_mode="HTML")
            elif db_cache['media_type'] == 'audio': 
                await smart_send(message.bot.send_audio, caption_base=caption, audio=db_cache['file_id'], parse_mode="HTML", reply_markup=reply_markup)
            elif db_cache['media_type'] == 'photo': 
                await smart_send(message.bot.send_photo, caption_base=caption, photo=db_cache['file_id'], parse_mode="HTML")
            await logger(user, "CACHE_HIT", url)
            return
        except: pass

    status_msg = None
    now = time.time()
    last_status = LAST_STATUS_TIME.get(user.id, 0)
    if (now - last_status) > 2.0:
        try:
            status_msg = await smart_send(message.bot.send_message, text=await t(user.id, 'wait'))
            LAST_STATUS_TIME[user.id] = now
        except: pass

    async def download_task():
        await logger(user, "MSG_LINK", url)
        return await download_content(url)

    try:
        files, folder_path, error, meta = await queue_manager.process_task(user.id, download_task)
    except Exception as e:
        if status_msg: await safe_api_call(status_msg.delete)
        return

    if error and "IS_SPOTIFY_PLAYLIST" in str(error):
        if status_msg: await safe_api_call(status_msg.delete)
        if folder_path: shutil.rmtree(folder_path, ignore_errors=True)
        await show_spotify_playlist_ui(message, url, smart_send, user.id)
        return

    if error:
        err_str = str(error).lower()
        if any(m in err_str for m in ["sign in", "login", "private", "access", "blocked", "followers", "confirm", "captcha"]):
             user_cookies = await get_user_cookie(user.id)
             if user_cookies:
                if status_msg: await safe_api_call(status_msg.edit_text, "🔐 Using cookies...")
                files, folder_path, error, meta = await download_content(url, {'user_cookie_content': user_cookies})
             else:
                txt = await t(user.id, 'auth_required')
                if status_msg: await safe_api_call(status_msg.delete)
                await smart_send(message.bot.send_message, text=txt, parse_mode="HTML")
                return

    if error:
        txt = await t(user.id, 'error', error=error)
        if status_msg: await safe_api_call(status_msg.edit_text, txt)
        else: await smart_send(message.bot.send_message, text=txt)
        await logger(user, "MSG_FAIL", error)
        return
        
    meta_artist, meta_title = None, None
    resolution_text = ""
    is_spoiler = False
    
    if meta:
        meta_artist = meta.get('artist') or meta.get('uploader')
        meta_title = meta.get('track') or meta.get('title')
        if meta.get('height'): resolution_text = f" ({meta.get('height')}p)"
        if meta.get('age_limit') and meta.get('age_limit') >= 18: is_spoiler = True
    elif files:
         info_json = next((f for f in files if f.endswith('.info.json')), None)
         if info_json:
             try:
                 with open(info_json, 'r', encoding='utf-8') as f:
                     info = json.load(f)
                     meta_artist = info.get('artist') or info.get('uploader')
                     meta_title = info.get('track') or info.get('title')
             except: pass

    is_music_url = "music.youtube.com" in url or "http://googleusercontent.com/spotify.com" in url or "soundcloud.com" in url
    
    video_exts = ['.mp4', '.mov', '.mkv', '.webm', '.ts']
    audio_exts = ['.mp3', '.ogg', '.wav', '.m4a', '.flac']
    image_exts = ['.jpg', '.jpeg', '.png', '.webp']
    
    target_file = None
    media_type = None 
    
    if is_music_url:
        target_file = next((f for f in files if f.endswith(tuple(audio_exts))), None)
        if target_file: media_type = 'audio'
    
    if not target_file:
        target_file = next((f for f in files if f.endswith(tuple(video_exts))), None)
        if target_file: media_type = 'video'

    if not target_file:
        target_file = next((f for f in files if f.endswith(tuple(audio_exts))), None)
        if target_file: media_type = 'audio'
        
    if not target_file:
        target_file = next((f for f in files if f.endswith(tuple(image_exts))), None)
        if target_file: 
            is_tiktok_photo = "tiktok" in url and len([f for f in files if f.endswith(tuple(image_exts))]) > 1
            if is_tiktok_photo:
                 media_type = 'tiktok_slides'
            elif not is_music_url and "youtube" not in url: 
                 media_type = 'photo'

    if not target_file and media_type != 'tiktok_slides':
        if status_msg: await safe_api_call(status_msg.edit_text, "❌ No supported media found.")
        return

    if target_file:
        try:
            f_size = os.path.getsize(target_file)
            if f_size > 49 * 1024 * 1024:
                if status_msg: await safe_api_call(status_msg.edit_text, f"⚠️ File is too big for Telegram Bot API ({round(f_size/1024/1024, 1)}MB > 50MB).")
                if folder_path: shutil.rmtree(folder_path, ignore_errors=True)
                return
        except: pass

    if not meta_title and target_file:
         fname = os.path.basename(target_file)
         meta_title = os.path.splitext(fname)[0].replace("_", " ")

    final_header = meta_title
    if meta_artist and meta_artist not in (meta_title or ""):
        final_header = f"{meta_artist} - {meta_title}"
    
    caption = make_caption(f"{final_header}{resolution_text}", url, caption_override, is_audio=(media_type == 'audio'))

    action_task = None
    sent_msg = None
    
    try:
        if media_type == 'tiktok_slides':
             if not await get_module_status("TikTokPhotos"):
                 await smart_send(message.bot.send_message, text=await t(user.id, 'module_disabled'))
                 return
             media_group = []
             images = [f for f in files if f.endswith(tuple(image_exts))][:10]
             for i, img in enumerate(images):
                 cap = caption if i == 0 else None
                 media_group.append(InputMediaPhoto(media=FSInputFile(img), caption=cap, parse_mode="HTML"))
             try: await safe_api_call(message.reply_media_group, media=media_group)
             except: await safe_api_call(message.answer_media_group, media=media_group)
             audio_f = next((f for f in files if f.endswith(tuple(audio_exts))), None)
             if audio_f:
                 bot_name = settings.BOT_USERNAME or "bot"
                 await smart_send(message.bot.send_audio, caption="🎵 Sound", audio=FSInputFile(audio_f), performer=f"@{bot_name}")
             if status_msg: await safe_api_call(status_msg.delete)
             return

        elif media_type == 'audio':
             await safe_api_call(message.bot.send_chat_action, chat_id=message.chat.id, action=ChatAction.UPLOAD_VOICE)
             thumb = next((f for f in files if f.endswith(('.jpg', '.png'))), None)
             reply_markup = get_clip_keyboard(url)
             sent_msg = await smart_send(
                 message.bot.send_audio, 
                 caption_base=caption, 
                 audio=FSInputFile(target_file), 
                 parse_mode="HTML", 
                 thumbnail=FSInputFile(thumb) if thumb else None, 
                 performer=meta_artist, 
                 title=meta_title, 
                 reply_markup=reply_markup
             )
             
        elif media_type == 'video':
             action_task = asyncio.create_task(send_action_loop(message.bot, message.chat.id, ChatAction.UPLOAD_VIDEO))
             sent_msg = await smart_send(
                 message.bot.send_video, 
                 caption_base=caption, 
                 video=FSInputFile(target_file), 
                 parse_mode="HTML", 
                 supports_streaming=True, 
                 has_spoiler=is_spoiler
             )
             
        elif media_type == 'photo':
             sent_msg = await smart_send(message.bot.send_photo, caption_base=caption, photo=FSInputFile(target_file), parse_mode="HTML")

        if sent_msg:
             fid = None
             if media_type == "video": fid = sent_msg.video.file_id
             elif media_type == "audio": fid = sent_msg.audio.file_id
             elif media_type == "photo": fid = sent_msg.photo[-1].file_id
             
             if fid: await save_cached_file(url, fid, media_type, title=final_header)
             
        if status_msg: await safe_api_call(status_msg.delete)

    except Exception as e:
        await logger(user, "MSG_FAIL", str(e))
        if status_msg: await safe_api_call(status_msg.edit_text, f"⚠️ Error sending file: {e}")
    finally:
        if action_task: action_task.cancel()
        if folder_path and os.path.exists(folder_path): shutil.rmtree(folder_path, ignore_errors=True)

@user_router.message(F.text & ~F.text.contains("http"))
async def handle_plain_text(message: types.Message):
    if message.text.startswith('/'): return
    if message.chat.type != "private": return
    user = message.from_user
    if not await get_module_status("TextFind"):
        await safe_api_call(message.answer, await t(user.id, 'module_disabled'))
        return
    await safe_api_call(message.bot.send_chat_action, chat_id=message.chat.id, action=ChatAction.TYPING)
    results = await search_youtube(message.text.strip(), limit=5)
    if not results:
        await safe_api_call(message.answer, await t(user.id, 'nothing_found'))
        return
    buttons = []
    for res in results:
        title = res.get('title', 'Track')
        buttons.append([InlineKeyboardButton(text=f"{title} ({res['duration']})", callback_data=f"music:YT:{res['id']}")])
    buttons.append([InlineKeyboardButton(text="❌ Close", callback_data="delete_msg")])
    await safe_api_call(message.answer, f"🔍 Results for: {message.text}", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))