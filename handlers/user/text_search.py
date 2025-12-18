# -*- coding: utf-8 -*-
import asyncio
import html
import logging
import os
import shutil

from aiogram import Router, F, types
from aiogram.enums import ChatAction
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

from services.search_service import search_youtube
from services.platforms.platform_manager import download_content
from services.odesli_service import get_links_by_url
from handlers.search_handler import make_caption

logger = logging.getLogger(__name__)
router = Router()


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


@router.message(F.text, ~F.text.startswith("/"), ~F.text.contains("http"))
async def yt_text_search(message: types.Message):
    # Keep it simple: only private chats
    if message.chat.type != "private":
        return

    query = (message.text or "").strip()
    if not query:
        return

    try:
        await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    except Exception:
        pass

    try:
        results = await search_youtube(query, limit=5)
    except Exception as e:
        logger.exception("YouTube search failed")
        await message.answer(f"❌ {html.escape(str(e))}")
        return

    if not results:
        await message.answer("❌ Nothing found")
        return

    buttons: list[list[InlineKeyboardButton]] = []
    for res in results[:5]:
        title = (res.get("title") or "Result").strip()
        duration = (res.get("duration") or "").strip()
        vid = res.get("id")
        if not vid:
            continue
        text = f"{title} ({duration})" if duration else title
        buttons.append([InlineKeyboardButton(text=text[:64], callback_data=f"ytpick:{vid}")])

    if not buttons:
        await message.answer("❌ Nothing found")
        return

    await message.answer(
        f"🔍 {query}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("ytpick:"))
async def yt_pick_download(cb: types.CallbackQuery):
    vid = cb.data.split(":", 1)[1]
    src_url = f"https://youtu.be/{vid}"

    status = None
    pulsar = None
    try:
        status = await cb.message.answer("⏳")
    except Exception:
        pass

    try:
        pulsar = _ActionPulsar(cb.bot, cb.message.chat.id, ChatAction.UPLOAD_DOCUMENT)
        pulsar.start()
    except Exception:
        pulsar = None

    custom_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "writethumbnail": False,
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
        await cb.message.answer(f"❌ {html.escape(str(error))}")
        if folder:
            shutil.rmtree(folder, ignore_errors=True)
        return

    try:
        target = next((f for f in files if f.lower().endswith((".mp4", ".mov"))), None)
        if not target:
            raise Exception("No video found")

        if pulsar:
            pulsar.set_action(ChatAction.UPLOAD_VIDEO)

        links_page = None
        try:
            links = await get_links_by_url(src_url)
            if links and links.get("page"):
                links_page = links["page"]
        except Exception:
            pass

        caption = make_caption(meta or {}, src_url, links_page=links_page)

        await cb.message.answer_video(
            FSInputFile(target),
            caption=caption,
            parse_mode="HTML",
            supports_streaming=True,
        )
    except Exception as e:
        await cb.message.answer(f"⚠️ {html.escape(str(e))}")
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
