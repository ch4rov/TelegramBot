import os
import shutil
import tempfile
from uuid import uuid4
from aiogram import Router, F, types
from aiogram.filters import CommandStart, Command
from aiogram.types import FSInputFile, InputMediaPhoto, InputMediaVideo
from aiogram.enums import ChatAction

from services.database import add_or_update_user, get_cached_file, save_cached_file
from logs.logger import send_log_groupable as send_log, log_other_message
from services.downloads import download_content, is_valid_url
from services.cache import get_cached_content, add_to_cache
from services.url_cleaner import clean_url
import messages as msg 
import settings

router = Router()
ACTIVE_DOWNLOADS = {}
ADMIN_ID = os.getenv("ADMIN_ID")

async def check_access_and_update(user, message: types.Message):
    is_new, is_banned, ban_reason = await add_or_update_user(user.id, user.username)
    if is_banned:
        reason_text = f"\nПричина: {ban_reason}" if ban_reason else ""
        text = f"⛔ Вы заблокированы.{reason_text}\nСвязь с админом: @ch4rov"
        await message.answer(text)
        return False, False
    return True, is_new

@router.message(Command("menu"))
async def cmd_menu(message: types.Message):
    can, _ = await check_access_and_update(message.from_user, message)
    if not can: return
    text = msg.MSG_MENU_HEADER + msg.MSG_MENU_USER
    if str(message.from_user.id) == str(ADMIN_ID):
        text += msg.MSG_MENU_ADMIN
    await message.answer(text, parse_mode="Markdown")

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    can, is_new = await check_access_and_update(message.from_user, message)
    if not can: return
    await message.answer(msg.MSG_START)
    if is_new:
        await send_log("NEW_USER", f"New: {message.from_user.full_name} (ID: {message.from_user.id})", user=message.from_user)
        if ADMIN_ID:
            try: await message.bot.send_message(ADMIN_ID, f"🔔 New User: {message.from_user.full_name}")
            except: pass

@router.message(F.text.contains("http"))
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
    
    # Чистка от инъекций
    for bad_char in [';', '\n', ' ', '$', '`', '|']: 
        if bad_char in url_raw: url_raw = url_raw.split(bad_char)[0]

    # Нормализация
    url = clean_url(url_raw)

    if not is_valid_url(url):
        await message.answer(msg.MSG_ERR_LINK)
        await send_log("SECURITY", f"bad link: <{url_raw}>", user=user)
        return

    # 1. SMART CACHE
    db_cache = await get_cached_file(url)
    
    # Функция для создания подписи
    def make_caption(title, link):
        bot_link = "@ch4roff_bot"
        if caption_override: return f"{caption_override}\n\n{bot_link}"
        if not title: return bot_link
        # Экранируем спецсимволы для HTML
        safe_title = str(title).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return f'<a href="{link}">{safe_title}</a>\n\n{bot_link}'

    if db_cache:
        file_id = db_cache['file_id']
        media_type = db_cache['media_type']
        saved_title = db_cache['title']
        
        caption_html = make_caption(saved_title, url)
        
        await send_log("SUCCESS", f"Успешно [DB CACHE] (<{url}>)", user=user)
        try:
            if media_type == 'audio': await message.answer_audio(file_id, caption=caption_html, parse_mode="HTML")
            elif media_type == 'video': await message.answer_video(file_id, caption=caption_html, parse_mode="HTML")
            elif media_type == 'photo': await message.answer_photo(file_id, caption=caption_html, parse_mode="HTML")
            return 
        except Exception: pass

    # 2. ЗАГРУЗКА
    cached_files, cached_folder = await get_cached_content(url)
    tmp_path = None
    
    if cached_files:
        files = cached_files
        folder_path = cached_folder 
        from_cache = True
    else:
        from_cache = False
        if ACTIVE_DOWNLOADS.get(user.id, 0) >= settings.MAX_CONCURRENT_DOWNLOADS:
            await message.answer("⚠️ Слишком много загрузок. Подождите.")
            return

        ACTIVE_DOWNLOADS[user.id] = ACTIVE_DOWNLOADS.get(user.id, 0) + 1
        await send_log("USER_REQ", f"<{url}>", user=user)
        await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)

        # Отправляем только ⏳ сообщение, без обновлений
        try:
            await message.answer("⏳")
        except:
            pass

        files, folder_path, error = await download_content(url)

        if error:
            await message.answer(f"⚠️ {error}")
            
            await send_log("FAIL", f"Fail: {error}", user=user)
            
            if ADMIN_ID and str(user.id) == str(ADMIN_ID):
                try: await message.bot.send_message(ADMIN_ID, f"❌ Error:\n{url}\n{error}")
                except: pass

            if user.id in ACTIVE_DOWNLOADS:
                if ACTIVE_DOWNLOADS[user.id] > 0: ACTIVE_DOWNLOADS[user.id] -= 1
                else: del ACTIVE_DOWNLOADS[user.id]
            
            # Исправленный блок удаления временного файла
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except: pass
            return

    # 3. ОТПРАВКА
    try:
        media_files = []
        thumb_file = None
        
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.webp']: thumb_file = f
            elif ext in ['.mp4', '.mov', '.mkv', '.webm', '.ts', '.mp3', '.m4a', '.ogg', '.wav']: media_files.append(f)

        image_exts = ['.jpg', '.jpeg', '.png', '.webp']
        video_exts = ['.mp4', '.mov', '.mkv', '.webm', '.ts']
        
        if not media_files and thumb_file:
             media_files = [f for f in files if os.path.splitext(f)[1].lower() in image_exts]
             thumb_file = None

        if not media_files: raise Exception("Files not found")

        # Приоритет Видео
        has_video = any(os.path.splitext(f)[1].lower() in video_exts for f in media_files)
        if has_video:
            media_files = [f for f in media_files if os.path.splitext(f)[1].lower() in video_exts]

        filename_full = os.path.basename(media_files[0])
        filename_no_ext = os.path.splitext(filename_full)[0]
        first_ext = os.path.splitext(media_files[0])[1].lower()

        sent_msg = None
        media_type_str = None
        
        final_caption = make_caption(filename_no_ext, url)

        # 1. АУДИО
        if len(media_files) == 1 and first_ext in ['.mp3', '.m4a', '.ogg', '.wav']:
            await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_VOICE)
            performer, title = "Unknown", filename_no_ext
            if " - " in filename_no_ext:
                parts = filename_no_ext.split(" - ", 1)
                performer, title = parts[0], parts[1]
            
            sent_msg = await message.answer_audio(
                FSInputFile(media_files[0]), 
                caption=final_caption,
                parse_mode="HTML",
                thumbnail=FSInputFile(thumb_file) if thumb_file else None,
                performer=performer, title=title
            )
            media_type_str = "audio"

        # 2. ВИДЕО
        elif len(media_files) == 1 and first_ext in video_exts:
            await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_VIDEO)
            
            sent_msg = await message.answer_video(
                FSInputFile(media_files[0]), 
                caption=final_caption, 
                parse_mode="HTML",
                thumbnail=None, 
                supports_streaming=True
            )
            media_type_str = "video"

        # 3. АЛЬБОМ
        elif len(media_files) > 1:
            await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_MEDIA)
            media_group = []
            for f_path in media_files[:10]:
                f_ext = os.path.splitext(f_path)[1].lower()
                inp = FSInputFile(f_path)
                if f_ext in ['.jpg', '.jpeg', '.png']: media_group.append(InputMediaPhoto(media=inp))
                else: media_group.append(InputMediaVideo(media=inp))
            
            if media_group:
                media_group[0].caption = final_caption
                media_group[0].parse_mode = "HTML"
                await message.answer_media_group(media_group)

        # 4. ФОТО
        else:
            sent_msg = await message.answer_photo(FSInputFile(media_files[0]), caption=final_caption, parse_mode="HTML")
            media_type_str = "photo"

        prefix = "[КЭШ] " if from_cache else ""
        await send_log("SUCCESS", f"{prefix}Успешно (<{url}>)", user=user)

        if sent_msg and media_type_str:
            fid = None
            if media_type_str == "video" and sent_msg.video: fid = sent_msg.video.file_id
            elif media_type_str == "audio" and sent_msg.audio: fid = sent_msg.audio.file_id
            elif media_type_str == "photo" and sent_msg.photo: fid = sent_msg.photo[-1].file_id
            
            if fid:
                await save_cached_file(url, fid, media_type_str, title=filename_no_ext)

        if not from_cache and folder_path:
            await add_to_cache(url, folder_path, files)

    except Exception as e:
        await message.answer(msg.MSG_ERR_SEND)
        await send_log("FAIL", f"Send Error: {e}", user=user)
        if not from_cache and folder_path and os.path.exists(folder_path):
             shutil.rmtree(folder_path, ignore_errors=True)
        
    finally:
        # Исправленный блок удаления
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except: pass

        if not from_cache:
            if user.id in ACTIVE_DOWNLOADS:
                if ACTIVE_DOWNLOADS[user.id] > 0: ACTIVE_DOWNLOADS[user.id] -= 1
                else: del ACTIVE_DOWNLOADS[user.id]

@router.message(F.text & ~F.text.contains("http"))
async def handle_plain_text(message: types.Message):
    user = message.from_user
    if not message.text: return
    txt = message.text.strip()
    if not txt or txt.startswith("/"): return
    can, _ = await check_access_and_update(user, message)
    if not can: return
    try: await log_other_message(txt, user=user)
    except: pass