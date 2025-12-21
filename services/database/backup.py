from __future__ import annotations

import asyncio
import datetime as _dt
import logging
import os
import sqlite3
import tempfile
import zipfile

from aiogram.types import FSInputFile

logger = logging.getLogger(__name__)


def _repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def get_tech_chat_id() -> int | None:
    raw = (os.getenv("TECH_CHAT_ID") or "").strip()
    if raw and raw.lstrip("-").isdigit():
        try:
            return int(raw)
        except Exception:
            return None
    return None


def get_sqlite_db_path() -> str | None:
    # Prefer config.DB_URL (sqlite+aiosqlite:////path)
    try:
        from core.config import config

        db_url = getattr(config, "DB_URL", "") or ""
        if db_url.startswith("sqlite+") and ":///" in db_url:
            path = db_url.split(":///", 1)[1].strip()
            if path:
                return path
    except Exception:
        pass

    # Fallback to DB_PATH env
    try:
        db_path = (os.getenv("DB_PATH") or "").strip()
        if db_path:
            return db_path
    except Exception:
        pass

    return None


def _resolve_db_path(db_path: str) -> str:
    if os.path.isabs(db_path):
        return db_path
    return os.path.join(_repo_root(), db_path)


def _sqlite_backup(src_db_path: str, dst_db_path: str) -> None:
    """Create a consistent sqlite backup even while DB is in use."""
    src_db_path = _resolve_db_path(src_db_path)

    os.makedirs(os.path.dirname(dst_db_path), exist_ok=True)

    # Ensure destination doesn't exist
    try:
        if os.path.exists(dst_db_path):
            os.remove(dst_db_path)
    except Exception:
        pass

    src = sqlite3.connect(src_db_path)
    try:
        dst = sqlite3.connect(dst_db_path)
        try:
            src.backup(dst)
            dst.commit()
        finally:
            dst.close()
    finally:
        src.close()


def _zip_one_file(src_path: str, zip_path: str, arcname: str) -> None:
    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
    try:
        if os.path.exists(zip_path):
            os.remove(zip_path)
    except Exception:
        pass

    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(src_path, arcname=arcname)


async def send_db_backup(bot, caption: str | None = None) -> bool:
    """Create an archived sqlite backup and send to TECH_CHAT_ID."""
    tech_chat_id = get_tech_chat_id()
    if not tech_chat_id:
        return False

    db_path = get_sqlite_db_path()
    if not db_path:
        return False

    resolved = _resolve_db_path(db_path)
    if not os.path.exists(resolved):
        return False

    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")

    with tempfile.TemporaryDirectory(prefix="tgbot_db_backup_") as tmp:
        backup_db = os.path.join(tmp, f"bot_{ts}.db")
        backup_zip = os.path.join(tmp, f"db_backup_{ts}.zip")
        try:
            await asyncio.to_thread(_sqlite_backup, db_path, backup_db)
            await asyncio.to_thread(_zip_one_file, backup_db, backup_zip, arcname=os.path.basename(resolved))

            await bot.send_document(
                tech_chat_id,
                FSInputFile(backup_zip),
                caption=caption or "💾 DB backup",
                disable_notification=True,
            )
            return True
        except Exception:
            logger.exception("Failed to send DB backup")
            return False


async def run_periodic_db_backup(bot) -> None:
    """Run a daily DB backup once per 24h at a fixed local time.

    Behavior:
    - Sends backup only once per day (tracked in DB system_settings).
    - Default schedule: 04:00 local time.
    - If the bot starts after today's scheduled time and today's backup wasn't sent yet,
      it will run shortly after startup (instead of waiting a full day).

    Env:
    - TECH_CHAT_ID must be set.
    - DB_BACKUP_DAILY_AT (default: 04:00)
    - DB_BACKUP_RUN_ON_START (default: 0)  # legacy/manual override
    """

    from datetime import timedelta

    try:
        from services.database.repo import get_system_value, set_system_value
    except Exception:
        get_system_value = None
        set_system_value = None

    key_last_day = "db_backup_last_day"  # YYYY-MM-DD

    def _parse_hhmm(raw: str) -> tuple[int, int]:
        try:
            raw = (raw or "").strip()
            if not raw:
                return 4, 0
            parts = raw.split(":")
            if len(parts) != 2:
                return 4, 0
            h = int(parts[0])
            m = int(parts[1])
            if not (0 <= h <= 23 and 0 <= m <= 59):
                return 4, 0
            return h, m
        except Exception:
            return 4, 0

    daily_at = os.getenv("DB_BACKUP_DAILY_AT") or "04:00"
    hour, minute = _parse_hhmm(daily_at)

    run_on_start = (os.getenv("DB_BACKUP_RUN_ON_START") or "0").strip().lower() not in ("0", "false", "no", "off")

    async def _mark_sent(day: str) -> None:
        if set_system_value:
            try:
                await set_system_value(key_last_day, day)
            except Exception:
                pass

    async def _already_sent(day: str) -> bool:
        if not get_system_value:
            return False
        try:
            return (await get_system_value(key_last_day)) == day
        except Exception:
            return False

    async def _try_send_if_due(now: _dt.datetime) -> bool:
        today = now.strftime("%Y-%m-%d")
        scheduled_today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now < scheduled_today and not run_on_start:
            return False
        if await _already_sent(today):
            return False

        ok = await send_db_backup(bot, caption="💾 DB backup (daily)")
        logger.info("Daily DB backup ok=%s", ok)
        if ok:
            await _mark_sent(today)
        return ok

    # On startup: run if it's due (or if explicitly requested via DB_BACKUP_RUN_ON_START).
    try:
        await _try_send_if_due(_dt.datetime.now())
    except Exception:
        logger.exception("Daily DB backup (startup) failed")

    while True:
        now = _dt.datetime.now()
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= now:
            next_run = next_run + timedelta(days=1)

        sleep_s = max(30.0, (next_run - now).total_seconds())
        await asyncio.sleep(sleep_s)

        try:
            ok = await _try_send_if_due(_dt.datetime.now())
            # If sending failed, retry in 1 hour (keeps daily guarantee without spamming).
            if not ok:
                await asyncio.sleep(3600)
        except Exception:
            logger.exception("Daily DB backup failed")
            await asyncio.sleep(3600)
