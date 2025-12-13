import time
from aiogram import BaseMiddleware
from aiogram.types import Message

class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, limit: float = 0.7):
        self.limit = limit
        self.user_timestamps = {}

    async def __call__(self, handler, event, data):
        if not isinstance(event, Message):
            return await handler(event, data)
            
        user_id = event.from_user.id
        now = time.time()
        
        if user_id in self.user_timestamps:
            if now - self.user_timestamps[user_id] < self.limit:
                return
        
        self.user_timestamps[user_id] = now
        return await handler(event, data)