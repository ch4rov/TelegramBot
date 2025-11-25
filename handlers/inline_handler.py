import os
import shutil
import uuid
import asyncio
from aiogram import Router, F, types
from aiogram.types import (
    InlineQueryResultCachedVideo, 
    InlineQueryResultCachedAudio, # <--- Используем для музыки
    InputMediaVideo, 
    InputMediaAudio, 
    FSInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InlineQueryResultArticle, 
    InputTextMessageContent
)
from loader import bot
from services.downloads import download_content, is_valid_url
from services.database_service import get_user
from services.lastfm_service import get_user_recent_track
from services.search_service import search_music # Универсальный поиск
import settings

router = Router()

# --- КОНФИГУРАЦИЯ ЗАГЛУШЕК ---
# 1. Видео-заглушка (для ссылок)
PLACEHOLDER_VIDEO_ID = "BAACAgIAAxkBAAE-Ud9pJTv8aMQwTbYs7hN5zHqb9Epz6AACE34AAraNMUnM0M23YCUF0DYE" 
# 2. Аудио-заглушка (для поиска музыки/Last.fm)
PLACEHOLDER_AUDIO_ID = "CQACAgIAAxkDAAIFcWkmO4LEqQIgMGeMrRlkJ7fLKQVxAAKRgQAC2IoxSbFgB6UvfGcbNgQ"

@router.inline_query()
async def inline_query_handler(query: types.InlineQuery):
    text = query.query.strip()
    user_id = query.from_user.id
    results = []

    # ==========================================
    # 1. ЕСЛИ ЭТО ССЫЛКА -> ВИДЕО ЗАГЛУШКА
    # ==========================================
    if text and is_valid_url(text):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 Скачать", callback_data="processing")]
        ])
        
        results.append(InlineQueryResultCachedVideo(
            id=str(uuid.uuid4()),
            video_file_id=PLACEHOLDER_VIDEO_ID,
            title="📥 Скачать по ссылке",
            description="Нажмите для загрузки видео/фото",
            caption="⏳ *Загрузка...*",
            parse_mode="Markdown",
            reply_markup=keyboard
        ))

    # ==========================================
    # 2. ЕСЛИ ЭТО ТЕКСТ / ПУСТО -> АУДИО ЗАГЛУШКА (МУЗЫКА)
    # ==========================================
    else:
        # Если введен текст - это поиск музыки
        search_query = text
        
        # Если пусто - берем из Last.fm
        if not search_query:
            user_db = await get_user(user_id)
            lfm_user = user_db['lastfm_username'] if user_db and 'lastfm_username' in user_db else None
            
            if lfm_user:
                track = await get_user_recent_track(lfm_user)
                if track:
                    search_query = track['query'] # "Artist - Title"
            
        if search_query:
            # Формируем ID для колбэка: "music:Artist - Track"
            # (Обрезаем до 50 символов, чтобы влезло в лимит Telegram)
            result_id = f"music:{search_query[:50]}"

            keyboard_lfm = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎵 Найти и скачать", callback_data="processing")]
            ])

            # Показываем Аудио-плеер
            results.append(InlineQueryResultCachedAudio(
                id=result_id,
                audio_file_id=PLACEHOLDER_AUDIO_ID,
                caption=f"🔎 Ищу: {search_query}", # Этот текст будет виден при отправке
                reply_markup=keyboard_lfm
                # Заголовок в меню выбора берется из метаданных файла заглушки
            ))
        
        # Если Last.fm нет и текст пустой - подсказка
        if not search_query:
            results.append(InlineQueryResultArticle(
                id="login_hint",
                title="🎵 Моя музыка (Last.fm)",
                description="Подключи профиль или введи название трека!",
                input_message_content=InputTextMessageContent(
                    message_text="Чтобы подключить свою музыку:\n👉 <code>/login ваш_ник</code>\n\nИли просто введите название песни после тега бота.",
                    parse_mode="HTML"
                )
            ))

    await query.answer(results, cache_time=2, is_personal=True)


@router.chosen_inline_result()
async def chosen_handler(chosen_result: types.ChosenInlineResult):
    result_id = chosen_result.result_id
    inline_msg_id = chosen_result.inline_message_id
    user_id = chosen_result.from_user.id 
    
    if not inline_msg_id: return

    # Определяем режим работы по ID результата
    is_music_mode = result_id.startswith("music:") or result_id.startswith("lfm:")
    
    url = None
    title_for_caption = "Загрузка..."

    # --- РЕЖИМ МУЗЫКИ (ПОИСК) ---
    if is_music_mode:
        # Вытаскиваем запрос
        if result_id.startswith("music:"): query_str = result_id.split("music:", 1)[1]
        else: query_str = result_id.split("lfm:", 1)[1]
        
        # Ищем трек (YouTube -> SoundCloud)
        # Используем твой service/search_service.py
        search_results = await search_music(query_str, limit=1)
        
        if not search_results:
            await bot.edit_message_caption(inline_message_id=inline_msg_id, caption=f"❌ Не найдено: {query_str}")
            return
            
        url = search_results[0]['url']
        title_for_caption = search_results[0]['title']
        
        # Пишем пользователю, что нашли
        try: await bot.edit_message_caption(inline_message_id=inline_msg_id, caption=f"📥 Качаю: {title_for_caption}...")
        except: pass

    # --- РЕЖИМ ССЫЛКИ ---
    else:
        url = chosen_result.query.strip()

    if not url: return

    # --- НАСТРОЙКИ СКАЧИВАНИЯ ---
    custom_opts = {}
    # Если это музыкальный режим - ОБЯЗАТЕЛЬНО конвертируем в MP3
    # Иначе мы не сможем заменить Audio-заглушку на файл
    if is_music_mode:
        custom_opts = {
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        }

    files, folder_path, error = await download_content(url, custom_opts)

    if error:
        try: await bot.edit_message_caption(inline_message_id=inline_msg_id, caption=f"❌ {error}")
        except: pass
        return

    try:
        media_files = []
        thumb_file = None
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.webp']: thumb_file = f
            elif ext in ['.mp4', '.mov', '.mkv', '.webm', '.ts', '.mp3', '.m4a', '.ogg', '.wav']: media_files.append(f)

        if not media_files: raise Exception("Empty media")

        target_file = media_files[0]
        ext = os.path.splitext(target_file)[1].lower()
        filename = os.path.basename(target_file)
        media_object = FSInputFile(target_file, filename=filename)
        thumbnail_object = FSInputFile(thumb_file) if thumb_file else None
        
        # Определяем тип скачанного файла
        is_audio_file = filename.endswith(('.mp3', '.m4a', '.ogg', '.wav'))
        
        telegram_file_id = None
        sent_message_obj = None

        # 1. ШЛЕМ В ЛС (ЧТОБЫ ПОЛУЧИТЬ ID)
        try:
            # АУДИО
            if is_audio_file:
                performer = "Unknown"
                title = os.path.splitext(filename)[0]
                if " - " in title: parts = title.split(" - ", 1); performer = parts[0]; title = parts[1]
                
                sent_message_obj = await bot.send_audio(
                    chat_id=user_id, 
                    audio=media_object, 
                    thumbnail=thumbnail_object,
                    caption=None, 
                    performer=performer, title=title, 
                    disable_notification=True
                )
                telegram_file_id = sent_message_obj.audio.file_id
            
            # ВИДЕО
            else:
                sent_message_obj = await bot.send_video(
                    chat_id=user_id, video=media_object, thumbnail=None,
                    caption=None, supports_streaming=True, disable_notification=True
                )
                telegram_file_id = sent_message_obj.video.file_id

        except Exception:
            await bot.edit_message_caption(inline_message_id=inline_msg_id, caption="⚠️ Бот заблокирован в ЛС.", reply_markup=None)
            return

        # 2. ОБНОВЛЯЕМ ИНЛАЙН
        # Тут строгая проверка типов!
        # Мы можем заменить: Audio -> Audio, Video -> Video.
        # Смешивать нельзя.
        
        new_media = None
        
        if is_music_mode and is_audio_file:
            # Мы обещали Аудио (заглушка) и скачали Аудио -> ОК
            new_media = InputMediaAudio(media=telegram_file_id, caption=None)
            
        elif not is_music_mode and not is_audio_file:
            # Мы обещали Видео (заглушка) и скачали Видео -> ОК
            new_media = InputMediaVideo(media=telegram_file_id, caption=None, supports_streaming=True)
            
        else:
            # Типы не совпали (например, кинули ссылку на YouTube, а это оказался только звук, или наоборот)
            # Редактировать нельзя, оставляем как есть (файл уже в ЛС)
            await bot.edit_message_caption(
                inline_message_id=inline_msg_id, 
                caption="✅ Файл отправлен в ЛС (смена типа невозможна).", 
                reply_markup=None
            )

        # Если типы совпали - заменяем
        if new_media:
            try:
                await bot.edit_message_media(inline_message_id=inline_msg_id, media=new_media, reply_markup=None)
                # Удаляем из ЛС (чистота)
                if sent_message_obj:
                    await asyncio.sleep(0.5)
                    await bot.delete_message(chat_id=user_id, message_id=sent_message_obj.message_id)
            except Exception as e:
                print(f"Edit Error: {e}")

    except Exception as e:
        try: await bot.edit_message_caption(inline_message_id=inline_msg_id, caption="⚠️ Error.", reply_markup=None)
        except: pass
    finally:
        if folder_path and os.path.exists(folder_path): shutil.rmtree(folder_path, ignore_errors=True)