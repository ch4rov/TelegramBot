import os
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, InlineQuery, InlineQueryResultArticle, InputTextMessageContent, Update
import settings # <--- БЕРЕМ НАСТРОЙКИ ОТСЮДА

# Ссылка на основного бота
STABLE_BOT_LINK = "https://t.me/ch4rov_bot"
BLOCK_TEXT = (
    "🚧 <b>Тестовый режим</b>\n\n"
    "Этот бот используется только для разработки.\n"
    f"Перейдите в основную версию: <a href='{STABLE_BOT_LINK}'>@ch4rov_bot</a> 🤖"
)

class AccessMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Update, data):
        
        # 1. ГЛАВНАЯ ПРОВЕРКА:
        # Берем переменную из settings.py
        if not settings.IS_TEST_ENV:
            return await handler(event, data)

        # ----------------------------------------------------------------
        # Если код дошел сюда — значит мы на ТЕСТОВОМ боте. Включаем защиту.
        # ----------------------------------------------------------------

        # Определяем ID пользователя из любого типа события
        user_id = None
        if event.message: user_id = event.message.from_user.id
        elif event.callback_query: user_id = event.callback_query.from_user.id
        elif event.inline_query: user_id = event.inline_query.from_user.id
        elif event.chosen_inline_result: user_id = event.chosen_inline_result.from_user.id

        # Если юзера нет в списке тестеров -> БЛОКИРУЕМ
        if user_id and user_id not in settings.TESTERS_LIST:
            
            # Блокировка сообщения
            if event.message:
                try:
                    await event.message.answer(BLOCK_TEXT, parse_mode="HTML", disable_web_page_preview=True)
                except: pass
                return
            
            # Блокировка кнопки
            elif event.callback_query:
                try:
                    await event.callback_query.answer("⛔ Доступ только для тестеров.", show_alert=True)
                except: pass
                return
            
            # Блокировка инлайна (показываем заглушку)
            elif event.inline_query:
                result = InlineQueryResultArticle(
                    id="block",
                    title="🚧 Тестовый режим",
                    description="Доступ ограничен.",
                    input_message_content=InputTextMessageContent(message_text=BLOCK_TEXT, parse_mode="HTML", disable_web_page_preview=True)
                )
                try:
                    await event.inline_query.answer([result], cache_time=5, is_personal=True)
                except: pass
                return
            
            # Игнорируем выбор результата
            elif event.chosen_inline_result:
                return

        # Если это тестер — пропускаем
        return await handler(event, data)