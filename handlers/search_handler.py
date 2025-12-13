import os
import shutil
import html
from aiogram import Router, F, types
from aiogram.types import FSInputFile
from aiogram.enums import ChatAction
from loader import bot
from services.platforms.platform_manager import download_content, is_valid_url
import settings

router = Router()

# Лимиты в байтах
LIMIT_PUBLIC = 49 * 1024 * 1024       # ~49 MB (с запасом)
LIMIT_LOCAL = 1990 * 1024 * 1024      # ~1.95 GB

@router.message(F.text)
async def message_handler(message: types.Message):
    text = message.text.strip()
    user_id = message.from_user.id
    
    if text.startswith("/"): return

    if is_valid_url(text):
        status_msg = await message.answer("⏳ <b>Анализирую ссылку...</b>", parse_mode="HTML")
        
        # --- ОПРЕДЕЛЯЕМ ЛИМИТЫ И ФОРМАТ ---
        is_local = getattr(settings, 'USE_LOCAL_SERVER', False)
        current_limit = LIMIT_LOCAL if is_local else LIMIT_PUBLIC
        
        if is_local:
            # Локальный сервер: Качаем максимум
            format_str = 'bestvideo+bestaudio/best'
        else:
            # Публичный API: Пытаемся найти лучшее качество, но НЕ БОЛЕЕ 50МБ
            # Если не найдет <50МБ, скачает 'worst' (худшее), чтобы хоть что-то отправить
            format_str = 'best[filesize<50M]/bestvideo[filesize<40M]+bestaudio/best[height<=480]/worst'

        custom_opts = {
            'format': format_str,
            'merge_output_format': 'mp4',
            'postprocessors': [{'key': 'EmbedThumbnail'}, {'key': 'FFmpegMetadata'}],
            'writethumbnail': True,
            'noplaylist': True
        }

        # Качаем
        files, folder_path, error, meta = await download_content(text, custom_opts)

        if error:
            try: await status_msg.edit_text(f"❌ <b>Ошибка:</b> {html.escape(error)}", parse_mode="HTML")
            except: pass
            if folder_path: shutil.rmtree(folder_path, ignore_errors=True)
            return

        try:
            # Фильтр файлов
            media_files = []
            thumb_file = None
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in ['.jpg', '.jpeg', '.png', '.webp']: thumb_file = f
                elif ext in ['.mp4', '.mov', '.mkv', '.webm', '.avi', '.mp3', '.m4a', '.wav', '.flac', '.ogg']:
                    media_files.append(f)

            if not media_files:
                await status_msg.edit_text("❌ Медиафайлы не найдены.")
                return

            target_file = media_files[0]
            filename = os.path.basename(target_file)
            ext = os.path.splitext(target_file)[1].lower()
            file_size = os.path.getsize(target_file)

            # --- ГЛАВНАЯ ПРОВЕРКА РАЗМЕРА ---
            if file_size > current_limit:
                limit_str = "2 GB" if is_local else "50 MB"
                size_str = f"{file_size / (1024*1024):.1f} MB"
                await status_msg.edit_text(
                    f"⚠️ <b>Файл слишком большой!</b>\n"
                    f"Размер: {size_str}\n"
                    f"Лимит бота: {limit_str}\n\n"
                    f"<i>Попробуйте на локальном сервере или выберите видео короче.</i>",
                    parse_mode="HTML"
                )
                return
            # --------------------------------

            media_input = FSInputFile(target_file, filename=filename)
            thumb_input = FSInputFile(thumb_file) if thumb_file else None

            if not meta: meta = {}
            title = meta.get('title', filename)
            artist = meta.get('artist') or meta.get('uploader')
            
            caption = f'<a href="{text}">{html.escape(title)}</a>'
            if artist: caption = f"<b>{html.escape(artist)}</b> - " + caption
            bot_username = getattr(settings, 'BOT_USERNAME', 'bot')
            caption += f"\n\n@{bot_username}"

            sent_message = None
            
            # Отправка
            if ext in ['.mp3', '.m4a', '.wav', '.flac', '.ogg']:
                await bot.send_chat_action(user_id, ChatAction.UPLOAD_VOICE)
                sent_message = await message.answer_audio(
                    media_input, caption=caption, parse_mode="HTML",
                    thumbnail=thumb_input, title=title, performer=artist
                )
            elif ext in ['.mp4', '.mov']:
                await bot.send_chat_action(user_id, ChatAction.UPLOAD_VIDEO)
                sent_message = await message.answer_video(
                    media_input, caption=caption, parse_mode="HTML",
                    thumbnail=thumb_input, supports_streaming=True,
                    width=meta.get('width'), height=meta.get('height'), duration=meta.get('duration')
                )
            else:
                await bot.send_chat_action(user_id, ChatAction.UPLOAD_DOCUMENT)
                sent_message = await message.answer_document(
                    media_input, caption=caption, parse_mode="HTML", thumbnail=thumb_input
                )

            if sent_message:
                try: await status_msg.delete()
                except: pass
            else:
                await status_msg.edit_text("⚠️ Не удалось отправить файл (ошибка API).")

        except Exception as e:
            print(f"Error sending direct link: {e}")
            try: await status_msg.edit_text(f"⚠️ Ошибка отправки: {e}")
            except: pass
        finally:
            if folder_path and os.path.exists(folder_path): shutil.rmtree(folder_path, ignore_errors=True)