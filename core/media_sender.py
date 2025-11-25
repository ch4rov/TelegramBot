"""Unified media sending module - handles video, audio, photo"""
import os
from aiogram.types import FSInputFile
from aiogram import Bot


class MediaSender:
    """Unified media sending for all media types"""

    def __init__(self, bot: Bot):
        self.bot = bot

    async def send_media(self, chat_id: int, file_path: str, 
                        caption: str = None, thumb_file: str = None) -> object:
        """
        Universal media send - detects type and sends appropriate media.
        Returns message object or None if failed.
        """
        if not os.path.exists(file_path):
            return None

        ext = os.path.splitext(file_path)[1].lower()

        if ext in ['.mp4', '.mov', '.mkv', '.webm', '.ts']:
            return await self._send_video(chat_id, file_path, caption, thumb_file)
        elif ext in ['.mp3', '.m4a', '.ogg', '.wav']:
            return await self._send_audio(chat_id, file_path, caption, thumb_file)
        elif ext in ['.jpg', '.jpeg', '.png', '.webp']:
            return await self._send_photo(chat_id, file_path, caption)
        
        return None

    async def _send_video(self, chat_id: int, file_path: str,
                         caption: str = None, thumb_file: str = None) -> object:
        """Send video file"""
        try:
            msg = await self.bot.send_video(
                chat_id=chat_id,
                video=FSInputFile(file_path),
                caption=caption,
                thumbnail=None,  # Let Telegram extract from video (better quality)
                supports_streaming=True,
                parse_mode="HTML" if caption else None,
                disable_notification=True
            )
            return msg
        except Exception as e:
            print(f"❌ Error sending video: {e}")
            return None

    async def _send_audio(self, chat_id: int, file_path: str,
                         caption: str = None, thumb_file: str = None) -> object:
        """Send audio file with metadata"""
        try:
            filename = os.path.basename(file_path)
            performer = "Unknown"
            title = os.path.splitext(filename)[0]
            
            if " - " in title:
                parts = title.split(" - ", 1)
                performer, title = parts[0], parts[1]

            thumbnail_obj = None
            if thumb_file and os.path.exists(thumb_file):
                thumbnail_obj = FSInputFile(thumb_file)

            msg = await self.bot.send_audio(
                chat_id=chat_id,
                audio=FSInputFile(file_path),
                caption=caption,
                thumbnail=thumbnail_obj,
                performer=performer,
                title=title,
                parse_mode="HTML" if caption else None,
                disable_notification=True
            )
            return msg
        except Exception as e:
            print(f"❌ Error sending audio: {e}")
            return None

    async def _send_photo(self, chat_id: int, file_path: str,
                         caption: str = None) -> object:
        """Send photo file"""
        try:
            msg = await self.bot.send_photo(
                chat_id=chat_id,
                photo=FSInputFile(file_path),
                caption=caption,
                parse_mode="HTML" if caption else None,
                disable_notification=True
            )
            return msg
        except Exception as e:
            print(f"❌ Error sending photo: {e}")
            return None

    async def get_file_id(self, msg: object, media_type: str) -> str:
        """Extract file_id from sent message based on media type"""
        if not msg:
            return None
        
        try:
            if media_type == 'video' and msg.video:
                return msg.video.file_id
            elif media_type == 'audio' and msg.audio:
                return msg.audio.file_id
            elif media_type == 'photo' and msg.photo:
                return msg.photo[-1].file_id
        except Exception:
            pass
        
        return None
