# -*- coding: utf-8 -*-
from aiogram import Router, types
from aiogram.filters import Command
import asyncio
import time
from handlers.admin.filters import AdminFilter
from services.platforms.platform_manager import download_content
import logging

logger = logging.getLogger(__name__)
router = Router()
router.message.filter(AdminFilter())

CHECK_URLS = [
    ("YouTube Video", "https://youtu.be/zUWZJPC5V9M"),
    ("YouTube Music", "https://music.youtube.com/watch?v=BvwG48W0tcc"),
    ("Instagram Reel", "https://www.instagram.com/reel/DQyynEMinzX"),
    ("TikTok Video", "https://www.tiktok.com/@ch4rov/video/7552260996673375544"),
    ("Twitch Clip", "https://www.twitch.tv/ch4rov/clip/RelentlessShyArugulaAsianGlow-t5GUjoNYhrSOp45Q"),
    ("VK Video", "https://vk.com/video-180667440_456239018"),
    ("SoundCloud", "https://soundcloud.com/ocqbbed9ek3i/yaryy-tolko-ne-begi"),
    ("Spotify", "https://open.spotify.com/track/6DIFo72cCtzy7nB2Zxyjx9"),
]

@router.message(Command("check"))
async def cmd_check(message: types.Message):
    """System health check - тестирует все доступные сервисы"""
    try:
        await message.answer("🚀 <b>Starting System Health Check...</b>", parse_mode="HTML", disable_notification=True)
        status_msg = await message.answer("⏳ Initializing...", parse_mode="HTML", disable_notification=True)
        
        report = ["🛡 <b>System Health Report</b>", ""]
        success_count = 0
        start_time = time.time()

        for platform_name, url in CHECK_URLS:
            if not url:
                report.append(f"❓ <b>{platform_name}</b>: Skipped")
                continue

            try:
                await status_msg.edit_text(f"⏳ Checking <b>{platform_name}</b>...", parse_mode="HTML")
                
                files, path, error, meta = await download_content(url)

                if files and not error:
                    report.append(f"✅ <b>{platform_name}</b>: OK")
                    success_count += 1
                    try:
                        import shutil
                        shutil.rmtree(path, ignore_errors=True)
                    except:
                        pass
                else:
                    err_text = error or "No files"
                    report.append(f"❌ <b>{platform_name}</b>: Fail ({err_text[:30]})")
                    
            except Exception as e:
                report.append(f"❌ <b>{platform_name}</b>: Error ({str(e)[:30]})")

        total_time = round(time.time() - start_time, 2)
        report.append(f"\n⏱ Total Time: {total_time}s")
        report.append(f"📊 Result: {success_count}/{len(CHECK_URLS)} passed")

        final_text = "\n".join(report)
        await status_msg.edit_text(final_text, parse_mode="HTML")
        
        logger.info(f"Admin {message.from_user.id} ran health check")
    except Exception as e:
        logger.error(f"Error in /check: {e}")
        await message.answer(f"❌ Error: {e}", disable_notification=True)
