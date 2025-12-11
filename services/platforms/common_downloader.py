import yt_dlp
import os
import shutil
import uuid
import asyncio
import re
import json
from abc import ABC, abstractmethod
import settings

class ErrorCaptureLogger:
    def __init__(self):
        self.error_message = None
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg):
        self.error_message = msg
        print(f"[YT-DLP ERROR] {msg}")

def _clean_error_message(error_text: str) -> str:
    if not error_text: return "Unknown Error"

    if "Instagram sent an empty media response" in str(error_text):
        return "Instagram Post Unavailable. Possibly Private or Deleted."

    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    text = ansi_escape.sub('', str(error_text))
    
    if "ERROR:" in text: 
        parts = text.split("ERROR:", 1)
        if len(parts) > 1: text = parts[1].strip()
    
    lines = text.split('\n')
    # Filter out traceback lines
    clean_lines = [line for line in lines if "Traceback" not in line and "File " not in line and line.strip()]
    return " ".join(clean_lines[:2])

class CommonDownloader(ABC):
    def __init__(self, url: str):
        self.url = url
        self.unique_id = str(uuid.uuid4())
        self.download_path = os.path.join("downloads", self.unique_id)
        self.options = {} 

    def configure(self, **kwargs):
        self.options.update(kwargs)

    @abstractmethod
    def get_platform_settings(self) -> dict:
        pass

    async def download(self):
        # 1. FFmpeg Check
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        local_ffmpeg = os.path.join(base_dir, "core", "installs", "ffmpeg.exe")
        
        ffmpeg_location = None
        if os.path.exists(local_ffmpeg): 
            ffmpeg_location = os.path.dirname(local_ffmpeg)
        elif shutil.which("ffmpeg"): 
            ffmpeg_location = None
        else:
            print(f"❌ [SYSTEM] FFmpeg not found!")
            return None, None, "System Error: FFmpeg missing.", None

        if not os.path.exists(self.download_path): 
            os.makedirs(self.download_path)

        skip_conversion = self.options.get('skip_conversion', False)
        user_cookie_content = self.options.get('user_cookie_content')

        capture_logger = ErrorCaptureLogger()
        ydl_opts = self.get_platform_settings()
        
        # --- НАСТРОЙКА (СРАЗУ SAFE MODE) ---
        ydl_opts.update({
            'outtmpl': f'{self.download_path}/%(id)s.%(ext)s',
            'max_filesize': settings.MAX_FILE_SIZE,
            'logger': capture_logger,
            'quiet': True,
            # Оставляем True для получения обложки, но не конвертируем её жестко
            'writethumbnail': True, 
            'writeinfojson': True, 
            'overwrites': True,
            'force_overwrites': True,
            'socket_timeout': 20,
            'trim_file_name': 200,
            # Инициализируем пустой список постпроцессоров, чтобы добавить только нужное
            'postprocessors': []
        })

        if ffmpeg_location: 
            ydl_opts['ffmpeg_location'] = ffmpeg_location

        # Добавляем куки
        if user_cookie_content:
            cpath = os.path.join(self.download_path, "user.txt")
            with open(cpath, "w", encoding="utf-8") as f: f.write(user_cookie_content)
            ydl_opts['cookiefile'] = cpath
        elif os.path.exists("cookies.txt"):
            ydl_opts['cookiefile'] = "cookies.txt"

        # --- ЛОГИКА ПОСТПРОЦЕССИНГА ---
        # Добавляем конвертацию видео в MP4 (если не отключено)
        # Это то, что было в "Safe Mode"
        if not skip_conversion:
             ydl_opts['postprocessors'].append({
                 'key': 'FFmpegVideoConvertor', 
                 'preferedformat': 'mp4'
             })
        
        # Мы убрали 'FFmpegMetadata' и 'FFmpegThumbnailsConvertor', которые были в 1-м способе,
        # так как они часто вызывают ошибки на специфических видео.

        # === ЗАПУСК СКАЧИВАНИЯ ===
        print(f"⬇️ [DOWNLOAD] Start: {self.url}")
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._run_yt_dlp(ydl_opts))
        
        files = self._get_files()
        
        # Проверка ошибок
        if not files:
            # Если файлов нет, смотрим ошибку
            err_msg = capture_logger.error_message or "Unknown Error"
            
            if "too large" in str(err_msg):
                self._safe_remove()
                return None, None, "File too large", None
            
            print(f"❌ [DOWNLOAD] Failed: {err_msg}")
            self._safe_remove()
            return None, None, _clean_error_message(err_msg), None

        # === УСПЕХ: ЧИТАЕМ МЕТАДАННЫЕ ===
        metadata = {}
        info_json = next((f for f in files if f.endswith('.info.json')), None)
        if info_json:
            try:
                with open(info_json, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            except: pass
            
        # Чистим список от json и мусора
        clean_files = [f for f in files if not f.endswith('.info.json')]

        print(f"✅ [DOWNLOAD] Success. Files: {len(clean_files)}")
        return clean_files, self.download_path, None, metadata

    def _run_yt_dlp(self, opts):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([self.url])
        except Exception: pass

    def _get_files(self):
        found = []
        for root, _, filenames in os.walk(self.download_path):
            for f in filenames:
                if f == "user.txt": continue
                if not f.endswith(('.tmp', '.part', '.ytdl')):
                    fp = os.path.join(root, f)
                    if os.path.getsize(fp) > 0: found.append(fp)
        return found

    def _safe_remove(self):
        try:
            if os.path.exists(self.download_path): 
                shutil.rmtree(self.download_path, ignore_errors=True)
        except: pass