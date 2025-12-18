from aiogram import Router
from . import main_start, cookies, video_notes, commands

# Create main router for all user commands
user_router = Router()

# Include all sub-routers
user_router.include_router(main_start.router)
user_router.include_router(commands.user_router)
user_router.include_router(cookies.router)
user_router.include_router(video_notes.router)