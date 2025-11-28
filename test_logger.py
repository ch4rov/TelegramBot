import asyncio
# Импортируем наш новый логгер
from services.logger.verbose_logger import console

async def test():
    print("\n--- 🚀 ЗАПУСК ТЕСТА ЛОГГЕРА ---\n")
    
    # Проверяем все уровни логирования
    console.info("Это обычное информационное сообщение (INFO).")
    await asyncio.sleep(0.5)
    
    console.debug("Это сообщение для отладки, скрытых деталей (DEBUG).")
    await asyncio.sleep(0.5)
    
    console.warn("Внимание! Это предупреждение (WARN).")
    await asyncio.sleep(0.5)
    
    console.error("О нет! Это сообщение об ошибке (ERROR).")
    await asyncio.sleep(0.5)
    
    console.success("Ура! Операция выполнена успешно (SUCCESS).")
    
    print("\n--- 🏁 КОНЕЦ ТЕСТА ---\n")

if __name__ == "__main__":
    asyncio.run(test())