# -*- coding: utf-8 -*-
import logging
from aiogram import Router, types
from services.database.repo import add_or_update_user, is_user_banned
from core.config import config

logger = logging.getLogger(__name__)

# Main user router
user_router = Router()

async def check_access_and_update(user: types.User, message: types.Message | None = None):
    """Checks if user is allowed to use bot and updates their info"""
    try:
        # Telegram system account (channel post forwarding in linked groups)
        if getattr(user, "id", None) == 777000:
            return False, False, False, "en"

        user_id = user.id
        username = user.username or ""
        full_name = user.full_name or "Unknown"
        language_code = user.language_code or "en"
        
        tag = f"@{username}" if username else ""

        # Update user in database
        db_user = await add_or_update_user(
            user_id=user_id,
            username=username,
            full_name=full_name,
            tag=tag,
            language=language_code
        )

        # Check if banned
        if db_user.is_banned:
            if message:
                await message.reply(
                    f"Access Denied\nReason: {db_user.ban_reason}",
                    disable_notification=True
                )
            logger.warning(f"Banned user {user_id} tried to use bot")
            return False, False, True, db_user.language

        # Check maintenance mode
        if config.USE_LOCAL_SERVER and user_id not in config.ADMIN_IDS:
            if message:
                await message.reply("Maintenance mode active", disable_notification=True)
            return False, False, False, db_user.language

        return True, False, False, db_user.language
    
    except Exception as e:
        logger.error(f"Error in check_access_and_update: {e}")
        if message:
            await message.reply("Error processing request", disable_notification=True)
        return False, False, False, "en"