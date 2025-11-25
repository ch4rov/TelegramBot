import subprocess
import sys
import time

# Имя файла твоего бота
BOT_SCRIPT = "main.py"
# Код выхода для специальной перезагрузки
RESTART_EXIT_CODE = 65

def start_bot():
    interpreter = sys.executable  # Используем тот же Python (из venv)
    print("🔋 [RUNNER] Запуск планировщика...")

    while True:
        try:
            print(f"\n🚀 [RUNNER] Запуск {BOT_SCRIPT}...")
            # Запускаем бота
            process = subprocess.Popen([interpreter, BOT_SCRIPT])
            process.wait()  # Ждем завершения

            # Проверяем, как завершился бот
            if process.returncode == RESTART_EXIT_CODE:
                print("♻️ [RUNNER] Команда перезагрузки. Рестарт через 1 сек...")
                time.sleep(1)
            elif process.returncode == 0:
                print("🛑 [RUNNER] Бот остановлен вручную (код 0). Выход.")
                break
            else:
                print(f"⚠️ [RUNNER] Бот упал (код {process.returncode}). Перезапуск через 5 сек...")
                time.sleep(5)

        except KeyboardInterrupt:
            print("\n🛑 [RUNNER] Остановка по Ctrl+C")
            if 'process' in locals():
                process.terminate()
            break
        except Exception as e:
            print(f"❌ [RUNNER] Критическая ошибка: {e}")
            break

if __name__ == "__main__":
    start_bot()