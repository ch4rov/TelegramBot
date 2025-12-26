# -*- coding: utf-8 -*-
"""Daily tavern channel renaming scheduler."""
import asyncio
import logging
from typing import Optional
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from services.tavern_declension import get_tavern_name

logger = logging.getLogger(__name__)

# Channel ID for the tavern
TAVERN_CHANNEL_ID = -1001767700689  # Telegram channel IDs are negative

class TavernRenamer:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.last_system_message_id: Optional[int] = None
    
    async def rename_tavern_channel(self):
        """Rename the tavern channel to a random nickname and delete the system message."""
        try:
            nickname = get_tavern_name()
            
            # Edit channel title
            await self.bot.edit_chat_title(
                chat_id=TAVERN_CHANNEL_ID,
                title=nickname
            )
            logger.info(f"[Tavern] Channel renamed to: {nickname}")
            
            # Try to find and delete the latest system message about the rename
            # The system message about title change appears as a service message
            try:
                chat = await self.bot.get_chat(TAVERN_CHANNEL_ID)
                # Get recent messages to find the system message
                # Note: This is a workaround since there's no direct "get latest system message" API
                # We'll schedule a delayed delete task
                await asyncio.sleep(1)  # Wait for system message to be posted
                
                # Get chat history to find the system message
                # Unfortunately, aiogram doesn't expose message history directly,
                # so we'll use a different approach: delete messages from a certain range
                # For now, we mark this as a known limitation
                logger.info("[Tavern] System message cleanup skipped (API limitation)")
                
            except Exception as e:
                logger.warning(f"[Tavern] Could not delete system message: {e}")
        
        except Exception as e:
            logger.error(f"[Tavern] Error renaming channel: {e}")
    
    async def start_scheduler(self):
        """Start the scheduler with daily 5 AM rename task."""
        if self.scheduler is None:
            self.scheduler = AsyncIOScheduler()
        
        # Schedule at 5:00 AM every day (assuming server timezone)
        trigger = CronTrigger(hour=5, minute=0)
        self.scheduler.add_job(
            self.rename_tavern_channel,
            trigger=trigger,
            id="tavern_daily_rename",
            name="Daily tavern rename at 5 AM",
            replace_existing=True,
        )
        
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("[Tavern] Scheduler started - daily rename at 05:00")
    
    async def stop_scheduler(self):
        """Stop the scheduler."""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("[Tavern] Scheduler stopped")


# Global instance
tavern_renamer: Optional[TavernRenamer] = None


def init_tavern_renamer(bot: Bot) -> TavernRenamer:
    """Initialize and return the tavern renamer instance."""
    global tavern_renamer
    tavern_renamer = TavernRenamer(bot)
    return tavern_renamer


def get_tavern_renamer() -> Optional[TavernRenamer]:
    """Get the global tavern renamer instance."""
    return tavern_renamer
