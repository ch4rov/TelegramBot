# -*- coding: utf-8 -*-
import sys
import os
import time
import logging
import re
import datetime
import asyncio
import subprocess
import shutil
import settings
from aiogram import Router, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from handlers.admin.filters import AdminFilter
from services.database.repo import get_all_users
from services.database.backup import send_db_backup

logger = logging.getLogger(__name__)
router = Router()
router.message.filter(AdminFilter())

_UPDATE_PENDING: dict[int, dict] = {}


def _is_running_in_docker() -> bool:
    # Common, cheap checks
    try:
        if os.path.exists("/.dockerenv"):
            return True
    except Exception:
        pass
    try:
        cgroup = "/proc/1/cgroup"
        if os.path.exists(cgroup):
            with open(cgroup, "r", encoding="utf-8", errors="ignore") as f:
                txt = f.read().lower()
            if "docker" in txt or "containerd" in txt or "kubepods" in txt:
                return True
    except Exception:
        pass
    return False


def _docker_update_instructions(repo_hint: str | None = None) -> str:
    repo_hint = repo_hint or "<path-to-TelegramBot>"
    # Keep it short and copy-pastable for admins.
    return (
        "⚠️ /update inside Docker cannot pull from git (usually .git is not in the image).\n\n"
        "Update on the host where the repo and docker-compose.yml live:\n"
        f"<code>cd {repo_hint}</code>\n"
        "<code>git pull</code>\n"
        "<code>docker compose up -d --build --force-recreate</code>\n"
        "\nThen check logs:\n"
        "<code>docker compose logs -f --tail=200 telegrambot</code>"
    )


async def _run_git(args: list[str], cwd: str) -> tuple[int, str, str]:
    def _sync():
        try:
            p = subprocess.run(
                ["git", *args],
                cwd=cwd,
                capture_output=True,
                text=True,
                shell=False,
            )
            return p.returncode, (p.stdout or ""), (p.stderr or "")
        except Exception as e:
            return -1, "", str(e)

    return await asyncio.to_thread(_sync)


def _repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


# Время запуска бота
BOT_START_TIME = time.time()
BOT_COMMAND_COUNT = 0

@router.message(Command("status"))
async def cmd_status(message: types.Message):
    """Bot status and health check command"""
    try:
        global BOT_COMMAND_COUNT
        
        users = await get_all_users()
        count = len(users)
        active = sum(1 for u in users if u.is_active)
        banned = sum(1 for u in users if u.is_banned)
        
        # Calculate uptime
        uptime_seconds = time.time() - BOT_START_TIME
        uptime_hours = uptime_seconds / 3600
        uptime_days = uptime_hours / 24
        
        # Ping calculation
        start_ping = time.time()
        # Simulate a small operation
        await get_all_users()
        ping = (time.time() - start_ping) * 1000  # in milliseconds
        
        # Count temp files (cache)
        cache_count = 0
        if os.path.exists("tempfiles"):
            cache_count = len([f for f in os.listdir("tempfiles") if os.path.isfile(os.path.join("tempfiles", f))])
        
        # Format uptime
        if uptime_days >= 1:
            uptime_str = f"{int(uptime_days)}d {int(uptime_hours % 24)}h"
        else:
            uptime_str = f"{int(uptime_hours)}h {int((uptime_seconds % 3600) / 60)}m"

        text = (
            "🤖 Bot Status\n"
            + ("═" * 25)
            + "\n\n"
            + f"⏱ Ping: {ping:.2f}ms\n"
            + f"⏰ Uptime: {uptime_str}\n"
            + f"📊 Commands processed: {BOT_COMMAND_COUNT}\n\n"
            + f"👥 Users: {count}\n"
            + f"✅ Active: {active}\n"
            + f"🚫 Banned: {banned}\n\n"
            + f"💾 Cache files: {cache_count}\n"
            + f"🐍 Python: {sys.version.split()[0]}"
        )
        await message.reply(text, disable_notification=True)
        logger.info(f"Admin {message.from_user.id} used /status")
    except Exception as e:
        logger.error(f"Error in /status: {e}")
        await message.reply("Error getting bot status", disable_notification=True)


@router.message(Command("cmd"))
async def cmd_cmd(message: types.Message):
    """List all bot commands known to settings.BOT_COMMANDS_LIST (including hidden)."""
    try:
        items = list(getattr(settings, "BOT_COMMANDS_LIST", []) or [])

        # Show only commands that work without required arguments.
        # (Commands like /ban require an argument, so they are excluded to stay "click-to-send" friendly.)
        skip_requires_args = {"ban", "unban", "answer", "edituser"}
        # In Docker, /update cannot work inside the container; hide it from the tappable list.
        if _is_running_in_docker():
            skip_requires_args.add("update")
        items = [x for x in items if x and str(x[0]) not in skip_requires_args]

        user_cmds = [x for x in items if len(x) >= 5 and x[3] == "user"]
        admin_cmds = [x for x in items if len(x) >= 5 and x[3] == "admin"]

        def _fmt(it):
            name, en, ru, who, show = it[:5]
            menu = " ✅" if show else ""
            # No <code> wrapper so Telegram keeps it as a tappable /command.
            return f"/{name}{menu} — {ru} / {en}"

        lines = ["<b>Commands</b>"]
        if user_cmds:
            lines.append("\n<b>User</b>")
            lines.extend(_fmt(it) for it in user_cmds)
        if admin_cmds:
            lines.append("\n<b>Admin</b>")
            lines.extend(_fmt(it) for it in admin_cmds)

        lines.append("\n✅ = shown in menu")

        await message.reply("\n".join(lines), disable_notification=True, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error in /cmd: {e}")
        await message.reply("Error building command list", disable_notification=True)


def parse_time_to_seconds(time_str: str) -> int:
    """Парсит строку времени типа '5m', '1h', '1d' в секунды"""
    match = re.match(r"^(\d+)([smhd])$", time_str.lower().strip())
    if not match:
        return None
    
    value, unit = match.groups()
    value = int(value)
    
    multipliers = {
        's': 1,
        'm': 60,
        'h': 3600,
        'd': 86400
    }
    
    return value * multipliers.get(unit, 1)


_TEMPFILES_DIR = "tempfiles"
_TEMPFILES_PRESERVE_TOP = {"_inline_placeholders"}


def _is_in_preserved_tempfiles_dir(path: str) -> bool:
    """Returns True if path is inside a preserved top-level dir under tempfiles."""
    try:
        rel = os.path.relpath(path, _TEMPFILES_DIR)
        rel_norm = rel.replace("\\", "/")
        top = rel_norm.split("/", 1)[0]
        return top in _TEMPFILES_PRESERVE_TOP
    except Exception:
        return False


def _clear_tempfiles_all() -> int:
    """Delete everything in tempfiles except preserved dirs. Returns deleted file count."""
    deleted = 0
    if not os.path.exists(_TEMPFILES_DIR):
        return 0

    import shutil

    for name in os.listdir(_TEMPFILES_DIR):
        if name in _TEMPFILES_PRESERVE_TOP:
            continue
        p = os.path.join(_TEMPFILES_DIR, name)
        try:
            if os.path.isfile(p):
                os.remove(p)
                deleted += 1
            elif os.path.isdir(p):
                # Count files inside for reporting (best-effort)
                try:
                    for root, _, files in os.walk(p):
                        deleted += len(files)
                except Exception:
                    pass
                shutil.rmtree(p, ignore_errors=True)
        except Exception:
            pass

    # Ensure base dir exists
    try:
        os.makedirs(_TEMPFILES_DIR, exist_ok=True)
        for keep in _TEMPFILES_PRESERVE_TOP:
            os.makedirs(os.path.join(_TEMPFILES_DIR, keep), exist_ok=True)
    except Exception:
        pass
    return deleted


def _clear_tempfiles_older_than(seconds: int) -> int:
    """Delete files under tempfiles older than seconds (recursive), preserving placeholder dir."""
    deleted = 0
    if not seconds or seconds <= 0:
        return 0
    if not os.path.exists(_TEMPFILES_DIR):
        return 0

    now = time.time()

    # Remove old files
    for root, _, files in os.walk(_TEMPFILES_DIR):
        if _is_in_preserved_tempfiles_dir(root):
            continue
        for filename in files:
            fp = os.path.join(root, filename)
            try:
                if _is_in_preserved_tempfiles_dir(fp):
                    continue
                file_age = now - os.path.getmtime(fp)
                if file_age > seconds:
                    os.remove(fp)
                    deleted += 1
            except Exception:
                pass

    # Prune empty directories (bottom-up), but never remove preserved tops
    try:
        for root, dirs, _ in os.walk(_TEMPFILES_DIR, topdown=False):
            for d in dirs:
                dp = os.path.join(root, d)
                if _is_in_preserved_tempfiles_dir(dp):
                    continue
                try:
                    if os.path.isdir(dp) and not os.listdir(dp):
                        os.rmdir(dp)
                except Exception:
                    pass
    except Exception:
        pass

    return deleted

@router.message(Command("clearcache"))
async def cmd_clearcache(message: types.Message, command: CommandObject):
    """Invalidate (bypass) DB media cache bindings.

    This does NOT delete rows from media_cache (so /edituser history stays available).
    It only makes the bot ignore cached URL→file_id bindings until the URL is downloaded again.

    Usage: /clearcache [5m|1h|1d|all]
    """
    try:
        if not command.args:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="5 минут", callback_data="cache_5m"),
                    InlineKeyboardButton(text="1 час", callback_data="cache_1h"),
                ],
                [
                    InlineKeyboardButton(text="1 день", callback_data="cache_1d"),
                    InlineKeyboardButton(text="Весь кеш", callback_data="cache_all"),
                ]
            ])
            await message.answer("Выберите, какой кеш URL→file_id сбросить:", reply_markup=kb, disable_notification=True)
            return
        
        time_arg = command.args.strip()
        
        if time_arg == "all":
            from services.database.repo import bypass_media_cache_all
            targeted = await bypass_media_cache_all()
            await message.answer(f"✅ DB кеш сброшен (помечено записей: {targeted})", disable_notification=True)
            logger.info(f"Admin {message.from_user.id} bypassed all DB media cache (targeted {targeted})")
        else:
            seconds = parse_time_to_seconds(time_arg)
            if not seconds:
                await message.answer("❌ Неверный формат времени. Используйте: 5m, 1h, 1d или all", disable_notification=True)
                return

            from services.database.repo import bypass_media_cache_recent
            targeted = await bypass_media_cache_recent(int(seconds))
            await message.answer(f"✅ DB кеш сброшен (помечено записей: {targeted})", disable_notification=True)
            logger.info(f"Admin {message.from_user.id} bypassed DB media cache recent window={time_arg} (targeted {targeted})")
    except Exception as e:
        logger.error(f"Error in /clearcache: {e}")
        await message.answer("❌ Ошибка при удалении кеша", disable_notification=True)

@router.callback_query(F.data.startswith("cache_"))
async def handle_cache_button(query: types.CallbackQuery):
    """Обработчик кнопок очистки кеша"""
    try:
        action = query.data.replace("cache_", "")
        
        if action == "all":
            from services.database.repo import bypass_media_cache_all
            targeted = await bypass_media_cache_all()
            await query.answer(f"✅ DB кеш сброшен (записей: {targeted})", show_alert=True)
            logger.info(f"Admin {query.from_user.id} bypassed all DB media cache via button (targeted {targeted})")
        else:
            seconds = parse_time_to_seconds(action)
            if seconds:
                from services.database.repo import bypass_media_cache_recent
                targeted = await bypass_media_cache_recent(int(seconds))
                await query.answer(f"✅ DB кеш сброшен (записей: {targeted})", show_alert=True)
                logger.info(f"Admin {query.from_user.id} bypassed DB media cache via button window={action} (targeted {targeted})")
        
        await query.message.delete()
    except Exception as e:
        logger.error(f"Error in cache callback: {e}")
        await query.answer("❌ Ошибка", show_alert=True)


@router.message(Command("savedb"))
async def cmd_savedb(message: types.Message):
    """Send DB backup to technical chat (TECH_CHAT_ID)."""
    ok = await send_db_backup(message.bot, caption=f"💾 DB backup (by {message.from_user.id})")
    if ok:
        await message.answer("✅ Backup sent to tech chat", disable_notification=True)
    else:
        await message.answer("❌ Backup failed (check TECH_CHAT_ID and DB settings)", disable_notification=True)


@router.message(Command("update"))
async def cmd_update(message: types.Message):
    """Pull latest code from GitHub and restart (admin only)."""
    repo = _repo_root()

    # If running inside Docker, disable /update (cannot pull inside image without .git and docker engine access).
    if _is_running_in_docker():
        repo_hint = os.getenv("UPDATE_REPO_HINT", "/path/to/TelegramBot").strip() or "/path/to/TelegramBot"
        await message.answer(_docker_update_instructions(repo_hint=repo_hint), parse_mode="HTML")
        return

    # Basic git availability/worktree checks
    rc, out, err = await _run_git(["rev-parse", "--is-inside-work-tree"], cwd=repo)
    if rc != 0 or "true" not in (out or "").lower():
        # In Docker builds we often exclude .git; provide the correct update flow.
        if _is_running_in_docker() or os.path.exists(os.path.join(repo, "docker-compose.yml")):
            repo_hint = os.getenv("UPDATE_REPO_HINT", "/path/to/TelegramBot").strip() or "/path/to/TelegramBot"
            await message.answer(_docker_update_instructions(repo_hint=repo_hint), parse_mode="HTML")
            return
        await message.answer("❌ Not a git repository (cannot update).")
        return

    # STABLE should not have local diffs; enforce a stable git view.
    # 1) Ignore permission/filemode noise (common on servers)
    await _run_git(["config", "core.filemode", "false"], cwd=repo)

    # 2) Only block on tracked diffs; untracked runtime files should not block updates
    rc, out, err = await _run_git(["status", "--porcelain", "--untracked-files=no"], cwd=repo)
    if rc != 0:
        await message.answer(f"❌ Git status failed: {err or out}")
        return

    # If tracked files are dirty, we'll force reset/clean during confirm step.
    tracked_dirty = bool((out or "").strip())

    rc, branch, err = await _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo)
    branch = (branch or "").strip() or "main"

    # Fetch and check if behind upstream
    await message.answer("⏳ Checking for updates…", disable_notification=True)
    rc, out, err = await _run_git(["fetch", "--all", "--prune"], cwd=repo)
    if rc != 0:
        await message.answer(f"❌ Git fetch failed: {err or out}")
        return

    # Count commits behind upstream
    rc, behind, err = await _run_git(["rev-list", "--count", "HEAD..@{u}"], cwd=repo)
    behind_s = (behind or "").strip()
    if rc != 0:
        await message.answer("❌ No upstream tracking branch. Set it: git branch --set-upstream-to origin/" + branch)
        return

    try:
        behind_n = int(behind_s)
    except Exception:
        behind_n = 0

    if behind_n <= 0:
        await message.answer("✅ Already up to date.")
        return

    # Show confirmation
    rc, local_sha, _ = await _run_git(["rev-parse", "--short", "HEAD"], cwd=repo)
    local_sha = (local_sha or "").strip()
    rc, remote_sha, _ = await _run_git(["rev-parse", "--short", "@{u}"], cwd=repo)
    remote_sha = (remote_sha or "").strip()

    _UPDATE_PENDING[message.from_user.id] = {"repo": repo, "branch": branch, "tracked_dirty": tracked_dirty}

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Обновить и перезапустить", callback_data="upd:confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="upd:cancel"),
        ]
    ])
    await message.answer(
        f"🔄 Updates available: <b>{behind_n}</b>\n"
        f"<b>Branch:</b> <code>{branch}</code>\n"
        f"<b>Local:</b> <code>{local_sha}</code> → <b>Remote:</b> <code>{remote_sha}</code>\n\n"
        + ("⚠️ Local tracked changes will be discarded.\n" if tracked_dirty else "")
        + "Apply update?",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("upd:"))
async def cb_update(query: types.CallbackQuery):
    admin_id = query.from_user.id
    action = (query.data or "").split(":", 1)[1] if ":" in (query.data or "") else ""

    pending = _UPDATE_PENDING.get(admin_id)
    if not pending:
        await query.answer("No pending update", show_alert=True)
        return

    if action == "cancel":
        _UPDATE_PENDING.pop(admin_id, None)
        await query.answer("Cancelled")
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    if action != "confirm":
        await query.answer("Unknown action", show_alert=True)
        return

    repo = pending["repo"]
    tracked_dirty = bool(pending.get("tracked_dirty"))
    _UPDATE_PENDING.pop(admin_id, None)

    await query.answer("Updating…")
    try:
        await query.message.edit_text("⏳ Pulling latest code…", reply_markup=None)
    except Exception:
        pass

    # Force-clean worktree before pull (STABLE must stay clean)
    if tracked_dirty:
        await _run_git(["reset", "--hard", "HEAD"], cwd=repo)

    # Remove untracked files (ignored files stay intact)
    await _run_git(["clean", "-fd"], cwd=repo)

    rc, out, err = await _run_git(["pull", "--ff-only"], cwd=repo)
    if rc != 0:
        msg = (err or out or "").strip()
        if len(msg) > 3500:
            msg = msg[:3500] + "…"
        try:
            await query.message.edit_text(f"❌ Git pull failed:\n<code>{msg}</code>")
        except Exception:
            pass
        return

    try:
        await query.message.edit_text("✅ Updated. Restarting…")
    except Exception:
        pass

    # Hard-exit so run.py can restart
    await asyncio.sleep(0.5)
    os._exit(0)
