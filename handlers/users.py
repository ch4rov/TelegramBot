import os
import shutil
import tempfile
from uuid import uuid4
from aiogram import Router, F, types
from aiogram.filters import CommandStart, Command, ChatMemberUpdatedFilter, KICKED, MEMBER
from aiogram.types import FSInputFile, InputMediaPhoto, InputMediaVideo, ChatMemberUpdated
from aiogram.enums import ChatAction

# Импорты (ВАЖНО: set_user_active добавлен)
from services.database import add_or_update_user, get_cached_file, save_cached_file, set_user_active
from logs.logger import send_log_groupable as send_log, log_other_message
from services.downloads import download_content, is_valid_url
from services.cache import get_cached_content, add_to_cache
import messages as msg 
import settings 

router = Router()
ACTIVE_DOWNLOADS = {}
ADMIN_ID = os.getenv("ADMIN_ID")

# --- СЛУШАТЕЛИ БЛОКИРОВКИ (В САМОМ НАЧАЛЕ) ---

@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=KICKED))
async def user_blocked_bot(event: ChatMemberUpdated):
    """Пользователь заблокировал бота"""
    # Обновляем базу: is_active = 0
    await set_user_active(event.from_user.id, False)
    # Логируем как INFO (не FAIL), так как это действие юзера
    await send_log("INFO", "Пользователь заблокировал бота ⛔", user=event.from_user)

@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=MEMBER))
async def user_unblocked_bot(event: ChatMemberUpdated):
    """Пользователь разблокировал бота"""
    # Обновляем базу: is_active = 1
    await set_user_active(event.from_user.id, True)
    # Логируем как INFO (чтобы логгер подставил User Info)
    await send_log("INFO", "Пользователь разблокировал бота 🟢", user=event.from_user)


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
        log_text = f"Новый пользователь: {message.from_user.username} (ID: {message.from_user.id})"
        await send_log("NEW_USER", log_text, user=message.from_user)
        
        if ADMIN_ID:
            try:
                clean_name = message.from_user.full_name
                username = f"@{message.from_user.username}" if message.from_user.username else "без юзернейма"
                await message.bot.send_message(
                    ADMIN_ID,
                    f"🔔 **Новый пользователь!**\n"
                    f"👤 {clean_name} ({username})\n"
                    f"🆔 `{message.from_user.id}`",
                    parse_mode="Markdown"
                )
            except: pass

@router.message(F.text.contains("http"))
async def handle_link(message: types.Message):
    user = message.from_user
    can, _ = await check_access_and_update(user, message)
    if not can: return
    
    # --- СТЕРИЛИЗАЦИЯ ССЫЛКИ (САМОЕ ВАЖНОЕ) ---
    raw_text = message.text.strip()
    
    # 1. Если есть pipe "|", отделяем подпись
    caption_override = None
    if "|" in raw_text:
        parts = raw_text.split("|", 1)
        url_part = parts[0].strip()
        caption_override = parts[1].strip()
    else:
        url_part = raw_text

    # 2. ЖЕСТКАЯ ЧИСТКА
    # Берем всё до первого пробела, переноса строки, точки с запятой или знака доллара
    # Это физически отрезает хвост "; $(curl ...)"
    for bad_char in [';', '\n', ' ', '$', '`', '|']: 
        if bad_char in url_part:
            url_part = url_part.split(bad_char)[0]

    url = url_part.strip()
    # -------------------------------------------
    
    if not is_valid_url(url):
        await message.answer(msg.MSG_ERR_LINK)
        await send_log("SECURITY", f"прислал запрещенную ссылку: <{url}>", user=user)
        return

    # 1. SMART CACHE
    db_cache = await get_cached_file(url)
    if db_cache:
        file_id = db_cache['file_id']
        media_type = db_cache['media_type']
        final_caption = caption_override or msg.MSG_CAPTION
        
        await send_log("SUCCESS", f"Успешно [DB CACHE] (<{url}>)", user=user)
        try:
            if media_type == 'audio': await message.answer_audio(file_id, caption=final_caption)
            elif media_type == 'video': await message.answer_video(file_id, caption=final_caption)
            elif media_type == 'photo': await message.answer_photo(file_id, caption=final_caption)
            return 
        except Exception: pass

    # 2. FILE CACHE
    cached_files, cached_folder = await get_cached_content(url)
    status_msg = None 
    placeholder_msg = None
    tmp_path = None
    
    if cached_files:
        files = cached_files
        folder_path = cached_folder 
        from_cache = True
    else:
        from_cache = False
        current_downloads = ACTIVE_DOWNLOADS.get(user.id, 0)
        if current_downloads >= settings.MAX_CONCURRENT_DOWNLOADS:
            await message.answer(f"⚠️ Слишком много загрузок. Подождите.")
            return

        ACTIVE_DOWNLOADS[user.id] = current_downloads + 1
        await send_log("USER_REQ", f"<{url}>", user=user)
        await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)

        try:
            tmp_name = f"placeholder_{uuid4().hex}.bin"
            tmp_path = os.path.join(tempfile.gettempdir(), tmp_name)
            with open(tmp_path, "wb") as tf: tf.write(b"\0" * 2048)
            try: placeholder_msg = await message.answer_document(FSInputFile(tmp_path), caption=msg.MSG_WAIT)
            except: pass
            try: status_msg = await message.answer(msg.MSG_WAIT)
            except: pass
        except Exception:
            status_msg = await message.answer(msg.MSG_WAIT)

        files, folder_path, error = await download_content(url)

        if error:
            if status_msg: await status_msg.edit_text(f"⚠️ Ошибка: {error}")
            else: await message.answer(f"⚠️ Ошибка: {error}")
            
            await send_log("FAIL", f"Download Fail ({error})", user=user)
            
            if user.id in ACTIVE_DOWNLOADS:
                if ACTIVE_DOWNLOADS[user.id] > 0: ACTIVE_DOWNLOADS[user.id] -= 1
                else: del ACTIVE_DOWNLOADS[user.id]
            
            if tmp_path and os.path.exists(tmp_path):
                try: os.remove(tmp_path)
                except: pass
            return

    # 3. SENDING
    try:
        media_files = []
        thumb_file = None
        
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.webp']: thumb_file = f
            elif ext in ['.mp4', '.mov', '.mkv', '.webm', '.ts', '.mp3', '.m4a', '.ogg', '.wav']: media_files.append(f)

        image_exts = ['.jpg', '.jpeg', '.png', '.webp']
        if not media_files and thumb_file:
             media_files = [f for f in files if os.path.splitext(f)[1].lower() in image_exts]
             thumb_file = None

        if not media_files: raise Exception("Файлы не найдены.")

        filename_full = os.path.basename(media_files[0])
        filename_no_ext = os.path.splitext(filename_full)[0]
        first_ext = os.path.splitext(media_files[0])[1].lower()

        sent_msg = None
        media_type_str = None

        if len(media_files) == 1 and first_ext in ['.mp3', '.m4a', '.ogg', '.wav']:
            await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_VOICE)
            performer = "Unknown"
            title = filename_no_ext
            if " - " in filename_no_ext:
                parts = filename_no_ext.split(" - ", 1)
                performer = parts[0]
                title = parts[1]
            
            sent_msg = await message.answer_audio(
                FSInputFile(media_files[0]), 
                caption=caption_override or msg.MSG_CAPTION, 
                thumbnail=FSInputFile(thumb_file) if thumb_file else None,
                performer=performer, title=title
            )
            media_type_str = "audio"

        elif len(media_files) == 1 and first_ext in ['.mp4', '.mov', '.mkv', '.webm', '.ts']:
            await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_VIDEO)
            clean_caption = f"{filename_no_ext}\n{msg.MSG_CAPTION}"
            
            sent_msg = await message.answer_video(
                FSInputFile(media_files[0]), 
                caption=caption_override or clean_caption, 
                thumbnail=None, # Fix squared video
                supports_streaming=True
            )
            media_type_str = "video"

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
                media_group[0].caption = caption_override or msg.MSG_CAPTION
                await message.answer_media_group(media_group)

        else:
            sent_msg = await message.answer_photo(FSInputFile(media_files[0]), caption=caption_override or msg.MSG_CAPTION)
            media_type_str = "photo"

        prefix = "[КЭШ] " if from_cache else ""
        await send_log("SUCCESS", f"{prefix}Успешно (<{url}>)", user=user)

        if sent_msg and media_type_str:
            fid = None
            if media_type_str == "video" and sent_msg.video: fid = sent_msg.video.file_id
            elif media_type_str == "audio" and sent_msg.audio: fid = sent_msg.audio.file_id
            elif media_type_str == "photo" and sent_msg.photo: fid = sent_msg.photo[-1].file_id
            if fid: await save_cached_file(url, fid, media_type_str)

        if not from_cache and folder_path:
            await add_to_cache(url, folder_path, files)

        try:
            if placeholder_msg: await message.bot.delete_message(message.chat.id, placeholder_msg.message_id)
            if status_msg: await message.bot.delete_message(message.chat.id, status_msg.message_id)
        except: pass

    except Exception as e:
        await message.answer(msg.MSG_ERR_SEND)
        await send_log("FAIL", f"Send Error: {e}", user=user)
        if not from_cache and folder_path and os.path.exists(folder_path):
             shutil.rmtree(folder_path, ignore_errors=True)
        
    finally:
        try:
            if tmp_path and os.path.exists(tmp_path): os.remove(tmp_path)
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
    try:
        await log_other_message(txt, user=user)
    except: pass