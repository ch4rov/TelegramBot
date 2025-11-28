import os
import zipfile
import io
import urllib.request
import shutil
import sys

# Ссылка на стабильную сборку FFmpeg
FFMPEG_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
# Определяем путь к папке installs относительно текущего файла
TARGET_DIR = os.path.dirname(os.path.abspath(__file__)) 

def check_and_install_ffmpeg():
    """
    Проверяет наличие ffmpeg.exe в core/installs/. Если нет - качает и устанавливает.
    """
    ffmpeg_exe_path = os.path.join(TARGET_DIR, "ffmpeg.exe")
    ffprobe_exe_path = os.path.join(TARGET_DIR, "ffprobe.exe")
    
    # Если файлы уже есть - выходим
    if os.path.exists(ffmpeg_exe_path) and os.path.exists(ffprobe_exe_path):
        print("✅ [SYSTEM] FFmpeg найден в core/installs/.")
        return

    print(f"⚠️ [SYSTEM] FFmpeg не найден. Начинаю автоматическую загрузку в {TARGET_DIR}...")
    print(f"⬇️ Скачивание архива...")

    try:
        # 1. Скачиваем в память
        # Используем таймаут, чтобы не висело вечно
        with urllib.request.urlopen(FFMPEG_URL, timeout=60) as response:
            zip_data = response.read()

        print("📦 Распаковка и извлечение...")

        # 2. Открываем архив из памяти
        with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
            
            # Создаем временную папку для распаковки
            temp_extract_dir = os.path.join(TARGET_DIR, "temp_extract")
            if os.path.exists(temp_extract_dir):
                shutil.rmtree(temp_extract_dir)
            os.makedirs(temp_extract_dir, exist_ok=True)
            
            z.extractall(temp_extract_dir)

            # 3. Ищем exe файлы внутри распакованных папок (они могут быть глубоко)
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

            # Удаляем временную папку
            shutil.rmtree(temp_extract_dir)

        if found_ffmpeg and found_ffprobe:
            print("✅ [SYSTEM] FFmpeg успешно установлен!")
        else:
            print("❌ [ERROR] Не удалось найти ffmpeg.exe внутри архива.")
            sys.exit(1)

    except Exception as e:
        print(f"❌ [ERROR] Ошибка установки FFmpeg: {e}")
        sys.exit(1)