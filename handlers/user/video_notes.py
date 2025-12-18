# -*- coding: utf-8 -*-
import os
import asyncio
import logging
import uuid
import subprocess
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.exceptions import TelegramBadRequest
from aiogram.enums import ChatAction
from core.config import config
from services.database.repo import is_user_banned, increment_request_count

logger = logging.getLogger(__name__)
router = Router()


def _t(user_lang: str, key: str) -> str:
    lang = (user_lang or "en").lower()
    if key == "too_big":
        return (
            "❌ Видео слишком большое. Telegram не дает боту скачать такие файлы (лимит около 20MB).\n"
            "Отправь видео меньше ~20МБ."
            if lang == "ru"
            else "❌ Video is too large. Telegram doesn't allow bots to download such files (limit is ~20MB).\nSend a video smaller than ~20MB."
        )
    if key == "generic_error":
        return "❌ Ошибка обработки видео" if lang == "ru" else "❌ Error processing video"
    return ""


async def _send_action(message: types.Message, action: ChatAction):
    try:
        await message.bot.send_chat_action(chat_id=message.chat.id, action=action)
    except Exception:
        pass


async def _pulse_action(message: types.Message, get_action, stop: asyncio.Event, interval_s: float = 4.0):
    while not stop.is_set():
        try:
            await _send_action(message, get_action())
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_s)
        except asyncio.TimeoutError:
            continue

class VideoNoteState(StatesGroup):
    recording = State()

@router.message(Command("videomessage"))
async def cmd_videomessage(message: types.Message, state: FSMContext):
    """Video message mode"""
    try:
        user = message.from_user
        
        # Проверяем бан
        banned = await is_user_banned(user.id)
        if banned:
            await message.answer("You are banned from using this bot.", disable_notification=True)
            return
        
        await increment_request_count(user.id)
        
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ Выход / Exit")]],
            resize_keyboard=True
        )
        await message.answer(
            "🎥 <b>Video Note Mode</b>\n\nSend me any video and I'll convert it to a video note (square 640x640).\n\n"
            "Press ❌ Exit button to leave this mode.",
            reply_markup=kb,
            disable_notification=True,
            parse_mode="HTML"
        )
        await state.set_state(VideoNoteState.recording)
        logger.info(f"User {user.id} entered video note mode")
    except Exception as e:
        logger.error(f"Error in cmd_videomessage: {e}")

@router.message(VideoNoteState.recording, F.text.in_(["❌ Выход / Exit", "Exit", "exit"]))
async def exit_mode(message: types.Message, state: FSMContext):
    """Exit video mode"""
    try:
        await state.clear()
        await message.answer(
            "Video note mode disabled.",
            reply_markup=ReplyKeyboardRemove(),
            disable_notification=True
        )
        logger.info(f"User {message.from_user.id} exited video note mode")
    except Exception as e:
        logger.error(f"Error in exit_mode: {e}")

@router.message(VideoNoteState.recording, F.video)
async def process_video(message: types.Message, user_lang: str = "en"):
    """Process video"""
    status = None
    stop = asyncio.Event()
    current_action = ChatAction.UPLOAD_DOCUMENT
    pulse_task: asyncio.Task | None = None
    try:
        status = await message.answer("⏳", disable_notification=True)

        def _get_action():
            return current_action

        pulse_task = asyncio.create_task(_pulse_action(message, _get_action, stop))

        # Bots can't download very large user-uploaded files via getFile (Telegram-side limit).
        try:
            if message.video and message.video.file_size and message.video.file_size > 20 * 1024 * 1024:
                await message.answer(_t(user_lang, "too_big"), disable_notification=True)
                try:
                    if status:
                        await status.delete()
                except Exception:
                    pass
                stop.set()
                if pulse_task:
                    try:
                        await pulse_task
                    except Exception:
                        pass
                return
        except Exception:
            pass
        
        file_id = message.video.file_id
        file = await message.bot.get_file(file_id)
        
        temp_dir = "tempfiles"
        os.makedirs(temp_dir, exist_ok=True)
        
        input_path = os.path.join(temp_dir, f"vid_in_{uuid.uuid4()}.mp4")
        output_path = os.path.join(temp_dir, f"vid_out_{uuid.uuid4()}.mp4")
        
        await message.bot.download_file(file.file_path, input_path)

        # Stage: converting into video note
        current_action = ChatAction.RECORD_VIDEO_NOTE
        
        # FFmpeg: Crop to square (min side), scale 640x640, format mp4
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        installs_dir = os.path.join(base_dir, "core", "installs")
        ffmpeg_path = os.path.join(installs_dir, "ffmpeg.exe")
        if not os.path.exists(ffmpeg_path):
            ffmpeg_path = "ffmpeg"

        vf = "crop=min(iw\\,ih):min(iw\\,ih),scale=640:640"
        args = [
            ffmpeg_path,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            input_path,
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "26",
            "-c:a",
            "aac",
            "-b:a",
            "64k",
            "-f",
            "mp4",
            output_path,
        ]

        completed = await asyncio.to_thread(
            subprocess.run,
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0:
            err = (completed.stderr or b"").decode("utf-8", errors="ignore").strip()
            raise Exception(err or f"ffmpeg failed with code {completed.returncode}")
        
        if os.path.exists(output_path):
            # Stage: uploading video note to Telegram
            current_action = ChatAction.UPLOAD_VIDEO_NOTE
            await message.answer_video_note(FSInputFile(output_path), disable_notification=True)
            os.remove(output_path)
            logger.info(f"User {message.from_user.id} converted video to video note")
        else:
            await message.answer("❌ Error converting video", disable_notification=True)
        
        if os.path.exists(input_path):
            os.remove(input_path)
        
        try:
            await status.delete()
        except:
            pass

        stop.set()
        if pulse_task:
            try:
                await pulse_task
            except Exception:
                pass
            
    except Exception as e:
        logger.exception("Error processing video")
        if isinstance(e, TelegramBadRequest) and "file is too big" in str(e).lower():
            await message.answer(_t(user_lang, "too_big"), disable_notification=True)
        else:
            await message.answer(_t(user_lang, "generic_error"), disable_notification=True)
        try:
            if status:
                await status.delete()
        except Exception:
            pass

        stop.set()
        if pulse_task:
            try:
                await pulse_task
            except Exception:
                pass