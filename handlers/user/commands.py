# -*- coding: utf-8 -*-
import logging
from aiogram import types
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from handlers.user.router import user_router
from services.database.repo import is_user_banned, increment_request_count, set_lastfm_username, get_lastfm_username, set_user_language, get_user_language

logger = logging.getLogger(__name__)

@user_router.message(Command("login"))
async def cmd_login(message: types.Message, command: CommandObject):
    """Login to Last.fm: /login USERNAME"""
    try:
        user = message.from_user
        is_banned = await is_user_banned(user.id)
        
        if is_banned:
            await message.answer("You are banned from using this bot.", disable_notification=True)
            return
        
        # Получаем язык пользователя
        from services.database.repo import get_user_language
        from services.localization import i18n
        lang = await get_user_language(user.id)
        
        if not command.args:
            # Show current Last.fm account if linked
            lastfm_user = await get_lastfm_username(user.id)
            if lastfm_user:
                text = i18n.get("login_current", lang, username=lastfm_user)
                await message.answer(text, disable_notification=True)
            else:
                text = i18n.get("login_usage", lang)
                await message.answer(text, disable_notification=True)
            return
        
        lastfm_username = command.args.strip()
        await set_lastfm_username(user.id, lastfm_username)
        
        text = i18n.get("login_success", lang, username=lastfm_username)
        await message.answer(text, disable_notification=True)
        logger.info(f"User {user.id} linked Last.fm account: {lastfm_username}")
        await increment_request_count(user.id)
    except Exception as e:
        logger.error(f"Error in /login: {e}")
        await message.answer("Error processing command", disable_notification=True)

@user_router.message(Command("addcookies"))
async def cmd_addcookies(message: types.Message):
    """Add cookies command"""
    try:
        user = message.from_user
        is_banned = await is_user_banned(user.id)
        
        if is_banned:
            await message.answer("You are banned from using this bot.", disable_notification=True)
            return
        
        text = (
            "Cookies allow the bot to access restricted content.\n\n"
            "This feature is under construction.\n"
            "Supported platforms: YouTube, TikTok, VK, Instagram"
        )
        await message.answer(text, disable_notification=True)
        logger.info(f"User {user.id} used /addcookies")
        await increment_request_count(user.id)
    except Exception as e:
        logger.error(f"Error in /addcookies: {e}")

@user_router.message(Command("language"))
async def cmd_language(message: types.Message):
    """Toggle language: /language"""
    try:
        user = message.from_user
        is_banned = await is_user_banned(user.id)
        
        if is_banned:
            await message.answer("You are banned from using this bot.", disable_notification=True)
            return
        
        from services.localization import i18n
        
        # Get current language
        current_lang = await get_user_language(user.id)
        
        # Toggle language
        new_lang = "ru" if current_lang == "en" else "en"
        await set_user_language(user.id, new_lang)
        
        # Prepare confirmation message
        if new_lang == "en":
            text = "✅ Language set to English"
        else:
            text = "✅ Язык установлен на русский"
        
        await message.answer(text, disable_notification=True)
        logger.info(f"User {user.id} switched language from {current_lang} to {new_lang}")
        await increment_request_count(user.id)
    except Exception as e:
        logger.error(f"Error in /language: {e}")
        await message.answer("Error processing command", disable_notification=True)