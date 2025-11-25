import os
import zipfile
import io
import urllib.request

# Ссылка на стабильную сборку FFmpeg (официальный репозиторий)
URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"

print(f"🚀 Начинаю скачивание FFmpeg с {URL}...")
print("Это может занять минуту, файл весит около 30-40 МБ.")

# Скачиваем архив в оперативную память
response = urllib.request.urlopen(URL)
zip_data = response.read()

print("📦 Распаковка архива...")

# Открываем архив из памяти
with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
    # Ищем файлы ffmpeg.exe и ffprobe.exe внутри архива
    for file in z.namelist():
        if file.endswith("ffmpeg.exe") or file.endswith("ffprobe.exe"):
            # Извлекаем только их в текущую папку
            filename = os.path.basename(file)
            with open(filename, 'wb') as f_out:
                f_out.write(z.read(file))
            print(f"✅ Извлечен: {filename}")

print("🎉 Готово! FFmpeg установлен в папку с ботом.")