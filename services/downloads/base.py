import yt_dlp
import os
import shutil
import uuid
import asyncio
import re
from datetime import datetime
import settings

# --- ШПИОН ДЛЯ ПЕРЕХВАТА ОШИБОК ---
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

async def base_download(url: str, custom_opts: dict = None):
    unique_id = str(uuid.uuid4())
    download_folder = os.path.join("downloads", unique_id)
    if not os.path.exists(download_folder): os.makedirs(download_folder)

    skip_conversion = False
    user_cookie_content = None
    opts_copy = custom_opts.copy() if custom_opts else {}

    if opts_copy:
        if 'skip_conversion' in opts_copy:
            skip_conversion = opts_copy['skip_conversion']
            del opts_copy['skip_conversion']
        if 'user_cookie_content' in opts_copy:
            user_cookie_content = opts_copy['user_cookie_content']
            del opts_copy['user_cookie_content']

    # === ПОПЫТКА 1: КРАСИВАЯ ===
    capture_logger = ErrorCaptureLogger()
    ydl_opts = {
        'outtmpl': f'{download_folder}/%(title)s.%(ext)s',
        'max_filesize': settings.MAX_FILE_SIZE, 
        'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
        'logger': capture_logger,
        'ignoreerrors': True,
        'quiet': False,
        'noplaylist': True,
        'writethumbnail': True,
        'writeinfojson': True,
        'overwrites': True,
        'force_overwrites': True,
        'socket_timeout': 20,
        'extractor_timeout': 30,
        'trim_file_name': 160, # Длинное имя
        'postprocessors': []
    }
    
    if user_cookie_content:
        cpath = os.path.join(download_folder, "user.txt")
        with open(cpath, "w", encoding="utf-8") as f: f.write(user_cookie_content)
        ydl_opts['cookiefile'] = cpath
    elif os.path.exists("cookies.txt"):
        ydl_opts['cookiefile'] = "cookies.txt"

    if not skip_conversion:
        ydl_opts['postprocessors'].append({'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'})
    ydl_opts['postprocessors'].append({'key': 'FFmpegMetadata', 'add_metadata': True})
    ydl_opts['postprocessors'].append({'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'})

    if opts_copy:
        if 'postprocessors' in opts_copy:
            base_pp = ydl_opts['postprocessors'][:]
            custom_pp = opts_copy['postprocessors']
            is_audio = any(p.get('key') == 'FFmpegExtractAudio' for p in custom_pp)
            if is_audio:
                base_pp = [p for p in base_pp if p['key'] != 'FFmpegVideoConvertor']
            ydl_opts['postprocessors'] = custom_pp + base_pp
            del opts_copy['postprocessors']
        ydl_opts.update(opts_copy)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: _run_yt_dlp(url, ydl_opts))
    
    files = _check_files(download_folder)
    
    # === ПОПЫТКА 2: БЕЗОПАСНАЯ (Если первая упала) ===
    if not files or capture_logger.error_message:
        print(f"⚠️ [RETRY] Первая попытка не удалась. Запуск Safe Mode...")
        
        # Чистим папку
        for f in os.listdir(download_folder):
            if f != "user.txt": 
                try:
                    full_p = os.path.join(download_folder, f)
                    if os.path.isfile(full_p): os.remove(full_p)
                    else: shutil.rmtree(full_p)
                except: pass

        capture_logger_2 = ErrorCaptureLogger()
        retry_opts = ydl_opts.copy()
        retry_opts['logger'] = capture_logger_2
        
        # УПРОЩАЕМ ИМЯ ФАЙЛА
        retry_opts['writethumbnail'] = False # Без обложки
        retry_opts['trim_file_name'] = 100   # Лимит 100 символов (было 50)
        retry_opts['restrictfilenames'] = True # <--- ВАЖНО: Заменяет кириллицу и спецсимволы на ASCII, чтобы Windows не ругалась
        retry_opts['postprocessors'] = []    
        
        # Возвращаем аудио-конвертер, если он нужен
        if custom_opts and 'postprocessors' in custom_opts: # Берем из исходного custom_opts, т.к. opts_copy уже пуст
            # Нужно заново восстановить логику аудио
            # (Упрощенно: если просили аудио, добавим конвертер)
             if any('FFmpegExtractAudio' in str(p) for p in custom_opts.get('postprocessors', [])):
                 retry_opts['postprocessors'].append({'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'})
        
        if not retry_opts['postprocessors'] and not skip_conversion:
             retry_opts['postprocessors'].append({'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'})

        await loop.run_in_executor(None, lambda: _run_yt_dlp(url, retry_opts))
        files = _check_files(download_folder)
        
        if not files:
            err_msg = capture_logger_2.error_message or capture_logger.error_message or "Unknown Error"
            _safe_remove(download_folder)
            return None, None, _clean_error_message(err_msg)

    return files, download_folder, None


def _check_files(folder):
    found_files = []
    for root, dirs, filenames in os.walk(folder):
        for filename in filenames:
            if filename == "user.txt": continue
            if not filename.endswith(('.tmp', '.part', '.info.json', '.ytdl')):
                file_path = os.path.join(root, filename)
                if os.path.getsize(file_path) > 0: found_files.append(file_path)
    return found_files

def _run_yt_dlp(url, opts):
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    except Exception: pass

def _safe_remove(path):
    try:
        if os.path.exists(path): shutil.rmtree(path, ignore_errors=True)
    except: pass