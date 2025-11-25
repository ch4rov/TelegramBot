import os
import shutil
import time
import asyncio
import logging
import settings # Берем настройки отсюда

# Структура кэша: { url: {"path": folder_path, "time": timestamp, "files": [list_of_files]} }
CACHE_STORAGE = {}

logging.basicConfig(level=logging.INFO)

async def get_cached_content(url: str):
    if url in CACHE_STORAGE:
        entry = CACHE_STORAGE[url]
        # Используем переменную из settings
        if time.time() - entry["time"] < settings.CACHE_TTL:
            if os.path.exists(entry["path"]):
                logging.info(f"✅ CACHE HIT: {url}")
                return entry["files"], entry["path"]
            else:
                del CACHE_STORAGE[url]
    return None, None

async def add_to_cache(url: str, folder_path: str, files: list):
    CACHE_STORAGE[url] = {
        "path": folder_path,
        "time": time.time(),
        "files": files
    }
    logging.info(f"💾 CACHE ADDED: {url} (TTL: {settings.CACHE_TTL}s)")

async def cache_cleaner_task():
    while True:
        try:
            await asyncio.sleep(60)
            current_time = time.time()
            to_delete = []

            for url, entry in CACHE_STORAGE.items():
                if current_time - entry["time"] > settings.CACHE_TTL:
                    to_delete.append(url)

            for url in to_delete:
                entry = CACHE_STORAGE[url]
                folder = entry["path"]
                if os.path.exists(folder):
                    try:
                        shutil.rmtree(folder, ignore_errors=True)
                        logging.info(f"🗑️ CACHE CLEAN: Удалена папка {folder}")
                    except Exception as e:
                        logging.error(f"CACHE ERROR: {e}")
                
                del CACHE_STORAGE[url]

        except Exception as e:
            logging.error(f"CRITICAL CACHE LOOP ERROR: {e}")
            await asyncio.sleep(60)

loop = asyncio.get_event_loop()
loop.create_task(cache_cleaner_task())