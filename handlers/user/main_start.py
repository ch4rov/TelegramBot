# -*- coding: utf-8 -*-
import logging
from aiogram import Router, F, types
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from services.database.repo import add_or_update_user, set_user_language, get_user, get_module_status
from services.localization import LocalizationService
from settings import MODULES_LIST, BOT_COMMANDS_LIST, ADMIN_IDS

router = Router()
logger = logging.getLogger(__name__)


def build_commands_text(lang: str, user_id: int):
    """UX: show only 4 commands in the start menu text."""
    if lang == "ru":
        return (
            "**🔧 Команды:**\n"
            "/start - Главное меню\n"
            "/login - Подключения\n"
            "/language - Язык\n"
            "/videomessage - Видеосообщение"
        )
    return (
        "**🔧 Commands:**\n"
        "/start - Main Menu\n"
        "/login - Connections\n"
        "/language - Language\n"
        "/videomessage - Video Note"
    )


async def get_start_message(name: str, lang: str, user_id: int):
    """Собирает полное сообщение /start"""
    
    if lang == "en":
        greeting = f"**👋 Hello, {name}!**"
        description = ("🎵 Download music, videos, and media content.\n"
                  "🎬 Support for multiple platforms.\n"
                  "💬 Share directly in chat with your friend via @ch4rov\\_bot and tap \"Send\".")
        policy_text = "📋 [Privacy Policy](https://telegra.ph/EN-ch4roBO---Policy-terms-and-information-12-18) • CEO: @ch4rov"
        platforms_label = "**📦 Available platforms:**"
    else:
        greeting = f"**👋 Привет, {name}!**"
        description = ("🎵 Загружайте музыку, видео и медиа-контент.\n"
                  "🎬 Поддержка множества платформ.\n"
                  "💬 Отправляй не выходя из чата с другом через @ch4rov\\_bot и нажми кнопку \"Отправить\".")
        policy_text = "📋 [Политика конфиденциальности](https://telegra.ph/RU-ch4roBO---Politika-konfidencialnosti-i-obrabotki-dannyh-12-18) • CEO: @ch4rov"
        platforms_label = "**📦 Доступные платформы:**"
    
    # Build enabled platforms list
    enabled_list = []
    for module_name in MODULES_LIST:
        is_enabled = await get_module_status(module_name)
        if is_enabled:
            enabled_list.append(module_name)
    
    platforms_text = ", ".join(enabled_list) if enabled_list else ("No platforms available" if lang == "en" else "Платформы недоступны")
    
    # Build commands text
    all_commands = build_commands_text(lang, user_id)
    
    # Combine all text
    full_text = (
        f"{greeting}\n\n"
        f"{description}\n\n"
        f"{platforms_label} {platforms_text}\n\n"
        f"{all_commands}\n\n"
        f"{policy_text}"
    )
    
    return full_text


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    try:
        from services.localization import i18n
        
        user = message.from_user
        
        # Проверяем, есть ли юзер в базе
        db_user = await get_user(user.id)

        # Если юзера нет - предлагаем выбор языка
        if not db_user:
            # Регистрируем с дефолтным языком (en)
            await add_or_update_user(
                user.id, 
                user.username, 
                user.full_name or "User",
                "",
                language="en"
            )
            
            # Предлагаем выбор языка
            kb = InlineKeyboardBuilder()
            kb.button(text="🇬🇧 English", callback_data="set_lang:en")
            kb.button(text="🇷🇺 Русский", callback_data="set_lang:ru")
            kb.adjust(2)
            
            text = "👋 Hello! / Привет!\n\nPlease choose your language:\nПожалуйста, выберите язык:"
            
            await message.reply(text, reply_markup=kb.as_markup(), disable_notification=True)
            logger.info(f"New user registered: {user.id} (@{user.username})")
            return

        # Если юзер уже есть - показываем полное меню
        lang = db_user.language
        name = user.first_name or "User"
        
        full_text = await get_start_message(name, lang, user.id)
        
        await message.reply(full_text, parse_mode="Markdown", disable_notification=True)
        logger.info(f"User {user.id} sent /start")
    
    except Exception as e:
        logger.error(f"Error in /start: {e}")
        await message.reply("Error processing /start", disable_notification=True)


@router.callback_query(F.data.startswith("set_lang:"))
async def callback_set_lang(callback: types.CallbackQuery):
    """Обработчик выбора языка"""
    try:
        lang_code = callback.data.split(":")[1]
        user = callback.from_user
        name = user.first_name or "User"
        
        # Устанавливаем язык
        await set_user_language(user.id, lang_code)
        
        # Удаляем сообщение с выбором языка
        try:
            await callback.message.delete()
        except:
            pass
        
        # Собираем полное сообщение
        full_text = await get_start_message(name, lang_code, user.id)
        
        await callback.message.reply(full_text, parse_mode="Markdown", disable_notification=True)
        
        logger.info(f"User {user.id} set language to {lang_code}")
    
    except Exception as e:
        logger.error(f"Error in language selection: {e}")

