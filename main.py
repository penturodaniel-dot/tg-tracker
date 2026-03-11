import asyncio
import logging
import os
import json
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher, types as tg_types
from aiogram.filters import ChatMemberUpdatedFilter, JOIN_TRANSITION, Command
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from database import Database
from meta_capi import send_subscribe_event

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
SECRET    = os.getenv("DASHBOARD_PASSWORD", "changeme")
DEFAULT_PIXEL_ID   = os.getenv("PIXEL_ID", "")
DEFAULT_META_TOKEN = os.getenv("META_TOKEN", "")

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher()
db  = Database()

if not db.get_setting("pixel_id") and DEFAULT_PIXEL_ID:
    db.set_setting("pixel_id", DEFAULT_PIXEL_ID)
if not db.get_setting("meta_token") and DEFAULT_META_TOKEN:
    db.set_setting("meta_token", DEFAULT_META_TOKEN)


# ══════════════════════════════════════════════════════════════════════════════
# BOT HANDLERS
# ══════════════════════════════════════════════════════════════════════════════

@dp.chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def on_user_join(event: tg_types.ChatMemberUpdated):
    channel_ids = db.get_channel_ids()
    cid = str(event.chat.id)
    if cid not in channel_ids:
        return
    user = event.new_chat_member.user
    raw_link = event.invite_link.invite_link if event.invite_link else None
    campaign = db.get_campaign_by_link(raw_link)
    campaign_name = campaign["name"] if campaign else "organic"
    db.log_join(user_id=user.id, channel_id=cid, invite_link=raw_link, campaign_name=campaign_name)
    pixel_id   = db.get_setting("pixel_id")
    meta_token = db.get_setting("meta_token")
    await send_subscribe_event(pixel_id, meta_token, str(user.id), campaign_name)
    asyncio.create_task(send_flow_messages(user.id, cid))


@dp.message(Command("start"))
async def on_start(message: tg_types.Message):
    user = message.from_user
    name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Гость"
    username = user.username
    conv = db.get_or_create_conversation(str(user.id), name, username)
    db.get_or_create_client(str(user.id), name, username, conv["id"])
    welcome = db.get_setting("welcome_message", "Привет! Чем могу помочь? 👋")
    await message.answer(welcome)
    log.info(f"START user={user.id} name={name}")


@dp.message()
async def on_message(message: tg_types.Message):
    if message.chat.type != "private":
        return
    user = message.from_user
    name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Гость"
    username = user.username
    text = message.text or message.caption or "[медиафайл]"

    conv = db.get_or_create_conversation(str(user.id), name, username)
    db.get_or_create_client(str(user.id), name, username, conv["id"])
    db.save_message(
        conversation_id=conv["id"],
        tg_chat_id=str(user.id),
        sender_type="visitor",
        content=text,
        tg_message_id=message.message_id
    )
    db.update_conversation_last_message(str(user.id), text, increment_unread=True)
    log.info(f"MSG from user={user.id}: {text[:50]}")


async def send_flow_messages(user_id: int, channel_id: str):
    flows = db.get_flows(channel_id)
    for flow in flows:
        if not flow["active"]: continue
        if db.was_flow_sent(user_id, channel_id, flow["step"]): continue
        if flow["delay_min"] > 0:
            await asyncio.sleep(flow["delay_min"] * 60)
        try:
            await bot.send_message(user_id, flow["message"])
            db.log_flow_sent(user_id, channel_id, flow["step"])
        except Exception as e:
            log.warning(f"Flow error user={user_id}: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(dp.start_polling(bot, allowed_updates=["chat_member", "message"]))
    log.info("Bot polling started")
    yield
    await bot.session.close()


app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ══════════════════════════════════════════════════════════════════════════════
# CSS + NAV
# ══════════════════════════════════════════════════════════════════════════════

CSS = """
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:#0a0d14;color:#e2e8f0;min-height:100vh}
a{color:inherit;text-decoration:none}
.sidebar{position:fixed;top:0;left:0;width:220px;height:100vh;background:#0f1219;border-right:1px solid #1e2535;padding:24px 0;z-index:10;overflow-y:auto}
.sidebar .logo{padding:0 20px 24px;font-size:1.1rem;font-weight:700;color:#fff;border-bottom:1px solid #1e2535;display:flex;align-items:center;gap:8px}
.sidebar .logo span{color:#3b82f6}
.nav-item{display:flex;align-items:center;justify-content:space-between;padding:11px 20px;font-size:.88rem;color:#94a3b8;cursor:pointer;transition:all .15s}
.nav-item:hover,.nav-item.active{background:#1a2030;color:#fff}
.nav-item.active{border-right:2px solid #3b82f6}
.nav-label{display:flex;align-items:center;gap:10px}
.badge-count{background:#ef4444;color:#fff;border-radius:20px;padding:1px 7px;font-size:.72rem;font-weight:700}
.main{margin-left:220px;padding:0}
/* ── CHAT LAYOUT ── */
.chat-layout{display:grid;grid-template-columns:320px 1fr;height:100vh}
.conv-list{background:#0f1219;border-right:1px solid #1e2535;overflow-y:auto;display:flex;flex-direction:column}
.conv-search{padding:16px;border-bottom:1px solid #1e2535}
.conv-search input{width:100%;background:#0a0d14;border:1px solid #1e2535;border-radius:8px;padding:8px 12px;color:#e2e8f0;font-size:.85rem;outline:none}
.conv-search input:focus{border-color:#3b82f6}
.conv-item{padding:14px 16px;border-bottom:1px solid #0a0d14;cursor:pointer;transition:background .15s;position:relative}
.conv-item:hover{background:#151b27}
.conv-item.active{background:#1a2535;border-right:2px solid #3b82f6}
.conv-item.unread{background:#111827}
.conv-name{font-weight:600;font-size:.9rem;color:#fff;margin-bottom:3px;display:flex;align-items:center;justify-content:space-between}
.conv-preview{font-size:.8rem;color:#64748b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:220px}
.conv-time{font-size:.72rem;color:#475569}
.unread-dot{width:8px;height:8px;background:#3b82f6;border-radius:50%;flex-shrink:0}
.unread-num{background:#3b82f6;color:#fff;border-radius:20px;padding:1px 6px;font-size:.7rem;font-weight:700}
/* ── CHAT WINDOW ── */
.chat-window{display:flex;flex-direction:column;height:100vh}
.chat-header{padding:16px 20px;border-bottom:1px solid #1e2535;background:#0f1219;display:flex;align-items:center;justify-content:space-between;flex-shrink:0}
.chat-header-info h3{font-size:1rem;font-weight:600;color:#fff}
.chat-header-info p{font-size:.8rem;color:#64748b;margin-top:2px}
.chat-header-actions{display:flex;gap:8px}
.chat-messages{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:12px;background:#0a0d14}
.msg{max-width:70%;word-break:break-word}
.msg.visitor{align-self:flex-start}
.msg.manager{align-self:flex-end}
.msg-bubble{padding:10px 14px;border-radius:14px;font-size:.9rem;line-height:1.5}
.msg.visitor .msg-bubble{background:#1e2535;color:#e2e8f0;border-bottom-left-radius:4px}
.msg.manager .msg-bubble{background:#2563eb;color:#fff;border-bottom-right-radius:4px}
.msg-time{font-size:.72rem;color:#475569;margin-top:4px;text-align:right}
.msg.visitor .msg-time{text-align:left}
.chat-input{padding:16px 20px;border-top:1px solid #1e2535;background:#0f1219;flex-shrink:0}
.chat-input-row{display:flex;gap:10px;align-items:flex-end}
.chat-input textarea{flex:1;background:#0a0d14;border:1px solid #1e2535;border-radius:10px;padding:10px 14px;color:#e2e8f0;font-size:.9rem;outline:none;resize:none;max-height:120px;font-family:system-ui}
.chat-input textarea:focus{border-color:#3b82f6}
.send-btn{background:#3b82f6;color:#fff;border:none;border-radius:10px;padding:10px 18px;cursor:pointer;font-size:.9rem;font-weight:600;flex-shrink:0;height:42px}
.send-btn:hover{background:#2563eb}
.no-conv{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:#475569;gap:12px}
.no-conv-icon{font-size:3rem}
/* ── GENERAL ── */
.page-wrap{padding:32px}
.page-title{font-size:1.4rem;font-weight:700;color:#fff;margin-bottom:6px}
.page-sub{font-size:.85rem;color:#64748b;margin-bottom:28px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-bottom:28px}
.card{background:#111827;border:1px solid #1e2535;border-radius:12px;padding:18px}
.card .val{font-size:1.8rem;font-weight:700;color:#60a5fa}
.card .lbl{font-size:.78rem;color:#64748b;margin-top:4px}
.section{background:#111827;border:1px solid #1e2535;border-radius:12px;margin-bottom:20px;overflow:hidden}
.section-head{padding:14px 20px;border-bottom:1px solid #1e2535;display:flex;justify-content:space-between;align-items:center}
.section-head h3{font-size:.95rem;font-weight:600}
.section-body{padding:20px}
table{width:100%;border-collapse:collapse}
th{padding:10px 14px;text-align:left;font-size:.75rem;text-transform:uppercase;color:#64748b;letter-spacing:.05em;border-bottom:1px solid #1e2535}
td{padding:11px 14px;font-size:.86rem;border-bottom:1px solid #0f1219}
tr:last-child td{border-bottom:none}
.badge{display:inline-block;padding:2px 10px;border-radius:20px;font-size:.75rem;background:#1e3a5f;color:#60a5fa}
.badge-green{background:#052e16;color:#34d399}
.form-row{display:flex;gap:10px;flex-wrap:wrap}
input[type=text],input[type=number],input[type=email],select,textarea{background:#0a0d14;border:1px solid #1e2535;border-radius:8px;padding:9px 14px;color:#e2e8f0;font-size:.88rem;outline:none;width:100%}
input:focus,select:focus,textarea:focus{border-color:#3b82f6}
textarea{resize:vertical;min-height:80px;font-family:system-ui}
.btn{background:#3b82f6;color:#fff;border:none;border-radius:8px;padding:9px 20px;cursor:pointer;font-size:.88rem;font-weight:600;white-space:nowrap}
.btn:hover{background:#2563eb}
.btn-red{background:#dc2626}.btn-red:hover{background:#b91c1c}
.btn-gray{background:#1e2535;color:#94a3b8;border:none}.btn-gray:hover{background:#2d3748;color:#fff}
.btn-green{background:#059669;color:#fff;border:none}.btn-green:hover{background:#047857}
.btn-sm{padding:5px 12px;font-size:.8rem}
.link-box{background:#0a0d14;border:1px solid #1e2535;border-radius:6px;padding:8px 12px;font-family:monospace;font-size:.8rem;word-break:break-all;color:#a5f3fc}
.alert-green{background:#052e16;border:1px solid #166534;border-radius:8px;padding:12px 16px;color:#86efac;margin-bottom:16px;font-size:.88rem}
.alert-red{background:#2d0a0a;border:1px solid #7f1d1d;border-radius:8px;padding:12px 16px;color:#fca5a5;margin-bottom:16px;font-size:.88rem}
.empty{text-align:center;padding:28px;color:#475569;font-size:.88rem}
.tag{display:inline-block;background:#1e2535;border-radius:4px;padding:2px 8px;font-size:.75rem;color:#94a3b8;font-family:monospace}
.del-btn{background:none;border:none;cursor:pointer;color:#ef4444;font-size:.88rem;padding:4px 8px;border-radius:4px}
.del-btn:hover{background:#2d0a0a}
.field-group{display:flex;flex-direction:column;gap:6px;flex:1}
.field-label{font-size:.78rem;color:#64748b;font-weight:500}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.status-open{color:#34d399}.status-closed{color:#ef4444}
.avatar{width:38px;height:38px;border-radius:50%;background:#1e3a5f;display:flex;align-items:center;justify-content:center;font-size:1rem;flex-shrink:0;font-weight:700;color:#60a5fa}
</style>
"""

NAV = [
    ("📊", "Обзор",        "overview",   False),
    ("💬", "Чаты",         "chat",       True),
    ("📡", "Каналы",       "channels",   False),
    ("🔗", "Кампании",     "campaigns",  False),
    ("👥", "Клиенты",      "clients",    False),
    ("🌐", "Лендинг",      "landing",    False),
    ("💬", "Msg Flow",     "flow",       False),
    ("⚙️",  "Настройки",   "settings",   False),
]

def nav_html(active: str, key: str) -> str:
    stats = db.get_stats()
    unread = stats.get("unread", 0)
    items = ""
    for icon, label, page, show_badge in NAV:
        cls = "nav-item active" if page == active else "nav-item"
        badge = f'<span class="badge-count">{unread}</span>' if show_badge and unread > 0 else ""
        items += f'<a href="/{page}?key={key}" class="{cls}"><span class="nav-label">{icon} {label}</span>{badge}</a>'
    return f'<div class="sidebar"><div class="logo">📡 TG<span>Tracker</span></div>{items}</div>'

def base(content: str, active: str, key: str) -> str:
    return f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>TG Tracker</title>{CSS}</head><body>{nav_html(active, key)}<div class="main">{content}</div></body></html>'

def auth_check(key: str):
    if key != SECRET:
        return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Login</title>{CSS}</head>
        <body><div style="max-width:340px;margin:80px auto">
        <div class="page-title" style="margin-bottom:20px">🔐 TG Tracker</div>
        <form method="get"><div class="form-row">
        <input type="text" name="key" placeholder="Пароль"/>
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
    <div class="page-sub">Общая статистика</div>
    <div class="cards">
      <div class="card"><div class="val">{s['total']}</div><div class="lbl">Подписчиков</div></div>
      <div class="card"><div class="val">{s['from_ads']}</div><div class="lbl">Из рекламы</div></div>
      <div class="card"><div class="val">{s['conversations']}</div><div class="lbl">Диалогов</div></div>
      <div class="card"><div class="val" style="color:#ef4444">{s['unread']}</div><div class="lbl">Непрочитанных</div></div>
      <div class="card"><div class="val">{s['channels']}</div><div class="lbl">Каналов</div></div>
    </div>
    <div class="section">
      <div class="section-head"><h3>🕐 Последние подписки</h3><span class="tag">Pixel: {pixel}</span></div>
      <table><thead><tr><th>Время</th><th>Канал</th><th>Кампания</th></tr></thead><tbody>{rows}</tbody></table>
    </div></div>"""
    return HTMLResponse(base(content, "overview", key))


# ══════════════════════════════════════════════════════════════════════════════
# CHAT PANEL
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/chat", response_class=HTMLResponse)
async def chat_panel(key: str = "", conv_id: int = 0):
    err = auth_check(key)
    if err: return err

    convs = db.get_conversations()
    active_conv = None
    messages_html = ""
    header_html = ""

    if conv_id:
        active_conv = db.get_conversation(conv_id)
        if active_conv:
            db.mark_conversation_read(conv_id)
            msgs = db.get_messages(conv_id)
            client = db.get_client_by_conv(conv_id)
            for m in msgs:
                t = m["created_at"][11:16]
                sender = m["sender_type"]
                content = m["content"] or ""
                messages_html += f"""
                <div class="msg {sender}">
                  <div class="msg-bubble">{content}</div>
                  <div class="msg-time">{t}</div>
                </div>"""

            status_badge = f'<span class="status-{active_conv["status"]}">{active_conv["status"]}</span>'
            uname = f"@{active_conv['username']}" if active_conv.get('username') else active_conv.get('tg_chat_id','')

            # Client info panel
            client_html = ""
            if client:
                client_html = f"""
                <div style="background:#0a0d14;border:1px solid #1e2535;border-radius:8px;padding:12px;margin-top:8px;font-size:.82rem">
                  <div style="color:#64748b;margin-bottom:6px">👤 Карточка клиента</div>
                  <div style="color:#94a3b8">📞 {client.get('phone') or '—'}</div>
                  <div style="color:#94a3b8">📧 {client.get('email') or '—'}</div>
                  {f'<div style="color:#94a3b8;margin-top:4px">📝 {client["notes"]}</div>' if client.get('notes') else ''}
                  <a href="/clients?key={key}&edit={client['id']}" style="color:#3b82f6;font-size:.78rem">Редактировать →</a>
                </div>"""

            close_btn = ""
            if active_conv["status"] == "open":
                close_btn = f'<form method="post" action="/chat/close?key={key}" style="display:inline"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn btn-gray btn-sm">✓ Закрыть</button></form>'
            else:
                close_btn = f'<form method="post" action="/chat/reopen?key={key}" style="display:inline"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn btn-sm" style="background:#059669">↺ Открыть</button></form>'

            header_html = f"""
            <div class="chat-header">
              <div style="display:flex;align-items:center;gap:12px">
                <div class="avatar">{active_conv['visitor_name'][0].upper()}</div>
                <div class="chat-header-info">
                  <h3>{active_conv['visitor_name']} {status_badge}</h3>
                  <p>{uname}</p>
                  {client_html}
                </div>
              </div>
              <div class="chat-header-actions">
                <a href="https://t.me/{active_conv.get('username','')}" target="_blank">
                  <button class="btn btn-gray btn-sm">Telegram →</button>
                </a>
                {close_btn}
              </div>
            </div>"""

    # Conversations list
    conv_items = ""
    for c in convs:
        is_active = c["id"] == conv_id
        cls = "conv-item active" if is_active else ("conv-item unread" if c["unread_count"] > 0 else "conv-item")
        time_str = (c.get("last_message_at") or c["created_at"])[:16].replace("T", " ")
        preview = c.get("last_message") or "Нет сообщений"
        ucount = f'<span class="unread-num">{c["unread_count"]}</span>' if c["unread_count"] > 0 else ""
        status_dot = "🟢" if c["status"] == "open" else "⚫"
        conv_items += f"""
        <a href="/chat?key={key}&conv_id={c['id']}">
          <div class="{cls}">
            <div class="conv-name">
              <span>{status_dot} {c['visitor_name']}</span>
              {ucount}
            </div>
            <div class="conv-preview">{preview}</div>
            <div class="conv-time">{time_str}</div>
          </div>
        </a>"""

    if not conv_items:
        conv_items = '<div class="empty" style="padding:40px 16px">Диалогов пока нет.<br><br>Люди начнут появляться<br>когда напишут боту</div>'

    # Right panel
    if active_conv and conv_id:
        right_panel = f"""
        {header_html}
        <div class="chat-messages" id="msgs">{messages_html}</div>
        <div class="chat-input">
          <div class="chat-input-row">
            <textarea id="reply-text" placeholder="Написать сообщение... (Enter — отправить, Shift+Enter — новая строка)"
              rows="1" onkeydown="handleKey(event)"></textarea>
            <button class="send-btn" onclick="sendMsg()">Отправить</button>
          </div>
        </div>"""
    else:
        right_panel = """
        <div class="no-conv">
          <div class="no-conv-icon">💬</div>
          <div>Выбери диалог слева</div>
          <div style="font-size:.82rem;color:#334155">или дождись нового сообщения</div>
        </div>"""

    content = f"""
    <div class="chat-layout">
      <div class="conv-list">
        <div class="conv-search"><input type="text" id="search" placeholder="🔍 Поиск..." oninput="filterConvs(this.value)"/></div>
        <div id="conv-items">{conv_items}</div>
      </div>
      <div class="chat-window">{right_panel}</div>
    </div>
    <script>
    // Scroll to bottom
    const msgsEl = document.getElementById('msgs');
    if (msgsEl) msgsEl.scrollTop = msgsEl.scrollHeight;

    // Send message
    async function sendMsg() {{
      const ta = document.getElementById('reply-text');
      const text = ta.value.trim();
      if (!text) return;
      ta.value = '';
      const res = await fetch('/chat/send?key={key}', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
        body: 'conv_id={conv_id}&text=' + encodeURIComponent(text)
      }});
      if (res.ok) loadNewMsgs();
    }}

    function handleKey(e) {{
      if (e.key === 'Enter' && !e.shiftKey) {{ e.preventDefault(); sendMsg(); }}
    }}

    // Poll for new messages every 3 seconds
    let lastId = {f"document.querySelectorAll('.msg').length" if active_conv else 0};
    {"setInterval(loadNewMsgs, 3000);" if active_conv and conv_id else "setInterval(checkUnread, 5000);"}

    async function loadNewMsgs() {{
      const msgs = document.querySelectorAll('.msg');
      const lastMsgEl = msgs[msgs.length-1];
      const lastMsgId = lastMsgEl ? lastMsgEl.dataset.id : 0;
      const res = await fetch('/api/messages/{conv_id}?after=' + (lastMsgId || 0) + '&key={key}');
      const data = await res.json();
      if (data.messages && data.messages.length > 0) {{
        const container = document.getElementById('msgs');
        data.messages.forEach(m => {{
          const div = document.createElement('div');
          div.className = 'msg ' + m.sender_type;
          div.dataset.id = m.id;
          div.innerHTML = '<div class="msg-bubble">' + escHtml(m.content) + '</div><div class="msg-time">' + m.created_at.substring(11,16) + '</div>';
          container.appendChild(div);
        }});
        container.scrollTop = container.scrollHeight;
      }}
      // Update sidebar unread
      updateSidebarBadge();
    }}

    async function checkUnread() {{
      updateSidebarBadge();
    }}

    async function updateSidebarBadge() {{
      const res = await fetch('/api/stats?key={key}');
      const data = await res.json();
      const badge = document.querySelector('.nav-item .badge-count');
      if (data.unread > 0) {{
        if (badge) badge.textContent = data.unread;
        else {{
          const chatNav = document.querySelector('a[href*="/chat"]');
          if (chatNav) {{
            const sp = document.createElement('span');
            sp.className = 'badge-count';
            sp.textContent = data.unread;
            chatNav.appendChild(sp);
          }}
        }}
      }} else if (badge) badge.remove();
    }}

    function escHtml(t) {{
      return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\\n/g,'<br>');
    }}

    function filterConvs(q) {{
      document.querySelectorAll('.conv-item').forEach(el => {{
        const name = el.querySelector('.conv-name')?.textContent?.toLowerCase() || '';
        el.parentElement.style.display = name.includes(q.toLowerCase()) ? '' : 'none';
      }});
    }}
    </script>"""

    return HTMLResponse(f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>TG Tracker — Чаты</title>{CSS}</head><body>{nav_html("chat", key)}<div class="main">{content}</div></body></html>')


@app.post("/chat/send")
async def chat_send(key: str = "", conv_id: int = Form(...), text: str = Form(...)):
    if key != SECRET:
        return JSONResponse({"error": "unauthorized"}, 401)
    conv = db.get_conversation(conv_id)
    if not conv:
        return JSONResponse({"error": "not found"}, 404)
    try:
        await bot.send_message(int(conv["tg_chat_id"]), text)
        db.save_message(conv_id, conv["tg_chat_id"], "manager", text)
        db.update_conversation_last_message(conv["tg_chat_id"], f"Вы: {text}", increment_unread=False)
        return JSONResponse({"ok": True})
    except Exception as e:
        log.error(f"Send error: {e}")
        return JSONResponse({"error": str(e)}, 500)


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


# ── API endpoints ─────────────────────────────────────────────────────────────

@app.get("/api/messages/{conv_id}")
async def api_messages(conv_id: int, after: int = 0, key: str = ""):
    if key != SECRET: return JSONResponse({"error": "unauthorized"}, 401)
    msgs = db.get_new_messages(conv_id, after)
    return JSONResponse({"messages": msgs})


@app.get("/api/stats")
async def api_stats(key: str = ""):
    if key != SECRET: return JSONResponse({"error": "unauthorized"}, 401)
    return JSONResponse(db.get_stats())


# ══════════════════════════════════════════════════════════════════════════════
# CLIENTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/clients", response_class=HTMLResponse)
async def clients_page(key: str = "", edit: int = 0, msg: str = ""):
    err = auth_check(key)
    if err: return err

    clients = db.get_clients()
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""

    edit_form = ""
    if edit:
        from database import Database as DB2
        db2 = db
        with db2._conn() as conn:
            cl = conn.execute("SELECT * FROM clients WHERE id=?", (edit,)).fetchone()
        if cl:
            cl = dict(cl)
            edit_form = f"""
            <div class="section" style="margin-bottom:24px">
              <div class="section-head"><h3>✏️ Редактировать клиента: {cl['name']}</h3></div>
              <div class="section-body">
                <form method="post" action="/clients/update?key={key}">
                  <input type="hidden" name="client_id" value="{cl['id']}"/>
                  <div class="grid-2" style="margin-bottom:12px">
                    <div class="field-group"><div class="field-label">Имя</div>
                      <input type="text" name="name" value="{cl.get('name') or ''}"/></div>
                    <div class="field-group"><div class="field-label">Телефон</div>
                      <input type="text" name="phone" value="{cl.get('phone') or ''}"/></div>
                    <div class="field-group"><div class="field-label">Email</div>
                      <input type="email" name="email" value="{cl.get('email') or ''}"/></div>
                    <div class="field-group"><div class="field-label">Теги (через запятую)</div>
                      <input type="text" name="tags" value="{cl.get('tags') or ''}"/></div>
                  </div>
                  <div class="field-group" style="margin-bottom:12px">
                    <div class="field-label">Заметки</div>
                    <textarea name="notes">{cl.get('notes') or ''}</textarea>
                  </div>
                  <div style="display:flex;gap:8px">
                    <button class="btn">💾 Сохранить</button>
                    <a href="/clients?key={key}"><button class="btn btn-gray" type="button">Отмена</button></a>
                  </div>
                </form>
              </div>
            </div>"""

    rows = "".join(f"""<tr>
        <td>
          <div style="font-weight:600;color:#fff">{c['name'] or '—'}</div>
          <div style="font-size:.78rem;color:#64748b">@{c['username'] or '—'}</div>
        </td>
        <td>{c.get('phone') or '—'}</td>
        <td>{c.get('email') or '—'}</td>
        <td style="font-size:.78rem;color:#94a3b8">{c.get('tags') or '—'}</td>
        <td>{c['created_at'][:10]}</td>
        <td>
          <a href="/clients?key={key}&edit={c['id']}"><button class="btn btn-sm">✏️</button></a>
          {'<a href="/chat?key=' + key + '&conv_id=' + str(c.get("conversation_id","")) + '"><button class="btn btn-gray btn-sm" style="margin-left:4px">💬</button></a>' if c.get("conversation_id") else ''}
        </td>
    </tr>""" for c in clients) or '<tr><td colspan="6"><div class="empty">Клиентов пока нет</div></td></tr>'

    content = f"""<div class="page-wrap">
    <div class="page-title">👥 База клиентов</div>
    <div class="page-sub">Все кто написал боту</div>
    {alert}
    {edit_form}
    <div class="section">
      <div class="section-head"><h3>📋 Клиенты ({len(clients)})</h3></div>
      <table><thead><tr><th>Имя</th><th>Телефон</th><th>Email</th><th>Теги</th><th>Добавлен</th><th></th></tr></thead>
      <tbody>{rows}</tbody></table>
    </div></div>"""
    return HTMLResponse(base(content, "clients", key))


@app.post("/clients/update")
async def clients_update(key: str = "", client_id: int = Form(...), name: str = Form(""),
                          phone: str = Form(""), email: str = Form(""),
                          notes: str = Form(""), tags: str = Form("")):
    if key != SECRET: return RedirectResponse(f"/clients?key={key}", 303)
    db.update_client(client_id, name, phone, email, notes, tags)
    return RedirectResponse(f"/clients?key={key}&msg=Клиент+обновлён", 303)


# ══════════════════════════════════════════════════════════════════════════════
# CHANNELS, CAMPAIGNS, LANDING, FLOW, SETTINGS — без изменений из v2
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/channels", response_class=HTMLResponse)
async def channels_page(key: str = "", msg: str = "", err: str = ""):
    r = auth_check(key)
    if r: return r
    channels = db.get_channels()
    bot_info = await bot.get_me()
    bot_link = f"https://t.me/{bot_info.username}"
    rows = "".join(f"""<tr><td><b>{c['name']}</b></td><td><span class="tag">{c['channel_id']}</span></td>
        <td style="color:#34d399;font-weight:600">{c['total_joins']}</td><td>{c['created_at'][:10]}</td>
        <td><form method="post" action="/channels/delete?key={key}" style="display:inline">
        <input type="hidden" name="channel_id" value="{c['channel_id']}"/>
        <button class="del-btn">✕</button></form></td></tr>""" for c in channels
    ) or '<tr><td colspan="5"><div class="empty">Каналов нет</div></td></tr>'
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else (f'<div class="alert-red">❌ {err}</div>' if err else "")
    content = f"""<div class="page-wrap">
    <div class="page-title">📡 Каналы</div><div class="page-sub">Управление каналами</div>
    <div class="section"><div class="section-head"><h3>🤖 Ссылка на бота</h3></div>
    <div class="section-body"><p style="color:#94a3b8;font-size:.88rem;margin-bottom:10px">
    Добавь как <b style="color:#fff">Администратора</b> в каждый канал:</p>
    <div class="link-box">{bot_link}</div></div></div>
    <div class="section"><div class="section-head"><h3>➕ Добавить</h3></div><div class="section-body">
    {alert}<form method="post" action="/channels/add?key={key}"><div class="form-row">
    <div class="field-group"><div class="field-label">Название</div>
    <input type="text" name="name" placeholder="Phoenix" required/></div>
    <div class="field-group"><div class="field-label">ID канала</div>
    <input type="text" name="channel_id" placeholder="-1003835844880" required/></div>
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
    r = auth_check(key)
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
    alert = f'<div class="alert-green">✅ Ссылка:<div class="link-box" style="margin-top:8px">{new_link}</div></div>' if new_link else (f'<div class="alert-red">❌ {err}</div>' if err else "")
    content = f"""<div class="page-wrap">
    <div class="page-title">🔗 Кампании</div><div class="page-sub">Ссылки для рекламы</div>{alert}
    <div class="section"><div class="section-head"><h3>➕ Создать</h3></div><div class="section-body">
    <form method="post" action="/campaigns/create?key={key}"><div class="form-row">
    <div class="field-group"><div class="field-label">Канал</div><select name="channel_id">{ch_opts}</select></div>
    <div class="field-group"><div class="field-label">Название</div><input type="text" name="name" placeholder="FB_Broad_March" required/></div>
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
        link_obj = await bot.create_chat_invite_link(chat_id=int(channel_id), name=name[:32])
        db.save_campaign(name=name, channel_id=channel_id, invite_link=link_obj.invite_link)
        return RedirectResponse(f"/campaigns?key={key}&msg={link_obj.invite_link}", 303)
    except Exception as e:
        return RedirectResponse(f"/campaigns?key={key}&err={str(e)}", 303)

@app.get("/landing", response_class=HTMLResponse)
async def landing_admin(key: str = "", msg: str = ""):
    r = auth_check(key); 
    if r: return r
    links = db.get_landing_links()
    rows = "".join(f"""<tr><td style="font-size:1.3rem">{l['emoji']}</td><td><b>{l['title']}</b></td>
        <td><a href="{l['tg_link']}" target="_blank" style="color:#60a5fa">{l['tg_link']}</a></td>
        <td><form method="post" action="/landing/delete?key={key}" style="display:inline">
        <input type="hidden" name="link_id" value="{l['id']}"/>
        <button class="del-btn">✕</button></form></td></tr>""" for l in links
    ) or '<tr><td colspan="4"><div class="empty">Ссылок нет</div></td></tr>'
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""
    content = f"""<div class="page-wrap"><div class="page-title">🌐 Лендинг</div>
    <div class="page-sub">Публичная страница: <a href="/page" target="_blank" style="color:#3b82f6">/page</a></div>
    <div class="section"><div class="section-head"><h3>➕ Добавить ссылку</h3></div><div class="section-body">
    {alert}<form method="post" action="/landing/add?key={key}"><div class="form-row">
    <div class="field-group" style="max-width:80px"><div class="field-label">Эмодзи</div>
    <input type="text" name="emoji" value="📢"/></div>
    <div class="field-group"><div class="field-label">Название</div>
    <input type="text" name="title" placeholder="Канал Phoenix" required/></div>
    <div class="field-group"><div class="field-label">Ссылка</div>
    <input type="text" name="tg_link" placeholder="https://t.me/+xxxxxxxx" required/></div>
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
    return RedirectResponse(f"/landing?key={key}&msg=Ссылка+добавлена", 303)

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
    btns  = "".join(f"""<a href="{l['tg_link']}" target="_blank" class="ch-btn">
        <span style="font-size:1.5rem">{l['emoji']}</span>
        <span style="flex:1;font-size:1rem;font-weight:600;color:#fff">{l['title']}</span>
        <span style="color:#3b82f6">→</span></a>""" for l in links
    ) or '<p style="color:#555;text-align:center">Скоро</p>'
    return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
    <style>*{{box-sizing:border-box;margin:0;padding:0}}body{{background:#0a0d14;color:#e2e8f0;min-height:100vh;display:flex;align-items:center;justify-content:center;font-family:system-ui;padding:24px}}
    .wrap{{width:100%;max-width:420px}}h1{{font-size:1.6rem;font-weight:700;text-align:center;margin-bottom:8px}}
    .sub{{text-align:center;color:#64748b;font-size:.9rem;margin-bottom:32px}}
    .ch-btn{{display:flex;align-items:center;gap:14px;background:#111827;border:1px solid #1e2535;border-radius:14px;padding:16px 20px;margin-bottom:12px;transition:all .2s;cursor:pointer;text-decoration:none}}
    .ch-btn:hover{{background:#1a2030;border-color:#3b82f6;transform:translateY(-2px)}}</style></head>
    <body><div class="wrap"><h1>{title}</h1><p class="sub">{sub}</p>{btns}</div></body></html>""")

@app.get("/flow", response_class=HTMLResponse)
async def flow_page(key: str = "", msg: str = ""):
    r = auth_check(key); 
    if r: return r
    channels = db.get_channels()
    flows    = db.get_flows()
    ch_opts  = "".join(f'<option value="{c["channel_id"]}">{c["name"]}</option>' for c in channels) or '<option disabled>Нет каналов</option>'
    ch_map   = {c["channel_id"]: c["name"] for c in channels}
    rows = "".join(f"""<tr><td><span class="badge">{ch_map.get(f['channel_id'],f['channel_id'])}</span></td>
        <td>Шаг {f['step']}</td><td>{f['delay_min']} мин</td>
        <td>{f['message'][:60]}{'…' if len(f['message'])>60 else ''}</td>
        <td><form method="post" action="/flow/delete?key={key}" style="display:inline">
        <input type="hidden" name="flow_id" value="{f['id']}"/>
        <button class="del-btn">✕</button></form></td></tr>""" for f in flows
    ) or '<tr><td colspan="5"><div class="empty">Нет шагов</div></td></tr>'
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""
    content = f"""<div class="page-wrap"><div class="page-title">💬 Message Flow</div>
    <div class="page-sub">Авто-сообщения новым подписчикам</div>
    <div class="section"><div class="section-head"><h3>➕ Добавить шаг</h3></div><div class="section-body">
    {alert}<form method="post" action="/flow/add?key={key}">
    <div class="form-row" style="margin-bottom:12px">
    <div class="field-group"><div class="field-label">Канал</div><select name="channel_id">{ch_opts}</select></div>
    <div class="field-group" style="max-width:100px"><div class="field-label">Шаг №</div>
    <input type="number" name="step" value="0" min="0"/></div>
    <div class="field-group" style="max-width:160px"><div class="field-label">Задержка (мин)</div>
    <input type="number" name="delay_min" value="0" min="0"/></div></div>
    <div class="field-group" style="margin-bottom:12px"><div class="field-label">Текст</div>
    <textarea name="message" placeholder="Привет! Спасибо за подписку 👋" required></textarea></div>
    <button class="btn">Добавить</button></form></div></div>
    <div class="section"><div class="section-head"><h3>📋 Шаги ({len(flows)})</h3></div>
    <table><thead><tr><th>Канал</th><th>Шаг</th><th>Задержка</th><th>Сообщение</th><th></th></tr></thead>
    <tbody>{rows}</tbody></table></div></div>"""
    return HTMLResponse(base(content, "flow", key))

@app.post("/flow/add")
async def flow_add(key: str = "", channel_id: str = Form(...), step: int = Form(0), delay_min: int = Form(0), message: str = Form(...)):
    if key != SECRET: return RedirectResponse(f"/flow?key={key}", 303)
    db.add_flow_step(channel_id, step, delay_min, message)
    return RedirectResponse(f"/flow?key={key}&msg=Шаг+добавлен", 303)

@app.post("/flow/delete")
async def flow_delete(key: str = "", flow_id: int = Form(...)):
    if key != SECRET: return RedirectResponse(f"/flow?key={key}", 303)
    db.delete_flow_step(flow_id)
    return RedirectResponse(f"/flow?key={key}", 303)

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(key: str = "", msg: str = ""):
    r = auth_check(key); 
    if r: return r
    pixel_id   = db.get_setting("pixel_id")
    meta_token = db.get_setting("meta_token")
    land_title = db.get_setting("landing_title", "Наши каналы")
    land_sub   = db.get_setting("landing_subtitle", "Подписывайся и будь в курсе")
    welcome    = db.get_setting("welcome_message", "Привет! Чем могу помочь? 👋")
    bot_info   = await bot.get_me()
    masked     = meta_token[:12] + "..." + meta_token[-6:] if len(meta_token) > 20 else meta_token
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""
    content = f"""<div class="page-wrap"><div class="page-title">⚙️ Настройки</div>
    <div class="page-sub">Пиксель, тексты, параметры</div>{alert}
    <div class="section"><div class="section-head"><h3>📡 Meta Pixel & CAPI</h3></div><div class="section-body">
    <form method="post" action="/settings/pixel?key={key}">
    <div class="grid-2" style="margin-bottom:12px">
    <div class="field-group"><div class="field-label">Pixel ID</div>
    <input type="text" name="pixel_id" value="{pixel_id}"/></div>
    <div class="field-group"><div class="field-label">Access Token (текущий: {masked})</div>
    <input type="text" name="meta_token" placeholder="Оставь пустым — не менять"/></div></div>
    <button class="btn">💾 Сохранить пиксель</button></form></div></div>
    <div class="section"><div class="section-head"><h3>🤖 Бот</h3></div><div class="section-body">
    <form method="post" action="/settings/bot?key={key}">
    <div class="field-group" style="margin-bottom:12px"><div class="field-label">Приветственное сообщение (/start)</div>
    <textarea name="welcome_message">{welcome}</textarea></div>
    <button class="btn">💾 Сохранить</button></form>
    <div style="margin-top:16px;padding:14px;background:#0a0d14;border:1px solid #1e2535;border-radius:8px;font-size:.85rem;color:#94a3b8;line-height:2">
    <b style="color:#fff">Имя:</b> {bot_info.full_name}<br>
    <b style="color:#fff">Username:</b> @{bot_info.username}</div></div></div>
    <div class="section"><div class="section-head"><h3>🌐 Лендинг</h3></div><div class="section-body">
    <form method="post" action="/settings/landing?key={key}">
    <div class="grid-2" style="margin-bottom:12px">
    <div class="field-group"><div class="field-label">Заголовок</div>
    <input type="text" name="landing_title" value="{land_title}"/></div>
    <div class="field-group"><div class="field-label">Подзаголовок</div>
    <input type="text" name="landing_subtitle" value="{land_sub}"/></div></div>
    <button class="btn">💾 Сохранить</button></form></div></div></div>"""
    return HTMLResponse(base(content, "settings", key))

@app.post("/settings/pixel")
async def settings_pixel(key: str = "", pixel_id: str = Form(""), meta_token: str = Form("")):
    if key != SECRET: return RedirectResponse(f"/settings?key={key}", 303)
    if pixel_id.strip():   db.set_setting("pixel_id",   pixel_id.strip())
    if meta_token.strip(): db.set_setting("meta_token", meta_token.strip())
    return RedirectResponse(f"/settings?key={key}&msg=Пиксель+обновлён", 303)

@app.post("/settings/bot")
async def settings_bot(key: str = "", welcome_message: str = Form("")):
    if key != SECRET: return RedirectResponse(f"/settings?key={key}", 303)
    if welcome_message: db.set_setting("welcome_message", welcome_message)
    return RedirectResponse(f"/settings?key={key}&msg=Сохранено", 303)

@app.post("/settings/landing")
async def settings_landing(key: str = "", landing_title: str = Form(""), landing_subtitle: str = Form("")):
    if key != SECRET: return RedirectResponse(f"/settings?key={key}", 303)
    if landing_title:    db.set_setting("landing_title",    landing_title)
    if landing_subtitle: db.set_setting("landing_subtitle", landing_subtitle)
    return RedirectResponse(f"/settings?key={key}&msg=Лендинг+обновлён", 303)

@app.get("/health")
async def health():
    return {"status": "ok", "version": "3.0"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
