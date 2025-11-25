import os
import asyncio
from aiogram import Router, F, types
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile
from aiogram.enums import ChatAction
from services.database import add_or_update_user, check_ban
from services.logger import send_log
from services.downloader import download_video

# Импортируем наши тексты
import messages as msg 

router = Router()

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    if await check_ban(message.from_user.id): return
    
    is_new = await add_or_update_user(message.from_user.id, message.from_user.username)
    
    # Используем переменную из файла messages.py
    await message.answer(msg.MSG_START)
    
    if is_new:
        await send_log("INFO", f"🎉 Новый пользователь: @{message.from_user.username} ({message.from_user.id})")

@router.message(F.text.contains("http"))
async def handle_link(message: types.Message):
    user_id = message.from_user.id
    if await check_ban(user_id): return
    
    url = message.text.strip()
    await add_or_update_user(user_id, message.from_user.username)
    
    # 1. Тут теперь просто смайлик из переменной
    status_msg = await message.answer(msg.MSG_WAIT)
    
    await send_log("USER", f"Скачивание: {url} (от @{message.from_user.username})")

    file_path, error = await download_video(url)

    if error:
        # Для ошибок с динамическим текстом можно оставить f-строку или склеить
        await status_msg.edit_text(f"⚠️ Ошибка: {error}")
        await send_log("ERROR", f"Ошибка скачивания: {error}")
        return

    try:
        await status_msg.delete()
        await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_VIDEO)

        video = FSInputFile(file_path)
        
        # 2. Тут теперь твоя подпись из переменной
        await message.answer_video(video, caption=msg.MSG_CAPTION)
        
        await send_log("INFO", f"Видео успешно отправлено @{message.from_user.username}")
        
    except Exception as e:
        await message.answer(msg.MSG_ERR_SEND)
        await send_log("ERROR", f"Ошибка отправки в TG: {e}")
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass