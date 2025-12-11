import asyncio
from collections import deque
import settings

class QueueManager:
    def __init__(self):
        # {user_id: Semaphore}
        self.user_locks = {}
        # {user_id: int}
        self.active_tasks = {}
        self.global_sem = asyncio.Semaphore(settings.GLOBAL_MAX_CONCURRENT)
        self.limit_mode = 'on' 

    def set_mode(self, mode: str):
        self.limit_mode = mode

    async def process_task(self, user_id: int, coroutine_func, *args, **kwargs):
        """
        Выполняет задачу с учетом лимитов.
        Гарантирует освобождение слота при ошибках.
        """
        if user_id not in self.user_locks:
            self.user_locks[user_id] = asyncio.Semaphore(settings.USER_MAX_CONCURRENT)
            self.active_tasks[user_id] = 0

        # Увеличиваем счетчик ПЕРЕД ожиданием
        self.active_tasks[user_id] += 1
        
        try:
            # 1. Личный лимит (ждем слот)
            async with self.user_locks[user_id]:
                # 2. Глобальный лимит
                is_admin = str(user_id) == str(settings.ADMIN_ID)
                
                if self.limit_mode == 'on':
                    async with self.global_sem:
                        return await coroutine_func(*args, **kwargs)
                
                elif self.limit_mode == 'user' and not is_admin:
                    async with self.global_sem:
                        return await coroutine_func(*args, **kwargs)
                
                else:
                    return await coroutine_func(*args, **kwargs)
                    
        finally:
            # Всегда уменьшаем счетчик, что бы ни случилось
            if user_id in self.active_tasks:
                self.active_tasks[user_id] -= 1
                if self.active_tasks[user_id] <= 0:
                    # Чистим мусор, если задач нет
                    self.active_tasks.pop(user_id, None)
                    # Семафор не удаляем, чтобы не сломать ожидающие задачи

queue_manager = QueueManager()