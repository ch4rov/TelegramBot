import asyncio
from collections import defaultdict

class QueueManager:
    def __init__(self):
        # Словарь локов: для каждого user_id свой замок
        self._locks = defaultdict(asyncio.Lock)

    async def run_serial(self, user_id, coro_func):
        """Run a coroutine sequentially per-user, without swallowing exceptions."""
        lock = self._locks[user_id]
        async with lock:
            return await coro_func()

    async def process_task(self, user_id, task_func):
        """
        Гарантирует, что для одного юзера задачи выполняются по очереди.
        Если юзер отправил 5 ссылок, они обработаются одна за другой.
        """
        lock = self._locks[user_id]
        
        # Если лок занят, бот будет ждать здесь
        async with lock:
            try:
                # Выполняем задачу (скачивание)
                return await task_func()
            except Exception as e:
                print(f"[QUEUE] Error processing task for {user_id}: {e}")
                # Возвращаем пустые значения, чтобы бот мог отправить сообщение об ошибке
                return None, None, str(e), None

# Глобальный экземпляр
queue_manager = QueueManager()