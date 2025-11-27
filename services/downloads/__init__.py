from . import tiktok, instagram, youtube, soundcloud, twitch, vk
import re
import settings

# --- ДЕБАГ-ФУНКЦИЯ ---
def is_valid_url(url: str) -> bool:
    print(f"\n🕵️ [DEBUG VALIDATION] Проверяю ссылку: '{url}'")
    
    # 1. Проверка на запрещенные символы
    if re.search(r'[;$\`"\'\{\}\[\]\|\^]', url):
        print("❌ [DEBUG] Найдены запрещенные символы (Shell Injection protection).")
        return False

    # 2. Перебор паттернов
    print(f"📋 [DEBUG] Список разрешенных паттернов ({len(settings.URL_PATTERNS)} шт):")
    
    for i, pattern in enumerate(settings.URL_PATTERNS):
        # re.match ищет совпадение с начала строки
        match = re.match(pattern, url)
        
        if match:
            print(f"✅ [DEBUG] СОВПАДЕНИЕ! Паттерн #{i}: {pattern}")
            return True
        else:
            # Для дебага можно раскомментировать, но будет много спама
            # print(f"   [DEBUG] Не подошел паттерн #{i}: {pattern}")
            pass

    print("⛔ [DEBUG] Ни один паттерн не подошел. Ссылка отклонена.")
    return False

async def download_content(url: str, custom_opts: dict = None):
    print(f"🚀 [DEBUG DOWNLOAD] Запрос на скачивание: {url}")
    
    if not is_valid_url(url):
        return None, None, "Ссылка не поддерживается или запрещена ⛔"

    # Роутинг
    if "tiktok.com" in url:
        print("   -> Выбран модуль: TikTok")
        return await tiktok.download(url, custom_opts)
        
    elif "instagram.com" in url:
        print("   -> Выбран модуль: Instagram")
        return await instagram.download(url, custom_opts)
        
    elif "youtube.com" in url or "youtu.be" in url:
        print("   -> Выбран модуль: YouTube")
        return await youtube.download(url, custom_opts)
        
    elif "soundcloud.com" in url:
        print("   -> Выбран модуль: SoundCloud")
        return await soundcloud.download(url, custom_opts)
    
    elif "twitch.tv" in url:
        print("   -> Выбран модуль: Twitch")
        return await twitch.download(url, custom_opts)

    # Добавил проверку vkvideo.ru сюда же
    elif "vk.com" in url or "vk.ru" in url or "vkvideo.ru" in url:
        print("   -> Выбран модуль: VK")
        return await vk.download(url, custom_opts)

    else:
        print("❌ [DEBUG] Модуль не найден (хотя валидация прошла!)")
        return None, None, "Неизвестный сервис."