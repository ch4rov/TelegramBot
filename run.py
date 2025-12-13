import os
import sys
import time
import subprocess
from core.installs.ffmpeg_installer import check_and_install_ffmpeg

def main():
    check_and_install_ffmpeg()

    while True:
        print("\n🔋 [RUNNER] Запуск main.py...")
        process = subprocess.Popen([sys.executable, "main.py"])
        
        try:
            process.wait()
        except KeyboardInterrupt:
            print("\n🛑 Останавливаю бота...")
            process.terminate()
            
            try:
                subprocess.run(f"taskkill /F /T /PID {process.pid}", shell=True, stderr=subprocess.DEVNULL)
            except: pass
            
            break

        exit_code = process.returncode
        print(f"⚠️ [RUNNER] Бот упал (код {exit_code}). Перезапуск через 5 сек...")
        time.sleep(5)

if __name__ == "__main__":
    main()