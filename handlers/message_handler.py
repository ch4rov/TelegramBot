"""Message handler - processes user links and text messages"""
import os
import shutil
from aiogram import Router, F, types
from aiogram.filters import CommandStart, Command
from aiogram.types import FSInputFile, InputMediaPhoto, InputMediaVideo
from aiogram.enums import ChatAction

from core.access_manager import AccessManager
from core.media_sender import MediaSender
from core.queue_manager import queue_manager
from services.database_service import add_or_update_user, get_cached_file, save_cached_file
from services.logger_service import send_log_groupable as send_log, log_other_message
from services.downloads import download_content, is_valid_url
from services.cache_service import get_cached_content, add_to_cache
from services.url_cleaner import clean_url
import messages as msg 
import settings

router = Router()
ACTIVE_DOWNLOADS = {}


async def _process_link(message: types.Message, url: str, media_sender: MediaSender):
    """Extract common link processing logic"""
    user = message.from_user
    
    # Check access
    can_proceed, _ = await AccessManager.ensure_user_access(user, message)
    if not can_proceed:
        return
    
    # Clean URL
    url = clean_url(url)
    
    if not is_valid_url(url):
        await message.answer(msg.MSG_ERR_LINK)
        await send_log("SECURITY", f"bad link: <{url}>", user=user)
        return

    # 1. SMART CACHE
    db_cache = await get_cached_file(url)
    
    def make_caption(title, link):
        bot_link = "@ch4roff_bot"
        if not title:
            return bot_link
        safe_title = str(title).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return f'<a href="{link}">{safe_title}</a>\n\n{bot_link}'

    if db_cache:
        file_id = db_cache['file_id']
        media_type = db_cache['media_type']
        saved_title = db_cache['title']
        
        caption_html = make_caption(saved_title, url)
        
        await send_log("SUCCESS", f"Успешно [DB CACHE] (<{url}>)", user=user)
        try:
            if media_type == 'audio':
                await message.answer_audio(file_id, caption=caption_html, parse_mode="HTML")
            elif media_type == 'video':
                await message.answer_video(file_id, caption=caption_html, parse_mode="HTML")
            elif media_type == 'photo':
                await message.answer_photo(file_id, caption=caption_html, parse_mode="HTML")
            return 
        except Exception:
            pass

    # 2. DOWNLOAD
    cached_files, cached_folder = await get_cached_content(url)
    
    if cached_files:
        files = cached_files
        folder_path = cached_folder 
        from_cache = True
    else:
        from_cache = False
        if ACTIVE_DOWNLOADS.get(user.id, 0) >= settings.MAX_CONCURRENT_DOWNLOADS:
            await message.answer("⚠️ Слишком много загрузок. Подождите.")
            return

        ACTIVE_DOWNLOADS[user.id] = ACTIVE_DOWNLOADS.get(user.id, 0) + 1
        await send_log("USER_REQ", f"<{url}>", user=user)
        await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)

        # Show loading indicator
        try:
            await message.answer("⏳")
        except:
            pass

        files, folder_path, error = await download_content(url)

        if error:
            await message.answer(f"⚠️ {error}")
            await send_log("FAIL", f"Fail: {error}", user=user)
            
            admin_id = AccessManager.get_admin_id()
            if admin_id and str(user.id) == str(admin_id):
                try:
                    await message.bot.send_message(admin_id, f"❌ Error:\n{url}\n{error}")
                except:
                    pass

            if user.id in ACTIVE_DOWNLOADS:
                if ACTIVE_DOWNLOADS[user.id] > 0:
                    ACTIVE_DOWNLOADS[user.id] -= 1
                else:
                    del ACTIVE_DOWNLOADS[user.id]
            return

    # 3. SEND MEDIA
    try:
        media_files = []
        thumb_file = None
        
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                thumb_file = f
            elif ext in ['.mp4', '.mov', '.mkv', '.webm', '.ts', '.mp3', '.m4a', '.ogg', '.wav']:
                media_files.append(f)

        image_exts = ['.jpg', '.jpeg', '.png', '.webp']
        video_exts = ['.mp4', '.mov', '.mkv', '.webm', '.ts']
        
        if not media_files and thumb_file:
            media_files = [f for f in files if os.path.splitext(f)[1].lower() in image_exts]
            thumb_file = None

        if not media_files:
            raise Exception("Files not found")

        # Priority: video over other formats
        has_video = any(os.path.splitext(f)[1].lower() in video_exts for f in media_files)
        if has_video:
            media_files = [f for f in media_files if os.path.splitext(f)[1].lower() in video_exts]

        filename_no_ext = os.path.splitext(os.path.basename(media_files[0]))[0]
        final_caption = make_caption(filename_no_ext, url)

        # Send media
        sent_msg = await media_sender.send_media(
            chat_id=message.chat.id,
            file_path=media_files[0],
            caption=final_caption,
            thumb_file=thumb_file
        )

        prefix = "[КЭШ] " if from_cache else ""
        await send_log("SUCCESS", f"{prefix}Успешно (<{url}>)", user=user)

        if sent_msg:
            # Determine media type and get file_id
            ext = os.path.splitext(media_files[0])[1].lower()
            if ext in video_exts:
                media_type_str = 'video'
            elif ext in ['.mp3', '.m4a', '.ogg', '.wav']:
                media_type_str = 'audio'
            elif ext in image_exts:
                media_type_str = 'photo'
            else:
                media_type_str = None
            
            if media_type_str:
                fid = await media_sender.get_file_id(sent_msg, media_type_str)
                if fid:
                    await save_cached_file(url, fid, media_type_str, title=filename_no_ext)

        if not from_cache and folder_path:
            await add_to_cache(url, folder_path, files)
        
        # Mark as processed in queue
        queue_manager.mark_as_processed(user.id, url)

    except Exception as e:
        await message.answer(msg.MSG_ERR_SEND)
        await send_log("FAIL", f"Send Error: {e}", user=user)
        if not from_cache and folder_path and os.path.exists(folder_path):
            shutil.rmtree(folder_path, ignore_errors=True)
    
    finally:
        if not from_cache:
            if user.id in ACTIVE_DOWNLOADS:
                if ACTIVE_DOWNLOADS[user.id] > 0:
                    ACTIVE_DOWNLOADS[user.id] -= 1
                else:
                    del ACTIVE_DOWNLOADS[user.id]


@router.message(Command("menu"))
async def cmd_menu(message: types.Message):
    can_proceed, _ = await AccessManager.ensure_user_access(message.from_user, message)
    if not can_proceed:
        return
    
    text = msg.MSG_MENU_HEADER + msg.MSG_MENU_USER
    if AccessManager.is_admin(message.from_user.id):
        text += msg.MSG_MENU_ADMIN
    await message.answer(text, parse_mode="Markdown")


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    can_proceed, is_new = await AccessManager.ensure_user_access(message.from_user, message)
    if not can_proceed:
        return
    
    await message.answer(msg.MSG_START)
    if is_new:
        await send_log("NEW_USER", f"New: {message.from_user.full_name} (ID: {message.from_user.id})", 
                      user=message.from_user)
        admin_id = AccessManager.get_admin_id()
        if admin_id:
            try:
                await message.bot.send_message(admin_id, f"🔔 New User: {message.from_user.full_name}")
            except:
                pass


@router.message(F.text.contains("http"))
async def handle_link(message: types.Message):
    media_sender = MediaSender(message.bot)
    
    url_raw = message.text.strip()
    
    # Save to queue for crash recovery
    queue_manager.add_message(
        user_id=message.from_user.id,
        text=url_raw,
        message_id=message.message_id,
        chat_id=message.chat.id,
        username=message.from_user.username
    )
    
    # Clean from injections
    for bad_char in [';', '\n', ' ', '$', '`', '|']:
        if bad_char in url_raw:
            url_raw = url_raw.split(bad_char)[0]
    
    await _process_link(message, url_raw, media_sender)


@router.message(F.text & ~F.text.contains("http"))
async def handle_plain_text(message: types.Message):
    user = message.from_user
    if not message.text:
        return
    
    txt = message.text.strip()
    if not txt or txt.startswith("/"):
        return
    
    can_proceed, _ = await AccessManager.ensure_user_access(user, message)
    if not can_proceed:
        return
    
    try:
        await log_other_message(txt, user=user)
    except:
        pass
