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
      {item("💬", "Msg Flow", "flow_clients", "blue")}
      <div class="nav-divider"></div>
      <div class="nav-section">👔 Сотрудники</div>
      {item("💬", "Чаты", "chat", "orange", badge=True)}
      {item("🗂", "База", "staff", "orange")}
      {item("💬", "Msg Flow HR", "flow_staff", "orange")}
      {admin_section}
      <div class="sidebar-footer">
        <div class="bot-status"><div class="dot {'dot-green' if b1 else 'dot-red'}"></div><span>{b1_name}</span></div>
        <div class="bot-status"><div class="dot {'dot-green' if b2 else 'dot-red'}"></div><span>{b2_name}</span></div>
        <a href="/logout"><div style="padding:8px 10px;font-size:.76rem;color:#475569;cursor:pointer">⬅ Выйти</div></a>
      </div>
    </div>"""


def base(content: str, active: str, request: Request) -> str:
    return f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>TG Tracker</title>{CSS}</head><body>{nav_html(active, request)}<div class="main">{content}</div></body></html>'


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
    async function sendMsg(){{
      const ta=document.getElementById('reply-text');
      const text=ta.value.trim(); if(!text) return; ta.value='';
      await fetch('/chat/send',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:'conv_id={conv_id}&text='+encodeURIComponent(text)}});
      loadNewMsgs();
    }}
    function handleKey(e){{if(e.key==='Enter'&&!e.shiftKey){{e.preventDefault();sendMsg();}}}}
    {"setInterval(loadNewMsgs,3000);" if active_conv else "setInterval(checkUnread,5000);"}
    async function loadNewMsgs(){{
      const msgs=document.querySelectorAll('.msg[data-id]');
      const lastId=msgs.length?msgs[msgs.length-1].dataset.id:0;
      const res=await fetch('/api/messages/{conv_id}?after='+lastId);
      const data=await res.json();
      if(data.messages&&data.messages.length>0){{
        const c=document.getElementById('msgs');
        data.messages.forEach(m=>{{const d=document.createElement('div');d.className='msg '+m.sender_type;d.dataset.id=m.id;
          d.innerHTML='<div class="msg-bubble">'+esc(m.content)+'</div><div class="msg-time">'+m.created_at.substring(11,16)+'</div>';
          c.appendChild(d);}});c.scrollTop=c.scrollHeight;}}
    }}
    async function checkUnread(){{
      const r=await fetch('/api/stats');const d=await r.json();
      const b=document.querySelector('.badge-count');
      if(d.unread>0){{if(b)b.textContent=d.unread;}}else if(b)b.remove();
    }}
    function esc(t){{return(t||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\\n/g,'<br>');}}
    function filterConvs(q){{document.querySelectorAll('.conv-item').forEach(el=>{{
      const n=el.querySelector('.conv-name')?.textContent?.toLowerCase()||'';
      el.parentElement.style.display=n.includes(q.toLowerCase())?'':'none';}});}}
    </script>"""

    return HTMLResponse(f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>Чаты</title>{CSS}</head><body>{nav_html("chat",request)}<div class="main">{content}</div></body></html>')


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
    rows = "".join(f"""<tr><td style="font-size:1.2rem">{l['emoji']}</td><td><b>{l['title']}</b></td>
        <td><a href="{l['tg_link']}" target="_blank" style="color:#60a5fa">{l['tg_link']}</a></td>
        <td><form method="post" action="/landing/delete"><input type="hidden" name="link_id" value="{l['id']}"/>
        <button class="del-btn">✕</button></form></td></tr>""" for l in links
    ) or '<tr><td colspan="4"><div class="empty">Нет ссылок</div></td></tr>'
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""
    content = f"""<div class="page-wrap"><div class="page-title">🌐 Лендинг</div>
    <div class="page-sub">Публичная страница: <a href="/page" target="_blank" style="color:#3b82f6">/page →</a></div>
    <div class="section"><div class="section-head"><h3>➕ Добавить кнопку</h3></div><div class="section-body">
    {alert}<form method="post" action="/landing/add"><div class="form-row">
    <div class="field-group" style="max-width:80px"><div class="field-label">Эмодзи</div><input type="text" name="emoji" value="📢"/></div>
    <div class="field-group"><div class="field-label">Название</div><input type="text" name="title" placeholder="Phoenix" required/></div>
    <div class="field-group"><div class="field-label">Ссылка TG</div><input type="text" name="tg_link" placeholder="https://t.me/+xxx" required/></div>
    <div style="display:flex;align-items:flex-end"><button class="btn">Добавить</button></div>
    </div></form></div></div>
    <div class="section"><div class="section-head"><h3>🔗 Кнопки ({len(links)}/10)</h3></div>
    <table><thead><tr><th></th><th>Название</th><th>Ссылка</th><th></th></tr></thead>
    <tbody>{rows}</tbody></table></div></div>"""
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


@app.get("/page", response_class=HTMLResponse)
async def public_page():
    links = db.get_landing_links()
    title = db.get_setting("landing_title", "Наши каналы")
    sub   = db.get_setting("landing_subtitle", "Подписывайся и будь в курсе")
    btns  = "".join(f'<a href="{l["tg_link"]}" target="_blank" class="ch-btn"><span style="font-size:1.4rem">{l["emoji"]}</span><span style="flex:1;font-weight:600;color:#fff">{l["title"]}</span><span style="color:#3b82f6">→</span></a>' for l in links) or '<p style="text-align:center;color:#475569">Скоро</p>'
    return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
    <style>*{{box-sizing:border-box;margin:0;padding:0}}body{{background:#0a0d14;min-height:100vh;display:flex;align-items:center;justify-content:center;font-family:system-ui;padding:24px}}
    .wrap{{width:100%;max-width:420px}}h1{{font-size:1.5rem;font-weight:700;text-align:center;margin-bottom:8px;color:#fff}}
    .sub{{text-align:center;color:#475569;font-size:.9rem;margin-bottom:28px}}
    .ch-btn{{display:flex;align-items:center;gap:14px;background:#111827;border:1px solid #1a2030;border-radius:14px;padding:16px 20px;margin-bottom:10px;transition:all .2s;text-decoration:none}}
    .ch-btn:hover{{background:#1a2030;border-color:#3b82f6;transform:translateY(-2px)}}</style></head>
    <body><div class="wrap"><h1>{title}</h1><p class="sub">{sub}</p>{btns}</div></body></html>""")


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


@app.get("/health")
async def health():
    return {"status": "ok", "version": "5.0",
            "bot1": bool(bot_manager.get_tracker_bot()),
            "bot2": bool(bot_manager.get_staff_bot())}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
