import os
import shutil
from aiogram import Router, F, types
from aiogram.filters import CommandStart, Command
from aiogram.types import FSInputFile, InputMediaPhoto, InputMediaVideo
from aiogram.enums import ChatAction
from services.database import add_or_update_user
from logs.logger import send_log_groupable as send_log
from services.downloads import download_content, is_valid_url
from services.cache import get_cached_content, add_to_cache
import messages as msg 
import settings # Импортируем настройки

router = Router()

ACTIVE_DOWNLOADS = {}

def is_admin(user_id):
    return str(user_id) == str(os.getenv("ADMIN_ID"))

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
    if is_admin(message.from_user.id):
        text += msg.MSG_MENU_ADMIN
    await message.answer(text, parse_mode="Markdown")

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    can, is_new = await check_access_and_update(message.from_user, message)
    if not can: return
    await message.answer(msg.MSG_START)
    if is_new:
        log_text = f"Новый пользователь: {message.from_user.username} (ID: {message.from_user.id})"
        await send_log("NEW_USER", log_text, user=message.from_user)

@router.message(F.text.contains("http"))
async def handle_link(message: types.Message):
    user = message.from_user
    can, _ = await check_access_and_update(user, message)
    if not can: return
    
    url = message.text.strip()
    
    if not is_valid_url(url):
        await message.answer(msg.MSG_ERR_LINK)
        # ВАЖНО: < > вокруг url отключают предпросмотр в Discord
        await send_log("SECURITY", f"прислал запрещенную ссылку: <{url}>", user=user)
        return

    # --- ПРОВЕРКА КЭША ---
    cached_files, cached_folder = await get_cached_content(url)
    
    status_msg = None 
    
    if cached_files:
        files = cached_files
        folder_path = cached_folder 
        from_cache = True
    else:
        from_cache = False
        
        current_downloads = ACTIVE_DOWNLOADS.get(user.id, 0)
        # Лимит берем из settings
        if current_downloads >= settings.MAX_CONCURRENT_DOWNLOADS:
            await message.answer(f"⚠️ Слишком много загрузок ({current_downloads}/{settings.MAX_CONCURRENT_DOWNLOADS}). Подождите.")
            return

        ACTIVE_DOWNLOADS[user.id] = current_downloads + 1
        await send_log("USER_REQ", f"<{url}>", user=user)
        
        await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
        status_msg = await message.answer(msg.MSG_WAIT)

        files, folder_path, error = await download_content(url)

        if error:
            if status_msg: await status_msg.edit_text(f"⚠️ Ошибка: {error}")
            else: await message.answer(f"⚠️ Ошибка: {error}")
            
            await send_log("FAIL", f"Download Fail ({error})", user=user)
            if user.id in ACTIVE_DOWNLOADS:
                if ACTIVE_DOWNLOADS[user.id] > 0: ACTIVE_DOWNLOADS[user.id] -= 1
                else: del ACTIVE_DOWNLOADS[user.id]
            return

    # --- ОТПРАВКА ---
    try:
        if status_msg:
            await status_msg.delete()

        media_files = []
        thumb_file = None
        
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                thumb_file = f
            elif ext in ['.mp4', '.mov', '.mkv', '.webm', '.ts', '.mp3', '.m4a', '.ogg', '.wav']:
                media_files.append(f)

        if not media_files and thumb_file:
             media_files = [f for f in files if os.path.splitext(f)[1].lower() in ['.jpg', '.jpeg', '.png', '.webp']]
             thumb_file = None

        if not media_files:
            raise Exception("Файлы не найдены.")

        filename_full = os.path.basename(media_files[0])
        filename_no_ext = os.path.splitext(filename_full)[0]
        first_ext = os.path.splitext(media_files[0])[1].lower()

        # 1. АУДИО (YouTube Music, SoundCloud)
        if len(media_files) == 1 and first_ext in ['.mp3', '.m4a', '.ogg', '.wav']:
            await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_VOICE)
            
            performer = "Unknown"
            title = filename_no_ext
            if " - " in filename_no_ext:
                parts = filename_no_ext.split(" - ", 1)
                performer = parts[0]
                title = parts[1]
            
            await message.answer_audio(
                FSInputFile(media_files[0]), 
                caption=msg.MSG_CAPTION, 
                thumbnail=FSInputFile(thumb_file) if thumb_file else None,
                performer=performer,
                title=title
            )

        # 2. ВИДЕО
        elif len(media_files) == 1 and first_ext in ['.mp4', '.mov', '.mkv', '.webm', '.ts']:
            await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_VIDEO)
            clean_caption = f"{filename_no_ext}\n{msg.MSG_CAPTION}"
            
            await message.answer_video(
                FSInputFile(media_files[0]), 
                caption=clean_caption, 
                thumbnail=FSInputFile(thumb_file) if thumb_file else None, 
                supports_streaming=True
            )

        # 3. АЛЬБОМЫ
        elif len(media_files) > 1:
            await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_MEDIA)
            media_group = []
            for file_path in media_files[:10]:
                f_ext = os.path.splitext(file_path)[1].lower()
                input_file = FSInputFile(file_path)
                if f_ext in ['.jpg', '.jpeg', '.png', '.webp']:
                    media_group.append(InputMediaPhoto(media=input_file))
                elif f_ext in ['.mp4', '.mov', '.mkv']:
                    media_group.append(InputMediaVideo(media=input_file))
            if media_group:
                media_group[0].caption = msg.MSG_CAPTION
                await message.answer_media_group(media_group)

        else:
             await message.answer_photo(FSInputFile(media_files[0]), caption=msg.MSG_CAPTION)

        # ЛОГИ: Добавляем [КЭШ] и скобки < >
        prefix = "[КЭШ] " if from_cache else ""
        await send_log("SUCCESS", f"{prefix}Успешно (<{url}>)", user=user)

        # Сохранение в кэш (если новая загрузка)
        if not from_cache and folder_path:
            await add_to_cache(url, folder_path, files)
        
    except Exception as e:
        await message.answer(msg.MSG_ERR_SEND)
        await send_log("FAIL", f"Send Error: {e}", user=user)
        if not from_cache and folder_path and os.path.exists(folder_path):
             shutil.rmtree(folder_path, ignore_errors=True)
        
    finally:
        if not from_cache:
            if user.id in ACTIVE_DOWNLOADS:
                if ACTIVE_DOWNLOADS[user.id] > 0:
                    ACTIVE_DOWNLOADS[user.id] -= 1
                else:
                    del ACTIVE_DOWNLOADS[user.id]