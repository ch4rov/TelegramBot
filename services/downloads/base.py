import yt_dlp
import os
import shutil
import uuid
import asyncio
from datetime import datetime

async def base_download(url: str, custom_opts: dict = None):
    unique_id = str(uuid.uuid4())
    download_folder = os.path.join("downloads", unique_id)
    
    if not os.path.exists(download_folder):
        os.makedirs(download_folder)

    # Флаги
    skip_conversion = False
    skip_metadata = False 

    if custom_opts:
        if 'skip_conversion' in custom_opts:
            skip_conversion = custom_opts['skip_conversion']
            del custom_opts['skip_conversion']
        if 'skip_metadata' in custom_opts:
            skip_metadata = custom_opts['skip_metadata']
            del custom_opts['skip_metadata']

    ydl_opts = {
        'outtmpl': f'{download_folder}/%(artist,uploader)s - %(title)s.%(ext)s',
        'max_filesize': 50 * 1024 * 1024,
        'ignoreerrors': True,
        'quiet': True,
        'noplaylist': True,
        'writethumbnail': True,
        'overwrites': True,
        'force_overwrites': True,
        'socket_timeout': 30,
        'extractor_timeout': 60,
        'trim_file_name': 200,
        'postprocessors': []
    }

    # 1. Конвертация в MP4 (Если не отключена и это не аудио)
    # Это спасет, если YouTube все-таки отдал WebM
    if not skip_conversion:
        ydl_opts['postprocessors'].append({
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        })
    
    # 2. Метаданные
    if not skip_metadata:
        ydl_opts['postprocessors'].append({
            'key': 'FFmpegMetadata', 
            'add_metadata': True
        })

    # 3. Слияние с кастомными настройками
    if custom_opts:
        if 'postprocessors' in custom_opts:
            base_pp = ydl_opts['postprocessors'][:]
            custom_pp = custom_opts['postprocessors']
            
            # Если качаем аудио (Music/Soundcloud), убираем видео-конвертер
            is_audio = any(p.get('key') == 'FFmpegExtractAudio' for p in custom_pp)
            if is_audio:
                base_pp = [p for p in base_pp if p.get('key') != 'FFmpegVideoConvertor']
            
            ydl_opts['postprocessors'] = custom_pp + base_pp
            del custom_opts['postprocessors']
            
        ydl_opts.update(custom_opts)

    try:
        loop = asyncio.get_event_loop()
        # Запускаем yt-dlp
        error_output = await loop.run_in_executor(None, lambda: _run_yt_dlp(url, ydl_opts))
        
        if error_output:
            try:
                log_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'logs', 'files')
                if not os.path.exists(log_dir): os.makedirs(log_dir)
                log_path = os.path.join(log_dir, 'full_log.txt')
                with open(log_path, 'a', encoding='utf-8') as f:
                    ts = datetime.utcnow().isoformat()
                    f.write(f"{ts} | YT-DLP-ERROR | URL:{url} | {error_output}\n")
            except: pass
        
        await asyncio.sleep(1)

        files = []
        for root, dirs, filenames in os.walk(download_folder):
            for filename in filenames:
                if not filename.endswith(('.tmp', '.part', '.info.json', '.ytdl')):
                    file_path = os.path.join(root, filename)
                    if os.path.getsize(file_path) > 0:
                        files.append(file_path)

        if not files:
            shutil.rmtree(download_folder, ignore_errors=True)
            return None, None, "Не удалось скачать файлы."

        return files, download_folder, None

    except yt_dlp.utils.DownloadError as e:
        _safe_remove(download_folder)
        if 'File is larger than' in str(e): return None, None, "❌ Файл >50 МБ."
        return None, None, f"Ошибка загрузки: {str(e)}"
    except Exception as e:
        _safe_remove(download_folder)
        return None, None, f"Системная ошибка: {str(e)}"

def _run_yt_dlp(url, opts):
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    except Exception as e:
        return str(e)
    return None

def _safe_remove(path):
    try:
        if os.path.exists(path): shutil.rmtree(path, ignore_errors=True)
    except: pass