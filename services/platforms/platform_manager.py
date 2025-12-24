# -*- coding: utf-8 -*-
import os
import shutil
import uuid
import logging
import re
import asyncio
import yt_dlp
from services.database.repo import get_user_cookie, get_global_cookie
from services.odesli_service import get_links_by_url
import subprocess
import json
import shutil

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
    'apple_music': r'music\.apple\.com',
    # Yandex Music can be hosted on multiple TLDs (ru/by/kz/com); Disk short links are yadi.sk
    'yandex': r'(music\.yandex\.(ru|by|kz|com)|disk\.yandex\.ru|yadi\.sk)',
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

    # TikTok: prefer API-based strategy (fixes yt-dlp "Unsupported URL" for /photo/)
    try:
        if url and re.search(URL_PATTERNS.get('tiktok', r'$^'), url):
            from services.platforms.TikTokDownloader.tiktok_strategy import TikTokStrategy

            strategy = TikTokStrategy(url)
            files, folder, error, meta = await strategy.download()
            if files:
                return files, folder, None, meta or {}
            if error:
                # For hard failures (private/deleted/unsupported), return early.
                if str(error).strip().lower() in (
                    "video unavailable",
                    "api busy (too many requests)",
                    "tiktok api busy (too many requests)",
                ):
                    return [], folder, error, meta or {}
                # Otherwise fall back to yt-dlp below.
    except Exception:
        # Fallback to yt-dlp below.
        pass

    is_yandex_music = bool(url and re.search(r'music\.yandex\.(ru|by|kz|com)', url))
    is_apple_music = bool(url and re.search(r'music\.apple\.com', url))
    is_yandex_disk = bool(url and re.search(r'(disk\.yandex\.ru|yadi\.sk)', url))

    # Yandex Disk public links: download directly via Disk API (yt-dlp doesn't reliably support these).
    if is_yandex_disk:
        folder_name = str(uuid.uuid4())
        save_path = os.path.join("tempfiles", folder_name)
        os.makedirs(save_path, exist_ok=True)
        try:
            from services.platforms.YandexDownloader import YandexDiskPublicStrategy

            strategy = YandexDiskPublicStrategy(original_url)
            files, folder, error, meta = await strategy.download(save_path)
            return files or [], folder or save_path, error, meta or {}
        except Exception as e:
            # Fall back to yt-dlp attempts below
            logger.warning(f"Yandex Disk direct download failed, falling back to yt-dlp: {e}")
            try:
                if os.path.exists(save_path):
                    shutil.rmtree(save_path, ignore_errors=True)
            except Exception:
                pass

    # Spotify / Yandex Music / Apple Music are not directly downloadable; fall back via Odesli (song.link)
    try:
        if url and (re.search(URL_PATTERNS.get('spotify', r'$^'), url) or is_yandex_music or is_apple_music):
            links = await get_links_by_url(url)
            yt_url = None
            sc_url = None
            if links and links.get('links'):
                yt_url = links['links'].get('YouTube')
                sc_url = links['links'].get('SoundCloud')
            if yt_url:
                url = yt_url
                logger.info(f"Odesli fallback via YouTube: {original_url} -> {url}")
            elif sc_url:
                url = sc_url
                logger.info(f"Odesli fallback via SoundCloud: {original_url} -> {url}")
    except Exception as e:
        logger.warning(f"Odesli fallback failed for {original_url}: {e}")

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
            service = "instagram"
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
        # A bit more robust defaults for flaky networks
        'retries': 3,
        'fragment_retries': 3,
        # Helps speed on DASH/HLS without going crazy
        'concurrent_fragment_downloads': 4,
    }

    is_youtube = bool(re.search(URL_PATTERNS['youtube'], url))
    is_instagram = bool(re.search(URL_PATTERNS['instagram'], url))

    # YouTube: prefer H.264/AAC MP4 to avoid iOS Telegram "static image with audio".
    if is_youtube and 'format' not in ydl_opts and not (custom_opts and 'format' in custom_opts):
        ydl_opts['format'] = 'bv*[ext=mp4][vcodec^=avc1]+ba[ext=m4a]/b[ext=mp4]/b'
        ydl_opts['merge_output_format'] = 'mp4'
        ydl_opts['remuxvideo'] = 'mp4'

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
        # Use .exe only on Windows; in Docker/Linux prefer system ffmpeg
        import platform as _plat
        if _plat.system().lower().startswith("win") and os.path.exists(local_ffmpeg):
            ydl_opts["ffmpeg_location"] = local_ffmpeg
        else:
            system_ffmpeg = shutil.which("ffmpeg")
            if system_ffmpeg:
                # yt-dlp accepts either the binary path or the directory
                ydl_opts["ffmpeg_location"] = os.path.dirname(system_ffmpeg) or system_ffmpeg
    except Exception:
        pass

    # TikTok Photos: encourage extractor to download the carousel items.
    if url and re.search(URL_PATTERNS.get('tiktok', r'$^'), url) and "/photo/" in url and 'format' not in ydl_opts:
        ydl_opts['format'] = 'best'
        # Try Android-like extractor settings (helps carousel extraction)
        ydl_opts['http_headers'] = {
            'User-Agent': 'com.zhiliaoapp.musically/2022600030 (Linux; U; Android 7.1.2; es_ES; SM-G988N; Build/NRD90M; Cronet/41.0.2272.118)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        }
        ydl_opts['extractor_args'] = {
            'tiktok': {
                'api_hostname': 'api16-normal-c-useast1a.tiktokv.com',
                'app_version': '20.2.2',
                'manifest_app_version': '2022600030',
            }
        }
        ydl_opts['socket_timeout'] = max(int(ydl_opts.get('socket_timeout') or 0), 30)

    if cookie_path:
        ydl_opts['cookiefile'] = cookie_path

    if custom_opts:
        ydl_opts.update(custom_opts)

    meta = {}
    error = None
    files = []

    # Base attempts: retry with fallback formats for cases where merging is required
    base_attempts = [
        dict(ydl_opts),
        {**ydl_opts, 'format': 'best[ext=mp4]/best'},
        {**ydl_opts, 'format': 'best'},
    ]

    attempts = base_attempts

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

    def _find_ffmpeg() -> str | None:
        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            installs_dir = os.path.join(base_dir, "core", "installs")
            local_ffmpeg = os.path.join(installs_dir, "ffmpeg.exe")
            if os.path.exists(local_ffmpeg):
                return local_ffmpeg
        except Exception:
            pass
        return shutil.which("ffmpeg")

    def _probe_video_stream(video_path: str) -> dict:
        ffprobe = _find_ffprobe()
        if not ffprobe:
            return {}
        try:
            args = [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name,avg_frame_rate,nb_frames",
                "-of",
                "json",
                video_path,
            ]
            completed = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
            if completed.returncode != 0:
                return {}
            data = json.loads((completed.stdout or b"{}").decode("utf-8", errors="ignore") or "{}")
            streams = data.get("streams") or []
            return (streams[0] or {}) if streams else {}
        except Exception:
            return {}

    def _ensure_ios_playable_mp4(video_path: str) -> str:
        """If mp4 uses AV1/VP9 etc., re-encode to H.264/AAC for iOS clients."""
        if not video_path or not os.path.exists(video_path):
            return video_path

        stream = _probe_video_stream(video_path)
        codec = (stream.get("codec_name") or "").lower().strip()

        # iOS Telegram often fails to decode AV1/VP9; it can look like a static image with audio.
        if codec in ("av1", "av01", "vp9", "vp09", "vp8"):
            ffmpeg = _find_ffmpeg()
            if not ffmpeg:
                return video_path

            tmp_out = os.path.splitext(video_path)[0] + "_h264.mp4"
            args = [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                video_path,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                tmp_out,
            ]
            completed = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False)
            if completed.returncode == 0 and os.path.exists(tmp_out) and os.path.getsize(tmp_out) > 0:
                try:
                    os.replace(tmp_out, video_path)
                except Exception:
                    return tmp_out
            else:
                try:
                    if os.path.exists(tmp_out):
                        os.remove(tmp_out)
                except Exception:
                    pass
        return video_path

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

    # TikTok: normalize common private/blocked/deleted errors.
    if error and original_url and re.search(URL_PATTERNS.get('tiktok', r'$^'), original_url):
        lower = str(error).lower()
        if any(s in lower for s in ("private", "unavailable", "not available", "not found", "removed", "deleted", "forbidden", "403", "ip address is blocked", "blocked from accessing")):
            error = "Video unavailable"

        # TikTok Photos: yt-dlp may not support /photo/ on some environments.
        if "unsupported url" in lower:
            try:
                from services.platforms.TikTokDownloader.tiktok_strategy import TikTokStrategy

                strategy = TikTokStrategy(original_url)
                s_files, s_folder, s_error, s_meta = await strategy.download()
                if s_files:
                    return s_files, s_folder, None, s_meta or {}
                if s_error and str(s_error).strip().lower() in ("video unavailable", "api busy (too many requests)"):
                    return [], s_folder, "Video unavailable", s_meta or {}
            except Exception:
                pass
    
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

    # Instagram/YouTube: ensure the resulting mp4 is iOS-playable (avoid AV1/VP9).
    if (is_instagram or is_youtube) and not error:
        video_candidates = [f for f in files if f.lower().endswith(".mp4")]
        for vp in video_candidates[:1]:
            fixed_path = _ensure_ios_playable_mp4(vp)
            if fixed_path != vp:
                # Update list if we had to write to a different file path.
                try:
                    files = [fixed_path if f == vp else f for f in files]
                except Exception:
                    pass

    return files, save_path, error, meta