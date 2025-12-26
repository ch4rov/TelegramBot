# -*- coding: utf-8 -*-
"""Tavern channel daily renaming task."""
import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot
from services.tavern_declension import get_tavern_name

logger = logging.getLogger(__name__)

# For channels: Telegram Bot API expects negative IDs in the format -100<channel_id>
TAVERN_CHANNEL_ID = -1001767700689  # From user: 1767700689 -> -100 + 1767700689


async def schedule_tavern_renamer(bot: Bot):
    """
    Background task that renames the tavern channel daily at 5 AM.
    Runs indefinitely.
    """
    logger.info("[Tavern] Renaming scheduler started")
    
    while True:
        try:
            now = datetime.now()
            
            # Calculate next 5 AM
            next_5am = now.replace(hour=5, minute=0, second=0, microsecond=0)
            if now >= next_5am:
                # If we're past 5 AM today, schedule for tomorrow
                next_5am += timedelta(days=1)
            
            wait_seconds = (next_5am - now).total_seconds()
            logger.info(f"[Tavern] Next rename scheduled for {next_5am.strftime('%Y-%m-%d %H:%M:%S')} (in {wait_seconds:.0f}s)")
            
            # Wait until 5 AM
            await asyncio.sleep(wait_seconds)
            
            # Perform the rename
            try:
                new_name = get_tavern_name()
                await bot.set_chat_title(
                    chat_id=TAVERN_CHANNEL_ID,
                    title=new_name
                )
                logger.info(f"[Tavern] Channel renamed to: {new_name}")
                
                # Try to delete the system message about title change
                await asyncio.sleep(0.5)
                try:
                    # Post a temporary message to find the right position
                    temp_msg = await bot.send_message(
                        chat_id=TAVERN_CHANNEL_ID,
                        text="🔄",
                        disable_notification=True
                    )
                    temp_msg_id = temp_msg.message_id
                    
                    # Delete our temporary message
                    await asyncio.sleep(0.2)
                    await bot.delete_message(chat_id=TAVERN_CHANNEL_ID, message_id=temp_msg_id)
                    
                    # Try to delete the system message (should be near our temp message)
                    from aiogram.errors import TelegramBadRequest
                    for msg_id in range(temp_msg_id - 1, max(temp_msg_id - 5, 0), -1):
                        try:
                            await bot.delete_message(chat_id=TAVERN_CHANNEL_ID, message_id=msg_id)
                            logger.info(f"[Tavern] Deleted system message ID {msg_id}")
                            break
                        except TelegramBadRequest:
                            pass
                        except Exception:
                            pass
                except Exception as e:
                    logger.debug(f"[Tavern] Could not clean up system message: {e}")
                    
            except Exception as e:
                logger.error(f"[Tavern] Failed to rename channel: {e}")
                # Retry after 1 minute if it fails
                await asyncio.sleep(60)
        
        except asyncio.CancelledError:
            logger.info("[Tavern] Renaming scheduler stopped")
            break
        except Exception as e:
            logger.error(f"[Tavern] Unexpected error in scheduler: {e}")
            # Wait 1 minute before retrying
            await asyncio.sleep(60)
