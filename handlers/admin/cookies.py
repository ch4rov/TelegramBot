# -*- coding: utf-8 -*-
import logging
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from handlers.admin.filters import AdminFilter
from services.database.repo import save_global_cookie, increment_request_count

logger = logging.getLogger(__name__)
router = Router()
router.message.filter(AdminFilter())

class GlobalCookieState(StatesGroup):
    waiting_for_service = State()
    waiting_for_file = State()

SERVICES = {
    "youtube": "YouTube",
    "tiktok": "TikTok",
    "vk": "VK"
}

@router.message(Command("sharecookies"))
async def cmd_sharecookies(message: types.Message, state: FSMContext):
    """Admin: Upload global cookies for platform"""
    try:
        kb = InlineKeyboardBuilder()
        for code, name in SERVICES.items():
            kb.button(text=name, callback_data=f"adm_cook:{code}")
        kb.button(text="Cancel", callback_data="adm_cook:cancel")
        kb.adjust(2)
        
        await message.answer("Global Cookies Upload\nSelect platform:", reply_markup=kb.as_markup(), disable_notification=True)
        await state.set_state(GlobalCookieState.waiting_for_service)
        logger.info(f"Admin {message.from_user.id} started /sharecookies")
    except Exception as e:
        logger.error(f"Error in /sharecookies: {e}")

@router.callback_query(GlobalCookieState.waiting_for_service, F.data.startswith("adm_cook:"))
async def cb_service_select(callback: types.CallbackQuery, state: FSMContext):
    """Select service for global cookies"""
    try:
        service = callback.data.split(":")[1]
        
        if service == "cancel":
            await state.clear()
            try:
                await callback.message.delete()
            except:
                pass
            return

        await state.update_data(service=service)
        await callback.message.edit_text(
            f"Send Netscape cookie file for {SERVICES[service]}.\n\n"
            "This will replace existing global cookies for this service."
        )
        await state.set_state(GlobalCookieState.waiting_for_file)
    except Exception as e:
        logger.error(f"Error in cb_service_select: {e}")

@router.message(GlobalCookieState.waiting_for_file, F.document)
async def handle_cookie_file(message: types.Message, state: FSMContext):
    """Handle admin cookie file upload"""
    try:
        data = await state.get_data()
        service = data.get('service', 'unknown')
        
        # Download file
        file_obj = await message.bot.get_file(message.document.file_id)
        file_content = await message.bot.download_file(file_obj.file_path)
        content_str = file_content.read().decode('utf-8', errors='ignore')

        # Basic validation
        if "Netscape" not in content_str or len(content_str) < 50:
            await message.answer("File does not look like Netscape cookies. Try again.", disable_notification=True)
            logger.warning(f"Admin {message.from_user.id} tried to upload invalid cookies for {service}")
            return

        await save_global_cookie(service, content_str)
        
        await message.answer(f"Global Cookies for {SERVICES[service]} updated!", disable_notification=True)
        await increment_request_count(message.from_user.id)
        logger.info(f"Admin {message.from_user.id} uploaded global cookies for {service}")
        await state.clear()
    except Exception as e:
        logger.error(f"Error handling cookie file: {e}")
        await message.answer("Error saving cookies", disable_notification=True)