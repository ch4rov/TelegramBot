import asyncio
from aiogram import BaseMiddleware, types
from services.database_service import log_message_to_db

class GroupLoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        result = await handler(event, data)

        if isinstance(event, types.Message):
            message = event
        elif isinstance(event, types.Update) and event.message:
            message = event.message
        else:
            return result

        if message.chat.type not in {'group', 'supergroup'}:
            return result

        user = message.from_user
        if not user:
            return result

        text_content = message.text or message.caption or "[Media]"
        username = user.username or user.first_name or "Unknown"
        
        asyncio.create_task(log_message_to_db(
            user_id=user.id,
            chat_id=message.chat.id,
            message_id=message.message_id,
            username=username,
            text=text_content,
            msg_type="GROUP_MSG"
        ))

        return result