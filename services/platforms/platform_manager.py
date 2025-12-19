# -*- coding: utf-8 -*-
import os
import shutil
import uuid
import logging
import re
import asyncio
import yt_dlp
from services.database.repo import get_user_cookie, get_global_cookie
from core.config import config
from services.odesli_service import get_links_by_url
import subprocess
import json

logger = logging.getLogger(__name__)

# URL patterns for different platforms
URL_PATTERNS = {
    'youtube': r'(youtube\.com|youtu\.be)',
    'tiktok': r'tiktok\.com',
    'instagram': r'instagram\.com',
    'vk': r'vk\.com|vkontakte\.ru',
    'twitch': r'(twitch\.tv|clips\.twitch\.tv)',
    'soundcloud': r'soundcloud\.com',
    'spotify': r'open\.spotify\.com',
}

def is_valid_url(text):
    """Check if text is a valid platform URL"""
    if not text:
        return False
    
    for platform, pattern in URL_PATTERNS.items():
        if re.search(pattern, text):
            return True
    return False

async def download_content(url, custom_opts=None, user_id=None):
    """Download content from URL using yt-dlp"""
    original_url = url

    # Spotify is not directly downloadable; fall back to a YouTube link via Odesli (song.link)
    try:
        if url and re.search(URL_PATTERNS.get('spotify', r'$^'), url):
            links = await get_links_by_url(url)
            yt_url = None
            if links and links.get('links'):
                yt_url = links['links'].get('YouTube')
            if yt_url:
                url = yt_url
                logger.info(f"Spotify fallback via YouTube: {original_url} -> {url}")
    except Exception as e:
        logger.warning(f"Spotify fallback failed for {original_url}: {e}")

    folder_name = str(uuid.uuid4())
    save_path = os.path.join("tempfiles", folder_name)
    os.makedirs(save_path, exist_ok=True)

    cookie_path = None
    
    # Try to get cookies from database
    if user_id:
        # Determine service from URL
        service = "youtube"
        if "tiktok" in url:
            service = "tiktok"
        elif "instagram" in url:
            service = "youtube"  # Instagram uses similar cookies
        elif "vk" in url:
            service = "vk"
        elif "twitch" in url:
            service = "twitch"
        elif "soundcloud" in url:
            service = "soundcloud"
        elif "spotify" in url:
            service = "spotify"
        
        # Try user cookies first
        cookie_data = await get_user_cookie(user_id, service)
        
        # If no user cookies, try global cookies
        if not cookie_data:
            cookie_data = await get_global_cookie(service)
        
        if cookie_data:
            cookie_path = os.path.join(save_path, "cookies.txt")
            with open(cookie_path, "w", encoding="utf-8") as f:
                f.write(cookie_data)

    ydl_opts = {
        'outtmpl': os.path.join(save_path, '%(title)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'writeinfojson': False,
        'writethumbnail': False,
        'restrictfilenames': True,
    }

    is_instagram = bool(re.search(URL_PATTERNS['instagram'], url))

    # Instagram sometimes offers "storyboard"/still-image variants; prefer a real H.264 mp4 video when possible.
    if is_instagram and 'format' not in ydl_opts and not (custom_opts and 'format' in custom_opts):
        ydl_opts['format'] = 'bv*[ext=mp4][vcodec^=avc1]+ba[ext=m4a]/b[ext=mp4]/b'
        ydl_opts['merge_output_format'] = 'mp4'
        # Remux to mp4 if needed (no re-encode) when ffmpeg is available.
        ydl_opts['remuxvideo'] = 'mp4'

    # Ensure yt-dlp can find ffmpeg/ffprobe (needed for merging formats)
    try:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        installs_dir = os.path.join(base_dir, "core", "installs")
        local_ffmpeg = os.path.join(installs_dir, "ffmpeg.exe")
        local_ffprobe = os.path.join(installs_dir, "ffprobe.exe")
        if os.path.exists(local_ffmpeg) and os.path.exists(local_ffprobe):
            ydl_opts['ffmpeg_location'] = installs_dir
            ydl_opts['prefer_ffmpeg'] = True
            os.environ["PATH"] = f"{installs_dir}{os.pathsep}" + os.environ.get("PATH", "")
    except Exception:
        pass

    # Default safer format for YouTube: prefer a single-file mp4 when possible
    if re.search(URL_PATTERNS['youtube'], url) and 'format' not in ydl_opts:
        ydl_opts['format'] = 'best[ext=mp4]/best'

    if cookie_path:
        ydl_opts['cookiefile'] = cookie_path

    if custom_opts:
        ydl_opts.update(custom_opts)

    meta = {}
    error = None
    files = []

    # Retry with fallback formats for cases where merging is required
    attempts = [
        dict(ydl_opts),
        {**ydl_opts, 'format': 'best[ext=mp4]/best'},
        {**ydl_opts, 'format': 'best'},
    ]

    def _find_ffprobe() -> str | None:
        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            installs_dir = os.path.join(base_dir, "core", "installs")
            local_ffprobe = os.path.join(installs_dir, "ffprobe.exe")
            if os.path.exists(local_ffprobe):
                return local_ffprobe
        except Exception:
            pass
        return shutil.which("ffprobe")

    def _looks_like_static_video(video_path: str) -> bool:
        ffprobe = _find_ffprobe()
        if not ffprobe:
            return False
        try:
            args = [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=nb_frames,avg_frame_rate,r_frame_rate,codec_name",
                "-of",
                "json",
                video_path,
            ]
            completed = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
            if completed.returncode != 0:
                return False
            data = json.loads((completed.stdout or b"{}").decode("utf-8", errors="ignore") or "{}")
            streams = data.get("streams") or []
            if not streams:
                return False
            stream = streams[0] or {}
            nb_frames = stream.get("nb_frames")
            if nb_frames is not None:
                try:
                    if int(nb_frames) <= 1:
                        return True
                except Exception:
                    pass
            # Fallback heuristic: some broken outputs report 0/0 fps.
            afr = str(stream.get("avg_frame_rate") or "")
            if afr.strip() in ("0/0", "0"):
                return True
        except Exception:
            return False
        return False

    def _extract_sync(opts: dict):
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=True)

    for idx, opts in enumerate(attempts, start=1):
        try:
            info = await asyncio.to_thread(_extract_sync, opts)
            meta = info
            logger.info(f"Successfully downloaded from: {url} (attempt {idx})")
            error = None
            break
        except Exception as e:
            error = str(e)
            logger.error(f"Error downloading {url} (attempt {idx}): {error}")
    
    # Collect downloaded files
    if os.path.exists(save_path):
        for root, dirs, filenames in os.walk(save_path):
            for f in filenames:
                files.append(os.path.join(root, f))

    # Instagram: if the resulting mp4 looks like a still image with audio, retry once with stricter selection.
    if is_instagram and not error:
        video_candidates = [f for f in files if f.lower().endswith((".mp4", ".mov", ".mkv", ".webm"))]
        maybe_video = video_candidates[0] if video_candidates else None
        if maybe_video and _looks_like_static_video(maybe_video):
            logger.warning("Instagram download looks static; retrying with stricter format selection")
            try:
                # Clean folder and retry
                for root, _, filenames in os.walk(save_path):
                    for fn in filenames:
                        try:
                            os.remove(os.path.join(root, fn))
                        except Exception:
                            pass
                retry_opts = dict(ydl_opts)
                retry_opts['format'] = 'bv*[vcodec^=avc1][ext=mp4]+ba[ext=m4a]/bv*+ba/b'
                retry_opts['merge_output_format'] = 'mp4'
                retry_opts['remuxvideo'] = 'mp4'
                info = await asyncio.to_thread(_extract_sync, retry_opts)
                meta = info
                error = None

                files = []
                for root, dirs, filenames in os.walk(save_path):
                    for f in filenames:
                        files.append(os.path.join(root, f))
            except Exception as e:
                error = str(e)
                logger.error(f"Instagram retry failed: {error}")

    return files, save_path, error, meta