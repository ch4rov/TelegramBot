import os
import settings
from aiohttp import web
from services.database_service import get_all_users

async def handle_index(request):
    return web.Response(text="<h1>Telegram Bot Dashboard</h1><a href='/stats'>Stats</a> | <a href='/logs'>Logs</a>", content_type='text/html')

async def handle_stats(request):
    users = await get_all_users()
    html = "<h1>Statistics</h1>"
    html += f"<p>Total Users: {len(users)}</p>"
    html += "<ul>"
    for u in users[:50]:
        html += f"<li>{u['user_id']} - {u['username']}</li>"
    html += "</ul>"
    return web.Response(text=html, content_type='text/html')

async def handle_logs(request):
    log_path = os.path.join("logs", "files", "full_log.txt")
    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8") as f:
            # Читаем последние 100 строк
            lines = f.readlines()[-100:]
            content = "<br>".join(lines)
    else:
        content = "No logs yet."
    return web.Response(text=f"<h1>Live Logs</h1><pre>{content}</pre>", content_type='text/html')

def setup_web_app():
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/stats', handle_stats)
    app.router.add_get('/logs', handle_logs)
    return app

async def run_web_server():
    if not settings.ENABLE_WEB_DASHBOARD: return
    app = setup_web_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, settings.WEB_SERVER_HOST, settings.WEB_SERVER_PORT)
    await site.start()
    print(f"🌍 [WEB] Dashboard started on http://{settings.WEB_SERVER_HOST}:{settings.WEB_SERVER_PORT}")