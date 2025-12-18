# -*- coding: utf-8 -*-
import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# 1. Paths
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

if not ENV_PATH.exists():
    print("[ERROR] .env file not found: " + str(ENV_PATH))
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
        
        self.USE_LOCAL_SERVER = os.getenv("USE_LOCAL_SERVER", "False").lower() in ("true", "1", "yes")
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