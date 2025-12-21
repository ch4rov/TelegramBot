# -*- coding: utf-8 -*-
import asyncio
import logging
import time
import traceback
from typing import Any, Iterable, Optional

from core.config import config

logger = logging.getLogger(__name__)


class ErrorReporter:
    """Reports unexpected exceptions to admins with simple deduplication."""

    def __init__(self, bot, dedupe_window_s: float = 60.0):
        self._bot = bot
        self._dedupe_window_s = float(dedupe_window_s)
        self._recent: dict[str, float] = {}

    def _should_skip(self, key: str, now: float) -> bool:
        try:
            ts = self._recent.get(key)
            if ts is not None and (now - ts) <= self._dedupe_window_s:
                return True
            # prune expired entries lazily
            to_del = [k for k, v in self._recent.items() if (now - v) > self._dedupe_window_s]
            for k in to_del:
                self._recent.pop(k, None)
        except Exception:
            pass
        return False

    async def report(
        self,
        where: str,
        exc: Exception,
        user_id: Optional[int] = None,
        chat_id: Optional[int] = None,
        preview: str | None = None,
        extra: Any = None,
    ) -> None:
        now = time.time()
        key = f"{where}:{exc.__class__.__name__}:{str(exc)}"
        if self._should_skip(key, now):
            return
        self._recent[key] = now

        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        logger.error("Unhandled exception in %s: %s\n%s", where, exc, tb)

        admins: Iterable[int] = getattr(config, "ADMIN_IDS", []) or []
        if not admins:
            return

        lines = [
            "🚨 Exception",
            f"Place: {where}",
            f"Type: {exc.__class__.__name__}",
            f"Message: {exc}",
        ]
        if user_id:
            lines.append(f"User: {user_id}")
        if chat_id:
            lines.append(f"Chat: {chat_id}")
        if preview:
            lines.append(f"Preview: {preview}")
        if extra:
            try:
                lines.append(f"Extra: {extra}")
            except Exception:
                pass

        # Limit traceback length to avoid hitting Telegram message limit
        tb_snippet = (tb[:3500] + "…") if len(tb) > 3500 else tb
        lines.append("\nTraceback:\n" + tb_snippet)

        text = "\n".join(lines)
        await self._safe_broadcast(admins, text)

    async def _safe_broadcast(self, admins: Iterable[int], text: str) -> None:
        tasks = []
        for admin_id in admins:
            try:
                tasks.append(self._bot.send_message(admin_id, text))
            except Exception:
                # If scheduling fails, continue with others
                continue
        if not tasks:
            return
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception:
            pass
