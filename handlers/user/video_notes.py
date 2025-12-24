# -*- coding: utf-8 -*-
import os
import asyncio
import logging
import uuid
import shutil
from core.tg_safe import safe_reply
import subprocess
from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.exceptions import TelegramBadRequest
from aiogram.enums import ChatAction
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiohttp.client_exceptions import ClientResponseError
from core.config import config
from services.database.repo import is_user_banned, increment_request_count, upsert_cached_media, log_user_request
from services.platforms.TelegramDownloader.workflow import fix_local_path

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


async def _get_video_duration(ffprobe_path: str, video_path: str) -> float | None:
    """Get video duration in seconds using ffprobe."""
    args = [
        ffprobe_path,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1:nokey=1",
        video_path,
    ]
    try:
        completed = await asyncio.to_thread(
            subprocess.run,
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if completed.returncode == 0:
            duration_str = (completed.stdout or b"").decode("utf-8", errors="ignore").strip()
            return float(duration_str)
    except Exception:
        pass
    return None


async def _download_video_to_path(bot: Bot, file_id: str, destination_path: str) -> None:
    file = await bot.get_file(file_id)
    download_path = file.file_path
    if config.USE_LOCAL_SERVER:
        # Local Bot API may return an absolute container path; aiogram expects a relative path.
        download_path = fix_local_path(download_path, bot.token)
    await bot.download_file(download_path, destination_path)


async def _optimize_video_size(
    ffmpeg_path: str,
    input_path: str,
    output_path: str,
    max_size_mb: float = 49.0,
    vf: str = "crop=min(iw\\,ih):min(iw\\,ih),scale=640:640",
) -> bool:
    """
    Encode video and if it exceeds max_size_mb, re-encode with lower bitrate.
    Returns True on success, False on failure.
    """
    max_size_bytes = max_size_mb * 1024 * 1024
    
    # First pass: encode with default settings
    args = [
        ffmpeg_path,
        "-y",
        "-hide_banner",
        "-loglevel", "error",
        "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "26",
        "-c:a", "aac",
        "-b:a", "64k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-f", "mp4",
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
        logger.error(f"FFmpeg encoding failed: {err}")
        return False
    
    if not os.path.exists(output_path):
        logger.error(f"Output file not created: {output_path}")
        return False
    
    file_size = os.path.getsize(output_path)
    
    # If file is within limit, we're done
    if file_size <= max_size_bytes:
        logger.info(f"Video size {file_size / 1024 / 1024:.1f} MB is within limit")
        return True
    
    logger.info(f"Video size {file_size / 1024 / 1024:.1f} MB exceeds limit; re-encoding with lower bitrate...")
    
    # Get video duration to calculate target bitrate
    ffprobe_path = _find_ffprobe()
    
    duration = await _get_video_duration(ffprobe_path, input_path)
    if not duration or duration <= 0:
        logger.warning("Could not determine video duration; using file size heuristic")
        # Fallback: reduce CRF by 3-4 points (lower quality)
        target_crf = 30
    else:
        # Calculate target bitrate: reserve 64k for audio + 50k margin
        audio_bitrate = 64
        margin = 50
        available_bitrate = (max_size_bytes * 8 / 1000) / duration - audio_bitrate - margin
        available_bitrate = max(500, available_bitrate)  # At least 500 kbps
        
        logger.info(f"Video duration: {duration:.1f}s, target bitrate: {available_bitrate:.0f} kbps")
        
        # Use -b:v for constant bitrate instead of CRF
        args = [
            ffmpeg_path,
            "-y",
            "-hide_banner",
            "-loglevel", "error",
            "-i", input_path,
            "-vf", vf,
            "-c:v", "libx264",
            "-preset", "fast",
            "-b:v", f"{available_bitrate:.0f}k",
            "-maxrate", f"{available_bitrate * 1.2:.0f}k",
            "-bufsize", f"{available_bitrate * 2:.0f}k",
            "-c:a", "aac",
            "-b:a", "64k",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-f", "mp4",
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
            logger.error(f"FFmpeg re-encoding failed: {err}")
            return False
        
        new_size = os.path.getsize(output_path)
        logger.info(f"Re-encoded video size: {new_size / 1024 / 1024:.1f} MB")
        return True
    
    return False

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
            await safe_reply(message, "You are banned from using this bot.", disable_notification=True)
            return
        
        await increment_request_count(user.id)
        
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ Выход / Exit")]],
            resize_keyboard=True
        )
        await safe_reply(
            message,
            "🎥 <b>Video Note Mode</b>\n\nSend me any video and I'll convert it to a video note (square 640x640).\n\n"
            "Press ❌ Exit button to leave this mode.",
            reply_markup=kb,
            disable_notification=True,
            parse_mode="HTML",
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
        await safe_reply(
            message,
            "Video note mode disabled.",
            reply_markup=ReplyKeyboardRemove(),
            disable_notification=True,
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
        status = await safe_reply(message, "⏳", disable_notification=True)

        def _get_action():
            return current_action

        pulse_task = asyncio.create_task(_pulse_action(message, _get_action, stop))

        # Bots can't download very large user-uploaded files via getFile (Telegram-side limit).
        try:
            if message.video and message.video.file_size and message.video.file_size > 20 * 1024 * 1024:
                await safe_reply(message, _t(user_lang, "too_big"), disable_notification=True)
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
        cache_key = None
        try:
            # Use file_unique_id to avoid token-specific file_id volatility.
            cache_key = f"tg:video_note:{message.video.file_unique_id}"
        except Exception:
            cache_key = f"tg:video_note:{file_id}"
        
        temp_dir = "tempfiles"
        os.makedirs(temp_dir, exist_ok=True)
        
        input_path = os.path.join(temp_dir, f"vid_in_{uuid.uuid4()}.mp4")
        output_path = os.path.join(temp_dir, f"vid_out_{uuid.uuid4()}.mp4")
        
        try:
            await _download_video_to_path(message.bot, file_id, input_path)
        except ClientResponseError as e:
            # Some Local Bot API deployments are started with --local and don't serve files via /file,
            # which results in 404s. In that case, fall back to the public Bot API for downloads.
            if config.USE_LOCAL_SERVER and e.status == 404:
                logger.warning("Local Bot API /file returned 404; falling back to public Bot API for download")
                public_bot = Bot(
                    token=message.bot.token,
                    session=AiohttpSession(),
                    default=DefaultBotProperties(parse_mode=None),
                )
                try:
                    await _download_video_to_path(public_bot, file_id, input_path)
                finally:
                    try:
                        await public_bot.session.close()
                    except Exception:
                        pass
            else:
                raise
        except Exception:
            raise

        # Stage: converting into video note
        current_action = ChatAction.RECORD_VIDEO_NOTE
        
        # FFmpeg: Crop to square (min side), scale 640x640, format mp4
        ffmpeg_path = _find_ffmpeg()
        # Ensure directory of ffmpeg is in PATH (avoids WSL shims on Windows)
        try:
            if ffmpeg_path and os.path.isfile(ffmpeg_path):
                ffdir = os.path.dirname(ffmpeg_path)
                os.environ["PATH"] = ffdir + os.pathsep + os.environ.get("PATH", "")
        except Exception:
            pass

        vf = "crop=min(iw\\,ih):min(iw\\,ih),scale=640:640"
        
        # Optimize video size: encode and re-encode if needed to fit in 49 MB
        ok = await _optimize_video_size(
            ffmpeg_path=ffmpeg_path,
            input_path=input_path,
            output_path=output_path,
            max_size_mb=49.0,
            vf=vf,
        )
        if not ok:
            raise Exception("Failed to encode video")
        
        if os.path.exists(output_path):
            # Stage: uploading video note to Telegram
            current_action = ChatAction.UPLOAD_VIDEO_NOTE
            try:
                sent = await message.reply_video_note(FSInputFile(output_path), disable_notification=True)
            except Exception:
                sent = await message.answer_video_note(FSInputFile(output_path), disable_notification=True)
            os.remove(output_path)
            logger.info(f"User {message.from_user.id} converted video to video note")

            # Cache + history
            try:
                if sent and getattr(sent, "video_note", None) and cache_key:
                    cache = await upsert_cached_media(
                        message.from_user.id,
                        cache_key,
                        sent.video_note.file_id,
                        "video_note",
                        title="Video note",
                    )
                    await log_user_request(
                        message.from_user.id,
                        kind="videomessage",
                        input_text="/videomessage",
                        url=cache_key,
                        media_type="video_note",
                        title="Video note",
                        cache_hit=False,
                        cache_id=cache.id,
                    )
            except Exception:
                pass
        else:
            await safe_reply(message, "❌ Error converting video", disable_notification=True)
        
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

def _find_ffmpeg() -> str:
    # Prefer bundled Windows binary if present
    try:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        installs_dir = os.path.join(base_dir, "core", "installs")
        win_ffmpeg = os.path.join(installs_dir, "ffmpeg.exe")
        if os.path.exists(win_ffmpeg):
            return win_ffmpeg
    except Exception:
        pass
    # Linux default path inside Docker
    if os.path.exists("/usr/bin/ffmpeg"):
        return "/usr/bin/ffmpeg"
    # System PATH
    found = shutil.which("ffmpeg")
    return found or "ffmpeg"

def _find_ffprobe() -> str:
    try:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        installs_dir = os.path.join(base_dir, "core", "installs")
        win_ffprobe = os.path.join(installs_dir, "ffprobe.exe")
        if os.path.exists(win_ffprobe):
            return win_ffprobe
    except Exception:
        pass
    if os.path.exists("/usr/bin/ffprobe"):
        return "/usr/bin/ffprobe"
    found = shutil.which("ffprobe")
    return found or "ffprobe"
            
    except Exception as e:
        logger.exception("Error processing video")
        if isinstance(e, TelegramBadRequest) and "file is too big" in str(e).lower():
            await safe_reply(message, _t(user_lang, "too_big"), disable_notification=True, parse_mode=None)
        else:
            # Avoid HTML parsing errors from angle brackets in exception texts (bot default parse_mode is HTML).
            await safe_reply(message, _t(user_lang, "generic_error"), disable_notification=True, parse_mode=None)
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