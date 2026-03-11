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
.chart-bar{width:100%;border-radius:3px 3px 0 0;min-height:2px;transition:height .3s}
.chart-bar.blue{background:#3b82f6}
.chart-bar.orange{background:#f97316}
.chart-label{font-size:.6rem;color:#334155;margin-top:3px;transform:rotate(-45deg);transform-origin:top right;white-space:nowrap}
</style>"""



NOTIFY_JS = """<script>
// ═══════════════════════════════════════════
//  GLOBAL NOTIFICATION SYSTEM
// ═══════════════════════════════════════════
const _notifySnap = {};
let _notifyFirst = true;
let _audioCtx = null;

function _getAudioCtx() {
  if (!_audioCtx) _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  return _audioCtx;
}

window.playNotifySound = function(type) {
  try {
    const ctx = _getAudioCtx();
    const freqs = type === 'wa' ? [660, 880] : [880, 1100];
    freqs.forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain); gain.connect(ctx.destination);
      osc.frequency.value = freq;
      osc.type = 'sine';
      const t = ctx.currentTime + i * 0.13;
      gain.gain.setValueAtTime(0, t);
      gain.gain.linearRampToValueAtTime(0.25, t + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.001, t + 0.4);
      osc.start(t); osc.stop(t + 0.4);
    });
  } catch(e) {}
};

window.showToast = function(title, body, type) {
  type = type || 'tg';
  const color = type === 'wa' ? '#25d366' : '#3b82f6';
  const icon  = type === 'wa' ? '💚' : '💬';
  if (!document.getElementById('_notify_style')) {
    const s = document.createElement('style');
    s.id = '_notify_style';
    s.textContent = `@keyframes _slideIn{from{transform:translateX(120%);opacity:0}to{transform:translateX(0);opacity:1}}
      @keyframes _fadeOut{to{opacity:0;transform:translateX(120%)}}
      ._toast{position:fixed;right:24px;z-index:99999;background:#1e2a3a;border-radius:12px;
        padding:14px 18px;min-width:260px;max-width:340px;box-shadow:0 8px 32px rgba(0,0,0,.5);
        cursor:pointer;animation:_slideIn .3s ease;font-family:system-ui;transition:bottom .2s}`;
    document.head.appendChild(s);
  }
  // Stack existing toasts up
  document.querySelectorAll('._toast').forEach((t, i) => {
    t.style.bottom = (24 + (i + 1) * 82) + 'px';
  });
  const el = document.createElement('div');
  el.className = '_toast';
  el.style.cssText = `border:1px solid ${color};border-left:4px solid ${color};bottom:24px`;
  el.innerHTML = `<div style="font-size:.72rem;color:${color};font-weight:700;letter-spacing:.05em;margin-bottom:5px">${icon} ${title.toUpperCase()}</div>
    <div style="font-size:.85rem;color:#e2e8f0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:300px">${body}</div>`;
  el.onclick = () => { el.style.animation='_fadeOut .25s ease forwards'; setTimeout(()=>el.remove(),250); };
  document.body.appendChild(el);
  setTimeout(() => { if(el.parentNode){el.style.animation='_fadeOut .25s ease forwards';setTimeout(()=>el.remove(),250);} }, 6000);
  // Browser notification
  if (Notification.permission === 'granted') {
    try { new Notification(title, {body: body.substring(0,80), tag: 'tgtracker'}); } catch(e) {}
  }
};

function _notifyCheck(convs, type) {
  let totalUnread = 0;
  convs.forEach(c => {
    totalUnread += c.unread_count || 0;
    const key = type + '_' + c.id;
    const prev = _notifySnap[key];
    if (!_notifyFirst && prev !== undefined && c.unread_count > prev && c.last_message) {
      playNotifySound(type);
      const name = c.visitor_name || (type === 'wa' ? 'WhatsApp' : 'Telegram');
      showToast(name, c.last_message, type);
    }
    _notifySnap[key] = c.unread_count;
  });
  return totalUnread;
}

// Update browser tab title with unread count
function _updateTabTitle(total) {
  const base = document.title.replace(/^[(][0-9]+[)] */, '');
  document.title = total > 0 ? '(' + total + ') ' + base : base;
}

// Global poll — runs on ALL pages every 5s
async function _globalNotifyPoll() {
  try {
    const [tg, wa] = await Promise.all([
      fetch('/api/conversations').then(r=>r.json()).catch(()=>({conversations:[]})),
      fetch('/api/wa_conversations').then(r=>r.json()).catch(()=>({conversations:[]}))
    ]);
    const t1 = _notifyCheck(tg.conversations || [], 'tg');
    const t2 = _notifyCheck(wa.conversations || [], 'wa');
    _updateTabTitle(t1 + t2);
    _notifyFirst = false;
  } catch(e) {}
}

// Init: request permission then start polling
(async function() {
  if (typeof Notification !== 'undefined' && Notification.permission === 'default') {
    await Notification.requestPermission();
  }
  await _globalNotifyPoll(); // baseline snapshot (no alerts, just sets _notifySnap)
  setInterval(_globalNotifyPoll, 5000);
})();
</script>"""


def nav_html(active: str, request: Request) -> str:
    user = check_session(request)
    stats = db.get_stats()
    unread = stats.get("unread", 0)
    b1 = bot_manager.get_tracker_bot()
    b2 = bot_manager.get_staff_bot()
    b1_name = db.get_setting("bot1_name", "Бот трекер")
    b2_name = db.get_setting("bot2_name", "Бот сотрудники")
    role = user["role"] if user else "manager"

    def item(icon, label, page, section_color="blue", badge=False):
        cls = f"nav-item active {section_color}" if page == active else "nav-item"
        bdg = f'<span class="badge-count">{unread}</span>' if badge and unread > 0 else ""
        return f'<a href="/{page}"><div class="{cls}"><span class="nav-label">{icon} {label}</span>{bdg}</div></a>'

    admin_section = ""
    if role == "admin":
        admin_section = f"""
        <div class="nav-divider"></div>
        {item("🔐", "Пользователи", "users", "blue")}
        {item("⚙️", "Настройки", "settings", "blue")}"""

    return f"""
    <div class="sidebar">
      <div class="logo">
        <div>📡 TG<span>Tracker</span></div>
        <div class="logo-user">{user['username'] if user else ''}</div>
      </div>
      {item("📊", "Обзор", "overview", "blue")}
      {item("📈", "Статистика", "analytics", "blue")}
      <div class="nav-divider"></div>
      <div class="nav-section">👥 Клиенты</div>
      {item("📡", "Каналы", "channels", "blue")}
      {item("🔗", "Кампании", "campaigns", "blue")}
      {item("🌐", "Лендинг", "landing", "blue")}
      <div class="nav-divider"></div>
      <div class="nav-section">👔 Сотрудники</div>
      {item("💬", "TG Чаты", "chat", "orange", badge=True)}
      {item("💚", "WA Чаты", "wa/chat", "orange")}
      {item("🗂", "База", "staff", "orange")}
      {item("🌐", "Лендинг HR", "staff/landing", "orange")}
      {admin_section}
      <div class="sidebar-footer">
        <div class="bot-status"><div class="dot {'dot-green' if b1 else 'dot-red'}"></div><span>{b1_name}</span></div>
        <div class="bot-status"><div class="dot {'dot-green' if b2 else 'dot-red'}"></div><span>{b2_name}</span></div>
        <a href="/logout"><div style="padding:8px 10px;font-size:.76rem;color:#475569;cursor:pointer">⬅ Выйти</div></a>
      </div>
    </div>"""


def base(content: str, active: str, request: Request) -> str:
    return f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>TG Tracker</title>{CSS}</head><body>{nav_html(active, request)}<div class="main">{content}</div>{NOTIFY_JS}</body></html>'


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
    Страница редиректа с трекингом UTM и fbclid.
    Использование: /go?to=https://t.me/+xxx&utm_source=fb&utm_campaign=march&fbclid=xxx
    """
    if not to:
        return HTMLResponse("<h2>Ссылка не указана</h2>", 400)

    # fbp из куки если не передан
    cookie_fbp = request.cookies.get("_fbp") or fbp

    # Сохраняем клик
    click_id = db.save_click(
        fbclid=fbclid,
        fbp=cookie_fbp,
        utm_source=utm_source,
        utm_medium=utm_medium,
        utm_campaign=utm_campaign,
        utm_content=utm_content,
        utm_term=utm_term,
        referrer=request.headers.get("referer"),
        target_type="channel",
        target_id=to,
        user_agent=request.headers.get("user-agent", "")[:255],
        ip_address=request.client.host if request.client else None,
    )
    log.info(f"[/go] click_id={click_id} fbclid={fbclid} utm={utm_campaign} → {to[:60]}")

    # Добавляем ref_ параметр в Telegram ссылку
    destination = to
    if "t.me" in to:
        sep = "&" if "?" in to else "?"
        destination = f"{to}{sep}start=ref_{click_id}"

    # Промежуточная страница для сохранения fbp куки
    return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <meta http-equiv="refresh" content="0;url={destination}">
    <script>
      // Сохраняем fbp если есть
      if (document.cookie.indexOf('_fbp') === -1) {{
        const fbp = 'fb.1.' + Date.now() + '.' + Math.random().toString(36).substr(2,9);
        document.cookie = '_fbp=' + fbp + ';max-age=7776000;path=/;SameSite=Lax';
      }}
      setTimeout(function(){{ window.location.href = '{destination}'; }}, 100);
    </script>
    </head><body style="background:#0a0d14;color:#e2e8f0;display:flex;align-items:center;justify-content:center;min-height:100vh;font-family:system-ui">
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

@app.get("/analytics", response_class=HTMLResponse)
async def analytics(request: Request):
    user, err = require_auth(request)
    if err: return err

    joins_by_day  = db.get_joins_by_day(30)
    staff_by_day  = db.get_staff_by_day(30)
    campaign_stats = db.get_campaign_stats()
    click_stats   = db.get_click_stats(30)
    funnel        = db.get_staff_funnel()

    # WA статистика
    wa_convs      = db.get_wa_conversations()
    wa_total      = len(wa_convs)
    wa_open       = sum(1 for c in wa_convs if c.get("status") == "open")
    wa_closed     = wa_total - wa_open
    wa_unread     = sum(c.get("unread_count", 0) for c in wa_convs)
    wa_fb_sent    = sum(1 for c in wa_convs if c.get("fb_event_sent"))

    # WA таблица (вынесена из f-string чтобы избежать SyntaxError в Python 3.11)
    if wa_convs:
        wa_rows = ""
        for c in wa_convs[:20]:
            badge_cls = "badge-green" if c["status"] == "open" else "badge-gray"
            status_lbl = "🟢 Открыт" if c["status"] == "open" else "⚫ Закрыт"
            fb_badge = "<span class='badge-green'>✓ FB</span>" if c.get("fb_event_sent") else "—"
            preview = (c.get("last_message") or "—")[:60]
            date = (c.get("last_message_at") or c["created_at"])[:10]
            wa_rows += f"""<tr>
              <td style="font-weight:600;color:#fff">{c["visitor_name"]}</td>
              <td style="color:#25d366">+{c["wa_number"]}</td>
              <td><span class="{badge_cls}">{status_lbl}</span></td>
              <td style="max-width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#64748b">{preview}</td>
              <td>{fb_badge}</td>
              <td>{date}</td></tr>"""
        wa_table_html = f"""<div class="section">
          <div class="section-head"><h3>💚 Последние WA диалоги</h3></div>
          <table><thead><tr><th>Контакт</th><th>Номер</th><th>Статус</th><th>Последнее сообщение</th><th>FB Lead</th><th>Дата</th></tr></thead>
          <tbody>{wa_rows}</tbody></table></div>"""
    else:
        wa_table_html = '<div class="section"><div class="section-body"><div class="empty">Нет WA диалогов — подключи WhatsApp в разделе WA Настройка</div></div></div>'

    # Строим chart HTML
    def bar_chart(data, key, color, label):
        if not data: return '<div class="empty">Нет данных</div>'
        max_val = max((d[key] for d in data), default=1) or 1
        bars = ""
        for d in data[-20:]:
            h = max(4, int(d[key] / max_val * 140))
            day = d["day"][-5:] if d.get("day") else ""
            bars += f'<div class="chart-bar-wrap"><div class="chart-bar {color}" style="height:{h}px" title="{d[key]}"></div><div class="chart-label">{day}</div></div>'
        return f'<div class="chart-wrap">{bars}</div><div style="font-size:.75rem;color:#475569;margin-top:8px">{label} (последние 30 дней)</div>'

    # Кампании таблица
    camp_rows = "".join(f"""<tr>
        <td><span class="badge">{c['campaign_name']}</span></td>
        <td style="font-weight:700;color:#60a5fa">{c['joins']}</td>
        <td>{c['first_join'][:10] if c.get('first_join') else '—'}</td>
        <td>{c['last_join'][:10] if c.get('last_join') else '—'}</td>
    </tr>""" for c in campaign_stats) or '<tr><td colspan="4"><div class="empty">Нет данных</div></td></tr>'

    fn_steps = [("new","🆕 Новых"),("review","👀 Смотрим"),("interview","🎙 Интервью"),("hired","✅ Принят"),("rejected","❌ Отказ")]
    funnel_html = "".join(f"""<div class="funnel-step">
        <div class="fn" style="color:{'#34d399' if s=='hired' else '#f87171' if s=='rejected' else '#60a5fa'}">{funnel.get(s,0)}</div>
        <div class="fl">{l}</div></div>""" for s,l in fn_steps)

    content = f"""<div class="page-wrap">
    <div class="page-title">📈 Статистика</div>
    <div class="page-sub">Графики и аналитика</div>

    <div class="section">
      <div class="section-head"><h3>📡 Подписки по дням (Клиенты)</h3></div>
      <div class="section-body">{bar_chart(joins_by_day, 'cnt', 'blue', 'Подписок в день')}</div>
    </div>

    <div class="section">
      <div class="section-head"><h3>🎯 Клики /go по дням</h3></div>
      <div class="section-body">{bar_chart(click_stats, 'clicks', 'blue', 'Кликов в день')}</div>
    </div>

    <div class="section">
      <div class="section-head"><h3>👔 Новые сотрудники по дням</h3></div>
      <div class="section-body">{bar_chart(staff_by_day, 'cnt', 'orange', 'Сотрудников в день')}</div>
    </div>

    <div style="font-size:.76rem;font-weight:700;color:#f97316;text-transform:uppercase;letter-spacing:.08em;margin:18px 0 10px">Воронка сотрудников</div>
    <div class="funnel">{funnel_html}</div>

    <div style="font-size:.76rem;font-weight:700;color:#25d366;text-transform:uppercase;letter-spacing:.08em;margin:18px 0 10px">💚 WhatsApp — Статистика</div>
    <div class="cards" style="margin-bottom:18px">
      <div class="card"><div class="val green">{wa_total}</div><div class="lbl">Всего WA диалогов</div></div>
      <div class="card"><div class="val green">{wa_open}</div><div class="lbl">Открытых</div></div>
      <div class="card"><div class="val" style="color:#64748b">{wa_closed}</div><div class="lbl">Закрытых</div></div>
      <div class="card"><div class="val orange">{wa_unread}</div><div class="lbl">Непрочитанных</div></div>
      <div class="card"><div class="val green">{wa_fb_sent}</div><div class="lbl">FB Lead отправлен</div></div>
    </div>

    {wa_table_html}

    <div class="section">
      <div class="section-head"><h3>🔗 Кампании по подпискам</h3></div>
      <table><thead><tr><th>Кампания</th><th>Подписчиков</th><th>Первая</th><th>Последняя</th></tr></thead>
      <tbody>{camp_rows}</tbody></table>
    </div></div>"""
    return HTMLResponse(base(content, "analytics", request))


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
    active_name = ""

    if conv_id:
        active_conv = db.get_conversation(conv_id)
        if active_conv:
            db.mark_conversation_read(conv_id)
            msgs = db.get_messages(conv_id)
            staff = db.get_staff_by_conv(conv_id)
            utm = db.get_utm_by_conv(conv_id)
            for m in msgs:
                t = m["created_at"][11:16]
                messages_html += f"""<div class="msg {m['sender_type']}" data-id="{m['id']}">
                  <div class="msg-bubble">{(m['content'] or '').replace('<','&lt;')}</div>
                  <div class="msg-time">{t}</div></div>"""

            active_name = (active_conv.get('visitor_name') or '').replace('"','')
            uname = f"@{active_conv['username']}" if active_conv.get('username') else active_conv.get('tg_chat_id','')
            status_color = "#34d399" if active_conv["status"] == "open" else "#ef4444"

            # UTM теги
            utm_tags = ""
            if utm:
                tags = []
                if utm.get("utm_source"):   tags.append(f"src:{utm['utm_source']}")
                if utm.get("utm_campaign"): tags.append(f"camp:{utm['utm_campaign']}")
                if utm.get("fbclid"):       tags.append("fbclid ✓")
                if tags:
                    utm_tags = '<div class="utm-row">' + "".join(f'<span class="utm-tag">{t}</span>' for t in tags) + '</div>'

            # Карточка сотрудника
            staff_info = ""
            fb_sent = ""
            if staff:
                icon, label, badge_cls = STAFF_STATUSES.get(staff.get("status","new"), ("🆕","Новый","badge-gray"))
                fb_sent = f'<span class="badge-green" style="font-size:.72rem">FB Lead ✓</span>' if staff.get("fb_event_sent") else ""
                staff_info = f"""<div style="font-size:.79rem;color:#64748b;margin-top:4px">
                  <span class="{badge_cls}">{icon} {label}</span>
                  {f' · {staff["position"]}' if staff.get("position") else ''}
                  {f' · 📞 {staff["phone"]}' if staff.get("phone") else ''}
                  {fb_sent}
                  <a href="/staff?edit={staff['id']}" style="color:#f97316;margin-left:8px">Карточка →</a>
                </div>"""

            close_btn = f'<form method="post" action="/chat/close"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-gray btn-sm">✓ Закрыть</button></form>' if active_conv["status"] == "open" else f'<form method="post" action="/chat/reopen"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-orange btn-sm">↺ Открыть</button></form>'
            header_html = f"""<div class="chat-header">
              <div style="display:flex;align-items:flex-start;gap:12px">
                <div class="avatar">{active_conv['visitor_name'][0].upper()}</div>
                <div>
                  <div style="font-weight:700;color:#fff">{active_conv['visitor_name']} <span style="color:{status_color};font-size:.74rem">●</span></div>
                  <div style="font-size:.79rem;color:#475569">{uname}</div>
                  {staff_info}
                  {utm_tags}
                </div>
              </div>
              <div style="display:flex;gap:8px;flex-shrink:0">{close_btn}</div>
            </div>"""

    conv_items = ""
    for c in convs:
        cls = "conv-item active" if c["id"] == conv_id else "conv-item"
        t = (c.get("last_message_at") or c["created_at"])[:16].replace("T"," ")
        ucount = f'<span class="unread-num">{c["unread_count"]}</span>' if c["unread_count"] > 0 else ""
        dot = "🟢" if c["status"] == "open" else "⚫"
        conv_items += f"""<a href="/chat?conv_id={c['id']}"><div class="{cls}">
          <div class="conv-name"><span>{dot} {c['visitor_name']}</span>{ucount}</div>
          <div class="conv-preview">{c.get('last_message') or 'Нет сообщений'}</div>
          <div class="conv-time">{t}</div></div></a>"""

    if not conv_items:
        conv_items = '<div class="empty" style="padding:36px 14px">Диалогов пока нет</div>'

    b2 = bot_manager.get_staff_bot()
    bot_warn = "" if b2 else '<div style="background:#431407;border:1px solid #7c2d12;border-radius:7px;padding:9px 12px;font-size:.8rem;color:#fb923c;margin-bottom:8px">⚠️ Бот не запущен — <a href="/settings" style="color:#fb923c;text-decoration:underline">Настройки</a></div>'

    right = f"""{header_html}
    <div class="chat-messages" id="msgs">{messages_html}</div>
    <div class="chat-input"><div class="chat-input-row">
      <textarea id="reply-text" placeholder="Ответить сотруднику… (Enter — отправить)" rows="1" onkeydown="handleKey(event)"></textarea>
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
    const ACTIVE_ID={conv_id};
    const ACTIVE_NAME="{active_name}";
    let _snap={{}};
    let _firstMsgLoad=true;

    // Единый цикл: обновляем список + сообщения каждые 3с
    setInterval(pollAll,3000);
    async function pollAll(){{
      await refreshConvList();
      if(ACTIVE_ID) await loadNewMsgs();
    }}

    // Умное обновление списка диалогов (без мерцания — только при изменениях)
    async function refreshConvList(){{
      try{{
        const r=await fetch('/api/conversations');
        const d=await r.json();
        if(!d.conversations) return;
        let changed=false,total=0;
        const ids=new Set(d.conversations.map(c=>c.id));
        d.conversations.forEach(c=>{{
          total+=c.unread_count||0;
          const p=_snap[c.id];
          if(!p||p.u!==c.unread_count||p.m!==c.last_message||p.s!==c.status){{
            changed=true;_snap[c.id]={{u:c.unread_count,m:c.last_message,s:c.status}};
          }}
        }});
        for(const id in _snap)if(!ids.has(+id)){{changed=true;delete _snap[id];}}
        if(changed){{
          const q=(document.querySelector('.conv-search input')?.value||'').toLowerCase();
          let html='';
          d.conversations.forEach(c=>{{
            const cls='conv-item'+(c.id===ACTIVE_ID?' active':'');
            const t=(c.last_message_at||c.created_at).substring(0,16).replace('T',' ');
            const unum=c.unread_count>0?`<span class="unread-num">${{c.unread_count}}</span>`:'';
            const dot=c.status==='open'?'🟢':'⚫';
            const name=esc(c.visitor_name||'');
            const preview=esc(c.last_message||'Нет сообщений');
            const vis=!q||name.toLowerCase().includes(q);
            html+=`<a href="/chat?conv_id=${{c.id}}" style="${{vis?'':'display:none'}}"><div class="${{cls}}">
              <div class="conv-name"><span>${{dot}} ${{name}}</span>${{unum}}</div>
              <div class="conv-preview">${{preview}}</div>
              <div class="conv-time">${{t}}</div></div></a>`;
          }});
          if(!html)html='<div class="empty" style="padding:36px 14px">Диалогов пока нет</div>';
          document.getElementById('conv-items').innerHTML=html;
        }}
        // Обновляем бейдж в сайдбаре
        const b=document.querySelector('.badge-count');
        if(total>0){{if(b)b.textContent=total;}}else if(b)b.remove();
      }}catch(e){{}}
    }}

    async function sendMsg(){{
      const ta=document.getElementById('reply-text');
      const text=ta.value.trim(); if(!text) return; ta.value='';
      await fetch('/chat/send',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:'conv_id={conv_id}&text='+encodeURIComponent(text)}});
      await loadNewMsgs();
    }}
    function handleKey(e){{if(e.key==='Enter'&&!e.shiftKey){{e.preventDefault();sendMsg();}}}}
    async function loadNewMsgs(){{
      const msgs=document.querySelectorAll('.msg[data-id]');
      const lastId=msgs.length?msgs[msgs.length-1].dataset.id:0;
      const res=await fetch('/api/messages/{conv_id}?after='+lastId);
      const data=await res.json();
      if(data.messages&&data.messages.length>0){{
        const c=document.getElementById('msgs');
        const incoming=data.messages.filter(m=>m.sender_type==='visitor');
        if(!_firstMsgLoad&&incoming.length>0&&typeof playNotifySound!=='undefined'){{
          playNotifySound('tg');
          showToast(ACTIVE_NAME,incoming[incoming.length-1].content,'tg');
        }}
        data.messages.forEach(m=>{{const d=document.createElement('div');d.className='msg '+m.sender_type;d.dataset.id=m.id;
          d.innerHTML='<div class="msg-bubble">'+esc(m.content)+'</div><div class="msg-time">'+m.created_at.substring(11,16)+'</div>';
          c.appendChild(d);}});c.scrollTop=c.scrollHeight;
        _firstMsgLoad=false;
      }} else {{ _firstMsgLoad=false; }}
    }}
    function esc(t){{return(t||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\\n/g,'<br>');}}
    function filterConvs(q){{document.querySelectorAll('.conv-item').forEach(el=>{{
      const n=el.querySelector('.conv-name')?.textContent?.toLowerCase()||'';
      el.parentElement.style.display=n.includes(q.toLowerCase())?'':'none';}});}}
    </script>"""

    return HTMLResponse(f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>Чаты</title>{CSS}</head><body>{nav_html("chat",request)}<div class="main">{content}</div>{NOTIFY_JS}</body></html>')


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
    app_url   = db.get_setting("app_url", "").rstrip("/")
    ch_opts = "".join(f'<option value="{c["channel_id"]}">{c["name"]}</option>' for c in channels) or '<option disabled>Сначала добавь каналы</option>'
    rows = "".join(f"""<tr>
        <td><span class="badge">{c['name']}</span></td>
        <td><span class="tag" style="font-size:.7rem">{c['channel_id']}</span></td>
        <td><div class="link-box" style="max-width:220px">{c['invite_link']}</div></td>
        <td><div class="link-box" style="max-width:220px;color:#7dd3fc">{app_url}/go?to={c['invite_link']}&utm_campaign={c['name']}</div></td>
        <td style="color:#34d399;font-weight:600">{c['joins']}</td>
        <td>{c['created_at'][:10]}</td></tr>""" for c in campaigns
    ) or '<tr><td colspan="6"><div class="empty">Кампаний нет</div></td></tr>'
    new_link = msg if msg.startswith("https://") else ""
    alert = f'<div class="alert-green">✅ Ссылка:<div class="link-box" style="margin-top:8px">{new_link}</div><div style="margin-top:8px;color:#7dd3fc">📎 /go ссылка:<div class="link-box" style="margin-top:4px">{app_url}/go?to={new_link}&utm_campaign=your_campaign</div></div></div>' if new_link else (f'<div class="alert-red">❌ {err_msg}</div>' if err_msg else "")
    content = f"""<div class="page-wrap"><div class="page-title">🔗 Кампании</div>
    <div class="page-sub">Invite-ссылки + /go ссылки для рекламы с UTM-трекингом</div>{alert}
    <div class="section"><div class="section-head"><h3>➕ Создать ссылку</h3></div><div class="section-body">
    <form method="post" action="/campaigns/create"><div class="form-row">
    <div class="field-group"><div class="field-label">Канал</div><select name="channel_id">{ch_opts}</select></div>
    <div class="field-group"><div class="field-label">Название кампании</div><input type="text" name="name" placeholder="FB_Broad_March" required/></div>
    <div style="display:flex;align-items:flex-end"><button class="btn">Создать</button></div>
    </div></form></div></div>
    <div class="section"><div class="section-head"><h3>📋 Кампании ({len(campaigns)})</h3></div>
    <table><thead><tr><th>Кампания</th><th>Канал</th><th>Invite Link</th><th>/go ссылка</th><th>Подписчиков</th><th>Создана</th></tr></thead>
    <tbody>{rows}</tbody></table></div></div>"""
    return HTMLResponse(base(content, "campaigns", request))


@app.post("/campaigns/create")
async def campaigns_create(request: Request, channel_id: str = Form(...), name: str = Form(...)):
    user, err = require_auth(request)
    if err: return err
    try:
        b1 = bot_manager.get_tracker_bot()
        if not b1: return RedirectResponse("/campaigns?err_msg=Бот+1+не+запущен", 303)
        link_obj = await b1.create_chat_invite_link(chat_id=int(channel_id), name=name[:32])
        db.save_campaign(name=name, channel_id=channel_id, invite_link=link_obj.invite_link)
        return RedirectResponse(f"/campaigns?msg={link_obj.invite_link}", 303)
    except Exception as e:
        return RedirectResponse(f"/campaigns?err_msg={str(e)}", 303)


@app.get("/landing", response_class=HTMLResponse)
async def landing_admin(request: Request, msg: str = ""):
    user, err = require_auth(request)
    if err: return err
    links = db.get_landing_links()
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""

    rows = "".join(f"""<tr>
        <td style="font-size:1.2rem">{l['emoji']}</td>
        <td><b>{l['title']}</b></td>
        <td><a href="{l['tg_link']}" target="_blank" style="color:#60a5fa;font-size:.8rem">{l['tg_link'][:40]}...</a></td>
        <td><form method="post" action="/landing/delete"><input type="hidden" name="link_id" value="{l['id']}"/>
        <button class="del-btn">✕</button></form></td></tr>""" for l in links
    ) or '<tr><td colspan="4"><div class="empty">Нет ссылок — добавь TG каналы для кнопки Contact me</div></td></tr>'

    # Текущие значения
    def gs(k, d=""): return db.get_setting(k, d)

    content = f"""<div class="page-wrap">
    <div class="page-title">🌐 Лендинг — Клиенты</div>
    <div class="page-sub">Публичная страница: <a href="/page" target="_blank" style="color:#3b82f6">/page →</a></div>
    {alert}

    <div class="section">
      <div class="section-head"><h3>📩 Кнопки Contact me (TG каналы)</h3></div>
      <div class="section-body">
        <form method="post" action="/landing/add"><div class="form-row" style="margin-bottom:10px">
          <div class="field-group" style="max-width:80px"><div class="field-label">Эмодзи</div><input type="text" name="emoji" value="📢"/></div>
          <div class="field-group"><div class="field-label">Название</div><input type="text" name="title" placeholder="Мой канал" required/></div>
          <div class="field-group"><div class="field-label">Ссылка TG</div><input type="text" name="tg_link" placeholder="https://t.me/+xxx" required/></div>
          <div style="display:flex;align-items:flex-end"><button class="btn">Добавить</button></div>
        </div></form>
        <table><thead><tr><th></th><th>Название</th><th>Ссылка</th><th></th></tr></thead>
        <tbody>{rows}</tbody></table>
      </div>
    </div>

    <div class="section">
      <div class="section-head"><h3>✏️ Тексты лендинга</h3></div>
      <div class="section-body">
        <form method="post" action="/landing/texts">
          <div class="grid-2" style="margin-bottom:12px">
            <div class="field-group"><div class="field-label">Заголовок Hero</div><input type="text" name="land_hero_title" value="{gs('land_hero_title','Relaxation and Balance 🌿✨')}"/></div>
            <div class="field-group"><div class="field-label">Подзаголовок Hero</div><input type="text" name="land_hero_sub" value="{gs('land_hero_sub','I invite you to enjoy a soothing body massage in a comfortable, private setting.')}"/></div>
            <div class="field-group"><div class="field-label">Заголовок "Included"</div><input type="text" name="land_incl_title" value="{gs('land_incl_title','Included in the session:')}"/></div>
            <div class="field-group"><div class="field-label">УТП 1</div><input type="text" name="land_utp1" value="{gs('land_utp1','💆‍♂️ Full body massage')}"/></div>
            <div class="field-group"><div class="field-label">УТП 2</div><input type="text" name="land_utp2" value="{gs('land_utp2','🤍 Full body contact massage')}"/></div>
            <div class="field-group"><div class="field-label">УТП 3</div><input type="text" name="land_utp3" value="{gs('land_utp3','🔥 Relaxation completion')}"/></div>
            <div class="field-group"><div class="field-label">Тариф 1 (мин — цена)</div><input type="text" name="land_rate1" value="{gs('land_rate1','60 min — $230')}"/></div>
            <div class="field-group"><div class="field-label">Тариф 2</div><input type="text" name="land_rate2" value="{gs('land_rate2','30 min — $200')}"/></div>
            <div class="field-group"><div class="field-label">Тариф 3</div><input type="text" name="land_rate3" value="{gs('land_rate3','15 min — $140')}"/></div>
            <div class="field-group"><div class="field-label">Важно 1</div><input type="text" name="land_info1" value="{gs('land_info1','📌 Extra services can only be discussed in person during the session.')}"/></div>
            <div class="field-group"><div class="field-label">Важно 2</div><input type="text" name="land_info2" value="{gs('land_info2','💵 Payment is accepted in cash only. Please prepare the exact amount.')}"/></div>
            <div class="field-group"><div class="field-label">Важно 3</div><input type="text" name="land_info3" value="{gs('land_info3','⚠️ Same-day appointments only. Advance bookings are not available.')}"/></div>
          </div>
          <div class="field-group" style="margin-bottom:12px">
            <div class="field-label">Описание (attire/about)</div>
            <textarea name="land_attire">{gs('land_attire',"✨ I'll greet you in elegant attire and provide a relaxing massage in comfortable, minimal clothing. Touching me is not allowed.")}</textarea>
          </div>
          <div class="field-group" style="margin-bottom:12px">
            <div class="field-label">CTA текст для бронирования</div>
            <input type="text" name="land_book_cta" value="{gs('land_book_cta','💌 Message me to book your session!')}"/>
          </div>
          <button class="btn">💾 Сохранить тексты</button>
        </form>
      </div>
    </div>

    <div class="section">
      <div class="section-head"><h3>📸 Медиа (фото и видео)</h3></div>
      <div class="section-body">
        <div style="font-size:.8rem;color:#475569;margin-bottom:12px">
          Вставь URL-ы через запятую. Для Cloudinary: загрузи файл и скопируй ссылку с .jpg/.mp4<br>
          Пример: <span class="tag">https://res.cloudinary.com/XXX/image/upload/v1/photo1.jpg, https://...</span>
        </div>
        <form method="post" action="/landing/media">
          <div class="field-group" style="margin-bottom:12px">
            <div class="field-label">📷 Фото URL-ы (через запятую)</div>
            <textarea name="land_photo_urls" placeholder="https://res.cloudinary.com/...">{gs('land_photo_urls','')}</textarea>
          </div>
          <div class="field-group" style="margin-bottom:12px">
            <div class="field-label">🎬 Видео URL-ы (через запятую)</div>
            <textarea name="land_video_urls" placeholder="https://res.cloudinary.com/...">{gs('land_video_urls','')}</textarea>
          </div>
          <button class="btn">💾 Сохранить медиа</button>
        </form>
      </div>
    </div>
    </div>"""
    return HTMLResponse(base(content, "landing", request))


@app.post("/landing/add")
async def landing_add(request: Request, title: str = Form(...), tg_link: str = Form(...), emoji: str = Form("📢")):
    user, err = require_auth(request)
    if err: return err
    db.add_landing_link(title.strip(), tg_link.strip(), emoji.strip() or "📢")
    return RedirectResponse("/landing?msg=Добавлено", 303)


@app.post("/landing/delete")
async def landing_delete(request: Request, link_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.delete_landing_link(link_id)
    return RedirectResponse("/landing", 303)


@app.post("/landing/texts")
async def landing_texts(request: Request,
    land_hero_title: str = Form(""), land_hero_sub: str = Form(""),
    land_incl_title: str = Form(""), land_utp1: str = Form(""),
    land_utp2: str = Form(""), land_utp3: str = Form(""),
    land_attire: str = Form(""), land_rate1: str = Form(""),
    land_rate2: str = Form(""), land_rate3: str = Form(""),
    land_info1: str = Form(""), land_info2: str = Form(""),
    land_info3: str = Form(""), land_book_cta: str = Form("")):
    user, err = require_auth(request)
    if err: return err
    for key, val in [
        ("land_hero_title", land_hero_title), ("land_hero_sub", land_hero_sub),
        ("land_incl_title", land_incl_title), ("land_utp1", land_utp1),
        ("land_utp2", land_utp2), ("land_utp3", land_utp3),
        ("land_attire", land_attire), ("land_rate1", land_rate1),
        ("land_rate2", land_rate2), ("land_rate3", land_rate3),
        ("land_info1", land_info1), ("land_info2", land_info2),
        ("land_info3", land_info3), ("land_book_cta", land_book_cta),
    ]:
        if val.strip(): db.set_setting(key, val.strip())
    return RedirectResponse("/landing?msg=Тексты+сохранены", 303)


@app.post("/landing/media")
async def landing_media(request: Request,
    land_photo_urls: str = Form(""), land_video_urls: str = Form("")):
    user, err = require_auth(request)
    if err: return err
    db.set_setting("land_photo_urls", land_photo_urls.strip())
    db.set_setting("land_video_urls", land_video_urls.strip())
    return RedirectResponse("/landing?msg=Медиа+сохранены", 303)


# ══════════════════════════════════════════════════════════════════════════════
# STAFF LANDING — Лендинг для сотрудников
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/staff/landing", response_class=HTMLResponse)
async def staff_landing_admin(request: Request, msg: str = ""):
    user, err = require_auth(request, role="admin")
    if err: return err
    links = db.get_staff_landing_links()
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""

    tg_links = [l for l in links if l["link_type"] == "tg"]
    wa_links = [l for l in links if l["link_type"] == "wa"]

    def link_rows(lst, ltype):
        if not lst:
            return f'<tr><td colspan="4"><div class="empty">Нет ссылок типа {ltype}</div></td></tr>'
        return "".join(f"""<tr>
            <td style="font-size:1.2rem">{l["emoji"]}</td>
            <td><b>{l["title"]}</b></td>
            <td style="font-size:.8rem;color:#60a5fa">{l["url"][:45]}...</td>
            <td><form method="post" action="/staff/landing/delete">
              <input type="hidden" name="link_id" value="{l["id"]}"/>
              <button class="del-btn">✕</button></form></td></tr>""" for l in lst)

    def gs(k, d=""): return db.get_setting(k, d)

    content = f"""<div class="page-wrap">
    <div class="page-title">🌐 Лендинг HR — Сотрудники</div>
    <div class="page-sub">Публичная страница: <a href="/staff/page" target="_blank" style="color:#f97316">/staff/page →</a></div>
    {alert}

    <div class="section" style="border-left:3px solid #2BA5F7">
      <div class="section-head"><h3>✈️ Telegram кнопки</h3></div>
      <div class="section-body">
        <form method="post" action="/staff/landing/add"><div class="form-row" style="margin-bottom:10px">
          <input type="hidden" name="link_type" value="tg"/>
          <div class="field-group" style="max-width:70px"><div class="field-label">Emoji</div><input type="text" name="emoji" value="✈️"/></div>
          <div class="field-group"><div class="field-label">Название</div><input type="text" name="title" placeholder="Наш Telegram" required/></div>
          <div class="field-group"><div class="field-label">Ссылка t.me</div><input type="text" name="url" placeholder="https://t.me/username" required/></div>
          <div style="display:flex;align-items:flex-end"><button class="btn">Добавить</button></div>
        </div></form>
        <table><thead><tr><th></th><th>Название</th><th>Ссылка</th><th></th></tr></thead>
        <tbody>{link_rows(tg_links, "tg")}</tbody></table>
      </div>
    </div>

    <div class="section" style="border-left:3px solid #25d366">
      <div class="section-head"><h3>💚 WhatsApp кнопки</h3></div>
      <div class="section-body">
        <form method="post" action="/staff/landing/add"><div class="form-row" style="margin-bottom:10px">
          <input type="hidden" name="link_type" value="wa"/>
          <div class="field-group" style="max-width:70px"><div class="field-label">Emoji</div><input type="text" name="emoji" value="💚"/></div>
          <div class="field-group"><div class="field-label">Название</div><input type="text" name="title" placeholder="Написать в WhatsApp" required/></div>
          <div class="field-group"><div class="field-label">Ссылка wa.me</div><input type="text" name="url" placeholder="https://wa.me/1234567890" required/></div>
          <div style="display:flex;align-items:flex-end"><button class="btn-green">Добавить</button></div>
        </div></form>
        <table><thead><tr><th></th><th>Название</th><th>Ссылка</th><th></th></tr></thead>
        <tbody>{link_rows(wa_links, "wa")}</tbody></table>
      </div>
    </div>

    <div class="section">
      <div class="section-head"><h3>✏️ Тексты и настройки</h3></div>
      <div class="section-body">
        <form method="post" action="/staff/landing/texts">
          <div class="grid-2" style="margin-bottom:12px">
            <div class="field-group"><div class="field-label">Hero заголовок (строка 1)</div><input type="text" name="sl_hero1" value="{gs("sl_hero1","РАБОТА")}"/></div>
            <div class="field-group"><div class="field-label">Hero заголовок (строка 2)</div><input type="text" name="sl_hero2" value="{gs("sl_hero2","МАССАЖИСТКОЙ")}"/></div>
            <div class="field-group"><div class="field-label">Hero бейдж</div><input type="text" name="sl_badge" value="{gs("sl_badge","в США")}"/></div>
            <div class="field-group"><div class="field-label">Hero подзаголовок</div><input type="text" name="sl_hero_sub" value="{gs("sl_hero_sub","Свяжитесь с нами и начните зарабатывать деньги прямо сейчас!")}"/></div>
            <div class="field-group"><div class="field-label">Hero badge-label (напр. Элитный СПА)</div><input type="text" name="sl_hero_badge" value="{gs("sl_hero_badge","⭐ Элитный СПА")}"/></div>
            <div class="field-group"><div class="field-label">Hero фото URL (Cloudinary)</div><input type="text" name="sl_hero_img" value="{gs("sl_hero_img","")}"/></div>
          </div>
          <button class="btn">💾 Сохранить тексты</button>
        </form>
      </div>
    </div>
    </div>"""
    return HTMLResponse(base(content, "staff/landing", request))


@app.post("/staff/landing/add")
async def staff_landing_add(request: Request, title: str = Form(...),
    url: str = Form(...), link_type: str = Form("tg"), emoji: str = Form("📢")):
    user, err = require_auth(request, role="admin")
    if err: return err
    db.add_staff_landing_link(title.strip(), url.strip(), link_type, emoji.strip() or "📢")
    return RedirectResponse("/staff/landing?msg=Добавлено", 303)


@app.post("/staff/landing/delete")
async def staff_landing_delete(request: Request, link_id: int = Form(...)):
    user, err = require_auth(request, role="admin")
    if err: return err
    db.delete_staff_landing_link(link_id)
    return RedirectResponse("/staff/landing", 303)


@app.post("/staff/landing/texts")
async def staff_landing_texts(request: Request,
    sl_hero1: str = Form(""), sl_hero2: str = Form(""), sl_badge: str = Form(""),
    sl_hero_sub: str = Form(""), sl_hero_badge: str = Form(""), sl_hero_img: str = Form("")):
    user, err = require_auth(request, role="admin")
    if err: return err
    for k, v in [("sl_hero1",sl_hero1),("sl_hero2",sl_hero2),("sl_badge",sl_badge),
                  ("sl_hero_sub",sl_hero_sub),("sl_hero_badge",sl_hero_badge),("sl_hero_img",sl_hero_img)]:
        if v.strip(): db.set_setting(k, v.strip())
    return RedirectResponse("/staff/landing?msg=Сохранено", 303)


@app.get("/staff/page", response_class=HTMLResponse)
async def staff_public_page():
    links = db.get_staff_landing_links()
    tg_links = [l for l in links if l["link_type"] == "tg"]
    wa_links = [l for l in links if l["link_type"] == "wa"]

    def gs(k, d=""): return db.get_setting(k, d)
    hero1      = gs("sl_hero1", "РАБОТА")
    hero2      = gs("sl_hero2", "МАССАЖИСТКОЙ")
    badge      = gs("sl_badge", "в США")
    hero_sub   = gs("sl_hero_sub", "Свяжитесь с нами и начните зарабатывать деньги прямо сейчас!")
    hero_badge = gs("sl_hero_badge", "⭐ Элитный СПА")
    hero_img   = gs("sl_hero_img", "")

    hero_img_html = f'<img src="{hero_img}" alt="massage" style="width:100%;height:100%;object-fit:cover"/>' if hero_img else '<div style="width:100%;height:100%;background:linear-gradient(135deg,#e879f9,#a21caf);display:flex;align-items:center;justify-content:center;font-size:4rem">💆‍♀️</div>'

    def contact_btns(lst, color, icon):
        if not lst: return ""
        return "".join(f'<a href="{l["url"]}" target="_blank" class="cta-btn" style="background:{color};display:flex;align-items:center;justify-content:center;gap:10px;margin:6px 0;text-decoration:none"><span>{l["emoji"]}</span> {l["title"]}</a>' for l in lst)

    tg_btns = contact_btns(tg_links, "linear-gradient(135deg,#2BA5F7,#1a7fd4)", "✈️")
    wa_btns = contact_btns(wa_links, "linear-gradient(135deg,#25d366,#128c7e)", "💚")
    all_btns_popup = tg_btns + wa_btns or '<p style="text-align:center;color:#999;padding:20px">Контакты не настроены</p>'
    first_tg = tg_links[0]["url"] if tg_links else "#"
    first_wa = wa_links[0]["url"] if wa_links else "#"

    def inline_btns():
        btns = ""
        if tg_links:
            btns += f'<a href="{tg_links[0]["url"]}" target="_blank" class="cta-btn" style="background:linear-gradient(135deg,#e040fb,#9c27b0);display:inline-flex;align-items:center;gap:10px;padding:14px 32px;border-radius:50px;color:#fff;font-weight:700;font-size:1rem;text-decoration:none"><svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.894 8.221l-1.97 9.28c-.145.658-.537.818-1.084.508l-3-2.21-1.447 1.394c-.16.16-.295.295-.605.295l.213-3.053 5.56-5.023c.242-.213-.054-.333-.373-.12l-6.871 4.326-2.962-.924c-.643-.204-.657-.643.136-.953l11.57-4.461c.537-.194 1.006.131.833.941z"/></svg>Связаться в Телеграм</a>'
        return btns

    cta_html = inline_btns()

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Massage Job USA</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{--pink:#e040fb;--pink2:#f06292;--grad:linear-gradient(135deg,#e040fb,#9c27b0);--dark:#1a1a2e}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#fff;color:#1a1a2e;overflow-x:hidden}}
a{{text-decoration:none;color:inherit}}

/* NAV */
.nav{{display:flex;align-items:center;justify-content:space-between;padding:14px 40px;background:#fff;
  border-bottom:1px solid #f5e6ff;position:sticky;top:0;z-index:50;box-shadow:0 2px 12px rgba(224,64,251,.08)}}
.nav-logo{{display:flex;align-items:center;gap:10px;font-weight:800;font-size:1.05rem}}
.nav-logo-icon{{width:36px;height:36px;background:var(--grad);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:1.2rem}}
.nav-links{{display:flex;gap:28px;font-size:.88rem;color:#555}}
.nav-links a:hover{{color:var(--pink)}}
.nav-tg{{display:flex;align-items:center;gap:7px;color:var(--pink);font-weight:600;font-size:.88rem}}
@media(max-width:768px){{.nav-links{{display:none}}.nav{{padding:12px 20px}}}}

/* HERO */
.hero{{display:grid;grid-template-columns:1fr 1fr;min-height:85vh;background:linear-gradient(135deg,#fce4ec 0%,#f8bbd0 40%,#f3e5f5 100%);position:relative;overflow:hidden}}
@media(max-width:768px){{.hero{{grid-template-columns:1fr;min-height:auto}}}}
.hero-left{{padding:80px 60px;display:flex;flex-direction:column;justify-content:center}}
@media(max-width:768px){{.hero-left{{padding:40px 24px}}}}
.hero-badge{{display:inline-block;background:var(--grad);color:#fff;border-radius:50px;padding:8px 20px;font-size:.88rem;font-weight:700;margin-bottom:24px;width:fit-content}}
.hero-h1{{font-size:clamp(2.8rem,6vw,5rem);font-weight:900;line-height:1;letter-spacing:-.02em;color:#1a1a2e;margin-bottom:12px}}
.hero-h1 span{{color:var(--pink)}}
.hero-sub{{font-size:1rem;color:#555;margin:20px 0 32px;line-height:1.6;max-width:440px}}
.hero-right{{position:relative;display:flex;align-items:center;justify-content:center;padding:40px}}
@media(max-width:768px){{.hero-right{{height:320px;padding:20px}}}}
.hero-circle{{width:420px;height:420px;border-radius:50%;overflow:hidden;border:6px solid rgba(224,64,251,.3);
  box-shadow:0 0 80px rgba(224,64,251,.25);position:relative}}
@media(max-width:768px){{.hero-circle{{width:260px;height:260px}}}}
.hero-float{{position:absolute;bottom:60px;right:80px;background:#fff;border-radius:16px;padding:12px 20px;
  display:flex;align-items:center;gap:10px;font-weight:700;font-size:.88rem;
  box-shadow:0 8px 32px rgba(0,0,0,.12)}}
@media(max-width:768px){{.hero-float{{bottom:20px;right:20px;font-size:.75rem;padding:8px 14px}}}}
.hero-star{{font-size:1.4rem}}

/* SECTIONS */
.section{{padding:80px 40px;max-width:1200px;margin:0 auto}}
@media(max-width:768px){{.section{{padding:48px 20px}}}}
.section-bg{{background:linear-gradient(135deg,#fce4ec,#f3e5f5);padding:80px 40px}}
.sec-tag{{display:inline-block;background:var(--grad);color:#fff;border-radius:50px;padding:6px 18px;font-size:.8rem;font-weight:700;margin-bottom:16px}}
.sec-h2{{font-size:clamp(1.8rem,4vw,2.8rem);font-weight:900;color:#1a1a2e;margin-bottom:8px}}
.sec-h2 .pink{{color:var(--pink)}}
.sec-sub{{color:#777;margin-bottom:40px;font-size:.95rem}}

/* BENEFITS GRID */
.benefits-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:24px}}
@media(max-width:768px){{.benefits-grid{{grid-template-columns:1fr}}}}
.benefit-card{{background:#fff;border-radius:20px;padding:28px;box-shadow:0 4px 24px rgba(0,0,0,.06)}}
.benefit-icon{{width:52px;height:52px;background:var(--grad);border-radius:14px;display:flex;align-items:center;justify-content:center;font-size:1.4rem;margin-bottom:16px}}
.benefit-title{{font-weight:800;font-size:1.05rem;margin-bottom:8px}}
.benefit-line{{width:40px;height:3px;background:var(--grad);border-radius:3px;margin-bottom:12px}}
.benefit-text{{color:#666;font-size:.88rem;line-height:1.6}}

/* PINK BANNER */
.pink-banner{{background:var(--grad);padding:64px 40px;text-align:center;position:relative;overflow:hidden}}
.pink-banner::before,.pink-banner::after{{content:"🌴";position:absolute;font-size:8rem;opacity:.2;top:50%;transform:translateY(-50%)}}
.pink-banner::before{{left:-40px}}
.pink-banner::after{{right:-40px}}
.banner-h2{{font-size:clamp(1.6rem,4vw,2.4rem);font-weight:900;color:#fff;margin-bottom:12px}}
.banner-sub{{color:rgba(255,255,255,.85);margin-bottom:32px;font-size:.95rem}}

/* TWO-COL */
.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:60px;align-items:center}}
@media(max-width:768px){{.two-col{{grid-template-columns:1fr}}}}
.req-list{{list-style:none;margin:20px 0 32px}}
.req-list li{{display:flex;align-items:flex-start;gap:10px;padding:8px 0;font-size:.95rem;color:#444}}
.req-dot{{width:10px;height:10px;background:var(--grad);border-radius:50%;flex-shrink:0;margin-top:6px}}
.req-circle{{width:380px;height:380px;border-radius:50%;overflow:hidden;border:6px solid rgba(224,64,251,.25);box-shadow:0 0 60px rgba(224,64,251,.2)}}
@media(max-width:768px){{.req-circle{{width:260px;height:260px;margin:0 auto}}}}

/* STEPS */
.steps-grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}}
@media(max-width:768px){{.steps-grid{{grid-template-columns:1fr}}}}
.step-card{{background:#fff;border-radius:20px;padding:28px;box-shadow:0 4px 24px rgba(0,0,0,.06);position:relative}}
.step-num{{position:absolute;top:16px;right:20px;font-size:3rem;font-weight:900;color:#f3e5f5}}
.step-icon{{width:52px;height:52px;background:var(--grad);border-radius:14px;display:flex;align-items:center;justify-content:center;font-size:1.4rem;margin-bottom:14px}}
.step-title{{font-weight:800;margin-bottom:8px;font-size:1rem}}
.step-text{{color:#666;font-size:.85rem;line-height:1.6}}

/* PROVIDES */
.provides-box{{background:#fff;border-radius:20px;padding:8px;box-shadow:0 4px 24px rgba(0,0,0,.06);max-width:700px;margin:0 auto}}
.provide-item{{display:flex;align-items:center;gap:16px;padding:18px 20px;border-bottom:1px solid #f5f5f5}}
.provide-item:last-child{{border-bottom:none}}
.provide-icon{{width:44px;height:44px;background:var(--grad);border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:1.2rem;flex-shrink:0}}
.provide-text{{font-size:.95rem;color:#333;font-weight:500}}

/* REVIEWS */
.reviews-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}}
@media(max-width:900px){{.reviews-grid{{grid-template-columns:1fr 1fr}}}}
@media(max-width:600px){{.reviews-grid{{grid-template-columns:1fr}}}}
.review-card{{background:#fff;border-radius:16px;padding:20px;box-shadow:0 4px 20px rgba(0,0,0,.07)}}
.stars{{color:var(--pink);font-size:1rem;margin-bottom:8px}}
.rev-name{{font-weight:800;font-size:.95rem}}
.rev-from{{color:#999;font-size:.78rem;margin-bottom:10px}}
.rev-stats{{display:flex;gap:14px;margin-bottom:12px;font-size:.78rem;color:#888}}
.rev-stat{{display:flex;align-items:center;gap:4px}}
.rev-earn{{color:#22c55e;font-weight:700}}
.rev-text{{font-size:.83rem;color:#555;line-height:1.5}}

/* FAQ */
.faq-list{{max-width:760px;margin:0 auto}}
.faq-item{{border-bottom:1px solid #f0e6ff;overflow:hidden}}
.faq-q{{display:flex;justify-content:space-between;align-items:center;padding:20px 0;cursor:pointer;font-weight:600;font-size:.95rem;color:#1a1a2e}}
.faq-q:hover{{color:var(--pink)}}
.faq-icon{{font-size:1.2rem;color:var(--pink);transition:transform .3s;flex-shrink:0}}
.faq-a{{max-height:0;overflow:hidden;transition:max-height .3s ease;color:#555;font-size:.88rem;line-height:1.7}}
.faq-a.open{{max-height:200px;padding-bottom:16px}}
.faq-icon.open{{transform:rotate(180deg)}}

/* FINAL CTA */
.final-cta{{background:var(--grad);padding:80px 40px;text-align:center;position:relative;overflow:hidden}}
.final-cta::before{{content:"";position:absolute;width:200px;height:200px;border-radius:50%;
  background:rgba(255,255,255,.1);top:-50px;left:-50px}}
.final-cta::after{{content:"";position:absolute;width:150px;height:150px;border-radius:50%;
  background:rgba(255,255,255,.1);bottom:-30px;right:10%}}
.final-h2{{font-size:clamp(1.5rem,3.5vw,2.2rem);font-weight:900;color:#fff;margin-bottom:12px;position:relative}}
.final-sub{{color:rgba(255,255,255,.85);margin-bottom:32px;position:relative}}

/* FOOTER */
.footer{{background:#1a1a2e;padding:48px 40px;color:#aaa}}
@media(max-width:768px){{.footer{{padding:32px 20px}}}}
.footer-grid{{display:grid;grid-template-columns:1.5fr 1fr 1fr;gap:40px;max-width:1000px;margin:0 auto 32px}}
@media(max-width:768px){{.footer-grid{{grid-template-columns:1fr}}}}
.footer-logo{{display:flex;align-items:center;gap:10px;font-weight:800;color:#fff;margin-bottom:12px;font-size:1.05rem}}
.footer-text{{font-size:.83rem;line-height:1.6;color:#888}}
.footer-col h4{{color:#fff;font-weight:700;margin-bottom:14px;font-size:.9rem}}
.footer-col a{{display:block;color:#888;font-size:.83rem;margin-bottom:8px}}
.footer-col a:hover{{color:var(--pink)}}
.footer-bottom{{border-top:1px solid #2d2d4e;padding-top:20px;text-align:center;font-size:.78rem;color:#555;max-width:1000px;margin:0 auto}}

/* CTA BTN */
.cta-btn{{background:var(--grad);color:#fff;border:none;border-radius:50px;padding:14px 36px;
  font-size:1rem;font-weight:700;cursor:pointer;font-family:inherit;transition:all .2s;
  box-shadow:0 4px 20px rgba(224,64,251,.3);display:inline-flex;align-items:center;gap:8px}}
.cta-btn:hover{{transform:translateY(-2px);box-shadow:0 8px 32px rgba(224,64,251,.45)}}
.cta-btn.white{{background:#fff;color:var(--pink);box-shadow:0 4px 20px rgba(0,0,0,.15)}}

/* MODAL */
.modal-overlay{{position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:100;
  display:none;align-items:center;justify-content:center;padding:20px}}
.modal-overlay.open{{display:flex}}
.modal{{background:#fff;border-radius:24px;width:100%;max-width:420px;padding:32px 28px;position:relative}}
.modal-close{{position:absolute;top:14px;right:16px;background:#f5f5f5;border:none;border-radius:50%;
  width:30px;height:30px;cursor:pointer;font-size:1rem;display:flex;align-items:center;justify-content:center}}
.modal-title{{font-size:1.2rem;font-weight:800;color:#1a1a2e;margin-bottom:20px}}
.modal-btn{{display:flex;align-items:center;gap:12px;padding:14px 18px;border-radius:14px;margin-bottom:10px;
  font-weight:700;font-size:.95rem;color:#fff;transition:all .2s}}
.modal-btn:hover{{transform:translateX(4px)}}
.modal-tg{{background:linear-gradient(135deg,#2BA5F7,#1a7fd4)}}
.modal-wa{{background:linear-gradient(135deg,#25d366,#128c7e)}}
</style>
</head>
<body>

<!-- NAV -->
<nav class="nav">
  <div class="nav-logo">
    <div class="nav-logo-icon">💆</div>
    <span>Massage Job USA</span>
  </div>
  <div class="nav-links">
    <a href="#vacancy">Вакансия</a>
    <a href="#benefits">Преимущества</a>
    <a href="#requirements">Требования</a>
    <a href="#how">Как начать</a>
    <a href="#reviews">Отзывы</a>
    <a href="#faq">FAQ</a>
  </div>
  <div class="nav-tg" onclick="openModal()">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.894 8.221l-1.97 9.28c-.145.658-.537.818-1.084.508l-3-2.21-1.447 1.394c-.16.16-.295.295-.605.295l.213-3.053 5.56-5.023c.242-.213-.054-.333-.373-.12l-6.871 4.326-2.962-.924c-.643-.204-.657-.643.136-.953l11.57-4.461c.537-.194 1.006.131.833.941z"/></svg>
    Telegram
  </div>
</nav>

<!-- HERO -->
<section class="hero" id="vacancy">
  <div class="hero-left">
    <div class="hero-badge">{badge}</div>
    <h1 class="hero-h1">{hero1}<br>{hero2}</h1>
    <p class="hero-sub">{hero_sub}</p>
    <div onclick="openModal()" style="cursor:pointer">{cta_html or '<button class="cta-btn" onclick="openModal()"><svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.894 8.221l-1.97 9.28c-.145.658-.537.818-1.084.508l-3-2.21-1.447 1.394c-.16.16-.295.295-.605.295l.213-3.053 5.56-5.023c.242-.213-.054-.333-.373-.12l-6.871 4.326-2.962-.924c-.643-.204-.657-.643.136-.953l11.57-4.461c.537-.194 1.006.131.833.941z"/></svg>Связаться в Телеграм</button>'}</div>
  </div>
  <div class="hero-right">
    <div class="hero-circle">{hero_img_html}</div>
    <div class="hero-float"><span class="hero-star">⭐</span> {hero_badge}</div>
  </div>
</section>

<!-- ABOUT -->
<section class="section-bg">
  <div style="max-width:1200px;margin:0 auto;display:grid;grid-template-columns:1fr 1fr;gap:60px;align-items:center" id="about">
    <div>
      <div class="sec-tag">Увлекательная карьера и</div>
      <h2 class="sec-h2">Большие заработки для <span class="pink">Массажисток</span></h2>
      <p style="color:#555;line-height:1.8;margin-bottom:16px">Работа массажисткой в США — уникальный шанс построить успешную карьеру в индустрии красоты и здоровья. Практика показывает: каждая массажистка может зарабатывать от $1500 в день. Главное — желание развиваться.</p>
      <p style="color:#555;line-height:1.8;margin-bottom:32px">С таким доходом осуществите свои мечты: купите машину, квартиру, помогите близким, запустите собственный бизнес. Вы начнёте зарабатывать с первого дня и сразу почувствуете разницу в качестве жизни.</p>
      <div style="width:60px;height:3px;background:var(--grad);border-radius:3px;margin-bottom:28px"></div>
      <button class="cta-btn" onclick="openModal()">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.894 8.221l-1.97 9.28c-.145.658-.537.818-1.084.508l-3-2.21-1.447 1.394c-.16.16-.295.295-.605.295l.213-3.053 5.56-5.023c.242-.213-.054-.333-.373-.12l-6.871 4.326-2.962-.924c-.643-.204-.657-.643.136-.953l11.57-4.461c.537-.194 1.006.131.833.941z"/></svg>
        Связаться в Телеграм
      </button>
    </div>
    <div style="display:flex;justify-content:flex-end;align-items:center">
      <div style="font-size:8rem;opacity:.3">💆‍♀️</div>
    </div>
  </div>
</section>

<!-- PINK BANNER 1 -->
<div class="pink-banner">
  <h2 class="banner-h2">Начни зарабатывать уже сегодня</h2>
  <p class="banner-sub">Присоединяйся к нашей команде и получай стабильный доход с первого дня работы.</p>
  <button class="cta-btn white" onclick="openModal()">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.894 8.221l-1.97 9.28c-.145.658-.537.818-1.084.508l-3-2.21-1.447 1.394c-.16.16-.295.295-.605.295l.213-3.053 5.56-5.023c.242-.213-.054-.333-.373-.12l-6.871 4.326-2.962-.924c-.643-.204-.657-.643.136-.953l11.57-4.461c.537-.194 1.006.131.833.941z"/></svg>
    Связаться в Телеграм
  </button>
</div>

<!-- BENEFITS -->
<div style="padding:80px 40px;background:#fafafa" id="benefits">
  <div style="max-width:1200px;margin:0 auto">
    <h2 class="sec-h2" style="text-align:center;margin-bottom:6px">Почему стоит начать</h2>
    <p class="sec-sub" style="text-align:center">работать <span style="color:var(--pink);font-weight:700">с нами?</span></p>
    <div class="benefits-grid" style="margin-top:40px">
      <div class="benefit-card"><div class="benefit-icon">👁</div><div class="benefit-title">Работайте анонимно</div><div class="benefit-line"></div><p class="benefit-text">Ваши личные данные защищены. Мы гарантируем полную конфиденциальность всем нашим специалистам.</p></div>
      <div class="benefit-card"><div class="benefit-icon">🕐</div><div class="benefit-title">Работайте когда хотите</div><div class="benefit-line"></div><p class="benefit-text">Гибкий график позволяет совмещать работу с образованием и личной жизнью.</p></div>
      <div class="benefit-card"><div class="benefit-icon">🛡</div><div class="benefit-title">Безопасность</div><div class="benefit-line"></div><p class="benefit-text">Все клиенты проходят тщательную проверку. Ваша безопасность — наш приоритет.</p></div>
      <div class="benefit-card"><div class="benefit-icon">💵</div><div class="benefit-title">Оплата каждый день</div><div class="benefit-line"></div><p class="benefit-text">Оплата происходит перед каждой процедурой, поэтому вы сразу получаете свой доход и полностью контролируете свой заработок.</p></div>
      <div class="benefit-card"><div class="benefit-icon">🎧</div><div class="benefit-title">Обучение и поддержка</div><div class="benefit-line"></div><p class="benefit-text">Если у вас нет опыта — это не проблема. Мы предоставляем обучение для будущих массажисток. На протяжении всей работы вам доступна поддержка.</p></div>
      <div class="benefit-card"><div class="benefit-icon">🏠</div><div class="benefit-title">Предоставляем комфортное жильё</div><div class="benefit-line"></div><p class="benefit-text">На время сотрудничества мы предоставляем комфортное проживание. Также предусмотрена возможность смены локации в разных городах по территории США.</p></div>
    </div>
  </div>
</div>

<!-- REQUIREMENTS -->
<div style="padding:80px 40px;background:#fff" id="requirements">
  <div style="max-width:1200px;margin:0 auto">
    <div class="two-col">
      <div>
        <h2 class="sec-h2">Требования к<br><span class="pink">кандидаткам</span></h2>
        <p style="color:#555;margin:16px 0">Вы нам подойдёте, если вы:</p>
        <ul class="req-list">
          <li><span class="req-dot"></span>имеете опыт работы или готовы обучаться с нуля</li>
          <li><span class="req-dot"></span>ответственны и дисциплинированы</li>
          <li><span class="req-dot"></span>коммуникабельны и ориентированы на клиента</li>
          <li><span class="req-dot"></span>ухожены и придерживаетесь аккуратного внешнего вида</li>
          <li><span class="req-dot"></span>готовы соблюдать стандарты сервиса</li>
        </ul>
        <button class="cta-btn" onclick="openModal()">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.894 8.221l-1.97 9.28c-.145.658-.537.818-1.084.508l-3-2.21-1.447 1.394c-.16.16-.295.295-.605.295l.213-3.053 5.56-5.023c.242-.213-.054-.333-.373-.12l-6.871 4.326-2.962-.924c-.643-.204-.657-.643.136-.953l11.57-4.461c.537-.194 1.006.131.833.941z"/></svg>
          Связаться в Телеграм
        </button>
      </div>
      <div style="display:flex;justify-content:center">
        <div class="req-circle">
          {hero_img_html}
        </div>
      </div>
    </div>
  </div>
</div>

<!-- HOW TO START -->
<div style="padding:80px 40px;background:#fafafa" id="how">
  <div style="max-width:900px;margin:0 auto">
    <h2 class="sec-h2" style="text-align:center;margin-bottom:40px">Как начать <span class="pink">работать</span></h2>
    <div class="steps-grid">
      <div class="step-card"><div class="step-num">1</div><div class="step-icon">✈️</div><div class="step-title">1. Переходите в телеграм</div><p class="step-text">С вами на связи будет наш HR специалист.</p></div>
      <div class="step-card"><div class="step-num">2</div><div class="step-icon">💬</div><div class="step-title">2. Уточняете детали</div><p class="step-text">Наш HR-специалист подробно отвечает на все ваши вопросы.</p></div>
    </div>
    <div class="step-card" style="margin-top:20px">
      <div class="step-num">3</div>
      <div class="step-icon">📋</div>
      <div class="step-title">3. Заполняете анкету</div>
      <p class="step-text">От вас потребуется минимум информации:<br><br>
        • имя и возраст (Анна 24 года)<br>
        • ваше текущее местонахождение в США (Лос-Анджелес)<br>
        • номер телефона или Telegram для связи (+1(xxx) xxx-xxx или ник тг @Anya24)<br>
        • одно фото в полный рост (необходимо для понимания вашего внешнего вида. Фото используется исключительно для предварительного рассмотрения кандидатуры.*)
      </p>
    </div>
    <p style="text-align:center;color:#555;margin:28px 0;font-style:italic">Начните сегодня и уже завтра вы будете радоваться стабильному заработку!</p>
    <div style="text-align:center">
      <button class="cta-btn" onclick="openModal()">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.894 8.221l-1.97 9.28c-.145.658-.537.818-1.084.508l-3-2.21-1.447 1.394c-.16.16-.295.295-.605.295l.213-3.053 5.56-5.023c.242-.213-.054-.333-.373-.12l-6.871 4.326-2.962-.924c-.643-.204-.657-.643.136-.953l11.57-4.461c.537-.194 1.006.131.833.941z"/></svg>
        Связаться в Телеграм
      </button>
    </div>
  </div>
</div>

<!-- PROVIDES -->
<div style="padding:80px 40px;background:#fff">
  <div style="max-width:900px;margin:0 auto">
    <h2 class="sec-h2" style="text-align:center;margin-bottom:40px">Что предоставляет <span class="pink">вам компания</span></h2>
    <div class="provides-box">
      <div class="provide-item"><div class="provide-icon">🏠</div><span class="provide-text">Комфортное жильё на время работы</span></div>
      <div class="provide-item"><div class="provide-icon">📦</div><span class="provide-text">Материалы необходимые для массажа</span></div>
      <div class="provide-item"><div class="provide-icon">👥</div><span class="provide-text">Стабильный поток клиентов</span></div>
      <div class="provide-item"><div class="provide-icon">🎧</div><span class="provide-text">Круглосуточная поддержка по всем вопросам</span></div>
    </div>
  </div>
</div>

<!-- REVIEWS -->
<div style="padding:80px 40px;background:#fafafa" id="reviews">
  <div style="max-width:1200px;margin:0 auto">
    <h2 class="sec-h2" style="text-align:center;margin-bottom:6px">Что специалисты говорят</h2>
    <p class="sec-sub" style="text-align:center">про работу <span style="color:var(--pink);font-weight:700">с нами</span></p>
    <div class="reviews-grid" style="margin-top:40px">
      <div class="review-card"><div class="stars">★★★★★</div><div class="rev-name">Анна</div><div class="rev-from">из Украины</div><div class="rev-stats"><span class="rev-stat">🕐 3 месяца</span><span class="rev-stat rev-earn">+$35,000</span></div><p class="rev-text">Спасибо большое! Заработок превосходит все ожидания. Работаю в премиальном спа в Майами, условия потрясающие.</p></div>
      <div class="review-card"><div class="stars">★★★★★</div><div class="rev-name">Елена</div><div class="rev-from">из России</div><div class="rev-stats"><span class="rev-stat">🕐 5 месяцев</span><span class="rev-stat rev-earn">+$55,000</span></div><p class="rev-text">Работаю с ними уже давно. Стабильный поток клиентов, отличный заработок. Скоро снова поеду в тур по новым городам.</p></div>
      <div class="review-card"><div class="stars">★★★★★</div><div class="rev-name">Мария</div><div class="rev-from">из Беларуси</div><div class="rev-stats"><span class="rev-stat">🕐 2 месяца</span><span class="rev-stat rev-earn">+$22,000</span></div><p class="rev-text">Познакомилась с интересными людьми, побывала в Нью-Йорке и Лос-Анджелесе. На заработанные деньги открыла свой массажный кабинет дома.</p></div>
      <div class="review-card"><div class="stars">★★★★★</div><div class="rev-name">София</div><div class="rev-from">из Молдовы</div><div class="rev-stats"><span class="rev-stat">🕐 4 месяца</span><span class="rev-stat rev-earn">+$42,000</span></div><p class="rev-text">Очень довольна условиями работы. Безопасно, комфортно и прибыльно. Рекомендую всем!</p></div>
    </div>
  </div>
</div>

<!-- FAQ -->
<div style="padding:80px 40px;background:#fff" id="faq">
  <div style="max-width:900px;margin:0 auto">
    <h2 class="sec-h2" style="text-align:center;margin-bottom:48px">Вопросы и <span class="pink">ответы</span></h2>
    <div class="faq-list">
      <div class="faq-item"><div class="faq-q" onclick="toggleFaq(this)"><span>Где вы находитесь?</span><span class="faq-icon">⌄</span></div><div class="faq-a">Мы работаем по всей территории США — Нью-Йорк, Лос-Анджелес, Майами, Чикаго и другие города.</div></div>
      <div class="faq-item"><div class="faq-q" onclick="toggleFaq(this)"><span>Сколько я могу заработать за смену?</span><span class="faq-icon">⌄</span></div><div class="faq-a">В среднем от $500 до $1500+ за смену. Точный доход зависит от города, количества клиентов и вашей активности.</div></div>
      <div class="faq-item"><div class="faq-q" onclick="toggleFaq(this)"><span>Я никогда не работала массажисткой. Смогу ли я?</span><span class="faq-icon">⌄</span></div><div class="faq-a">Да! Мы предоставляем полное обучение с нуля. Опыт не обязателен — главное желание работать.</div></div>
      <div class="faq-item"><div class="faq-q" onclick="toggleFaq(this)"><span>Насколько безопасно у вас работать?</span><span class="faq-icon">⌄</span></div><div class="faq-a">Безопасность — наш приоритет. Все клиенты проходят проверку. Мы обеспечиваем безопасные условия работы.</div></div>
      <div class="faq-item"><div class="faq-q" onclick="toggleFaq(this)"><span>Я боюсь, что у меня не получится, и это меня беспокоит.</span><span class="faq-icon">⌄</span></div><div class="faq-a">Понимаем ваши опасения. Именно поэтому мы предоставляем обучение и постоянную поддержку. Вы не будете одни.</div></div>
      <div class="faq-item"><div class="faq-q" onclick="toggleFaq(this)"><span>Сколько дней в неделю я могу работать?</span><span class="faq-icon">⌄</span></div><div class="faq-a">График полностью гибкий. Работайте столько, сколько хотите — от 2 до 7 дней в неделю.</div></div>
      <div class="faq-item"><div class="faq-q" onclick="toggleFaq(this)"><span>Какие документы нужны для трудоустройства?</span><span class="faq-icon">⌄</span></div><div class="faq-a">Минимум документов. Уточните детали у нашего HR-специалиста в Telegram.</div></div>
      <div class="faq-item"><div class="faq-q" onclick="toggleFaq(this)"><span>Кто ваши клиенты?</span><span class="faq-icon">⌄</span></div><div class="faq-a">Проверенные клиенты премиум-класса. Все проходят предварительный отбор для вашей безопасности.</div></div>
    </div>
  </div>
</div>

<!-- FINAL CTA -->
<div class="final-cta">
  <h2 class="final-h2">Хочешь зарабатывать от 30 000$ в месяц<br>без лишней суеты и забот?</h2>
  <p class="final-sub">Заполняй анкету и меняй свою жизнь.</p>
  <button class="cta-btn white" onclick="openModal()">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.894 8.221l-1.97 9.28c-.145.658-.537.818-1.084.508l-3-2.21-1.447 1.394c-.16.16-.295.295-.605.295l.213-3.053 5.56-5.023c.242-.213-.054-.333-.373-.12l-6.871 4.326-2.962-.924c-.643-.204-.657-.643.136-.953l11.57-4.461c.537-.194 1.006.131.833.941z"/></svg>
    Связаться в Телеграм
  </button>
</div>

<!-- FOOTER -->
<footer class="footer">
  <div class="footer-grid">
    <div>
      <div class="footer-logo"><div class="nav-logo-icon">💆</div> Massage Job USA</div>
      <p class="footer-text">Мы поможем вам адаптироваться и закрыть все финансовые вопросы. Если у вас остались какие-либо вопросы, пишите нашему менеджеру, он поможет вам и ответит на все вопросы.</p>
    </div>
    <div class="footer-col">
      <h4>Навигация</h4>
      <a href="#vacancy">Вакансия</a>
      <a href="#benefits">Преимущества</a>
      <a href="#requirements">Требования</a>
      <a href="#how">Как начать</a>
      <a href="#reviews">Отзывы</a>
    </div>
    <div class="footer-col">
      <h4>Контакты</h4>
      <a onclick="openModal()" style="cursor:pointer">✈️ Telegram</a>
      <a style="color:#888">📍 Вся территория США</a>
    </div>
  </div>
  <div class="footer-bottom">© 2026 Massage Job USA. Все права защищены.</div>
</footer>

<!-- MODAL -->
<div class="modal-overlay" id="contact-modal" onclick="if(event.target===this)closeModal()">
  <div class="modal">
    <button class="modal-close" onclick="closeModal()">✕</button>
    <div class="modal-title">Выбери способ связи</div>
    {all_btns_popup}
  </div>
</div>

<script>
function openModal(){{document.getElementById('contact-modal').classList.add('open');document.body.style.overflow='hidden'}}
function closeModal(){{document.getElementById('contact-modal').classList.remove('open');document.body.style.overflow=''}}
document.addEventListener('keydown',e=>{{if(e.key==='Escape')closeModal()}});
function toggleFaq(el){{
  const ans=el.nextElementSibling;
  const icon=el.querySelector('.faq-icon');
  ans.classList.toggle('open');
  icon.classList.toggle('open');
}}
// Smooth scroll
document.querySelectorAll('a[href^="#"]').forEach(a=>{{
  a.addEventListener('click',e=>{{
    const t=document.querySelector(a.getAttribute('href'));
    if(t){{e.preventDefault();t.scrollIntoView({{behavior:'smooth'}})}}
  }})
}});
</script>
</body></html>""")


@app.get("/page", response_class=HTMLResponse)
async def public_page():
    links = db.get_landing_links()

    # Настройки лендинга из БД (с дефолтами по ТЗ)
    hero_title    = db.get_setting("land_hero_title",    "Relaxation and Balance 🌿✨")
    hero_sub      = db.get_setting("land_hero_sub",      "I invite you to enjoy a soothing body massage in a comfortable, private setting.")
    incl_title    = db.get_setting("land_incl_title",    "Included in the session:")
    utp1          = db.get_setting("land_utp1",          "💆‍♂️ Full body massage")
    utp2          = db.get_setting("land_utp2",          "🤍 Full body contact massage")
    utp3          = db.get_setting("land_utp3",          "🔥 Relaxation completion")
    attire_text   = db.get_setting("land_attire",        "✨ I'll greet you in elegant attire and provide a relaxing massage in comfortable, minimal clothing. Touching me is not allowed.")
    rate1         = db.get_setting("land_rate1",         "60 min — $230")
    rate2         = db.get_setting("land_rate2",         "30 min — $200")
    rate3         = db.get_setting("land_rate3",         "15 min — $140")
    info1         = db.get_setting("land_info1",         "📌 Extra services can only be discussed in person during the session.")
    info2         = db.get_setting("land_info2",         "💵 Payment is accepted in cash only. Please prepare the exact amount.")
    info3         = db.get_setting("land_info3",         "⚠️ Same-day appointments only. Advance bookings are not available.")
    book_cta      = db.get_setting("land_book_cta",      "💌 Message me to book your session!")
    photo_urls    = db.get_setting("land_photo_urls",    "")   # через запятую
    video_urls    = db.get_setting("land_video_urls",    "")   # через запятую

    # Галерея
    photos = [u.strip() for u in photo_urls.split(",") if u.strip()]
    videos = [u.strip() for u in video_urls.split(",") if u.strip()]

    photo_thumbs = "".join(f'<div class="gallery-thumb" onclick="openMedia(\'photo\',{i})"><img src="{u}" alt="photo"/></div>' for i, u in enumerate(photos))
    video_thumbs = "".join(f'<div class="gallery-thumb" onclick="openMedia(\'video\',{i})"><video src="{u}" muted></video><div class="play-icon">▶</div></div>' for i, u in enumerate(videos))

    photo_items_js = "[" + ",".join(f'"{u}"' for u in photos) + "]"
    video_items_js = "[" + ",".join(f'"{u}"' for u in videos) + "]"

    # Кнопки TG каналов для попапа Contact me
    contact_btns = "".join(f'''<a href="{l["tg_link"]}" target="_blank" class="contact-btn">
      <span class="contact-icon">{l["emoji"]}</span>
      <span>{l["title"]}</span>
      <span class="contact-arrow">→</span></a>''' for l in links) or '<p style="text-align:center;color:#94a3b8;padding:20px">Контакты не добавлены — настрой в Лендинг</p>'

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{hero_title}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  :root{{
    --bg:#080b12;--surface:#0f1420;--surface2:#141c2a;
    --border:#1e2a3a;--accent:#c9a96e;--accent2:#e8c99a;
    --text:#f0ece4;--muted:#7a8499;--danger:#e05252;
  }}
  body{{background:var(--bg);color:var(--text);font-family:'Georgia',serif;min-height:100vh;overflow-x:hidden}}
  a{{text-decoration:none;color:inherit}}

  /* ALERT BAR */
  .alert-bar{{background:linear-gradient(90deg,#1a0a0a,#2d1515,#1a0a0a);border-bottom:1px solid #5c1f1f;
    padding:10px 20px;text-align:center;font-size:.82rem;color:#fca5a5;letter-spacing:.04em;
    display:flex;align-items:center;justify-content:center;gap:8px}}

  /* HERO */
  .hero{{padding:60px 24px 48px;text-align:center;position:relative;
    background:radial-gradient(ellipse at 50% 0%,#1a1508 0%,transparent 70%)}}
  .hero::before{{content:'';position:absolute;top:0;left:0;right:0;height:1px;
    background:linear-gradient(90deg,transparent,var(--accent),transparent)}}
  .hero-title{{font-size:clamp(1.6rem,5vw,2.4rem);font-weight:400;letter-spacing:-.01em;
    color:var(--text);margin-bottom:16px;line-height:1.3}}
  .hero-sub{{font-size:1rem;color:var(--muted);max-width:360px;margin:0 auto 32px;line-height:1.7;font-style:italic}}
  .divider{{width:60px;height:1px;background:linear-gradient(90deg,transparent,var(--accent),transparent);
    margin:28px auto}}

  /* SECTIONS */
  .section{{padding:40px 24px;max-width:520px;margin:0 auto}}
  .section-title{{font-size:1.1rem;color:var(--accent);letter-spacing:.08em;text-transform:uppercase;
    margin-bottom:24px;text-align:center;font-family:system-ui;font-weight:600}}

  /* UTP LIST */
  .utp-list{{display:flex;flex-direction:column;gap:12px}}
  .utp-item{{background:var(--surface);border:1px solid var(--border);border-radius:14px;
    padding:16px 20px;font-size:1rem;color:var(--text);display:flex;align-items:center;gap:12px;
    border-left:3px solid var(--accent)}}

  /* ATTIRE */
  .attire-box{{background:var(--surface);border:1px solid var(--border);border-radius:16px;
    padding:20px 24px;font-size:.95rem;color:var(--muted);line-height:1.8;text-align:center;
    font-style:italic}}

  /* GALLERY */
  .media-block{{background:var(--surface);border:1px solid var(--border);border-radius:20px;padding:24px}}
  .media-title{{font-size:1rem;color:var(--text);font-weight:600;margin-bottom:16px;text-align:center}}
  .media-btns{{display:flex;gap:10px;justify-content:center;margin-bottom:16px}}
  .media-btn{{flex:1;max-width:160px;padding:12px;border-radius:12px;border:1px solid var(--border);
    background:var(--surface2);color:var(--text);cursor:pointer;font-size:.9rem;font-family:inherit;
    transition:all .2s;font-weight:600}}
  .media-btn:hover,.media-btn.active{{background:var(--accent);border-color:var(--accent);color:#000}}
  .gallery-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;display:none}}
  .gallery-grid.active{{display:grid}}
  .gallery-thumb{{aspect-ratio:1;border-radius:10px;overflow:hidden;cursor:pointer;position:relative;
    background:var(--surface2);border:1px solid var(--border)}}
  .gallery-thumb img,.gallery-thumb video{{width:100%;height:100%;object-fit:cover;transition:.2s}}
  .gallery-thumb:hover img,.gallery-thumb:hover video{{transform:scale(1.05)}}
  .play-icon{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
    font-size:1.8rem;color:rgba(255,255,255,.85);pointer-events:none}}

  /* RATES */
  .rates-list{{display:flex;flex-direction:column;gap:10px}}
  .rate-item{{display:flex;justify-content:space-between;align-items:center;
    padding:16px 20px;background:var(--surface);border:1px solid var(--border);border-radius:14px}}
  .rate-dur{{font-size:.95rem;color:var(--muted)}}
  .rate-price{{font-size:1.15rem;font-weight:700;color:var(--accent)}}

  /* IMPORTANT */
  .info-box{{background:linear-gradient(135deg,#0f1a0f,#0a1208);border:1px solid #2d4a2d;
    border-radius:16px;padding:24px}}
  .info-title{{font-size:.85rem;font-weight:700;color:#86efac;letter-spacing:.1em;
    text-transform:uppercase;margin-bottom:16px}}
  .info-item{{display:flex;gap:12px;padding:10px 0;border-bottom:1px solid #1a2a1a;
    font-size:.9rem;color:#a7c4a7;line-height:1.6}}
  .info-item:last-child{{border-bottom:none}}

  /* CTA BOOK */
  .book-cta{{text-align:center;padding:32px 24px;font-size:1.1rem;color:var(--accent);
    font-style:italic;letter-spacing:.02em}}

  /* CONTACT SECTION */
  .contact-section{{padding:40px 24px 60px;max-width:520px;margin:0 auto}}
  .contact-title{{font-size:1.3rem;color:var(--text);text-align:center;margin-bottom:24px;font-weight:400}}
  .contact-btn{{display:flex;align-items:center;gap:14px;background:var(--surface);
    border:1px solid var(--border);border-radius:16px;padding:18px 22px;margin-bottom:10px;
    transition:all .2s;color:var(--text);font-size:.95rem}}
  .contact-btn:hover{{background:var(--surface2);border-color:var(--accent);transform:translateX(4px)}}
  .contact-icon{{font-size:1.5rem;flex-shrink:0}}
  .contact-arrow{{margin-left:auto;color:var(--accent);font-size:1.1rem}}

  /* CTA BUTTON */
  .cta-wrap{{text-align:center;margin:28px 0}}
  .cta-btn{{display:inline-block;background:linear-gradient(135deg,var(--accent),var(--accent2));
    color:#0a0a0a;font-weight:700;padding:15px 40px;border-radius:50px;font-size:1rem;
    cursor:pointer;border:none;font-family:inherit;letter-spacing:.03em;transition:all .2s;
    box-shadow:0 4px 24px rgba(201,169,110,.25)}}
  .cta-btn:hover{{transform:translateY(-2px);box-shadow:0 8px 32px rgba(201,169,110,.4)}}

  /* POPUP MODAL */
  .modal-overlay{{position:fixed;inset:0;background:rgba(0,0,0,.92);z-index:100;
    display:none;align-items:center;justify-content:center;padding:20px}}
  .modal-overlay.open{{display:flex}}
  .modal{{background:var(--surface);border:1px solid var(--border);border-radius:20px;
    width:100%;max-width:460px;padding:28px 24px;position:relative;max-height:90vh;overflow-y:auto}}
  .modal-close{{position:absolute;top:16px;right:16px;background:var(--surface2);border:1px solid var(--border);
    border-radius:50%;width:32px;height:32px;display:flex;align-items:center;justify-content:center;
    cursor:pointer;color:var(--muted);font-size:1.1rem;line-height:1}}
  .modal-title{{font-size:1.15rem;color:var(--text);margin-bottom:20px;font-weight:600}}

  /* LIGHTBOX */
  .lightbox{{position:fixed;inset:0;background:rgba(0,0,0,.97);z-index:200;
    display:none;align-items:center;justify-content:center;flex-direction:column}}
  .lightbox.open{{display:flex}}
  .lightbox img,.lightbox video{{max-width:95vw;max-height:80vh;border-radius:12px;object-fit:contain}}
  .lightbox-close{{position:absolute;top:20px;right:20px;color:#fff;font-size:2rem;cursor:pointer;
    background:rgba(255,255,255,.1);border-radius:50%;width:44px;height:44px;
    display:flex;align-items:center;justify-content:center}}
  .lightbox-nav{{display:flex;gap:16px;margin-top:16px}}
  .lightbox-nav button{{background:rgba(255,255,255,.12);border:none;color:#fff;padding:10px 24px;
    border-radius:50px;cursor:pointer;font-size:.95rem}}
  .lightbox-nav button:hover{{background:rgba(255,255,255,.2)}}
</style>
</head>
<body>

<!-- БЛОК 1: Alert bar -->
<div class="alert-bar">⚠️ No Fake Service &nbsp;💯</div>

<!-- БЛОК 2-3: Hero -->
<div class="hero">
  <div class="divider"></div>
  <h1 class="hero-title">{hero_title}</h1>
  <p class="hero-sub">{hero_sub}</p>
  <!-- БЛОК 4: CTA -->
  <div class="cta-wrap">
    <button class="cta-btn" onclick="openContact()">Contact me</button>
  </div>
  <div class="divider"></div>
</div>

<!-- БЛОК 5-6: Included -->
<div class="section">
  <div class="section-title">{incl_title}</div>
  <div class="utp-list">
    <div class="utp-item">{utp1}</div>
    <div class="utp-item">{utp2}</div>
    <div class="utp-item">{utp3}</div>
  </div>
</div>

<!-- БЛОК 7: Attire description -->
<div class="section" style="padding-top:0">
  <div class="attire-box">{attire_text}</div>
</div>

<!-- БЛОК 8: Photos & Videos -->
<div class="section" style="padding-top:0">
  <div class="media-block">
    <div class="media-title">📸 Photos and videos</div>
    <div class="media-btns">
      <button class="media-btn" id="btn-video" onclick="showGallery('video')">🎬 Видео</button>
      <button class="media-btn" id="btn-photo" onclick="showGallery('photo')">📷 Фото</button>
    </div>
    <div class="gallery-grid" id="grid-photo">{photo_thumbs if photo_thumbs else '<div style="color:var(--muted);text-align:center;padding:20px;grid-column:1/-1">Фото не добавлены</div>'}</div>
    <div class="gallery-grid" id="grid-video">{video_thumbs if video_thumbs else '<div style="color:var(--muted);text-align:center;padding:20px;grid-column:1/-1">Видео не добавлены</div>'}</div>
  </div>
</div>

<!-- БЛОК 9: CTA -->
<div class="cta-wrap">
  <button class="cta-btn" onclick="openContact()">Contact me</button>
</div>

<!-- БЛОК 10: Rates -->
<div class="section">
  <div class="section-title">💰 Rates:</div>
  <div class="rates-list">
    <div class="rate-item"><span class="rate-dur">{rate1.split("—")[0].strip() if "—" in rate1 else rate1}</span><span class="rate-price">{rate1.split("—")[1].strip() if "—" in rate1 else ""}</span></div>
    <div class="rate-item"><span class="rate-dur">{rate2.split("—")[0].strip() if "—" in rate2 else rate2}</span><span class="rate-price">{rate2.split("—")[1].strip() if "—" in rate2 else ""}</span></div>
    <div class="rate-item"><span class="rate-dur">{rate3.split("—")[0].strip() if "—" in rate3 else rate3}</span><span class="rate-price">{rate3.split("—")[1].strip() if "—" in rate3 else ""}</span></div>
  </div>
</div>

<!-- БЛОК 11: CTA -->
<div class="cta-wrap">
  <button class="cta-btn" onclick="openContact()">Contact me</button>
</div>

<!-- БЛОК 12: Important Information -->
<div class="section">
  <div class="info-box">
    <div class="info-title">Important Information</div>
    <div class="info-item">{info1}</div>
    <div class="info-item">{info2}</div>
    <div class="info-item">{info3}</div>
  </div>
</div>

<!-- БЛОК 13: Book CTA text -->
<div class="book-cta">{book_cta}</div>

<!-- БЛОК 14-15: Contact me section -->
<div class="contact-section" id="contact">
  <div class="divider"></div>
  <h2 class="contact-title">Contact me:</h2>
  <button class="cta-btn" style="display:block;width:100%;margin-bottom:0;border-radius:16px" onclick="openContact()">📩 Contact me</button>
</div>

<!-- ПОПАП Contact me -->
<div class="modal-overlay" id="contact-modal" onclick="if(event.target===this)closeContact()">
  <div class="modal">
    <div class="modal-close" onclick="closeContact()">✕</div>
    <div class="modal-title">📩 Contact me</div>
    {contact_btns}
  </div>
</div>

<!-- LIGHTBOX для галереи -->
<div class="lightbox" id="lightbox">
  <div class="lightbox-close" onclick="closeLightbox()">✕</div>
  <div id="lightbox-content"></div>
  <div class="lightbox-nav">
    <button onclick="prevMedia()">← Пред</button>
    <button onclick="nextMedia()">След →</button>
  </div>
</div>

<script>
  // Contact popup
  function openContact(){{document.getElementById('contact-modal').classList.add('open');document.body.style.overflow='hidden'}}
  function closeContact(){{document.getElementById('contact-modal').classList.remove('open');document.body.style.overflow=''}}
  document.addEventListener('keydown',e=>{{if(e.key==='Escape'){{closeContact();closeLightbox();}}}});

  // Gallery tabs
  function showGallery(type){{
    document.getElementById('grid-photo').classList.toggle('active', type==='photo');
    document.getElementById('grid-video').classList.toggle('active', type==='video');
    document.getElementById('btn-photo').classList.toggle('active', type==='photo');
    document.getElementById('btn-video').classList.toggle('active', type==='video');
  }}

  // Lightbox
  const PHOTOS = {photo_items_js};
  const VIDEOS = {video_items_js};
  let _mediaType='photo', _mediaIdx=0;
  function openMedia(type, idx){{
    _mediaType=type; _mediaIdx=idx;
    renderLightbox();
    document.getElementById('lightbox').classList.add('open');
    document.body.style.overflow='hidden';
  }}
  function renderLightbox(){{
    const arr = _mediaType==='photo'?PHOTOS:VIDEOS;
    const url = arr[_mediaIdx];
    const el = document.getElementById('lightbox-content');
    if(_mediaType==='photo'){{
      el.innerHTML=`<img src="${{url}}" alt="photo"/>`;
    }} else {{
      el.innerHTML=`<video src="${{url}}" controls autoplay style="max-width:95vw;max-height:80vh;border-radius:12px"></video>`;
    }}
  }}
  function closeLightbox(){{
    document.getElementById('lightbox').classList.remove('open');
    document.body.style.overflow='';
    document.getElementById('lightbox-content').innerHTML='';
  }}
  function prevMedia(){{const arr=_mediaType==='photo'?PHOTOS:VIDEOS;_mediaIdx=(_mediaIdx-1+arr.length)%arr.length;renderLightbox();}}
  function nextMedia(){{const arr=_mediaType==='photo'?PHOTOS:VIDEOS;_mediaIdx=(_mediaIdx+1)%arr.length;renderLightbox();}}
</script>
</body></html>""")


@app.get("/flow_clients", response_class=HTMLResponse)
async def flow_clients(request: Request, msg: str = ""):
    user, err = require_auth(request)
    if err: return err
    return HTMLResponse(base(await _flow_content("tracker", "flow_clients", "💬 Msg Flow — Клиенты", "Автосообщения после вступления в канал", msg), "flow_clients", request))


@app.get("/flow_staff", response_class=HTMLResponse)
async def flow_staff(request: Request, msg: str = ""):
    user, err = require_auth(request)
    if err: return err
    return HTMLResponse(base(await _flow_content("staff", "flow_staff", "💬 Msg Flow — HR", "Автосообщения новым сотрудникам", msg), "flow_staff", request))


async def _flow_content(bot_type, page, title, sub, msg):
    channels = db.get_channels()
    flows    = db.get_flows(bot_type=bot_type)
    ch_opts  = "".join(f'<option value="{c["channel_id"]}">{c["name"]}</option>' for c in channels) or '<option value="all">Все</option>'
    ch_map   = {c["channel_id"]: c["name"] for c in channels}
    btn = "btn" if bot_type == "tracker" else "btn-orange"
    rows = "".join(f"""<tr><td><span class="badge">{ch_map.get(f['channel_id'],f['channel_id'])}</span></td>
        <td>Шаг {f['step']}</td><td>{f['delay_min']} мин</td>
        <td style="max-width:300px">{f['message'][:80]}{'…' if len(f['message'])>80 else ''}</td>
        <td><form method="post" action="/flow/delete?next={page}"><input type="hidden" name="flow_id" value="{f['id']}"/>
        <button class="del-btn">✕</button></form></td></tr>""" for f in flows
    ) or '<tr><td colspan="5"><div class="empty">Нет шагов</div></td></tr>'
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""
    return f"""<div class="page-wrap"><div class="page-title">{title}</div><div class="page-sub">{sub}</div>
    <div class="section"><div class="section-head"><h3>➕ Добавить шаг</h3></div><div class="section-body">
    {alert}<form method="post" action="/flow/add?next={page}">
    <input type="hidden" name="bot_type" value="{bot_type}"/>
    <div class="form-row" style="margin-bottom:12px">
    <div class="field-group"><div class="field-label">Канал</div><select name="channel_id">{ch_opts}</select></div>
    <div class="field-group" style="max-width:100px"><div class="field-label">Шаг №</div><input type="number" name="step" value="0" min="0"/></div>
    <div class="field-group" style="max-width:160px"><div class="field-label">Задержка (мин)</div><input type="number" name="delay_min" value="0" min="0"/></div></div>
    <div class="field-group" style="margin-bottom:12px"><div class="field-label">Текст</div>
    <textarea name="message" placeholder="Текст автосообщения..." required></textarea></div>
    <button class="{btn}">Добавить шаг</button></form></div></div>
    <div class="section"><div class="section-head"><h3>📋 Шаги ({len(flows)})</h3></div>
    <table><thead><tr><th>Канал</th><th>Шаг</th><th>Задержка</th><th>Сообщение</th><th></th></tr></thead>
    <tbody>{rows}</tbody></table></div></div>"""


@app.post("/flow/add")
async def flow_add(request: Request, next: str = "flow_clients", channel_id: str = Form(...),
                   bot_type: str = Form("tracker"), step: int = Form(0), delay_min: int = Form(0), message: str = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.add_flow_step(channel_id, bot_type, step, delay_min, message)
    return RedirectResponse(f"/{next}?msg=Шаг+добавлен", 303)


@app.post("/flow/delete")
async def flow_delete(request: Request, next: str = "flow_clients", flow_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.delete_flow_step(flow_id)
    return RedirectResponse(f"/{next}", 303)


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


@app.get("/api/conversations")
async def api_conversations(request: Request):
    user = check_session(request)
    if not user: return JSONResponse({"error": "unauthorized"}, 401)
    return JSONResponse({"conversations": db.get_conversations()})


@app.get("/api/wa_conversations")
async def api_wa_conversations(request: Request):
    user = check_session(request)
    if not user: return JSONResponse({"error": "unauthorized"}, 401)
    return JSONResponse({"conversations": db.get_wa_conversations()})


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
    wa_active_name = ""
    if conv_id:
        active_conv = db.get_wa_conversation(conv_id)
        if active_conv:
            wa_active_name = (active_conv.get('visitor_name') or '').replace('"','')
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
    const WA_ACTIVE_ID={conv_id};
    const WA_ACTIVE_NAME="{wa_active_name}";
    let _waSnap={{}};
    let _firstWaMsgLoad=true;

    // Единый цикл: обновляем список + сообщения каждые 3с
    setInterval(waPollAll,3000);
    async function waPollAll(){{
      await refreshWaConvList();
      if(WA_ACTIVE_ID) await loadNewWaMsgs();
    }}

    // Умное обновление WA списка диалогов (без мерцания)
    async function refreshWaConvList(){{
      try{{
        const r=await fetch('/api/wa_conversations');
        const d=await r.json();
        if(!d.conversations) return;
        let changed=false;
        const ids=new Set(d.conversations.map(c=>c.id));
        d.conversations.forEach(c=>{{
          const p=_waSnap[c.id];
          if(!p||p.u!==c.unread_count||p.m!==c.last_message||p.s!==c.status){{
            changed=true;_waSnap[c.id]={{u:c.unread_count,m:c.last_message,s:c.status}};
          }}
        }});
        for(const id in _waSnap)if(!ids.has(+id)){{changed=true;delete _waSnap[id];}}
        if(changed){{
          const q=(document.querySelector('.conv-search input')?.value||'').toLowerCase();
          let html='';
          d.conversations.forEach(c=>{{
            const cls='conv-item'+(c.id===WA_ACTIVE_ID?' active':'');
            const t=(c.last_message_at||c.created_at).substring(0,16).replace('T',' ');
            const unum=c.unread_count>0?`<span class="unread-num" style="background:#25d366">${{c.unread_count}}</span>`:'';
            const dot=c.status==='open'?'🟢':'⚫';
            const name=esc(c.visitor_name||'');
            const preview=esc(c.last_message||'Нет сообщений');
            const vis=!q||name.toLowerCase().includes(q);
            html+=`<a href="/wa/chat?conv_id=${{c.id}}" style="${{vis?'':'display:none'}}"><div class="${{cls}}">
              <div class="conv-name"><span>${{dot}} ${{name}}</span>${{unum}}</div>
              <div class="conv-preview">${{preview}}</div>
              <div class="conv-time">💚 +${{c.wa_number||''}} · ${{t}}</div></div></a>`;
          }});
          if(!html)html='<div class="empty" style="padding:36px 14px">Нет WA диалогов.<br><br>Подключи WhatsApp<br>в разделе WA Настройка</div>';
          document.getElementById('conv-items').innerHTML=html;
        }}
      }}catch(e){{}}
    }}

    async function sendWaMsg(){{
      const ta=document.getElementById('wa-reply');
      const text=ta.value.trim(); if(!text) return; ta.value='';
      await fetch('/wa/send',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},
        body:'conv_id={conv_id}&text='+encodeURIComponent(text)}});
      await loadNewWaMsgs();
    }}
    function handleWaKey(e){{if(e.key==='Enter'&&!e.shiftKey){{e.preventDefault();sendWaMsg();}}}}
    async function loadNewWaMsgs(){{
      const msgs=document.querySelectorAll('#wa-msgs .msg[data-id]');
      const lastId=msgs.length?msgs[msgs.length-1].dataset.id:0;
      const res=await fetch('/api/wa_messages/{conv_id}?after='+lastId);
      const data=await res.json();
      if(data.messages&&data.messages.length>0){{
        const c=document.getElementById('wa-msgs');
        const incoming=data.messages.filter(m=>m.sender_type==='visitor');
        if(!_firstWaMsgLoad&&incoming.length>0&&typeof playNotifySound!=='undefined'){{
          playNotifySound('wa');
          showToast(WA_ACTIVE_NAME,incoming[incoming.length-1].content,'wa');
        }}
        data.messages.forEach(m=>{{const d=document.createElement('div');d.className='msg '+m.sender_type;d.dataset.id=m.id;
          d.innerHTML='<div class="msg-bubble">'+esc(m.content)+'</div><div class="msg-time">'+m.created_at.substring(11,16)+'</div>';
          c.appendChild(d);}});c.scrollTop=c.scrollHeight;
        _firstWaMsgLoad=false;
      }} else {{ _firstWaMsgLoad=false; }}
    }}
    function esc(t){{return(t||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\\n/g,'<br>');}}
    function filterConvs(q){{document.querySelectorAll('.conv-item').forEach(el=>{{
      const n=el.querySelector('.conv-name')?.textContent?.toLowerCase()||'';
      el.parentElement.style.display=n.includes(q.toLowerCase())?'':'none';}});}}
    </script>"""
    return HTMLResponse(f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>WA Чаты</title>{CSS}</head><body>{nav_html("wa_chat",request)}<div class="main">{content}</div>{NOTIFY_JS}</body></html>')


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
