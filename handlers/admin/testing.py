from aiogram import Router, F
from aiogram.types import Message
import asyncio
import time
# Используем новый путь импорта
from services.platforms.common_downloader import CommonDownloader
from services.database_service import clear_file_cache
# Импортируем функцию-алиас из новой системы
from core.logger_system import send_log
import settings

admin_router = Router()

CHECK_URLS = [
    ("YouTube Video", "https://youtu.be/zUWZJPC5V9M"),
    ("YouTube Music", "https://music.youtube.com/watch?v=BvwG48W0tcc"),
    ("Instagram Reel", "https://www.instagram.com/reel/DQyynEMinzX"),
    ("TikTok Video", "https://www.tiktok.com/@ch4rov/video/7552260996673375544"),
    ("TikTok Audio", "https://www.tiktok.com/music/tiktok-audio-example-7000000000000000000"),
    ("Twitch Clip", "https://www.twitch.tv/ch4rov/clip/RelentlessShyArugulaAsianGlow-t5GUjoNYhrSOp45Q"),
    ("VK Clip", "https://vkvideo.ru/clip-226699225_456242206"),
    ("VK Video", "https://vk.com/video-180667440_456239018"),
    ("SoundCloud", "https://soundcloud.com/ocqbbed9ek3i/yaryy-tolko-ne-begi"),
    ("Spotify", "https://open.spotify.com/track/6DIFo72cCtzy7nB2Zxyjx9?si=bc61bf01ee854ea9"),
]

# Проверьте, что ваш ID есть в settings.ADMIN_IDS, иначе этот хендлер не сработает!
@admin_router.message(F.command == "check")
async def cmd_check(message: Message):
    # Дополнительная проверка на админа, если фильтр не стоит на роутере
    if message.from_user.id not in settings.ADMIN_IDS:
        return

    await clear_file_cache()
    
    status_msg = await message.answer("🚀 <b>Starting System Health Check...</b>\n<i>Cache cleared.</i>", parse_mode="HTML")
    
    report = ["🛡 <b>System Health Report</b>", ""]
    success_count = 0
    
    start_time = time.time()

    for platform_name, url in CHECK_URLS:
        if not url:
            report.append(f"❓ <b>{platform_name}</b>: Skipped")
            continue

        try:
            await status_msg.edit_text(f"⏳ Checking <b>{platform_name}</b>...", parse_mode="HTML")
            
            # Скачиваем, но создаем временный класс-наследник для тестов
            # (или используем логику CommonDownloader, но она абстрактная. 
            # Нам нужно использовать platform_manager или создать конкретную реализацию)
            
            # ВАЖНО: CommonDownloader - абстрактный класс. Его нельзя вызвать напрямую.
            # Лучше использовать download_content из platform_manager
            from services.platforms.platform_manager import download_content
            
            # Эмулируем вызов (download_content сам определит платформу)
            files, path, error, meta = await download_content(url)

            if files and not error:
                report.append(f"✅ <b>{platform_name}</b>: OK")
                success_count += 1
                try:
                    import shutil
                    shutil.rmtree(path, ignore_errors=True)
                except: pass
            else:
                err_text = error or "No files"
                report.append(f"❌ <b>{platform_name}</b>: Fail ({err_text})")
                
        except Exception as e:
            report.append(f"❌ <b>{platform_name}</b>: Error ({str(e)[:40]})")

    total_time = round(time.time() - start_time, 2)
    report.append(f"\n⏱ Total Time: {total_time}s")
    report.append(f"📊 Result: {success_count}/{len(CHECK_URLS)} passed")

    final_text = "\n".join(report)
    await status_msg.edit_text(final_text, parse_mode="HTML")
    
    await send_log("ADMIN", "Health Check finished", admin=message.from_user)