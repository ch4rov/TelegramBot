from aiogram import Router, types
from services.database_service import add_or_update_user
import html
import settings

# Общий роутер для всех пользовательских функций
user_router = Router()

# Глобальная переменная для лимитов
ACTIVE_DOWNLOADS = {}

async def check_access_and_update(user, message: types.Message):
    """Проверка прав и обновление статистики"""
    is_new, is_banned, ban_reason = await add_or_update_user(user.id, user.username)
    if is_banned:
        await message.answer(f"⛔ Вы заблокированы.\nПричина: {ban_reason}")
        return False, False
    return True, is_new

def make_caption(title_text, url, override=None):
    """Формирует подпись"""
    bot_name = settings.BOT_USERNAME or "ch4roff_bot"
    bot_link = f"@{bot_name}"
    if override:
        return f"{html.escape(override)}\n\n{bot_link}"
    if not title_text:
        return bot_link
    return f'<a href="{url}">{html.escape(title_text)}</a>\n\n{bot_link}'