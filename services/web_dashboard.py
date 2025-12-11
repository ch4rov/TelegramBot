import os
import time
import sys
import platform
import shutil
import aiohttp
import math
from aiohttp import web
import json
import re
import asyncio
import subprocess
from datetime import datetime
import settings
from services.database_service import (
    get_all_users, get_module_status, set_module_status, 
    get_stats_period, get_user_logs, get_global_stats,
    get_system_value, get_user, web_ban_user, web_unban_user,
    get_users_filtered, delete_user_logs, import_legacy_logs
)
from core.logger_system import send_log
from core.queue_manager import queue_manager
from loader import bot

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GROUPS_LOG_DIR = os.path.join(BASE_DIR, 'logs', 'group_logs')

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

        .content {{ flex: 1; padding: 40px; overflow-y: auto; scroll-behavior: smooth; }}
        h1 {{ margin-top: 0; font-size: 28px; margin-bottom: 20px; }}
        h2 {{ font-size: 20px; margin-bottom: 15px; margin-top: 30px; color: var(--text-sec); }}
        
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .card {{ background: var(--card); padding: 20px; border-radius: 12px; border: 1px solid var(--border); }}
        .stat-val {{ font-size: 32px; font-weight: bold; margin: 10px 0 5px; }}
        .stat-lbl {{ color: var(--text-sec); font-size: 14px; }}
        
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ text-align: left; color: var(--text-sec); padding: 12px; border-bottom: 1px solid var(--border); font-size: 13px; text-transform: uppercase; cursor: pointer; user-select: none; }}
        th:hover {{ color: var(--text); }}
        td {{ padding: 12px; border-bottom: 1px solid var(--border); vertical-align: middle; font-size: 14px; }}
        
        .user-row {{ cursor: pointer; transition: .2s; }}
        .user-row:hover {{ background: rgba(255,255,255,0.05); }}
        .avatar {{ width: 36px; height: 36px; background: var(--accent); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; margin-right: 12px; float: left; object-fit: cover; color: white; }}
        .avatar.group {{ background: #BF5AF2; }}
        .avatar-gen {{ font-size: 14px; }}
        
        .chat-wrapper {{ display: flex; flex-direction: column; flex: 1; min-height: 0; }}
        .chat-header {{ flex-shrink: 0; background: var(--card); padding: 15px; border-radius: 12px; border: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
        
        .chat-messages {{ flex: 1; overflow-y: auto; padding-right: 10px; display: flex; flex-direction: column; gap: 10px; padding-bottom: 20px; }}
        
        .msg-row {{ display: flex; width: 100%; }}
        .msg-row.left {{ justify-content: flex-start; }} 
        .msg-row.right {{ justify-content: flex-end; }}
        .msg-row.center {{ justify-content: center; }}
        
        .msg {{ max-width: 70%; padding: 10px 14px; border-radius: 16px; font-size: 15px; position: relative; word-wrap: break-word; }}
        .msg.in {{ background: var(--msg-in); border-bottom-left-radius: 4px; }}
        .msg.out {{ background: var(--msg-out); color: white; border-bottom-right-radius: 4px; }}
        .msg.sys {{ background: transparent; border: 1px solid var(--border); color: var(--text-sec); font-size: 13px; font-style: italic; text-align: center; }}
        
        .msg-meta {{ margin-top: 5px; font-size: 10px; opacity: 0.6; display: flex; justify-content: flex-end; align-items: center; gap: 5px; }}
        .fwd-btn {{ background: none; border: 1px solid #555; color: #fff; cursor: pointer; border-radius: 4px; padding: 2px 6px; font-size: 10px; transition: .2s; }}
        .fwd-btn:hover {{ background: var(--accent); border-color: var(--accent); }}

        .chat-input-box {{ flex-shrink: 0; background: var(--card); padding: 15px; border-radius: 12px; border: 1px solid var(--border); margin-top: 20px; }}
        .input-form {{ display: flex; gap: 10px; }}
        .input-field {{ flex: 1; background: #111; border: 1px solid var(--border); color: white; padding: 12px; border-radius: 8px; outline: none; }}
        
        .btn {{ background: var(--accent); color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; text-decoration: none; }}
        .btn:hover {{ opacity: 0.9; transform: translateY(-1px); }}
        .btn-red {{ background: var(--red); }} .btn-green {{ background: var(--green); }} .btn-gray {{ background: #444; }} .btn-orange {{ background: #FF9F0A; }}
        
        .switch {{ display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid var(--border); }}
        .switch input {{ transform: scale(1.5); }}
        .action-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 15px; }}
        .logs-box {{ background: #000; color: #0f0; padding: 10px; border-radius: 4px; overflow-x: auto; font-family: monospace; white-space: pre-wrap; font-size: 12px; }}
        .login-body {{ display: flex; align-items: center; justify-content: center; height: 100vh; background: var(--bg); }}
        
        .pagination {{ display: flex; gap: 5px; margin-top: 10px; justify-content: center; }}
        .page-link {{ padding: 6px 12px; background: #444; border-radius: 6px; text-decoration: none; color: white; font-size: 14px; }}
        .page-link.active {{ background: var(--accent); }}
        .search-bar {{ width: 100%; padding: 12px; background: #111; border: 1px solid var(--border); color: white; border-radius: 8px; margin-bottom: 20px; box-sizing: border-box; }}
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

@web.middleware
async def auth_middleware(request, handler):
    if request.path in ['/login', '/api/login']: return await handler(request)
    if request.cookies.get('admin_session') == settings.WEB_SECRET_KEY: return await handler(request)
    return web.HTTPFound('/login')

async def handle_login(request):
    return web.Response(text="""<form action='/api/login' method='post' style='display:flex;justify-content:center;align-items:center;height:100vh;background:#131314;'><div style='background:#2C2C2E;padding:40px;border-radius:10px;'><h2 style='color:white;text-align:center;'>Login</h2><input name='password' type='password' placeholder='Password' style='padding:12px;width:100%;box-sizing:border-box;margin-bottom:10px;background:#111;border:1px solid #444;color:white;border-radius:6px;'><button style='padding:12px;width:100%;background:#0A84FF;color:white;border:none;border-radius:6px;cursor:pointer;'>Enter</button></div></form>""", content_type='text/html')

async def api_login(request):
    data = await request.post()
    if data.get('password') == settings.WEB_ADMIN_PASS:
        r = web.HTTPFound('/')
        r.set_cookie('admin_session', settings.WEB_SECRET_KEY, max_age=2592000)
        return r
    return web.Response(text="Wrong password", status=401)

async def handle_logout(request):
    r = web.HTTPFound('/login'); r.del_cookie('admin_session'); return r

async def handle_index(request):
    all_users = await get_all_users()
    
    # Считаем
    real_users = len([u for u in all_users if u['user_id'] > 0]) # Люди
    groups_count = len([u for u in all_users if u['user_id'] < 0]) # Группы
    
    # Статистика запросов
    total_reqs, success_reqs = await get_global_stats()
    rate = f"{round((success_reqs/total_reqs)*100,1)}%" if total_reqs else "0%"
    active = sum(queue_manager.active_tasks.values())
    uptime = format_uptime(settings.START_TIME)
    
    # JS для автообновления
    js = """<script>async def up(){if(document.hidden)return;try{let r=await fetch('/api/stats?t='+Date.now()); if(!r.ok)return; let d=await r.json();document.getElementById('u').innerText=d.users_display;document.getElementById('r').innerText=d.reqs;document.getElementById('p').innerText=d.rate;document.getElementById('q').innerText=d.active;document.getElementById('t').innerText=d.uptime;}catch(e){}}setInterval(up, 1000);</script>"""
    
    h = f"""
    <h1>Dashboard</h1>
    <div class="grid">
        <div class="card">
            <div class="stat-lbl">Users</div>
            <div class="stat-val" id="u">{real_users} (+{groups_count})</div>
        </div>
        <div class="card">
            <div class="stat-lbl">Requests</div>
            <div class="stat-val" id="r">{success_reqs}/{total_reqs}</div>
            <div class="stat-lbl" id="p" style="color:var(--green)">{rate}</div>
        </div>
        <div class="card">
            <div class="stat-lbl">Queue</div>
            <div class="stat-val" id="q">{active}</div>
        </div>
        <div class="card">
            <div class="stat-lbl">Uptime</div>
            <div class="stat-val" id="t">{uptime}</div>
            <div class="stat-lbl">v{settings.BOT_VERSION}</div>
        </div>
    </div>
    {js}"""
    return web.Response(text=HTML_BASE.format(content=h), content_type='text/html')

async def handle_users(request):
    query = request.query.get('q', '')
    page = int(request.query.get('page', 1))
    sort = request.query.get('sort', 'last_seen')
    order = request.query.get('order', 'desc')
    
    users = await get_users_filtered(query)
    
    def get_sort_val(u):
        val = u.get(sort)
        if not val: return 0
        if isinstance(val, str) and sort in ['last_seen', 'first_seen']:
            return val
        return val

    try:
        users.sort(key=get_sort_val, reverse=(order == 'desc'))
    except: pass

    admins = []
    groups = []
    regulars = []
    
    admin_id = int(settings.ADMIN_ID) if settings.ADMIN_ID else 0
    testers = settings.TESTERS_LIST

    for u in users:
        uid = u['user_id']
        if uid == admin_id or uid in testers: admins.append(u)
        elif uid < 0: groups.append(u)
        else: regulars.append(u)

    def render_table(title, user_list, p_page=1, p_size=10):
        if not user_list: return ""
        
        total_p = math.ceil(len(user_list) / p_size)
        start = (p_page - 1) * p_size
        subset = user_list[start : start + p_size]
        
        next_order = 'asc' if order == 'desc' else 'desc'
        def th(key, name):
            return f"<th onclick=\"location.href='?q={query}&sort={key}&order={next_order}'\">{name} {'▼' if sort==key and order=='desc' else '▲' if sort==key else ''}</th>"

        rows = ""
        for u in subset:
            uid = u['user_id']
            name = u['username'] or u.get('full_name') or "NoName"
            
            colors = ['#FF3B30', '#FF9500', '#FFCC00', '#4CD964', '#5AC8FA', '#007AFF', '#5856D6', '#AF52DE']
            bg_color = colors[abs(uid) % len(colors)]
            initials = name[:2].upper()
            
            ava = f"""<div style="position:relative;width:36px;height:36px;margin-right:12px;"><div class="avatar avatar-gen" style="background:{bg_color};position:absolute;top:0;left:0;">{initials}</div><img src="/api/avatar/{uid}" class="avatar" style="position:absolute;top:0;left:0;" onerror="this.style.display='none'"></div>"""
            
            bg = "#2C2C2E"
            badges = ""
            if uid == admin_id: badges = " 👑"
            elif uid in testers: badges = " 🗝️"
            if u['is_banned']: 
                bg = "#3A1E1E"
                badges += " ⛔"
            
            target_link = f"/groups/{uid}" if uid < 0 else f"/user/{uid}"
            
            joined = u.get('first_seen', 'Unknown').split(' ')[0]
            last = u.get('last_seen', 'Unknown')
            msgs = u.get('req_count', 0)
            
            rows += f"""<tr style="background:{bg};" class="user-row" onclick="location.href='{target_link}'">
                <td style="display:flex;align-items:center;">{ava}<div><b>{name}</b>{badges}<br><span style="color:#888;font-size:12px;">{uid}</span></div></td>
                <td>{joined}</td>
                <td>{last}</td>
                <td>{msgs}</td>
                </tr>"""

        pag = ""
        if total_p > 1:
            pag = "<div class='pagination'>"
            for i in range(1, total_p + 1):
                cls = "active" if i == p_page else ""
                pag += f"<a href='?q={query}&page={i}&sort={sort}&order={order}' class='page-link {cls}'>{i}</a>"
            pag += "</div>"

        return f"""
        <h2>{title} <span style="font-size:14px;opacity:0.5;">({len(user_list)})</span></h2>
        <div class="card" style="padding:0;">
            <table width="100%" cellspacing="0">
                <tr>
                    {th('username', 'User')}
                    {th('first_seen', 'Joined')}
                    {th('last_seen', 'Last Active')}
                    {th('req_count', 'Msgs')}
                </tr>
                {rows}
            </table>
        </div>{pag}"""

    content = f"""
    <div style="display:flex; justify-content:space-between; align-items:center;">
        <h1>Users Database</h1>
        <a href="/" class="btn btn-gray">Back</a>
    </div>
    
    <form action="/users" method="get">
        <input name="q" class="search-bar" placeholder="Search by ID, username or name..." value="{query}" autofocus>
    </form>
    
    {render_table("🛡️ Administration & Testers", admins, page)}
    {render_table("👥 Groups", groups, page)}
    {render_table("👤 Users", regulars, page)}
    
    { "<center style='color:#666; margin-top:50px;'>No results found.</center>" if not (admins or groups or regulars) else "" }
    """
    return web.Response(text=HTML_BASE.format(content=content), content_type='text/html')

async def handle_user_detail(request):
    try:
        uid = int(request.match_info['uid'])
        u = await get_user(uid)
        
        # ЧИТАЕМ ФАЙЛ ВМЕСТО БАЗЫ
        log_path = os.path.join(BASE_DIR, 'logs', 'user_logs', f"{uid}.txt")
        content = "Log file not found."
        
        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                content = f"Error reading log: {e}"

        name = u['username'] if u else "Unknown"
        
        # КНОПКИ ДЕЙСТВИЙ
        action_btns = f"""<button onclick="promptBan()" class="btn btn-red">Ban</button>"""
        if u and u['is_banned']: 
            action_btns = f"""<form action="/api/action" method="post" style="display:inline;"><input type="hidden" name="user_id" value="{uid}"><input type="hidden" name="action" value="unban"><button class="btn btn-green">Unban</button></form>"""
        
        # АВАТАРКА
        colors = ['#FF3B30', '#FF9500', '#FFCC00', '#4CD964', '#5AC8FA', '#007AFF', '#5856D6', '#AF52DE']
        bg_color = colors[abs(uid) % len(colors)]
        initials = name[:2].upper()
        ava = f"""<div style="position:relative;width:44px;height:44px;"><div class="avatar avatar-gen" style="background:{bg_color};width:44px;height:44px;position:absolute;top:0;left:0;font-size:18px;">{initials}</div><img src="/api/avatar/{uid}" class="avatar" style="width:44px;height:44px;position:absolute;top:0;left:0;" onerror="this.style.display='none'"></div>"""

        h = f"""
        <div class="chat-header">
            <div class="user-meta">{ava}<div><h2 style="margin:0;">{name}</h2><span style="color:#aaa;font-size:12px;">ID: {uid}</span></div></div>
            <div style="display:flex; gap:10px;">
                <button onclick="api('clear_logs?uid={uid}', 'Clear History')" class="btn btn-orange">Clear File</button>
                {action_btns}
                <a href="/users" class="btn btn-gray">Back</a>
            </div>
        </div>
        
        <div class="chat-wrapper">
            <div class="logs-box" id="logBox" style="flex:1; margin-bottom:20px; border:1px solid #333;">{content}</div>
            
            <div class="chat-input-box">
                <form action="/api/action" method="post" class="input-form">
                    <input type="hidden" name="user_id" value="{uid}">
                    <input type="hidden" name="action" value="send">
                    <input type="text" name="text" class="input-field" placeholder="Reply to user (via bot)..." required autofocus>
                    <button class="btn">Send</button>
                </form>
            </div>
        </div>
        
        <script>
            // Авто-скролл вниз
            const logBox = document.getElementById('logBox');
            if(logBox) {{ logBox.scrollTop = logBox.scrollHeight; }}
            
            function promptBan() {{
                let r = prompt("Reason:");
                if(r) {{
                    let f = document.createElement('form'); f.method='POST'; f.action='/api/action';
                    f.innerHTML=`<input type='hidden' name='user_id' value='{uid}'><input type='hidden' name='action' value='ban'><input type='hidden' name='reason' value='${{r}}'>`;
                    document.body.appendChild(f); f.submit();
                }}
            }}
            function api(url, msg){{ if(confirm(msg)) location.href='/api/'+url; }}
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
                <button onclick="api('import_logs')" class="btn btn-green">Import Old Logs</button>
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

async def handle_group_view(request):
    chat_id = request.match_info['chat_id']
    file_path = os.path.join(GROUPS_LOG_DIR, f"{chat_id}.txt")

    if not os.path.exists(file_path):
        return web.Response(text="Log not found", status=404)

    try:
        with open(file_path, "r", encoding="utf-8") as f: content = f.read()
    except Exception as e: content = f"Error: {e}"

    h = f"""
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
        <h2>Log: {chat_id}</h2>
        <div>
            <a href="/groups/{chat_id}/delete" onclick="return confirm('Delete?')" class="btn btn-red" style="margin-right:10px;">🗑 Clear</a>
            <a href="/users" class="btn btn-gray">Back</a>
        </div>
    </div>
    <div class="logs-box">{content}</div>
    """
    return web.Response(text=HTML_BASE.format(content=h), content_type='text/html')

async def handle_group_delete(request):
    chat_id = request.match_info['chat_id']
    file_path = os.path.join(GROUPS_LOG_DIR, f"{chat_id}.txt")
    if os.path.exists(file_path): os.remove(file_path)
    return web.HTTPFound('/users')

async def api_get_stats(request):
    all_users = await get_all_users()
    real_users = len([u for u in all_users if u['user_id'] > 0])
    groups_count = len([u for u in all_users if u['user_id'] < 0])
    
    t, s = await get_global_stats()
    r = f"{round((s/t)*100,1)}%" if t else "0%"
    
    return web.json_response({
        'users_display': f"{real_users} (+{groups_count})", # <--- ВОТ ТУТ ФОРМАТ
        'reqs':f"{s}/{t}", 
        'rate':r, 
        'active':sum(queue_manager.active_tasks.values()), 
        'uptime':format_uptime(settings.START_TIME)
    })

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
        sent = False
        try:
            fid = None
            if "[Video]" in text: fid = text.split("] ")[1].split(" |")[0].strip()
            elif "[Audio]" in text: fid = text.split("] ")[1].split(" |")[0].strip()
            elif "[Photo]" in text: fid = text.split("] ")[1].strip()
            
            if fid:
                if "[Video]" in text: await bot.send_video(settings.ADMIN_ID, fid, caption=f"Fwd from {uid}")
                elif "[Audio]" in text: await bot.send_audio(settings.ADMIN_ID, fid, caption=f"Fwd from {uid}")
                elif "[Photo]" in text: await bot.send_photo(settings.ADMIN_ID, fid, caption=f"Fwd from {uid}")
                sent = True
        except: pass
        
        if not sent:
            await bot.send_message(settings.ADMIN_ID, f"📨 <b>Fwd from {uid}:</b>\n{text}", parse_mode="HTML")

    return web.HTTPFound(f"/user/{uid}")

async def api_toggle_module(request):
    m = request.query.get('mod')
    if m: await set_module_status(m, not await get_module_status(m)); await send_log("ADMIN", f"Web: Toggle {m}")
    return web.Response(text="OK")

async def api_clear_logs(request):
    uid = int(request.query['uid'])
    from services.database_service import delete_user_logs
    await delete_user_logs(uid)
    await send_log("ADMIN", f"Web: Cleared history for {uid}")
    return web.HTTPFound(f"/user/{uid}")

async def api_import_logs(request):
    from services.database_service import import_legacy_logs
    count = await import_legacy_logs()
    await send_log("ADMIN", f"Web: Imported {count} logs")
    return web.HTTPFound("/settings")

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
    
    app.router.add_get('/groups/{chat_id}', handle_group_view)
    app.router.add_get('/groups/{chat_id}/delete', handle_group_delete)
    
    app.router.add_post('/api/action', api_action_user)
    app.router.add_get('/api/clear_logs', api_clear_logs)
    app.router.add_get('/api/import_logs', api_import_logs)
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
            print(f"⚠️ Port {port} busy. Trying {port+1}...")
            port += 1