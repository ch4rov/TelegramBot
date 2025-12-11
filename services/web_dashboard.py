import os
import time
import sys
import platform
import shutil
import aiohttp
from aiohttp import web
import json
import re
import asyncio
from datetime import datetime
import settings
from services.database_service import (
    get_all_users, get_module_status, set_module_status, 
    get_stats_period, get_user_logs, get_global_stats,
    get_system_value, get_user, web_ban_user, web_unban_user
)
from logs.logger import send_log
from core.queue_manager import queue_manager
from loader import bot

# --- HTML TEMPLATE ---
HTML_BASE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bot Admin</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {{ --bg: #131314; --sidebar: #1E1E1E; --card: #2C2C2E; --text: #FFF; --text-sec: #AAA; --accent: #0A84FF; --green: #30D158; --red: #FF453A; --border: #3A3A3C; --msg-in: #262628; --msg-out: #0A84FF; }}
        body {{ background: var(--bg); color: var(--text); font-family: 'Inter', sans-serif; margin: 0; display: flex; height: 100vh; overflow: hidden; }}
        
        ::-webkit-scrollbar {{ width: 8px; }}
        ::-webkit-scrollbar-track {{ background: var(--bg); }}
        ::-webkit-scrollbar-thumb {{ background: #444; border-radius: 4px; }}

        .sidebar {{ width: 260px; background: var(--sidebar); padding: 20px; display: flex; flex-direction: column; border-right: 1px solid var(--border); flex-shrink: 0; }}
        .nav-link {{ color: var(--text-sec); text-decoration: none; padding: 12px; border-radius: 8px; margin-bottom: 5px; display: block; transition: .2s; }}
        .nav-link:hover, .nav-link.active {{ background: rgba(255,255,255,0.1); color: var(--text); }}
        .logout {{ margin-top: auto; color: var(--red); }}

        .content {{ flex: 1; padding: 40px; overflow-y: auto; position: relative; scroll-behavior: auto; display: flex; flex-direction: column; }}
        h1 {{ margin-top: 0; font-size: 28px; margin-bottom: 20px; }}
        
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .card {{ background: var(--card); padding: 20px; border-radius: 12px; border: 1px solid var(--border); }}
        .stat-val {{ font-size: 32px; font-weight: bold; margin: 10px 0 5px; }}
        .stat-lbl {{ color: var(--text-sec); font-size: 14px; }}
        
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ text-align: left; color: var(--text-sec); padding: 12px; border-bottom: 1px solid var(--border); }}
        td {{ padding: 12px; border-bottom: 1px solid var(--border); vertical-align: middle; }}
        .user-row:hover {{ background: rgba(255,255,255,0.05); cursor: pointer; }}
        .avatar {{ width: 36px; height: 36px; background: var(--accent); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin-right: 10px; float: left; object-fit: cover; }}
        .avatar.group {{ background: #BF5AF2; }}
        
        /* CHAT INTERFACE */
        .chat-wrapper {{ display: flex; flex-direction: column; flex: 1; min-height: 0; }}
        .chat-header {{ flex-shrink: 0; background: var(--card); padding: 15px; border-radius: 12px; border: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
        
        .chat-messages {{ flex: 1; overflow-y: auto; padding-right: 10px; display: flex; flex-direction: column; gap: 10px; padding-bottom: 20px; }}
        
        .msg-row {{ display: flex; width: 100%; }}
        .msg-row.left {{ justify-content: flex-start; }} 
        .msg-row.right {{ justify-content: flex-end; }}
        .msg-row.center {{ justify-content: center; }}
        
        .msg {{ max-width: 70%; padding: 10px 14px; border-radius: 14px; font-size: 15px; position: relative; word-wrap: break-word; }}
        .msg.in {{ background: var(--msg-in); border-bottom-left-radius: 4px; }}
        .msg.out {{ background: var(--msg-out); color: white; border-bottom-right-radius: 4px; }}
        .msg.sys {{ background: transparent; border: 1px solid var(--border); color: var(--text-sec); font-size: 13px; font-style: italic; text-align: center; }}
        
        .msg-meta {{ margin-top: 5px; font-size: 10px; opacity: 0.6; display: flex; justify-content: flex-end; align-items: center; gap: 5px; }}
        .fwd-btn {{ background: none; border: 1px solid #555; color: #fff; cursor: pointer; border-radius: 4px; padding: 2px 6px; font-size: 10px; transition: .2s; }}
        .fwd-btn:hover {{ background: var(--accent); border-color: var(--accent); }}

        /* INPUT AREA (STICKY BOTTOM) */
        .chat-input-box {{ flex-shrink: 0; background: var(--card); padding: 15px; border-radius: 12px; border: 1px solid var(--border); margin-top: 20px; }}
        .input-form {{ display: flex; gap: 10px; }}
        .input-field {{ flex: 1; background: #111; border: 1px solid var(--border); color: white; padding: 12px; border-radius: 8px; outline: none; }}
        
        .btn {{ background: var(--accent); color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; text-decoration: none; display: inline-block; text-align: center; }}
        .btn-red {{ background: var(--red); }} .btn-green {{ background: var(--green); }} .btn-gray {{ background: #444; }} .btn-orange {{ background: #FF9F0A; }}
        
        .switch {{ display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid var(--border); }}
        .switch input {{ transform: scale(1.5); }}
        .action-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 15px; }}
        .logs-box {{ background: #000; color: #0f0; padding: 10px; border-radius: 4px; overflow-x: auto; font-family: monospace; white-space: pre-wrap; font-size: 12px; }}
        .login-body {{ display: flex; align-items: center; justify-content: center; height: 100vh; background: var(--bg); }}
    </style>
</head>
<body>
    <div class="sidebar">
        <h2 style="padding-left:10px;">🤖 Admin</h2>
        <a href="/" class="nav-link">📊 Dashboard</a>
        <a href="/users" class="nav-link">👥 Users</a>
        <a href="/settings" class="nav-link">⚙️ Settings</a>
        <a href="/logs" class="nav-link">📝 Logs</a>
        <a href="/logout" class="nav-link logout">🚪 Logout</a>
    </div>
    <div class="content" id="content">
        {content}
    </div>
    <script>
        document.querySelectorAll('.nav-link').forEach(l => {{ if(l.getAttribute('href') === window.location.pathname) l.classList.add('active'); }});
    </script>
</body>
</html>
"""

def format_uptime(start_time):
    s = int(time.time() - start_time)
    return f"{s // 86400}d {(s % 86400) // 3600}h {(s % 3600) // 60}m"

# --- MIDDLEWARE ---
@web.middleware
async def auth_middleware(request, handler):
    if request.path in ['/login', '/api/login']: return await handler(request)
    if request.cookies.get('admin_session') == settings.WEB_SECRET_KEY: return await handler(request)
    return web.HTTPFound('/login')

# --- HANDLERS ---
async def handle_login(request):
    html = f"""<form action='/api/login' method='post' style='display:flex;justify-content:center;align-items:center;height:100vh;background:#131314;'><div style='background:#2C2C2E;padding:40px;border-radius:10px;'><h2 style='color:white;text-align:center;'>Login</h2><input name='password' type='password' placeholder='Password' style='padding:12px;width:100%;box-sizing:border-box;margin-bottom:10px;background:#111;border:1px solid #444;color:white;border-radius:6px;'><button style='padding:12px;width:100%;background:#0A84FF;color:white;border:none;border-radius:6px;cursor:pointer;'>Enter</button></div></form>"""
    return web.Response(text=html, content_type='text/html')

async def api_login(request):
    data = await request.post()
    if data.get('password') == settings.WEB_ADMIN_PASS:
        r = web.HTTPFound('/')
        r.set_cookie('admin_session', settings.WEB_SECRET_KEY, max_age=2592000)
        return r
    return web.Response(text="Access Denied", status=401)

async def handle_logout(request):
    resp = web.HTTPFound('/login'); resp.del_cookie('admin_session'); return resp

# --- PAGES ---
async def handle_index(request):
    # Данные сразу с сервера
    u_count = len(await get_all_users())
    total, success = await get_global_stats()
    rate = f"{round((success/total)*100,1)}%" if total else "0%"
    active = sum(queue_manager.active_tasks.values())
    uptime = format_uptime(settings.START_TIME)
    
    sys_info = f"Python {sys.version.split()[0]} | {platform.system()}"
    try: _, _, free = shutil.disk_usage("."); disk = f"{free // (2**30)}GB free"
    except: disk = "N/A"
    local_ffmpeg = os.path.join("core", "installs", "ffmpeg.exe")
    ffmpeg_st = "🟢 Local" if os.path.exists(local_ffmpeg) else ("🟢 System" if shutil.which("ffmpeg") else "🔴 Missing")
    server_mode = "LOCAL" if settings.USE_LOCAL_SERVER else "CLOUD"

    # JS для обновления (опционально)
    js = """<script>
    async def up(){
        if(document.hidden)return;
        try{
            let r=await fetch('/api/stats?t='+Date.now()); if(!r.ok)return;
            let d=await r.json();
            document.getElementById('u').innerText=d.users;
            document.getElementById('r').innerText=d.reqs;
            document.getElementById('p').innerText=d.rate;
            document.getElementById('q').innerText=d.active;
            document.getElementById('t').innerText=d.uptime;
        }catch(e){}
    }
    setInterval(up, 2000);
    </script>"""
    
    h = f"""
    <h1>Dashboard</h1>
    <div class="grid">
        <div class="card"><div class="stat-lbl">Total Users</div><div class="stat-val" id="u">{u_count}</div></div>
        <div class="card"><div class="stat-lbl">Requests</div><div class="stat-val" id="r">{success}/{total}</div><div class="stat-lbl" id="p" style="color:var(--green)">{rate}</div></div>
        <div class="card"><div class="stat-lbl">Queue</div><div class="stat-val" id="q">{active}</div></div>
        <div class="card"><div class="stat-lbl">Uptime</div><div class="stat-val" id="t">{uptime}</div><div class="stat-lbl">v{settings.BOT_VERSION}</div></div>
    </div>
    <h2>System Health</h2>
    <div class="grid">
        <div class="card"><div class="stat-lbl">Server Mode</div><div class="stat-val" style="font-size:20px;">{server_mode}</div></div>
        <div class="card"><div class="stat-lbl">Disk</div><div class="stat-val" style="font-size:20px;">{disk}</div></div>
        <div class="card"><div class="stat-lbl">FFmpeg</div><div class="stat-val" style="font-size:20px;">{ffmpeg_st}</div></div>
        <div class="card"><div class="stat-lbl">Env</div><div class="stat-val" style="font-size:16px;">{sys_info}</div></div>
    </div>
    {js}
    """
    return web.Response(text=HTML_BASE.format(content=h), content_type='text/html')

async def handle_users(request):
    sort = request.query.get('sort', 'last_seen')
    filter_type = request.query.get('type', 'all')
    from services.database_service import get_users_with_stats
    users = await get_users_with_stats(sort_by=sort)
    
    if filter_type == 'user': users = [u for u in users if u['user_id'] > 0]
    elif filter_type == 'group': users = [u for u in users if u['user_id'] < 0]

    rows = ""
    for u in users[:100]:
        uid = u['user_id']
        name = u['username'] or "NoName"
        initials = name[:2].upper()
        bg = "#2C2C2E"
        if u['is_banned']: bg = "#3A1E1E"
        
        # Аватарка (прокси)
        ava = f'<img src="/api/avatar/{uid}" class="avatar {"group" if uid<0 else ""}" onerror="this.style.display=\'none\'">'
        
        rows += f"""<tr style="background:{bg}; cursor:pointer;" onclick="location.href='/user/{uid}'">
        <td style="padding:12px; border-bottom:1px solid #3A3A3C;"><div style="display:flex; align-items:center; gap:10px;">{ava}<div><b>{name}</b><br><span style="color:#888;font-size:12px;">{uid}</span></div></div></td>
        <td>{u['req_count']}</td><td>{u['first_seen']}</td><td>{u['last_seen']}</td></tr>"""
    
    h = f"""<h1>Users</h1><div style="margin-bottom:20px;"><a href="/users?sort=last_seen" class="btn">Sort Date</a> <a href="/users?sort=requests" class="btn">Sort Activity</a></div><div class="card" style="padding:0;"><table width="100%" cellspacing="0">{rows}</table></div>"""
    return web.Response(text=HTML_BASE.format(content=h), content_type='text/html')

async def handle_user_detail(request):
    try:
        uid = int(request.match_info['uid'])
        u = await get_user(uid)
        
        # Берем историю
        logs = await get_user_logs(uid, limit=None)
        # logs возвращает DESC (новые сверху).
        # Для классического чата нужно перевернуть (старые сверху, новые внизу)
        chat_logs = list(reversed(logs))
        
        name = u['username'] if u else "Unknown"
        action_btns = f"""<button onclick="promptBan()" class="btn btn-red">Ban</button>"""
        if u and u['is_banned']: action_btns = f"""<form action="/api/action" method="post" style="display:inline;"><input type="hidden" name="user_id" value="{uid}"><input type="hidden" name="action" value="unban"><button class="btn btn-green">Unban</button></form>"""
        
        chat_html = ""
        for l in chat_logs:
            act = l['action']
            txt = l['details']
            tm = l['timestamp'].split('T')[-1][:8]
            
            row_cls = "left"; msg_cls = "in"; sender = name
            
            if act in ['ADMIN']:
                row_cls = "right"; msg_cls = "out"; sender = "Admin"
            elif act in ['SUCCESS', 'FAIL']:
                row_cls = "center"; msg_cls = "sys"; sender = "BOT"
                if act == 'SUCCESS': txt = f"✅ {txt}"
                if act == 'FAIL': txt = f"❌ {txt}"

            # Кнопка Forward (ТОЛЬКО НА SUCCESS - чтобы переслать файл админу)
            tools = ""
            if act == 'SUCCESS':
                 tools = f"""<form action="/api/action" method="post" style="display:inline;"><input type="hidden" name="user_id" value="{uid}"><input type="hidden" name="action" value="forward_to_admin"><input type="hidden" name="text" value="{txt}"><button class="fwd-btn" title="Get File">↗️</button></form>"""

            chat_html += f"""
            <div class="msg-row {row_cls}">
                <div class="msg {msg_cls}">
                    <div style="font-size:10px;opacity:0.7;margin-bottom:4px;">{sender}</div>
                    {txt}
                    <div class="msg-meta"><span>{tm}</span>{tools}</div>
                </div>
            </div>"""

        if not chat_html: chat_html = "<center>No history.</center>"

        h = f"""
        <div class="chat-layout">
            <div class="chat-header">
                <div style="display:flex;align-items:center;gap:15px;">
                    <img src="/api/avatar/{uid}" class="avatar" onerror="this.style.display='none'">
                    <div><h2 style="margin:0;">{name}</h2><span style="color:#aaa;font-size:12px;">ID: {uid}</span></div>
                </div>
                <div style="display:flex;gap:10px;">{action_btns}<a href="/users" class="btn btn-gray">Back</a></div>
            </div>
            
            <div class="chat-messages" id="chatBox">
                {chat_html}
            </div>
            
            <div class="chat-input-box">
                <form action="/api/action" method="post" class="input-form">
                    <input type="hidden" name="user_id" value="{uid}">
                    <input type="hidden" name="action" value="send">
                    <input type="text" name="text" class="input-field" placeholder="Type reply..." required autofocus>
                    <button class="btn">Send</button>
                </form>
            </div>
        </div>
        
        <script>
            // AUTO SCROLL TO BOTTOM
            const chatBox = document.getElementById('chatBox');
            if(chatBox) {{ chatBox.scrollTop = chatBox.scrollHeight; }}
            
            function promptBan() {{
                let r = prompt("Reason:");
                if(r) {{
                    let f = document.createElement('form'); f.method='POST'; f.action='/api/action';
                    f.innerHTML=`<input type='hidden' name='user_id' value='{uid}'><input type='hidden' name='action' value='ban'><input type='hidden' name='reason' value='${{r}}'>`;
                    document.body.appendChild(f); f.submit();
                }}
            }}
        </script>
        """
        return web.Response(text=HTML_BASE.format(content=h), content_type='text/html')
    except Exception as e: return web.Response(text=f"Error: {e}")

async def handle_settings(request):
    modules = ""
    for mod in settings.MODULES_LIST:
        is_on = await get_module_status(mod)
        chk = "checked" if is_on else ""
        modules += f"""<div class="switch"><span>{mod}</span><label><input type="checkbox" onchange="toggle('{mod}')" {chk}><span class="slider"></span></label></div>"""
    
    vid_ph = await get_system_value("placeholder_video") or "None"
    aud_ph = await get_system_value("placeholder_audio") or "None"
    mode = "LOCAL" if settings.USE_LOCAL_SERVER else "CLOUD"
    if os.path.exists(settings.FORCE_CLOUD_FILE): mode += " (Forced)"

    h = f"""
    <h1>Settings</h1>
    <div class="grid">
        <div class="card"><h3>Modules</h3>{modules}</div>
        <div class="card">
            <h3>System</h3>
            <p>Mode: <b>{mode}</b></p>
            <div class="action-grid">
                <button onclick="api('clearcache')" class="btn btn-orange">Clear Cache</button>
                <button onclick="api('restart')" class="btn btn-red">Restart Bot</button>
                <button onclick="api('fix_ffmpeg')" class="btn btn-gray">Fix FFmpeg</button>
                <button onclick="api('return_local')" class="btn btn-green">Retry Local</button>
                <button onclick="api('reset_placeholders')" class="btn btn-gray">Reset PH</button>
                <button onclick="api('force_update')" class="btn btn-red">Force Update</button>
            </div>
            <div style="margin-top:15px; font-size:12px; color:#666;">Vid: {vid_ph[:8]}... Aud: {aud_ph[:8]}...</div>
        </div>
    </div>
    <script>
    function toggle(m){{fetch('/api/toggle_module?mod='+m,{{method:'POST'}});}}
    function api(e){{if(confirm('Sure?')) location.href='/api/'+e;}}
    </script>
    """
    return web.Response(text=HTML_BASE.format(content=h), content_type='text/html')

async def handle_logs_page(request):
    log_path = os.path.join("logs", "files", "full_log.txt")
    c = "No logs."
    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8") as f: c = "".join(f.readlines()[-300:])
    return web.Response(text=HTML_BASE.format(content=f"<h1>Logs</h1><div class='logs-box'>{c}</div>"), content_type='text/html')

# --- API ---
async def api_get_stats(request):
    u = len(await get_all_users())
    t, s = await get_global_stats()
    r = f"{round((s/t)*100,1)}%" if t else "0%"
    return web.json_response({'users':u, 'reqs':f"{s}/{t}", 'rate':r, 'active':sum(queue_manager.active_tasks.values()), 'uptime':format_uptime(settings.START_TIME)})

async def api_get_avatar(request):
    try:
        uid = int(request.match_info['uid'])
        photos = await bot.get_user_profile_photos(uid, limit=1)
        if not photos.total_count: return web.Response(status=404)
        f = await bot.download(photos.photos[0][0].file_id)
        return web.Response(body=f.read(), content_type='image/jpeg')
    except: return web.Response(status=404)

async def api_action_user(request):
    d = await request.post()
    act = d.get('action'); uid = int(d.get('user_id'))
    if act == 'ban': await web_ban_user(uid, d.get('reason','Admin')); await send_log("ADMIN", f"Web Ban {uid}")
    elif act == 'unban': await web_unban_user(uid); await send_log("ADMIN", f"Web Unban {uid}")
    elif act == 'send':
        try:
            await bot.send_message(uid, f"📩 <b>Admin:</b>\n{d.get('text')}", parse_mode="HTML")
            from services.database_service import log_activity
            await log_activity(int(uid), "Admin", "ADMIN", d.get('text'))
            await send_log("ADMIN", f"Web Reply to {uid}: {d.get('text')}")
        except: pass
        
    elif act == 'forward_to_admin' and settings.ADMIN_ID:
        text = d.get('text')
        # УМНАЯ ПЕРЕСЫЛКА МЕДИА
        sent = False
        try:
            # Парсим лог: "[Audio] file_id | meta"
            # или "Cache Hit: url -> file_id" - тут сложнее, так как в SUCCESS логе только URL
            # Но в новых логах мы пишем "[Audio] file_id" при загрузке
            
            # Пробуем найти FileID по сигнатуре
            # Пример лога: "✅ [Audio] CQACAg... | Artist - Track"
            
            # Регулярка для FileID (примерная)
            match = re.search(r'\[(Video|Audio|Photo)\]\s+([A-Za-z0-9_-]+)', text)
            if match:
                m_type = match.group(1)
                fid = match.group(2)
                
                caption = f"📨 <b>Forward from {uid}</b>"
                
                if m_type == 'Video': await bot.send_video(settings.ADMIN_ID, fid, caption=caption, parse_mode="HTML")
                elif m_type == 'Audio': await bot.send_audio(settings.ADMIN_ID, fid, caption=caption, parse_mode="HTML")
                elif m_type == 'Photo': await bot.send_photo(settings.ADMIN_ID, fid, caption=caption, parse_mode="HTML")
                sent = True
        except: pass
        
        if not sent:
            await bot.send_message(settings.ADMIN_ID, f"📨 <b>Fwd from {uid}:</b>\n{text}", parse_mode="HTML")

    return web.HTTPFound(f"/user/{uid}")

async def api_toggle_module(request):
    mod = request.query.get('mod')
    if mod:
        curr = await get_module_status(mod)
        await set_module_status(mod, not curr)
        await send_log("ADMIN", f"Web: Toggle {mod}")
    return web.Response(text="OK")

async def api_clearcache(request):
    from services.database_service import clear_file_cache
    await clear_file_cache()
    await send_log("ADMIN", "Web: Cache cleared")
    return web.HTTPFound("/settings")

async def api_restart(request):
    await send_log("ADMIN", "Web: Restart Triggered")
    import sys
    sys.exit(65)

async def api_fix_ffmpeg(request):
    from core.installs.ffmpeg_installer import check_and_install_ffmpeg
    await asyncio.to_thread(check_and_install_ffmpeg)
    await send_log("ADMIN", "Web: FFmpeg reinstall triggered")
    return web.HTTPFound("/settings")

async def api_return_local(request):
    if os.path.exists(settings.FORCE_CLOUD_FILE):
        os.remove(settings.FORCE_CLOUD_FILE)
        await send_log("ADMIN", "Web: Force Cloud flag removed. Restarting...")
        import sys
        sys.exit(65)
    return web.HTTPFound("/settings")

async def api_reset_placeholders(request):
    from services.placeholder_service import generate_new_placeholder
    await generate_new_placeholder('video')
    await generate_new_placeholder('audio')
    await send_log("ADMIN", "Web: Placeholders reset")
    return web.HTTPFound("/settings")

async def api_force_update(request):
    await send_log("ADMIN", "Web: Force Update Triggered")
    proc = await asyncio.create_subprocess_shell("git fetch origin && git reset --hard origin/main", stdout=asyncio.subprocess.PIPE)
    await proc.communicate()
    import sys
    sys.exit(65)
    
async def api_toggle_module(request):
    m = request.query.get('mod')
    if m: await set_module_status(m, not await get_module_status(m)); await send_log("ADMIN", f"Web: Toggle {m}")
    return web.Response(text="OK")

async def api_clearcache(request):
    from services.database_service import clear_file_cache
    await clear_file_cache(); await send_log("ADMIN", "Web: Cache cleared")
    return web.HTTPFound("/settings")

async def api_restart(request):
    await send_log("ADMIN", "Web: Restart"); import sys; sys.exit(65)

async def api_fix_ffmpeg(request):
    from core.installs.ffmpeg_installer import check_and_install_ffmpeg
    await asyncio.to_thread(check_and_install_ffmpeg); return web.HTTPFound("/settings")

async def api_return_local(request):
    if os.path.exists(settings.FORCE_CLOUD_FILE): os.remove(settings.FORCE_CLOUD_FILE)
    import sys; sys.exit(65)

async def api_reset_placeholders(request):
    from services.placeholder_service import generate_new_placeholder
    await generate_new_placeholder('video'); await generate_new_placeholder('audio')
    return web.HTTPFound("/settings")

async def api_force_update(request):
    proc = await asyncio.create_subprocess_shell("git fetch origin && git reset --hard origin/main", stdout=asyncio.subprocess.PIPE)
    await proc.communicate(); import sys; sys.exit(65)

def setup_web_app():
    app = web.Application(middlewares=[auth_middleware])
    app.router.add_get('/', handle_index)
    app.router.add_get('/login', handle_login)
    app.router.add_post('/api/login', api_login)
    app.router.add_get('/logout', handle_logout)
    app.router.add_get('/api/stats', api_get_stats)
    app.router.add_get('/api/avatar/{uid}', api_get_avatar)
    app.router.add_get('/users', handle_users)
    app.router.add_get('/user/{uid}', handle_user_detail)
    app.router.add_get('/settings', handle_settings)
    app.router.add_get('/logs', handle_logs_page)
    app.router.add_post('/api/action', api_action_user)
    app.router.add_post('/api/toggle_module', api_toggle_module)
    app.router.add_get('/api/clearcache', api_clearcache)
    app.router.add_get('/api/restart', api_restart)
    app.router.add_get('/api/fix_ffmpeg', api_fix_ffmpeg)
    app.router.add_get('/api/return_local', api_return_local)
    app.router.add_get('/api/reset_placeholders', api_reset_placeholders)
    app.router.add_get('/api/force_update', api_force_update)
    return app

async def run_web_server():
    if not settings.ENABLE_WEB_DASHBOARD: return
    port = settings.WEB_SERVER_PORT
    for _ in range(5):
        try:
            app = setup_web_app()
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, settings.WEB_SERVER_HOST, port)
            await site.start()
            print(f"🌍 [WEB] Dashboard started on http://{settings.WEB_SERVER_HOST}:{port}")
            return
        except OSError:
            port += 1