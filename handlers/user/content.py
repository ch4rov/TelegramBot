import os
import shutil
import json 
import asyncio 
import re
import time
from aiogram import F, types, Bot
from aiogram.types import FSInputFile, InputMediaPhoto, InputMediaVideo, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ChatAction

from .router import user_router, check_access_and_update, make_caption, ACTIVE_DOWNLOADS
from services.database_service import get_cached_file, save_cached_file, get_user_cookie, get_module_status
from logs.logger import send_log_groupable as send_log, log_other_message
from services.platforms.platform_manager import download_content, is_valid_url
from services.url_cleaner import clean_url
from services.search_service import search_youtube
import messages as msg 
import settings

def get_clip_keyboard(url: str):
    if "music.youtube.com" in url or "youtu" in url:
        video_id = None
        if "v=" in url: 
            try: video_id = url.split("v=")[1].split("&")[0]
            except: pass
        elif "youtu.be/" in url: 
            try: video_id = url.split("youtu.be/")[1].split("?")[0]
            except: pass
        if video_id:
            return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎬 Загрузить клип", callback_data=f"get_clip:{video_id}")]])
    return None

async def send_action_loop(bot: Bot, chat_id: int, action: ChatAction, delay: int = 5):
    try:
        while True:
            await bot.send_chat_action(chat_id=chat_id, action=action)
            await asyncio.sleep(delay)
    except asyncio.CancelledError: pass

# --- ОБРАБОТКА ССЫЛОК ---
@user_router.message(F.text.contains("http"))
async def handle_link(message: types.Message):
    user = message.from_user
    can, _ = await check_access_and_update(user, message)
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

    if not is_valid_url(url):
        if message.chat.type != "private": return
        await message.answer(msg.MSG_ERR_LINK)
        return
    
    # --- ОТКЛЮЧЕНИЕ ПЛЕЙЛИСТОВ SPOTIFY ---
    # Если юзер кинул альбом или плейлист - просим трек
    if "spotify" in url and ("/playlist/" in url or "/album/" in url):
        await message.answer(
            "⚠️ <b>Плейлисты и альбомы Spotify не поддерживаются.</b>\n"
            "Пожалуйста, отправьте ссылку на конкретный трек.", 
            parse_mode="HTML"
        )
        return
    # -------------------------------------

    # 1. SMART CACHE
    db_cache = await get_cached_file(url)
    if db_cache:
        try:
            caption = make_caption(db_cache['title'], url, caption_override)
            reply_markup = None
            if db_cache['media_type'] == 'audio': reply_markup = get_clip_keyboard(url)

            if db_cache['media_type'] == 'video': 
                await message.answer_video(db_cache['file_id'], caption=caption, parse_mode="HTML")
            elif db_cache['media_type'] == 'audio': 
                await message.answer_audio(db_cache['file_id'], caption=caption, parse_mode="HTML", reply_markup=reply_markup)
            elif db_cache['media_type'] == 'photo': 
                await message.answer_photo(db_cache['file_id'], caption=caption, parse_mode="HTML")
            await send_log("SUCCESS", f"Успешно [DB CACHE] (<{url}>)", user=user)
            return
        except: pass

    # 2. ЗАГРУЗКА
    if ACTIVE_DOWNLOADS.get(user.id, 0) >= settings.MAX_CONCURRENT_DOWNLOADS:
        await message.answer("⚠️ Слишком много загрузок.")
        return
    ACTIVE_DOWNLOADS[user.id] = ACTIVE_DOWNLOADS.get(user.id, 0) + 1
    
    await send_log("USER_REQ", f"<{url}>", user=user)
    status_msg = await message.answer("⏳")

    files, folder_path, error, meta = await download_content(url)

    # ОБРАБОТКА ОШИБОК
    if error:
        err_str = str(error).lower()
        auth_markers = ["sign in", "login", "private", "access", "blocked", "followers", "confirm", "captcha", "unsupported url"]
        if any(m in err_str for m in auth_markers):
            user_cookies = await get_user_cookie(user.id)
            if user_cookies:
                await status_msg.edit_text("🔐 Доступ ограничен. Пробую куки...")
                files, folder_path, error, meta = await download_content(url, {'user_cookie_content': user_cookies})
            else:
                await message.answer("🔒 <b>Ошибка доступа.</b>\nПришлите файл <code>cookies.txt</code>.", parse_mode="HTML")
                await status_msg.delete()
                if user.id in ACTIVE_DOWNLOADS: del ACTIVE_DOWNLOADS[user.id]
                return

        if error and ("too large" in err_str or "larger than" in err_str) and not settings.USE_LOCAL_SERVER:
            await status_msg.edit_text("⚠️ Файл > 50 МБ. Пробую сжать...")
            low_opts = {'format': 'worst[ext=mp4]+bestaudio[ext=m4a]/worst[ext=mp4]/worst', 'user_cookie_content': await get_user_cookie(user.id)}
            files, folder_path, error, meta = await download_content(url, low_opts)
            if error: error = "Даже в низком качестве файл слишком большой (>50 МБ)."
        
    if error:
        await status_msg.edit_text(f"⚠️ {error}")
        await send_log("FAIL", f"Fail: {error}", user=user)
        if user.id in ACTIVE_DOWNLOADS: del ACTIVE_DOWNLOADS[user.id]
        return
        
    # МЕТАДАННЫЕ
    resolution_text = ""
    name_no_ext = ""
    vid_width, vid_height = None, None
    meta_artist, meta_title = None, None

    if meta:
        h, w = meta.get('height'), meta.get('width')
        if h and w:
            vid_height, vid_width = h, w
            res_str = "1080p" if h >= 1080 else f"{h}p"
            resolution_text = f" ({res_str})"
        meta_artist = meta.get('artist') or meta.get('uploader') or meta.get('creator') or meta.get('channel')
        meta_title = meta.get('track') or meta.get('title') or meta.get('alt_title')
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
            
        caption = make_caption(f"{caption_header}{resolution_text}", url, caption_override)
        sent_msg, m_type = None, None 

        if is_tiktok_photo and len([f for f in media_files if f.endswith(tuple(image_exts))]) > 1:
            if not await get_module_status("TikTokPhotos"):
                 await message.answer(msg.MSG_DISABLE_MODULE)
                 await status_msg.delete()
                 return
            await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_PHOTO)
            media_group = []
            images = [f for f in media_files if f.endswith(tuple(image_exts))]
            for i, img in enumerate(images[:10]):
                cap = caption if i == 0 else None
                media_group.append(InputMediaPhoto(media=FSInputFile(img), caption=cap, parse_mode="HTML"))
            await message.answer_media_group(media_group)
            audio_f = next((f for f in files if f.endswith(tuple(audio_exts))), None)
            bot_name = settings.BOT_USERNAME or "ch4roff_bot"
            if audio_f: await message.answer_audio(FSInputFile(audio_f), caption="🎵 Sound", performer=f"@{bot_name}")
            await send_log("SUCCESS", f"TikTok Carousel (<{url}>)", user=user)
            await status_msg.delete()
            return

        if ext in audio_exts:
            await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_VOICE)
            thumb = next((f for f in files if f.endswith(('.jpg', '.png'))), None)
            reply_markup = get_clip_keyboard(url)
            sent_msg = await message.answer_audio(
                FSInputFile(target), caption=caption, parse_mode="HTML",
                thumbnail=FSInputFile(thumb) if thumb else None,
                performer=final_artist, title=final_title, reply_markup=reply_markup
            )
            m_type = "audio"

        elif ext in video_exts:
            action_task = asyncio.create_task(send_action_loop(message.bot, message.chat.id, ChatAction.UPLOAD_VIDEO))
            sent_msg = await message.answer_video(
                FSInputFile(target), caption=caption, parse_mode="HTML",
                thumbnail=None, supports_streaming=True,
                width=vid_width, height=vid_height
            )
            m_type = "video"
        
        else:
            sent_msg = await message.answer_photo(FSInputFile(target), caption=caption, parse_mode="HTML")
            m_type = "photo"

        await send_log("SUCCESS", f"Успешно (<{url}>)", user=user)
        
        if sent_msg and m_type:
            fid = None
            if m_type == "video": fid = sent_msg.video.file_id
            elif m_type == "audio": fid = sent_msg.audio.file_id
            elif m_type == "photo": fid = sent_msg.photo[-1].file_id
            if fid: await save_cached_file(url, fid, m_type, title=caption_header) 

        await status_msg.delete() 

    except Exception as e:
        if "Request timeout error" in str(e): await send_log("WARN", f"Timeout: {e}", user=user)
        else:
            await message.answer(f"⚠️ Ошибка отправки файла. {e}")
            await send_log("FAIL", f"Send Error: {e}", user=user)
    finally:
        if action_task: action_task.cancel()
        if ACTIVE_DOWNLOADS.get(user.id) > 0: ACTIVE_DOWNLOADS[user.id] -= 1
        if folder_path and os.path.exists(folder_path): shutil.rmtree(folder_path, ignore_errors=True)

@user_router.message(F.text & ~F.text.contains("http"))
async def handle_plain_text(message: types.Message):
    if message.chat.type != "private": return
    user = message.from_user
    if not message.text: return
    txt = message.text.strip()
    if not txt or txt.startswith("/"): return
    can, _ = await check_access_and_update(user, message)
    if not can: return
    try: await log_other_message(txt, user=user)
    except: pass

    if not await get_module_status("TextFind"):
        await message.answer(msg.MSG_DISABLE_MODULE)
        return

    await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    results = await search_youtube(txt, limit=5)
    
    if not results:
        await message.answer(f"🔍 Ничего не найдено: {txt}")
        return

    buttons = []
    for res in results:
        full_title = f"{res['title']} ({res['duration']})"
        if len(full_title) > 50: full_title = full_title[:47] + "..."
        source = res.get('source', 'YT')
        buttons.append([InlineKeyboardButton(text=full_title, callback_data=f"music:{source}:{res['id']}")])
    
    buttons.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="delete_msg")])
    await message.answer(f"🔎 <b>Поиск:</b>\n<code>{txt}</code>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")