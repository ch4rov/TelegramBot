import os
import zipfile
import io
import urllib.request
import shutil
import sys

FFMPEG_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"

# Получаем папку, где лежит ЭТОТ файл
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# ЛОГИКА: 
# Если файл лежит в .../core/installs, то качаем прямо сюда.
# Если файл лежит в .../core, то качаем в .../core/installs.
if CURRENT_DIR.endswith("installs"):
    TARGET_DIR = CURRENT_DIR
else:
    TARGET_DIR = os.path.join(CURRENT_DIR, "installs")

def check_and_install_ffmpeg():
    # Создаем папку, если её нет (на случай если скрипт в core/)
    os.makedirs(TARGET_DIR, exist_ok=True)
    
    ffmpeg_exe_path = os.path.join(TARGET_DIR, "ffmpeg.exe")
    ffprobe_exe_path = os.path.join(TARGET_DIR, "ffprobe.exe")
    
    # Проверяем наличие
    if os.path.exists(ffmpeg_exe_path) and os.path.exists(ffprobe_exe_path):
        print(f"✅ [SYSTEM] FFmpeg найден: {ffmpeg_exe_path}")
        return

    print(f"⚠️ [SYSTEM] FFmpeg не найден. Скачивание в: {TARGET_DIR}")
    print(f"⬇️ Скачивание архива...")

    try:
        with urllib.request.urlopen(FFMPEG_URL, timeout=60) as response:
            zip_data = response.read()

        print("📦 Распаковка...")

        with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
            temp_extract_dir = os.path.join(TARGET_DIR, "temp_extract")
            if os.path.exists(temp_extract_dir):
                shutil.rmtree(temp_extract_dir)
            os.makedirs(temp_extract_dir, exist_ok=True)
            
            z.extractall(temp_extract_dir)

            found_ffmpeg = False
            found_ffprobe = False

            for root, dirs, files in os.walk(temp_extract_dir):
                for file in files:
                    if file == "ffmpeg.exe":
                        shutil.move(os.path.join(root, file), ffmpeg_exe_path)
                        found_ffmpeg = True
                    elif file == "ffprobe.exe":
                        shutil.move(os.path.join(root, file), ffprobe_exe_path)
                        found_ffprobe = True

            shutil.rmtree(temp_extract_dir)

        if found_ffmpeg and found_ffprobe:
            print("✅ [SYSTEM] FFmpeg успешно установлен!")
        else:
            print("❌ [ERROR] Не удалось найти ffmpeg.exe внутри архива.")
            sys.exit(1)

    except Exception as e:
        print(f"❌ [ERROR] Ошибка установки FFmpeg: {e}")
        # Не выходим через sys.exit, чтобы бот мог попробовать запуститься (хотя без ffmpeg видео не будет)