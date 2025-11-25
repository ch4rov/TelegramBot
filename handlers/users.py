import os
import shutil
from aiogram import Router, F, types
from aiogram.filters import CommandStart, Command
from aiogram.types import FSInputFile, InputMediaPhoto, InputMediaVideo
from aiogram.enums import ChatAction
from services.database import add_or_update_user
from services.logger import send_log
from services.downloads import download_content, is_valid_url
import messages as msg 

router = Router()

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
        await send_log("SECURITY", f"прислал запрещенную ссылку: <{url}>", user=user)
        return

    await send_log("USER_REQ", f"<{url}>", user=user)
    
    # 1. Статус "Записываю..." пока качаем
    await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.RECORD_VIDEO)
    status_msg = await message.answer(msg.MSG_WAIT)

    files, folder_path, error = await download_content(url)

    if error:
        await status_msg.edit_text(f"⚠️ Ошибка: {error}")
        await send_log("FAIL", f"Download Fail ({error})", user=user)
        return

    try:
        await status_msg.delete()
        
        # --- ЛОГИКА СОРТИРОВКИ ФАЙЛОВ ---
        media_files = []
        thumb_file = None
        
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                # Если нашли картинку - запоминаем её как обложку
                # (берем последнюю найденную, обычно она одна)
                thumb_file = f
            elif ext in ['.mp4', '.mov', '.mkv', '.webm', '.ts', '.mp3', '.m4a', '.ogg', '.wav']:
                media_files.append(f)

        # Если медиафайлов нет, но есть картинки (альбом фото)
        if not media_files and thumb_file:
             # Значит это были просто фото, добавляем их обратно в список для обработки
             media_files = [f for f in files if os.path.splitext(f)[1].lower() in ['.jpg', '.jpeg', '.png', '.webp']]
             thumb_file = None # Обложка не нужна для альбома фото

        if not media_files:
            raise Exception("Файлы скачались, но формат не распознан.")

        # --- СЦЕНАРИИ ОТПРАВКИ ---

        # 1. Одиночное Аудио (YouTube Music, SoundCloud)
        first_ext = os.path.splitext(media_files[0])[1].lower()
        if len(media_files) == 1 and first_ext in ['.mp3', '.m4a', '.ogg', '.wav']:
            await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_VOICE)
            
            audio = FSInputFile(media_files[0])
            thumb = FSInputFile(thumb_file) if thumb_file else None
            
            await message.answer_audio(audio, caption=msg.MSG_CAPTION, thumbnail=thumb)

        # 2. Одиночное Видео (Twitch, YouTube, Reels)
        elif len(media_files) == 1 and first_ext in ['.mp4', '.mov', '.mkv', '.webm', '.ts']:
            await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_VIDEO)
            
            video = FSInputFile(media_files[0])
            thumb = FSInputFile(thumb_file) if thumb_file else None
            
            # width и height можно не указывать, телеграм сам поймет, но thumb важен
            await message.answer_video(video, caption=msg.MSG_CAPTION, thumbnail=thumb, supports_streaming=True)

        # 3. Альбом (TikTok слайды, Instagram карусель)
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
                
            if len(files) > 10:
                await message.answer("⚠️ Отправлены первые 10 файлов.")

        # 4. Если скачалась только одна картинка (странный случай, но бывает)
        else:
             await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_PHOTO)
             await message.answer_photo(FSInputFile(media_files[0]), caption=msg.MSG_CAPTION)

        await send_log("SUCCESS", f"Успешно (<{url}>)", user=user)
        
    except Exception as e:
        await message.answer(msg.MSG_ERR_SEND)
        await send_log("FAIL", f"Send Error: {e}", user=user)
        
    finally:
        if folder_path and os.path.exists(folder_path):
            shutil.rmtree(folder_path, ignore_errors=True)