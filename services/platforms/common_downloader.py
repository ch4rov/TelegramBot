import yt_dlp
import os
import shutil
import uuid
import asyncio
import re
from abc import ABC, abstractmethod
import settings

# --- ШПИОН ДЛЯ ПЕРЕХВАТА ОШИБОК ---
class ErrorCaptureLogger:
    def __init__(self):
        self.error_message = None
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg):
        self.error_message = msg
        # Используем обычный print
        print(f"[YT-DLP ERROR] {msg}") 

def _clean_error_message(error_text: str) -> str:
    if not error_text: return "Unknown Error"
    # Убираем цвета консоли
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    text = ansi_escape.sub('', str(error_text))
    
    if "ERROR:" in text: 
        text = text.split("ERROR:", 1)[1].strip()
    
    lines = text.split('\n')
    # Фильтруем мусор (трейсбэки)
    clean_lines = [line for line in lines if "Traceback" not in line and "File " not in line and line.strip()]
    return " ".join(clean_lines[:2])

class CommonDownloader(ABC):
    def __init__(self, url: str):
        self.url = url
        self.unique_id = str(uuid.uuid4())
        self.download_path = os.path.join("downloads", self.unique_id)
        self.options = {} 

    def configure(self, **kwargs):
        """Принимает динамические настройки"""
        self.options.update(kwargs)

    @abstractmethod
    def get_platform_settings(self) -> dict:
        pass

    async def download(self):
        # 1. ПРОВЕРКА FFMPEG
        # Вычисляем корень проекта (services/platforms/ -> вверх на 2 уровня)
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        local_ffmpeg = os.path.join(base_dir, "core", "installs", "ffmpeg.exe")
        
        ffmpeg_location = None
        if os.path.exists(local_ffmpeg):
            ffmpeg_location = os.path.dirname(local_ffmpeg)
        elif shutil.which("ffmpeg"):
            ffmpeg_location = None
        else:
            print(f"❌ [SYSTEM] FFmpeg не найден! Ожидал тут: {local_ffmpeg}")
            return None, None, "System Error: FFmpeg missing."

        if not os.path.exists(self.download_path):
            os.makedirs(self.download_path)

        # 2. Флаги
        skip_conversion = self.options.get('skip_conversion', False)
        user_cookie_content = self.options.get('user_cookie_content')

        # 3. Настройки
        capture_logger = ErrorCaptureLogger()
        ydl_opts = self.get_platform_settings()
        
        ydl_opts.update({
            'outtmpl': f'{self.download_path}/%(title)s.%(ext)s',
            'max_filesize': settings.MAX_FILE_SIZE,
            'logger': capture_logger,
            'quiet': True,
            'writethumbnail': True,
            'writeinfojson': True,
            'overwrites': True,
            'force_overwrites': True,
            'socket_timeout': 20,
            'extractor_timeout': 45,
            'trim_file_name': 160
        })

        if 'postprocessors' not in ydl_opts:
            ydl_opts['postprocessors'] = []

        if not skip_conversion:
             # Проверяем, чтобы не дублировать конвертер
             has_conv = any(p['key'] == 'FFmpegVideoConvertor' for p in ydl_opts['postprocessors'])
             if not has_conv:
                 ydl_opts['postprocessors'].insert(0, {'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'})

        ydl_opts['postprocessors'].append({'key': 'FFmpegMetadata', 'add_metadata': True})
        ydl_opts['postprocessors'].append({'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'})

        if ffmpeg_location:
            ydl_opts['ffmpeg_location'] = ffmpeg_location

        if user_cookie_content:
            cpath = os.path.join(self.download_path, "user.txt")
            with open(cpath, "w", encoding="utf-8") as f: f.write(user_cookie_content)
            ydl_opts['cookiefile'] = cpath
        elif os.path.exists("cookies.txt"):
            ydl_opts['cookiefile'] = "cookies.txt"

        # === ПОПЫТКА 1 ===
        print(f"⬇️ [DOWNLOAD] Start: {self.url}")
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._run_yt_dlp(ydl_opts))
        
        files = self._get_files()
        
        # Проверка ошибки размера
        err_msg = capture_logger.error_message
        if err_msg and ("too large" in str(err_msg) or "max_filesize" in str(err_msg)):
             print(f"⚠️ [DOWNLOAD] File too large: {self.url}")
             self._safe_remove()
             return None, None, "File too large"

        # === ПОПЫТКА 2: SAFE MODE ===
        if not files or err_msg:
            print(f"⚠️ [DOWNLOAD] Retry Safe Mode... Reason: {err_msg}")
            self._clean_folder()

            capture_logger_2 = ErrorCaptureLogger()
            retry_opts = ydl_opts.copy()
            retry_opts['logger'] = capture_logger_2
            retry_opts['writethumbnail'] = False
            retry_opts['trim_file_name'] = 50
            retry_opts['restrictfilenames'] = True
            retry_opts['postprocessors'] = []

            # Восстанавливаем конвертеры, если нужны
            if 'postprocessors' in self.options:
                retry_opts['postprocessors'].extend(self.options['postprocessors'])
            elif not skip_conversion:
                retry_opts['postprocessors'].append({'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'})
            
            if ffmpeg_location: retry_opts['ffmpeg_location'] = ffmpeg_location

            await loop.run_in_executor(None, lambda: self._run_yt_dlp(retry_opts))
            files = self._get_files()
            
            # Проверка ошибки размера (Попытка 2)
            err_msg_2 = capture_logger_2.error_message
            if err_msg_2 and ("too large" in str(err_msg_2) or "max_filesize" in str(err_msg_2)):
                 self._safe_remove()
                 return None, None, "File too large"

            if not files:
                final_err = err_msg_2 or err_msg or "Unknown"
                print(f"❌ [DOWNLOAD] Failed: {final_err}")
                self._safe_remove()
                return None, None, _clean_error_message(final_err)

        print(f"✅ [DOWNLOAD] Success. Files: {len(files)}")
        return files, self.download_path, None

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
                if not f.endswith(('.tmp', '.part', '.info.json', '.ytdl')):
                    fp = os.path.join(root, f)
                    if os.path.getsize(fp) > 0: found.append(fp)
        return found

    def _clean_folder(self):
        for f in os.listdir(self.download_path):
            if f != "user.txt":
                p = os.path.join(self.download_path, f)
                try:
                    if os.path.isfile(p): os.remove(p)
                    else: shutil.rmtree(p)
                except: pass

    def _safe_remove(self):
        try:
            if os.path.exists(self.download_path): 
                shutil.rmtree(self.download_path, ignore_errors=True)
        except: pass