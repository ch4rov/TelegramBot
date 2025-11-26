import os
import shutil
import traceback
from aiogram import Router, F, types
from aiogram.types import FSInputFile
from aiogram.enums import ChatAction

from services.downloads import download_content
from services.database_service import add_or_update_user

print("📢 [SYSTEM] Модуль handlers/search_handler.py загружен!")

router = Router()

@router.callback_query(F.data == "delete_msg")
async def delete_message(callback: types.CallbackQuery):
    try: await callback.message.delete()
    except: pass

# Ловим ЛЮБУЮ кнопку, которая начинается с music:
@router.callback_query(F.data.startswith("music:"))
async def handle_music_selection(callback: types.CallbackQuery):
    # ОТЛАДКА: Пишем в консоль сразу при нажатии
    print(f"🔘 [DEBUG] Нажата кнопка: {callback.data}")

    try:
        # 1. Парсим данные
        parts = callback.data.split(":", 1)
        if len(parts) < 2: 
            print("❌ [DEBUG] Кривые данные в кнопке")
            return
        
        video_id = parts[1]
        url = f"https://youtu.be/{video_id}"
        user = callback.from_user

        # 2. Обновляем статистику
        await add_or_update_user(user.id, user.username)

        # 3. Ответ пользователю
        await callback.answer("🎧 Начинаю загрузку...")
        
        try:
            await callback.message.edit_text(
                f"📥 <b>Скачиваю трек...</b>\n<code>{url}</code>", 
                reply_markup=None, 
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"⚠️ [DEBUG] Не смог отредактировать сообщение: {e}")

        # 4. Настройки (ТОЛЬКО АУДИО)
        custom_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [
                {'key': 'EmbedThumbnail'},
                {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}
            ]
        }

        # 5. Скачивание
        print(f"⬇️ [DEBUG] Начало загрузки: {url}")
        files, folder_path, error = await download_content(url, custom_opts)

        if error:
            print(f"❌ [DEBUG] Ошибка загрузки: {error}")
            try: await callback.message.edit_text(f"❌ Ошибка: {error}")
            except: pass
            return

        # 6. Отправка
        try:
            await callback.bot.send_chat_action(chat_id=callback.message.chat.id, action=ChatAction.UPLOAD_VOICE)
            
            media_files = []
            thumb_file = None
            
            for f in files:
                if f.endswith(('.jpg', '.png', '.webp')): thumb_file = f
                elif f.endswith(('.mp3', '.m4a', '.ogg', '.wav')): media_files.append(f)

            if not media_files: raise Exception("Файл не создан (пусто)")

            target = media_files[0]
            filename = os.path.basename(target)
            
            # Парсим имя
            performer = "@ch4roff_bot"
            title = os.path.splitext(filename)[0]
            if " - " in title:
                p_parts = title.split(" - ", 1)
                performer = p_parts[0]
                title = p_parts[1]

            print(f"📤 [DEBUG] Отправка: {filename}")
            
            # Отправляем
            await callback.message.answer_audio(
                FSInputFile(target),
                caption=f'<a href="{url}">{title}</a>',
                parse_mode="HTML",
                thumbnail=FSInputFile(thumb_file) if thumb_file else None,
                performer=performer,
                title=title
            )
            
            # Удаляем сообщение "Скачиваю..."
            try: await callback.message.delete()
            except: pass

        except Exception as e:
            print(f"❌ [DEBUG] Ошибка отправки: {traceback.format_exc()}")
            try: await callback.message.edit_text(f"⚠️ Ошибка отправки: {e}")
            except: pass
        
        finally:
            if folder_path and os.path.exists(folder_path):
                shutil.rmtree(folder_path, ignore_errors=True)

    except Exception as critical_e:
        print(f"🔥 [CRITICAL ERROR] {traceback.format_exc()}")