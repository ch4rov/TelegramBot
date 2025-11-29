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
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    text = ansi_escape.sub('', str(error_text))
    if "ERROR:" in text: text = text.split("ERROR:", 1)[1].strip()
    lines = text.split('\n')
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
        # 1. Проверка FFmpeg
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        local_ffmpeg = os.path.join(base_dir, "core", "installs", "ffmpeg.exe")
        
        ffmpeg_location = None
        if os.path.exists(local_ffmpeg): ffmpeg_location = os.path.dirname(local_ffmpeg)
        elif shutil.which("ffmpeg"): ffmpeg_location = None
        else:
            print(f"❌ [SYSTEM] FFmpeg не найден!")
            return None, None, "System Error: FFmpeg missing.", None

        if not os.path.exists(self.download_path): os.makedirs(self.download_path)

        skip_conversion = self.options.get('skip_conversion', False)
        user_cookie_content = self.options.get('user_cookie_content')

        capture_logger = ErrorCaptureLogger()
        ydl_opts = self.get_platform_settings()
        
        ydl_opts.update({
            # БЕЗОПАСНОЕ ИМЯ ФАЙЛА (на диске)
            # Мы не используем title здесь, чтобы избежать спецсимволов
            'outtmpl': f'{self.download_path}/%(id)s.%(ext)s',
            
            'max_filesize': settings.MAX_FILE_SIZE,
            'logger': capture_logger,
            'quiet': True,
            'writethumbnail': True,
            'writeinfojson': True, # Обязательно для метаданных
            'overwrites': True,
            'socket_timeout': 20,
            'trim_file_name': 200
        })

        if 'postprocessors' not in ydl_opts: ydl_opts['postprocessors'] = []

        if not skip_conversion:
             has_conv = any(p['key'] == 'FFmpegVideoConvertor' for p in ydl_opts['postprocessors'])
             if not has_conv: ydl_opts['postprocessors'].insert(0, {'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'})

        ydl_opts['postprocessors'].append({'key': 'FFmpegMetadata', 'add_metadata': True})
        ydl_opts['postprocessors'].append({'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'})

        if ffmpeg_location: ydl_opts['ffmpeg_location'] = ffmpeg_location

        if user_cookie_content:
            cpath = os.path.join(self.download_path, "user.txt")
            with open(cpath, "w", encoding="utf-8") as f: f.write(user_cookie_content)
            ydl_opts['cookiefile'] = cpath
        elif os.path.exists("cookies.txt"):
            ydl_opts['cookiefile'] = "cookies.txt"

        # === ЗАПУСК ===
        print(f"⬇️ [DOWNLOAD] Start: {self.url}")
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._run_yt_dlp(ydl_opts))
        
        files = self._get_files()
        
        # Ошибка размера
        if capture_logger.error_message and "too large" in str(capture_logger.error_message):
             self._safe_remove()
             return None, None, "File too large", None

        # === SAFE MODE ===
        if not files or capture_logger.error_message:
            print(f"⚠️ [DOWNLOAD] Retry Safe Mode...")
            self._clean_folder()

            capture_logger_2 = ErrorCaptureLogger()
            retry_opts = ydl_opts.copy()
            retry_opts['logger'] = capture_logger_2
            retry_opts['writethumbnail'] = False
            retry_opts['postprocessors'] = []
            
            if 'postprocessors' in self.options:
                retry_opts['postprocessors'].extend(self.options['postprocessors'])
            elif not skip_conversion:
                retry_opts['postprocessors'].append({'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'})
            
            if ffmpeg_location: retry_opts['ffmpeg_location'] = ffmpeg_location

            await loop.run_in_executor(None, lambda: self._run_yt_dlp(retry_opts))
            files = self._get_files()

            if not files:
                err = capture_logger_2.error_message or capture_logger.error_message or "Unknown"
                print(f"❌ [DOWNLOAD] Failed: {err}")
                self._safe_remove()
                return None, None, _clean_error_message(err), None

        # === ЧТЕНИЕ МЕТАДАННЫХ ===
        metadata = {}
        info_json = next((f for f in files if f.endswith('.info.json')), None)
        if info_json:
            try:
                with open(info_json, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            except: pass
            
        # Удаляем технические файлы из списка (оставляем только медиа)
        clean_files = [f for f in files if not f.endswith('.info.json')]

        print(f"✅ [DOWNLOAD] Success. Files: {len(clean_files)}")
        # ВОЗВРАЩАЕМ 4 ЗНАЧЕНИЯ
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

    def _clean_folder(self):
        for f in os.listdir(self.download_path):
            if f != "user.txt":
                try:
                    p = os.path.join(self.download_path, f)
                    if os.path.isfile(p): os.remove(p)
                    else: shutil.rmtree(p)
                except: pass

    def _safe_remove(self):
        try:
            if os.path.exists(self.download_path): 
                shutil.rmtree(self.download_path, ignore_errors=True)
        except: pass