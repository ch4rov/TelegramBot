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

    video_ph = await get_placeholder('video')
    audio_ph = await get_placeholder('audio')

    if not video_ph or not audio_ph: return

    # --- СЦЕНАРИЙ 1: ССЫЛКА ---
    if text and is_valid_url(text):
        if not await get_module_status("InlineVideo"):
            results.append(InlineQueryResultArticle(
                id="disabled", title="⛔ Модуль отключен", 
                input_message_content=InputTextMessageContent(message_text="⚠️ Инлайн-загрузка отключена.")
            ))
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 Загрузка...", callback_data="processing")]])
            results.append(InlineQueryResultCachedVideo(
                id=str(uuid.uuid4()),
                video_file_id=video_ph, 
                title="📥 Скачать по ссылке",
                description=text,
                caption="⏳ *Начинаю загрузку...*", 
                parse_mode="Markdown",
                reply_markup=keyboard
            ))

    # --- СЦЕНАРИЙ 2: ПОИСК МУЗЫКИ ---
    else:
        if not await get_module_status("InlineAudio"):
            if text:
                 results.append(InlineQueryResultArticle(
                    id="disabled_audio", title="⛔ Модуль отключен", 
                    input_message_content=InputTextMessageContent(message_text="⚠️ Инлайн-поиск отключен.")
                ))
            await query.answer(results, cache_time=5, is_personal=True)
            return

        search_query = text
        if not search_query:
            user_db = await get_user(user_id)
            lfm_user = user_db['lastfm_username'] if user_db and 'lastfm_username' in user_db else None
            if lfm_user:
                track = await get_user_recent_track(lfm_user)
                if track: search_query = track['query']

        if search_query:
            result_id = f"music:{search_query[:50]}"
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"🔎 {search_query}", callback_data="processing")]])
            results.append(InlineQueryResultCachedAudio(
                id=result_id, 
                audio_file_id=audio_ph,
                caption=f"🔎 Ищу: {search_query}...",
                reply_markup=keyboard
            ))
        else:
            results.append(InlineQueryResultArticle(
                id="login_hint", title="🔗 Подключить Last.fm", 
                description="Показывай музыку в статусе",
                input_message_content=InputTextMessageContent(
                    message_text="Чтобы подключить Last.fm:\n👉 <code>/login ваш_ник</code>", parse_mode="HTML"
                )
            ))

    await query.answer(results, cache_time=2, is_personal=True)


@router.chosen_inline_result()
async def chosen_handler(chosen_result: types.ChosenInlineResult):
    result_id = chosen_result.result_id
    inline_msg_id = chosen_result.inline_message_id
    user_id = chosen_result.from_user.id 
    if not inline_msg_id: return

    is_music = result_id.startswith("music:")
    url = None
    
    if is_music:
        query = result_id.split(":", 1)[1]
        res = await search_music(query, limit=1)
        if not res:
            try: await bot.edit_message_caption(inline_message_id=inline_msg_id, caption=f"❌ Не найдено: {query}")
            except: pass
            return
        url = res[0]['url']
        try: await bot.edit_message_caption(inline_message_id=inline_msg_id, caption=f"📥 Качаю: {res[0]['title']}...")
        except: pass
    else:
        url = chosen_result.query.strip()

    if not url: return

    custom_opts = {}
    if is_music:
        custom_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{'key': 'EmbedThumbnail'}, {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
        }

    files, folder_path, error, meta = await download_content(url, custom_opts)

    if error:
        try: await bot.edit_message_caption(inline_message_id=inline_msg_id, caption=f"❌ {error}")
        except: pass
        if folder_path: shutil.rmtree(folder_path, ignore_errors=True)
        return

    try:
        media_files = []
        thumb_file = None
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.webp']: thumb_file = f
            elif ext in ['.mp4', '.mov', '.mkv', '.webm', '.ts', '.mp3', '.m4a', '.ogg', '.wav']: media_files.append(f)

        if not media_files: raise Exception("No media")

        target_file = media_files[0]
        filename = os.path.basename(target_file)
        ext = os.path.splitext(target_file)[1].lower()
        
        media_obj = FSInputFile(target_file, filename=filename)
        is_audio = ext in ['.mp3', '.m4a', '.ogg', '.wav']
        
        # --- МЕТАДАННЫЕ ---
        clean_title = None
        meta_artist = None
        meta_title = None

        if meta:
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

        # Чистка имени файла
        fname = os.path.basename(target_file)
        clean_filename = os.path.splitext(fname)[0]
        clean_filename = re.sub(r'\[.*?\]', '', clean_filename).strip()
        if "_" in clean_filename and " " not in clean_filename:
            clean_filename = clean_filename.replace("_", " ")

        final_artist = meta_artist
        final_title = meta_title if meta_title else clean_filename
        if not final_artist and " - " in final_title:
             parts = final_title.split(" - ", 1)
             final_artist = parts[0]
             final_title = parts[1]
             
        # Имя бота (для performer аудио, но не для подписи!)
        bot_performer = f"@{settings.BOT_USERNAME or 'ch4roff_bot'}"
        if not final_artist: final_artist = bot_performer

        caption_header = final_title
        if meta_artist and meta_artist not in final_title:
            caption_header = f"{meta_artist} - {final_title}"
            
        # --- ФОРМИРУЕМ ПОДПИСЬ БЕЗ ТЕГА ---
        clean_header_esc = html.escape(caption_header)
        caption_text = f'<a href="{url}">{clean_header_esc}</a>'
        
        # Для аудио можно добавить ссылку на платформы, но без тега бота
        if is_audio:
            clean_source = url.split("?")[0] if "?" in url else url
            odesli_url = f"https://song.link/{clean_source}"
            caption_text += f" | <a href=\"{odesli_url}\">🌐 Links</a>"
        # ----------------------------------

        telegram_file_id, media_type, sent_msg = None, None, None

        # 3. ОТПРАВКА В ЛС
        try:
            if is_audio:
                thumb = FSInputFile(thumb_file) if thumb_file else None
                reply_markup = get_clip_keyboard(url)
                
                sent_msg = await bot.send_audio(
                    user_id, media_obj, 
                    caption=caption_text, parse_mode="HTML",
                    thumbnail=thumb,
                    performer=final_artist, title=final_title,
                    disable_notification=True,
                    reply_markup=reply_markup
                )
                telegram_file_id = sent_msg.audio.file_id
                media_type = 'audio'
            else:
                sent_msg = await bot.send_video(
                    user_id, media_obj, 
                    caption=caption_text, parse_mode="HTML",
                    thumbnail=None, 
                    supports_streaming=True, disable_notification=True
                )
                telegram_file_id = sent_msg.video.file_id
                media_type = 'video'
        except Exception as e:
            print(f"Inline send error: {e}")
            await bot.edit_message_caption(inline_message_id=inline_msg_id, caption="⚠️ Бот должен быть запущен в ЛС (напишите /start).")
            return

        # 4. ЗАМЕНА ИНЛАЙНА
        if telegram_file_id:
            new_media = None
            
            if media_type == 'audio' and is_music:
                new_media = InputMediaAudio(media=telegram_file_id, caption=caption_text, parse_mode="HTML")
            elif media_type == 'video' and not is_music:
                new_media = InputMediaVideo(media=telegram_file_id, caption=caption_text, parse_mode="HTML", supports_streaming=True)
            
            if new_media:
                await bot.edit_message_media(inline_message_id=inline_msg_id, media=new_media, reply_markup=None)
                if sent_msg:
                    await asyncio.sleep(0.5)
                    try: await bot.delete_message(user_id, sent_msg.message_id)
                    except: pass
            else:
                await bot.edit_message_caption(inline_message_id=inline_msg_id, caption="✅ Файл отправлен в ЛС.")

    except Exception as e:
        print(f"Inline Error: {e}")
        try: await bot.edit_message_caption(inline_message_id=inline_msg_id, caption="⚠️ Ошибка.")
        except: pass
    finally:
        if folder_path and os.path.exists(folder_path): shutil.rmtree(folder_path, ignore_errors=True)