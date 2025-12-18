# -*- coding: utf-8 -*-
import logging
import os
import asyncio
import subprocess
from aiogram.types import FSInputFile
from services.database.repo import get_system_value, set_system_value
import settings
from core.loader import bot
from core.config import config

logger = logging.getLogger(__name__)

async def get_placeholder(placeholder_type: str):
    """Get placeholder file_id from database"""
    key = f"placeholder_{placeholder_type}"
    file_id = await get_system_value(key)
    
    if file_id:
        logger.info(f"Got placeholder for {placeholder_type}")
        return file_id
    
    logger.warning(f"Placeholder {placeholder_type} not found")
    return None

async def ensure_placeholders():
    """Ensure all placeholders exist"""
    logger.info("Checking placeholders...")

    admin_id = config.ADMIN_IDS[0] if getattr(config, "ADMIN_IDS", None) else None
    if not admin_id:
        logger.warning("Cannot ensure placeholders: ADMIN_IDS is empty")
        return

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    installs_dir = os.path.join(repo_root, "core", "installs")
    ffmpeg = os.path.join(installs_dir, "ffmpeg.exe") if os.path.exists(os.path.join(installs_dir, "ffmpeg.exe")) else "ffmpeg"

    ph_dir = os.path.join(settings.TEMP_DIR, "_inline_placeholders")
    os.makedirs(ph_dir, exist_ok=True)

    async def run_ffmpeg(args: list[str]) -> bool:
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=False,
            )
            if completed.returncode != 0:
                err = (completed.stderr or b"").decode("utf-8", errors="ignore").strip()
                logger.warning(f"FFmpeg placeholder generation failed: {err}")
            return completed.returncode == 0
        except Exception as e:
            logger.warning(f"FFmpeg placeholder generation error: {e}")
            return False

    # --- Video placeholder ---
    vid_id = await get_system_value("placeholder_video")
    if not vid_id:
        video_path = os.path.join(ph_dir, "placeholder_video.mp4")
        args = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=640x360:d=1",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=stereo",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "64k",
            "-movflags",
            "+faststart",
            video_path,
        ]
        ok = await run_ffmpeg(args)
        if ok and os.path.exists(video_path):
            try:
                msg = await bot.send_video(admin_id, FSInputFile(video_path), caption="inline video placeholder")
                await set_system_value("placeholder_video", msg.video.file_id)
                try:
                    await bot.delete_message(admin_id, msg.message_id)
                except Exception:
                    pass
                logger.info("Video placeholder created")
            except Exception as e:
                logger.warning(f"Failed to upload video placeholder: {e}")
        else:
            logger.warning("Video placeholder not created")
    else:
        logger.info("Video placeholder OK")

    # --- Audio placeholder ---
    aud_id = await get_system_value("placeholder_audio")
    if not aud_id:
        audio_path = os.path.join(ph_dir, "placeholder_audio.mp3")
        args = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=stereo",
            "-t",
            "1",
            "-c:a",
            "libmp3lame",
            "-q:a",
            "6",
            audio_path,
        ]
        ok = await run_ffmpeg(args)
        if ok and os.path.exists(audio_path):
            try:
                msg = await bot.send_audio(admin_id, FSInputFile(audio_path), caption="inline audio placeholder")
                await set_system_value("placeholder_audio", msg.audio.file_id)
                try:
                    await bot.delete_message(admin_id, msg.message_id)
                except Exception:
                    pass
                logger.info("Audio placeholder created")
            except Exception as e:
                logger.warning(f"Failed to upload audio placeholder: {e}")
        else:
            logger.warning("Audio placeholder not created")
    else:
        logger.info("Audio placeholder OK")

    # --- Localized audio placeholders (for inline result list title) ---
    # Telegram clients display audio title/performer for cached-audio results; cached-audio itself has no `title` field.
    # So we upload two cached audios with different metadata.
    try:
        audio_path = os.path.join(ph_dir, "placeholder_audio.mp3")
        if os.path.exists(audio_path):
            aud_en = await get_system_value("placeholder_audio_en")
            if not aud_en:
                try:
                    msg = await bot.send_audio(
                        admin_id,
                        FSInputFile(audio_path),
                        caption="inline audio placeholder (en)",
                        title="Send as audio",
                    )
                    await set_system_value("placeholder_audio_en", msg.audio.file_id)
                    try:
                        await bot.delete_message(admin_id, msg.message_id)
                    except Exception:
                        pass
                    logger.info("Audio placeholder EN created")
                except Exception as e:
                    logger.warning(f"Failed to upload audio placeholder EN: {e}")
            else:
                logger.info("Audio placeholder EN OK")

            aud_ru = await get_system_value("placeholder_audio_ru")
            if not aud_ru:
                try:
                    msg = await bot.send_audio(
                        admin_id,
                        FSInputFile(audio_path),
                        caption="inline audio placeholder (ru)",
                        title="Отправить аудио",
                    )
                    await set_system_value("placeholder_audio_ru", msg.audio.file_id)
                    try:
                        await bot.delete_message(admin_id, msg.message_id)
                    except Exception:
                        pass
                    logger.info("Audio placeholder RU created")
                except Exception as e:
                    logger.warning(f"Failed to upload audio placeholder RU: {e}")
            else:
                logger.info("Audio placeholder RU OK")
        else:
            logger.warning("Localized audio placeholders skipped: placeholder file missing")
    except Exception as e:
        logger.warning(f"Localized audio placeholders error: {e}")