import asyncio
import hashlib
import logging
import os
from contextlib import asynccontextmanager
from urllib.parse import urlencode, quote

from fastapi import FastAPI, Request, Form, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

import httpx
import meta_capi
import bot_manager
from database import Database

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

SECRET             = os.getenv("DASHBOARD_PASSWORD", "changeme")
DEFAULT_BOT1_TOKEN = os.getenv("BOT_TOKEN", "")
DEFAULT_BOT2_TOKEN = os.getenv("BOT2_TOKEN", "")
DEFAULT_PIXEL_ID   = os.getenv("PIXEL_ID", "")
DEFAULT_META_TOKEN = os.getenv("META_TOKEN", "")
APP_URL            = os.getenv("APP_URL", "")
WA_URL             = os.getenv("WA_SERVICE_URL", "").rstrip("/")
WA_SECRET          = os.getenv("WA_API_SECRET",  "changeme")
WA_WH_SECRET       = os.getenv("WA_WEBHOOK_SECRET", "changeme")

db = Database()
bot_manager.init(db, meta_capi)

for key, val in [
    ("bot1_token",  DEFAULT_BOT1_TOKEN),
    ("bot2_token",  DEFAULT_BOT2_TOKEN),
    ("pixel_id",    DEFAULT_PIXEL_ID),
    ("meta_token",  DEFAULT_META_TOKEN),
    ("dashboard_password", SECRET),
    ("app_url",     APP_URL),
]:
    if val and not db.get_setting(key):
        db.set_setting(key, val)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot_manager.start_tracker_bot(db.get_setting("bot1_token"))
    await bot_manager.start_staff_bot(db.get_setting("bot2_token"))
    yield
    await bot_manager.stop_tracker_bot()
    await bot_manager.stop_staff_bot()


app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ══════════════════════════════════════════════════════════════════════════════
# AUTH helpers
# ══════════════════════════════════════════════════════════════════════════════

def check_session(request: Request) -> dict | None:
    """Возвращает user dict если сессия валидна, иначе None"""
    token = request.cookies.get("session")
    if not token: return None
    # token = sha256(username+password+secret)
    for u in db.get_users():
        expected = hashlib.sha256(f"{u['username']}{SECRET}".encode()).hexdigest()
        if token == expected:
            return u
    return None


def require_auth(request: Request, role: str = None):
    user = check_session(request)
    if not user:
        return None, RedirectResponse("/login", 303)
    if role and user["role"] != role and user["role"] != "admin":
        return None, HTMLResponse("<h2>Нет доступа</h2>", 403)
    return user, None


# ══════════════════════════════════════════════════════════════════════════════
# CSS
# ══════════════════════════════════════════════════════════════════════════════

CSS = """<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:#0a0d14;color:#e2e8f0;min-height:100vh}
a{color:inherit;text-decoration:none}
.sidebar{position:fixed;top:0;left:0;width:230px;height:100vh;background:#0b0e17;border-right:1px solid #1a2030;display:flex;flex-direction:column;z-index:10;overflow-y:auto}
.logo{padding:20px;font-size:1.1rem;font-weight:800;color:#fff;border-bottom:1px solid #1a2030;letter-spacing:-.01em;display:flex;align-items:center;justify-content:space-between}
.logo span{color:#3b82f6}
.logo-user{font-size:.72rem;color:#475569;font-weight:400}
.nav-section{padding:14px 14px 5px;font-size:.67rem;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:#334155}
.nav-divider{height:1px;background:#1a2030;margin:6px 14px}
.nav-item{display:flex;align-items:center;justify-content:space-between;padding:9px 14px;font-size:.86rem;color:#64748b;border-radius:8px;margin:1px 8px;transition:all .15s;cursor:pointer}
.nav-item:hover{background:#151d2e;color:#e2e8f0}
.nav-item.active{background:#1a2535;color:#fff;font-weight:600}
.nav-item.active.blue{border-left:3px solid #3b82f6;padding-left:11px}
.nav-item.active.orange{border-left:3px solid #f97316;padding-left:11px}
.nav-label{display:flex;align-items:center;gap:9px}
.badge-count{background:#ef4444;color:#fff;border-radius:20px;padding:1px 7px;font-size:.7rem;font-weight:700;min-width:20px;text-align:center}
.sidebar-footer{margin-top:auto;padding:12px;border-top:1px solid #1a2030}
.bot-status{display:flex;align-items:center;gap:8px;padding:7px 10px;background:#0f1420;border-radius:7px;margin-bottom:5px;font-size:.76rem;color:#64748b}
.dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.dot-green{background:#34d399}.dot-red{background:#ef4444}
.main{margin-left:230px}
/* CHAT */
.chat-layout{display:grid;grid-template-columns:300px 1fr;height:100vh}
.conv-list{background:#0b0e17;border-right:1px solid #1a2030;overflow-y:auto;display:flex;flex-direction:column}
.conv-search{padding:12px;border-bottom:1px solid #1a2030}
.conv-search input{width:100%;background:#0a0d14;border:1px solid #1a2030;border-radius:8px;padding:8px 12px;color:#e2e8f0;font-size:.84rem;outline:none}
.conv-item{padding:12px 14px;border-bottom:1px solid #0a0d14;cursor:pointer;transition:background .12s}
.conv-item:hover{background:#111827}
.conv-item.active{background:#1a2030;border-right:2px solid #f97316}
.conv-name{font-weight:600;font-size:.87rem;color:#fff;display:flex;align-items:center;justify-content:space-between;margin-bottom:3px}
.conv-preview{font-size:.77rem;color:#475569;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.conv-time{font-size:.69rem;color:#334155;margin-top:2px}
.unread-num{background:#f97316;color:#fff;border-radius:20px;padding:1px 7px;font-size:.69rem;font-weight:700}
.chat-window{display:flex;flex-direction:column;height:100vh}
.chat-header{padding:14px 18px;border-bottom:1px solid #1a2030;background:#0b0e17;display:flex;align-items:flex-start;justify-content:space-between;flex-shrink:0}
.chat-messages{flex:1;overflow-y:auto;padding:18px;display:flex;flex-direction:column;gap:10px}
.msg{max-width:68%;word-break:break-word}
.msg.visitor{align-self:flex-start}.msg.manager{align-self:flex-end}
.msg-bubble{padding:10px 14px;border-radius:14px;font-size:.87rem;line-height:1.55}
.msg.visitor .msg-bubble{background:#1e2535;color:#e2e8f0;border-bottom-left-radius:4px}
.msg.manager .msg-bubble{background:#ea580c;color:#fff;border-bottom-right-radius:4px}
.msg-time{font-size:.69rem;color:#475569;margin-top:3px}
.msg.visitor .msg-time{text-align:left}.msg.manager .msg-time{text-align:right}
.chat-input{padding:14px 18px;border-top:1px solid #1a2030;background:#0b0e17;flex-shrink:0}
.chat-input-row{display:flex;gap:8px;align-items:flex-end}
.chat-input textarea{flex:1;background:#0a0d14;border:1px solid #1a2030;border-radius:10px;padding:10px 13px;color:#e2e8f0;font-size:.87rem;outline:none;resize:none;max-height:120px;font-family:system-ui}
.chat-input textarea:focus{border-color:#f97316}
.send-btn-orange{background:#ea580c;color:#fff;border:none;border-radius:10px;padding:10px 18px;cursor:pointer;font-size:.87rem;font-weight:600;height:42px;flex-shrink:0}
.send-btn-orange:hover{background:#c2410c}
.no-conv{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:#334155;gap:12px}
/* GENERAL */
.page-wrap{padding:28px;max-width:1100px}
.page-title{font-size:1.3rem;font-weight:700;color:#fff;margin-bottom:3px}
.page-sub{font-size:.82rem;color:#475569;margin-bottom:22px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:11px;margin-bottom:22px}
.card{background:#111827;border:1px solid #1a2030;border-radius:12px;padding:16px}
.card .val{font-size:1.7rem;font-weight:700;color:#60a5fa}
.card .val.orange{color:#fb923c}.card .val.green{color:#34d399}.card .val.red{color:#f87171}
.card .lbl{font-size:.74rem;color:#475569;margin-top:3px}
.section{background:#111827;border:1px solid #1a2030;border-radius:12px;margin-bottom:16px;overflow:hidden}
.section-head{padding:13px 18px;border-bottom:1px solid #1a2030;display:flex;justify-content:space-between;align-items:center}
.section-head h3{font-size:.9rem;font-weight:600;color:#e2e8f0}
.section-body{padding:16px}
table{width:100%;border-collapse:collapse}
th{padding:9px 13px;text-align:left;font-size:.72rem;text-transform:uppercase;color:#475569;letter-spacing:.05em;border-bottom:1px solid #1a2030}
td{padding:10px 13px;font-size:.83rem;border-bottom:1px solid #0f1420}
tr:last-child td{border-bottom:none}
.badge{display:inline-block;padding:2px 9px;border-radius:20px;font-size:.73rem;background:#1e3a5f;color:#60a5fa}
.badge-orange{background:#431407;color:#fb923c}
.badge-green{background:#052e16;color:#34d399}
.badge-red{background:#2d0a0a;color:#f87171}
.badge-gray{background:#1a2030;color:#64748b}
.badge-yellow{background:#422006;color:#fbbf24}
form{display:contents}
.form-row{display:flex;gap:10px;flex-wrap:wrap}
input[type=text],input[type=number],input[type=email],input[type=password],select,textarea{background:#0a0d14;border:1px solid #1a2030;border-radius:8px;padding:9px 13px;color:#e2e8f0;font-size:.85rem;outline:none;width:100%;font-family:system-ui}
input:focus,select:focus,textarea:focus{border-color:#3b82f6}
textarea{resize:vertical;min-height:80px}
.btn{display:inline-block;background:#3b82f6;color:#fff;border:none;border-radius:8px;padding:9px 18px;cursor:pointer;font-size:.85rem;font-weight:600;white-space:nowrap}
.btn:hover{background:#2563eb}
.btn-orange{background:#ea580c;color:#fff;border:none;border-radius:8px;padding:9px 18px;cursor:pointer;font-size:.85rem;font-weight:600}
.btn-orange:hover{background:#c2410c}
.btn-red{background:#dc2626;color:#fff;border:none;border-radius:8px;padding:9px 18px;cursor:pointer;font-size:.85rem;font-weight:600}
.btn-red:hover{background:#b91c1c}
.btn-gray{background:#1e2535;color:#94a3b8;border:none;border-radius:8px;padding:9px 18px;cursor:pointer;font-size:.85rem;font-weight:600}
.btn-gray:hover{background:#2d3748;color:#fff}
.btn-green{background:#059669;color:#fff;border:none;border-radius:8px;padding:9px 18px;cursor:pointer;font-size:.85rem;font-weight:600}
.btn-green:hover{background:#047857}
.btn-sm{padding:5px 11px;font-size:.77rem;border-radius:6px}
.link-box{background:#0a0d14;border:1px solid #1a2030;border-radius:6px;padding:8px 12px;font-family:monospace;font-size:.77rem;word-break:break-all;color:#a5f3fc}
.alert-green{background:#052e16;border:1px solid #166534;border-radius:8px;padding:11px 15px;color:#86efac;margin-bottom:14px;font-size:.85rem}
.alert-red{background:#2d0a0a;border:1px solid #7f1d1d;border-radius:8px;padding:11px 15px;color:#fca5a5;margin-bottom:14px;font-size:.85rem}
.empty{text-align:center;padding:28px;color:#334155;font-size:.85rem}
.tag{display:inline-block;background:#1a2030;border-radius:4px;padding:2px 7px;font-size:.72rem;color:#64748b;font-family:monospace}
.del-btn{background:none;border:none;cursor:pointer;color:#ef4444;font-size:.83rem;padding:4px 8px;border-radius:4px}
.del-btn:hover{background:#2d0a0a}
.field-group{display:flex;flex-direction:column;gap:5px;flex:1}
.field-label{font-size:.74rem;color:#475569;font-weight:600;text-transform:uppercase;letter-spacing:.04em}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:13px}
.grid-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:13px}
.avatar{width:36px;height:36px;border-radius:50%;background:#431407;display:flex;align-items:center;justify-content:center;font-size:.9rem;flex-shrink:0;font-weight:700;color:#fb923c}
/* FUNNEL */
.funnel{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:22px}
.funnel-step{background:#111827;border:1px solid #1a2030;border-radius:10px;padding:14px;text-align:center}
.funnel-step .fn{font-size:1.5rem;font-weight:700;margin-bottom:4px}
.funnel-step .fl{font-size:.74rem;color:#475569}
/* UTM BADGE */
.utm-row{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px}
.utm-tag{background:#0f2040;border:1px solid #1e3a5f;border-radius:4px;padding:2px 8px;font-size:.72rem;color:#7dd3fc;font-family:monospace}
/* CHART */
.chart-wrap{height:160px;display:flex;align-items:flex-end;gap:3px;padding:8px 0}
.chart-bar-wrap{display:flex;flex-direction:column;align-items:center;flex:1;height:100%}
.chart-bar{width:100%;border-radius:4px 4px 0 0;min-height:2px;transition:height .3s}
.chart-bar.blue{background:linear-gradient(180deg,#6366f1,#4f46e5)}
.chart-bar.orange{background:linear-gradient(180deg,#f97316,#ea580c)}
.chart-bar.green{background:linear-gradient(180deg,#34d399,#10b981)}
.chart-label{font-size:.58rem;color:var(--text3);margin-top:3px;transform:rotate(-45deg);transform-origin:top right;white-space:nowrap}
/* ── TOAST ────────────────────────────────────────────────────────────────── */
#toast-container{position:fixed;top:18px;right:18px;z-index:9999;display:flex;flex-direction:column;gap:8px;pointer-events:none}
.toast{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:12px 16px;box-shadow:0 8px 32px rgba(0,0,0,.5);max-width:300px;pointer-events:auto;animation:toastIn .25s ease;cursor:pointer}
.toast.tg-toast{border-left:3px solid #38bdf8}
.toast.wa-toast{border-left:3px solid #25d366}
.toast-title{font-size:.81rem;font-weight:700;color:var(--text);margin-bottom:2px}
.toast-body{font-size:.75rem;color:var(--text2)}
@keyframes toastIn{from{opacity:0;transform:translateX(20px)}to{opacity:1;transform:none}}
</style>"""


def nav_html(active: str, request: Request) -> str:
    user = check_session(request)
    stats = db.get_stats()
    unread     = stats.get("unread", 0)
    wa_unread  = stats.get("wa_unread", 0)
    b1 = bot_manager.get_tracker_bot()
    b2 = bot_manager.get_staff_bot()
    b1_name = db.get_setting("bot1_name", "Бот трекер")
    b2_name = db.get_setting("bot2_name", "Бот сотрудники")
    wa_status  = db.get_setting("wa_status", "disconnected")
    role = user["role"] if user else "manager"

    def item(icon, label, page, section_color="blue", badge_count=0, url=None):
        href = url or f"/{page}"
        act  = page == active or (url and url.strip("/") == active)
        cls  = f"nav-item active {section_color}" if act else "nav-item"
        bdg  = f'<span class="badge-count">{badge_count}</span>' if badge_count > 0 else ""
        return f'<a href="{href}"><div class="{cls}"><span class="nav-label">{icon} {label}</span>{bdg}</div></a>'

    admin_section = ""
    if role == "admin":
        admin_section = f"""
        <div class="nav-divider"></div>
        {item("🔐", "Пользователи", "users", "blue")}
        {item("⚙️", "Настройки", "settings", "blue")}"""

    wa_dot = "dot-green" if wa_status == "ready" else ("dot-yellow" if wa_status == "qr" else "dot-red")

    return f"""
    <div class="sidebar" id="sidebar">
      <div class="logo">
        <div>
          <div class="logo-brand">📡 TGTracker</div>
          <div class="logo-user">{user['username'] if user else ''}</div>
        </div>
        <div class="logo-right">
          <div class="theme-toggle" onclick="toggleTheme()" title="Сменить тему" id="theme-btn">🌙</div>
        </div>
      </div>
      {item("📊", "Обзор", "overview", "blue")}
      <div class="nav-divider"></div>
      <div class="nav-section">👥 Клиенты</div>
      {item("📡", "Каналы", "channels", "blue")}
      {item("🔗", "Кампании", "campaigns", "blue")}
      {item("🎨", "Шаблоны", "landings", "blue")}
      {item("📈", "Статистика", "analytics_clients", "blue", url="/analytics/clients")}
      <div class="nav-divider"></div>
      <div class="nav-section">👔 Сотрудники</div>
      {item("💬", "TG Чаты", "chat", "orange", badge_count=unread)}
      {item("💚", "WA Чаты", "wa_chat", "orange", badge_count=wa_unread, url="/wa/chat")}
      {item("🗂", "База", "staff", "orange")}
      {item("🌐", "Лендинги HR", "landings_staff", "orange")}
      {item("📊", "Статистика", "analytics_staff", "orange", url="/analytics/staff")}
      {admin_section}
      <div class="sidebar-footer">
        <div class="bot-status"><div class="dot {'dot-green' if b1 else 'dot-red'}"></div><span>{b1_name}</span></div>
        <div class="bot-status"><div class="dot {'dot-green' if b2 else 'dot-red'}"></div><span>{b2_name}</span></div>
        <div class="bot-status"><div class="dot {wa_dot}"></div><span>WhatsApp {'✓' if wa_status == 'ready' else ('QR...' if wa_status == 'qr' else '✗')}</span></div>
        <a href="/logout"><div style="padding:7px 9px;font-size:.74rem;color:var(--text3);cursor:pointer">⬅ Выйти</div></a>
      </div>
    </div>
    <div id="toast-container"></div>
    <script>
    // Theme
    (function(){{
      const t = localStorage.getItem('theme') || 'dark';
      if(t === 'light') document.body.classList.add('light');
      const btn = document.getElementById('theme-btn');
      if(btn) btn.textContent = t === 'light' ? '🌙' : '☀️';
    }})();
    function toggleTheme(){{
      const isLight = document.body.classList.toggle('light');
      localStorage.setItem('theme', isLight ? 'light' : 'dark');
      const btn = document.getElementById('theme-btn');
      if(btn) btn.textContent = isLight ? '🌙' : '☀️';
    }}
    // Toast notifications
    let audioCtx = null;
    function playPing(){{
      try{{
        if(!audioCtx) audioCtx = new (window.AudioContext||window.webkitAudioContext)();
        const o = audioCtx.createOscillator();
        const g = audioCtx.createGain();
        o.connect(g); g.connect(audioCtx.destination);
        o.frequency.setValueAtTime(880, audioCtx.currentTime);
        o.frequency.setValueAtTime(1100, audioCtx.currentTime + 0.1);
        g.gain.setValueAtTime(0.3, audioCtx.currentTime);
        g.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.4);
        o.start(); o.stop(audioCtx.currentTime + 0.4);
      }}catch(e){{}}
    }}
    function showToast(title, body, type, url){{
      const c = document.getElementById('toast-container');
      const d = document.createElement('div');
      d.className = 'toast ' + (type || '');
      d.innerHTML = '<div class="toast-title">' + title + '</div><div class="toast-body">' + body + '</div>';
      if(url) d.onclick = () => location.href = url;
      c.appendChild(d);
      playPing();
      setTimeout(() => {{ d.style.animation = 'toastIn .25s ease reverse'; setTimeout(() => d.remove(), 250); }}, 5000);
    }}
    // Global unread polling (all pages)
    let _lastTgUnread = {unread}, _lastWaUnread = {wa_unread};
    async function pollUnread(){{
      try{{
        const r = await fetch('/api/stats');
        const d = await r.json();
        // Update badges in nav
        const tgBadge = document.querySelector('a[href="/chat"] .badge-count');
        const waBadge = document.querySelector('a[href="/wa/chat"] .badge-count');
        if(tgBadge) tgBadge.textContent = d.unread || '';
        if(waBadge) waBadge.textContent = d.wa_unread || '';
        // Toasts on new messages
        if(d.unread > _lastTgUnread) showToast('💬 TG — новое сообщение', 'Перейти в TG чаты', 'tg-toast', '/chat');
        if(d.wa_unread > _lastWaUnread) showToast('💚 WA — новое сообщение', 'Перейти в WA чаты', 'wa-toast', '/wa/chat');
        _lastTgUnread = d.unread; _lastWaUnread = d.wa_unread;
      }}catch(e){{}}
    }}
    setInterval(pollUnread, 5000);
    </script>"""


def base(content: str, active: str, request: Request) -> str:
    return f'<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>TGTracker</title><link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">{CSS}</head><body>{nav_html(active, request)}<div class="main">{content}</div></body></html>'


STAFF_STATUSES = {
    "new":         ("🆕", "Новый",          "badge-gray"),
    "review":      ("👀", "На рассмотрении", "badge-yellow"),
    "interview":   ("🎙", "Интервью",        "badge"),
    "hired":       ("✅", "Принят",          "badge-green"),
    "rejected":    ("❌", "Отказ",           "badge-red"),
}


# ══════════════════════════════════════════════════════════════════════════════
# AUTH PAGES
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/login", response_class=HTMLResponse)
async def login_page(error: str = ""):
    alert = f'<div class="alert-red">{error}</div>' if error else ""
    return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Вход</title>{CSS}</head>
    <body><div style="max-width:360px;margin:100px auto;padding:0 16px">
    <div style="font-size:1.4rem;font-weight:800;color:#fff;margin-bottom:6px">📡 TG<span style="color:#3b82f6">Tracker</span></div>
    <div style="color:#475569;font-size:.85rem;margin-bottom:24px">Войдите чтобы продолжить</div>
    {alert}
    <div class="section"><div class="section-body">
    <form method="post" action="/login" style="display:flex;flex-direction:column;gap:12px">
      <div class="field-group"><div class="field-label">Логин</div><input type="text" name="username" autofocus/></div>
      <div class="field-group"><div class="field-label">Пароль</div><input type="password" name="password"/></div>
      <button class="btn" style="width:100%">Войти</button>
    </form>
    </div></div></div></body></html>""")


@app.post("/login")
async def login_submit(username: str = Form(...), password: str = Form(...)):
    user = db.verify_user(username, password)
    if not user:
        return RedirectResponse("/login?error=Неверный+логин+или+пароль", 303)
    token = hashlib.sha256(f"{user['username']}{SECRET}".encode()).hexdigest()
    resp = RedirectResponse("/overview", 303)
    resp.set_cookie("session", token, max_age=86400*30, httponly=True)
    return resp


@app.get("/logout")
async def logout():
    resp = RedirectResponse("/login", 303)
    resp.delete_cookie("session")
    return resp


# ══════════════════════════════════════════════════════════════════════════════
# /go — UTM REDIRECT
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/go")
async def go_redirect(
    request: Request,
    to: str = "",
    fbclid: str = None,
    fbp: str = None,
    utm_source: str = None,
    utm_medium: str = None,
    utm_campaign: str = None,
    utm_content: str = None,
    utm_term: str = None,
):
    """
    Страница редиректа с трекингом.
    Использование: /go?to=https://t.me/+xxx&utm_source=fb&utm_campaign=march&fbclid=xxx
    ⚡ fbp берётся из cookie _fbp (устанавливается Meta Pixel на лендинге)
    ⚡ fbc = fb.1.{timestamp}.{fbclid} — для matching в Ads Manager
    """
    if not to:
        return HTMLResponse("<h2>Ссылка не указана</h2>", 400)

    # fbp из cookie — именно там он правильный (Meta Pixel ставит его сам)
    cookie_fbp = request.cookies.get("_fbp") or fbp

    # Сохраняем клик со ВСЕМИ данными для FB CAPI
    click_id = db.save_click(
        fbclid    = fbclid,
        fbp       = cookie_fbp,
        utm_source   = utm_source,
        utm_medium   = utm_medium,
        utm_campaign = utm_campaign,
        utm_content  = utm_content,
        utm_term     = utm_term,
        referrer  = request.headers.get("referer"),
        target_type  = "channel",
        target_id    = to,
        user_agent   = request.headers.get("user-agent", "")[:255],
        ip_address   = request.client.host if request.client else None,
    )
    log.info(f"[/go] click_id={click_id} fbclid={'✓' if fbclid else '—'} fbp={'✓' if cookie_fbp else '—'} utm={utm_campaign} → {to[:60]}")

    # Добавляем ref_ параметр в Telegram ссылку для связи с ботом
    destination = to
    if "t.me" in to:
        sep = "&" if "?" in to else "?"
        destination = f"{to}{sep}start=ref_{click_id}"

    # Промежуточная страница — здесь fbp ТОЧНО уже есть в cookie (с лендинга)
    return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <meta http-equiv="refresh" content="0;url={destination}">
    <script>
      // Убеждаемся что fbp есть — нужен для FB CAPI Subscribe
      if (!document.cookie.includes('_fbp')) {{
        var fbp = 'fb.1.' + Date.now() + '.' + Math.random().toString(36).substr(2,9);
        document.cookie = '_fbp=' + fbp + ';max-age=7776000;path=/;SameSite=Lax';
      }}
      setTimeout(function(){{ window.location.href = '{destination}'; }}, 80);
    </script>
    </head><body style="background:#060a0f;color:#e8f0f8;display:flex;align-items:center;justify-content:center;min-height:100vh;font-family:system-ui">
    <div style="text-align:center"><div style="font-size:2rem;margin-bottom:12px">📡</div>
    <div>Перенаправляем...</div></div></body></html>""")


# ══════════════════════════════════════════════════════════════════════════════
# OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
@app.get("/overview", response_class=HTMLResponse)
async def overview(request: Request):
    user, err = require_auth(request)
    if err: return err
    s = db.get_stats()
    joins = db.get_recent_joins(20)
    funnel = db.get_staff_funnel()
    pixel = db.get_setting("pixel_id", "—")

    rows = "".join(f"""<tr>
        <td>{j['joined_at'][:16].replace('T',' ')}</td>
        <td><span class="tag">{j.get('channel_name') or j.get('channel_id','—')}</span></td>
        <td><span class="badge">{j['campaign_name']}</span></td>
        <td>{'<span class="badge-green">✓</span>' if j.get('click_id') else '—'}</td>
    </tr>""" for j in joins) or '<tr><td colspan="4"><div class="empty">Пока нет</div></td></tr>'

    fn_steps = [
        ("new", "🆕 Новых"),
        ("review", "👀 Смотрим"),
        ("interview", "🎙 Интервью"),
        ("hired", "✅ Принят"),
        ("rejected", "❌ Отказ"),
    ]
    funnel_html = "".join(f"""<div class="funnel-step">
        <div class="fn" style="color:{'#34d399' if s=='hired' else '#f87171' if s=='rejected' else '#60a5fa'}">{funnel.get(s,0)}</div>
        <div class="fl">{l}</div></div>""" for s, l in fn_steps)

    content = f"""<div class="page-wrap">
    <div class="page-title">📊 Обзор</div>
    <div class="page-sub">Общая статистика системы</div>

    <div style="font-size:.76rem;font-weight:700;color:#3b82f6;text-transform:uppercase;letter-spacing:.08em;margin-bottom:10px">👥 Клиенты</div>
    <div class="cards" style="margin-bottom:18px">
      <div class="card"><div class="val">{s['total']}</div><div class="lbl">Подписчиков</div></div>
      <div class="card"><div class="val">{s['from_ads']}</div><div class="lbl">Из рекламы</div></div>
      <div class="card"><div class="val">{s['organic']}</div><div class="lbl">Органика</div></div>
      <div class="card"><div class="val">{s['clicks']}</div><div class="lbl">Кликов (/go)</div></div>
    </div>

    <div style="font-size:.76rem;font-weight:700;color:#f97316;text-transform:uppercase;letter-spacing:.08em;margin-bottom:10px">👔 Сотрудники — Воронка</div>
    <div class="funnel">{funnel_html}</div>
    <div class="cards" style="margin-bottom:18px">
      <div class="card"><div class="val orange">{s['conversations']}</div><div class="lbl">Диалогов</div></div>
      <div class="card"><div class="val orange" style="color:#ef4444">{s['unread']}</div><div class="lbl">Непрочитанных</div></div>
      <div class="card"><div class="val orange">{s['staff']}</div><div class="lbl">Сотрудников</div></div>
    </div>

    <div class="section">
      <div class="section-head"><h3>🕐 Последние подписки</h3><span class="tag">Pixel: {pixel}</span></div>
      <table><thead><tr><th>Время</th><th>Канал</th><th>Кампания</th><th>UTM</th></tr></thead>
      <tbody>{rows}</tbody></table>
    </div></div>"""
    return HTMLResponse(base(content, "overview", request))


# ══════════════════════════════════════════════════════════════════════════════
# ANALYTICS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/analytics/clients", response_class=HTMLResponse)
async def analytics_clients(request: Request,
    date_from: str = "", date_to: str = "", period: str = "30"):
    user, err = require_auth(request)
    if err: return err

    days = int(period) if period.isdigit() else 30
    df   = date_from or None
    dt   = date_to   or None

    joins_day   = db.get_joins_by_day(days=days, date_from=df, date_to=dt)
    clicks_day  = db.get_clicks_by_day(days=days, date_from=df, date_to=dt)
    summary     = db.get_joins_summary(days=days, date_from=df, date_to=dt)
    cl_summary  = db.get_clicks_summary(days=days, date_from=df, date_to=dt)
    by_channel  = db.get_joins_by_channel(days=days, date_from=df, date_to=dt)
    by_campaign = db.get_joins_by_campaign(days=days, date_from=df, date_to=dt)
    utm_src     = db.get_utm_sources(days=days, date_from=df, date_to=dt)
    recent      = db.get_recent_joins_detailed(50, days=days, date_from=df, date_to=dt)

    # Конверсия клики → подписки
    cr = round(summary["total"] / cl_summary["total"] * 100, 1) if cl_summary["total"] else 0

    def sparkline(data, key, color="#60a5fa"):
        if not data: return '<div style="color:var(--text3);font-size:.8rem">Нет данных</div>'
        mx = max((d[key] for d in data), default=1) or 1
        bars = ""
        for d in data:
            h = max(3, int(d[key] / mx * 80))
            tip = f"{d.get('day','')}: {d[key]}"
            bars += f'<div style="display:flex;flex-direction:column;align-items:center;gap:2px;flex:1;min-width:0">' \
                    f'<div title="{tip}" style="width:100%;background:{color};border-radius:3px 3px 0 0;height:{h}px;min-height:3px;cursor:default"></div>' \
                    f'<div style="font-size:.55rem;color:var(--text3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:28px">{str(d.get("day",""))[-5:]}</div></div>'
        return f'<div style="display:flex;align-items:flex-end;gap:2px;height:100px;padding:10px 0 0">{bars}</div>'

    def kpi(val, label, sub="", color="var(--accent)"):
        return f'''<div class="kpi-card">
            <div class="kpi-val" style="color:{color}">{val}</div>
            <div class="kpi-label">{label}</div>
            {"<div class='kpi-sub'>"+sub+"</div>" if sub else ""}
        </div>'''

    # Таблица каналов
    ch_rows = ""
    for c in by_channel:
        pct = round(c["joins"] / summary["total"] * 100) if summary["total"] else 0
        ch_rows += f"""<tr>
            <td style="font-weight:600">{c['channel_name']}</td>
            <td><div style="display:flex;align-items:center;gap:8px">
                <div style="flex:1;background:var(--bg3);border-radius:4px;height:6px">
                    <div style="width:{pct}%;background:var(--accent);border-radius:4px;height:6px"></div>
                </div>
                <span style="font-weight:700;color:var(--accent);min-width:28px">{c['joins']}</span>
            </div></td>
            <td style="color:#f97316">{c['from_ads']}</td>
            <td style="color:var(--text3);font-size:.8rem">{c['last_join'][:10] if c.get('last_join') else '—'}</td>
        </tr>"""
    ch_rows = ch_rows or '<tr><td colspan="4"><div class="empty">Нет данных</div></td></tr>'

    # Таблица кампаний
    camp_rows = ""
    for c in by_campaign:
        camp_rows += f"""<tr>
            <td><span class="badge">{c['campaign_name']}</span></td>
            <td style="font-weight:700;color:var(--accent)">{c['joins']}</td>
            <td style="color:var(--text3)">{c['tracked']}</td>
            <td style="color:var(--text3);font-size:.8rem">{c['first_join'][:10] if c.get('first_join') else '—'}</td>
            <td style="color:var(--text3);font-size:.8rem">{c['last_join'][:10] if c.get('last_join') else '—'}</td>
        </tr>"""
    camp_rows = camp_rows or '<tr><td colspan="5"><div class="empty">Нет данных</div></td></tr>'

    # UTM источники
    utm_rows = ""
    for u in utm_src:
        utm_rows += f"""<tr>
            <td><span class="badge-gray">{u['source']}</span></td>
            <td style="color:var(--text3)">{u['medium']}</td>
            <td style="font-weight:600">{u['clicks']}</td>
        </tr>"""
    utm_rows = utm_rows or '<tr><td colspan="3"><div class="empty">Нет данных</div></td></tr>'

    # Последние подписки
    recent_rows = ""
    for j in recent[:30]:
        src_icon = "📘" if j.get("utm_source") in ("facebook","fb") else ("🔗" if j.get("utm_source") else "🌿")
        recent_rows += f"""<tr>
            <td style="color:var(--text3);font-size:.78rem">{str(j['joined_at'])[:16].replace('T',' ')}</td>
            <td style="font-weight:600">{j.get('channel_name','—')}</td>
            <td><span class="badge" style="font-size:.7rem">{j['campaign_name']}</span></td>
            <td title="{j.get('utm_source','') or ''}">{src_icon} {j.get('utm_source') or 'organic'}</td>
            <td>{"✅" if j.get('fbclid') else "—"}</td>
        </tr>"""
    recent_rows = recent_rows or '<tr><td colspan="5"><div class="empty">Нет подписок за период</div></td></tr>'

    # Dual chart data (joins + clicks по дням)
    chart_html = _dual_sparkline(joins_day, clicks_day)

    sel_period = lambda v,l: f'<option value="{v}" {"selected" if period==v else ""}>{l}</option>'
    content = f"""<div class="page-wrap">
    <div class="page-title">📈 Статистика Клиентов</div>
    <div class="page-sub">Подписки, клики, кампании, конверсия</div>

    <form method="get" action="/analytics/clients" style="display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap;margin-bottom:24px">
      <div class="field-group" style="max-width:150px">
        <div class="field-label">Период</div>
        <select name="period" onchange="this.form.submit()">
          {sel_period("7","7 дней")}
          {sel_period("14","14 дней")}
          {sel_period("30","30 дней")}
          {sel_period("60","60 дней")}
          {sel_period("90","90 дней")}
        </select>
      </div>
      <div class="field-group"><div class="field-label">С даты</div>
        <input type="date" name="date_from" value="{date_from}"/></div>
      <div class="field-group"><div class="field-label">По дату</div>
        <input type="date" name="date_to" value="{date_to}"/></div>
      <div style="display:flex;align-items:flex-end;gap:6px">
        <button class="btn">Применить</button>
        <a href="/analytics/clients" class="btn-gray">Сбросить</a>
      </div>
    </form>

    <div class="kpi-grid">
      {kpi(summary['total'], 'Подписок всего', f"{summary['from_ads']} из рекламы / {summary['organic']} organic")}
      {kpi(cl_summary['total'], 'Кликов на /go', f"{cl_summary['from_fb']} из Facebook")}
      {kpi(f"{cr}%", 'Конверсия', 'клики → подписки', "#34d399" if cr>10 else "#f97316")}
      {kpi(cl_summary['has_fbp'], 'С fbp cookie', 'для FB CAPI matching')}
      {kpi(summary['channels_active'], 'Активных каналов', '')}
      {kpi(summary['campaigns_active'], 'Кампаний', '')}
    </div>

    <div class="section">
      <div class="section-head"><h3>📊 Подписки и клики по дням</h3></div>
      <div class="section-body">{chart_html}</div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
      <div class="section">
        <div class="section-head"><h3>📡 По каналам</h3></div>
        <table><thead><tr><th>Канал</th><th>Подписок</th><th>Реклама</th><th>Последняя</th></tr></thead>
        <tbody>{ch_rows}</tbody></table>
      </div>
      <div class="section">
        <div class="section-head"><h3>🔗 Источники трафика</h3></div>
        <table><thead><tr><th>Источник</th><th>Medium</th><th>Кликов</th></tr></thead>
        <tbody>{utm_rows}</tbody></table>
      </div>
    </div>

    <div class="section">
      <div class="section-head"><h3>🎯 По кампаниям</h3></div>
      <table><thead><tr><th>Кампания</th><th>Подписок</th><th>Трекинг</th><th>Первая</th><th>Последняя</th></tr></thead>
      <tbody>{camp_rows}</tbody></table>
    </div>

    <div class="section">
      <div class="section-head"><h3>⏱ Последние подписки</h3></div>
      <table><thead><tr><th>Время</th><th>Канал</th><th>Кампания</th><th>Источник</th><th>fbclid</th></tr></thead>
      <tbody>{recent_rows}</tbody></table>
    </div>
    </div>"""
    return HTMLResponse(base(content + _analytics_css(), "analytics_clients", request))


@app.get("/analytics/staff", response_class=HTMLResponse)
async def analytics_staff(request: Request,
    date_from: str = "", date_to: str = "", period: str = "30"):
    user, err = require_auth(request)
    if err: return err

    days = int(period) if period.isdigit() else 30
    df   = date_from or None
    dt   = date_to   or None

    summary    = db.get_staff_summary(days=days, date_from=df, date_to=dt)
    by_day     = db.get_staff_by_day(days=days, date_from=df, date_to=dt)
    msg_day    = db.get_messages_by_day(days=days, date_from=df, date_to=dt)
    wa_day     = db.get_wa_messages_by_day(days=days, date_from=df, date_to=dt)
    msg_sum    = db.get_messages_summary(days=days, date_from=df, date_to=dt)
    funnel     = db.get_staff_funnel(date_from=df, date_to=dt)
    resp_stats = db.get_staff_response_stats(days=days, date_from=df, date_to=dt)

    def kpi(val, label, sub="", color="var(--accent)"):
        return f'''<div class="kpi-card">
            <div class="kpi-val" style="color:{color}">{val}</div>
            <div class="kpi-label">{label}</div>
            {"<div class='kpi-sub'>"+sub+"</div>" if sub else ""}
        </div>'''

    def sparkline(data, key, color="#f97316"):
        if not data: return '<div style="color:var(--text3);font-size:.8rem">Нет данных</div>'
        mx = max((d[key] for d in data), default=1) or 1
        bars = ""
        for d in data:
            h = max(3, int(d[key] / mx * 80))
            bars += f'<div style="display:flex;flex-direction:column;align-items:center;gap:2px;flex:1;min-width:0">' \
                    f'<div title="{d.get("day","")}: {d[key]}" style="width:100%;background:{color};border-radius:3px 3px 0 0;height:{h}px;min-height:3px;cursor:default"></div>' \
                    f'<div style="font-size:.55rem;color:var(--text3);white-space:nowrap;overflow:hidden;max-width:28px">{str(d.get("day",""))[-5:]}</div></div>'
        return f'<div style="display:flex;align-items:flex-end;gap:2px;height:100px;padding:10px 0 0">{bars}</div>'

    # Воронка
    fn_total  = summary["total"] or 1
    fn_steps  = [
        ("s_new",       "🆕 Новые",     "#60a5fa"),
        ("s_review",    "👀 Смотрим",   "#a78bfa"),
        ("s_interview", "🎙 Интервью",  "#f59e0b"),
        ("s_hired",     "✅ Принят",    "#34d399"),
        ("s_rejected",  "❌ Отказ",     "#f87171"),
    ]
    funnel_html = ""
    for key, label, color in fn_steps:
        val = summary.get(key, 0)
        pct = round(val / fn_total * 100)
        funnel_html += f"""<div class="funnel-item">
            <div style="display:flex;justify-content:space-between;margin-bottom:4px">
                <span style="font-size:.85rem;font-weight:600">{label}</span>
                <span style="font-weight:700;color:{color}">{val} <span style="color:var(--text3);font-size:.75rem">({pct}%)</span></span>
            </div>
            <div style="background:var(--bg3);border-radius:6px;height:8px">
                <div style="width:{pct}%;background:{color};border-radius:6px;height:8px;transition:width .3s"></div>
            </div>
        </div>"""

    # Конверсия найм
    conv_hire = funnel.get("conversion_hired", 0)

    # Таблица активности сотрудников
    staff_rows = ""
    status_colors = {"new":"var(--accent)","review":"#a78bfa","interview":"#f59e0b","hired":"#34d399","rejected":"#f87171"}
    for s in resp_stats:
        sc = status_colors.get(s.get("status","new"), "var(--text3)")
        last_msg = str(s.get("last_message_at",""))[:16].replace("T"," ") if s.get("last_message_at") else "—"
        staff_rows += f"""<tr>
            <td style="font-weight:600">{s.get('name') or '—'}</td>
            <td><span style="color:{sc};font-weight:600;font-size:.8rem">{s.get('status','—')}</span></td>
            <td style="color:var(--accent);font-weight:700">{s['msg_count']}</td>
            <td style="color:var(--text3);font-size:.78rem">{last_msg}</td>
            <td style="color:var(--text3);font-size:.78rem">{str(s.get('created_at',''))[:10]}</td>
        </tr>"""
    staff_rows = staff_rows or '<tr><td colspan="5"><div class="empty">Нет данных</div></td></tr>'

    sel_period = lambda v,l: f'<option value="{v}" {"selected" if period==v else ""}>{l}</option>'
    content = f"""<div class="page-wrap">
    <div class="page-title">📊 Статистика Сотрудников</div>
    <div class="page-sub">Лиды, воронка найма, активность переписки</div>

    <form method="get" action="/analytics/staff" style="display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap;margin-bottom:24px">
      <div class="field-group" style="max-width:150px">
        <div class="field-label">Период</div>
        <select name="period" onchange="this.form.submit()">
          {sel_period("7","7 дней")}
          {sel_period("14","14 дней")}
          {sel_period("30","30 дней")}
          {sel_period("60","60 дней")}
          {sel_period("90","90 дней")}
        </select>
      </div>
      <div class="field-group"><div class="field-label">С даты</div>
        <input type="date" name="date_from" value="{date_from}"/></div>
      <div class="field-group"><div class="field-label">По дату</div>
        <input type="date" name="date_to" value="{date_to}"/></div>
      <div style="display:flex;align-items:flex-end;gap:6px">
        <button class="btn">Применить</button>
        <a href="/analytics/staff" class="btn-gray">Сбросить</a>
      </div>
    </form>

    <div class="kpi-grid">
      {kpi(summary['total'], 'Новых лидов', f"за период")}
      {kpi(summary['s_hired'], 'Принято', f'{conv_hire}% конверсия', '#34d399')}
      {kpi(summary['s_interview'], 'На интервью', '', '#f59e0b')}
      {kpi(summary['s_rejected'], 'Отказов', '', '#f87171')}
      {kpi(msg_sum['total'], 'Сообщений TG', f"{msg_sum['incoming']} вх / {msg_sum['outgoing']} исх")}
      {kpi(msg_sum['active_convos'], 'Активных чатов', '')}
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
      <div class="section">
        <div class="section-head"><h3>📈 Новые лиды по дням</h3></div>
        <div class="section-body">{sparkline(by_day, 'cnt', '#f97316')}</div>
      </div>
      <div class="section">
        <div class="section-head"><h3>💬 Сообщения TG по дням</h3></div>
        <div class="section-body">{sparkline(msg_day, 'total', '#60a5fa')}</div>
      </div>
    </div>

    <div class="section">
      <div class="section-head"><h3>🎯 Воронка найма</h3></div>
      <div class="section-body"><div style="display:flex;flex-direction:column;gap:12px;max-width:500px">{funnel_html}</div></div>
    </div>

    <div class="section">
      <div class="section-head"><h3>👥 Активность по сотрудникам</h3></div>
      <table><thead><tr><th>Имя</th><th>Статус</th><th>Сообщений</th><th>Последнее сообщение</th><th>Добавлен</th></tr></thead>
      <tbody>{staff_rows}</tbody></table>
    </div>
    </div>"""
    return HTMLResponse(base(content + _analytics_css(), "analytics_staff", request))


def _dual_sparkline(joins_day, clicks_day):
    """График подписок + кликов на одной шкале"""
    if not joins_day and not clicks_day:
        return '<div class="empty">Нет данных за период</div>'
    # Объединяем дни
    days_set = sorted(set(
        [d["day"] for d in joins_day] + [d["day"] for d in clicks_day]
    ))
    j_map = {d["day"]: d["cnt"] for d in joins_day}
    c_map = {d["day"]: d["clicks"] for d in clicks_day}
    mx = max([j_map.get(d,0) for d in days_set] + [c_map.get(d,0) for d in days_set] + [1])
    bars = ""
    for day in days_set[-40:]:
        jh = max(2, int(j_map.get(day,0) / mx * 90))
        ch = max(2, int(c_map.get(day,0) / mx * 90))
        label = str(day)[-5:]
        bars += f'''<div style="display:flex;flex-direction:column;align-items:center;gap:1px;flex:1;min-width:0">
            <div style="width:100%;display:flex;align-items:flex-end;gap:1px;height:92px">
                <div title="{day} подписок: {j_map.get(day,0)}" style="flex:1;background:#60a5fa;border-radius:2px 2px 0 0;height:{jh}px"></div>
                <div title="{day} кликов: {c_map.get(day,0)}" style="flex:1;background:rgba(249,115,22,.5);border-radius:2px 2px 0 0;height:{ch}px"></div>
            </div>
            <div style="font-size:.52rem;color:var(--text3);max-width:28px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{label}</div>
        </div>'''
    legend = '''<div style="display:flex;gap:16px;margin-top:10px;font-size:.78rem;color:var(--text3)">
        <span><span style="display:inline-block;width:10px;height:10px;background:#60a5fa;border-radius:2px;margin-right:4px"></span>Подписки</span>
        <span><span style="display:inline-block;width:10px;height:10px;background:rgba(249,115,22,.5);border-radius:2px;margin-right:4px"></span>Клики</span>
    </div>'''
    return f'<div style="display:flex;align-items:flex-end;gap:2px;height:110px">{bars}</div>{legend}'


def _analytics_css():
    return """<style>
    .kpi-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;margin-bottom:24px}
    .kpi-card{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:16px;text-align:center}
    .kpi-val{font-size:1.8rem;font-weight:800;line-height:1.1;margin-bottom:4px}
    .kpi-label{font-size:.78rem;font-weight:600;color:var(--text3);text-transform:uppercase;letter-spacing:.04em}
    .kpi-sub{font-size:.72rem;color:var(--text3);margin-top:4px}
    .funnel-item{margin-bottom:8px}
    @media(max-width:640px){.kpi-grid{grid-template-columns:repeat(2,1fr)}}
    </style>"""


# ══════════════════════════════════════════════════════════════════════════════
# CHAT
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/chat", response_class=HTMLResponse)
async def chat_panel(request: Request, conv_id: int = 0):
    user, err = require_auth(request)
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
            utm = db.get_utm_by_conv(conv_id)
            for m in msgs:
                t = m["created_at"][11:16]
                if m.get("media_url") and m.get("media_type","").startswith("image"):
                    bubble = f'<img src="{m["media_url"]}" class="msg-img" onclick="window.open(this.src)" />'
                else:
                    bubble = f'<div class="msg-bubble">{(m["content"] or "").replace("<","&lt;").replace(chr(10),"<br>")}</div>'
                messages_html += f'<div class="msg {m["sender_type"]}" data-id="{m["id"]}">{bubble}<div class="msg-time">{t}</div></div>'

            uname = f"@{active_conv['username']}" if active_conv.get('username') else active_conv.get('tg_chat_id','')
            status_color = "var(--green)" if active_conv["status"] == "open" else "var(--red)"

            utm_tags = ""
            if utm:
                tags = []
                if utm.get("utm_source"):   tags.append(f"src:{utm['utm_source']}")
                if utm.get("utm_campaign"): tags.append(f"camp:{utm['utm_campaign']}")
                if utm.get("fbclid"):       tags.append("fbclid ✓")
                if tags:
                    utm_tags = '<div style="display:flex;flex-wrap:wrap;gap:3px;margin-top:5px">' + "".join(f'<span class="utm-tag">{t}</span>' for t in tags) + '</div>'

            fb_btn = ""
            if staff:
                icon, label, badge_cls = STAFF_STATUSES.get(staff.get("status","new"), ("🆕","Новый","badge-gray"))
                if staff.get("fb_event_sent"):
                    fb_btn = '<span class="badge-green" style="font-size:.72rem;padding:3px 9px">FB Lead ✓ отправлен</span>'
                else:
                    fb_btn = f'<form method="post" action="/chat/send_lead" style="display:inline"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn btn-sm" style="font-size:.74rem">📤 Lead → FB</button></form>'

            tg_number = active_conv.get("tg_chat_id","")
            call_btn = f'<a href="tg://user?id={tg_number}" class="btn-gray btn-sm" style="display:inline-flex;align-items:center;gap:4px;padding:5px 10px;border-radius:7px;font-size:.74rem;border:1px solid var(--border);text-decoration:none">📞 Звонок</a>' if tg_number else ""

            close_btn = (f'<form method="post" action="/chat/close"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-gray btn-sm">✓ Закрыть</button></form>'
                        if active_conv["status"] == "open"
                        else f'<form method="post" action="/chat/reopen"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-orange btn-sm">↺ Открыть</button></form>')

            staff_link = f'<a href="/staff?edit={staff["id"]}" style="color:var(--orange);font-size:.74rem">Карточка →</a>' if staff else ""

            header_html = f"""<div class="chat-header">
              <div style="display:flex;align-items:flex-start;gap:12px;flex:1">
                <div class="avatar">{active_conv['visitor_name'][0].upper()}</div>
                <div style="flex:1">
                  <div style="font-weight:700;color:var(--text)">{active_conv['visitor_name']} <span style="color:{status_color};font-size:.72rem">●</span></div>
                  <div style="font-size:.78rem;color:var(--text3)">{uname} {staff_link}</div>
                  <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:6px;align-items:center">
                    {fb_btn} {call_btn}
                  </div>
                  {utm_tags}
                </div>
              </div>
              <div style="display:flex;gap:6px;flex-shrink:0">{close_btn}</div>
            </div>"""

    conv_items = ""
    for c in convs:
        cls = "conv-item active" if c["id"] == conv_id else "conv-item"
        t = (c.get("last_message_at") or c["created_at"])[:16].replace("T"," ")
        ucount = f'<span class="unread-num">{c["unread_count"]}</span>' if c["unread_count"] > 0 else ""
        dot = "🟢" if c["status"] == "open" else "⚫"
        # Source badge
        if c.get("fbclid"):
            src_badge = '<span class="source-badge source-fb">🔵 FB</span>'
        elif c.get("utm_source"):
            src_badge = f'<span class="source-badge source-tg">{c["utm_source"][:12]}</span>'
        else:
            src_badge = '<span class="source-badge source-organic">organic</span>'
        utm_line = ""
        if c.get("utm_campaign"):
            utm_line = f'<div class="conv-meta"><span class="utm-tag">{c["utm_campaign"][:20]}</span></div>'
        conv_items += f"""<a href="/chat?conv_id={c['id']}"><div class="{cls}">
          <div class="conv-name"><span>{dot} {c['visitor_name']}</span>{ucount}</div>
          <div class="conv-preview">{c.get('last_message') or 'Нет сообщений'}</div>
          <div class="conv-time" style="display:flex;align-items:center;justify-content:space-between">{t} {src_badge}</div>
          {utm_line}</div></a>"""

    if not conv_items:
        conv_items = '<div class="empty" style="padding:36px 14px">Диалогов пока нет</div>'

    b2 = bot_manager.get_staff_bot()
    bot_warn = "" if b2 else '<div style="background:rgba(249,115,22,.1);border:1px solid rgba(249,115,22,.3);border-radius:8px;padding:9px 12px;font-size:.79rem;color:var(--orange);margin-bottom:8px">⚠️ Бот не запущен — <a href="/settings" style="color:var(--orange);text-decoration:underline">Настройки</a></div>'

    right = f"""{header_html}
    <div class="chat-messages" id="msgs">{messages_html}</div>
    <div class="chat-input"><div class="chat-input-row">
      <textarea id="reply-text" placeholder="Ответить… (Enter — отправить)" rows="1" onkeydown="handleKey(event)"></textarea>
      <button class="send-btn-orange" onclick="sendMsg()">Отправить</button>
    </div></div>""" if active_conv else '<div class="no-conv"><div style="font-size:2.5rem">👔</div><div>Выбери диалог</div></div>'

    content = f"""<div class="chat-layout">
      <div class="conv-list">
        <div class="conv-search">{bot_warn}<input type="text" placeholder="🔍 Поиск..." oninput="filterConvs(this.value)"/></div>
        <div id="conv-items">{conv_items}</div>
      </div>
      <div class="chat-window">{right}</div>
    </div>
    <script>
    const msgsEl=document.getElementById('msgs');
    if(msgsEl) msgsEl.scrollTop=msgsEl.scrollHeight;
    async function sendMsg(){{
      const ta=document.getElementById('reply-text');
      const text=ta.value.trim(); if(!text) return; ta.value='';
      await fetch('/chat/send',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:'conv_id={conv_id}&text='+encodeURIComponent(text)}});
      loadNewMsgs();
    }}
    function handleKey(e){{if(e.key==='Enter'&&!e.shiftKey){{e.preventDefault();sendMsg();}}}}
    {"setInterval(loadNewMsgs,3000);" if active_conv else ""}
    async function loadNewMsgs(){{
      const msgs=document.querySelectorAll('#msgs .msg[data-id]');
      const lastId=msgs.length?msgs[msgs.length-1].dataset.id:0;
      const res=await fetch('/api/messages/{conv_id}?after='+lastId);
      const data=await res.json();
      if(data.messages&&data.messages.length>0){{
        const c=document.getElementById('msgs');
        data.messages.forEach(m=>{{const d=document.createElement('div');d.className='msg '+m.sender_type;d.dataset.id=m.id;
          let inner = m.media_url && (m.media_type||'').startsWith('image') ?
            '<img src="'+m.media_url+'" class="msg-img" onclick="window.open(this.src)"/>' :
            '<div class="msg-bubble">'+esc(m.content||'')+'</div>';
          d.innerHTML=inner+'<div class="msg-time">'+m.created_at.substring(11,16)+'</div>';
          c.appendChild(d);}});c.scrollTop=c.scrollHeight;}}
    }}
    function esc(t){{return(t||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\\n/g,'<br>');}}
    function filterConvs(q){{document.querySelectorAll('.conv-item').forEach(el=>{{
      const n=el.querySelector('.conv-name')?.textContent?.toLowerCase()||'';
      el.parentElement.style.display=n.includes(q.toLowerCase())?'':'none';}});}}
    </script>"""

    return HTMLResponse(f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>TG Чаты</title><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">{CSS}</head><body>{nav_html("chat",request)}<div class="main">{content}</div></body></html>')


@app.post("/chat/send")
async def chat_send(request: Request, conv_id: int = Form(...), text: str = Form(...)):
    user, err = require_auth(request)
    if err: return JSONResponse({"error": "unauthorized"}, 401)
    conv = db.get_conversation(conv_id)
    if not conv: return JSONResponse({"error": "not found"}, 404)
    ok = await bot_manager.send_staff_message(conv["tg_chat_id"], text)
    if ok:
        db.save_message(conv_id, conv["tg_chat_id"], "manager", text)
        db.update_conversation_last_message(conv["tg_chat_id"], f"Вы: {text}", increment_unread=False)
    return JSONResponse({"ok": ok})


@app.post("/chat/close")
async def chat_close(request: Request, conv_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.close_conversation(conv_id)
    return RedirectResponse(f"/chat?conv_id={conv_id}", 303)


@app.post("/chat/reopen")
async def chat_reopen(request: Request, conv_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.reopen_conversation(conv_id)
    return RedirectResponse(f"/chat?conv_id={conv_id}", 303)


@app.post("/chat/send_lead")
async def chat_send_lead(request: Request, conv_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    conv  = db.get_conversation(conv_id)
    staff = db.get_staff_by_conv(conv_id) if conv else None
    if not conv: return RedirectResponse("/chat", 303)
    if staff and staff.get("fb_event_sent"):
        return RedirectResponse(f"/chat?conv_id={conv_id}", 303)
    pixel_id   = db.get_setting("pixel_id")
    meta_token = db.get_setting("meta_token")
    sent = await meta_capi.send_lead_event(
        pixel_id, meta_token,
        user_id=conv.get("tg_chat_id",""),
        campaign=conv.get("utm_campaign","telegram")
    )
    if sent and staff:
        db.set_staff_fb_event(staff["id"], "Lead")
    return RedirectResponse(f"/chat?conv_id={conv_id}", 303)


# ══════════════════════════════════════════════════════════════════════════════
# STAFF BASE
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/staff", response_class=HTMLResponse)
async def staff_page(request: Request, edit: int = 0, status_filter: str = "", msg: str = ""):
    user, err = require_auth(request)
    if err: return err
    staff_list = db.get_staff(status_filter if status_filter else None)
    funnel = db.get_staff_funnel()
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""

    # Фильтр
    filter_btns = '<a href="/staff"><button class="btn-gray btn-sm" style="margin-right:4px">Все</button></a>'
    for s, (icon, label, _) in STAFF_STATUSES.items():
        active_style = "background:#1a2535;color:#fff;" if status_filter == s else ""
        cnt = funnel.get(s, 0)
        filter_btns += f'<a href="/staff?status_filter={s}"><button class="btn-gray btn-sm" style="margin-right:4px;{active_style}">{icon} {label} ({cnt})</button></a>'

    edit_form = ""
    if edit:
        with db._conn() as conn:
            s = conn.execute("SELECT * FROM staff WHERE id=?", (edit,)).fetchone()
        if s:
            s = dict(s)
            status_opts = "".join(f'<option value="{k}" {"selected" if s.get("status")==k else ""}>{icon} {label}</option>'
                                  for k, (icon, label, _) in STAFF_STATUSES.items())
            edit_form = f"""<div class="section" style="margin-bottom:18px;border-left:3px solid #f97316">
              <div class="section-head"><h3>✏️ {s['name']}</h3></div>
              <div class="section-body">
                <form method="post" action="/staff/update">
                  <input type="hidden" name="staff_id" value="{s['id']}"/>
                  <div class="grid-3" style="margin-bottom:12px">
                    <div class="field-group"><div class="field-label">Имя</div><input type="text" name="name" value="{s.get('name') or ''}"/></div>
                    <div class="field-group"><div class="field-label">Телефон</div><input type="text" name="phone" value="{s.get('phone') or ''}"/></div>
                    <div class="field-group"><div class="field-label">Email</div><input type="email" name="email" value="{s.get('email') or ''}"/></div>
                    <div class="field-group"><div class="field-label">Должность</div><input type="text" name="position" value="{s.get('position') or ''}"/></div>
                    <div class="field-group"><div class="field-label">Статус</div><select name="status">{status_opts}</select></div>
                    <div class="field-group"><div class="field-label">Теги</div><input type="text" name="tags" value="{s.get('tags') or ''}"/></div>
                  </div>
                  <div class="field-group" style="margin-bottom:12px"><div class="field-label">Заметки</div><textarea name="notes">{s.get('notes') or ''}</textarea></div>
                  <div style="display:flex;gap:8px">
                    <button class="btn-orange">💾 Сохранить</button>
                    <a href="/staff"><button class="btn-gray" type="button">Отмена</button></a>
                  </div>
                </form>
              </div></div>"""

    rows = ""
    for s in staff_list:
        icon, label, badge_cls = STAFF_STATUSES.get(s.get("status","new"), ("🆕","Новый","badge-gray"))
        fb = '<span class="badge-green" style="font-size:.7rem">FB ✓</span>' if s.get("fb_event_sent") else ""
        rows += f"""<tr>
            <td><div style="font-weight:600;color:#fff">{s['name'] or '—'}</div>
              <div style="font-size:.75rem;color:#475569">@{s['username'] or '—'}</div></td>
            <td>{s.get('position') or '—'}</td>
            <td><span class="{badge_cls}">{icon} {label}</span></td>
            <td>{s.get('phone') or '—'}</td>
            <td>{fb}</td>
            <td>{s['created_at'][:10]}</td>
            <td style="white-space:nowrap">
              <a href="/staff?edit={s['id']}"><button class="btn-orange btn-sm">✏️</button></a>
              {'<a href="/chat?conv_id=' + str(s.get("conversation_id","")) + '"><button class="btn-gray btn-sm" style="margin-left:4px">💬</button></a>' if s.get("conversation_id") else ''}
            </td></tr>"""

    if not rows:
        rows = '<tr><td colspan="7"><div class="empty">Нет сотрудников</div></td></tr>'

    content = f"""<div class="page-wrap">
    <div class="page-title">🗂 База сотрудников</div>
    <div class="page-sub">Все кто написал боту</div>
    {alert}
    <div style="margin-bottom:16px">{filter_btns}</div>
    {edit_form}
    <div class="section">
      <div class="section-head"><h3>📋 Сотрудники ({len(staff_list)})</h3></div>
      <table><thead><tr><th>Имя</th><th>Должность</th><th>Статус</th><th>Телефон</th><th>FB</th><th>Добавлен</th><th></th></tr></thead>
      <tbody>{rows}</tbody></table>
    </div></div>"""
    return HTMLResponse(base(content, "staff", request))


@app.post("/staff/update")
async def staff_update(request: Request, staff_id: int = Form(...), name: str = Form(""),
                        phone: str = Form(""), email: str = Form(""), position: str = Form(""),
                        status: str = Form("new"), notes: str = Form(""), tags: str = Form("")):
    user, err = require_auth(request)
    if err: return err
    db.update_staff(staff_id, name, phone, email, position, status, notes, tags)
    return RedirectResponse(f"/staff?msg=Сохранено", 303)


# ══════════════════════════════════════════════════════════════════════════════
# USERS (admin only)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, msg: str = ""):
    user, err = require_auth(request, role="admin")
    if err: return err
    users = db.get_users()
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""
    rows = "".join(f"""<tr>
        <td><b>{u['username']}</b></td>
        <td><span class="{'badge' if u['role']=='admin' else 'badge-gray'}">{u['role']}</span></td>
        <td>{u['created_at'][:10]}</td>
        <td>{'<form method="post" action="/users/delete"><input type="hidden" name="user_id" value="' + str(u['id']) + '"/><button class="del-btn">✕</button></form>' if u['username'] != user['username'] else '—'}</td>
    </tr>""" for u in users)
    content = f"""<div class="page-wrap">
    <div class="page-title">🔐 Пользователи</div>
    <div class="page-sub">Управление доступом к системе</div>
    {alert}
    <div class="section"><div class="section-head"><h3>➕ Добавить пользователя</h3></div>
    <div class="section-body">
      <form method="post" action="/users/add">
        <div class="form-row">
          <div class="field-group"><div class="field-label">Логин</div><input type="text" name="username" required/></div>
          <div class="field-group"><div class="field-label">Пароль</div><input type="password" name="password" required/></div>
          <div class="field-group" style="max-width:160px"><div class="field-label">Роль</div>
            <select name="role"><option value="manager">manager</option><option value="admin">admin</option></select></div>
          <div style="display:flex;align-items:flex-end"><button class="btn">Добавить</button></div>
        </div>
      </form>
    </div></div>
    <div class="section"><div class="section-head"><h3>👤 Пользователи ({len(users)})</h3></div>
    <table><thead><tr><th>Логин</th><th>Роль</th><th>Создан</th><th></th></tr></thead>
    <tbody>{rows}</tbody></table></div></div>"""
    return HTMLResponse(base(content, "users", request))


@app.post("/users/add")
async def users_add(request: Request, username: str = Form(...), password: str = Form(...), role: str = Form("manager")):
    user, err = require_auth(request, role="admin")
    if err: return err
    try:
        db.create_user(username.strip(), password, role)
        return RedirectResponse("/users?msg=Пользователь+добавлен", 303)
    except:
        return RedirectResponse("/users?msg=Такой+логин+уже+существует", 303)


@app.post("/users/delete")
async def users_delete(request: Request, user_id: int = Form(...)):
    user, err = require_auth(request, role="admin")
    if err: return err
    db.delete_user(user_id)
    return RedirectResponse("/users?msg=Удалён", 303)


# ══════════════════════════════════════════════════════════════════════════════
# SETTINGS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, msg: str = ""):
    user, err = require_auth(request, role="admin")
    if err: return err

    b1_info = await bot_manager.get_bot_info(bot_manager.get_tracker_bot())
    b2_info = await bot_manager.get_bot_info(bot_manager.get_staff_bot())
    pixel_id      = db.get_setting("pixel_id")
    meta_token    = db.get_setting("meta_token")
    land_title    = db.get_setting("landing_title", "Наши каналы")
    land_sub      = db.get_setting("landing_subtitle", "Подписывайся и будь в курсе")
    staff_welcome = db.get_setting("staff_welcome", "Привет! Напиши своё имя и должность 👋")
    notify_chat   = db.get_setting("notify_chat_id", "")
    app_url       = db.get_setting("app_url", "")
    masked = meta_token[:12] + "..." + meta_token[-6:] if len(meta_token) > 20 else meta_token
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""

    def bot_card(title, color, info, field, route):
        status = f'<span style="color:#34d399">● Активен — <a href="{info.get("link","")}" target="_blank" style="color:#60a5fa">@{info.get("username","")}</a></span>' if info.get("active") else '<span style="color:#ef4444">● Не запущен</span>'
        border = "#3b82f6" if color == "blue" else "#f97316"
        btn = "btn" if color == "blue" else "btn-orange"
        return f"""<div class="section" style="border-left:3px solid {border}">
          <div class="section-head"><h3>{title}</h3><span style="font-size:.82rem">{status}</span></div>
          <div class="section-body">
            <form method="post" action="/{route}"><div class="form-row">
              <div class="field-group"><div class="field-label">Новый токен бота</div>
              <input type="text" name="{field}" placeholder="Вставь токен от @BotFather — оставь пустым чтобы не менять"/></div>
              <div style="display:flex;align-items:flex-end"><button class="{btn}">🔄 Сменить</button></div>
            </div></form>
          </div></div>"""

    content = f"""<div class="page-wrap">
    <div class="page-title">⚙️ Настройки</div><div class="page-sub">Управление ботами и системой</div>
    {alert}

    <div class="section-head" style="padding:0;margin-bottom:12px"><h3 style="font-size:.78rem;font-weight:700;color:#3b82f6;text-transform:uppercase;letter-spacing:.08em">🤖 Управление ботами</h3></div>
    {bot_card("🔵 Бот 1 — Трекер (Клиенты)", "blue", b1_info, "bot1_token", "settings/bot1")}
    {bot_card("🟠 Бот 2 — Сотрудники", "orange", b2_info, "bot2_token", "settings/bot2")}

    <div class="section" style="border-left:3px solid #25d366">
      <div class="section-head"><h3>💚 WhatsApp</h3>
        <span style="font-size:.82rem">{
            '<span style="color:#34d399">● Подключён · +' + db.get_setting("wa_connected_number","") + '</span>'
            if db.get_setting("wa_status") == "ready"
            else ('<span style="color:#fbbf24">● Ожидает QR...</span>'
                  if db.get_setting("wa_status") == "qr"
                  else '<span style="color:#ef4444">● Не подключён</span>')
        }</span>
      </div>
      <div class="section-body">
        <a href="/wa/setup" class="btn" style="background:#059669;display:inline-flex;align-items:center;gap:8px;text-decoration:none">
          📱 Открыть подключение WhatsApp / QR-код
        </a>
        <div style="font-size:.78rem;color:var(--text3);margin-top:8px">
          Здесь сканируешь QR для подключения номера. После деплоя нужно переподключать если статус ⚫.
        </div>
      </div>
    </div>

    <div class="section">
      <div class="section-head"><h3>📡 Meta Pixel & CAPI</h3></div>
      <div class="section-body">
        <form method="post" action="/settings/pixel">
          <div class="grid-2" style="margin-bottom:12px">
            <div class="field-group"><div class="field-label">Pixel ID</div><input type="text" name="pixel_id" value="{pixel_id}"/></div>
            <div class="field-group"><div class="field-label">Access Token (сейчас: {masked})</div><input type="text" name="meta_token" placeholder="Оставь пустым — не менять"/></div>
          </div>
          <button class="btn">💾 Сохранить</button>
        </form>
      </div>
    </div>

    <div class="section">
      <div class="section-head"><h3>🔔 Уведомления менеджеру</h3></div>
      <div class="section-body">
        <form method="post" action="/settings/notify">
          <div class="grid-2" style="margin-bottom:12px">
            <div class="field-group"><div class="field-label">Telegram Chat ID менеджера</div>
              <input type="text" name="notify_chat_id" value="{notify_chat}" placeholder="Например: 123456789"/>
              <span style="font-size:.75rem;color:#475569">Напишите /start @userinfobot чтобы узнать свой ID</span>
            </div>
            <div class="field-group"><div class="field-label">URL приложения (для кнопки в уведомлении)</div>
              <input type="text" name="app_url" value="{app_url}" placeholder="https://web-production-xxx.up.railway.app"/>
            </div>
          </div>
          <button class="btn">💾 Сохранить</button>
        </form>
      </div>
    </div>

    <div class="section" style="border-left:3px solid #f97316">
      <div class="section-head"><h3>👔 Бот сотрудников — тексты</h3></div>
      <div class="section-body">
        <form method="post" action="/settings/staff_welcome">
          <div class="field-group" style="margin-bottom:12px">
            <div class="field-label">Приветственное сообщение (/start)</div>
            <textarea name="staff_welcome">{staff_welcome}</textarea>
          </div>
          <button class="btn-orange">💾 Сохранить</button>
        </form>
      </div>
    </div>

    <div class="section">
      <div class="section-head"><h3>🌐 Лендинг</h3></div>
      <div class="section-body">
        <form method="post" action="/settings/landing">
          <div class="grid-2" style="margin-bottom:12px">
            <div class="field-group"><div class="field-label">Заголовок</div><input type="text" name="landing_title" value="{land_title}"/></div>
            <div class="field-group"><div class="field-label">Подзаголовок</div><input type="text" name="landing_subtitle" value="{land_sub}"/></div>
          </div>
          <button class="btn">💾 Сохранить</button>
        </form>
      </div>
    </div></div>"""
    return HTMLResponse(base(content, "settings", request))


@app.post("/settings/bot1")
async def settings_bot1(request: Request, bot1_token: str = Form("")):
    user, err = require_auth(request, role="admin")
    if err: return err
    if bot1_token.strip():
        db.set_setting("bot1_token", bot1_token.strip())
        await bot_manager.start_tracker_bot(bot1_token.strip())
        info = await bot_manager.get_bot_info(bot_manager.get_tracker_bot())
        if info.get("username"): db.set_setting("bot1_name", f"@{info['username']}")
    return RedirectResponse("/settings?msg=Бот+1+обновлён", 303)


@app.post("/settings/bot2")
async def settings_bot2(request: Request, bot2_token: str = Form("")):
    user, err = require_auth(request, role="admin")
    if err: return err
    if bot2_token.strip():
        db.set_setting("bot2_token", bot2_token.strip())
        await bot_manager.start_staff_bot(bot2_token.strip())
        info = await bot_manager.get_bot_info(bot_manager.get_staff_bot())
        if info.get("username"): db.set_setting("bot2_name", f"@{info['username']}")
    return RedirectResponse("/settings?msg=Бот+2+обновлён", 303)


@app.post("/settings/pixel")
async def settings_pixel(request: Request, pixel_id: str = Form(""), meta_token: str = Form("")):
    user, err = require_auth(request, role="admin")
    if err: return err
    if pixel_id.strip():   db.set_setting("pixel_id",   pixel_id.strip())
    if meta_token.strip(): db.set_setting("meta_token", meta_token.strip())
    return RedirectResponse("/settings?msg=Пиксель+обновлён", 303)


@app.post("/settings/notify")
async def settings_notify(request: Request, notify_chat_id: str = Form(""), app_url: str = Form("")):
    user, err = require_auth(request, role="admin")
    if err: return err
    db.set_setting("notify_chat_id", notify_chat_id.strip())
    db.set_setting("app_url", app_url.strip())
    db.set_setting("dashboard_password", SECRET)
    return RedirectResponse("/settings?msg=Уведомления+настроены", 303)


@app.post("/settings/staff_welcome")
async def settings_staff_welcome(request: Request, staff_welcome: str = Form("")):
    user, err = require_auth(request, role="admin")
    if err: return err
    if staff_welcome: db.set_setting("staff_welcome", staff_welcome)
    return RedirectResponse("/settings?msg=Сохранено", 303)


@app.post("/settings/landing")
async def settings_landing(request: Request, landing_title: str = Form(""), landing_subtitle: str = Form("")):
    user, err = require_auth(request, role="admin")
    if err: return err
    if landing_title:    db.set_setting("landing_title", landing_title)
    if landing_subtitle: db.set_setting("landing_subtitle", landing_subtitle)
    return RedirectResponse("/settings?msg=Лендинг+обновлён", 303)


# ══════════════════════════════════════════════════════════════════════════════
# КАНАЛЫ / КАМПАНИИ / ЛЕНДИНГ / FLOW (без изменений логики)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/channels", response_class=HTMLResponse)
async def channels_page(request: Request, msg: str = "", err_msg: str = ""):
    user, err = require_auth(request)
    if err: return err
    channels = db.get_channels()
    b1 = bot_manager.get_tracker_bot()
    bot_link = (await b1.get_me()).username if b1 else "—"
    bot_link_url = f"https://t.me/{bot_link}" if b1 else "—"
    rows = "".join(f"""<tr><td><b>{c['name']}</b></td><td><span class="tag">{c['channel_id']}</span></td>
        <td style="color:#34d399;font-weight:600">{c['total_joins']}</td><td>{c['created_at'][:10]}</td>
        <td><form method="post" action="/channels/delete"><input type="hidden" name="channel_id" value="{c['channel_id']}"/>
        <button class="del-btn">✕</button></form></td></tr>""" for c in channels
    ) or '<tr><td colspan="5"><div class="empty">Каналов нет</div></td></tr>'
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else (f'<div class="alert-red">❌ {err_msg}</div>' if err_msg else "")
    content = f"""<div class="page-wrap"><div class="page-title">📡 Каналы</div>
    <div class="page-sub">Telegram-каналы для трекинга подписок</div>
    <div class="section"><div class="section-head"><h3>🤖 Бот трекер — добавь как администратора в каждый канал</h3></div>
    <div class="section-body"><div class="link-box">{bot_link_url}</div></div></div>
    <div class="section"><div class="section-head"><h3>➕ Добавить канал</h3></div><div class="section-body">
    {alert}<form method="post" action="/channels/add"><div class="form-row">
    <div class="field-group"><div class="field-label">Название</div><input type="text" name="name" placeholder="Phoenix" required/></div>
    <div class="field-group"><div class="field-label">ID канала</div><input type="text" name="channel_id" placeholder="-1003835844880" required/></div>
    <div style="display:flex;align-items:flex-end"><button class="btn">Добавить</button></div>
    </div></form></div></div>
    <div class="section"><div class="section-head"><h3>📋 Каналы ({len(channels)})</h3></div>
    <table><thead><tr><th>Название</th><th>ID</th><th>Подписчиков</th><th>Добавлен</th><th></th></tr></thead>
    <tbody>{rows}</tbody></table></div></div>"""
    return HTMLResponse(base(content, "channels", request))


@app.post("/channels/add")
async def channels_add(request: Request, name: str = Form(...), channel_id: str = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.add_channel(name.strip(), channel_id.strip())
    return RedirectResponse("/channels?msg=Канал+добавлен", 303)


@app.post("/channels/delete")
async def channels_delete(request: Request, channel_id: str = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.delete_channel(channel_id)
    return RedirectResponse("/channels?msg=Удалён", 303)


@app.get("/campaigns", response_class=HTMLResponse)
async def campaigns_page(request: Request, msg: str = "", err_msg: str = ""):
    user, err = require_auth(request)
    if err: return err
    channels  = db.get_channels()
    campaigns = db.get_campaigns()
    templates = db.get_landings(ltype="client")  # шаблоны лендингов
    app_url   = db.get_setting("app_url", "").rstrip("/")

    # Опции выбора шаблона
    tpl_opts = '<option value="">— Дефолтный (Relaxation) —</option>' + \
               "".join(f'<option value="{t["id"]}">{t["name"]}</option>' for t in templates)

    campaign_cards = ""
    for c in campaigns:
        slug_url = f"{app_url}/l/{c.get('slug','')}"
        cchans = db.get_campaign_channels(c["id"])

        # Текущий шаблон
        tpl = next((t for t in templates if t["id"] == c.get("landing_id")), None)
        tpl_badge = f'<span class="badge-green" style="font-size:.71rem">🎨 {tpl["name"]}</span>' if tpl else \
                    '<span class="badge-gray" style="font-size:.71rem">🎨 Дефолтный</span>'

        # Смена шаблона — inline select
        tpl_select_opts = '<option value="">— Дефолтный —</option>' + \
                          "".join(f'<option value="{t["id"]}" {"selected" if t["id"]==c.get("landing_id") else ""}>{t["name"]}</option>' for t in templates)
        tpl_switch = f"""<form method="post" action="/campaigns/set_template" style="display:flex;gap:6px;align-items:center">
          <input type="hidden" name="campaign_id" value="{c['id']}"/>
          <select name="landing_id" style="font-size:.77rem;padding:4px 8px;border-radius:7px;width:auto">{tpl_select_opts}</select>
          <button class="btn btn-sm" style="font-size:.74rem;padding:5px 10px">Сменить шаблон</button>
        </form>"""

        chan_rows = ""
        for cc in cchans:
            chan_rows += f"""<tr>
              <td style="font-weight:600">{cc.get('channel_name') or cc['channel_id']}</td>
              <td><div class="link-box" style="font-size:.69rem;padding:5px 9px">{cc['invite_link'][:50]}...</div></td>
              <td style="color:var(--green);font-weight:700">{cc['joins']}</td>
              <td><form method="post" action="/campaigns/channel/delete" style="display:inline">
                <input type="hidden" name="cc_id" value="{cc['id']}"/>
                <input type="hidden" name="campaign_id" value="{c['id']}"/>
                <button class="del-btn btn-sm">✕</button>
              </form></td>
            </tr>"""
        if not chan_rows:
            chan_rows = '<tr><td colspan="4"><div class="empty" style="padding:12px">Нет каналов — добавь ниже</div></td></tr>'

        ch_opts = "".join(f'<option value="{ch["channel_id"]}">{ch["name"]}</option>' for ch in channels)

        campaign_cards += f"""
        <div class="section" style="border-left:3px solid var(--accent)">
          <div class="section-head">
            <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
              <h3>🎯 {c['name']}</h3>
              <span class="badge" style="font-size:.72rem">{c['total_joins']} подписок</span>
              {tpl_badge}
            </div>
            <div style="display:flex;gap:8px;align-items:center">
              <a href="{slug_url}" target="_blank" class="btn-gray btn-sm">🌐 Лендинг</a>
              <form method="post" action="/campaigns/delete">
                <input type="hidden" name="campaign_id" value="{c['id']}"/>
                <button class="del-btn">✕</button>
              </form>
            </div>
          </div>
          <div class="section-body">
            <div style="margin-bottom:12px;padding:10px 14px;background:var(--bg3);border-radius:9px;border:1px solid var(--border)">
              <div style="font-size:.74rem;color:var(--text3);margin-bottom:5px;font-weight:700;text-transform:uppercase;letter-spacing:.05em">🔗 Ссылка в рекламу</div>
              <div class="link-box">{slug_url}</div>
              <div style="margin-top:10px">{tpl_switch}</div>
            </div>
            <table><thead><tr><th>Канал</th><th>Invite Link</th><th>Подписок</th><th></th></tr></thead>
            <tbody>{chan_rows}</tbody></table>
            <form method="post" action="/campaigns/channel/add" style="margin-top:14px;display:block">
              <input type="hidden" name="campaign_id" value="{c['id']}"/>
              <input type="hidden" name="campaign_name" value="{c['name']}"/>
              <div class="form-row">
                <div class="field-group"><div class="field-label">Добавить канал</div>
                  <select name="channel_id">{ch_opts}</select></div>
                <div style="display:flex;align-items:flex-end">
                  <button class="btn btn-sm">+ Добавить и создать ссылку</button>
                </div>
              </div>
            </form>
          </div>
        </div>"""

    if not campaign_cards:
        campaign_cards = '<div class="empty" style="padding:40px">Кампаний нет — создай первую</div>'

    # Подсказка если нет шаблонов
    tpl_hint = ""
    if not templates:
        tpl_hint = f'<div style="font-size:.8rem;color:var(--text3);margin-top:6px">💡 Нет кастомных шаблонов — <a href="/landings" style="color:var(--accent)">создай шаблон →</a> или будет использован дефолтный дизайн</div>'

    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else (f'<div class="alert-red">❌ {err_msg}</div>' if err_msg else "")
    content = f"""<div class="page-wrap">
    <div class="page-title">🔗 Кампании</div>
    <div class="page-sub">Кампания = каналы + шаблон лендинга. Ставишь ссылку /l/slug в рекламу — пользователь подписывается — фиксируется Subscribe в FB CAPI.</div>
    {alert}
    <div class="section">
      <div class="section-head"><h3>➕ Создать кампанию</h3></div>
      <div class="section-body">
        <form method="post" action="/campaigns/create"><div class="form-row">
          <div class="field-group"><div class="field-label">Название (будет в UTM)</div>
            <input type="text" name="name" placeholder="FB_Broad_March_NYC" required/></div>
          <div class="field-group" style="max-width:200px"><div class="field-label">URL slug</div>
            <input type="text" name="slug" placeholder="march-nyc"/></div>
          <div class="field-group" style="max-width:240px"><div class="field-label">🎨 Шаблон лендинга</div>
            <select name="landing_id">{tpl_opts}</select></div>
          <div style="display:flex;align-items:flex-end"><button class="btn">Создать</button></div>
        </div></form>
        {tpl_hint}
      </div>
    </div>
    {campaign_cards}
    </div>"""
    return HTMLResponse(base(content, "campaigns", request))


@app.post("/campaigns/create")
async def campaigns_create(request: Request, name: str = Form(...), slug: str = Form(""),
                            landing_id: str = Form("")):
    user, err = require_auth(request)
    if err: return err
    import re, secrets as _sec
    if not slug.strip():
        slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') + "-" + _sec.token_hex(3)
    lid = int(landing_id) if landing_id.strip().isdigit() else None
    try:
        db.create_campaign(name.strip(), slug.strip(), landing_id=lid)
        return RedirectResponse(f"/campaigns?msg=Кампания+{name}+создана", 303)
    except Exception as e:
        return RedirectResponse(f"/campaigns?err_msg={str(e)}", 303)


@app.post("/campaigns/set_template")
async def campaigns_set_template(request: Request, campaign_id: int = Form(...),
                                  landing_id: str = Form("")):
    user, err = require_auth(request)
    if err: return err
    lid = int(landing_id) if landing_id.strip().isdigit() else None
    db.update_campaign_landing(campaign_id, lid)
    return RedirectResponse("/campaigns?msg=Шаблон+обновлён", 303)


@app.post("/campaigns/delete")
async def campaigns_delete(request: Request, campaign_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.delete_campaign(campaign_id)
    return RedirectResponse("/campaigns", 303)


@app.post("/campaigns/channel/add")
async def campaigns_channel_add(request: Request, campaign_id: int = Form(...),
                                 campaign_name: str = Form(...), channel_id: str = Form(...)):
    user, err = require_auth(request)
    if err: return err
    try:
        b1 = bot_manager.get_tracker_bot()
        if not b1: return RedirectResponse("/campaigns?err_msg=Бот+1+не+запущен", 303)
        # Создаём invite-ссылку через бота
        link_name = f"{campaign_name[:20]}_{channel_id[-6:]}"
        link_obj = await b1.create_chat_invite_link(chat_id=int(channel_id), name=link_name[:32])
        # Получаем название канала
        try:
            chat = await b1.get_chat(int(channel_id))
            ch_name = chat.title or channel_id
        except Exception:
            ch_name = channel_id
        db.add_campaign_channel(campaign_id, channel_id, ch_name, link_obj.invite_link)
        return RedirectResponse(f"/campaigns?msg=Канал+добавлен+в+кампанию", 303)
    except Exception as e:
        return RedirectResponse(f"/campaigns?err_msg={str(e)}", 303)


@app.post("/campaigns/channel/delete")
async def campaigns_channel_delete(request: Request, cc_id: int = Form(...), campaign_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.remove_campaign_channel(cc_id)
    return RedirectResponse(f"/campaigns", 303)


@app.get("/landings", response_class=HTMLResponse)
async def landings_client(request: Request, msg: str = ""):
    user, err = require_auth(request)
    if err: return err
    return HTMLResponse(base(_landings_page(ltype="client", active="landings", msg=msg, request=request), "landings", request))


@app.get("/landings_staff", response_class=HTMLResponse)
async def landings_staff_page(request: Request, msg: str = ""):
    user, err = require_auth(request)
    if err: return err
    return HTMLResponse(base(_landings_page(ltype="staff", active="landings_staff", msg=msg, request=request), "landings_staff", request))


def _landings_page(ltype: str, active: str, msg: str, request: Request) -> str:
    landings = db.get_landings(ltype)
    if ltype == "staff":
        title = "💼 Лендинги HR"
        sub   = "Лендинги для рекрутинга. Кнопки контактов (TG/WA) настраиваются из админки."
    else:
        title = "🎨 Шаблоны лендингов"
        sub   = "Создай несколько дизайнов. При создании кампании выбираешь какой шаблон использовать."
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""
    rows = ""
    for l in landings:
        slug_url = f"/l/{l['slug']}"
        rows += f"""<tr>
          <td><b>{l['name']}</b></td>
          <td><a href="{slug_url}" target="_blank" class="link-box" style="display:inline-block">{slug_url}</a></td>
          <td><span class="{'badge-green' if l['active'] else 'badge-gray'}">{'Активен' if l['active'] else 'Скрыт'}</span></td>
          <td>
            <a href="/landings/edit?id={l['id']}" class="btn-gray btn-sm">✏️ Редакт.</a>
            <form method="post" action="/landings/delete" style="display:inline"><input type="hidden" name="id" value="{l['id']}"/><button class="del-btn btn-sm">✕</button></form>
          </td></tr>"""
    rows = rows or f'<tr><td colspan="4"><div class="empty">Нет шаблонов — создай первый</div></td></tr>'
    return f"""<div class="page-wrap"><div class="page-title">{title}</div>
    <div class="page-sub">{sub}</div>{alert}
    <div class="section"><div class="section-head"><h3>➕ Создать шаблон</h3></div><div class="section-body">
    <form method="post" action="/landings/create"><input type="hidden" name="ltype" value="{ltype}"/>
    <input type="hidden" name="redirect" value="/landings{'_staff' if ltype=='staff' else ''}"/>
    <div class="form-row">
      <div class="field-group"><div class="field-label">Название шаблона</div><input type="text" name="name" placeholder="{'Лендинг HR v2' if ltype=='staff' else 'Массаж NYC — стиль 2'}" required/></div>
      <div class="field-group" style="max-width:200px"><div class="field-label">URL slug {'(только для HR)' if ltype=='staff' else '(только для предпросмотра)'}</div><input type="text" name="slug" placeholder="{'hr-v2' if ltype=='staff' else 'nyc-v2'}" required/></div>
      <div style="display:flex;align-items:flex-end"><button class="btn">Создать</button></div>
    </div></form></div></div>
    <div class="section"><div class="section-head"><h3>📋 Шаблоны ({len(landings)})</h3></div>
    <table><thead><tr><th>Название</th><th>URL предпросмотра</th><th>Статус</th><th>Действия</th></tr></thead>
    <tbody>{rows}</tbody></table></div></div>"""


@app.post("/landings/create")
async def landings_create(request: Request, name: str = Form(...), slug: str = Form(...),
                           ltype: str = Form("client"), redirect: str = Form("/landings")):
    user, err = require_auth(request)
    if err: return err
    import re, json
    clean_slug = re.sub(r'[^a-z0-9-]', '-', slug.lower().strip())
    if ltype == "staff":
        content = json.dumps({"type": "staff"})
    else:
        content = json.dumps({"type": "client"})
    try:
        db.create_landing(name.strip(), ltype, clean_slug, content)
        return RedirectResponse(f"{redirect}?msg=Лендинг+создан", 303)
    except Exception as e:
        return RedirectResponse(f"{redirect}?msg=Ошибка:+{str(e)}", 303)


@app.post("/landings/delete")
async def landings_delete_route(request: Request, id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.delete_landing(id)
    return RedirectResponse("/landings", 303)


@app.get("/landings/edit", response_class=HTMLResponse)
async def landings_edit(request: Request, id: int = 0, msg: str = ""):
    user, err = require_auth(request)
    if err: return err
    landing = db.get_landing(id)
    if not landing: return RedirectResponse("/landings", 303)
    contacts = db.get_landing_contacts(id)
    app_url  = db.get_setting("app_url", "")
    alert    = f'<div class="alert-green">✅ {msg}</div>' if msg else ""

    contact_rows = ""
    for c in contacts:
        type_icon = "📱" if c["type"] == "telegram" else "💚"
        contact_rows += f"""<tr>
          <td>{type_icon} <span class="badge">{c['type']}</span></td>
          <td>{c['label']}</td>
          <td><a href="{c['url']}" target="_blank" style="color:var(--accent);font-size:.8rem">{c['url'][:40]}...</a></td>
          <td><form method="post" action="/landings/contact/delete"><input type="hidden" name="contact_id" value="{c['id']}"/><input type="hidden" name="landing_id" value="{id}"/><button class="del-btn">✕</button></form></td></tr>"""
    contact_rows = contact_rows or '<tr><td colspan="4"><div class="empty">Нет контактов</div></td></tr>'

    public_url = f"{app_url}/l/{landing['slug']}"
    back = "/landings_staff" if landing["type"] == "staff" else "/landings"
    content = f"""<div class="page-wrap">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px">
      <a href="{back}" class="btn-gray btn-sm">← Назад</a>
      <div class="page-title">✏️ {landing['name']}</div>
    </div>
    {alert}
    <div class="section"><div class="section-head"><h3>🔗 Публичная ссылка</h3></div>
    <div class="section-body"><div class="link-box">{public_url}</div>
    <a href="{public_url}" target="_blank" class="btn btn-sm" style="margin-top:10px;display:inline-block">Открыть лендинг →</a></div></div>
    <div class="section"><div class="section-head"><h3>➕ Добавить контакт / кнопку</h3><small style="color:var(--text3)">Эти кнопки появятся на лендинге</small></div>
    <div class="section-body"><form method="post" action="/landings/contact/add"><input type="hidden" name="landing_id" value="{id}"/>
    <div class="form-row">
      <div class="field-group" style="max-width:160px"><div class="field-label">Тип</div>
      <select name="ctype"><option value="telegram">📱 Telegram</option><option value="whatsapp">💚 WhatsApp</option><option value="other">🔗 Другое</option></select></div>
      <div class="field-group" style="max-width:180px"><div class="field-label">Текст кнопки</div><input type="text" name="label" placeholder="Написать в Telegram" required/></div>
      <div class="field-group"><div class="field-label">URL</div><input type="text" name="url" placeholder="https://t.me/username или https://wa.me/1..." required/></div>
      <div style="display:flex;align-items:flex-end"><button class="btn">Добавить</button></div>
    </div></form></div></div>
    <div class="section"><div class="section-head"><h3>🔘 Кнопки контактов ({len(contacts)})</h3></div>
    <table><thead><tr><th>Тип</th><th>Текст</th><th>URL</th><th></th></tr></thead>
    <tbody>{contact_rows}</tbody></table></div></div>"""
    return HTMLResponse(base(content, landing["type"] + "_landing", request))


@app.post("/landings/contact/add")
async def landing_contact_add(request: Request, landing_id: int = Form(...),
                               ctype: str = Form(...), label: str = Form(...), url: str = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.add_landing_contact(landing_id, ctype, label.strip(), url.strip())
    return RedirectResponse(f"/landings/edit?id={landing_id}&msg=Контакт+добавлен", 303)


@app.post("/landings/contact/delete")
async def landing_contact_delete(request: Request, contact_id: int = Form(...), landing_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.delete_landing_contact(contact_id)
    return RedirectResponse(f"/landings/edit?id={landing_id}", 303)


@app.get("/l/{slug}", response_class=HTMLResponse)
async def public_landing(request: Request, slug: str,
                          fbclid: str = None, utm_source: str = None,
                          utm_medium: str = None, utm_campaign: str = None,
                          utm_content: str = None, utm_term: str = None):
    # Ищем как Campaign slug
    campaign = db.get_campaign_by_slug(slug)
    if campaign:
        channels = db.get_campaign_channels(campaign["id"])
        app_url  = db.get_setting("app_url", "").rstrip("/")
        pixel_id = db.get_setting("pixel_id", "")

        # Строим /go ссылки для каждого канала
        btns = []
        for cc in channels:
            go_url = f"{app_url}/go?to={cc['invite_link']}&utm_campaign={campaign['name']}&utm_source={utm_source or 'facebook'}&utm_medium={utm_medium or 'paid'}"
            if fbclid:      go_url += f"&fbclid={fbclid}"
            if utm_content: go_url += f"&utm_content={utm_content}"
            btns.append({"url": go_url, "label": cc.get("channel_name") or "Вступить в группу"})

        # Если у кампании выбран кастомный шаблон — рендерим его
        if campaign.get("landing_id"):
            landing  = db.get_landing(campaign["landing_id"])
            contacts = db.get_landing_contacts(campaign["landing_id"]) if landing else []
            # Заменяем контакты на каналы кампании
            if landing:
                # Передаём каналы как контакты с /go ссылками
                chan_contacts = [{"type": "telegram", "label": b["label"], "url": b["url"]} for b in btns]
                return HTMLResponse(_render_client_landing(landing, chan_contacts, pixel_id=pixel_id))

        # Дефолтный шаблон (Relaxation)
        return HTMLResponse(_render_campaign_landing(campaign, btns, pixel_id, fbclid))

    # Иначе ищем как Staff Landing slug
    landing = db.get_landing_by_slug(slug)
    if not landing: return HTMLResponse("<h2>Not found</h2>", 404)
    contacts = db.get_landing_contacts(landing["id"])
    return HTMLResponse(_render_staff_landing(landing, contacts))


def _render_campaign_landing(campaign, btns: list, pixel_id: str, fbclid: str = None) -> str:
    """Лендинг кампании — показывает все каналы как кнопки подписки"""
    btn_html = ""
    for b in btns:
        icon_svg = '<svg viewBox="0 0 24 24" fill="currentColor" width="22" height="22"><path d="M9.036 15.28 8.87 18.64c.34 0 .49-.15.67-.33l1.6-1.54 3.31 2.43c.61.34 1.05.16 1.22-.56l2.2-10.3c.2-.9-.32-1.25-.92-1.03L3.9 10.01c-.88.34-.86.83-.15 1.05l3.29 1.02 7.64-4.82c.36-.23.69-.1.42.14z"/></svg>'
        btn_html += f'<a class="lnd-btn lnd-tg" href="{b["url"]}">{icon_svg} {b["label"]}</a>'

    pixel_js = ""
    if pixel_id:
        pixel_js = f"""
    <script>
    !function(f,b,e,v,n,t,s){{if(f.fbq)return;n=f.fbq=function(){{n.callMethod?
    n.callMethod.apply(n,arguments):n.queue.push(arguments)}};
    if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
    n.queue=[];t=b.createElement(e);t.async=!0;
    t.src=v;s=b.getElementsByTagName(e)[0];
    s.parentNode.insertBefore(t,s)}}(window,document,'script',
    'https://connect.facebook.net/en_US/fbevents.js');
    fbq('init', '{pixel_id}');
    fbq('track', 'PageView');
    // Подписка на кнопки
    document.querySelectorAll('.lnd-btn').forEach(function(btn) {{
        btn.addEventListener('click', function() {{
            fbq('track', 'Subscribe');
        }});
    }});
    </script>
    <noscript><img height="1" width="1" style="display:none"
    src="https://www.facebook.com/tr?id={pixel_id}&ev=PageView&noscript=1"/></noscript>"""

    return f"""<!DOCTYPE html><html lang="en"><head>
    <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Relaxation and Balance 🌿✨</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:'Inter',system-ui;background:#060a0f;color:#e8f0f8;min-height:100vh}}
    .top-bar{{background:linear-gradient(135deg,#1a0a2e,#0d1a2e);border-bottom:1px solid rgba(255,255,255,.08);padding:12px 20px;text-align:center;font-size:.82rem;font-weight:600;color:#f8d56b;letter-spacing:.02em}}
    .hero{{position:relative;min-height:50vh;display:flex;align-items:center;justify-content:center;text-align:center;overflow:hidden}}
    .hero::before{{content:"";position:absolute;inset:0;background:url('https://images.unsplash.com/photo-1544161515-4ab6ce6db874?q=80&w=1920&auto=format&fit=crop') center/cover;filter:brightness(.35)}}
    .hero::after{{content:"";position:absolute;inset:0;background:linear-gradient(to bottom,transparent 30%,#060a0f)}}
    .hero-inner{{position:relative;z-index:1;padding:48px 20px 32px}}
    .hero h1{{font-size:clamp(1.8rem,4vw,2.8rem);font-weight:800;line-height:1.15;margin-bottom:10px}}
    .hero p{{color:rgba(255,255,255,.7);max-width:500px;margin:0 auto;font-size:.95rem;line-height:1.7}}
    .wrap{{max-width:600px;margin:0 auto;padding:0 20px 60px}}
    .section-title{{font-size:1.1rem;font-weight:700;margin:32px 0 16px;color:#e8f0f8}}
    .utp-list{{display:flex;flex-direction:column;gap:10px;margin-bottom:32px}}
    .utp-item{{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:13px;padding:14px 18px;font-size:.9rem;line-height:1.5}}
    .desc-box{{background:rgba(99,102,241,.08);border:1px solid rgba(99,102,241,.25);border-radius:13px;padding:16px 20px;font-size:.88rem;line-height:1.7;color:rgba(255,255,255,.8);margin-bottom:32px}}
    .rates{{display:flex;flex-direction:column;gap:8px;margin-bottom:32px}}
    .rate-item{{display:flex;justify-content:space-between;align-items:center;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:11px;padding:14px 20px;font-weight:600}}
    .rate-price{{font-size:1.15rem;color:#a5f3fc}}
    .info-box{{background:rgba(248,212,0,.06);border:1px solid rgba(248,212,0,.2);border-radius:13px;padding:16px 20px;margin-bottom:32px}}
    .info-item{{font-size:.86rem;line-height:1.8;color:rgba(255,255,255,.8)}}
    .contact-section{{text-align:center;padding:32px 0}}
    #contact-anchor{{scroll-margin-top:20px}}
    .contact-title{{font-size:1.3rem;font-weight:800;margin-bottom:8px}}
    .contact-sub{{color:rgba(255,255,255,.5);font-size:.88rem;margin-bottom:24px}}
    .lnd-btn{{display:flex;align-items:center;justify-content:center;gap:10px;width:100%;padding:15px;border-radius:13px;font-weight:700;font-size:.95rem;text-decoration:none;margin-bottom:10px;transition:opacity .15s}}
    .lnd-btn:hover{{opacity:.88}}
    .lnd-tg{{background:#26A5E4;color:#fff}}
    .cta-btn{{display:flex;align-items:center;justify-content:center;width:100%;padding:15px;border-radius:13px;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.15);color:#fff;font-weight:600;font-size:.9rem;text-decoration:none;margin-bottom:10px;cursor:pointer;transition:background .15s}}
    .cta-btn:hover{{background:rgba(255,255,255,.16)}}
    .msg-book{{text-align:center;font-size:1rem;color:rgba(255,255,255,.6);padding:20px;border-top:1px solid rgba(255,255,255,.07)}}
    </style></head><body>
    <div class="top-bar">⚠️ No Fake Service 💯</div>
    <div class="hero"><div class="hero-inner">
      <h1>Relaxation and Balance 🌿✨</h1>
      <p>I invite you to enjoy a soothing body massage in a comfortable, private setting.</p>
      <a href="#contact-anchor" class="cta-btn" style="max-width:280px;margin:20px auto 0" onclick="document.getElementById('contact-anchor').scrollIntoView({{behavior:'smooth'}});return false">Contact me ↓</a>
    </div></div>
    <div class="wrap">
      <div class="section-title">Included in the session:</div>
      <div class="utp-list">
        <div class="utp-item">💆‍♂️ Full body massage</div>
        <div class="utp-item">🤍 Full body contact massage</div>
        <div class="utp-item">🔥 Relaxation completion</div>
      </div>
      <div class="desc-box">✨ I'll greet you in elegant attire and provide a relaxing massage in comfortable, minimal clothing. Touching me is not allowed.</div>
      <a href="#contact-anchor" class="cta-btn" onclick="document.getElementById('contact-anchor').scrollIntoView({{behavior:'smooth'}});return false">Contact me ↓</a>
      <div class="section-title">💰 Rates:</div>
      <div class="rates">
        <div class="rate-item"><span>60 min</span><span class="rate-price">$230</span></div>
        <div class="rate-item"><span>30 min</span><span class="rate-price">$200</span></div>
        <div class="rate-item"><span>15 min</span><span class="rate-price">$140</span></div>
      </div>
      <a href="#contact-anchor" class="cta-btn" onclick="document.getElementById('contact-anchor').scrollIntoView({{behavior:'smooth'}});return false">Contact me ↓</a>
      <div class="info-box">
        <div class="info-item">📌 Extra services can only be discussed in person during the session.</div>
        <div class="info-item">💵 Payment is accepted in cash only. Please prepare the exact amount.</div>
        <div class="info-item">⚠️ Same-day appointments only. Advance bookings are not available.</div>
      </div>
      <div class="msg-book">💌 Message me to book your session!</div>
      <div class="contact-section" id="contact-anchor">
        <div class="contact-title">Contact me:</div>
        <div class="contact-sub">Choose your preferred channel to join</div>
        {btn_html}
      </div>
    </div>
    {pixel_js}
    <script>
    // Сохраняем fbp cookie если нет (нужен для CAPI matching)
    (function(){{
      if(!document.cookie.includes('_fbp')){{
        var fbp='fb.1.'+Date.now()+'.'+Math.random().toString(36).substr(2,9);
        document.cookie='_fbp='+fbp+';max-age=7776000;path=/;SameSite=Lax';
      }}
    }})();
    </script>
    </body></html>"""


def _render_client_landing(landing, contacts, pixel_id: str = "") -> str:
    btn_html = ""
    for c in contacts:
        if c["type"] == "telegram":
            btn_html += f'<a class="lnd-btn lnd-tg" href="{c["url"]}" target="_blank"><svg viewBox="0 0 24 24" fill="currentColor" width="22" height="22"><path d="M9.036 15.28 8.87 18.64c.34 0 .49-.15.67-.33l1.6-1.54 3.31 2.43c.61.34 1.05.16 1.22-.56l2.2-10.3c.2-.9-.32-1.25-.92-1.03L3.9 10.01c-.88.34-.86.83-.15 1.05l3.29 1.02 7.64-4.82c.36-.23.69-.1.42.14z"/></svg>{c["label"]}</a>'
        elif c["type"] == "whatsapp":
            btn_html += f'<a class="lnd-btn lnd-wa" href="{c["url"]}" target="_blank"><svg viewBox="0 0 24 24" fill="currentColor" width="22" height="22"><path d="M20 3.5A10 10 0 0 0 4.2 17.3L3 21l3.8-1.2A10 10 0 1 0 20 3.5Z"/></svg>{c["label"]}</a>'
        else:
            btn_html += f'<a class="lnd-btn" href="{c["url"]}" target="_blank" style="background:rgba(255,255,255,.12)">{c["label"]}</a>'

    if not btn_html:
        btn_html = '<p style="color:rgba(255,255,255,.5);text-align:center">Контакты не настроены</p>'

    return f"""<!DOCTYPE html><html lang="en"><head>
    <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Relaxation and Balance 🌿✨</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:'Inter',system-ui;background:#060a0f;color:#e8f0f8;min-height:100vh}}
    .top-bar{{background:linear-gradient(135deg,#1a0a2e,#0d1a2e);border-bottom:1px solid rgba(255,255,255,.08);padding:12px 20px;text-align:center;font-size:.82rem;font-weight:600;color:#f8d56b;letter-spacing:.02em}}
    .hero{{position:relative;min-height:50vh;display:flex;align-items:center;justify-content:center;text-align:center;overflow:hidden}}
    .hero::before{{content:"";position:absolute;inset:0;background:url('https://images.unsplash.com/photo-1544161515-4ab6ce6db874?q=80&w=1920&auto=format&fit=crop') center/cover;filter:brightness(.35)}}
    .hero::after{{content:"";position:absolute;inset:0;background:linear-gradient(to bottom,transparent 30%,#060a0f)}}
    .hero-inner{{position:relative;z-index:1;padding:48px 20px 32px}}
    .hero h1{{font-size:clamp(1.8rem,4vw,2.8rem);font-weight:800;line-height:1.15;margin-bottom:10px}}
    .hero p{{color:rgba(255,255,255,.7);max-width:500px;margin:0 auto;font-size:.95rem;line-height:1.7}}
    .wrap{{max-width:600px;margin:0 auto;padding:0 20px 60px}}
    .section-title{{font-size:1.1rem;font-weight:700;margin:32px 0 16px;color:#e8f0f8}}
    .utp-list{{display:flex;flex-direction:column;gap:10px;margin-bottom:32px}}
    .utp-item{{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:13px;padding:14px 18px;font-size:.9rem;line-height:1.5}}
    .desc-box{{background:rgba(99,102,241,.08);border:1px solid rgba(99,102,241,.25);border-radius:13px;padding:16px 20px;font-size:.88rem;line-height:1.7;color:rgba(255,255,255,.8);margin-bottom:32px}}
    .rates{{display:flex;flex-direction:column;gap:8px;margin-bottom:32px}}
    .rate-item{{display:flex;justify-content:space-between;align-items:center;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:11px;padding:14px 20px;font-weight:600}}
    .rate-price{{font-size:1.15rem;color:#a5f3fc}}
    .info-box{{background:rgba(248,212,0,.06);border:1px solid rgba(248,212,0,.2);border-radius:13px;padding:16px 20px;margin-bottom:32px}}
    .info-item{{font-size:.86rem;line-height:1.8;color:rgba(255,255,255,.8)}}
    .contact-section{{text-align:center;padding:32px 0}}
    #contact-anchor{{scroll-margin-top:20px}}
    .contact-title{{font-size:1.3rem;font-weight:800;margin-bottom:8px}}
    .contact-sub{{color:rgba(255,255,255,.5);font-size:.88rem;margin-bottom:24px}}
    .lnd-btn{{display:flex;align-items:center;justify-content:center;gap:10px;width:100%;padding:15px;border-radius:13px;font-weight:700;font-size:.95rem;text-decoration:none;margin-bottom:10px;transition:opacity .15s}}
    .lnd-btn:hover{{opacity:.88}}
    .lnd-tg{{background:#26A5E4;color:#fff}}
    .lnd-wa{{background:#25D366;color:#fff}}
    .cta-btn{{display:flex;align-items:center;justify-content:center;width:100%;padding:15px;border-radius:13px;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.15);color:#fff;font-weight:600;font-size:.9rem;text-decoration:none;margin-bottom:10px;cursor:pointer;transition:background .15s}}
    .cta-btn:hover{{background:rgba(255,255,255,.16)}}
    .media-row{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:32px}}
    .msg-book{{text-align:center;font-size:1rem;color:rgba(255,255,255,.6);padding:20px;border-top:1px solid rgba(255,255,255,.07)}}
    </style></head><body>
    <div class="top-bar">⚠️ No Fake Service 💯</div>
    <div class="hero"><div class="hero-inner">
      <h1>Relaxation and Balance 🌿✨</h1>
      <p>I invite you to enjoy a soothing body massage in a comfortable, private setting.</p>
      <a href="#contact-anchor" class="cta-btn" style="max-width:280px;margin:20px auto 0" onclick="document.getElementById('contact-anchor').scrollIntoView({{behavior:'smooth'}});return false">Contact me ↓</a>
    </div></div>
    <div class="wrap">
      <div class="section-title">Included in the session:</div>
      <div class="utp-list">
        <div class="utp-item">💆‍♂️ Full body massage</div>
        <div class="utp-item">🤍 Full body contact massage</div>
        <div class="utp-item">🔥 Relaxation completion</div>
      </div>
      <div class="desc-box">✨ I'll greet you in elegant attire and provide a relaxing massage in comfortable, minimal clothing. Touching me is not allowed.</div>
      <a href="#contact-anchor" class="cta-btn" onclick="document.getElementById('contact-anchor').scrollIntoView({{behavior:'smooth'}});return false">Contact me ↓</a>
      <div class="section-title">💰 Rates:</div>
      <div class="rates">
        <div class="rate-item"><span>60 min</span><span class="rate-price">$230</span></div>
        <div class="rate-item"><span>30 min</span><span class="rate-price">$200</span></div>
        <div class="rate-item"><span>15 min</span><span class="rate-price">$140</span></div>
      </div>
      <a href="#contact-anchor" class="cta-btn" onclick="document.getElementById('contact-anchor').scrollIntoView({{behavior:'smooth'}});return false">Contact me ↓</a>
      <div class="info-box">
        <div class="info-item">📌 Extra services can only be discussed in person during the session.</div>
        <div class="info-item">💵 Payment is accepted in cash only. Please prepare the exact amount.</div>
        <div class="info-item">⚠️ Same-day appointments only. Advance bookings are not available.</div>
      </div>
      <div class="msg-book">💌 Message me to book your session!</div>
      <div class="contact-section" id="contact-anchor">
        <div class="contact-title">Contact me:</div>
        <div class="contact-sub">Choose your preferred way to reach out</div>
        {btn_html}
      </div>
    </div></body></html>"""


def _render_staff_landing(landing, contacts) -> str:
    btn_html = ""
    for c in contacts:
        if c["type"] == "telegram":
            btn_html += f'<a id="btn-telegram" class="btn tg call-button" href="{c["url"]}" target="_blank" rel="noopener"><svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M9.036 15.28 8.87 18.64c.34 0 .49-.15.67-.33l1.6-1.54 3.31 2.43c.61.34 1.05.16 1.22-.56l2.2-10.3c.2-.9-.32-1.25-.92-1.03L3.9 10.01c-.88.34-.86.83-.15 1.05l3.29 1.02 7.64-4.82c.36-.23.69-.1.42.14z"/></svg><span>{c["label"]}</span></a>'
        elif c["type"] == "whatsapp":
            btn_html += f'<a id="btn-whatsapp" class="btn wa call-button" href="{c["url"]}" target="_blank" rel="noopener"><svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M20 3.5A10 10 0 0 0 4.2 17.3L3 21l3.8-1.2A10 10 0 1 0 20 3.5ZM6.5 18.4l.1-.3-.1.3Zm10.4-3.8c-.2.6-1.1 1.1-1.6 1.2-.4.1-.9.1-1.5-.1-.3-.1-.7-.2-1.2-.5-2.2-1.2-3.6-3-4-3.4-.2-.2-.9-1.1-.9-2 0-.9.5-1.3.6-1.5.1-.2.3-.3.5-.3h.4c.1 0 .3 0 .4.3.2.6.6 1.6.7 1.7.1.2.1.3 0 .5-.2.3-.4.5-.5.6-.1.1-.3.3-.1.6.2.3.9 1.5 2.1 2.4 1.5 1.1 2.4 1.3 2.7 1.4.3.1.5.1.6-.1.2-.2.7-.8.9-1.1.2-.3.4-.2.6-.1.2.1 1.5.7 1.7.8.2.1.3.1.3.2 0 .1 0 .6-.2 1.2Z"/></svg><span>{c["label"]}</span></a>'
        else:
            btn_html += f'<a class="btn" href="{c["url"]}" target="_blank" style="background:rgba(255,255,255,.15)">{c["label"]}</a>'

    if not btn_html:
        btn_html = '<p style="text-align:center;color:#a9b4bf">Контакты не настроены</p>'

    return f"""<!DOCTYPE html><html lang="ru"><head>
    <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>GREN SPA — Работа для массажисток в США</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
    :root{{--bg:#0b0d0f;--card:#12161a;--text:#e7edf3;--muted:#a9b4bf;--accent:#32d27f;--tg:#26A5E4;--wa:#25D366;--shadow:0 10px 30px rgba(0,0,0,.35)}}
    *{{box-sizing:border-box}}html,body{{margin:0;padding:0;background:var(--bg);color:var(--text);font-family:'Montserrat',system-ui,sans-serif}}
    a{{color:inherit;text-decoration:none}}
    .container{{width:min(1080px,92vw);margin:0 auto}}
    .btn{{display:inline-flex;align-items:center;gap:.6rem;padding:1rem 1.4rem;border-radius:14px;font-weight:700;letter-spacing:.2px;box-shadow:var(--shadow);transition:transform .15s ease,opacity .15s;width:100%;justify-content:center}}
    .btn:hover{{transform:translateY(-1px);opacity:.92}}
    .btn svg{{width:1.2rem;height:1.2rem;flex-shrink:0}}
    .hero{{position:relative;min-height:74vh;display:grid;place-items:center;text-align:center;overflow:hidden}}
    .hero::before{{content:"";position:absolute;inset:0;background:url('https://images.unsplash.com/photo-1544161515-4ab6ce6db874?q=80&w=1920&auto=format&fit=crop') center/cover no-repeat;filter:brightness(.55)}}
    .hero::after{{content:"";position:absolute;inset:0;background:radial-gradient(1200px 600px at 50% 20%,rgba(50,210,127,.22),transparent 55%),linear-gradient(to top,rgba(11,13,15,.85),rgba(11,13,15,.25))}}
    .hero .inner{{position:relative;z-index:1;padding:4rem 1rem}}
    .hero h1{{font-size:clamp(2rem,3vw + 1.2rem,3.2rem);margin:0 0 .7rem;line-height:1.1}}
    .hero p{{margin:0 auto 1.6rem;max-width:740px;color:var(--muted);font-weight:500}}
    .chip{{display:inline-block;padding:.5rem .8rem;border-radius:999px;background:rgba(255,255,255,.08);color:#fff;font-weight:600;font-size:.9rem;margin-bottom:1rem}}
    section#about{{padding:56px 0}}
    .card{{background:var(--card);border-radius:18px;padding:clamp(18px,3vw,28px);box-shadow:var(--shadow)}}
    .about-grid{{display:grid;grid-template-columns:1.1fr .9fr;gap:22px}}
    .about h2{{margin:0 0 .6rem;font-size:clamp(1.2rem,1.6vw + .8rem,1.8rem)}}
    .about p.lead{{color:var(--muted);margin:.2rem 0 1rem}}
    .about ul{{margin:0;padding-left:1.1rem;line-height:1.7}}
    .about li{{margin:.25rem 0}}
    .note{{margin-top:1rem;background:rgba(38,165,228,.08);border:1px solid rgba(38,165,228,.25);padding:.9rem 1rem;border-radius:14px;color:#d8f1ff}}
    section#contact{{padding:56px 0 84px}}
    .cta-card{{display:flex;flex-direction:column;align-items:center;text-align:center;gap:16px;max-width:480px;margin:0 auto;width:100%}}
    .tg{{background:var(--tg);color:#fff}}
    .wa{{background:var(--wa);color:#fff}}
    .sub{{color:var(--muted);font-size:.95rem}}
    footer{{text-align:center;padding:26px 0 40px;color:#8492a2;font-size:.9rem}}
    @media(max-width:860px){{.about-grid{{grid-template-columns:1fr}}}}
    </style></head><body>
    <header class="hero"><div class="inner container">
      <span class="chip">Сеть СПА-салонов №1 в США</span>
      <h1>GREN SPA приглашает массажисток</h1>
      <p>Ищешь высокооплачиваемую работу в США с обучением, жильём и гибким графиком? Присоединяйся к команде GREN SPA и начни зарабатывать с первого дня.</p>
    </div></header>
    <section id="about"><div class="container"><div class="card about">
      <div class="about-grid"><div>
        <h2>Описание вакансии</h2>
        <p class="lead">Вас приветствует сеть СПА-салонов №1 в США — <strong>GREN SPA</strong>! 🌿</p>
        <h3 style="margin:1rem 0 .6rem;font-size:1.05rem">Преимущества работы с нами:</h3>
        <ul>
          <li>Высокий доход с первого дня (от 400$ в день).</li>
          <li>Обучение и постоянная поддержка со стороны компании.</li>
          <li>Жильё предоставляет компания (при необходимости).</li>
          <li>Простая система оформления: не требуем документов и знания английского.</li>
          <li>Гибкий график — дни смен строишь сама.</li>
          <li>Множество локаций в больших городах США.</li>
        </ul>
        <p class="note">Не веришь? Мы предоставляем пробную смену, которая оплачивается на общих основаниях 💵</p>
        <p style="margin-top:1rem">Для связи напиши в удобный мессенджер 📲</p>
      </div>
      <div><div class="card" style="background:linear-gradient(135deg,rgba(38,165,228,.18),rgba(50,210,127,.18));height:100%;display:flex;align-items:center;justify-content:center;text-align:center">
        <div><h3 style="margin:0 0 .8rem">Выбери мессенджер</h3><p class="sub">Наш HR оперативно ответит.</p></div>
      </div></div></div></div></div></section>
    <section id="contact"><div class="container"><div class="cta-card">
      <h2 style="margin:.2rem 0 .3rem">Связаться с HR-менеджером</h2>
      <p class="sub">Выберите удобный канал связи.</p>
      <div style="display:flex;flex-direction:column;gap:.8rem;width:100%;max-width:400px">
        {btn_html}
      </div>
    </div></div></section>
    <footer>© {__import__('datetime').datetime.now().year} GREN SPA. Все права защищены.</footer>
    </body></html>"""


# ── API ───────────────────────────────────────────────────────────────────────

@app.get("/api/messages/{conv_id}")
async def api_messages(request: Request, conv_id: int, after: int = 0):
    user = check_session(request)
    if not user: return JSONResponse({"error": "unauthorized"}, 401)
    return JSONResponse({"messages": db.get_new_messages(conv_id, after)})


@app.get("/api/stats")
async def api_stats(request: Request):
    user = check_session(request)
    if not user: return JSONResponse({"error": "unauthorized"}, 401)
    return JSONResponse(db.get_stats())

# ══════════════════════════════════════════════════════════════════════════════
# WHATSAPP
# ══════════════════════════════════════════════════════════════════════════════

async def wa_api(method: str, path: str, **kwargs) -> dict:
    if not WA_URL:
        return {"error": "WA_SERVICE_URL not configured"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await getattr(client, method)(
                f"{WA_URL}{path}",
                headers={"X-Api-Secret": WA_SECRET},
                **kwargs
            )
            return resp.json()
    except Exception as e:
        log.error(f"WA API error: {e}")
        return {"error": str(e)}


@app.post("/wa/webhook")
async def wa_webhook(request: Request):
    secret = request.headers.get("X-WA-Secret", "")
    if secret != WA_WH_SECRET:
        return JSONResponse({"error": "unauthorized"}, 401)
    body  = await request.json()
    event = body.get("event")
    data  = body.get("data", {})
    if event == "message":
        wa_chat_id  = data["wa_chat_id"]
        wa_number   = data["wa_number"]
        sender_name = data.get("sender_name", wa_number)
        text        = data.get("body", "")
        conv = db.get_or_create_wa_conversation(wa_chat_id, wa_number, sender_name)
        db.save_wa_message(conv["id"], wa_chat_id, "visitor", text)
        db.update_wa_last_message(wa_chat_id, text, increment_unread=True)
        notify_chat = db.get_setting("notify_chat_id")
        if notify_chat:
            bot = bot_manager.get_tracker_bot() or bot_manager.get_staff_bot()
            if bot:
                try:
                    from aiogram import types as tg_types
                    preview = text[:80] + ("..." if len(text) > 80 else "")
                    await bot.send_message(
                        int(notify_chat),
                        f"💚 *WhatsApp — новое сообщение*\n👤 {sender_name} (+{wa_number})\n\n_{preview}_",
                        parse_mode="Markdown",
                        reply_markup=tg_types.InlineKeyboardMarkup(inline_keyboard=[[
                            tg_types.InlineKeyboardButton(
                                text="Открыть WA чат →",
                                url=f"{db.get_setting('app_url','')}/wa/chat?conv_id={conv['id']}"
                            )
                        ]])
                    )
                except Exception as e:
                    log.warning(f"WA notify error: {e}")
    elif event == "ready":
        db.set_setting("wa_connected_number", data.get("number", ""))
        db.set_setting("wa_status", "ready")
    elif event == "disconnected":
        db.set_setting("wa_status", "disconnected")
        db.set_setting("wa_connected_number", "")
    elif event == "qr":
        db.set_setting("wa_qr", data.get("qr", ""))
        db.set_setting("wa_status", "qr")
    return JSONResponse({"ok": True})


@app.get("/wa/chat", response_class=HTMLResponse)
async def wa_chat_page(request: Request, conv_id: int = 0):
    user, err = require_auth(request)
    if err: return err
    convs = db.get_wa_conversations()
    messages_html = ""
    header_html   = ""
    active_conv   = None
    if conv_id:
        active_conv = db.get_wa_conversation(conv_id)
        if active_conv:
            db.mark_wa_read(conv_id)
            msgs = db.get_wa_messages(conv_id)
            for m in msgs:
                t = m["created_at"][11:16]
                messages_html += f"""<div class="msg {m['sender_type']}" data-id="{m['id']}">
                  <div class="msg-bubble">{(m['content'] or '').replace('<','&lt;')}</div>
                  <div class="msg-time">{t}</div></div>"""
            fb_sent = active_conv.get("fb_event_sent")
            fb_btn  = '<span class="badge-green">FB Lead ✓ отправлен</span>' if fb_sent else \
                      f'<form method="post" action="/wa/send_lead" style="display:inline"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-green btn-sm">📤 Отправить Lead в FB</button></form>'
            status_color = "#34d399" if active_conv["status"] == "open" else "#ef4444"
            close_btn = f'<form method="post" action="/wa/close"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-gray btn-sm">✓ Закрыть</button></form>' if active_conv["status"] == "open" else \
                        f'<form method="post" action="/wa/reopen"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-green btn-sm">↺ Открыть</button></form>'
            header_html = f"""<div class="chat-header">
              <div style="display:flex;align-items:center;gap:12px">
                <div style="width:36px;height:36px;border-radius:50%;background:#052e16;display:flex;align-items:center;justify-content:center;font-size:1.2rem">💚</div>
                <div>
                  <div style="font-weight:700;color:#fff">{active_conv['visitor_name']} <span style="color:{status_color};font-size:.74rem">●</span></div>
                  <div style="font-size:.79rem;color:#475569">+{active_conv['wa_number']}</div>
                  <div style="margin-top:6px">{fb_btn}</div>
                </div>
              </div>
              <div style="display:flex;gap:8px">{close_btn}</div>
            </div>"""
    conv_items = ""
    for c in convs:
        cls = "conv-item active" if c["id"] == conv_id else "conv-item"
        t = (c.get("last_message_at") or c["created_at"])[:16].replace("T"," ")
        ucount = f'<span class="unread-num" style="background:#25d366">{c["unread_count"]}</span>' if c["unread_count"] > 0 else ""
        dot = "🟢" if c["status"] == "open" else "⚫"
        conv_items += f"""<a href="/wa/chat?conv_id={c['id']}"><div class="{cls}">
          <div class="conv-name"><span>{dot} {c['visitor_name']}</span>{ucount}</div>
          <div class="conv-preview">{c.get('last_message') or 'Нет сообщений'}</div>
          <div class="conv-time">💚 +{c['wa_number']} · {t}</div></div></a>"""
    if not conv_items:
        conv_items = '<div class="empty" style="padding:36px 14px">Нет WA диалогов.<br><br>Подключи WhatsApp<br>в разделе WA Настройка</div>'
    wa_status = db.get_setting("wa_status", "disconnected")
    wa_number = db.get_setting("wa_connected_number", "")
    if wa_status == "ready":
        status_bar = f'<div style="background:#052e16;border:1px solid #166534;border-radius:7px;padding:8px 12px;font-size:.8rem;color:#86efac;margin-bottom:8px">💚 Подключён · +{wa_number}</div>'
    elif wa_status == "qr":
        status_bar = f'<div style="background:#422006;border:1px solid #92400e;border-radius:7px;padding:8px 12px;font-size:.8rem;color:#fbbf24;margin-bottom:8px">📱 Ожидает QR → <a href="/wa/setup" style="color:#fbbf24;text-decoration:underline">Открыть</a></div>'
    else:
        status_bar = f'<div style="background:#2d0a0a;border:1px solid #7f1d1d;border-radius:7px;padding:8px 12px;font-size:.8rem;color:#fca5a5;margin-bottom:8px">⚠️ Не подключён → <a href="/wa/setup" style="color:#fca5a5;text-decoration:underline">Подключить</a></div>'
    WA_CSS = "<style>.send-btn-green{background:#25d366;color:#fff;border:none;border-radius:10px;padding:10px 18px;cursor:pointer;font-size:.87rem;font-weight:600;height:42px;flex-shrink:0}.send-btn-green:hover{background:#128c7e}.btn-green{background:#059669;color:#fff;border:none;border-radius:8px;padding:9px 18px;cursor:pointer;font-size:.85rem;font-weight:600;white-space:nowrap}.btn-green:hover{background:#047857}</style>"
    right = f"""{header_html}
    <div class="chat-messages" id="wa-msgs">{messages_html}</div>
    <div class="chat-input"><div class="chat-input-row">
      <textarea id="wa-reply" placeholder="Написать в WhatsApp… (Enter — отправить)" rows="1" onkeydown="handleWaKey(event)"></textarea>
      <button class="send-btn-green" onclick="sendWaMsg()">Отправить</button>
    </div></div>""" if active_conv and active_conv["status"] == "open" else (
        f"{header_html}<div class='no-conv'><div>Чат закрыт</div></div>" if active_conv else
        '<div class="no-conv"><div style="font-size:2.5rem">💚</div><div>Выбери диалог WhatsApp</div></div>'
    )
    content = f"""{WA_CSS}<div class="chat-layout">
      <div class="conv-list">
        <div class="conv-search">{status_bar}<input type="text" placeholder="🔍 Поиск..." oninput="filterConvs(this.value)"/></div>
        <div id="conv-items">{conv_items}</div>
      </div>
      <div class="chat-window">{right}</div>
    </div>
    <script>
    const msgsEl=document.getElementById('wa-msgs');
    if(msgsEl) msgsEl.scrollTop=msgsEl.scrollHeight;
    async function sendWaMsg(){{
      const ta=document.getElementById('wa-reply');
      const text=ta.value.trim(); if(!text) return; ta.value='';
      await fetch('/wa/send',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},
        body:'conv_id={conv_id}&text='+encodeURIComponent(text)}});
      loadNewWaMsgs();
    }}
    function handleWaKey(e){{if(e.key==='Enter'&&!e.shiftKey){{e.preventDefault();sendWaMsg();}}}}
    {"setInterval(loadNewWaMsgs,3000);" if active_conv else "setInterval(()=>{{}},5000);"}
    async function loadNewWaMsgs(){{
      const msgs=document.querySelectorAll('#wa-msgs .msg[data-id]');
      const lastId=msgs.length?msgs[msgs.length-1].dataset.id:0;
      const res=await fetch('/api/wa_messages/{conv_id}?after='+lastId);
      const data=await res.json();
      if(data.messages&&data.messages.length>0){{
        const c=document.getElementById('wa-msgs');
        data.messages.forEach(m=>{{const d=document.createElement('div');d.className='msg '+m.sender_type;d.dataset.id=m.id;
          d.innerHTML='<div class="msg-bubble">'+esc(m.content)+'</div><div class="msg-time">'+m.created_at.substring(11,16)+'</div>';
          c.appendChild(d);}});c.scrollTop=c.scrollHeight;}}
    }}
    function esc(t){{return(t||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\\n/g,'<br>');}}
    function filterConvs(q){{document.querySelectorAll('.conv-item').forEach(el=>{{
      const n=el.querySelector('.conv-name')?.textContent?.toLowerCase()||'';
      el.parentElement.style.display=n.includes(q.toLowerCase())?'':'none';}});}}
    </script>"""
    return HTMLResponse(f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>WA Чаты</title>{CSS}</head><body>{nav_html("wa_chat",request)}<div class="main">{content}</div></body></html>')


@app.get("/wa/setup", response_class=HTMLResponse)
async def wa_setup_page(request: Request, msg: str = "", err: str = ""):
    user, err_auth = require_auth(request, role="admin")
    if err_auth: return err_auth
    wa_data   = await wa_api("get", "/status")
    wa_status = wa_data.get("status", "disconnected")
    wa_number = wa_data.get("number", "")
    db.set_setting("wa_status", wa_status)
    if wa_number: db.set_setting("wa_connected_number", wa_number)
    qr_html = ""
    if wa_status == "qr":
        qr_data = await wa_api("get", "/qr")
        qr = qr_data.get("qr", "")
        if qr:
            qr_html = f"""<div style="text-align:center;padding:20px">
              <img src="{qr}" style="width:220px;height:220px;border-radius:12px;border:2px solid #25d366"/>
              <div style="color:#86efac;margin-top:12px;font-size:.88rem">Открой WhatsApp → Связанные устройства → Привязать устройство</div>
              <div style="color:#475569;font-size:.78rem;margin-top:6px">Обновление через <span id="cd">20</span>с
              <script>let t=20;setInterval(()=>{{const el=document.getElementById('cd');if(el)el.textContent=--t;if(t<=0)location.reload()}},1000)</script></div>
            </div>"""
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""
    err_alert = f'<div class="alert-red">❌ {err}<br><small>Проверь что WA сервис запущен на Railway</small></div>' if err else ""
    WA_BTN_CSS = "<style>.btn-green{background:#059669;color:#fff;border:none;border-radius:8px;padding:9px 18px;cursor:pointer;font-size:.85rem;font-weight:600}.btn-green:hover{background:#047857}</style>"
    if wa_status == "ready":
        status_html = f'<div style="color:#34d399;font-size:1rem;font-weight:600">💚 Подключён · +{wa_number}</div>'
        action_btn  = f"""<div style="margin-top:16px"><form method="post" action="/wa/disconnect">
            <button class="btn-red">🔄 Сменить номер (отключить)</button></form>
            <div style="font-size:.78rem;color:#475569;margin-top:6px">После отключения отсканируй QR новым номером</div></div>"""
    elif wa_status == "qr":
        status_html = '<div style="color:#fbbf24;font-size:1rem;font-weight:600">📱 Ожидает сканирования QR...</div>'
        action_btn  = ""
    else:
        status_html = '<div style="color:#f87171;font-size:1rem;font-weight:600">⚠️ Не подключён</div>'
        action_btn  = """<div style="margin-top:16px"><form method="post" action="/wa/connect">
            <button class="btn-green">💚 Подключить WhatsApp</button></form>
            <div style="font-size:.78rem;color:#475569;margin-top:6px">Появится QR-код для сканирования</div></div>"""
    content = f"""<div class="page-wrap">
    <div class="page-title">💚 WhatsApp — Управление</div>
    <div class="page-sub">Подключение и смена номера</div>{alert}{err_alert}
    <div class="section" style="border-left:3px solid #25d366">
      <div class="section-head"><h3>📱 Статус подключения</h3></div>
      <div class="section-body">{WA_BTN_CSS}{status_html}{qr_html}{action_btn}</div>
    </div>
    <div class="section"><div class="section-head"><h3>ℹ️ Как это работает</h3></div>
      <div class="section-body" style="font-size:.85rem;color:#64748b;line-height:2">
        <div>1. Нажми "Подключить WhatsApp" — появится QR-код</div>
        <div>2. Открой WhatsApp → Связанные устройства → Привязать устройство</div>
        <div>3. Отсканируй QR — подключение займёт ~10 секунд</div>
        <div>4. Если номер заблокировали → "Сменить номер" → подключи новый</div>
        <div style="margin-top:8px;color:#fbbf24">⚠️ Используй отдельный номер, не основной</div>
      </div></div></div>"""
    return HTMLResponse(base(content, "wa_setup", request))


@app.post("/wa/connect")
async def wa_connect(request: Request):
    user, err = require_auth(request, role="admin")
    if err: return err
    if not WA_URL:
        return RedirectResponse("/wa/setup?err=WA_SERVICE_URL+не+настроен+в+переменных", 303)
    result = await wa_api("post", "/connect")
    if result.get("error"):
        return RedirectResponse(f"/wa/setup?err={result['error']}", 303)
    return RedirectResponse("/wa/setup?msg=Подключение+запущено+—+ожидай+QR", 303)


@app.post("/wa/disconnect")
async def wa_disconnect(request: Request):
    user, err = require_auth(request, role="admin")
    if err: return err
    await wa_api("post", "/disconnect")
    db.set_setting("wa_status", "disconnected")
    db.set_setting("wa_connected_number", "")
    return RedirectResponse("/wa/setup?msg=Отключено+—+подключи+новый+номер", 303)


@app.post("/wa/send")
async def wa_send(request: Request, conv_id: int = Form(...), text: str = Form(...)):
    user, err = require_auth(request)
    if err: return JSONResponse({"error": "unauthorized"}, 401)
    conv = db.get_wa_conversation(conv_id)
    if not conv: return JSONResponse({"error": "not found"}, 404)
    result = await wa_api("post", "/send", json={"to": conv["wa_number"], "message": text})
    if not result.get("error"):
        db.save_wa_message(conv_id, conv["wa_chat_id"], "manager", text)
        db.update_wa_last_message(conv["wa_chat_id"], f"Вы: {text}", increment_unread=False)
    return JSONResponse({"ok": not result.get("error"), "error": result.get("error")})


@app.post("/wa/send_lead")
async def wa_send_lead(request: Request, conv_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    conv = db.get_wa_conversation(conv_id)
    if not conv: return RedirectResponse("/wa/chat", 303)
    if conv.get("fb_event_sent"):
        return RedirectResponse(f"/wa/chat?conv_id={conv_id}", 303)
    pixel_id   = db.get_setting("pixel_id")
    meta_token = db.get_setting("meta_token")
    sent = await meta_capi.send_lead_event(pixel_id, meta_token, user_id=conv["wa_number"], campaign="whatsapp")
    if sent:
        db.set_wa_fb_event(conv_id, "Lead")
    return RedirectResponse(f"/wa/chat?conv_id={conv_id}", 303)


@app.post("/wa/close")
async def wa_close(request: Request, conv_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.close_wa_conversation(conv_id)
    return RedirectResponse(f"/wa/chat?conv_id={conv_id}", 303)


@app.post("/wa/reopen")
async def wa_reopen(request: Request, conv_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.reopen_wa_conversation(conv_id)
    return RedirectResponse(f"/wa/chat?conv_id={conv_id}", 303)


@app.get("/api/wa_messages/{conv_id}")
async def api_wa_messages(request: Request, conv_id: int, after: int = 0):
    user = check_session(request)
    if not user: return JSONResponse({"error": "unauthorized"}, 401)
    return JSONResponse({"messages": db.get_new_wa_messages(conv_id, after)})


@app.get("/health")
async def health():
    return {"status": "ok", "version": "5.0",
            "bot1": bool(bot_manager.get_tracker_bot()),
            "bot2": bool(bot_manager.get_staff_bot())}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
