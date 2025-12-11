import asyncio
from aiogram import types
from aiogram.filters import Command
from .router import admin_router, is_admin
# --- ИСПРАВЛЕННЫЙ ИМПОРТ ---
from core.logger_system import send_log
# ---------------------------

HEALTH_CHECK_URLS = [
    ("YouTube", "https://youtu.be/jNQXAC9IVRw"), 
    ("TikTok", "https://www.tiktok.com/@ch4rov/video/7552260996673375544"), 
    ("SoundCloud", "https://soundcloud.com/yayaheart/prosto-lera-ostav-menya-odnu"), 
]

@admin_router.message(Command("check"))
async def cmd_check(message: types.Message):
    if not is_admin(message.from_user.id): return

    from handlers.user.content import handle_link 

    status_msg = await message.answer("🏥 <b>Checking...</b>", parse_mode="HTML")
    success_count = 0
    
    for name, url in HEALTH_CHECK_URLS:
        try:
            await status_msg.edit_text(f"⏳ Testing: <b>{name}</b>...\nURL: <code>{url}</code>", parse_mode="HTML", disable_web_page_preview=True)
            fake_message = message.model_copy(update={'text': url})
            await handle_link(fake_message)
            success_count += 1
            await asyncio.sleep(3)
        except Exception as e:
            await message.answer(f"❌ Error in {name}: {e}")

    await status_msg.edit_text(f"✅ <b>Done!</b>\nPassed: {success_count}/{len(HEALTH_CHECK_URLS)}", parse_mode="HTML")
    await send_log("ADMIN", "Health Check finished", admin=message.from_user)