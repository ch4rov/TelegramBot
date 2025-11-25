"""Inline handler - processes inline queries"""
import os
import shutil
import uuid
import asyncio
from aiogram import Router, F, types
from aiogram.types import (
    InlineQueryResultCachedVideo, 
    InputMediaVideo, 
    InputMediaAudio, 
    InputMediaPhoto,
    FSInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from loader import bot
from services.downloads import download_content, is_valid_url
import settings

router = Router()

# Твой ID заглушки
PLACEHOLDER_VIDEO_ID = "BAACAgIAAxkBAAE-Ud9pJTv8aMQwTbYs7hN5zHqb9Epz6AACE34AAraNMUnM0M23YCUF0DYE" 

@router.inline_query()
async def inline_query_handler(query: types.InlineQuery):
    url = query.query.strip()
    
    if not url or not is_valid_url(url):
        return

    result_id = str(uuid.uuid4())

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏳ Загрузка...", callback_data="processing")]
    ])

    result = InlineQueryResultCachedVideo(
        id=result_id,
        video_file_id=PLACEHOLDER_VIDEO_ID,
        title="📥 Скачать",
        description="Нажмите для загрузки",
        caption="⏳ *Загрузка... Пожалуйста, подождите.*",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

    await query.answer([result], cache_time=0, is_personal=True)


@router.chosen_inline_result()
async def chosen_handler(chosen_result: types.ChosenInlineResult):
    """
    User selected inline result.
    Download content, send to PM, update inline with final media.
    Only hourglass emoji shown during loading, then final file appears.
    """
    url = chosen_result.query.strip()
    inline_msg_id = chosen_result.inline_message_id
    user_id = chosen_result.from_user.id 
    
    if not inline_msg_id:
        return

    # Show loading indicator in inline (update caption to hourglass only)
    try:
        await bot.edit_message_caption(
            inline_message_id=inline_msg_id,
            caption="⏳",
            reply_markup=None
        )
    except:
        pass

    files, folder_path, error = await download_content(url)

    if error:
        try:
            await bot.edit_message_caption(
                inline_message_id=inline_msg_id,
                caption=f"❌ Ошибка: {error}",
                reply_markup=None
            )
        except:
            pass
        return

    try:
        media_files = []
        thumb_file = None
        
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                thumb_file = f
            elif ext in ['.mp4', '.mov', '.mkv', '.webm', '.ts', '.mp3', '.m4a', '.ogg', '.wav']:
                media_files.append(f)

        if not media_files:
            raise Exception("Медиа не найдено")

        target_file = media_files[0]
        ext = os.path.splitext(target_file)[1].lower()
        filename = os.path.basename(target_file)
        
        media_object = FSInputFile(target_file, filename=filename)
        thumbnail_object = FSInputFile(thumb_file) if thumb_file else None

        telegram_file_id = None
        media_type = None 

        # --- SEND TO PM (final file only, no temp messages) ---
        try:
            if ext in ['.mp4', '.mov', '.mkv', '.webm', '.ts']:
                msg = await bot.send_video(
                    chat_id=user_id,
                    video=media_object,
                    thumbnail=None, 
                    caption=None,
                    supports_streaming=True,
                    disable_notification=True 
                )
                telegram_file_id = msg.video.file_id
                media_type = 'video'

            elif ext in ['.mp3', '.m4a', '.ogg', '.wav']:
                performer = "Unknown"
                title = os.path.splitext(filename)[0]
                if " - " in title:
                    parts = title.split(" - ", 1)
                    performer = parts[0]
                    title = parts[1]

                msg = await bot.send_audio(
                    chat_id=user_id,
                    audio=media_object,
                    thumbnail=thumbnail_object, 
                    caption=None,
                    performer=performer,
                    title=title,
                    disable_notification=True
                )
                telegram_file_id = msg.audio.file_id
                media_type = 'audio'

            elif ext in ['.jpg', '.jpeg', '.png']:
                msg = await bot.send_photo(
                    chat_id=user_id,
                    photo=media_object,
                    caption=None,
                    disable_notification=True
                )
                telegram_file_id = msg.photo[-1].file_id
                media_type = 'photo'

        except Exception as e_pm:
            print(f"❌ Ошибка отправки в ЛС: {e_pm}")
            try:
                await bot.edit_message_caption(
                    inline_message_id=inline_msg_id,
                    caption="⚠️ Ошибка: Разблокируйте бота в ЛС (@ch4roff_bot).",
                    reply_markup=None
                )
            except:
                pass
            return

        # --- UPDATE INLINE with final media ---
        if telegram_file_id:
            try:
                new_media = None
                
                if media_type == 'video':
                    new_media = InputMediaVideo(
                        media=telegram_file_id,
                        caption=None,
                        supports_streaming=True
                    )
                elif media_type == 'audio':
                    new_media = InputMediaAudio(
                        media=telegram_file_id,
                        caption=None
                    )
                elif media_type == 'photo':
                    new_media = InputMediaPhoto(
                        media=telegram_file_id,
                        caption=None
                    )

                if new_media:
                    await bot.edit_message_media(
                        inline_message_id=inline_msg_id,
                        media=new_media,
                        reply_markup=None
                    )
                
            except Exception as e_edit:
                print(f"❌ Inline Edit Error: {e_edit}")
                try:
                    await bot.edit_message_caption(
                        inline_message_id=inline_msg_id,
                        caption="✅ Файл загружен в ЛС.",
                        reply_markup=None
                    )
                except:
                    pass

    except Exception as e:
        print(f"Global Inline Error: {e}")
        try:
            await bot.edit_message_caption(
                inline_message_id=inline_msg_id,
                caption="⚠️ Ошибка.",
                reply_markup=None
            )
        except:
            pass

    finally:
        if folder_path and os.path.exists(folder_path):
            shutil.rmtree(folder_path, ignore_errors=True)
