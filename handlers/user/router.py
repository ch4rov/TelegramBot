from aiogram import Router, types
from services.database_service import add_or_update_user
import html
import settings

user_router = Router()
ACTIVE_DOWNLOADS = {}

async def check_access_and_update(user, message: types.Message):
    """
    Проверяет права пользователя И группы.
    """
    # 1. Проверяем/Регистрируем Пользователя
    is_new, is_banned, ban_reason, lang = await add_or_update_user(user.id, user.username or user.first_name)
    
    if is_banned:
        # В личке пишем, в группе молчим
        if message.chat.type == "private":
            await message.answer(f"⛔ You are banned.\nReason: {ban_reason}")
        return False, False, None, lang

    # 2. Если это ГРУППА - проверяем/регистрируем её тоже
    if message.chat.type in ["group", "supergroup"]:
        chat_id = message.chat.id
        chat_title = message.chat.title or "Group"
        
        # Регистрируем группу (ID < 0)
        # 4-й параметр (язык) для группы пока берем дефолтный или тот же
        _, is_chat_banned, chat_ban_reason, _ = await add_or_update_user(chat_id, chat_title)
        
        if is_chat_banned:
            # Если группа забанена - молчим и не работаем
            return False, False, None, lang

    return True, is_new, None, lang

# Функция подписи теперь принимает доп. параметр для тега
def make_caption(title_text, url, override=None, is_audio=False, request_by=None):
    bot_name = settings.BOT_USERNAME or "ch4roff_bot"
    bot_link = f"@{bot_name}"
    
    platforms_link = ""
    if is_audio and url:
        clean_source = url.split("?")[0] if "?" in url else url
        odesli_url = f"https://song.link/{clean_source}"
        platforms_link = f" | <a href=\"{odesli_url}\">🌐</a>"

    # Формируем футер
    footer_parts = [bot_link, platforms_link]
    if request_by:
        footer_parts.append(f"\n{request_by}")
        
    footer = "".join(footer_parts)

    if override:
        return f"{html.escape(override)}\n\n{footer}"
    
    if not title_text:
        return footer
    
    safe_title = html.escape(title_text)
    return f'<a href="{url}">{safe_title}</a>\n\n{footer}'