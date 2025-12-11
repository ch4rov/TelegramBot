import os
import shutil
import traceback
import html
import json
import re  # <--- ДОБАВЛЕН ИМПОРТ
from aiogram import Router, F, types
from aiogram.types import FSInputFile, InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ChatAction
from copy import copy

from services.database_service import add_or_update_user
from services.platforms.platform_manager import download_content
import settings

print("📢 [SYSTEM] Модуль handlers/search_handler.py загружен!")

router = Router()

def make_caption(title_text, url):
    bot_name = settings.BOT_USERNAME or "ch4roff_bot"
    bot_link = f"@{bot_name}"
    if not title_text: return bot_link
    safe_title = html.escape(title_text)
    return f'<a href="{url}">{safe_title}</a>\n\n{bot_link}'

@router.callback_query(F.data == "delete_msg")
async def delete_message(callback: types.CallbackQuery):
    try: await callback.message.delete()
    except: pass

# --- КЛИПЫ (ВИДЕО) ---
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
            parse_mode="HTML", reply_markup=None
        )
    except: pass

    custom_opts = {'force_video': True}
    
    # Распаковка 4 значений
    files, folder_path, error, meta = await download_content(url, custom_opts)

    if error:
        try: await callback.message.edit_caption(caption=f"❌ Ошибка: {error}")
        except: pass
        if folder_path: shutil.rmtree(folder_path, ignore_errors=True)
        return

    try:
        await callback.bot.send_chat_action(chat_id=callback.message.chat.id, action=ChatAction.UPLOAD_VIDEO)
        
        # Ищем видео
        video_file = next((f for f in files if f.endswith(('.mp4', '.mov', '.mkv', '.webm'))), None)
        if not video_file: raise Exception("Video file not found")
        
        clean_title = ""
        # 1. Пробуем из метаданных (переданных из загрузчика)
        if meta:
            clean_title = meta.get('title')

        # 2. Если нет, пробуем читать JSON с диска
        if not clean_title:
            info_json_file = next((f for f in files if f.endswith(('.info.json'))), None)
            if info_json_file:
                try:
                    with open(info_json_file, 'r', encoding='utf-8') as f:
                        info = json.load(f)
                        if info.get('title'): clean_title = info.get('title')
                except: pass
        
        # 3. Fallback на имя файла
        if not clean_title:
             fname = os.path.basename(video_file)
             clean_title = os.path.splitext(fname)[0]
             # Чистка
             clean_title = re.sub(r'\[.*?\]', '', clean_title).strip()
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

# --- МУЗЫКА (АУДИО) ---
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
        
        # Распаковка 4 значений
        files, folder_path, error, meta = await download_content(url, custom_opts)

        if error:
            try: await callback.message.edit_text(f"❌ Ошибка: {error}")
            except: pass
            return

        await callback.bot.send_chat_action(chat_id=callback.message.chat.id, action=ChatAction.UPLOAD_VOICE)
        
        # Ищем аудио (Расширенный список!)
        target = next((f for f in files if f.endswith(('.mp3', '.m4a', '.ogg', '.wav', '.webm', '.opus'))), None)
        thumb = next((f for f in files if f.endswith(('.jpg', '.png', '.webp'))), None)

        if not target: 
            # Логируем файлы, чтобы понять почему не нашли
            print(f"❌ [SEARCH ERROR] Файлы в папке: {files}")
            raise Exception("Файл не создан (или неверный формат)")

        # --- МЕТАДАННЫЕ ---
        if not meta: meta = {}
        meta_artist = meta.get('artist') or meta.get('uploader')
        meta_title = meta.get('track') or meta.get('title')

        # Если мета пустая, пробуем читать JSON с диска
        if not meta_title:
            info_json_file = next((f for f in files if f.endswith(('.info.json'))), None)
            if info_json_file:
                try:
                    with open(info_json_file, 'r', encoding='utf-8') as f:
                        info = json.load(f)
                        meta_artist = info.get('artist') or info.get('uploader')
                        meta_title = info.get('track') or info.get('title')
                except: pass

        filename = os.path.basename(target)
        bot_name = settings.BOT_USERNAME or "ch4roff_bot"
        performer = f"@{bot_name}"
        
        # Чистим имя файла от [ID]
        raw_name = os.path.splitext(filename)[0]
        clean_name = re.sub(r'\[.*?\]', '', raw_name).strip()
        
        title = meta_title or clean_name

        if meta_artist:
            performer = meta_artist
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