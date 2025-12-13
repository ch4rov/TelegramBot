import os
import shutil
import uuid
import asyncio
import html
import json
import re
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
from loader import bot
from services.platforms.platform_manager import download_content, is_valid_url 
from services.placeholder_service import get_placeholder 
from services.database_service import get_user, get_module_status
from services.lastfm_service import get_user_recent_track
from services.search_service import search_music
import settings

router = Router()

INLINE_SEARCH_CACHE = {}
# Лимиты
LIMIT_PUBLIC = 49 * 1024 * 1024
LIMIT_LOCAL = 1990 * 1024 * 1024

def clean_cache():
    if len(INLINE_SEARCH_CACHE) > 1000:
        INLINE_SEARCH_CACHE.clear()

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
            return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎬 Video / Clip", callback_data=f"get_clip:{video_id}")]])
    return None

@router.inline_query()
async def inline_query_handler(query: types.InlineQuery):
    text = query.query.strip()
    user_id = query.from_user.id
    results = []
    clean_cache()

    video_ph = await get_placeholder('video')
    audio_ph = await get_placeholder('audio')
    if not video_ph or not audio_ph: return

    # 1. Ссылка
    if text and is_valid_url(text):
        if await get_module_status("InlineVideo"):
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 Загрузка...", callback_data="processing")]])
            results.append(InlineQueryResultCachedVideo(
                id=str(uuid.uuid4()), video_file_id=video_ph, title="📥 Скачать по ссылке",
                description=text, caption="⏳ *Начинаю загрузку...*", parse_mode="Markdown", reply_markup=keyboard
            ))

    # 2. Поиск музыки
    else:
        if not await get_module_status("InlineAudio"): return
        search_query = text
        if not search_query:
            user_db = await get_user(user_id)
            lfm = user_db.get('lastfm_username') if user_db else None
            if lfm:
                t = await get_user_recent_track(lfm)
                if t: search_query = t['query']

        if search_query:
            query_id = str(uuid.uuid4())
            INLINE_SEARCH_CACHE[query_id] = search_query
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"🔎 {search_query[:30]}...", callback_data="processing")]])
            results.append(InlineQueryResultCachedAudio(
                id=f"music:{query_id}", audio_file_id=audio_ph,
                caption=f"🔎 Ищу: {search_query}...", reply_markup=keyboard
            ))
        else:
            results.append(InlineQueryResultArticle(
                id="login_hint", title="🔗 Подключить Last.fm", description="Показывай музыку в статусе",
                input_message_content=InputTextMessageContent(message_text="Подключить Last.fm: /login")
            ))

    try: await query.answer(results, cache_time=2, is_personal=True)
    except: pass


@router.chosen_inline_result()
async def chosen_handler(chosen_result: types.ChosenInlineResult):
    result_id = chosen_result.result_id
    inline_msg_id = chosen_result.inline_message_id
    user = chosen_result.from_user
    if not inline_msg_id: return

    is_music_mode = result_id.startswith("music:")
    url = None
    
    if is_music_mode:
        try:
            query_uuid = result_id.split(":", 1)[1]
            query = INLINE_SEARCH_CACHE.get(query_uuid) or chosen_result.query or "Unknown"
            print(f"[INLINE] {user.username}: Audio Search ({query})")
            
            res = await search_music(query, limit=1)
            if not res:
                try: await bot.edit_message_caption(inline_message_id=inline_msg_id, caption=f"❌ Не найдено: {query}")
                except: pass
                return
            url = res[0]['url']
            try: await bot.edit_message_caption(inline_message_id=inline_msg_id, caption=f"📥 Качаю: {res[0]['title']}...")
            except: pass
        except: return
    else:
        url = chosen_result.query.strip()

    if not url: return

    # === НАСТРОЙКИ СКАЧИВАНИЯ ===
    is_local = getattr(settings, 'USE_LOCAL_SERVER', False)
    current_limit = LIMIT_LOCAL if is_local else LIMIT_PUBLIC

    custom_opts = {}
    if is_music_mode:
        # Аудио обычно маленькое, но лучше перестраховаться
        custom_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
            'keepvideo': False
        }
    else:
        # Для видео жестко режем качество, если не локалка
        if is_local:
            format_str = 'bestvideo+bestaudio/best' # MP4 соберет сам yt-dlp если расширение не совпадает
        else:
            # Ищем лучшее до 50МБ, иначе худшее
            format_str = 'best[filesize<50M]/bestvideo[filesize<40M]+bestaudio/best[height<=480]/worst'
        
        custom_opts = {
            'format': format_str,
            'merge_output_format': 'mp4' # Всегда MP4 для совместимости
        }

    files, folder_path, error, meta = await download_content(url, custom_opts)

    if error:
        try: await bot.edit_message_caption(inline_message_id=inline_msg_id, caption=f"❌ {error}")
        except: pass
        if folder_path: shutil.rmtree(folder_path, ignore_errors=True)
        return

    try:
        # Поиск файла
        media_files = []
        thumb_file = None
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.webp']: thumb_file = f
            elif ext in ['.mp4', '.mov', '.mp3', '.m4a', '.ogg', '.wav', '.flac', '.webm']: 
                media_files.append(f)

        if not media_files: raise Exception("Empty media")

        if is_music_mode:
            media_files.sort(key=lambda x: 0 if x.endswith('.mp3') else 1)
        
        target_file = media_files[0]
        ext = os.path.splitext(target_file)[1].lower()
        
        # === ПРОВЕРКА РАЗМЕРА ===
        file_size = os.path.getsize(target_file)
        if file_size > current_limit:
            msg = f"⚠️ File too big ({file_size / (1024*1024):.1f} MB)."
            try: await bot.edit_message_caption(inline_message_id=inline_msg_id, caption=msg)
            except: pass
            return
        # ========================

        media_type = 'document'
        if is_music_mode:
            media_type = 'audio'
            # Принудительно MP3
            if ext not in ['.mp3', '.m4a', '.flac', '.wav', '.ogg']:
                new_path = os.path.splitext(target_file)[0] + ".mp3"
                shutil.move(target_file, new_path)
                target_file = new_path
        else:
            if ext in ['.mp3', '.m4a']: media_type = 'audio'
            elif ext in ['.mp4', '.mov']: media_type = 'video'

        # Подготовка к отправке
        filename = os.path.basename(target_file)
        media_obj = FSInputFile(target_file, filename=filename)
        
        meta_title = meta.get('title') if meta else os.path.splitext(filename)[0]
        meta_artist = meta.get('artist') or meta.get('uploader')
        
        caption = f'<a href="{url}">{html.escape(meta_title)}</a>'
        if is_music_mode: caption += f" | <a href=\"https://song.link/{url}\">Links</a>"

        sent_msg = None
        telegram_file_id = None

        if media_type == 'audio':
            thumb = FSInputFile(thumb_file) if thumb_file else None
            performer = meta_artist or "@bot"
            sent_msg = await bot.send_audio(
                user.id, media_obj, caption=caption, parse_mode="HTML",
                thumbnail=thumb, performer=performer, title=meta_title,
                reply_markup=get_clip_keyboard(url)
            )
            telegram_file_id = sent_msg.audio.file_id
        
        elif media_type == 'video':
            sent_msg = await bot.send_video(
                user.id, media_obj, caption=caption, parse_mode="HTML",
                supports_streaming=True
            )
            telegram_file_id = sent_msg.video.file_id
        
        else:
            sent_msg = await bot.send_document(
                user.id, media_obj, caption=caption, parse_mode="HTML"
            )
            telegram_file_id = sent_msg.document.file_id

        # Update Inline
        if telegram_file_id:
            new_media = None
            if media_type == 'audio': new_media = InputMediaAudio(media=telegram_file_id, caption=caption, parse_mode="HTML")
            elif media_type == 'video': new_media = InputMediaVideo(media=telegram_file_id, caption=caption, parse_mode="HTML", supports_streaming=True)
            
            if new_media:
                try: await bot.edit_message_media(inline_message_id=inline_msg_id, media=new_media)
                except: await bot.edit_message_caption(inline_message_id=inline_msg_id, caption="✅ Sent.")
            else:
                await bot.edit_message_caption(inline_message_id=inline_msg_id, caption="✅ Sent.")
            
            if sent_msg:
                await asyncio.sleep(0.5)
                try: await bot.delete_message(user.id, sent_msg.message_id)
                except: pass

    except Exception as e:
        print(f"Inline Error: {e}")
        try: await bot.edit_message_caption(inline_message_id=inline_msg_id, caption="⚠️ Error.")
        except: pass
    finally:
        if folder_path and os.path.exists(folder_path): shutil.rmtree(folder_path, ignore_errors=True)