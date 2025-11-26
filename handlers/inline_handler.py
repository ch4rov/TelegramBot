import os
import shutil
import uuid
import asyncio
import html
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
from services.downloads import download_content, is_valid_url
from services.database_service import get_user
from services.lastfm_service import get_user_recent_track
from services.search_service import search_music
import settings

router = Router()

PLACEHOLDER_VIDEO_ID = "BAACAgIAAxkBAAE-Ud9pJTv8aMQwTbYs7hN5zHqb9Epz6AACE34AAraNMUnM0M23YCUF0DYE" 
PLACEHOLDER_AUDIO_ID = "CQACAgIAAxkDAAIFcWkmO4LEqQIgMGeMrRlkJ7fLKQVxAAKRgQAC2IoxSbFgB6UvfGcbNgQ"

@router.inline_query()
async def inline_query_handler(query: types.InlineQuery):
    text = query.query.strip()
    user_id = query.from_user.id
    results = []

    if text and is_valid_url(text):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 Скачать", callback_data="processing")]
        ])
        results.append(InlineQueryResultCachedVideo(
            id=str(uuid.uuid4()),
            video_file_id=PLACEHOLDER_VIDEO_ID,
            title="📥 Скачать по ссылке",
            description="Нажмите для загрузки видео/фото",
            caption="⏳ *Загрузка...*",
            parse_mode="Markdown",
            reply_markup=keyboard
        ))
    else:
        search_query = text
        if not search_query:
            user_db = await get_user(user_id)
            lfm_user = user_db['lastfm_username'] if user_db and 'lastfm_username' in user_db else None
            if lfm_user:
                track = await get_user_recent_track(lfm_user)
                if track:
                    search_query = track['query']

        if search_query:
            result_id = f"music:{search_query[:50]}"
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"🔎 {search_query}", callback_data="processing")]
            ])
            results.append(InlineQueryResultCachedAudio(
                id=result_id,
                audio_file_id=PLACEHOLDER_AUDIO_ID,
                caption=f"🔎 Ищу: {search_query}...",
                reply_markup=keyboard
            ))
        else:
            results.append(InlineQueryResultArticle(
                id="login_hint",
                title="🔗 Подключить Last.fm",
                description="Показывай свою музыку!",
                input_message_content=InputTextMessageContent(
                    message_text="Чтобы подключить Last.fm:\n👉 <code>/login ваш_ник</code>",
                    parse_mode="HTML"
                )
            ))

    await query.answer(results, cache_time=1, is_personal=True)


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
        custom_opts = {'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]}

    files, folder_path, error = await download_content(url, custom_opts)

    if error:
        try: await bot.edit_message_caption(inline_message_id=inline_msg_id, caption=f"❌ {error}")
        except: pass
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
        filename_no_ext = os.path.splitext(filename)[0]
        
        media_obj = FSInputFile(target_file, filename=filename)
        is_audio = filename.endswith(('.mp3', '.m4a', '.ogg', '.wav'))
        
        clean_title = str(filename_no_ext).replace("&", "&amp;").replace("<", "&lt;")
        caption_text = f'<a href="{url}">{clean_title}</a>'

        telegram_file_id, media_type, sent_msg = None, None, None

        try:
            if is_audio:
                performer, title = "@ch4roff_bot", filename_no_ext
                if " - " in filename_no_ext: 
                    parts = filename_no_ext.split(" - ", 1)
                    performer, title = parts[0], parts[1]
                
                sent_msg = await bot.send_audio(
                    user_id, media_obj, 
                    caption=caption_text, parse_mode="HTML",
                    thumbnail=FSInputFile(thumb_file) if thumb_file else None, # <--- ПЕРЕДАЕМ ОБЛОЖКУ
                    performer=performer, title=title, disable_notification=True
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
        except:
            await bot.edit_message_caption(inline_message_id=inline_msg_id, caption="⚠️ Запустите бота в ЛС.")
            return

        if telegram_file_id:
            new_media = None
            if is_music and is_audio:
                new_media = InputMediaAudio(media=telegram_file_id, caption=caption_text, parse_mode="HTML")
            elif not is_music and not is_audio:
                new_media = InputMediaVideo(media=telegram_file_id, caption=caption_text, parse_mode="HTML", supports_streaming=True)
            
            if new_media:
                await bot.edit_message_media(inline_message_id=inline_msg_id, media=new_media, reply_markup=None)
                if sent_msg:
                    await asyncio.sleep(0.5)
                    try: await bot.delete_message(user_id, sent_msg.message_id)
                    except: pass
            else:
                await bot.edit_message_caption(inline_message_id=inline_msg_id, caption="✅ Файл в ЛС (смена типа).")

    except Exception as e:
        print(f"Inline Error: {e}")
        try: await bot.edit_message_caption(inline_message_id=inline_msg_id, caption="⚠️ Ошибка.")
        except: pass
    finally:
        if folder_path and os.path.exists(folder_path): shutil.rmtree(folder_path, ignore_errors=True)