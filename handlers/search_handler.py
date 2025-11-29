import os
import shutil
import traceback
import html
import json 
from aiogram import Router, F, types
from aiogram.types import FSInputFile, InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ChatAction
from copy import copy

# Импорты сервисов
from services.database_service import add_or_update_user
from services.platforms.platform_manager import download_content
import settings

print("📢 [SYSTEM] Модуль handlers/search_handler.py загружен!")

router = Router()

def make_caption(title_text, url):
    """Формирует стандартную подпись"""
    bot_name = settings.BOT_USERNAME or "ch4roff_bot"
    bot_link = f"@{bot_name}"
    
    if not title_text: return bot_link
    safe_title = html.escape(title_text)
    return f'<a href="{url}">{safe_title}</a>\n\n{bot_link}'

@router.callback_query(F.data == "delete_msg")
async def delete_message(callback: types.CallbackQuery):
    try: await callback.message.delete()
    except: pass

# --- ОБРАБОТКА КНОПКИ "СКАЧАТЬ КЛИП" ---
@router.callback_query(F.data.startswith("get_clip:"))
async def handle_get_clip(callback: types.CallbackQuery):
    try:
        video_id = callback.data.split(":")[1]
        url = f"https://youtu.be/{video_id}"
    except IndexError:
        await callback.answer("❌ Ошибка ID")
        return
    
    await callback.answer("🎬 Загружаю клип...")
    
    try:
        await callback.message.edit_caption(
            caption=f"⏳ Загрузка <a href=\"{url}\">клипа</a>...", 
            parse_mode="HTML", 
            reply_markup=None
        )
    except: pass

    custom_opts = {'force_video': True}

    # --- ИСПРАВЛЕНО: 4 ЗНАЧЕНИЯ ---
    files, folder_path, error, meta = await download_content(url, custom_opts)

    if error:
        try: await callback.message.edit_caption(caption=f"❌ Ошибка: {error}")
        except: pass
        if folder_path: shutil.rmtree(folder_path, ignore_errors=True)
        return

    try:
        await callback.bot.send_chat_action(chat_id=callback.message.chat.id, action=ChatAction.UPLOAD_VIDEO)
        
        video_file = next((f for f in files if f.endswith(('.mp4', '.mov', '.mkv'))), None)
        
        if not video_file: raise Exception("Video file not found")
        
        # Метаданные из META (или JSON)
        if not meta: meta = {}
        clean_title = meta.get('title')

        if not clean_title:
             fname = os.path.basename(video_file)
             clean_title = os.path.splitext(fname)[0]
             if clean_title.endswith("]"):
                 try: clean_title = clean_title.rsplit(" [", 1)[0]
                 except: pass
             if "_" in clean_title and " " not in clean_title:
                 clean_title = clean_title.replace("_", " ")

        final_caption = make_caption(clean_title, url)
        
        await callback.message.reply_video(
            FSInputFile(video_file),
            caption=final_caption,
            parse_mode="HTML",
            thumbnail=None, 
            supports_streaming=True
        )
        
        try:
            await callback.message.edit_caption(caption=final_caption, parse_mode="HTML", reply_markup=None)
        except: pass
        
    except Exception as e:
        try: await callback.message.answer(f"⚠️ Не удалось отправить видео: {e}")
        except: pass
    
    finally:
        if folder_path and os.path.exists(folder_path):
            shutil.rmtree(folder_path, ignore_errors=True)

# --- ОБРАБОТКА ПОИСКА МУЗЫКИ ---
@router.callback_query(F.data.startswith("music:"))
async def handle_music_selection(callback: types.CallbackQuery):
    try:
        data_parts = callback.data.split(":", 2)
        if len(data_parts) < 3:
            await callback.answer("❌ Ошибка данных")
            return
            
        source = data_parts[1]
        content_id = data_parts[2]
        
        if source == "YT": url = f"https://youtu.be/{content_id}"
        elif source == "SC": url = f"https://soundcloud.com/{content_id}"
        else: return

        user = callback.from_user
        await add_or_update_user(user.id, user.username)
        await callback.answer("🎧 Начинаю загрузку...")
        
        try: await callback.message.edit_text(f"📥 <b>Скачиваю трек...</b>\n<code>{url}</code>", reply_markup=None, parse_mode="HTML")
        except: await callback.message.answer(f"📥 <b>Скачиваю...</b>", parse_mode="HTML")

        custom_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{'key': 'EmbedThumbnail'}, {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
        }
        
        # --- ИСПРАВЛЕНО: 4 ЗНАЧЕНИЯ ---
        files, folder_path, error, meta = await download_content(url, custom_opts)

        if error:
            try: await callback.message.edit_text(f"❌ Ошибка: {error}")
            except: pass
            return

        await callback.bot.send_chat_action(chat_id=callback.message.chat.id, action=ChatAction.UPLOAD_VOICE)
        
        target = next((f for f in files if f.endswith(('.mp3', '.m4a', '.ogg', '.wav'))), None)
        thumb = next((f for f in files if f.endswith(('.jpg', '.png', '.webp'))), None)
        if not target: raise Exception("Файл не создан")

        if not meta: meta = {}
        meta_artist = meta.get('artist') or meta.get('uploader')
        meta_title = meta.get('track') or meta.get('title')

        filename = os.path.basename(target)
        bot_name = settings.BOT_USERNAME or "ch4roff_bot"
        performer = f"@{bot_name}"
        title = meta_title or os.path.splitext(filename)[0]
        
        # Чистим название от мусора
        title = re.sub(r'\[.*?\]', '', title).strip()

        if meta_artist: performer = meta_artist
        elif " - " in title:
             p_parts = title.split(" - ", 1)
             performer, title = p_parts[0], p_parts[1]

        caption_text = make_caption(f"{performer} - {title}", url)

        await callback.message.answer_audio(
            FSInputFile(target),
            caption=caption_text,
            parse_mode="HTML",
            thumbnail=FSInputFile(thumb) if thumb else None,
            performer=performer,
            title=title
        )
        
        try: await callback.message.delete()
        except: pass

    except Exception as e:
        print(f"🔥 [SEARCH ERROR] {traceback.format_exc()}")
        try: await callback.message.answer(f"⚠️ Ошибка: {e}")
        except: pass
    finally:
        if folder_path and os.path.exists(folder_path): shutil.rmtree(folder_path, ignore_errors=True)