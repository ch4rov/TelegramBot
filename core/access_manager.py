"""Access control and authorization management"""
import os
from aiogram import types
from services.database_service import add_or_update_user


class AccessManager:
    """Unified access control for users and admins"""

    @staticmethod
    def get_admin_id() -> str:
        """Get admin ID from environment"""
        return os.getenv("ADMIN_ID", "")

    @staticmethod
    def is_admin(user_id: int) -> bool:
        """Check if user is admin"""
        admin_id = AccessManager.get_admin_id()
        return str(user_id) == str(admin_id) if admin_id else False

    @staticmethod
    async def check_user_access(user_id: int, username: str):
        """Check user access and update DB (returns: is_new, is_banned, ban_reason)"""
        is_new, is_banned, ban_reason = await add_or_update_user(user_id, username)
        return is_new, is_banned, ban_reason

    @staticmethod
    async def ensure_user_access(user: types.User, message: types.Message) -> tuple:
        """
        Ensure user has access (check ban status).
        Returns: (can_proceed: bool, is_new: bool)
        """
        is_new, is_banned, ban_reason = await AccessManager.check_user_access(user.id, user.username)
        
        if is_banned:
            reason_text = f"\nПричина: {ban_reason}" if ban_reason else ""
            text = f"⛔ Вы заблокированы.{reason_text}\nСвязь с админом: @ch4rov"
            await message.answer(text)
            return False, is_new
        
        return True, is_new

    @staticmethod
    def ensure_admin(user_id: int) -> bool:
        """Check if user is admin, return True/False"""
        return AccessManager.is_admin(user_id)
