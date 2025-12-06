from aiogram import Router, types
from services.database_service import add_or_update_user
from languages import t
import html
import settings

# Общий роутер для всех пользовательских функций
user_router = Router()

# Глобальная переменная для лимитов
ACTIVE_DOWNLOADS = {}

async def check_access_and_update(user, message: types.Message):
    is_new, is_banned, ban_reason, lang = await add_or_update_user(user.id, user.username)
    if is_banned:
        await message.answer(f"⛔ You are banned.\nReason: {ban_reason}")
        return False, False, None, lang
    return True, is_new, None, lang

async def make_caption(title_text, url, user_id, override=None, is_audio=False):
    """
    Асинхронная функция подписи с переводом.
    """
    bot_name = settings.BOT_USERNAME or "ch4roff_bot"
    bot_link = f"@{bot_name}"
    
    platforms_link = ""
    if is_audio and url:
        clean_source = url.split("?")[0] if "?" in url else url
        odesli_url = f"https://song.link/{clean_source}"
        platforms_text = await t(user_id, 'platforms')
        platforms_link = f" | <a href=\"{odesli_url}\">{platforms_text}</a>"

    footer = f"{bot_link}{platforms_link}"

    if override:
        return f"{html.escape(override)}\n\n{footer}"
    
    if not title_text:
        return footer
    
    safe_title = html.escape(title_text)
    return f'<a href="{url}">{safe_title}</a>\n\n{footer}'