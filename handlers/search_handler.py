# -*- coding: utf-8 -*-
import os
import shutil
import traceback
import html
import json
import re
import logging
import asyncio
import subprocess
from aiogram import Router, F, types
from aiogram.types import FSInputFile, InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ChatAction
from services.database.repo import (
    add_or_update_user,
    increment_request_count,
    get_cached_media,
    upsert_cached_media,
    log_user_request,
)
from services.platforms.platform_manager import download_content, is_valid_url
import settings
from services.url_cleaner import clean_url
from services.odesli_service import get_links_by_url
from core.caption_utils import wrap_tail_in_blockquote

logger = logging.getLogger(__name__)
router = Router()

CAPTION_MAX_LEN = 1024

# aiogram versions differ: not all ChatAction enums exist (e.g., UPLOAD_AUDIO)
ACTION_UPLOAD_AUDIO = getattr(ChatAction, "UPLOAD_AUDIO", ChatAction.UPLOAD_DOCUMENT)


def _is_tiktok_cookie_required(url: str, error: str) -> bool:
    try:
        u = (url or "").lower()
        e = (error or "").lower()
        if "tiktok" not in u:
            return False
        # Typical yt-dlp messages for age/region/auth-gated TikTok posts
        markers = [
            "log in for access",
            "this post may not be comfortable",
            "use --cookies",
            "cookies-from-browser",
            "for the authentication",
        ]
        return any(m in e for m in markers)
    except Exception:
        return False


def _tiktok_cookies_hint(user_lang: str | None = None) -> str:
    lang = (user_lang or "en").lower()
    if lang == "ru":
        return (
            "⚠️ TikTok: для этого видео нужны куки (ограничение по возрасту/контенту).\n"
            "Вызови /addcookies → TikTok и отправь cookies.txt (Netscape format)."
        )
    return (
        "⚠️ TikTok: this post requires cookies (age/content restriction).\n"
        "Run /addcookies → TikTok and send a cookies.txt (Netscape format)."
    )


class _ActionPulsar:
    def __init__(self, bot, chat_id: int, action: ChatAction, interval_s: float = 4.0):
        self._bot = bot
        self._chat_id = chat_id
        self._action = action
        self._interval_s = interval_s
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

    def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    def set_action(self, action: ChatAction):
        self._action = action

    async def stop(self):
        self._stop.set()
        if self._task:
            try:
                await self._task
            except Exception:
                pass

    async def _run(self):
        while not self._stop.is_set():
            try:
                await self._bot.send_chat_action(chat_id=self._chat_id, action=self._action)
            except Exception:
                pass
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval_s)
            except asyncio.TimeoutError:
                continue


def _get_ffmpeg_path() -> str:
    try:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        # base_dir -> handlers; repo root is one more up
        repo_root = os.path.abspath(os.path.join(base_dir, ".."))
        ffmpeg_path = os.path.join(repo_root, "core", "installs", "ffmpeg.exe")
        if os.path.exists(ffmpeg_path):
            return ffmpeg_path
    except Exception:
        pass
    return "ffmpeg"


def _get_ffprobe_path() -> str:
    try:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        repo_root = os.path.abspath(os.path.join(base_dir, ".."))
        ffprobe_path = os.path.join(repo_root, "core", "installs", "ffprobe.exe")
        if os.path.exists(ffprobe_path):
            return ffprobe_path
    except Exception:
        pass
    return "ffprobe"


async def _probe_video_dims(path: str) -> tuple[int | None, int | None]:
    ffprobe = _get_ffprobe_path()
    args = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        path,
    ]
    try:
        completed = await asyncio.to_thread(
            subprocess.run,
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if completed.returncode != 0:
            return None, None
        data = json.loads((completed.stdout or b"{}").decode("utf-8", errors="ignore"))
        streams = data.get("streams") or []
        if not streams:
            return None, None
        w = streams[0].get("width")
        h = streams[0].get("height")
        try:
            w = int(w) if w else None
        except Exception:
            w = None
        try:
            h = int(h) if h else None
        except Exception:
            h = None
        return w, h
    except Exception:
        return None, None


async def _extract_audio_mp3(input_path: str, output_path: str) -> bool:
    ffmpeg = _get_ffmpeg_path()
    args = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        input_path,
        "-vn",
        "-c:a",
        "libmp3lame",
        "-q:a",
        "4",
        output_path,
    ]
    try:
        completed = await asyncio.to_thread(
            subprocess.run,
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )
        return completed.returncode == 0 and os.path.exists(output_path)
    except Exception:
        return False


async def _twitch_ios_normalize(input_path: str, output_path: str) -> bool:
    ffmpeg = _get_ffmpeg_path()
    args = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        input_path,
        "-vf",
        "scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        "-metadata:s:v:0",
        "rotate=0",
        output_path,
    ]
    try:
        completed = await asyncio.to_thread(
            subprocess.run,
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )
        return completed.returncode == 0 and os.path.exists(output_path)
    except Exception:
        return False


def _is_youtube_like(meta: dict, url: str) -> bool:
    try:
        if url and re.search(r"(youtube\.com|youtu\.be|music\.youtube\.com)", url, flags=re.IGNORECASE):
            return True
        extractor = (meta or {}).get("extractor_key") or ""
        return extractor.lower().startswith("youtube")
    except Exception:
        return False


def _safe_trim_escaped_html(s: str) -> str:
    """Trim string to avoid cutting HTML entities like '&amp'."""
    try:
        amp = s.rfind("&")
        semi = s.rfind(";")
        if amp > semi:
            return s[:amp]
    except Exception:
        pass
    return s


def make_caption(meta: dict, display_url: str, links_page: str | None = None) -> str:
    title = (meta or {}).get('title') or 'Media'

    parts = []
    if _is_youtube_like(meta or {}, display_url):
        uploader = (meta or {}).get('uploader') or (meta or {}).get('channel') or (meta or {}).get('uploader_id')
        if uploader:
            parts.append(f"<b>{html.escape(str(uploader))}</b>")

    parts.append(f'<a href="{display_url}">{html.escape(str(title))}</a>')

    caption = "\n".join(parts)
    if links_page:
        caption = caption + f' | <a href="{links_page}">Links</a>'

    # Add expandable full description (Telegram HTML supports <blockquote expandable>)
    try:
        description = (meta or {}).get('description')
        if description and _is_youtube_like(meta or {}, display_url):
            description = str(description).strip()
            if description:
                # Keep a reasonable raw cap; final cap enforced below.
                description = description[:4000]
                escaped = html.escape(description)
                prefix = "\n\n<blockquote expandable>"
                suffix = "</blockquote>"
                available = CAPTION_MAX_LEN - len(caption) - len(prefix) - len(suffix)
                if available >= 50:
                    if len(escaped) > available:
                        escaped = escaped[: max(0, available - 1)]
                        escaped = _safe_trim_escaped_html(escaped).rstrip() + "…"
                    caption = caption + prefix + escaped + suffix
    except Exception:
        pass

    if len(caption) > CAPTION_MAX_LEN:
        caption = caption[:CAPTION_MAX_LEN]
        caption = _safe_trim_escaped_html(caption)
    return wrap_tail_in_blockquote(caption)


def _extract_youtube_video_id(url: str) -> str | None:
    try:
        m = re.search(r"(?:v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{6,})", url)
        return m.group(1) if m else None
    except Exception:
        return None

@router.callback_query(F.data == "delete_msg")
async def delete_msg(cb: types.CallbackQuery):
    try: await cb.message.delete()
    except: pass


@router.callback_query(F.data.startswith("music:YT:"))
async def handle_music_selection(cb: types.CallbackQuery, user_lang: str = "en"):
    video_id = cb.data.split(":", 2)[2]
    src_url = f"https://youtu.be/{video_id}"

    # Per-user cache (audio)
    try:
        cached = await get_cached_media(cb.from_user.id, src_url, "audio")
    except Exception:
        cached = None
    if cached:
        try:
            caption = make_caption({"title": cached.title or "Media"}, src_url, links_page=None)
            await cb.message.answer_audio(
                cached.file_id,
                caption=caption,
                parse_mode="HTML",
            )
            try:
                await log_user_request(
                    cb.from_user.id,
                    kind="callback",
                    input_text=cb.data,
                    url=src_url,
                    media_type="audio",
                    title=cached.title,
                    cache_hit=True,
                    cache_id=cached.id,
                )
            except Exception:
                pass
        except Exception:
            pass
        return

    status = None
    pulsar = None
    try:
        status = await cb.message.answer("⏳")
    except Exception:
        pass

    try:
        pulsar = _ActionPulsar(cb.bot, cb.message.chat.id, ACTION_UPLOAD_AUDIO)
        pulsar.start()
    except Exception:
        pulsar = None

    custom_opts = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "writethumbnail": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }

    files, folder, error, meta = await download_content(src_url, custom_opts, user_id=cb.from_user.id)
    if error:
        if pulsar:
            await pulsar.stop()
        try:
            if status:
                await status.delete()
        except Exception:
            pass
        try:
            if _is_tiktok_cookie_required(src_url, str(error)):
                await cb.message.answer(_tiktok_cookies_hint(user_lang), disable_web_page_preview=True)
            else:
                await cb.message.answer(f"❌ {html.escape(str(error))}", parse_mode="HTML")
        except Exception:
            pass
        if folder:
            shutil.rmtree(folder, ignore_errors=True)
        return

    try:
        audio_exts = (".mp3", ".m4a", ".opus", ".ogg")
        target = next((f for f in files if f.lower().endswith(audio_exts)), None)
        if not target:
            raise Exception("No audio found")

        caption = make_caption(meta or {}, src_url, links_page=None)

        thumb_path = next((f for f in files if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))), None)
        performer = (meta or {}).get("artist") or (meta or {}).get("uploader") or (meta or {}).get("channel") or None
        title = (meta or {}).get("track") or (meta or {}).get("title") or None

        if pulsar:
            pulsar.set_action(ACTION_UPLOAD_AUDIO)

        sent = None
        if thumb_path:
            sent = await cb.message.answer_audio(
                FSInputFile(target),
                caption=caption,
                parse_mode="HTML",
                performer=performer,
                title=title,
                thumbnail=FSInputFile(thumb_path),
            )
        else:
            sent = await cb.message.answer_audio(
                FSInputFile(target),
                caption=caption,
                parse_mode="HTML",
                performer=performer,
                title=title,
            )

        try:
            if sent and sent.audio:
                cache_title = (meta or {}).get("track") or (meta or {}).get("title") or title
                cache = await upsert_cached_media(cb.from_user.id, src_url, sent.audio.file_id, "audio", title=str(cache_title) if cache_title else None)
                await log_user_request(
                    cb.from_user.id,
                    kind="callback",
                    input_text=cb.data,
                    url=src_url,
                    media_type="audio",
                    title=str(cache_title) if cache_title else None,
                    cache_hit=False,
                    cache_id=cache.id,
                )
        except Exception:
            pass
    except Exception as e:
        try:
            await cb.message.answer(f"⚠️ {html.escape(str(e))}", parse_mode="HTML")
        except Exception:
            pass
    finally:
        if pulsar:
            await pulsar.stop()
        try:
            if status:
                await status.delete()
        except Exception:
            pass
        if folder and os.path.exists(folder):
            shutil.rmtree(folder, ignore_errors=True)


@router.callback_query(F.data.startswith("ytm_clip:"))
async def cb_download_ytm_clip(cb: types.CallbackQuery, user_lang: str = "en"):
    url = cb.data.split(":", 1)[1]
    src_url = clean_url(url)

    # Per-user cache (video)
    try:
        cached = await get_cached_media(cb.from_user.id, src_url, "video")
    except Exception:
        cached = None
    if cached:
        try:
            caption = make_caption({"title": cached.title or "Media"}, src_url, links_page=None)
            await cb.message.answer_video(
                cached.file_id,
                caption=caption,
                supports_streaming=True,
                parse_mode="HTML",
            )
            try:
                await log_user_request(
                    cb.from_user.id,
                    kind="callback",
                    input_text=cb.data,
                    url=src_url,
                    media_type="video",
                    title=cached.title,
                    cache_hit=True,
                    cache_id=cached.id,
                )
            except Exception:
                pass
        except Exception:
            pass
        return

    status = None
    pulsar = None
    try:
        status = await cb.message.answer("⏳")
    except Exception:
        pass

    # Pulse ChatAction while we work
    try:
        pulsar = _ActionPulsar(cb.bot, cb.message.chat.id, ChatAction.UPLOAD_DOCUMENT)
        pulsar.start()
    except Exception:
        pulsar = None

    custom_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'writethumbnail': False,
    }

    files, folder, error, meta = await download_content(src_url, custom_opts, user_id=cb.from_user.id)
    if error:
        try:
            if status:
                await status.delete()
        except Exception:
            pass
        if pulsar:
            await pulsar.stop()
        try:
            if _is_tiktok_cookie_required(src_url, str(error)):
                await cb.message.answer(_tiktok_cookies_hint(user_lang), disable_web_page_preview=True)
            else:
                await cb.message.answer(f"❌ {html.escape(error)}", parse_mode="HTML")
        except Exception:
            pass
        if folder:
            shutil.rmtree(folder, ignore_errors=True)
        return

    try:
        target = next((f for f in files if f.lower().endswith(('.mp4', '.mov'))), None)
        if not target:
            raise Exception("No video found")

        links_page = None
        try:
            links = await get_links_by_url(src_url)
            if links and links.get('page'):
                links_page = links['page']
        except Exception:
            pass

        caption = make_caption(meta or {}, src_url, links_page=links_page)

        if pulsar:
            pulsar.set_action(ChatAction.UPLOAD_VIDEO)
        width = meta.get("width") if isinstance(meta, dict) else None
        height = meta.get("height") if isinstance(meta, dict) else None
        try:
            width = int(width) if width else None
        except Exception:
            width = None
        try:
            height = int(height) if height else None
        except Exception:
            height = None

        sent = await cb.message.answer_video(
            FSInputFile(target),
            caption=caption,
            supports_streaming=True,
            parse_mode="HTML",
            width=width,
            height=height,
        )

        try:
            if sent and sent.video:
                cache_title = (meta or {}).get("title")
                cache = await upsert_cached_media(cb.from_user.id, src_url, sent.video.file_id, "video", title=str(cache_title) if cache_title else None)
                await log_user_request(
                    cb.from_user.id,
                    kind="callback",
                    input_text=cb.data,
                    url=src_url,
                    media_type="video",
                    title=str(cache_title) if cache_title else None,
                    cache_hit=False,
                    cache_id=cache.id,
                )
        except Exception:
            pass
        if pulsar:
            await pulsar.stop()
        try:
            if status:
                await status.delete()
        except Exception:
            pass

    except Exception as e:
        if pulsar:
            await pulsar.stop()
        try:
            if status:
                await status.delete()
        except Exception:
            pass
        try:
            await cb.message.answer(f"⚠️ {html.escape(str(e))}", parse_mode="HTML")
        except Exception:
            pass
    finally:
        if folder and os.path.exists(folder):
            shutil.rmtree(folder, ignore_errors=True)

# --- ОБРАБОТКА ССЫЛОК В ЧАТЕ ---
@router.message(F.text, ~F.text.startswith("/"))
async def message_handler(message: types.Message, user_lang: str = "en"):
    text = message.text.strip()
    
    if is_valid_url(text):
        status = await message.answer("⏳")

        pulsar = None
        try:
            pulsar = _ActionPulsar(message.bot, message.chat.id, ChatAction.UPLOAD_DOCUMENT)
            pulsar.start()
        except Exception:
            pulsar = None
        
        # Обновляем юзера (на всякий случай)
        await add_or_update_user(message.from_user.id, message.from_user.username, message.from_user.full_name, "")

        display_url = clean_url(text)
        src_url = display_url

        is_tiktok = "tiktok" in src_url
        is_tiktok_photo = is_tiktok and ("/photo/" in src_url)

        is_ytm = "music.youtube.com" in src_url
        is_soundcloud = "soundcloud.com" in src_url
        is_spotify = "open.spotify.com" in src_url
        is_twitch = ("twitch.tv" in src_url) or ("clips.twitch.tv" in src_url)

        wants_audio = is_ytm or is_soundcloud or is_spotify
        cache_type = "tiktok_slides" if is_tiktok_photo else ("audio" if wants_audio else "video")

        # Cache hit: send without hitting platforms
        cached = None
        try:
            cached = await get_cached_media(message.from_user.id, display_url, cache_type)
        except Exception:
            cached = None

        # TikTok short links may not contain /photo/, but we can still cache them as slides.
        if not cached and is_tiktok and cache_type != "tiktok_slides":
            try:
                cached = await get_cached_media(message.from_user.id, display_url, "tiktok_slides")
                cache_type = "tiktok_slides" if cached else cache_type
            except Exception:
                pass

        if cached:
            try:
                caption = make_caption({"title": cached.title or "Media"}, display_url, links_page=None)

                if cache_type == "video":
                    await message.answer_video(cached.file_id, caption=caption, supports_streaming=True, parse_mode="HTML")
                elif cache_type == "audio":
                    await message.answer_audio(cached.file_id, caption=caption, parse_mode="HTML")
                elif cache_type == "tiktok_slides":
                    payload = {}
                    try:
                        payload = json.loads(cached.file_id or "{}")
                    except Exception:
                        payload = {}
                    photos = payload.get("photos") or []
                    audio_id = payload.get("audio")
                    if photos:
                        for chunk_start in range(0, len(photos), 10):
                            chunk = photos[chunk_start:chunk_start + 10]
                            media = []
                            for i, fid in enumerate(chunk):
                                cap = caption if (chunk_start == 0 and i == 0) else None
                                media.append(InputMediaPhoto(media=fid, caption=cap, parse_mode="HTML"))
                            try:
                                await message.answer_media_group(media=media)
                            except Exception:
                                pass
                    if audio_id:
                        try:
                            await message.answer_audio(audio_id, caption="🎵 Sound")
                        except Exception:
                            pass

                try:
                    await log_user_request(
                        message.from_user.id,
                        kind="message_url",
                        input_text=text,
                        url=display_url,
                        media_type=cache_type,
                        title=cached.title,
                        cache_hit=True,
                        cache_id=cached.id,
                    )
                except Exception:
                    pass
            finally:
                try:
                    await status.delete()
                except Exception:
                    pass
                if pulsar:
                    await pulsar.stop()
            return

        # Pre-resolve Links only when we actually download
        links_page = None
        try:
            links = await get_links_by_url(display_url)
            if links and links.get('page'):
                links_page = links['page']
        except Exception:
            pass

        # YouTube Music / SoundCloud / Spotify should be audio-only
        if is_ytm:
            custom_opts = {
                'format': 'bestaudio/best',
                'noplaylist': True,
                'writethumbnail': True,
                'postprocessors': [
                    {
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }
                ],
            }
        elif is_soundcloud or is_spotify:
            custom_opts = {
                'format': 'bestaudio/best',
                'noplaylist': True,
                'writethumbnail': True,
                'postprocessors': [
                    {
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }
                ],
            }
        else:
            custom_opts = {
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'merge_output_format': 'mp4',
                'noplaylist': True,
            }
        
        # Передаем user_id для кук!
        files, folder, error, meta = await download_content(src_url, custom_opts, user_id=message.from_user.id)
        
        if error:
            try:
                await status.delete()
            except Exception:
                pass
            if pulsar:
                await pulsar.stop()
            try:
                if _is_tiktok_cookie_required(src_url, str(error)):
                    await message.answer(_tiktok_cookies_hint(user_lang), disable_web_page_preview=True)
                else:
                    await message.answer(f"❌ {html.escape(str(error))}", parse_mode="HTML")
            except Exception:
                pass
            if folder: shutil.rmtree(folder, ignore_errors=True)
            return

        try:
            audio_exts = ('.mp3', '.m4a', '.opus', '.ogg')
            video_exts = ('.mp4', '.mov', '.mkv', '.webm')
            image_exts = ('.jpg', '.jpeg', '.png', '.webp')

            # TikTok Photos: send carousel as albums (10 per group) + attached audio
            images = [f for f in (files or []) if isinstance(f, str) and f.lower().endswith(image_exts)]
            audio_file = next((f for f in (files or []) if isinstance(f, str) and f.lower().endswith(audio_exts)), None)
            has_video = any(isinstance(f, str) and f.lower().endswith(video_exts) for f in (files or []))

            # TikTok Photos: API may return only images (no mp4) even for vm.tiktok.com shortlinks.
            if (is_tiktok_photo or (is_tiktok and images and not has_video)):
                if not images:
                    raise Exception("No images found")

                caption = make_caption(meta or {}, display_url, links_page=links_page)

                collected_photo_ids: list[str] = []
                for chunk_start in range(0, len(images), 10):
                    chunk = images[chunk_start:chunk_start + 10]
                    media = []
                    for i, img in enumerate(chunk):
                        cap = caption if (chunk_start == 0 and i == 0) else None
                        media.append(InputMediaPhoto(media=FSInputFile(img), caption=cap, parse_mode="HTML"))

                    msgs = await message.answer_media_group(media=media)
                    for m in (msgs or []):
                        try:
                            if m.photo:
                                collected_photo_ids.append(m.photo[-1].file_id)
                        except Exception:
                            pass

                audio_file_id = None
                if audio_file:
                    if pulsar:
                        pulsar.set_action(ACTION_UPLOAD_AUDIO)
                    try:
                        a_msg = await message.answer_audio(FSInputFile(audio_file), caption="🎵 Sound")
                        if a_msg and a_msg.audio:
                            audio_file_id = a_msg.audio.file_id
                    except Exception:
                        pass

                try:
                    payload = json.dumps({"photos": collected_photo_ids, "audio": audio_file_id}, ensure_ascii=False)
                    cache_title = (meta or {}).get("title")
                    cache = await upsert_cached_media(message.from_user.id, display_url, payload, "tiktok_slides", title=str(cache_title) if cache_title else None)
                    await log_user_request(
                        message.from_user.id,
                        kind="message_url",
                        input_text=text,
                        url=display_url,
                        media_type="tiktok_slides",
                        title=str(cache_title) if cache_title else None,
                        cache_hit=False,
                        cache_id=cache.id,
                    )
                except Exception:
                    pass

                try:
                    await status.delete()
                except Exception:
                    pass
                if pulsar:
                    await pulsar.stop()
                return

            if wants_audio:
                target = next((f for f in files if f.lower().endswith(audio_exts)), None)
            else:
                target = next((f for f in files if f.lower().endswith(video_exts)), None)

            # If we want audio but didn't get a proper audio file (e.g., only mp4/webm), extract mp3.
            if wants_audio and not target:
                video_src = next((f for f in files if f.lower().endswith(video_exts)), None)
                if video_src and folder:
                    mp3_path = os.path.join(folder, "audio.mp3")
                    ok = await _extract_audio_mp3(video_src, mp3_path)
                    if ok:
                        target = mp3_path
            if not target: raise Exception("No media found")

            # Safety: don't attempt to send too large files
            try:
                if os.path.getsize(target) > settings.MAX_FILE_SIZE:
                    raise Exception("FILE_TOO_LARGE")
            except OSError:
                pass
            
            caption = make_caption(meta or {}, display_url, links_page=links_page)

            is_video_target = target.lower().endswith(video_exts)
            if is_video_target:
                if is_twitch:
                    try:
                        normalized = os.path.join(folder, "twitch_ios.mp4")
                        ok = await _twitch_ios_normalize(target, normalized)
                        if ok:
                            target = normalized
                    except Exception:
                        pass

                if pulsar:
                    pulsar.set_action(ChatAction.UPLOAD_VIDEO)

                width, height = await _probe_video_dims(target)

                sent = await message.answer_video(
                    FSInputFile(target),
                    caption=caption,
                    supports_streaming=True,
                    parse_mode="HTML",
                    width=width,
                    height=height,
                )

                try:
                    if sent and sent.video:
                        cache_title = (meta or {}).get("title")
                        cache = await upsert_cached_media(message.from_user.id, display_url, sent.video.file_id, "video", title=str(cache_title) if cache_title else None)
                        await log_user_request(
                            message.from_user.id,
                            kind="message_url",
                            input_text=text,
                            url=display_url,
                            media_type="video",
                            title=str(cache_title) if cache_title else None,
                            cache_hit=False,
                            cache_id=cache.id,
                        )
                except Exception:
                    pass
            else:
                # Optional cover
                thumb_path = next((f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))), None)

                performer = meta.get('artist') or meta.get('uploader') or meta.get('channel') or None
                title = meta.get('track') or meta.get('title') or None

                kb = None
                if is_ytm:
                    button_text = "Скачать клип" if user_lang == "ru" else "Download clip"
                    kb_builder = InlineKeyboardBuilder()
                    kb_builder.button(text=button_text, callback_data=f"ytm_clip:{src_url}")
                    kb = kb_builder.as_markup()

                if pulsar:
                    pulsar.set_action(ACTION_UPLOAD_AUDIO)

                sent = None
                if thumb_path:
                    sent = await message.answer_audio(
                        FSInputFile(target),
                        caption=caption,
                        parse_mode="HTML",
                        performer=performer,
                        title=title,
                        thumbnail=FSInputFile(thumb_path),
                        reply_markup=kb,
                    )
                else:
                    sent = await message.answer_audio(
                        FSInputFile(target),
                        caption=caption,
                        parse_mode="HTML",
                        performer=performer,
                        title=title,
                        reply_markup=kb,
                    )

                try:
                    if sent and sent.audio:
                        cache_title = (meta or {}).get("track") or (meta or {}).get("title") or title
                        cache = await upsert_cached_media(message.from_user.id, display_url, sent.audio.file_id, "audio", title=str(cache_title) if cache_title else None)
                        await log_user_request(
                            message.from_user.id,
                            kind="message_url",
                            input_text=text,
                            url=display_url,
                            media_type="audio",
                            title=str(cache_title) if cache_title else None,
                            cache_hit=False,
                            cache_id=cache.id,
                        )
                except Exception:
                    pass
            
            try: await status.delete()
            except: pass
            if pulsar:
                await pulsar.stop()
            
        except Exception as e:
            try:
                await status.delete()
            except Exception:
                pass
            if pulsar:
                await pulsar.stop()
            msg = f"⚠️ {e}"
            if str(e) == "FILE_TOO_LARGE":
                msg = (
                    "❌ Файл слишком большой для отправки в Telegram."
                    if (user_lang or "en").lower() == "ru"
                    else "❌ File is too large to send to Telegram."
                )
            try:
                await message.answer(msg)
            except Exception:
                pass
        finally:
            if folder and os.path.exists(folder): shutil.rmtree(folder, ignore_errors=True)