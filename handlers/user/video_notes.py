import os
import shutil
from uuid import uuid4
from aiogram import Router, F, types, Bot
from aiogram.filters import Command
from aiogram.types import FSInputFile
from aiogram.enums import ChatAction
from aiogram.fsm.context import FSMContext
from aiogram.client.session.aiohttp import AiohttpSession

from .router import user_router, check_access_and_update
from services.platforms.TelegramDownloader.videomessage_converter import convert_to_video_note
from services.platforms.TelegramDownloader.workflow import IS_ENABLED as VIDEO_NOTE_ENABLED
from states import VideoNoteState
import messages as msg 

@user_router.message(Command("videomessage"))
async def cmd_videomessage(message: types.Message, state: FSMContext):
    # ИСПРАВЛЕНО: передаем message.from_user
    can, _, _, _ = await check_access_and_update(message.from_user, message)
    if not can: return
    
    if not VIDEO_NOTE_ENABLED:
        await message.answer("⚠️ Функция временно отключена.")
        return

    await message.answer(msg.MSG_VIDEO_MESSAGE, parse_mode="HTML")
    await state.set_state(VideoNoteState.waiting_for_video)

@user_router.message(VideoNoteState.waiting_for_video, F.video)
async def process_video_note(message: types.Message, state: FSMContext):
    await state.clear() 
    video = message.video
    
    if video.file_size > 50 * 1024 * 1024: 
        await message.answer("❌ Видео слишком большое (>50 МБ).")
        return

    msg = await message.answer("⏳ Скачиваю через Cloud API...")
    await message.bot.send_chat_action(message.chat.id, ChatAction.RECORD_VIDEO_NOTE)
    
    unique_id = str(uuid4())
    temp_dir = os.path.join("downloads", f"tg_{unique_id}")
    os.makedirs(temp_dir, exist_ok=True)

    input_path = os.path.join(temp_dir, "input.mp4")
    output_path = os.path.join(temp_dir, "output.mp4")
    
    cloud_session = AiohttpSession()
    cloud_bot = Bot(token=message.bot.token, session=cloud_session)

    try:
        await cloud_bot.download(video, destination=input_path)
        await convert_to_video_note(input_path, output_path)
        
        try:
            await cloud_bot.send_video_note(
                chat_id=message.chat.id, 
                video_note=FSInputFile(output_path), 
                reply_to_message_id=message.message_id
            )
        except:
            await cloud_bot.send_video_note(chat_id=message.chat.id, video_note=FSInputFile(output_path))
        await msg.delete()
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")
        print(f"Video Note Error: {e}")
    finally:
        await cloud_session.close()
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)