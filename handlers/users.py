import os
from aiogram import Router, F, types
from aiogram.filters import CommandStart, Command
from aiogram.types import FSInputFile
from aiogram.enums import ChatAction
from services.database import add_or_update_user
from services.logger import send_log
from services.downloader import download_video, is_valid_url
import messages as msg 

router = Router()

def is_admin(user_id):
    return str(user_id) == str(os.getenv("ADMIN_ID"))

async def check_access_and_update(user, message: types.Message):
    """
    Возвращает (can_continue: bool, is_new: bool)
    Если бан - пишет сообщение юзеру и возвращает False.
    """
    # Теперь функция возвращает 3 значения!
    is_new, is_banned, ban_reason = await add_or_update_user(user.id, user.username)
    
    if is_banned:
        reason_text = f"\nПричина: {ban_reason}" if ban_reason else ""
        text = f"⛔ Вы заблокированы.{reason_text}\nСвязь с админом: @ch4rov"
        await message.answer(text)
        return False, False
        
    return True, is_new

@router.message(Command("menu"))
async def cmd_menu(message: types.Message):
    can, _ = await check_access_and_update(message.from_user, message)
    if not can: return

    text = msg.MSG_MENU_HEADER + msg.MSG_MENU_USER
    if is_admin(message.from_user.id):
        text += msg.MSG_MENU_ADMIN
    await message.answer(text, parse_mode="Markdown")

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    can, is_new = await check_access_and_update(message.from_user, message)
    if not can: return
    
    await message.answer(msg.MSG_START)
    
    if is_new:
        log_text = f"Новый пользователь: {message.from_user.username} (ID: {message.from_user.id})"
        await send_log("NEW_USER", log_text, user=message.from_user)

@router.message(F.text.contains("http"))
async def handle_link(message: types.Message):
    user = message.from_user
    can, _ = await check_access_and_update(user, message)
    if not can: return
    
    url = message.text.strip()
    
    # SECURITY LOG
    if not is_valid_url(url):
        await message.answer(msg.MSG_ERR_LINK)
        await send_log("SECURITY", f"прислал запрещенную ссылку: <{url}>", user=user)
        return

    # USER REQUEST LOG
    await send_log("USER_REQ", f"<{url}>", user=user)
    status_msg = await message.answer(msg.MSG_WAIT)

    file_path, error = await download_video(url)

    if error:
        await status_msg.edit_text(f"⚠️ Ошибка: {error}")
        await send_log("FAIL", f"Download Fail ({error})", user=user)
        return

    try:
        await status_msg.delete()
        await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_VIDEO)

        video = FSInputFile(file_path)
        await message.answer_video(video, caption=msg.MSG_CAPTION)
        await send_log("SUCCESS", f"Успешно (<{url}>)", user=user)
        
    except Exception as e:
        await message.answer(msg.MSG_ERR_SEND)
        await send_log("FAIL", f"Send Error: {e}", user=user)
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass