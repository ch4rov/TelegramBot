from .router import user_router
from . import main_start, cookies, video_notes, links, text_search

# Import modules that register handlers directly on user_router
from . import commands  # noqa: F401

# Include sub-routers (separate Router instances)
user_router.include_router(main_start.router)
user_router.include_router(cookies.router)
user_router.include_router(video_notes.router)
user_router.include_router(links.links_router)
user_router.include_router(text_search.router)