from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from services.odesli_service import get_links_by_url

links_router = Router()

@links_router.callback_query(F.data == "get_links")
async def show_song_links(callback: types.CallbackQuery):
    # 1. Ищем ссылку в сообщении
    url = None
    message = callback.message
    
    # Проверяем caption_entities (так как это аудио с подписью)
    if message.caption_entities:
        for entity in message.caption_entities:
            if entity.type == "text_link":
                url = entity.url
                break
            elif entity.type == "url":
                # Если ссылка просто текстом
                url = message.caption[entity.offset : entity.offset + entity.length]
                break
    
    if not url:
        await callback.answer("❌ Ссылка не найдена в сообщении.", show_alert=True)
        return

    await callback.answer("🔍 Ищу ссылки на платформах...")

    # 2. Запрос к Odesli
    data = await get_links_by_url(url)
    
    if not data or not data.get('links'):
        await callback.answer("😔 Ничего не нашел на song.link", show_alert=True)
        return

    # 3. Формируем ответ
    text = "<b>🌐 Доступно на платформах:</b>\n\n"
    
    # Собираем кнопки
    rows = []
    for name, link in data['links'].items():
        rows.append([InlineKeyboardButton(text=f"🎵 {name}", url=link)])
    
    # Добавляем кнопку на сам song.link
    rows.append([InlineKeyboardButton(text="🔗 Все платформы (Song.link)", url=data['page'])])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    
    # Отправляем как скрытое сообщение (чтобы видел только нажавший)
    # Но aiogram не умеет слать ephemeral message как в дискорде,
    # поэтому просто отвечаем новым сообщением.
    await message.reply(text, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)