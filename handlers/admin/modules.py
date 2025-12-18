# -*- coding: utf-8 -*-
import logging
from aiogram import Router, types
from aiogram.filters import Command, CommandObject
from handlers.admin.filters import AdminFilter
from services.database.repo import get_module_status, set_module_status
from settings import MODULES_LIST

logger = logging.getLogger(__name__)
router = Router()
router.message.filter(AdminFilter())

@router.message(Command("modules"))
async def cmd_modules(message: types.Message, command: CommandObject):
    """Управление модулями: /modules [MODULE_NAME]"""
    try:
        # Если нет аргументов - показываем список модулей
        if not command.args:
            text = "Available Modules:\n\n"
            for module in MODULES_LIST:
                status = await get_module_status(module)
                status_emoji = "✅" if status else "❌"
                text += f"{status_emoji} `{module}` - `/modules {module}`\n"
            
            await message.answer(text, parse_mode="Markdown", disable_notification=True)
            logger.info(f"Admin {message.from_user.id} viewed modules list")
            return
        
        # Если есть аргумент - переключаем модуль
        module_name = command.args.strip()
        
        if module_name not in MODULES_LIST:
            await message.answer(f"Unknown module: {module_name}", disable_notification=True)
            return
        
        # Получаем текущий статус и переключаем
        current_status = await get_module_status(module_name)
        new_status = not current_status
        await set_module_status(module_name, new_status)
        
        status_text = "enabled" if new_status else "disabled"
        await message.answer(f"Module {module_name} is now {status_text}", disable_notification=True)
        logger.info(f"Admin {message.from_user.id} toggled {module_name} to {new_status}")
        
    except Exception as e:
        logger.error(f"Error in /modules: {e}")
        await message.answer("Error managing modules", disable_notification=True)
