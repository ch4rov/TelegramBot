import os
import shutil
import tempfile
import html
import json 
import asyncio 
import time
from uuid import uuid4
from aiogram import Router, F, types, Bot
from aiogram.filters import CommandStart, Command
from aiogram.types import FSInputFile, InputMediaPhoto, InputMediaVideo, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ChatAction

from services.database_service import add_or_update_user, get_cached_file, save_cached_file, set_lastfm_username, save_user_cookie, get_user_cookie
from logs.logger import send_log_groupable as send_log, log_other_message
from services.platforms.platform_manager import download_content, is_valid_url
from services.url_cleaner import clean_url
from services.search_service import search_youtube
import messages as msg 
import settings

router = Router()
ACTIVE_DOWNLOADS = {}
ADMIN_ID = os.getenv("ADMIN_ID")

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def convert_json_to_netscape(json_content: str) -> str:
    try:
        cookies = json.loads(json_content)
        netscape_lines = ["# Netscape HTTP Cookie File"]
        for cookie in cookies:
            domain = cookie.get('domain', '')
            if not domain.startswith('.') and domain.count('.') > 1: domain = '.' + domain
            flag = "TRUE" if domain.startswith('.') else "FALSE"
            path = cookie.get('path', '/')
            secure = "TRUE" if cookie.get('secure') else "FALSE"
            expiration = str(int(cookie.get('expirationDate', time.time() + 31536000)))
            name, value = cookie.get('name', ''), cookie.get('value', '')
            netscape_lines.append(f"{domain}\t{flag}\t{path}\t{secure}\t{expiration}\t{name}\t{value}")
        return "\n".join(netscape_lines)
    except Exception: return None

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

def get_clip_keyboard(url: str):
    if "music.youtube.com" in url or "youtu" in url:
        video_id = None
        if "v=" in url: 
            try: video_id = url.split("v=")[1].split("&")[0]
            except: pass
        elif "youtu.be/" in url: 
            try: video_id = url.split("youtu.be/")[1].split("?")[0]
            except: pass
        if video_id:
            return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎬 Загрузить клип", callback_data=f"get_clip:{video_id}")]])
    return None

async def send_action_loop(bot: Bot, chat_id: int, action: ChatAction, delay: int = 5):
    try:
        while True:
            await bot.send_chat_action(chat_id=chat_id, action=action)
            await asyncio.sleep(delay)
    except asyncio.CancelledError: pass

# --- КОМАНДЫ ---

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    can, is_new = await check_access_and_update(message.from_user, message)
    if not can: return
    
    bot_info = await message.bot.get_me()
    welcome_text = f"👋 Привет, {html.escape(message.from_user.first_name)}!\nЯ скачиваю музыку и видео с популярных площадок.\n"
    await message.answer(welcome_text, parse_mode="HTML")
    
    is_admin_user = str(message.from_user.id) == str(ADMIN_ID)
    text = "🤖 <b>Меню команд</b>\n\n"
    def format_cmd(cmd, desc, copy):
        if copy: return f"🔹 <code>/{cmd}</code> — {desc}\n"
        return f"🔹 /{cmd} — {desc}\n"

    text += "👤 <b>Для всех:</b>\n"
    for cmd, desc, cat, copy in settings.BOT_COMMANDS_LIST:
        if cat == "user": text += format_cmd(cmd, desc, copy)

    if is_admin_user:
        text += "\n🛡 <b>Модерация:</b>\n"
        for cmd, desc, cat, copy in settings.BOT_COMMANDS_LIST:
            if cat == "admin_mod": text += format_cmd(cmd, desc, copy).replace("🔹", "🔸")
        text += "\n⚙️ <b>Технические:</b>\n"
        for cmd, desc, cat, copy in settings.BOT_COMMANDS_LIST:
            if cat == "admin_tech": text += format_cmd(cmd, desc, copy).replace("🔹", "🔧")

    await message.answer(text, parse_mode="HTML")
    if is_new: await send_log("NEW_USER", f"New: {message.from_user.full_name} (ID: {message.from_user.id})", user=message.from_user)

@router.message(Command("menu"))
async def cmd_menu(message: types.Message):
    await cmd_start(message)

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

@router.message(F.document)
async def handle_document(message: types.Message):
    file_name = message.document.file_name
    if not file_name: return
    if file_name.lower().endswith(('.txt', '.json')):
        if "cookie" not in file_name.lower(): return
        can, _ = await check_access_and_update(message.from_user, message)
        if not can: return
        file = await message.bot.get_file(message.document.file_id)
        res = await message.bot.download_file(file.file_path)
        content = res.read().decode('utf-8', errors='ignore')
        if content.strip().startswith(('[', '{')):
            converted = convert_json_to_netscape(content)
            if converted: content = converted
        await save_user_cookie(message.from_user.id, content)
        await message.answer("🍪 <b>Куки сохранены!</b>", parse_mode="HTML")
        await send_log("INFO", f"User uploaded cookies ({file_name})", user=message.from_user)

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
        url_raw, caption_override = parts[0].strip(), parts[1].strip()
    
    for c in [';', '\n', ' ', '$', '`', '|']: 
        if c in url_raw: url_raw = url_raw.split(c)[0]
    url = clean_url(url_raw)

    if not is_valid_url(url):
        await message.answer(msg.MSG_ERR_LINK)
        return

    # 1. SMART CACHE
    db_cache = await get_cached_file(url)
    if db_cache:
        try:
            caption = make_caption(db_cache['title'], url, caption_override)
            if db_cache['media_type'] == 'audio':
                markup = get_clip_keyboard(url)
                await message.answer_audio(db_cache['file_id'], caption=caption, parse_mode="HTML", reply_markup=markup)
            elif db_cache['media_type'] == 'video': 
                await message.answer_video(db_cache['file_id'], caption=caption, parse_mode="HTML")
            elif db_cache['media_type'] == 'photo': 
                await message.answer_photo(db_cache['file_id'], caption=caption, parse_mode="HTML")
            await send_log("SUCCESS", f"Успешно [DB CACHE] (<{url}>)", user=user)
            return
        except: pass

    # 2. ЗАГРУЗКА
    if ACTIVE_DOWNLOADS.get(user.id, 0) >= settings.MAX_CONCURRENT_DOWNLOADS:
        await message.answer("⚠️ Слишком много загрузок.")
        return
    ACTIVE_DOWNLOADS[user.id] = ACTIVE_DOWNLOADS.get(user.id, 0) + 1
    
    await send_log("USER_REQ", f"<{url}>", user=user)
    status_msg = await message.answer("⏳")

    files, folder_path, error = await download_content(url)

    # --- ОБРАБОТКА ОШИБОК ---
    if error:
        err_str = str(error).lower()
        auth_markers = ["sign in", "login", "private", "access", "blocked", "followers", "confirm", "captcha", "unsupported url"]
        if any(m in err_str for m in auth_markers):
            user_cookies = await get_user_cookie(user.id)
            if user_cookies:
                await status_msg.edit_text("🔐 Доступ ограничен. Использую ваши куки...")
                files, folder_path, error = await download_content(url, {'user_cookie_content': user_cookies})
            else:
                await message.answer("🔒 <b>Требуется доступ.</b>\nПришлите файл <code>cookies.txt</code>.", parse_mode="HTML")
                await status_msg.delete()
                if user.id in ACTIVE_DOWNLOADS: del ACTIVE_DOWNLOADS[user.id]
                return

        if error and ("too large" in err_str or "larger than" in err_str) and not settings.USE_LOCAL_SERVER:
            await status_msg.edit_text("⚠️ Файл > 50 МБ. Пробую сжать...")
            low_opts = {'format': 'worst[ext=mp4]+bestaudio[ext=m4a]/worst[ext=mp4]/worst', 'user_cookie_content': await get_user_cookie(user.id)}
            files, folder_path, error = await download_content(url, low_opts)
            if error: error = "Даже в низком качестве файл слишком большой (>50 МБ)."
        
    if error:
        await status_msg.edit_text(f"⚠️ {error}")
        await send_log("FAIL", f"Fail: {error}", user=user)
        if user.id in ACTIVE_DOWNLOADS: del ACTIVE_DOWNLOADS[user.id]
        return
        
    # --- МЕТАДАННЫЕ ---
    resolution_text = ""
    name_no_ext = ""
    vid_width, vid_height = None, None
    
    info_json_file = next((f for f in files if f.endswith(('.info.json'))), None)
    if info_json_file:
        try:
            with open(info_json_file, 'r', encoding='utf-8') as f:
                info = json.load(f)
                height, width = info.get('height'), info.get('width')
                if height and width:
                    vid_height, vid_width = height, width
                    res_str = "1080p" if height >= 1080 else f"{height}p"
                    resolution_text = f" ({res_str})"
                title = info.get('title')
                if title: name_no_ext = title
        except: pass
    
    # 3. ОТПРАВКА
    action_task = None
    try:
        video_exts = ['.mp4', '.mov', '.mkv', '.webm', '.ts']
        audio_exts = ['.mp3', '.ogg', '.wav', '.m4a', '.flac', '.webm']
        image_exts = ['.jpg', '.jpeg', '.png', '.webp']
        
        media_files = [f for f in files if f.endswith(tuple(video_exts + audio_exts + image_exts))]
        
        # Типы
        is_tiktok_photo = "tiktok" in url and "/photo/" in url
        is_video_url = any(x in url for x in ['youtube', 'youtu.be', 'vk.com', 'reel', '/video/', 'twitch']) and not is_tiktok_photo
        
        # Фильтр картинок для видео
        if is_video_url:
             media_files = [f for f in media_files if not f.endswith(tuple(image_exts))]

        if not media_files: raise Exception("No media files found")

        target = media_files[0]
        fname = os.path.basename(target)
        if not name_no_ext: name_no_ext = os.path.splitext(fname)[0]
        ext = os.path.splitext(target)[1].lower()
        
        final_title = f"{name_no_ext}{resolution_text}"
        caption = make_caption(final_title, url, caption_override)
        
        sent_msg = None
        m_type = None 

        # СЦЕНАРИЙ 1: СЛАЙДШОУ
        if is_tiktok_photo and len([f for f in media_files if f.endswith(tuple(image_exts))]) > 1:
            await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_PHOTO)
            
            image_files = [f for f in media_files if f.endswith(tuple(image_exts))]
            audio_file = next((f for f in media_files if f.endswith(tuple(audio_exts))), None)
            
            media_group = []
            for i, img in enumerate(image_files[:10]):
                cap = caption if i == 0 else None
                media_group.append(InputMediaPhoto(media=FSInputFile(img), caption=cap, parse_mode="HTML"))
            
            await message.answer_media_group(media_group)
            
            if audio_file:
                await message.answer_audio(FSInputFile(audio_file), caption="🎵 Sound", performer="@ch4roff_bot")
            
            await send_log("SUCCESS", f"TikTok Carousel (<{url}>)", user=user)
            await status_msg.delete()
            return

        # СЦЕНАРИЙ 2: АУДИО
        if ext in audio_exts:
            await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_VOICE)
            performer, title = "@ch4roff_bot", final_title
            if " - " in final_title:
                p = final_title.split(" - ", 1)
                performer, title = p[0], p[1]
            
            thumb = next((f for f in files if f.endswith(('.jpg', '.png'))), None)
            reply_markup = get_clip_keyboard(url)

            sent_msg = await message.answer_audio(
                FSInputFile(target), caption=caption, parse_mode="HTML",
                thumbnail=FSInputFile(thumb) if thumb else None,
                performer=performer, title=title,
                reply_markup=reply_markup
            )
            m_type = "audio"

        # СЦЕНАРИЙ 3: ВИДЕО
        elif ext in video_exts:
            action_task = asyncio.create_task(send_action_loop(message.bot, message.chat.id, ChatAction.UPLOAD_VIDEO))
            sent_msg = await message.answer_video(
                FSInputFile(target), caption=caption, parse_mode="HTML",
                thumbnail=None, 
                supports_streaming=True,
                width=vid_width, height=vid_height
            )
            m_type = "video"
        
        # СЦЕНАРИЙ 4: ФОТО
        else:
            sent_msg = await message.answer_photo(FSInputFile(target), caption=caption, parse_mode="HTML")
            m_type = "photo"

        await send_log("SUCCESS", f"Успешно (<{url}>)", user=user)
        
        if sent_msg and m_type:
            fid = None
            if m_type == "video": fid = sent_msg.video.file_id
            elif m_type == "audio": fid = sent_msg.audio.file_id
            elif m_type == "photo": fid = sent_msg.photo[-1].file_id
            if fid: await save_cached_file(url, fid, m_type, title=name_no_ext) 

        await status_msg.delete() 

    except Exception as e:
        if "Request timeout error" in str(e):
            await send_log("WARN", f"Timeout: {e}", user=user)
        else:
            await message.answer(f"⚠️ Ошибка отправки файла. {e}")
            await send_log("FAIL", f"Send Error: {e}", user=user)
    finally:
        if action_task: action_task.cancel()
        if ACTIVE_DOWNLOADS.get(user.id) > 0: ACTIVE_DOWNLOADS[user.id] -= 1
        if folder_path and os.path.exists(folder_path): shutil.rmtree(folder_path, ignore_errors=True)

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
    await message.answer(f"🔎 <b>Поиск:</b>\n<code>{txt}</code>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")