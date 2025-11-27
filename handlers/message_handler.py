import os
import shutil
import tempfile
import html
import json 
import asyncio 
from uuid import uuid4
from aiogram import Router, F, types, Bot
from aiogram.filters import CommandStart, Command
from aiogram.types import FSInputFile, InputMediaPhoto, InputMediaVideo
from aiogram.enums import ChatAction

from services.database_service import add_or_update_user, get_cached_file, save_cached_file, set_lastfm_username, save_user_cookie, get_user_cookie
from logs.logger import send_log_groupable as send_log, log_other_message
from services.downloads import download_content, is_valid_url
# services.cache_service БОЛЬШЕ НЕ ИМПОРТИРУЕМ
from services.url_cleaner import clean_url
from services.search_service import search_youtube
import messages as msg 
import settings

router = Router()
ACTIVE_DOWNLOADS = {}
ADMIN_ID = os.getenv("ADMIN_ID")

async def check_access_and_update(user, message: types.Message):
    is_new, is_banned, ban_reason = await add_or_update_user(user.id, user.username)
    if is_banned:
        await message.answer(f"⛔ Вы заблокированы.\nПричина: {ban_reason}")
        return False, False
    return True, is_new

def make_caption(title_text, url, override=None):
    bot_link = "@ch4roff_bot"
    if override:
        safe_override = html.escape(override)
        return f"{safe_override}\n\n{bot_link}"
    if not title_text:
        return bot_link
    safe_title = html.escape(title_text)
    return f'<a href="{url}">{safe_title}</a>\n\n{bot_link}'

# --- ФУНКЦИЯ ДЛЯ НЕПРЕРЫВНОГО СТАТУСА ---
async def send_action_loop(bot: Bot, chat_id: int, action: ChatAction, delay: int = 5):
    try:
        while True:
            await bot.send_chat_action(chat_id=chat_id, action=action)
            await asyncio.sleep(delay)
    except asyncio.CancelledError:
        pass

# --- КОМАНДЫ ---
@router.message(Command("menu"))
async def cmd_menu(message: types.Message):
    can, _ = await check_access_and_update(message.from_user, message)
    if not can: return
    text = msg.MSG_MENU_HEADER + msg.MSG_MENU_USER
    if str(message.from_user.id) == str(ADMIN_ID):
        text += msg.MSG_MENU_ADMIN
    await message.answer(text, parse_mode="Markdown")

@router.message(Command("login"))
async def cmd_login(message: types.Message):
    can, _ = await check_access_and_update(message.from_user, message)
    if not can: return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("🔑 <b>Авторизация Last.fm</b>\nУкажите ник:\n<code>/login ваш_ник</code>", parse_mode="HTML")
        return
    lfm_username = parts[1]
    await set_lastfm_username(message.from_user.id, lfm_username)
    await message.answer(f"✅ Профиль <b>{lfm_username}</b> привязан!", parse_mode="HTML")

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    can, is_new = await check_access_and_update(message.from_user, message)
    if not can: return
    await message.answer(msg.MSG_START)
    if is_new:
        await send_log("NEW_USER", f"New: {message.from_user.full_name} (ID: {message.from_user.id})", user=message.from_user)
        if ADMIN_ID:
            try: await message.bot.send_message(ADMIN_ID, f"🔔 New User: {message.from_user.full_name}")
            except: pass

@router.message(F.document)
async def handle_document(message: types.Message):
    if message.document.file_name and message.document.file_name.lower() == "cookies.txt":
        can, _ = await check_access_and_update(message.from_user, message)
        if not can: return
        file = await message.bot.get_file(message.document.file_id)
        res = await message.bot.download_file(file.file_path)
        await save_user_cookie(message.from_user.id, res.read().decode('utf-8', errors='ignore'))
        await message.answer("🍪 <b>Куки сохранены!</b>\nТеперь я смогу качать видео из закрытых групп.", parse_mode="HTML")
        await send_log("INFO", "User uploaded cookies.txt", user=message.from_user)

# --- ОБРАБОТКА ССЫЛОК ---
@router.message(F.text.contains("http"))
async def handle_link(message: types.Message):
    user = message.from_user
    can, _ = await check_access_and_update(user, message)
    if not can: return
    
    url_raw = message.text.strip()
    caption_override = None
    if "|" in url_raw:
        parts = url_raw.split("|", 1)
        url_raw = parts[0].strip()
        caption_override = parts[1].strip()
    
    for c in [';', '\n', ' ', '$', '`', '|']: 
        if c in url_raw: url_raw = url_raw.split(c)[0]
    url = clean_url(url_raw)

    if not is_valid_url(url):
        await message.answer(msg.MSG_ERR_LINK)
        return

    # 1. SMART CACHE (БД: File ID)
    db_cache = await get_cached_file(url)
    if db_cache:
        try:
            caption = make_caption(db_cache['title'], url, caption_override)
            if db_cache['media_type'] == 'video': await message.answer_video(db_cache['file_id'], caption=caption, parse_mode="HTML")
            elif db_cache['media_type'] == 'audio': await message.answer_audio(db_cache['file_id'], caption=caption, parse_mode="HTML")
            elif db_cache['media_type'] == 'photo': await message.answer_photo(db_cache['file_id'], caption=caption, parse_mode="HTML")
            await send_log("SUCCESS", f"Успешно [DB CACHE] (<{url}>)", user=user)
            return
        except: pass

    # 2. ЗАГРУЗКА (ЕСЛИ НЕТ В БАЗЕ)
    if ACTIVE_DOWNLOADS.get(user.id, 0) >= settings.MAX_CONCURRENT_DOWNLOADS:
        await message.answer("⚠️ Слишком много загрузок.")
        return
    ACTIVE_DOWNLOADS[user.id] = ACTIVE_DOWNLOADS.get(user.id, 0) + 1
    
    await send_log("USER_REQ", f"<{url}>", user=user)
    
    # Статус
    status_msg = await message.answer("⏳")

    files, folder_path, error = await download_content(url)

    # --- ОБРАБОТКА ОШИБОК ---
    if error:
        err_str = str(error).lower()
        auth_markers = ["sign in", "login", "private", "access", "blocked", "followers", "confirm"]
        if any(m in err_str for m in auth_markers):
            user_cookies = await get_user_cookie(user.id)
            if user_cookies:
                await status_msg.edit_text("🔐 Доступ ограничен. Использую ваши куки...")
                files, folder_path, error = await download_content(url, {'user_cookie_content': user_cookies})
            else:
                await message.answer("🔒 <b>Ошибка доступа (Приватный контент).</b>\nПришлите файл <code>cookies.txt</code>.", parse_mode="HTML")
                await status_msg.delete()
                if user.id in ACTIVE_DOWNLOADS: del ACTIVE_DOWNLOADS[user.id]
                return

        if error and ("too large" in err_str or "larger than" in err_str) and not settings.USE_LOCAL_SERVER:
            await status_msg.edit_text("⚠️ Файл > 50 МБ. Пробую сжать...")
            low_quality_opts = {'format': 'worst[ext=mp4]+bestaudio[ext=m4a]/worst[ext=mp4]/worst', 'user_cookie_content': await get_user_cookie(user.id)}
            files, folder_path, error = await download_content(url, low_quality_opts)
            if error: error = "Даже в низком качестве файл слишком большой (>50 МБ)."
        
    if error:
        await status_msg.edit_text(f"⚠️ {error}")
        await send_log("FAIL", f"Fail: {error}", user=user)
        if user.id in ACTIVE_DOWNLOADS: del ACTIVE_DOWNLOADS[user.id]
        return
        
    # --- МЕТАДАННЫЕ ---
    resolution_text = ""
    name_no_ext = ""
    vid_width = None
    vid_height = None
    
    info_json_file = next((f for f in files if f.endswith(('.info.json'))), None)
    if info_json_file:
        try:
            with open(info_json_file, 'r', encoding='utf-8') as f:
                info = json.load(f)
                height = info.get('height')
                width = info.get('width')
                if height and width:
                    vid_height = height
                    vid_width = width
                    if height >= 1080: res_str = "1080p"
                    else: res_str = f"{height}p"
                    resolution_text = f" ({res_str})"
                title = info.get('title')
                if title: name_no_ext = title
        except Exception as e: pass
    
    # 3. ОТПРАВКА
    action_task = None
    try:
        media_files = [f for f in files if f.endswith(('.mp4', '.mov', '.mkv', '.mp3', '.ogg', '.wav', '.jpg', '.png'))]
        if not media_files: raise Exception("No media")

        target = media_files[0]
        fname = os.path.basename(target)
        if not name_no_ext: name_no_ext = os.path.splitext(fname)[0]
        ext = os.path.splitext(target)[1].lower()
        
        final_title = f"{name_no_ext}{resolution_text}"
        caption = make_caption(final_title, url, caption_override)
        
        sent_msg = None
        m_type = None 

        # Аудио
        if ext in ['.mp3', '.ogg', '.wav']:
            await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_VOICE)
            performer = "@ch4roff_bot"
            title = final_title
            if " - " in final_title:
                p = final_title.split(" - ", 1)
                performer, title = p[0], p[1]
            
            thumb = next((f for f in files if f.endswith(('.jpg', '.png'))), None)
            
            sent_msg = await message.answer_audio(
                FSInputFile(target), caption=caption, parse_mode="HTML",
                thumbnail=FSInputFile(thumb) if thumb else None,
                performer=performer, title=title
            )
            m_type = "audio"

        # Видео
        elif ext in ['.mp4', '.mov', '.mkv']:
            action_task = asyncio.create_task(send_action_loop(message.bot, message.chat.id, ChatAction.UPLOAD_VIDEO))
            
            sent_msg = await message.answer_video(
                FSInputFile(target), caption=caption, parse_mode="HTML",
                thumbnail=None,
                supports_streaming=True,
                width=vid_width,
                height=vid_height
            )
            m_type = "video"
        
        # Фото
        else:
            sent_msg = await message.answer_photo(FSInputFile(target), caption=caption, parse_mode="HTML")
            m_type = "photo"

        await send_log("SUCCESS", f"Успешно (<{url}>)", user=user)
        
        # Кэшируем ID для следующего раза
        if sent_msg and m_type:
            fid = None
            if m_type == "video": fid = sent_msg.video.file_id
            elif m_type == "audio": fid = sent_msg.audio.file_id
            elif m_type == "photo": fid = sent_msg.photo[-1].file_id
            
            if fid: await save_cached_file(url, fid, m_type, title=name_no_ext) 

        # Удаляем сообщение "⏳"
        await status_msg.delete() 

    except Exception as e:
        if "Request timeout error" in str(e):
            await send_log("WARN", f"Send Timeout (file sent?): {e}", user=user)
        else:
            await message.answer(f"⚠️ Ошибка отправки файла. {e}")
            await send_log("FAIL", f"Send Error: {e}", user=user)
    finally:
        if action_task: action_task.cancel()
        if ACTIVE_DOWNLOADS.get(user.id) > 0: ACTIVE_DOWNLOADS[user.id] -= 1
        
        # УДАЛЯЕМ ПАПКУ (Файловый кэш нам не нужен)
        if folder_path and os.path.exists(folder_path): shutil.rmtree(folder_path, ignore_errors=True)

# --- ПОИСК ПО ТЕКСТУ ---
@router.message(F.text & ~F.text.contains("http"))
async def handle_plain_text(message: types.Message):
    user = message.from_user
    if not message.text: return
    txt = message.text.strip()
    if not txt or txt.startswith("/"): return
    can, _ = await check_access_and_update(user, message)
    if not can: return
    try: await log_other_message(txt, user=user)
    except: pass

    await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    results = await search_youtube(txt, limit=5)
    
    if not results:
        await message.answer(f"🔍 Ничего не найдено: {txt}")
        return

    buttons = []
    for res in results:
        full_title = f"{res['title']} ({res['duration']})"
        if len(full_title) > 50: full_title = full_title[:47] + "..."
        source = res.get('source', 'YT')
        buttons.append([InlineKeyboardButton(text=full_title, callback_data=f"music:{source}:{res['id']}")])
    
    buttons.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="delete_msg")])
    
    await message.answer(
        f"🔎 <b>Результаты поиска:</b>\n<code>{txt}</code>", 
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )