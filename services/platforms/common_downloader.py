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
    return text.split('\n')[0]

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
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        local_ffmpeg = os.path.join(base_dir, "core", "installs", "ffmpeg.exe")
        
        ffmpeg_location = None
        if os.path.exists(local_ffmpeg):
            ffmpeg_location = local_ffmpeg  # полный путь к локальному бинарю
        else:
            system_ffmpeg = shutil.which("ffmpeg")
            if system_ffmpeg:
                ffmpeg_location = system_ffmpeg

        if not ffmpeg_location:
            return None, None, "System Error: FFmpeg missing.", None

        if not os.path.exists(self.download_path): 
            os.makedirs(self.download_path)

        user_cookie_content = self.options.get('user_cookie_content')
        capture_logger = ErrorCaptureLogger()
        ydl_opts = self.get_platform_settings()
        
        ydl_opts.update({
            'outtmpl': f'{self.download_path}/%(id)s.%(ext)s',
            'max_filesize': settings.MAX_FILE_SIZE,
            'logger': capture_logger,
            'quiet': True,
            'writeinfojson': True, 
            'overwrites': True,
            'socket_timeout': 15,
            'trim_file_name': 200,
            'postprocessors': []
        })

        is_yt_music = "music.youtube.com" in self.url
        is_twitch = "twitch.tv" in self.url
        is_spotify = "http://googleusercontent.com/spotify.com" in self.url
        is_soundcloud = "soundcloud.com" in self.url

        if is_yt_music or is_spotify or is_soundcloud:
            # === AUDIO MODE ===
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['writethumbnail'] = False 
            
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
            
        elif is_twitch:
            # === TWITCH SIMPLE MODE (Как раньше) ===
            ydl_opts['writethumbnail'] = True
            
            # 1. Просим yt-dlp сразу найти mp4, чтобы не конвертировать
            ydl_opts['format'] = 'best[ext=mp4]/best'
            
            # 2. УБИРАЕМ ВСЕ СЛОЖНЫЕ ФИЛЬТРЫ FFMPEG
            # Оставляем пустой список пост-процессоров для видео, 
            # yt-dlp сам склеит звук и видео, если они пойдут отдельными потоками.
            
            # Единственное, что оставим — это получение картинки (обложки)
            ydl_opts['postprocessors'].append({'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'})

        else:
            # === STANDARD VIDEO ===
            ydl_opts['writethumbnail'] = True
            # Instagram can sometimes provide still-image variants; prefer a real H.264 mp4 video when possible.
            if "instagram.com" in (self.url or ""):
                ydl_opts['format'] = 'bv*[ext=mp4][vcodec^=avc1]+ba[ext=m4a]/b[ext=mp4]/b'
                ydl_opts['merge_output_format'] = 'mp4'
                ydl_opts['remuxvideo'] = 'mp4'
            else:
                ydl_opts['format'] = 'bestvideo+bestaudio/best'
            ydl_opts['merge_output_format'] = 'mp4'
            
            ydl_opts['postprocessors'].append({'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'})
            ydl_opts['postprocessors'].append({'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'})
            ydl_opts['postprocessors'].append({'key': 'FFmpegMetadata', 'add_metadata': True})

        if ffmpeg_location:
            # yt-dlp принимает либо путь к бинарю, либо директорию; даём оба
            if os.path.isfile(ffmpeg_location):
                ydl_opts['ffmpeg_location'] = ffmpeg_location
                ffmpeg_dir = os.path.dirname(ffmpeg_location)
            else:
                ydl_opts['ffmpeg_location'] = ffmpeg_location
                ffmpeg_dir = ffmpeg_location

            ydl_opts['prefer_ffmpeg'] = True

            # Добавляем в PATH на всякий случай
            if ffmpeg_dir:
                os.environ["PATH"] = f"{ffmpeg_dir}{os.pathsep}" + os.environ.get("PATH", "")

        if user_cookie_content:
            cpath = os.path.join(self.download_path, "user.txt")
            with open(cpath, "w", encoding="utf-8") as f: f.write(user_cookie_content)
            ydl_opts['cookiefile'] = cpath
        elif os.path.exists("cookies.txt"):
            ydl_opts['cookiefile'] = "cookies.txt"

        try:
            loop = asyncio.get_event_loop()
            await asyncio.wait_for(
                loop.run_in_executor(None, lambda: self._run_yt_dlp(ydl_opts)),
                timeout=120.0
            )
        except asyncio.TimeoutError:
            self._safe_remove()
            return None, None, "Timeout: Processing took too long", None
        except Exception as e:
            self._safe_remove()
            return None, None, "Download Error", None
        
        files = self._get_files()
        
        if not files:
            err_msg = capture_logger.error_message or "Unknown Error"
            if "too large" in str(err_msg):
                self._safe_remove()
                return None, None, "File too large", None
            self._safe_remove()
            return None, None, _clean_error_message(err_msg), None

        metadata = {}
        info_json = next((f for f in files if f.endswith('.info.json')), None)
        if info_json:
            try:
                with open(info_json, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            except: pass
            
        clean_files = [f for f in files if not f.endswith('.info.json')]

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