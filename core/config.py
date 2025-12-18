# -*- coding: utf-8 -*-
import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Not a secret; used only for redirect message in test mode
DEFAULT_PROD_BOT_USERNAME = "ch4rov_bot"

# 1. Paths
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

if not ENV_PATH.exists():
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
"""
    try:
        ENV_PATH.write_text(template, encoding="utf-8")
        print("[CONFIG] Created missing .env template: " + str(ENV_PATH))
        print("[CONFIG] Please set TEST_BOT_TOKEN or BOT_TOKEN and restart.")
    except Exception as e:
        print("[ERROR] .env file not found and could not be created: " + str(ENV_PATH))
        print("[ERROR] " + str(e))
    sys.exit(1)

load_dotenv(dotenv_path=ENV_PATH)

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
            # SQLite (default)
            db_path = os.getenv("DB_PATH", str(BASE_DIR / "bot.db"))
            self.DB_URL = f"sqlite+aiosqlite:///{db_path}"

config = Settings()