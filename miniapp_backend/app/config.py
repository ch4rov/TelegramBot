import os


def _csv_ints(raw: str) -> list[int]:
    items = []
    for part in (raw or "").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            items.append(int(part))
    return items


BOT_TOKEN = (os.getenv("BOT_TOKEN") or os.getenv("TEST_BOT_TOKEN") or "").strip().strip('"').strip("'").strip()
DB_PATH = (os.getenv("DB_PATH") or "/data/bot.db").strip()
ADMIN_IDS = _csv_ints(os.getenv("ADMIN_IDS") or os.getenv("ADMIN_ID") or "")
IS_TEST_ENV = (os.getenv("IS_TEST_ENV") or "").strip().lower() in ("true", "1", "yes")

if IS_TEST_ENV:
    BOT_TOKEN = (os.getenv("TEST_BOT_TOKEN") or os.getenv("BOT_TOKEN") or "").strip().strip('"').strip("'").strip()
    PUBLIC_URL = (
        os.getenv("TEST_MINIAPP_PUBLIC_URL")
        or os.getenv("MINIAPP_PUBLIC_URL")
        or os.getenv("TEST_PUBLIC_BASE_URL")
        or os.getenv("PUBLIC_BASE_URL")
        or ""
    ).strip().rstrip("/")
else:
    BOT_TOKEN = (os.getenv("BOT_TOKEN") or os.getenv("TEST_BOT_TOKEN") or "").strip().strip('"').strip("'").strip()
    PUBLIC_URL = (
        os.getenv("MINIAPP_PUBLIC_URL")
        or os.getenv("PUBLIC_BASE_URL")
        or ""
    ).strip().rstrip("/")

LOG_PATH = (os.getenv("BOT_LOG_PATH") or "bot_actions.log").strip()
