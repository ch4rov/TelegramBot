import os
import sys
import asyncio
from aiogram import Router, types, exceptions
from aiogram.filters import Command
from aiogram.types import FSInputFile
from services.database import get_all_users, set_ban_status, get_user
from logs.logger import send_log
from services.downloads import download_content

# --- ОТЛАДКА ПРИ ЗАПУСКЕ ---
print("📢 [SYSTEM] Модуль handlers/admin.py загружен!")
# ---------------------------

router = Router()

def is_admin(user_id):
    """
    Проверяет права админа.
    Получаем ID внутри функции, чтобы гарантировать загрузку .env
    """
    env_admin_id = os.getenv("ADMIN_ID")
    
    if not env_admin_id:
        print("❌ [ADMIN ERROR] В файле .env не найден ADMIN_ID!")
        return False
        
    is_match = str(user_id) == str(env_admin_id)
    
    if not is_match:
        print(f"⚠️ [ADMIN DENIED] Твой ID: {user_id} | Нужен ID: {env_admin_id}")
    else:
        # Чтобы не спамить в консоль при каждом действии, можно закомментировать
        # print(f"✅ [ADMIN ACCESS] Доступ разрешен для: {user_id}")
        pass
        
    return is_match

# --- RESTART ---
@router.message(Command("restart"))
async def cmd_restart(message: types.Message):
    if not is_admin(message.from_user.id): return

    await message.answer("♻️ Перезагрузка системы...")
    await send_log("ADMIN", "Инициировал перезагрузку системы (Restart)", admin=message.from_user)
    
    # Завершаем процесс кодом 65. run.py поймает его и перезапустит бота.
    sys.exit(65)

# --- STATUS / USERS ---
@router.message(Command("status"))
async def cmd_status(message: types.Message):
    if not is_admin(message.from_user.id): return
    await message.answer("✅ Система работает штатно (v2.2 Inline + Fixes).")
    await send_log("ADMIN", "> /status", admin=message.from_user)

@router.message(Command("users"))
async def cmd_users(message: types.Message):
    if not is_admin(message.from_user.id): return

    users = await get_all_users()
    if not users:
        await message.answer("📂 База данных пуста.")
        return

    text = f"📋 **Всего пользователей: {len(users)}**\n\n"
    count = 0
    for u in users:
        if count >= 20:
            text += "\n...(и еще много)..."
            break

        status = "⛔" if u['is_banned'] else "✅"
        clean_name = str(u['username']).replace("_", "\\_").replace("*", "\\*") if u['username'] else "NoName"
        reason_txt = f"\n   Reason: _{u['ban_reason']}_" if u['is_banned'] and u['ban_reason'] else ""
        
        text += f"{status} `{u['user_id']}` | @{clean_name}{reason_txt}\n🕒 {u['last_seen']}\n\n"
        count += 1
        
    await message.answer(text, parse_mode="Markdown")

# --- BAN LOGIC ---
@router.message(Command("ban"))
async def cmd_ban(message: types.Message):
    if not is_admin(message.from_user.id): return
    
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("⚠️ Использование: `/ban ID [Причина]`", parse_mode="Markdown")
        return
        
    try:
        target_id = int(parts[1])
        new_reason = parts[2] if len(parts) > 2 else "Нарушение правил"
        
        user_data = await get_user(target_id)
        if not user_data:
            await message.answer("❌ Пользователь не найден в базе данных.")
            return

        is_already_banned = user_data['is_banned']
        old_reason = user_data['ban_reason']

        if is_already_banned:
            if old_reason == new_reason:
                await message.answer(f"⚠️ Пользователь `{target_id}` уже забанен по этой причине.")
                return
            else:
                await set_ban_status(target_id, True, new_reason)
                await message.answer(f"🔄 Причина бана для `{target_id}` обновлена на: {new_reason}")
                await send_log("ADMIN", f"Обновил причину бана для {target_id} на: {new_reason}", admin=message.from_user)
                return

        await set_ban_status(target_id, True, new_reason)
        await message.answer(f"⛔ Пользователь `{target_id}` забанен.\nПричина: {new_reason}", parse_mode="Markdown")
        
        log_msg = f"Забанил {target_id} (Причина: {new_reason})"
        await send_log("ADMIN", log_msg, admin=message.from_user)
        
        try:
            await message.bot.send_message(target_id, f"⛔ Вы были заблокированы администратором.\nПричина: {new_reason}\nСвязь: @ch4rov")
        except:
            pass 

    except ValueError:
        await message.answer("ID должен быть числом.")

# --- UNBAN LOGIC ---
@router.message(Command("unban"))
async def cmd_unban(message: types.Message):
    if not is_admin(message.from_user.id): return
    
    try:
        parts = message.text.split()
        if len(parts) < 2: return
        target_id = int(parts[1])
        
        user_data = await get_user(target_id)
        if not user_data or not user_data['is_banned']:
            await message.answer("⚠️ Этот пользователь не забанен.")
            return

        await set_ban_status(target_id, False)
        
        await message.answer(f"✅ Пользователь `{target_id}` разбанен.", parse_mode="Markdown")
        await send_log("ADMIN", f"Разбанил {target_id}", admin=message.from_user)
        
        try:
            await message.bot.send_message(target_id, "✅ Ваш аккаунт разблокирован.")
        except: pass
    except: pass

# --- ANSWER (admin -> user) ---
@router.message(Command("answer"))
async def cmd_answer(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    # Логика: либо ответ на сообщение, либо /answer ID ТЕКСТ
    rest = message.text.partition(' ')[2].strip()
    target_id = None
    text_to_send = None

    if message.reply_to_message and getattr(message.reply_to_message, 'from_user', None):
        if not rest:
            await message.answer("⚠️ Использование (ответ на сообщение): `/answer ТЕКСТ`", parse_mode="Markdown")
            return
        target_id = message.reply_to_message.from_user.id
        text_to_send = rest
    else:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            await message.answer("⚠️ Использование: `/answer ID ТЕКСТ`", parse_mode="Markdown")
            return
        try:
            target_id = int(parts[1])
        except ValueError:
            await message.answer("ID должен быть числом.")
            return
        text_to_send = parts[2]

    if not text_to_send or not target_id:
        return

    send_text = f"📩 Сообщение от администратора:\n\n{text_to_send}"
    try:
        await message.bot.send_message(target_id, send_text)
        await message.answer("✅ Сообщение отправлено.")
        await send_log("ADMIN", f"Отправил сообщение {target_id}: {text_to_send}", admin=message.from_user)
    except exceptions.TelegramAPIError as e:
        await message.answer(f"❌ Не удалось отправить сообщение: {e}")
        await send_log("FAIL", f"Send Error to {target_id}: {e}", admin=message.from_user)

# --- GET PLACEHOLDER (для Inline) ---
@router.message(Command("get_placeholder"))
async def cmd_get_placeholder(message: types.Message):
    if not is_admin(message.from_user.id): return
    
    # Укажи здесь точное имя твоего файла в корне!
    file_path = "placeholder.mp4" 

    if not os.path.exists(file_path):
        await message.answer(f"❌ Файл `{file_path}` не найден в папке бота (рядом с main.py).")
        return

    wait_msg = await message.answer("📤 Загружаю заглушку на сервера Telegram...")

    try:
        # Отправляем видео, чтобы получить его ID
        video = FSInputFile(file_path)
        sent_message = await message.answer_video(video, caption="Вот твоя заглушка")
        
        # Получаем ID
        file_id = sent_message.video.file_id
        
        await wait_msg.delete()
        await message.answer(
            f"✅ **File ID получен!**\n\n"
            f"Скопируй строку ниже и вставь в `handlers/inline.py`:\n\n"
            f"`{file_id}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

# --- CHECK (Тест скачивания) ---
@router.message(Command("check"))
async def cmd_check(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    # Список тестовых ссылок (можешь менять на свои актуальные)
    test_urls = [
        ("TikTok (Video)", "https://vm.tiktok.com/ZMAwhXDAj/"),
        ("TikTok (Photo)", "https://vm.tiktok.com/ZMAwhPq1f/"),
        ("Instagram (Reel)", "https://www.instagram.com/reel/DNQMnTAsR2k/?igsh=dzBranVrYWloM29i"),
        ("YouTube (Video)", "https://youtu.be/dQw4w9WgXcQ"),
        ("YouTube (Music)", "https://music.youtube.com/watch?v=dQw4w9WgXcQ"),
        ("Twitch (Clip)", "https://www.twitch.tv/ch4rov/clip/SmokyDirtyBobaResidentSleeper-geWW-E5kg0Tp-vs8"),
        ("SoundCloud", "https://soundcloud.com/ocqbbed9ek3i/yaryy-tolko-ne-begi"),
    ]

    await message.answer("🔍 Начинаю проверку скачивания со всех платформ...\n(Это может занять время)")

    for idx, (platform_name, url) in enumerate(test_urls, 1):
        # Имитируем отправку ссылки.
        # ВНИМАНИЕ: Мы просто отправляем ссылку в чат. 
        # Если бот (handlers/users.py) слушает этот чат и админа, он автоматически подхватит ссылку
        # и начнет скачивать её, как будто это обычное сообщение.
        
        msg_status = await message.answer(f"⏳ Тест {idx}/{len(test_urls)}: {platform_name}\n📎 Ссылка: {url}")
        
        # Отправляем ссылку, чтобы сработал users.py
        await message.answer(url)
        
        # Даем время на скачивание и отправку (можно увеличить, если инет медленный)
        await asyncio.sleep(5) 
        
        # Обновляем статус (чисто визуально, мы не проверяем результат программно, смотрим глазами)
        await msg_status.edit_text(f"✅ Тест {idx}/{len(test_urls)}: {platform_name} отправлен")
        
        # Пауза перед следующим тестом
        await asyncio.sleep(2)

    await message.answer("✅ Проверка завершена. Проверьте сообщения выше.")