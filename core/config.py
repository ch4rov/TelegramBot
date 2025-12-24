# -*- coding: utf-8 -*-
import os
import sys
import logging
import re
from pathlib import Path
from dotenv import load_dotenv

# Not a secret; used only for redirect message in test mode
DEFAULT_PROD_BOT_USERNAME = "ch4rov_bot"

# 1. Paths
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

# Only load .env if it exists (Docker sets vars via environment section instead)
# If running locally without Docker, create .env template if missing
running_in_docker = os.path.exists("/.dockerenv")

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
elif not running_in_docker:
    # Only create .env template if we're NOT in Docker
    template = """# TelegramBot environment
# Fill in at least one token (TEST_BOT_TOKEN or BOT_TOKEN) before запуск.

# Use test token if enabled
IS_TEST_ENV=True

# Tokens (put your bot token here)
TEST_BOT_TOKEN=
BOT_TOKEN=

# Admins (comma-separated)
ADMIN_IDS=

# Backward-compat (some parts of the project may still read ADMIN_ID)
ADMIN_ID=

# Local server mode
USE_LOCAL_SERVER=False
LOCAL_SERVER_URL=http://127.0.0.1:8081

# Database
# DB_TYPE=sqlite|postgres
DB_TYPE=sqlite
DB_PATH=bot.db
DB_USER=
DB_PASSWORD=
DB_HOST=localhost
DB_PORT=5432
DB_NAME=telegram_bot

# Optional
TECH_CHAT_ID=
LASTFM_API_KEY=
LASTFM_SECRET=

# === OAuth (Spotify) ===
# Public base URL of your tunnel, without trailing slash.
# Example: https://YOUR_PUBLIC_HOST
PUBLIC_BASE_URL=
TEST_PUBLIC_BASE_URL=

# Local HTTP server for OAuth callbacks (the tunnel points to this)
OAUTH_HTTP_HOST=127.0.0.1
OAUTH_HTTP_PORT=8088
TEST_OAUTH_HTTP_PORT=8089

# Spotify OAuth (separate apps for test/prod are recommended)
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
TEST_SPOTIFY_CLIENT_ID=
TEST_SPOTIFY_CLIENT_SECRET=
SPOTIFY_SCOPES=user-read-currently-playing user-read-recently-played
"""
    try:
        ENV_PATH.write_text(template, encoding="utf-8")
        print("[CONFIG] Created missing .env template: " + str(ENV_PATH))
        print("[CONFIG] Please set TEST_BOT_TOKEN or BOT_TOKEN and restart.")
    except Exception as e:
        print("[ERROR] .env file not found and could not be created: " + str(ENV_PATH))
        print("[ERROR] " + str(e))
    sys.exit(1)

class Settings:
    def __init__(self):
        logger = logging.getLogger("config")
        
        # 1. Determine mode (Test or Prod)
        self.IS_TEST = os.getenv("IS_TEST_ENV", "False").lower() in ("true", "1", "yes")
        
        # 2. Choose token
        if self.IS_TEST:
            print("[CONFIG] Running in TEST mode (TEST_BOT_TOKEN)")
            raw_token = os.getenv("TEST_BOT_TOKEN", "")
        else:
            print("[CONFIG] Running in PROD mode (BOT_TOKEN)")
            raw_token = os.getenv("BOT_TOKEN", "")

        # 3. Clean token from quotes and spaces
        self.BOT_TOKEN = raw_token.strip().strip('"').strip("'")

        # 4. Validate token
        if not self.BOT_TOKEN:
            token_name = "TEST_BOT_TOKEN" if self.IS_TEST else "BOT_TOKEN"
            print("[ERROR] Variable " + token_name + " is empty or not found in .env!")
            sys.exit(1)
            
        if ":" not in self.BOT_TOKEN or not self.BOT_TOKEN.split(":")[0].isdigit():
            print("[ERROR] Token format is incorrect (missing ':' or ID is not a number).")
            sys.exit(1)

        # 5. Admin IDs
        admin_ids_str = os.getenv("ADMIN_IDS", "")
        try:
            self.ADMIN_IDS = [int(x) for x in admin_ids_str.replace(" ", "").split(",") if x]
        except ValueError:
            self.ADMIN_IDS = []

        # Optional: production bot username for redirect in test mode
        self.PROD_BOT_USERNAME = os.getenv("PROD_BOT_USERNAME", "").strip() or DEFAULT_PROD_BOT_USERNAME
        
        self.USE_LOCAL_SERVER = os.getenv("USE_LOCAL_SERVER", "False").lower() in ("true", "1", "yes")
        self.LOCAL_SERVER_URL = os.getenv("LOCAL_SERVER_URL", "http://127.0.0.1:8081").strip()
        self.DROP_PENDING_UPDATES = True

        # === OAuth callback server & provider apps ===
        # Public base URL (tunnel). Used for redirect_uri.
        public_base_url = os.getenv("TEST_PUBLIC_BASE_URL" if self.IS_TEST else "PUBLIC_BASE_URL", "").strip()
        public_base_url = public_base_url.rstrip("/")

        if self.IS_TEST and not public_base_url:
            public_base_url = self._try_read_quick_tunnel_url().rstrip("/")

        self.PUBLIC_BASE_URL = public_base_url

        default_oauth_host = "0.0.0.0" if running_in_docker else "127.0.0.1"
        self.OAUTH_HTTP_HOST = (os.getenv("OAUTH_HTTP_HOST") or default_oauth_host).strip() or default_oauth_host
        port_var = "TEST_OAUTH_HTTP_PORT" if self.IS_TEST else "OAUTH_HTTP_PORT"
        try:
            self.OAUTH_HTTP_PORT = int(os.getenv(port_var, "8089" if self.IS_TEST else "8088"))
        except Exception:
            self.OAUTH_HTTP_PORT = 8089 if self.IS_TEST else 8088

        # Spotify
        self.SPOTIFY_CLIENT_ID = (os.getenv("TEST_SPOTIFY_CLIENT_ID" if self.IS_TEST else "SPOTIFY_CLIENT_ID", "") or "").strip()
        self.SPOTIFY_CLIENT_SECRET = (os.getenv("TEST_SPOTIFY_CLIENT_SECRET" if self.IS_TEST else "SPOTIFY_CLIENT_SECRET", "") or "").strip()
        self.SPOTIFY_SCOPES = (os.getenv("SPOTIFY_SCOPES", "user-read-currently-playing user-read-recently-played") or "").strip()

        # 6. Database
        db_type = os.getenv("DB_TYPE", "sqlite").lower()
        if db_type == "postgres":
            db_user = os.getenv("DB_USER", "")
            db_pass = os.getenv("DB_PASSWORD", "")
            db_host = os.getenv("DB_HOST", "localhost")
            db_port = os.getenv("DB_PORT", "5432")
            db_name = os.getenv("DB_NAME", "telegram_bot")
            self.DB_URL = f"postgresql+asyncpg://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
        else:
            db_path = os.getenv("DB_PATH", str(BASE_DIR / "bot.db"))
            self.DB_URL = f"sqlite+aiosqlite:///{db_path}"

    def _try_read_quick_tunnel_url(self) -> str:
        candidates = ["/data/cloudflared_url.txt", "/data/cloudflared.log"]
        pattern = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.IGNORECASE)
        for path in candidates:
            try:
                if not os.path.exists(path):
                    continue
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
                m = pattern.search(text)
                if m:
                    return m.group(0)
            except Exception:
                continue
        return ""

config = Settings()