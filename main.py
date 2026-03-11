import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from database import Database
from meta_capi import send_subscribe_event
import bot_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

SECRET             = os.getenv("DASHBOARD_PASSWORD", "changeme")
DEFAULT_BOT1_TOKEN = os.getenv("BOT_TOKEN", "")
DEFAULT_BOT2_TOKEN = os.getenv("BOT2_TOKEN", "")
DEFAULT_PIXEL_ID   = os.getenv("PIXEL_ID", "")
DEFAULT_META_TOKEN = os.getenv("META_TOKEN", "")

db = Database()
bot_manager.init(db, send_subscribe_event)

# Инициализируем настройки из env если БД пустая
for key, val in [
    ("bot1_token",  DEFAULT_BOT1_TOKEN),
    ("bot2_token",  DEFAULT_BOT2_TOKEN),
    ("pixel_id",    DEFAULT_PIXEL_ID),
    ("meta_token",  DEFAULT_META_TOKEN),
]:
    if val and not db.get_setting(key):
        db.set_setting(key, val)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Запускаем оба бота при старте
    await bot_manager.start_tracker_bot(db.get_setting("bot1_token"))
    await bot_manager.start_staff_bot(db.get_setting("bot2_token"))
    log.info("Both bots started")
    yield
    await bot_manager.stop_tracker_bot()
    await bot_manager.stop_staff_bot()


app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ══════════════════════════════════════════════════════════════════════════════
# CSS
# ══════════════════════════════════════════════════════════════════════════════

CSS = """<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:#0a0d14;color:#e2e8f0;min-height:100vh}
a{color:inherit;text-decoration:none}

/* ── SIDEBAR ── */
.sidebar{position:fixed;top:0;left:0;width:230px;height:100vh;background:#0b0e17;border-right:1px solid #1a2030;display:flex;flex-direction:column;z-index:10;overflow-y:auto}
.logo{padding:20px;font-size:1.1rem;font-weight:800;color:#fff;border-bottom:1px solid #1a2030;letter-spacing:-.01em}
.logo span{color:#3b82f6}
.nav-section{padding:16px 14px 6px;font-size:.68rem;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:#334155}
.nav-divider{height:1px;background:#1a2030;margin:8px 14px}
.nav-item{display:flex;align-items:center;justify-content:space-between;padding:9px 14px;font-size:.86rem;color:#64748b;border-radius:8px;margin:1px 8px;transition:all .15s;cursor:pointer}
.nav-item:hover{background:#151d2e;color:#e2e8f0}
.nav-item.active{background:#1a2535;color:#fff;font-weight:600}
.nav-item.active.blue{border-left:3px solid #3b82f6;padding-left:11px}
.nav-item.active.orange{border-left:3px solid #f97316;padding-left:11px}
.nav-label{display:flex;align-items:center;gap:9px}
.badge-count{background:#ef4444;color:#fff;border-radius:20px;padding:1px 7px;font-size:.7rem;font-weight:700;min-width:20px;text-align:center}
.sidebar-footer{margin-top:auto;padding:14px;border-top:1px solid #1a2030}
.bot-status{display:flex;align-items:center;gap:8px;padding:8px 10px;background:#0f1420;border-radius:8px;margin-bottom:6px;font-size:.78rem;color:#64748b}
.bot-status .dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.dot-green{background:#34d399}
.dot-red{background:#ef4444}

/* ── MAIN ── */
.main{margin-left:230px}

/* ── CHAT LAYOUT ── */
.chat-layout{display:grid;grid-template-columns:300px 1fr;height:100vh}
.conv-list{background:#0b0e17;border-right:1px solid #1a2030;overflow-y:auto;display:flex;flex-direction:column}
.conv-search{padding:14px;border-bottom:1px solid #1a2030}
.conv-search input{width:100%;background:#0a0d14;border:1px solid #1a2030;border-radius:8px;padding:8px 12px;color:#e2e8f0;font-size:.84rem;outline:none}
.conv-search input:focus{border-color:#f97316}
.conv-item{padding:13px 14px;border-bottom:1px solid #0a0d14;cursor:pointer;transition:background .12s}
.conv-item:hover{background:#111827}
.conv-item.active{background:#1a2030;border-right:2px solid #f97316}
.conv-name{font-weight:600;font-size:.88rem;color:#fff;display:flex;align-items:center;justify-content:space-between;margin-bottom:3px}
.conv-preview{font-size:.78rem;color:#475569;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.conv-time{font-size:.7rem;color:#334155;margin-top:3px}
.unread-num{background:#f97316;color:#fff;border-radius:20px;padding:1px 7px;font-size:.7rem;font-weight:700}
.chat-window{display:flex;flex-direction:column;height:100vh}
.chat-header{padding:14px 20px;border-bottom:1px solid #1a2030;background:#0b0e17;display:flex;align-items:center;justify-content:space-between;flex-shrink:0}
.chat-messages{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:10px}
.msg{max-width:68%;word-break:break-word}
.msg.visitor{align-self:flex-start}
.msg.manager{align-self:flex-end}
.msg-bubble{padding:10px 14px;border-radius:14px;font-size:.88rem;line-height:1.55}
.msg.visitor .msg-bubble{background:#1e2535;color:#e2e8f0;border-bottom-left-radius:4px}
.msg.manager .msg-bubble{background:#ea580c;color:#fff;border-bottom-right-radius:4px}
.msg-time{font-size:.7rem;color:#475569;margin-top:3px}
.msg.visitor .msg-time{text-align:left}
.msg.manager .msg-time{text-align:right}
.chat-input{padding:14px 20px;border-top:1px solid #1a2030;background:#0b0e17;flex-shrink:0}
.chat-input-row{display:flex;gap:8px;align-items:flex-end}
.chat-input textarea{flex:1;background:#0a0d14;border:1px solid #1a2030;border-radius:10px;padding:10px 14px;color:#e2e8f0;font-size:.88rem;outline:none;resize:none;max-height:120px;font-family:system-ui}
.chat-input textarea:focus{border-color:#f97316}
.send-btn-orange{background:#ea580c;color:#fff;border:none;border-radius:10px;padding:10px 18px;cursor:pointer;font-size:.88rem;font-weight:600;height:42px;flex-shrink:0}
.send-btn-orange:hover{background:#c2410c}
.no-conv{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:#334155;gap:12px}

/* ── GENERAL ── */
.page-wrap{padding:32px;max-width:1100px}
.page-title{font-size:1.35rem;font-weight:700;color:#fff;margin-bottom:4px}
.page-sub{font-size:.83rem;color:#475569;margin-bottom:26px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:12px;margin-bottom:26px}
.card{background:#111827;border:1px solid #1a2030;border-radius:12px;padding:18px}
.card .val{font-size:1.8rem;font-weight:700;color:#60a5fa}
.card .val.orange{color:#fb923c}
.card .lbl{font-size:.76rem;color:#475569;margin-top:3px}
.section{background:#111827;border:1px solid #1a2030;border-radius:12px;margin-bottom:18px;overflow:hidden}
.section-head{padding:14px 18px;border-bottom:1px solid #1a2030;display:flex;justify-content:space-between;align-items:center}
.section-head h3{font-size:.92rem;font-weight:600;color:#e2e8f0}
.section-body{padding:18px}
table{width:100%;border-collapse:collapse}
th{padding:9px 14px;text-align:left;font-size:.73rem;text-transform:uppercase;color:#475569;letter-spacing:.05em;border-bottom:1px solid #1a2030}
td{padding:10px 14px;font-size:.84rem;border-bottom:1px solid #0f1420}
tr:last-child td{border-bottom:none}
.badge{display:inline-block;padding:2px 10px;border-radius:20px;font-size:.74rem;background:#1e3a5f;color:#60a5fa}
.badge-orange{background:#431407;color:#fb923c}
.form-row{display:flex;gap:10px;flex-wrap:wrap}
input[type=text],input[type=number],input[type=email],input[type=password],select,textarea{background:#0a0d14;border:1px solid #1a2030;border-radius:8px;padding:9px 13px;color:#e2e8f0;font-size:.86rem;outline:none;width:100%;font-family:system-ui}
input:focus,select:focus,textarea:focus{border-color:#3b82f6}
textarea{resize:vertical;min-height:80px}
.btn{background:#3b82f6;color:#fff;border:none;border-radius:8px;padding:9px 20px;cursor:pointer;font-size:.86rem;font-weight:600;white-space:nowrap}
.btn:hover{background:#2563eb}
.btn-orange{background:#ea580c;color:#fff;border:none}.btn-orange:hover{background:#c2410c}
.btn-red{background:#dc2626;color:#fff;border:none}.btn-red:hover{background:#b91c1c}
.btn-gray{background:#1e2535;color:#94a3b8;border:none}.btn-gray:hover{background:#2d3748;color:#fff}
.btn-sm{padding:5px 12px;font-size:.78rem;border-radius:6px}
.link-box{background:#0a0d14;border:1px solid #1a2030;border-radius:6px;padding:8px 12px;font-family:monospace;font-size:.78rem;word-break:break-all;color:#a5f3fc}
.alert-green{background:#052e16;border:1px solid #166534;border-radius:8px;padding:11px 15px;color:#86efac;margin-bottom:14px;font-size:.86rem}
.alert-red{background:#2d0a0a;border:1px solid #7f1d1d;border-radius:8px;padding:11px 15px;color:#fca5a5;margin-bottom:14px;font-size:.86rem}
.empty{text-align:center;padding:28px;color:#334155;font-size:.86rem}
.tag{display:inline-block;background:#1a2030;border-radius:4px;padding:2px 7px;font-size:.73rem;color:#64748b;font-family:monospace}
.del-btn{background:none;border:none;cursor:pointer;color:#ef4444;font-size:.84rem;padding:4px 8px;border-radius:4px}
.del-btn:hover{background:#2d0a0a}
.field-group{display:flex;flex-direction:column;gap:5px;flex:1}
.field-label{font-size:.76rem;color:#475569;font-weight:600;text-transform:uppercase;letter-spacing:.04em}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.grid-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px}
.avatar{width:36px;height:36px;border-radius:50%;background:#431407;display:flex;align-items:center;justify-content:center;font-size:.95rem;flex-shrink:0;font-weight:700;color:#fb923c}
</style>"""


def nav_html(active: str, key: str) -> str:
    stats = db.get_stats()
    unread = stats.get("unread", 0)

    b1 = bot_manager.get_tracker_bot()
    b2 = bot_manager.get_staff_bot()
    b1_dot = "dot-green" if b1 else "dot-red"
    b2_dot = "dot-green" if b2 else "dot-red"
    b1_name = db.get_setting("bot1_name", "Бот трекер")
    b2_name = db.get_setting("bot2_name", "Бот сотрудники")

    def item(icon, label, page, section_color="blue", badge=False):
        cls = f"nav-item active {section_color}" if page == active else "nav-item"
        bdg = f'<span class="badge-count">{unread}</span>' if badge and unread > 0 else ""
        return f'<a href="/{page}?key={key}"><div class="{cls}"><span class="nav-label">{icon} {label}</span>{bdg}</div></a>'

    return f"""
    <div class="sidebar">
      <div class="logo">📡 TG<span>Tracker</span></div>

      {item("📊", "Обзор", "overview", "blue")}

      <div class="nav-divider"></div>
      <div class="nav-section">👥 Клиенты</div>
      {item("📡", "Каналы", "channels", "blue")}
      {item("🔗", "Кампании", "campaigns", "blue")}
      {item("🌐", "Лендинг", "landing", "blue")}
      {item("💬", "Msg Flow", "flow_clients", "blue")}

      <div class="nav-divider"></div>
      <div class="nav-section">👔 Сотрудники</div>
      {item("💬", "Чаты", "chat", "orange", badge=True)}
      {item("🗂", "База сотрудников", "staff", "orange")}
      {item("💬", "Msg Flow (HR)", "flow_staff", "orange")}

      <div class="nav-divider"></div>
      {item("⚙️", "Настройки", "settings", "blue")}

      <div class="sidebar-footer">
        <div class="bot-status">
          <div class="dot {b1_dot}"></div>
          <span>{b1_name}</span>
        </div>
        <div class="bot-status">
          <div class="dot {b2_dot}"></div>
          <span>{b2_name}</span>
        </div>
      </div>
    </div>"""


def base(content: str, active: str, key: str) -> str:
    return f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>TG Tracker</title>{CSS}</head><body>{nav_html(active, key)}<div class="main">{content}</div></body></html>'


def auth_check(key: str):
    if key != SECRET:
        return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Login</title>{CSS}</head>
        <body><div style="max-width:340px;margin:100px auto">
        <div style="font-size:1.4rem;font-weight:800;color:#fff;margin-bottom:20px">📡 TG Tracker</div>
        <form method="get"><div class="form-row">
        <input type="password" name="key" placeholder="Пароль"/>
        <button class="btn">Войти</button></div></form></div></body></html>""", status_code=401)
    return None


# ══════════════════════════════════════════════════════════════════════════════
# OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
@app.get("/overview", response_class=HTMLResponse)
async def overview(key: str = ""):
    err = auth_check(key)
    if err: return err
    s = db.get_stats()
    joins = db.get_recent_joins(20)
    rows = "".join(f"""<tr>
        <td>{j['joined_at'][:16].replace('T',' ')}</td>
        <td><span class="tag">{j.get('channel_id','—')}</span></td>
        <td><span class="badge">{j['campaign_name']}</span></td>
    </tr>""" for j in joins) or '<tr><td colspan="3"><div class="empty">Пока нет</div></td></tr>'
    pixel = db.get_setting("pixel_id", "—")
    content = f"""<div class="page-wrap">
    <div class="page-title">📊 Обзор</div>
    <div class="page-sub">Статистика по обоим направлениям</div>
    <div style="margin-bottom:10px;font-size:.78rem;font-weight:700;color:#3b82f6;text-transform:uppercase;letter-spacing:.1em">👥 Клиенты</div>
    <div class="cards">
      <div class="card"><div class="val">{s['total']}</div><div class="lbl">Подписчиков</div></div>
      <div class="card"><div class="val">{s['from_ads']}</div><div class="lbl">Из рекламы</div></div>
      <div class="card"><div class="val">{s['organic']}</div><div class="lbl">Органика</div></div>
      <div class="card"><div class="val">{s['channels']}</div><div class="lbl">Каналов</div></div>
    </div>
    <div style="margin-bottom:10px;font-size:.78rem;font-weight:700;color:#f97316;text-transform:uppercase;letter-spacing:.1em">👔 Сотрудники</div>
    <div class="cards">
      <div class="card"><div class="val orange">{s['conversations']}</div><div class="lbl">Диалогов</div></div>
      <div class="card"><div class="val orange">{s['unread']}</div><div class="lbl">Непрочитанных</div></div>
      <div class="card"><div class="val orange">{s['staff']}</div><div class="lbl">Сотрудников</div></div>
    </div>
    <div class="section">
      <div class="section-head"><h3>🕐 Последние подписки (Клиенты)</h3><span class="tag">Pixel: {pixel}</span></div>
      <table><thead><tr><th>Время</th><th>Канал</th><th>Кампания</th></tr></thead><tbody>{rows}</tbody></table>
    </div></div>"""
    return HTMLResponse(base(content, "overview", key))


# ══════════════════════════════════════════════════════════════════════════════
# CHAT (Сотрудники)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/chat", response_class=HTMLResponse)
async def chat_panel(key: str = "", conv_id: int = 0):
    err = auth_check(key)
    if err: return err

    convs = db.get_conversations()
    messages_html = ""
    header_html = ""
    active_conv = None

    if conv_id:
        active_conv = db.get_conversation(conv_id)
        if active_conv:
            db.mark_conversation_read(conv_id)
            msgs = db.get_messages(conv_id)
            staff = db.get_staff_by_conv(conv_id)
            for m in msgs:
                t = m["created_at"][11:16]
                messages_html += f"""
                <div class="msg {m['sender_type']}" data-id="{m['id']}">
                  <div class="msg-bubble">{m['content'] or ''}</div>
                  <div class="msg-time">{t}</div>
                </div>"""
            uname = f"@{active_conv['username']}" if active_conv.get('username') else active_conv.get('tg_chat_id','')
            status_color = "#34d399" if active_conv["status"] == "open" else "#ef4444"
            staff_html = ""
            if staff:
                staff_html = f"""<div style="font-size:.78rem;color:#64748b;margin-top:4px">
                  {staff.get('position') or ''} {('· 📞 ' + staff['phone']) if staff.get('phone') else ''}
                  <a href="/staff?key={key}&edit={staff['id']}" style="color:#f97316;margin-left:8px">Карточка →</a></div>"""
            close_btn = f'<form method="post" action="/chat/close?key={key}" style="display:inline"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn btn-gray btn-sm" type="submit">✓ Закрыть</button></form>' if active_conv["status"] == "open" else f'<form method="post" action="/chat/reopen?key={key}" style="display:inline"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-orange btn btn-sm" type="submit">↺ Открыть</button></form>'
            header_html = f"""
            <div class="chat-header">
              <div style="display:flex;align-items:center;gap:12px">
                <div class="avatar">{active_conv['visitor_name'][0].upper()}</div>
                <div>
                  <div style="font-weight:700;color:#fff;font-size:.95rem">{active_conv['visitor_name']} <span style="color:{status_color};font-size:.75rem">● {active_conv['status']}</span></div>
                  <div style="font-size:.8rem;color:#64748b">{uname}</div>
                  {staff_html}
                </div>
              </div>
              <div style="display:flex;gap:8px">{close_btn}</div>
            </div>"""

    conv_items = ""
    for c in convs:
        is_active = c["id"] == conv_id
        cls = "conv-item active" if is_active else "conv-item"
        t = (c.get("last_message_at") or c["created_at"])[:16].replace("T", " ")
        preview = c.get("last_message") or "Нет сообщений"
        ucount = f'<span class="unread-num">{c["unread_count"]}</span>' if c["unread_count"] > 0 else ""
        dot = "🟢" if c["status"] == "open" else "⚫"
        conv_items += f"""<a href="/chat?key={key}&conv_id={c['id']}">
          <div class="{cls}">
            <div class="conv-name"><span>{dot} {c['visitor_name']}</span>{ucount}</div>
            <div class="conv-preview">{preview}</div>
            <div class="conv-time">{t}</div>
          </div></a>"""

    if not conv_items:
        conv_items = '<div class="empty" style="padding:40px 16px">Диалогов пока нет.<br><br>Сотрудники появятся<br>когда напишут боту</div>'

    if active_conv and conv_id:
        right = f"""{header_html}
        <div class="chat-messages" id="msgs">{messages_html}</div>
        <div class="chat-input"><div class="chat-input-row">
          <textarea id="reply-text" placeholder="Написать сотруднику… (Enter — отправить)" rows="1" onkeydown="handleKey(event)"></textarea>
          <button class="send-btn-orange" onclick="sendMsg()">Отправить</button>
        </div></div>"""
    else:
        right = '<div class="no-conv"><div style="font-size:2.5rem">👔</div><div>Выбери диалог слева</div></div>'

    b2 = bot_manager.get_staff_bot()
    bot_warn = "" if b2 else '<div style="background:#431407;border:1px solid #7c2d12;border-radius:8px;padding:10px 14px;font-size:.82rem;color:#fb923c;margin-bottom:0">⚠️ Бот сотрудников не запущен — проверь токен в <a href="/settings?key=' + key + '" style="color:#fb923c;text-decoration:underline">Настройках</a></div>'

    content = f"""
    <div class="chat-layout">
      <div class="conv-list">
        <div class="conv-search">
          {bot_warn}
          <input type="text" placeholder="🔍 Поиск..." oninput="filterConvs(this.value)" style="margin-top:{'8px' if bot_warn else '0'}"/>
        </div>
        <div id="conv-items">{conv_items}</div>
      </div>
      <div class="chat-window">{right}</div>
    </div>
    <script>
    const msgsEl = document.getElementById('msgs');
    if (msgsEl) msgsEl.scrollTop = msgsEl.scrollHeight;

    async function sendMsg() {{
      const ta = document.getElementById('reply-text');
      const text = ta.value.trim();
      if (!text) return;
      ta.value = '';
      await fetch('/chat/send?key={key}', {{
        method:'POST', headers:{{'Content-Type':'application/x-www-form-urlencoded'}},
        body:'conv_id={conv_id}&text='+encodeURIComponent(text)
      }});
      loadNewMsgs();
    }}
    function handleKey(e) {{ if(e.key==='Enter'&&!e.shiftKey){{e.preventDefault();sendMsg();}} }}

    {"setInterval(loadNewMsgs,3000);" if active_conv and conv_id else "setInterval(checkUnread,5000);"}

    async function loadNewMsgs() {{
      const msgs = document.querySelectorAll('.msg[data-id]');
      const lastId = msgs.length ? msgs[msgs.length-1].dataset.id : 0;
      const res = await fetch('/api/messages/{conv_id}?after='+lastId+'&key={key}');
      const data = await res.json();
      if(data.messages&&data.messages.length>0) {{
        const c = document.getElementById('msgs');
        data.messages.forEach(m=>{{
          const d=document.createElement('div');
          d.className='msg '+m.sender_type; d.dataset.id=m.id;
          d.innerHTML='<div class="msg-bubble">'+esc(m.content)+'</div><div class="msg-time">'+m.created_at.substring(11,16)+'</div>';
          c.appendChild(d);
        }});
        c.scrollTop=c.scrollHeight;
      }}
    }}
    async function checkUnread() {{
      const r=await fetch('/api/stats?key={key}');
      const d=await r.json();
      const b=document.querySelector('.badge-count');
      if(d.unread>0){{if(b)b.textContent=d.unread;}}else if(b)b.remove();
    }}
    function esc(t){{return(t||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\\n/g,'<br>');}}
    function filterConvs(q){{document.querySelectorAll('.conv-item').forEach(el=>{{
      const n=el.querySelector('.conv-name')?.textContent?.toLowerCase()||'';
      el.parentElement.style.display=n.includes(q.toLowerCase())?'':'none';
    }});}}
    </script>"""

    return HTMLResponse(f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>Чаты — Сотрудники</title>{CSS}</head><body>{nav_html("chat", key)}<div class="main">{content}</div></body></html>')


@app.post("/chat/send")
async def chat_send(key: str = "", conv_id: int = Form(...), text: str = Form(...)):
    if key != SECRET: return JSONResponse({"error": "unauthorized"}, 401)
    conv = db.get_conversation(conv_id)
    if not conv: return JSONResponse({"error": "not found"}, 404)
    ok = await bot_manager.send_staff_message(conv["tg_chat_id"], text)
    if ok:
        db.save_message(conv_id, conv["tg_chat_id"], "manager", text)
        db.update_conversation_last_message(conv["tg_chat_id"], f"Вы: {text}", increment_unread=False)
    return JSONResponse({"ok": ok})


@app.post("/chat/close")
async def chat_close(key: str = "", conv_id: int = Form(...)):
    if key != SECRET: return RedirectResponse(f"/chat?key={key}", 303)
    db.close_conversation(conv_id)
    return RedirectResponse(f"/chat?key={key}&conv_id={conv_id}", 303)


@app.post("/chat/reopen")
async def chat_reopen(key: str = "", conv_id: int = Form(...)):
    if key != SECRET: return RedirectResponse(f"/chat?key={key}", 303)
    db.reopen_conversation(conv_id)
    return RedirectResponse(f"/chat?key={key}&conv_id={conv_id}", 303)


# ── API ───────────────────────────────────────────────────────────────────────

@app.get("/api/messages/{conv_id}")
async def api_messages(conv_id: int, after: int = 0, key: str = ""):
    if key != SECRET: return JSONResponse({"error": "unauthorized"}, 401)
    return JSONResponse({"messages": db.get_new_messages(conv_id, after)})

@app.get("/api/stats")
async def api_stats(key: str = ""):
    if key != SECRET: return JSONResponse({"error": "unauthorized"}, 401)
    return JSONResponse(db.get_stats())


# ══════════════════════════════════════════════════════════════════════════════
# STAFF — База сотрудников
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/staff", response_class=HTMLResponse)
async def staff_page(key: str = "", edit: int = 0, msg: str = ""):
    err = auth_check(key)
    if err: return err
    staff_list = db.get_staff()
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""
    edit_form = ""
    if edit:
        with db._conn() as conn:
            s = conn.execute("SELECT * FROM staff WHERE id=?", (edit,)).fetchone()
        if s:
            s = dict(s)
            edit_form = f"""<div class="section" style="margin-bottom:20px">
              <div class="section-head"><h3>✏️ Редактировать: {s['name']}</h3></div>
              <div class="section-body">
                <form method="post" action="/staff/update?key={key}">
                  <input type="hidden" name="staff_id" value="{s['id']}"/>
                  <div class="grid-3" style="margin-bottom:12px">
                    <div class="field-group"><div class="field-label">Имя</div><input type="text" name="name" value="{s.get('name') or ''}"/></div>
                    <div class="field-group"><div class="field-label">Телефон</div><input type="text" name="phone" value="{s.get('phone') or ''}"/></div>
                    <div class="field-group"><div class="field-label">Email</div><input type="email" name="email" value="{s.get('email') or ''}"/></div>
                    <div class="field-group"><div class="field-label">Должность</div><input type="text" name="position" value="{s.get('position') or ''}"/></div>
                    <div class="field-group"><div class="field-label">Теги</div><input type="text" name="tags" value="{s.get('tags') or ''}"/></div>
                  </div>
                  <div class="field-group" style="margin-bottom:12px"><div class="field-label">Заметки</div>
                  <textarea name="notes">{s.get('notes') or ''}</textarea></div>
                  <div style="display:flex;gap:8px">
                    <button class="btn btn-orange">💾 Сохранить</button>
                    <a href="/staff?key={key}"><button class="btn btn-gray" type="button">Отмена</button></a>
                  </div>
                </form>
              </div></div>"""

    rows = "".join(f"""<tr>
        <td><div style="font-weight:600;color:#fff">{s['name'] or '—'}</div>
          <div style="font-size:.76rem;color:#475569">@{s['username'] or '—'}</div></td>
        <td>{s.get('position') or '—'}</td>
        <td>{s.get('phone') or '—'}</td>
        <td>{s.get('tags') or '—'}</td>
        <td>{s['created_at'][:10]}</td>
        <td style="white-space:nowrap">
          <a href="/staff?key={key}&edit={s['id']}"><button class="btn btn-sm btn-orange">✏️</button></a>
          {'<a href="/chat?key=' + key + '&conv_id=' + str(s.get("conversation_id","")) + '"><button class="btn btn-gray btn-sm" style="margin-left:4px">💬</button></a>' if s.get("conversation_id") else ''}
        </td>
    </tr>""" for s in staff_list) or '<tr><td colspan="6"><div class="empty">Сотрудников пока нет — они появятся когда напишут боту</div></td></tr>'

    content = f"""<div class="page-wrap">
    <div class="page-title">🗂 База сотрудников</div>
    <div class="page-sub">Все кто написал боту для сотрудников</div>
    {alert}{edit_form}
    <div class="section">
      <div class="section-head"><h3>📋 Сотрудники ({len(staff_list)})</h3></div>
      <table><thead><tr><th>Имя</th><th>Должность</th><th>Телефон</th><th>Теги</th><th>Добавлен</th><th></th></tr></thead>
      <tbody>{rows}</tbody></table>
    </div></div>"""
    return HTMLResponse(base(content, "staff", key))


@app.post("/staff/update")
async def staff_update(key: str = "", staff_id: int = Form(...), name: str = Form(""),
                        phone: str = Form(""), email: str = Form(""), position: str = Form(""),
                        notes: str = Form(""), tags: str = Form("")):
    if key != SECRET: return RedirectResponse(f"/staff?key={key}", 303)
    db.update_staff(staff_id, name, phone, email, position, notes, tags)
    return RedirectResponse(f"/staff?key={key}&msg=Сохранено", 303)


# ══════════════════════════════════════════════════════════════════════════════
# SETTINGS — с управлением ботами
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(key: str = "", msg: str = ""):
    err = auth_check(key)
    if err: return err

    b1_info = await bot_manager.get_bot_info(bot_manager.get_tracker_bot())
    b2_info = await bot_manager.get_bot_info(bot_manager.get_staff_bot())
    pixel_id   = db.get_setting("pixel_id")
    meta_token = db.get_setting("meta_token")
    land_title = db.get_setting("landing_title", "Наши каналы")
    land_sub   = db.get_setting("landing_subtitle", "Подписывайся и будь в курсе")
    staff_welcome = db.get_setting("staff_welcome", "Привет! Напиши своё имя и должность 👋")
    masked = meta_token[:12] + "..." + meta_token[-6:] if len(meta_token) > 20 else meta_token
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""

    def bot_card(title, color, info, field, route, placeholder):
        status = f'<span style="color:#34d399">● Активен</span> — <a href="{info.get("link","")}" target="_blank" style="color:#60a5fa">@{info.get("username","")}</a>' if info.get("active") else '<span style="color:#ef4444">● Не запущен</span>'
        border = "#3b82f6" if color == "blue" else "#f97316"
        btn_cls = "btn" if color == "blue" else "btn btn-orange"
        return f"""<div class="section" style="border-left:3px solid {border}">
          <div class="section-head"><h3>{title}</h3><span style="font-size:.82rem">{status}</span></div>
          <div class="section-body">
            <form method="post" action="/{route}?key={key}">
              <div class="form-row">
                <div class="field-group"><div class="field-label">Токен бота</div>
                <input type="text" name="{field}" placeholder="{placeholder}"/></div>
                <div style="display:flex;align-items:flex-end"><button class="{btn_cls}">🔄 Сменить</button></div>
              </div>
              <p style="color:#475569;font-size:.78rem;margin-top:8px">Оставь пустым — токен не изменится</p>
            </form>
          </div></div>"""

    content = f"""<div class="page-wrap">
    <div class="page-title">⚙️ Настройки</div>
    <div class="page-sub">Управление ботами, пикселем и контентом</div>
    {alert}

    <div style="font-size:.78rem;font-weight:700;color:#3b82f6;text-transform:uppercase;letter-spacing:.1em;margin-bottom:12px">👥 Боты</div>
    {bot_card("🤖 Бот 1 — Трекер (Клиенты)", "blue", b1_info, "bot1_token", "settings/bot1", "Новый токен от @BotFather")}
    {bot_card("🤖 Бот 2 — Сотрудники", "orange", b2_info, "bot2_token", "settings/bot2", "Новый токен от @BotFather")}

    <div style="font-size:.78rem;font-weight:700;color:#3b82f6;text-transform:uppercase;letter-spacing:.1em;margin:20px 0 12px">📡 Meta Pixel</div>
    <div class="section">
      <div class="section-head"><h3>Facebook Conversions API</h3></div>
      <div class="section-body">
        <form method="post" action="/settings/pixel?key={key}">
          <div class="grid-2" style="margin-bottom:12px">
            <div class="field-group"><div class="field-label">Pixel ID</div>
            <input type="text" name="pixel_id" value="{pixel_id}"/></div>
            <div class="field-group"><div class="field-label">Access Token (сейчас: {masked})</div>
            <input type="text" name="meta_token" placeholder="Оставь пустым — не менять"/></div>
          </div>
          <button class="btn">💾 Сохранить</button>
        </form>
      </div>
    </div>

    <div style="font-size:.78rem;font-weight:700;color:#f97316;text-transform:uppercase;letter-spacing:.1em;margin:20px 0 12px">👔 Бот сотрудников — тексты</div>
    <div class="section" style="border-left:3px solid #f97316">
      <div class="section-head"><h3>Приветственное сообщение (/start)</h3></div>
      <div class="section-body">
        <form method="post" action="/settings/staff_welcome?key={key}">
          <div class="field-group" style="margin-bottom:12px">
            <textarea name="staff_welcome">{staff_welcome}</textarea>
          </div>
          <button class="btn btn-orange">💾 Сохранить</button>
        </form>
      </div>
    </div>

    <div style="font-size:.78rem;font-weight:700;color:#3b82f6;text-transform:uppercase;letter-spacing:.1em;margin:20px 0 12px">🌐 Лендинг</div>
    <div class="section">
      <div class="section-head"><h3>Тексты публичной страницы</h3></div>
      <div class="section-body">
        <form method="post" action="/settings/landing?key={key}">
          <div class="grid-2" style="margin-bottom:12px">
            <div class="field-group"><div class="field-label">Заголовок</div><input type="text" name="landing_title" value="{land_title}"/></div>
            <div class="field-group"><div class="field-label">Подзаголовок</div><input type="text" name="landing_subtitle" value="{land_sub}"/></div>
          </div>
          <button class="btn">💾 Сохранить</button>
        </form>
      </div>
    </div></div>"""
    return HTMLResponse(base(content, "settings", key))


@app.post("/settings/bot1")
async def settings_bot1(key: str = "", bot1_token: str = Form("")):
    if key != SECRET: return RedirectResponse(f"/settings?key={key}", 303)
    if bot1_token.strip():
        db.set_setting("bot1_token", bot1_token.strip())
        await bot_manager.start_tracker_bot(bot1_token.strip())
        info = await bot_manager.get_bot_info(bot_manager.get_tracker_bot())
        if info.get("username"): db.set_setting("bot1_name", f"@{info['username']}")
    return RedirectResponse(f"/settings?key={key}&msg=Бот+1+обновлён", 303)


@app.post("/settings/bot2")
async def settings_bot2(key: str = "", bot2_token: str = Form("")):
    if key != SECRET: return RedirectResponse(f"/settings?key={key}", 303)
    if bot2_token.strip():
        db.set_setting("bot2_token", bot2_token.strip())
        await bot_manager.start_staff_bot(bot2_token.strip())
        info = await bot_manager.get_bot_info(bot_manager.get_staff_bot())
        if info.get("username"): db.set_setting("bot2_name", f"@{info['username']}")
    return RedirectResponse(f"/settings?key={key}&msg=Бот+2+обновлён", 303)


@app.post("/settings/pixel")
async def settings_pixel(key: str = "", pixel_id: str = Form(""), meta_token: str = Form("")):
    if key != SECRET: return RedirectResponse(f"/settings?key={key}", 303)
    if pixel_id.strip():   db.set_setting("pixel_id",   pixel_id.strip())
    if meta_token.strip(): db.set_setting("meta_token", meta_token.strip())
    return RedirectResponse(f"/settings?key={key}&msg=Пиксель+обновлён", 303)


@app.post("/settings/staff_welcome")
async def settings_staff_welcome(key: str = "", staff_welcome: str = Form("")):
    if key != SECRET: return RedirectResponse(f"/settings?key={key}", 303)
    if staff_welcome: db.set_setting("staff_welcome", staff_welcome)
    return RedirectResponse(f"/settings?key={key}&msg=Сохранено", 303)


@app.post("/settings/landing")
async def settings_landing(key: str = "", landing_title: str = Form(""), landing_subtitle: str = Form("")):
    if key != SECRET: return RedirectResponse(f"/settings?key={key}", 303)
    if landing_title:    db.set_setting("landing_title",    landing_title)
    if landing_subtitle: db.set_setting("landing_subtitle", landing_subtitle)
    return RedirectResponse(f"/settings?key={key}&msg=Лендинг+обновлён", 303)


# ══════════════════════════════════════════════════════════════════════════════
# КЛИЕНТЫ: Каналы, Кампании, Лендинг, Flow
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/channels", response_class=HTMLResponse)
async def channels_page(key: str = "", msg: str = "", err: str = ""):
    r = auth_check(key);
    if r: return r
    channels = db.get_channels()
    b1 = bot_manager.get_tracker_bot()
    bot_link = "—"
    if b1:
        info = await b1.get_me()
        bot_link = f"https://t.me/{info.username}"
    rows = "".join(f"""<tr><td><b>{c['name']}</b></td><td><span class="tag">{c['channel_id']}</span></td>
        <td style="color:#34d399;font-weight:600">{c['total_joins']}</td><td>{c['created_at'][:10]}</td>
        <td><form method="post" action="/channels/delete?key={key}" style="display:inline">
        <input type="hidden" name="channel_id" value="{c['channel_id']}"/>
        <button class="del-btn">✕</button></form></td></tr>""" for c in channels
    ) or '<tr><td colspan="5"><div class="empty">Каналов нет</div></td></tr>'
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else (f'<div class="alert-red">❌ {err}</div>' if err else "")
    content = f"""<div class="page-wrap"><div class="page-title">📡 Каналы</div>
    <div class="page-sub">Управление Telegram-каналами для отслеживания подписок</div>
    <div class="section"><div class="section-head"><h3>🤖 Бот трекер (добавь в каналы как администратора)</h3></div>
    <div class="section-body"><div class="link-box">{bot_link}</div></div></div>
    <div class="section"><div class="section-head"><h3>➕ Добавить канал</h3></div><div class="section-body">
    {alert}<form method="post" action="/channels/add?key={key}"><div class="form-row">
    <div class="field-group"><div class="field-label">Название</div><input type="text" name="name" placeholder="Phoenix" required/></div>
    <div class="field-group"><div class="field-label">ID канала (со знаком минус)</div><input type="text" name="channel_id" placeholder="-1003835844880" required/></div>
    <div style="display:flex;align-items:flex-end"><button class="btn">Добавить</button></div>
    </div></form></div></div>
    <div class="section"><div class="section-head"><h3>📋 Каналы ({len(channels)})</h3></div>
    <table><thead><tr><th>Название</th><th>ID</th><th>Подписчиков</th><th>Добавлен</th><th></th></tr></thead>
    <tbody>{rows}</tbody></table></div></div>"""
    return HTMLResponse(base(content, "channels", key))

@app.post("/channels/add")
async def channels_add(key: str = "", name: str = Form(...), channel_id: str = Form(...)):
    if key != SECRET: return RedirectResponse(f"/channels?key={key}", 303)
    db.add_channel(name.strip(), channel_id.strip())
    return RedirectResponse(f"/channels?key={key}&msg=Канал+добавлен", 303)

@app.post("/channels/delete")
async def channels_delete(key: str = "", channel_id: str = Form(...)):
    if key != SECRET: return RedirectResponse(f"/channels?key={key}", 303)
    db.delete_channel(channel_id)
    return RedirectResponse(f"/channels?key={key}&msg=Удалён", 303)

@app.get("/campaigns", response_class=HTMLResponse)
async def campaigns_page(key: str = "", msg: str = "", err: str = ""):
    r = auth_check(key);
    if r: return r
    channels  = db.get_channels()
    campaigns = db.get_campaigns()
    ch_opts = "".join(f'<option value="{c["channel_id"]}">{c["name"]}</option>' for c in channels) or '<option disabled>Сначала добавь каналы</option>'
    rows = "".join(f"""<tr><td><span class="badge">{c['name']}</span></td>
        <td><span class="tag" style="font-size:.7rem">{c['channel_id']}</span></td>
        <td><div class="link-box" style="max-width:260px">{c['invite_link']}</div></td>
        <td style="color:#34d399;font-weight:600">{c['joins']}</td>
        <td>{c['created_at'][:10]}</td></tr>""" for c in campaigns
    ) or '<tr><td colspan="5"><div class="empty">Кампаний нет</div></td></tr>'
    new_link = msg if msg.startswith("https://") else ""
    alert = f'<div class="alert-green">✅ Ссылка создана:<div class="link-box" style="margin-top:8px">{new_link}</div></div>' if new_link else (f'<div class="alert-red">❌ {err}</div>' if err else "")
    content = f"""<div class="page-wrap"><div class="page-title">🔗 Кампании</div>
    <div class="page-sub">Invite-ссылки для рекламных кампаний</div>{alert}
    <div class="section"><div class="section-head"><h3>➕ Создать ссылку</h3></div><div class="section-body">
    <form method="post" action="/campaigns/create?key={key}"><div class="form-row">
    <div class="field-group"><div class="field-label">Канал</div><select name="channel_id">{ch_opts}</select></div>
    <div class="field-group"><div class="field-label">Название кампании</div><input type="text" name="name" placeholder="FB_Broad_March" required/></div>
    <div style="display:flex;align-items:flex-end"><button class="btn">Создать</button></div>
    </div></form></div></div>
    <div class="section"><div class="section-head"><h3>📋 Кампании ({len(campaigns)})</h3></div>
    <table><thead><tr><th>Кампания</th><th>Канал</th><th>Invite Link</th><th>Подписчиков</th><th>Создана</th></tr></thead>
    <tbody>{rows}</tbody></table></div></div>"""
    return HTMLResponse(base(content, "campaigns", key))

@app.post("/campaigns/create")
async def campaigns_create(key: str = "", channel_id: str = Form(...), name: str = Form(...)):
    if key != SECRET: return RedirectResponse(f"/campaigns?key={key}", 303)
    try:
        b1 = bot_manager.get_tracker_bot()
        if not b1: return RedirectResponse(f"/campaigns?key={key}&err=Бот+1+не+запущен", 303)
        link_obj = await b1.create_chat_invite_link(chat_id=int(channel_id), name=name[:32])
        db.save_campaign(name=name, channel_id=channel_id, invite_link=link_obj.invite_link)
        return RedirectResponse(f"/campaigns?key={key}&msg={link_obj.invite_link}", 303)
    except Exception as e:
        return RedirectResponse(f"/campaigns?key={key}&err={str(e)}", 303)

@app.get("/landing", response_class=HTMLResponse)
async def landing_admin(key: str = "", msg: str = ""):
    r = auth_check(key);
    if r: return r
    links = db.get_landing_links()
    rows = "".join(f"""<tr><td style="font-size:1.2rem">{l['emoji']}</td><td><b>{l['title']}</b></td>
        <td><a href="{l['tg_link']}" target="_blank" style="color:#60a5fa">{l['tg_link']}</a></td>
        <td><form method="post" action="/landing/delete?key={key}" style="display:inline">
        <input type="hidden" name="link_id" value="{l['id']}"/>
        <button class="del-btn">✕</button></form></td></tr>""" for l in links
    ) or '<tr><td colspan="4"><div class="empty">Ссылок нет</div></td></tr>'
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""
    content = f"""<div class="page-wrap"><div class="page-title">🌐 Лендинг</div>
    <div class="page-sub">Публичная страница: <a href="/page" target="_blank" style="color:#3b82f6">/page →</a></div>
    <div class="section"><div class="section-head"><h3>➕ Добавить кнопку</h3></div><div class="section-body">
    {alert}<form method="post" action="/landing/add?key={key}"><div class="form-row">
    <div class="field-group" style="max-width:80px"><div class="field-label">Эмодзи</div><input type="text" name="emoji" value="📢"/></div>
    <div class="field-group"><div class="field-label">Название</div><input type="text" name="title" placeholder="Канал Phoenix" required/></div>
    <div class="field-group"><div class="field-label">Ссылка TG</div><input type="text" name="tg_link" placeholder="https://t.me/+xxxxxxxx" required/></div>
    <div style="display:flex;align-items:flex-end"><button class="btn">Добавить</button></div>
    </div></form></div></div>
    <div class="section"><div class="section-head"><h3>🔗 Кнопки ({len(links)}/10)</h3></div>
    <table><thead><tr><th></th><th>Название</th><th>Ссылка</th><th></th></tr></thead>
    <tbody>{rows}</tbody></table></div></div>"""
    return HTMLResponse(base(content, "landing", key))

@app.post("/landing/add")
async def landing_add(key: str = "", title: str = Form(...), tg_link: str = Form(...), emoji: str = Form("📢")):
    if key != SECRET: return RedirectResponse(f"/landing?key={key}", 303)
    db.add_landing_link(title.strip(), tg_link.strip(), emoji.strip() or "📢")
    return RedirectResponse(f"/landing?key={key}&msg=Добавлено", 303)

@app.post("/landing/delete")
async def landing_delete(key: str = "", link_id: int = Form(...)):
    if key != SECRET: return RedirectResponse(f"/landing?key={key}", 303)
    db.delete_landing_link(link_id)
    return RedirectResponse(f"/landing?key={key}", 303)

@app.get("/page", response_class=HTMLResponse)
async def public_page():
    links = db.get_landing_links()
    title = db.get_setting("landing_title", "Наши каналы")
    sub   = db.get_setting("landing_subtitle", "Подписывайся и будь в курсе")
    btns  = "".join(f'<a href="{l["tg_link"]}" target="_blank" class="ch-btn"><span style="font-size:1.4rem">{l["emoji"]}</span><span style="flex:1;font-weight:600;color:#fff">{l["title"]}</span><span style="color:#3b82f6">→</span></a>' for l in links) or '<p style="text-align:center;color:#475569">Скоро</p>'
    return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
    <style>*{{box-sizing:border-box;margin:0;padding:0}}body{{background:#0a0d14;color:#e2e8f0;min-height:100vh;display:flex;align-items:center;justify-content:center;font-family:system-ui;padding:24px}}
    .wrap{{width:100%;max-width:420px}}h1{{font-size:1.5rem;font-weight:700;text-align:center;margin-bottom:8px;color:#fff}}.sub{{text-align:center;color:#475569;font-size:.9rem;margin-bottom:28px}}
    .ch-btn{{display:flex;align-items:center;gap:14px;background:#111827;border:1px solid #1a2030;border-radius:14px;padding:16px 20px;margin-bottom:10px;transition:all .2s;text-decoration:none}}
    .ch-btn:hover{{background:#1a2030;border-color:#3b82f6;transform:translateY(-2px)}}</style></head>
    <body><div class="wrap"><h1>{title}</h1><p class="sub">{sub}</p>{btns}</div></body></html>""")

@app.get("/flow_clients", response_class=HTMLResponse)
async def flow_clients(key: str = "", msg: str = ""):
    return await _flow_page(key, msg, "tracker", "flow_clients", "💬 Message Flow — Клиенты", "Авто-сообщения после вступления в канал")

@app.get("/flow_staff", response_class=HTMLResponse)
async def flow_staff(key: str = "", msg: str = ""):
    return await _flow_page(key, msg, "staff", "flow_staff", "💬 Message Flow — Сотрудники (HR)", "Авто-сообщения новым сотрудникам")

async def _flow_page(key: str, msg: str, bot_type: str, active_page: str, title: str, sub: str):
    r = auth_check(key);
    if r: return r
    channels = db.get_channels()
    flows    = db.get_flows(bot_type=bot_type)
    ch_opts  = "".join(f'<option value="{c["channel_id"]}">{c["name"]}</option>' for c in channels) or '<option value="all">Все</option>'
    ch_map   = {c["channel_id"]: c["name"] for c in channels}
    rows = "".join(f"""<tr><td><span class="badge">{ch_map.get(f['channel_id'],f['channel_id'])}</span></td>
        <td>Шаг {f['step']}</td><td>{f['delay_min']} мин</td>
        <td>{f['message'][:60]}{'…' if len(f['message'])>60 else ''}</td>
        <td><form method="post" action="/flow/delete?key={key}&next={active_page}" style="display:inline">
        <input type="hidden" name="flow_id" value="{f['id']}"/>
        <button class="del-btn">✕</button></form></td></tr>""" for f in flows
    ) or '<tr><td colspan="5"><div class="empty">Нет шагов</div></td></tr>'
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""
    btn_cls = "btn" if bot_type == "tracker" else "btn btn-orange"
    content = f"""<div class="page-wrap"><div class="page-title">{title}</div><div class="page-sub">{sub}</div>
    <div class="section"><div class="section-head"><h3>➕ Добавить шаг</h3></div><div class="section-body">
    {alert}<form method="post" action="/flow/add?key={key}&next={active_page}">
    <input type="hidden" name="bot_type" value="{bot_type}"/>
    <div class="form-row" style="margin-bottom:12px">
    <div class="field-group"><div class="field-label">Канал</div><select name="channel_id">{ch_opts}</select></div>
    <div class="field-group" style="max-width:100px"><div class="field-label">Шаг №</div><input type="number" name="step" value="0" min="0"/></div>
    <div class="field-group" style="max-width:160px"><div class="field-label">Задержка (мин)</div><input type="number" name="delay_min" value="0" min="0"/></div></div>
    <div class="field-group" style="margin-bottom:12px"><div class="field-label">Текст сообщения</div>
    <textarea name="message" placeholder="Текст автосообщения..." required></textarea></div>
    <button class="{btn_cls}">Добавить шаг</button></form></div></div>
    <div class="section"><div class="section-head"><h3>📋 Шаги ({len(flows)})</h3></div>
    <table><thead><tr><th>Канал</th><th>Шаг</th><th>Задержка</th><th>Сообщение</th><th></th></tr></thead>
    <tbody>{rows}</tbody></table></div></div>"""
    return HTMLResponse(base(content, active_page, key))

@app.post("/flow/add")
async def flow_add(key: str = "", next: str = "flow_clients", channel_id: str = Form(...),
                   bot_type: str = Form("tracker"), step: int = Form(0), delay_min: int = Form(0), message: str = Form(...)):
    if key != SECRET: return RedirectResponse(f"/{next}?key={key}", 303)
    db.add_flow_step(channel_id, bot_type, step, delay_min, message)
    return RedirectResponse(f"/{next}?key={key}&msg=Шаг+добавлен", 303)

@app.post("/flow/delete")
async def flow_delete(key: str = "", next: str = "flow_clients", flow_id: int = Form(...)):
    if key != SECRET: return RedirectResponse(f"/{next}?key={key}", 303)
    db.delete_flow_step(flow_id)
    return RedirectResponse(f"/{next}?key={key}", 303)

@app.get("/health")
async def health():
    b1 = bool(bot_manager.get_tracker_bot())
    b2 = bool(bot_manager.get_staff_bot())
    return {"status": "ok", "version": "4.0", "bot1": b1, "bot2": b2}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
