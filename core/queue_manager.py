import asyncio
from collections import deque
import settings

class QueueManager:
    def __init__(self):
        # {user_id: Semaphore}
        self.user_locks = {}
        # {user_id: int} - счетчик активных задач
        self.active_tasks = {}
        
        # Глобальный лимит (если включен)
        self.global_sem = asyncio.Semaphore(settings.GLOBAL_MAX_CONCURRENT)
        
        # Режим лимитов: 'on', 'user', 'off'
        self.limit_mode = 'on' 

    def set_mode(self, mode: str):
        self.limit_mode = mode

    async def process_task(self, user_id: int, coroutine_func, *args, **kwargs):
        """
        Добавляет задачу в очередь пользователя.
        Выполняет её, когда освободится слот (макс 3).
        """
        # 1. Инициализация семафора юзера (Лимит 3)
        if user_id not in self.user_locks:
            self.user_locks[user_id] = asyncio.Semaphore(settings.USER_MAX_CONCURRENT)
            self.active_tasks[user_id] = 0

        # Увеличиваем счетчик активных (для статистики)
        self.active_tasks[user_id] += 1
        
        # 2. Ждем слот пользователя
        async with self.user_locks[user_id]:
            try:
                # 3. Проверка глобальных лимитов
                is_admin = str(user_id) == str(settings.ADMIN_ID)
                
                # 'on' - лимит для всех
                if self.limit_mode == 'on':
                    async with self.global_sem:
                        return await coroutine_func(*args, **kwargs)
                
                # 'user' - лимит для всех, кроме админа
                elif self.limit_mode == 'user':
                    if is_admin:
                        return await coroutine_func(*args, **kwargs)
                    else:
                        async with self.global_sem:
                            return await coroutine_func(*args, **kwargs)
                
                # 'off' - глобального лимита нет (только лимит на юзера)
                else:
                    return await coroutine_func(*args, **kwargs)
                    
            finally:
                self.active_tasks[user_id] -= 1
                if self.active_tasks[user_id] <= 0:
                    del self.active_tasks[user_id]
                    # Не удаляем семафор сразу, чтобы избежать гонки, 
                    # но можно чистить user_locks периодически

# Глобальный инстанс
queue_manager = QueueManager()