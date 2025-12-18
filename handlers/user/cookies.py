# -*- coding: utf-8 -*-
import logging
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from services.localization import LocalizationService
from services.database.repo import save_user_cookie, increment_request_count

logger = logging.getLogger(__name__)
router = Router()

class UserCookieState(StatesGroup):
    selecting_service = State()
    uploading_file = State()

SERVICES = {"youtube": "YouTube", "tiktok": "TikTok", "vk": "VK"}

@router.message(Command("addcookies"))
async def cmd_addcookies(message: types.Message, i18n: LocalizationService, state: FSMContext):
    """Start adding cookies for user"""
    try:
        user = message.from_user
        await increment_request_count(user.id)
        
        text = "Upload Netscape cookies for a platform.\n\nCookies help access restricted content.\n\nSelect platform:"
        
        kb = InlineKeyboardBuilder()
        for code, name in SERVICES.items():
            kb.button(text=name, callback_data=f"usr_cook:{code}")
        kb.button(text="Cancel", callback_data="usr_cook:cancel")
        kb.adjust(2)
        
        await message.answer(text, reply_markup=kb.as_markup(), disable_notification=True)
        await state.set_state(UserCookieState.selecting_service)
        logger.info(f"User {user.id} started adding cookies")
    except Exception as e:
        logger.error(f"Error in cmd_addcookies: {e}")

@router.callback_query(UserCookieState.selecting_service, F.data.startswith("usr_cook:"))
async def cb_select_service(callback: types.CallbackQuery, state: FSMContext):
    """Select service for cookies"""
    try:
        service = callback.data.split(":")[1]
        
        if service == "cancel":
            await state.clear()
            try:
                await callback.message.delete()
            except:
                pass
            logger.info(f"User {callback.from_user.id} cancelled cookie upload")
            return

        await state.update_data(service=service)
        text = f"Upload Netscape cookies file for {SERVICES[service]}."
        await callback.message.edit_text(text, disable_notification=True)
        await state.set_state(UserCookieState.uploading_file)
        logger.info(f"User {callback.from_user.id} selected {service} for cookies")
    except Exception as e:
        logger.error(f"Error in cb_select_service: {e}")

@router.message(UserCookieState.uploading_file, F.document)
async def handle_file_upload(message: types.Message, state: FSMContext):
    """Handle cookie file upload"""
    try:
        data = await state.get_data()
        service = data.get('service', 'unknown')
        user = message.from_user
        
        file = message.document
        
        # Download file
        file_obj = await message.bot.get_file(file.file_id)
        content = (await message.bot.download_file(file_obj.file_path)).read().decode('utf-8', errors='ignore')

        # Basic validation
        if len(content) < 50 or "Netscape" not in content:
            await message.answer("Invalid cookies file format", disable_notification=True)
            logger.warning(f"User {user.id} uploaded invalid cookies file")
            return

        # Save cookies
        await save_user_cookie(user.id, service, content)
        await message.answer(f"Cookies for {SERVICES.get(service, service)} saved!", disable_notification=True)
        await state.clear()
        logger.info(f"User {user.id} uploaded cookies for {service}")
    except Exception as e:
        logger.error(f"Error in handle_file_upload: {e}")
        await message.answer("Error saving cookies", disable_notification=True)