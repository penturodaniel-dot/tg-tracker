import asyncio
import hashlib
import logging
import os
from contextlib import asynccontextmanager
from urllib.parse import urlencode, quote

from fastapi import FastAPI, Request, Form, Cookie, File, UploadFile
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


def require_auth(request: Request, role: str = None, tab: str = None):
    user = check_session(request)
    if not user:
        return None, RedirectResponse("/login", 303)
    if role and user["role"] != role and user["role"] != "admin":
        return None, HTMLResponse("<h2>Нет доступа</h2>", 403)
    # Проверяем доступ к вкладке для менеджеров
    if tab and user["role"] != "admin":
        perms = user.get("permissions", "") or ""
        allowed = [p.strip() for p in perms.split(",") if p.strip()]
        if allowed and tab not in allowed:
            return None, HTMLResponse(f'<html><body style="background:var(--bg);color:var(--text);font-family:Inter,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;flex-direction:column;gap:12px"><div style="font-size:2rem">🚫</div><div style="font-size:1.1rem;font-weight:600">Нет доступа к этому разделу</div><a href="/" style="color:var(--orange);font-size:.9rem">← Назад</a></body></html>', 403)
    return user, None


# ══════════════════════════════════════════════════════════════════════════════
# CSS
# ══════════════════════════════════════════════════════════════════════════════

CSS = """<style>
/* ═══════════════════════════════════════════════════
   DARK PRO — design system
   palette: bg #080c14 · surface #0e1320 · card #111827
            border #1c2438 · text #e2e8f0 · muted #4b5675
            orange #f97316 · blue #3b82f6 · green #22c55e
   ═══════════════════════════════════════════════════ */
:root{
  --bg:     #080c14;
  --bg2:    #0e1320;
  --bg3:    #111827;
  --border: #1c2438;
  --border2:#242d42;
  --text:   #e2e8f0;
  --text2:  #94a3b8;
  --text3:  #4b5675;
  --orange: #f97316;
  --orange2:#ea580c;
  --blue:   #3b82f6;
  --blue2:  #2563eb;
  --green:  #22c55e;
  --red:    #f87171;
  --radius: 10px;
  --radius-sm:6px;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;font-size:14px;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}

/* ── SIDEBAR ─────────────────────────────────────── */
.sidebar{position:fixed;top:0;left:0;width:224px;height:100vh;background:var(--bg2);border-right:1px solid var(--border);display:flex;flex-direction:column;z-index:10;overflow-y:auto}
.logo{padding:18px 16px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;flex-shrink:0}
.logo-brand{font-size:.97rem;font-weight:700;color:var(--text);letter-spacing:-.01em}
.logo-user{font-size:.72rem;color:var(--text3);margin-top:2px;font-weight:400}
.logo-right{display:flex;align-items:center;gap:6px}
.theme-toggle{cursor:pointer;font-size:1rem;padding:4px;border-radius:6px;transition:background .15s;color:var(--text3)}
.theme-toggle:hover{background:var(--border)}
.nav-section{padding:16px 16px 5px;font-size:.65rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--text3)}
.nav-divider{height:1px;background:var(--border);margin:6px 0}
.nav-item{display:flex;align-items:center;justify-content:space-between;padding:8px 12px;font-size:.82rem;color:var(--text3);border-radius:var(--radius-sm);margin:1px 8px;transition:all .12s;cursor:pointer}
.nav-item:hover{background:var(--bg3);color:var(--text2)}
.nav-item.active{background:var(--bg3);color:var(--text);font-weight:600}
.nav-item.active.blue{border-left:2px solid var(--blue);padding-left:10px;margin-left:6px}
.nav-item.active.orange{border-left:2px solid var(--orange);padding-left:10px;margin-left:6px}
.nav-label{display:flex;align-items:center;gap:8px}
.badge-count{background:var(--red);color:#fff;border-radius:99px;padding:0 6px;font-size:.67rem;font-weight:700;min-width:18px;height:16px;display:inline-flex;align-items:center;justify-content:center}
.sidebar-footer{margin-top:auto;padding:12px 10px;border-top:1px solid var(--border)}
.bot-status{display:flex;align-items:center;gap:7px;padding:5px 8px;border-radius:6px;margin-bottom:3px;font-size:.73rem;color:var(--text3)}
.dot{width:6px;height:6px;border-radius:50%;flex-shrink:0}
.dot-green{background:var(--green)}.dot-red{background:var(--red)}.dot-yellow{background:#fbbf24}
.main{margin-left:224px}

/* ── PAGE HEADER ─────────────────────────────────── */
.page-wrap{padding:26px 28px;max-width:1140px}
.page-title{font-size:1.25rem;font-weight:700;color:var(--text);margin-bottom:3px;letter-spacing:-.01em}
.page-sub{font-size:.8rem;color:var(--text3);margin-bottom:22px}

/* ── KPI CARDS ───────────────────────────────────── */
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:20px}
.card{background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius);padding:16px 18px;position:relative;overflow:hidden}
.card::after{content:"";position:absolute;top:0;left:0;right:0;height:2px;border-radius:var(--radius) var(--radius) 0 0}
.card.c-orange::after{background:var(--orange)}
.card.c-blue::after{background:var(--blue)}
.card.c-green::after{background:var(--green)}
.card.c-red::after{background:var(--red)}
.card .val{font-size:1.75rem;font-weight:700;color:var(--text);margin-bottom:4px;line-height:1}
.card .val.orange{color:var(--orange)}.card .val.green{color:var(--green)}.card .val.red{color:var(--red)}.card .val.blue{color:var(--blue)}
.card .lbl{font-size:.73rem;color:var(--text3);font-weight:500}
.card .sub{font-size:.69rem;color:var(--text3);margin-top:3px}

/* ── SECTIONS ────────────────────────────────────── */
.section{background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius);margin-bottom:14px;overflow:hidden}
.section-head{padding:12px 18px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center}
.section-head h3{font-size:.88rem;font-weight:600;color:var(--text)}
.section-body{padding:16px 18px}

/* ── TABLE ───────────────────────────────────────── */
table{width:100%;border-collapse:collapse}
th{padding:8px 13px;text-align:left;font-size:.68rem;text-transform:uppercase;letter-spacing:.07em;color:var(--text3);border-bottom:1px solid var(--border);font-weight:600}
td{padding:10px 13px;font-size:.82rem;border-bottom:1px solid var(--border);color:var(--text2)}
tr:last-child td{border-bottom:none}
tr:hover td{background:rgba(255,255,255,.012)}

/* ── BADGES ──────────────────────────────────────── */
.badge{display:inline-flex;align-items:center;padding:2px 8px;border-radius:99px;font-size:.71rem;font-weight:600;background:#1e3a5f;color:#60a5fa}
.badge-orange{background:#431407;color:#fb923c}
.badge-green{background:#052e16;color:#34d399}
.badge-red{background:#2d0a0a;color:var(--red)}
.badge-gray{background:#1c2438;color:var(--text3)}
.badge-yellow{background:#422006;color:#fbbf24}

/* ── FORMS ───────────────────────────────────────── */
form{display:contents}
.form-row{display:flex;gap:10px;flex-wrap:wrap}
.field-group{display:flex;flex-direction:column;gap:5px;flex:1;min-width:0}
.field-label{font-size:.7rem;color:var(--text3);font-weight:600;text-transform:uppercase;letter-spacing:.05em}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.grid-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}
input[type=text],input[type=number],input[type=email],input[type=password],select,textarea{
  background:var(--bg);border:1px solid var(--border2);border-radius:var(--radius-sm);
  padding:8px 12px;color:var(--text);font-size:.84rem;outline:none;width:100%;
  font-family:inherit;transition:border-color .15s}
input:focus,select:focus,textarea:focus{border-color:var(--orange)}
select option{background:var(--bg3)}
textarea{resize:vertical;min-height:80px;line-height:1.5}

/* ── BUTTONS ─────────────────────────────────────── */
.btn{display:inline-flex;align-items:center;gap:6px;background:var(--blue);color:#fff;border:none;border-radius:var(--radius-sm);padding:8px 16px;cursor:pointer;font-size:.83rem;font-weight:600;white-space:nowrap;font-family:inherit;transition:background .15s}
.btn:hover{background:var(--blue2)}
.btn-orange{background:var(--orange);color:#fff;border:none;border-radius:var(--radius-sm);padding:8px 16px;cursor:pointer;font-size:.83rem;font-weight:600;font-family:inherit;transition:background .15s}
.btn-orange:hover{background:var(--orange2)}
.btn-red{background:#dc2626;color:#fff;border:none;border-radius:var(--radius-sm);padding:8px 16px;cursor:pointer;font-size:.83rem;font-weight:600;font-family:inherit}
.btn-red:hover{background:#b91c1c}
.btn-gray{background:var(--bg);border:1px solid var(--border2);color:var(--text2);border-radius:var(--radius-sm);padding:8px 16px;cursor:pointer;font-size:.83rem;font-weight:500;font-family:inherit;transition:all .12s}
.btn-gray:hover{border-color:var(--text3);color:var(--text)}
.btn-green{background:#15803d;color:#fff;border:none;border-radius:var(--radius-sm);padding:8px 16px;cursor:pointer;font-size:.83rem;font-weight:600;font-family:inherit}
.btn-green:hover{background:#166534}
.btn-sm{padding:4px 10px;font-size:.75rem;border-radius:5px}
.del-btn{background:none;border:none;cursor:pointer;color:var(--red);font-size:.8rem;padding:4px 8px;border-radius:4px;transition:background .12s}
.del-btn:hover{background:#2d0a0a}

/* ── ALERTS ──────────────────────────────────────── */
.alert-green{background:#052e16;border:1px solid #166534;border-left:3px solid var(--green);border-radius:var(--radius-sm);padding:10px 14px;color:#86efac;margin-bottom:14px;font-size:.83rem}
.alert-red{background:#2d0a0a;border:1px solid #7f1d1d;border-left:3px solid var(--red);border-radius:var(--radius-sm);padding:10px 14px;color:#fca5a5;margin-bottom:14px;font-size:.83rem}
.empty{text-align:center;padding:32px;color:var(--text3);font-size:.84rem}
.link-box{background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 12px;font-family:'Courier New',monospace;font-size:.75rem;word-break:break-all;color:#67e8f9}
.tag{display:inline-block;background:var(--border);border-radius:4px;padding:2px 7px;font-size:.7rem;color:var(--text3);font-family:monospace}

/* ── CHAT ────────────────────────────────────────── */
.chat-layout{display:grid;grid-template-columns:300px 1fr;height:100vh}
.conv-list{background:var(--bg2);border-right:1px solid var(--border);overflow-y:auto;display:flex;flex-direction:column}
.conv-search{padding:12px;border-bottom:1px solid var(--border)}
.conv-search input{width:100%;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 12px;color:var(--text);font-size:.82rem;outline:none;font-family:inherit}
.conv-search input:focus{border-color:var(--orange)}
.conv-item{padding:11px 14px;border-bottom:1px solid var(--border);cursor:pointer;transition:background .1s}
.conv-item:hover{background:var(--bg3)}
.conv-item.active{background:var(--bg3);border-right:2px solid var(--orange)}
.conv-name{font-weight:600;font-size:.84rem;color:var(--text);display:flex;align-items:center;justify-content:space-between;margin-bottom:3px}
.conv-preview{font-size:.75rem;color:var(--text3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.conv-time{font-size:.68rem;color:var(--text3);margin-top:3px}
.unread-num{background:var(--orange);color:#fff;border-radius:99px;padding:1px 7px;font-size:.67rem;font-weight:700}
.chat-window{display:flex;flex-direction:column;height:100vh}
.chat-header{padding:14px 18px;border-bottom:1px solid var(--border);background:var(--bg2);display:flex;align-items:flex-start;justify-content:space-between;flex-shrink:0;gap:10px}
.chat-messages{flex:1;overflow-y:auto;padding:16px 18px;display:flex;flex-direction:column;gap:8px;background:var(--bg)}
.msg{max-width:68%;word-break:break-word}
.msg.visitor{align-self:flex-start}.msg.manager{align-self:flex-end}
.msg-bubble{padding:9px 13px;border-radius:14px;font-size:.84rem;line-height:1.55}
.msg.visitor .msg-bubble{background:var(--bg3);border:1px solid var(--border);color:var(--text);border-bottom-left-radius:3px}
.msg.manager .msg-bubble{background:var(--orange2);color:#fff;border-bottom-right-radius:3px}
.msg-time{font-size:.67rem;color:var(--text3);margin-top:4px;display:flex;align-items:center;gap:4px}
.msg.visitor .msg-time{justify-content:flex-start}.msg.manager .msg-time{justify-content:flex-end}
.msg-img{max-width:220px;max-height:220px;border-radius:8px;display:block;cursor:pointer;margin:3px 0}
.chat-input{padding:12px 18px;border-top:1px solid var(--border);background:var(--bg2);flex-shrink:0}
.chat-input-row{display:flex;gap:8px;align-items:flex-end}
.chat-input textarea{flex:1;background:var(--bg);border:1px solid var(--border2);border-radius:var(--radius-sm);padding:9px 13px;color:var(--text);font-size:.84rem;outline:none;resize:none;max-height:120px;font-family:inherit;transition:border-color .15s}
.chat-input textarea:focus{border-color:var(--orange)}
.send-btn-orange{background:var(--orange);color:#fff;border:none;border-radius:var(--radius-sm);padding:10px 18px;cursor:pointer;font-size:.84rem;font-weight:600;height:42px;flex-shrink:0;font-family:inherit;transition:background .15s}
.send-btn-orange:hover{background:var(--orange2)}
.no-conv{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:var(--text3);gap:10px;font-size:.85rem}

/* ── AVATAR ──────────────────────────────────────── */
.avatar{width:38px;height:38px;border-radius:50%;background:#431407;display:flex;align-items:center;justify-content:center;font-size:.88rem;flex-shrink:0;font-weight:700;color:#fb923c}

/* ── UTM TAGS ────────────────────────────────────── */
.utm-row{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px}
.utm-tag{background:#0c1e38;border:1px solid #1e3a5f;border-radius:4px;padding:2px 8px;font-size:.7rem;color:#7dd3fc;font-family:monospace}

/* ── CHARTS ──────────────────────────────────────── */
.chart-wrap{height:150px;display:flex;align-items:flex-end;gap:3px;padding:4px 0}
.chart-bar-wrap{display:flex;flex-direction:column;align-items:center;flex:1;height:100%}
.chart-bar{width:100%;border-radius:3px 3px 0 0;min-height:2px;transition:height .3s}
.chart-bar.blue{background:#3b82f6}
.chart-bar.orange{background:var(--orange)}
.chart-bar.green{background:var(--green)}
.chart-label{font-size:.56rem;color:var(--text3);margin-top:4px;transform:rotate(-40deg);transform-origin:top right;white-space:nowrap}

/* ── FUNNEL ──────────────────────────────────────── */
.funnel{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:20px}
.funnel-step{background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius);padding:14px;text-align:center}
.funnel-step .fn{font-size:1.5rem;font-weight:700;margin-bottom:4px}
.funnel-step .fl{font-size:.72rem;color:var(--text3)}

/* ── STATUS TABS ─────────────────────────────────── */
.status-tabs{display:flex;gap:4px;margin-bottom:10px}
.status-tab{padding:5px 12px;border-radius:99px;font-size:.76rem;cursor:pointer;border:1px solid var(--border);color:var(--text3);background:transparent;font-family:inherit;transition:all .12s}
.status-tab:hover{border-color:var(--border2);color:var(--text2)}
.status-tab.active{background:var(--orange);color:#fff;border-color:var(--orange);font-weight:600}

/* ── TOAST ───────────────────────────────────────── */
#toast-container{position:fixed;top:16px;right:16px;z-index:9999;display:flex;flex-direction:column;gap:8px;pointer-events:none}
.toast{background:var(--bg3);border:1px solid var(--border2);border-radius:var(--radius);padding:12px 15px;max-width:290px;pointer-events:auto;animation:toastIn .2s ease;cursor:pointer}
.toast.tg-toast{border-left:3px solid #38bdf8}
.toast.wa-toast{border-left:3px solid #25d366}
.toast-title{font-size:.8rem;font-weight:700;color:var(--text);margin-bottom:2px}
.toast-body{font-size:.73rem;color:var(--text3)}
@keyframes toastIn{from{opacity:0;transform:translateX(14px)}to{opacity:1;transform:none}}
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

    # Разрешённые вкладки для менеджера
    perms_str = (user.get("permissions", "") or "") if user else ""
    allowed_tabs = [p.strip() for p in perms_str.split(",") if p.strip()]
    def can(tab):
        if role == "admin": return True
        return not allowed_tabs or tab in allowed_tabs

    def item(icon, label, page, section_color="blue", badge_count=0, url=None, badge_id=None):
        if not can(page): return ""
        href = url or f"/{page}"
        act  = page == active or (url and url.strip("/") == active)
        cls  = f"nav-item active {section_color}" if act else "nav-item"
        bid  = f' id="{badge_id}"' if badge_id else ""
        hide = ' style="display:none"' if badge_count == 0 else ""
        bdg  = f'<span class="badge-count"{bid}{hide}>{badge_count if badge_count else ""}</span>'
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
          <div class="theme-toggle" onclick="toggleTheme()" title="Тема" id="theme-btn">☀️</div>
        </div>
      </div>
      {item("📊", "Обзор", "overview", "blue")}
      <div class="nav-divider"></div>
      <div class="nav-section">Клиенты</div>
      {item("📡", "Каналы", "channels", "blue")}
      {item("🔗", "Кампании", "campaigns", "blue")}
      {item("🎨", "Шаблоны", "landings", "blue")}
      {item("📈", "Статистика", "analytics_clients", "blue", url="/analytics/clients")}
      <div class="nav-divider"></div>
      <div class="nav-section">Сотрудники</div>
      {item("💬", "TG Чаты", "chat", "orange", badge_count=unread, badge_id="nav-tg-badge")}
      {item("💚", "WA Чаты", "wa_chat", "orange", badge_count=wa_unread, url="/wa/chat", badge_id="nav-wa-badge")}
      {item("🗂", "База", "staff", "orange")}
      {item("🌐", "Лендинги HR", "landings_staff", "orange")}
      {item("📊", "Статистика", "analytics_staff", "orange", url="/analytics/staff")}
      {admin_section}
      <div class="sidebar-footer">
        <div class="bot-status"><div class="dot {'dot-green' if b1 else 'dot-red'}"></div><span>{b1_name}</span></div>
        <div class="bot-status"><div class="dot {'dot-green' if b2 else 'dot-red'}"></div><span>{b2_name}</span></div>
        <div class="bot-status"><div class="dot {wa_dot}"></div><span>WhatsApp {'✓' if wa_status == 'ready' else ('QR...' if wa_status == 'qr' else '✗')}</span></div>
        <a href="/logout"><div style="padding:6px 8px;margin-top:4px;font-size:.73rem;color:var(--text3);cursor:pointer;border-radius:6px;transition:color .12s" onmouseover="this.style.color='var(--text)'" onmouseout="this.style.color='var(--text3)'">⬅ Выйти</div></a>
      </div>
    </div>
    <div id="toast-container"></div>
    <script>
    (function(){{
      const t = localStorage.getItem('theme') || 'dark';
      const btn = document.getElementById('theme-btn');
      if(btn) btn.textContent = t === 'light' ? '🌙' : '☀️';
    }})();
    function toggleTheme(){{
      const isLight = document.body.classList.toggle('light');
      localStorage.setItem('theme', isLight ? 'light' : 'dark');
      const btn = document.getElementById('theme-btn');
      if(btn) btn.textContent = isLight ? '🌙' : '☀️';
    }}
    let audioCtx = null;
    function playPing(){{
      try{{
        if(!audioCtx) audioCtx = new (window.AudioContext||window.webkitAudioContext)();
        const o = audioCtx.createOscillator();
        const g = audioCtx.createGain();
        o.connect(g); g.connect(audioCtx.destination);
        o.frequency.setValueAtTime(880, audioCtx.currentTime);
        o.frequency.setValueAtTime(1100, audioCtx.currentTime + 0.1);
        g.gain.setValueAtTime(0.25, audioCtx.currentTime);
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
      setTimeout(() => {{ d.style.animation = 'toastIn .2s ease reverse'; setTimeout(() => d.remove(), 200); }}, 5000);
    }}
    let _lastTgUnread = {unread}, _lastWaUnread = {wa_unread};
    function updateBadge(id, count){{
      const el = document.getElementById(id);
      if(!el) return;
      if(count > 0){{ el.textContent = count; el.style.display = ''; }}
      else {{ el.textContent = ''; el.style.display = 'none'; }}
    }}
    async function pollUnread(){{
      try{{
        const r = await fetch('/api/stats');
        const d = await r.json();
        updateBadge('nav-tg-badge', d.unread || 0);
        updateBadge('nav-wa-badge', d.wa_unread || 0);
        if(d.unread > _lastTgUnread) showToast('💬 Новое сообщение', 'TG чаты', 'tg-toast', '/chat');
        if(d.wa_unread > _lastWaUnread) showToast('💚 Новое сообщение', 'WhatsApp чаты', 'wa-toast', '/wa/chat');
        _lastTgUnread = d.unread || 0; _lastWaUnread = d.wa_unread || 0;
      }}catch(e){{}}
    }}
    setInterval(pollUnread, 5000);
    </script>"""


def base(content: str, active: str, request: Request) -> str:
    return f'''<!DOCTYPE html><html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TGTracker</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
{CSS}
</head><body>{nav_html(active, request)}<div class="main">{content}</div></body></html>'''


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
    alert = f'<div class="alert-red" style="margin-bottom:14px">{error}</div>' if error else ""
    return HTMLResponse(f"""<!DOCTYPE html><html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TGTracker · Вход</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
{CSS}</head>
<body style="display:flex;align-items:center;justify-content:center;min-height:100vh;background:var(--bg)">
<div style="width:100%;max-width:360px;padding:0 20px">
  <div style="text-align:center;margin-bottom:28px">
    <div style="font-size:1.6rem;margin-bottom:8px">📡</div>
    <div style="font-size:1.2rem;font-weight:700;color:var(--text);letter-spacing:-.01em">TGTracker</div>
    <div style="font-size:.8rem;color:var(--text3);margin-top:4px">Войдите чтобы продолжить</div>
  </div>
  {alert}
  <div style="background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius);padding:24px">
    <form method="post" action="/login" style="display:flex;flex-direction:column;gap:14px">
      <div class="field-group"><div class="field-label">Логин</div><input type="text" name="username" autofocus autocomplete="username"/></div>
      <div class="field-group"><div class="field-label">Пароль</div><input type="password" name="password" autocomplete="current-password"/></div>
      <button class="btn-orange" style="width:100%;margin-top:4px;padding:10px">Войти →</button>
    </form>
  </div>
</div>
</body></html>""")


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

    <div style="font-size:.68rem;font-weight:700;color:var(--blue);text-transform:uppercase;letter-spacing:.1em;margin-bottom:10px">Клиенты</div>
    <div class="cards" style="margin-bottom:20px">
      <div class="card c-blue"><div class="val blue">{s['total']}</div><div class="lbl">Подписчиков</div></div>
      <div class="card c-blue"><div class="val">{s['from_ads']}</div><div class="lbl">Из рекламы</div></div>
      <div class="card c-blue"><div class="val">{s['organic']}</div><div class="lbl">Органика</div></div>
      <div class="card c-blue"><div class="val">{s['clicks']}</div><div class="lbl">Кликов (/go)</div></div>
    </div>

    <div style="font-size:.68rem;font-weight:700;color:var(--orange);text-transform:uppercase;letter-spacing:.1em;margin-bottom:10px">Сотрудники — Воронка</div>
    <div class="funnel">{funnel_html}</div>
    <div class="cards" style="margin-bottom:20px">
      <div class="card c-orange"><div class="val orange">{s['conversations']}</div><div class="lbl">Диалогов</div></div>
      <div class="card c-red"><div class="val red">{s['unread']}</div><div class="lbl">Непрочитанных</div></div>
      <div class="card c-orange"><div class="val orange">{s['staff']}</div><div class="lbl">Сотрудников</div></div>
    </div>

    <div class="section">
      <div class="section-head"><h3>Последние подписки</h3><span class="tag">Pixel: {pixel}</span></div>
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
            <td style="color:var(--orange)">{c['from_ads']}</td>
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
    wa_stats   = db.get_wa_stats()
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
      {kpi(msg_sum['active_convos'], 'Активных TG чатов', '')}
      {kpi(wa_stats.get('total_convs', 0), 'WA чатов всего', f"{wa_stats.get('open_convs',0)} открытых", '#25d366')}
      {kpi(wa_stats.get('total_msgs', 0), 'Сообщений WA', f"{wa_stats.get('incoming',0)} вх / {wa_stats.get('outgoing',0)} исх", '#25d366')}
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
      <div class="section">
        <div class="section-head"><h3>💚 Сообщения WA по дням</h3></div>
        <div class="section-body">{sparkline(wa_day, 'total', '#25d366')}</div>
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
async def chat_panel(request: Request, conv_id: int = 0, status_filter: str = "open"):
    user, err = require_auth(request)
    if err: return err

    convs = db.get_conversations(status=status_filter if status_filter != "all" else None)
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
            # Аватарка
            photo_url = active_conv.get("photo_url","")
            if photo_url:
                avatar_html = f'<img src="{photo_url}" style="width:40px;height:40px;border-radius:50%;object-fit:cover;flex-shrink:0" onerror="this.style.display=\'none\';this.nextSibling.style.display=\'flex\'">' \
                              f'<div class="avatar" style="display:none">{active_conv["visitor_name"][0].upper()}</div>'
            else:
                avatar_html = f'<div class="avatar">{active_conv["visitor_name"][0].upper()}</div>'

            # Доп инфо из профиля TG
            profile_info = ""
            if active_conv.get("phone"):
                profile_info += f'<span style="font-size:.75rem;color:#60a5fa">📱 {active_conv["phone"]}</span> '
            if active_conv.get("bio"):
                profile_info += f'<div style="font-size:.74rem;color:var(--text3);margin-top:2px;font-style:italic">{active_conv["bio"][:80]}</div>'

            # UTM и источник
            utm_tags = ""
            if utm or active_conv.get("utm_source") or active_conv.get("fbclid"):
                src = utm.get("utm_source") if utm else active_conv.get("utm_source","")
                campaign = utm.get("utm_campaign") if utm else active_conv.get("utm_campaign","")
                fbclid = utm.get("fbclid") if utm else active_conv.get("fbclid","")
                utm_medium = utm.get("utm_medium","") if utm else ""
                utm_content = utm.get("utm_content","") if utm else ""
                utm_term = utm.get("utm_term","") if utm else ""

                tags = []
                if fbclid or src in ("facebook","fb","instagram"):
                    tags.append('<span class="utm-tag" style="background:#1e3a5f;color:#60a5fa">🔵 Facebook</span>')
                elif src:
                    tags.append(f'<span class="utm-tag">{src}</span>')
                if campaign: tags.append(f'<span class="utm-tag" title="campaign">🎯 {campaign[:25]}</span>')
                if utm_content: tags.append(f'<span class="utm-tag" title="ad">📌 {utm_content[:20]}</span>')
                if utm_term: tags.append(f'<span class="utm-tag" title="adset">{utm_term[:20]}</span>')
                if fbclid: tags.append('<span class="utm-tag badge-green">fbclid ✓</span>')
                if tags:
                    utm_tags = '<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:6px">' + "".join(tags) + '</div>'

            # Lead статус
            is_lead = staff and staff.get("fb_event_sent")
            lead_badge = '<span class="badge-green" style="font-size:.7rem;padding:2px 8px">✅ Lead отправлен</span>' if is_lead else \
                         f'<form method="post" action="/chat/send_lead" style="display:inline"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn btn-sm" style="font-size:.73rem;background:#1e3a5f;border:1px solid #3b5998;color:#93c5fd">📤 Lead → FB</button></form>'

            tg_number = active_conv.get("tg_chat_id","")
            call_btn = f'<a href="tg://user?id={tg_number}" class="btn-gray btn-sm" style="display:inline-flex;align-items:center;gap:4px;padding:5px 10px;border-radius:7px;font-size:.74rem;border:1px solid var(--border);text-decoration:none">📞 Звонок</a>' if tg_number else ""

            close_btn = (f'<form method="post" action="/chat/close"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-gray btn-sm">✓ Закрыть</button></form>'
                        if active_conv["status"] == "open"
                        else f'<form method="post" action="/chat/reopen"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-orange btn-sm">↺ Открыть</button></form>')

            delete_btn = f'<button class="btn-gray btn-sm" style="color:var(--red);border-color:#7f1d1d" onclick="deleteConv({conv_id})">🗑</button>'

            staff_link = f'<a href="/staff?edit={staff["id"]}" style="color:var(--orange);font-size:.74rem;text-decoration:none">Карточка →</a>' if staff else \
                         f'<a href="/staff/create_from_conv?conv_id={conv_id}" style="color:var(--text3);font-size:.74rem;text-decoration:none">+ Создать карточку</a>'

            header_html = f"""<div class="chat-header">
              <div style="display:flex;align-items:flex-start;gap:12px;flex:1">
                {avatar_html}
                <div style="flex:1">
                  <div style="font-weight:700;color:var(--text)">{active_conv['visitor_name']} <span style="color:{status_color};font-size:.72rem">●</span></div>
                  <div style="font-size:.78rem;color:var(--text3)">{uname} {staff_link}</div>
                  {profile_info}
                  <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:6px;align-items:center">
                    {lead_badge} {call_btn}
                  </div>
                  {utm_tags}
                </div>
              </div>
              <div style="display:flex;gap:6px;flex-shrink:0">{close_btn} {delete_btn}</div>
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
            utm_line = f'<div class="conv-meta"><span class="utm-tag">🎯 {c["utm_campaign"][:22]}</span></div>'
        conv_items += f"""<a href="/chat?conv_id={c['id']}&status_filter={status_filter}"><div class="{cls}">
          <div class="conv-name"><span>{dot} {c['visitor_name']}</span>{ucount}</div>
          <div class="conv-preview">{c.get('last_message') or 'Нет сообщений'}</div>
          <div class="conv-time" style="display:flex;align-items:center;justify-content:space-between">{t} {src_badge}</div>
          {utm_line}</div></a>"""

    if not conv_items:
        conv_items = '<div class="empty" style="padding:36px 14px">Диалогов нет</div>'

    b2 = bot_manager.get_staff_bot()
    bot_warn = "" if b2 else '<div style="background:rgba(249,115,22,.1);border:1px solid rgba(249,115,22,.3);border-radius:8px;padding:9px 12px;font-size:.79rem;color:var(--orange);margin-bottom:8px">⚠️ Бот не запущен — <a href="/settings" style="color:var(--orange);text-decoration:underline">Настройки</a></div>'

    # Табы фильтра статуса
    def stab(label, val):
        active_tab = "background:var(--orange);color:#fff" if val == status_filter else "background:var(--bg3);color:var(--text3)"
        return f'<a href="/chat?status_filter={val}" style="flex:1;text-align:center;padding:5px 0;border-radius:7px;font-size:.78rem;font-weight:600;text-decoration:none;{active_tab}">{label}</a>'

    status_tabs = f'<div style="display:flex;gap:4px;background:var(--bg2);border-radius:9px;padding:3px;margin-bottom:8px">{stab("🟢 Открытые","open")}{stab("⚫ Закрытые","closed")}{stab("Все","all")}</div>'

    right = f"""{header_html}
    <div class="chat-messages" id="msgs">{messages_html}</div>
    <div class="chat-input"><div class="chat-input-row">
      <input type="file" id="tg-file-input" accept="image/*,video/*,.pdf,.doc,.docx" style="display:none" onchange="sendTgFile(this)"/>
      <button class="send-btn-orange" style="background:#374151;padding:10px 13px;font-size:1.1rem" onclick="document.getElementById('tg-file-input').click()" title="Отправить файл">📎</button>
      <textarea id="reply-text" placeholder="Ответить… (Enter — отправить)" rows="1" onkeydown="handleKey(event)"></textarea>
      <button class="send-btn-orange" onclick="sendMsg()">Отправить</button>
    </div></div>""" if active_conv else '<div class="no-conv"><div style="font-size:2.5rem">👔</div><div>Выбери диалог</div></div>'

    content = f"""<div class="chat-layout">
      <div class="conv-list">
        <div class="conv-search">{bot_warn}{status_tabs}<input type="text" placeholder="🔍 Поиск..." oninput="filterConvs(this.value)"/></div>
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
    async function sendTgFile(input){{
      const file=input.files[0]; if(!file) return;
      const btn=document.querySelector('button[onclick*="tg-file-input"]');
      btn.textContent='⏳'; btn.disabled=true;
      const fd=new FormData(); fd.append('conv_id','{conv_id}'); fd.append('file',file);
      try{{
        const res=await fetch('/chat/send_media',{{method:'POST',body:fd}});
        const data=await res.json();
        if(data.ok) loadNewMsgs();
        else alert('Ошибка: '+(data.error||'неизвестно'));
      }}catch(e){{alert('Ошибка: '+e.message);}}
      btn.textContent='📎'; btn.disabled=false; input.value='';
    }}
    async function deleteConv(id){{
      if(!confirm('Удалить чат и все сообщения? Это действие нельзя отменить.')) return;
      const r=await fetch('/chat/delete',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:'conv_id='+id}});
      const d=await r.json();
      if(d.ok) window.location.href='/chat?status_filter={status_filter}';
      else alert('Ошибка удаления');
    }}
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

    return HTMLResponse(base(content, "chat", request))


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


@app.post("/chat/send_media")
async def chat_send_media(request: Request, conv_id: int = Form(...), file: UploadFile = File(...)):
    user, err = require_auth(request)
    if err: return JSONResponse({"error": "unauthorized"}, 401)
    conv = db.get_conversation(conv_id)
    if not conv: return JSONResponse({"error": "not found"}, 404)

    import io
    from aiogram.types import BufferedInputFile
    file_data = await file.read()
    mimetype  = file.content_type or "application/octet-stream"
    filename  = file.filename or "file"
    tg_chat_id = conv["tg_chat_id"]

    bot = bot_manager.get_staff_bot()
    if not bot:
        return JSONResponse({"ok": False, "error": "Bot not connected"})

    try:
        buf = BufferedInputFile(file_data, filename=filename)
        if mimetype.startswith("image/"):
            sent = await bot.send_photo(int(tg_chat_id), buf)
            text = "[фото]"
        elif mimetype.startswith("video/"):
            sent = await bot.send_video(int(tg_chat_id), buf)
            text = "[видео]"
        else:
            sent = await bot.send_document(int(tg_chat_id), buf)
            text = f"[файл: {filename}]"

        # Сохраняем ссылку через Telegram file_id
        bot_token = db.get_setting("bot2_token") or ""
        media_url = None
        if bot_token:
            try:
                if mimetype.startswith("image/") and sent.photo:
                    tg_file = await bot.get_file(sent.photo[-1].file_id)
                elif mimetype.startswith("video/") and sent.video:
                    tg_file = await bot.get_file(sent.video.file_id)
                elif sent.document:
                    tg_file = await bot.get_file(sent.document.file_id)
                else:
                    tg_file = None
                if tg_file:
                    media_url = f"https://api.telegram.org/file/bot{bot_token}/{tg_file.file_path}"
            except Exception: pass

        db.save_message(conv_id, tg_chat_id, "manager", text, media_url=media_url, media_type=mimetype)
        db.update_conversation_last_message(tg_chat_id, f"Вы: {text}", increment_unread=False)
        return JSONResponse({"ok": True})
    except Exception as e:
        log.error(f"[chat/send_media] error: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/chat/delete")
async def chat_delete(request: Request, conv_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return JSONResponse({"error": "unauthorized"}, 401)
    try:
        db.delete_conversation(conv_id)
        return JSONResponse({"ok": True})
    except Exception as e:
        log.error(f"[chat/delete] error: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


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
    # Пиксель сотрудников
    pixel_id   = db.get_setting("pixel_id_staff") or db.get_setting("pixel_id")
    meta_token = db.get_setting("meta_token_staff") or db.get_setting("meta_token")
    sent = await meta_capi.send_lead_event(
        pixel_id, meta_token,
        user_id=conv.get("tg_chat_id",""),
        campaign=conv.get("utm_campaign","telegram")
    )
    if sent and staff:
        db.set_staff_fb_event(staff["id"], "Lead")
    elif sent:
        # Если нет staff записи — помечаем в conversations
        db.set_conv_fb_event(conv_id, "Lead")
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
        s = db.get_staff_by_id(edit)
        if s:
            status_opts = "".join(f'<option value="{k}" {"selected" if s.get("status")==k else ""}>{icon} {label}</option>'
                                  for k, (icon, label, _) in STAFF_STATUSES.items())
            # Ссылка на чат (TG или WA)
            chat_link = ""
            if s.get("conversation_id"):
                chat_link = f'<a href="/chat?conv_id={s["conversation_id"]}" class="btn-gray btn-sm" style="text-decoration:none">💬 TG чат</a>'
            elif s.get("wa_conv_id"):
                chat_link = f'<a href="/wa/chat?conv_id={s["wa_conv_id"]}" class="btn-gray btn-sm" style="text-decoration:none;background:#052e16;border-color:#166534;color:#86efac">💚 WA чат</a>'
            edit_form = f"""<div class="section" style="margin-bottom:18px;border-left:3px solid #f97316">
              <div class="section-head"><h3>✏️ {s.get('name','Карточка')}</h3>{chat_link}</div>
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
              <div style="font-size:.75rem;color:var(--text3)">@{s['username'] or '—'}</div></td>
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


@app.get("/staff/create_from_conv")
async def staff_create_from_conv(request: Request, conv_id: int = 0):
    user, err = require_auth(request)
    if err: return err
    if not conv_id:
        return RedirectResponse("/chat", 303)
    conv = db.get_conversation(conv_id)
    if not conv:
        return RedirectResponse("/chat", 303)
    # Создаём или находим карточку
    existing = db.get_staff_by_conv(conv_id)
    if existing:
        return RedirectResponse(f"/staff?edit={existing['id']}", 303)
    # Создаём новую карточку
    staff = db.get_or_create_staff(
        tg_chat_id=conv.get("tg_chat_id"),
        name=conv.get("visitor_name","Новый"),
        username=conv.get("username",""),
        conv_id=conv_id
    )
    return RedirectResponse(f"/staff?edit={staff['id']}", 303)


@app.get("/staff/create_from_wa")
async def staff_create_from_wa(request: Request, conv_id: int = 0):
    user, err = require_auth(request)
    if err: return err
    if not conv_id:
        return RedirectResponse("/wa/chat", 303)
    conv = db.get_wa_conversation(conv_id)
    if not conv:
        return RedirectResponse("/wa/chat", 303)
    existing = db.get_staff_by_wa_conv(conv_id)
    if existing:
        return RedirectResponse(f"/staff?edit={existing['id']}", 303)
    staff = db.get_or_create_wa_staff(
        wa_conv_id=conv_id,
        name=conv.get("visitor_name","Новый"),
        wa_number=conv.get("wa_number","")
    )
    return RedirectResponse(f"/staff?edit={staff['id']}", 303)


# ══════════════════════════════════════════════════════════════════════════════
# USERS (admin only)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, msg: str = "", edit: int = 0):
    user, err = require_auth(request, role="admin")
    if err: return err
    users = db.get_users()
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""

    # Все вкладки и их названия
    ALL_TABS = [
        ("overview",         "📊 Обзор"),
        ("channels",         "📡 Каналы"),
        ("campaigns",        "🔗 Кампании"),
        ("landings",         "🎨 Шаблоны"),
        ("analytics_clients","📈 Статистика Клиентов"),
        ("chat",             "💬 TG Чаты"),
        ("wa_chat",          "💚 WA Чаты"),
        ("staff",            "🗂 База сотрудников"),
        ("landings_staff",   "🌐 Лендинги HR"),
        ("analytics_staff",  "📊 Статистика Сотрудников"),
    ]

    def perm_checkboxes(selected_perms):
        sel = [p.strip() for p in selected_perms.split(",") if p.strip()]
        boxes = ""
        for tab_id, tab_name in ALL_TABS:
            checked = "checked" if (not sel or tab_id in sel) else ""
            boxes += f'''<label style="display:flex;align-items:center;gap:7px;padding:5px 10px;background:var(--bg3);border-radius:7px;cursor:pointer;font-size:.82rem">
              <input type="checkbox" name="perm_{tab_id}" value="{tab_id}" {checked} style="accent-color:var(--orange)">
              {tab_name}
            </label>'''
        return f'<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:6px;margin-top:8px">{boxes}</div>'

    # Форма редактирования
    edit_form = ""
    if edit:
        eu = db.get_user_by_id(edit)
        if eu and eu["username"] != user["username"]:
            eu_perms = eu.get("permissions") or ""
            edit_form = f"""<div class="section" style="border-left:3px solid #f97316;margin-bottom:20px">
              <div class="section-head"><h3>✏️ Редактировать: {eu['username']}</h3></div>
              <div class="section-body">
                <form method="post" action="/users/update">
                  <input type="hidden" name="user_id" value="{eu['id']}"/>
                  <div class="grid-2" style="margin-bottom:12px">
                    <div class="field-group"><div class="field-label">Логин</div>
                      <input type="text" name="username" value="{eu['username']}" required/></div>
                    <div class="field-group"><div class="field-label">Роль</div>
                      <select name="role">
                        <option value="manager" {"selected" if eu["role"]=="manager" else ""}>manager</option>
                        <option value="admin" {"selected" if eu["role"]=="admin" else ""}>admin</option>
                      </select></div>
                    <div class="field-group"><div class="field-label">Новый пароль (оставь пустым — не менять)</div>
                      <input type="password" name="new_password" placeholder="Новый пароль..."/></div>
                  </div>
                  <div class="field-group" style="margin-bottom:12px">
                    <div class="field-label">🔒 Доступы к вкладкам (отмеченные вкладки доступны менеджеру)</div>
                    {perm_checkboxes(eu_perms)}
                  </div>
                  <div style="display:flex;gap:8px">
                    <button class="btn-orange">💾 Сохранить</button>
                    <a href="/users"><button class="btn-gray" type="button">Отмена</button></a>
                  </div>
                </form>
              </div></div>"""

    rows = ""
    for u in users:
        perms = u.get("permissions") or ""
        perm_count = len([p for p in perms.split(",") if p.strip()]) if perms else len(ALL_TABS)
        perm_badge = f'<span class="badge-gray" style="font-size:.7rem">{perm_count}/{len(ALL_TABS)} вкладок</span>'
        edit_btn = f'<a href="/users?edit={u["id"]}"><button class="btn-gray btn-sm">✏️</button></a>' if u["username"] != user["username"] else ""
        del_btn  = f'<form method="post" action="/users/delete" style="display:inline"><input type="hidden" name="user_id" value="{u["id"]}"/><button class="del-btn btn-sm">✕</button></form>' if u["username"] != user["username"] else ""
        rows += f"""<tr>
            <td><b>{u['username']}</b></td>
            <td><span class="{'badge' if u['role']=='admin' else 'badge-gray'}">{u['role']}</span></td>
            <td>{perm_badge}</td>
            <td>{u['created_at'][:10]}</td>
            <td style="white-space:nowrap">{edit_btn} {del_btn}</td>
        </tr>"""

    content = f"""<div class="page-wrap">
    <div class="page-title">🔐 Пользователи</div>
    <div class="page-sub">Управление доступом и правами</div>
    {alert}
    {edit_form}
    <div class="section"><div class="section-head"><h3>➕ Добавить пользователя</h3></div>
    <div class="section-body">
      <form method="post" action="/users/add">
        <div class="grid-2" style="margin-bottom:12px">
          <div class="field-group"><div class="field-label">Логин</div><input type="text" name="username" required/></div>
          <div class="field-group"><div class="field-label">Пароль</div><input type="password" name="password" required/></div>
          <div class="field-group"><div class="field-label">Роль</div>
            <select name="role"><option value="manager">manager</option><option value="admin">admin</option></select></div>
        </div>
        <div class="field-group" style="margin-bottom:12px">
          <div class="field-label">🔒 Доступы к вкладкам (по умолчанию — все открыты)</div>
          {perm_checkboxes("")}
        </div>
        <button class="btn">Добавить</button>
      </form>
    </div></div>
    <div class="section"><div class="section-head"><h3>👤 Пользователи ({len(users)})</h3></div>
    <table><thead><tr><th>Логин</th><th>Роль</th><th>Доступы</th><th>Создан</th><th></th></tr></thead>
    <tbody>{rows}</tbody></table></div></div>"""
    return HTMLResponse(base(content, "users", request))


@app.post("/users/add")
async def users_add(request: Request, username: str = Form(...), password: str = Form(...), role: str = Form("manager")):
    user, err = require_auth(request, role="admin")
    if err: return err
    ALL_TAB_IDS = ["overview","channels","campaigns","landings","analytics_clients",
                   "chat","wa_chat","staff","landings_staff","analytics_staff"]
    form = await request.form()
    # Собираем отмеченные чекбоксы
    checked = [t for t in ALL_TAB_IDS if form.get(f"perm_{t}")]
    # Если все отмечены — пустая строка (полный доступ)
    perms = "" if len(checked) == len(ALL_TAB_IDS) else ",".join(checked)
    try:
        db.create_user(username.strip(), password, role, perms)
        return RedirectResponse("/users?msg=Пользователь+добавлен", 303)
    except:
        return RedirectResponse("/users?msg=Такой+логин+уже+существует", 303)


@app.post("/users/update")
async def users_update(request: Request, user_id: int = Form(...), username: str = Form(...),
                        role: str = Form("manager"), new_password: str = Form("")):
    user, err = require_auth(request, role="admin")
    if err: return err
    ALL_TAB_IDS = ["overview","channels","campaigns","landings","analytics_clients",
                   "chat","wa_chat","staff","landings_staff","analytics_staff"]
    form = await request.form()
    checked = [t for t in ALL_TAB_IDS if form.get(f"perm_{t}")]
    perms = "" if len(checked) == len(ALL_TAB_IDS) else ",".join(checked)
    db.update_user(user_id, username.strip(), role, perms, new_password.strip() or None)
    return RedirectResponse("/users?msg=Сохранено", 303)


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
    # Раздельные пиксели
    pixel_clients   = db.get_setting("pixel_id_clients",   db.get_setting("pixel_id", ""))
    token_clients   = db.get_setting("meta_token_clients", db.get_setting("meta_token", ""))
    pixel_staff     = db.get_setting("pixel_id_staff",     "")
    token_staff     = db.get_setting("meta_token_staff",   "")
    notify_chat     = db.get_setting("notify_chat_id", "")
    app_url         = db.get_setting("app_url", "")

    def masked_tok(t): return t[:12] + "..." + t[-6:] if len(t) > 20 else (t or "—")

    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""

    def bot_card(title, color, info, field, route):
        status = f'<span style="color:#34d399">● Активен — <a href="{info.get("link","")}" target="_blank" style="color:#60a5fa">@{info.get("username","")}</a></span>' if info.get("active") else '<span style="color:var(--red)">● Не запущен</span>'
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

    <div class="section-head" style="padding:0;margin-bottom:12px"><h3 style="font-size:.78rem;font-weight:700;color:var(--blue);text-transform:uppercase;letter-spacing:.08em">🤖 Управление ботами</h3></div>
    {bot_card("🔵 Бот 1 — Трекер (Клиенты)", "blue", b1_info, "bot1_token", "settings/bot1")}
    {bot_card("🟠 Бот 2 — Сотрудники", "orange", b2_info, "bot2_token", "settings/bot2")}

    <div class="section" style="border-left:3px solid #25d366">
      <div class="section-head"><h3>💚 WhatsApp</h3>
        <span style="font-size:.82rem">{
            '<span style="color:#34d399">● Подключён · +' + db.get_setting("wa_connected_number","") + '</span>'
            if db.get_setting("wa_status") == "ready"
            else ('<span style="color:#fbbf24">● Ожидает QR...</span>'
                  if db.get_setting("wa_status") == "qr"
                  else '<span style="color:var(--red)">● Не подключён</span>')
        }</span>
      </div>
      <div class="section-body">
        <a href="/wa/setup" class="btn" style="background:#059669;display:inline-flex;align-items:center;gap:8px;text-decoration:none">
          📱 Открыть подключение WhatsApp / QR-код
        </a>
      </div>
    </div>

    <div class="section">
      <div class="section-head"><h3>📡 Meta Pixel & CAPI</h3></div>
      <div class="section-body">
        <form method="post" action="/settings/pixel">
          <div style="margin-bottom:16px">
            <div style="font-size:.78rem;font-weight:700;color:var(--blue);text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px">👥 Клиенты (Subscribe — при подписке на канал)</div>
            <div class="grid-2">
              <div class="field-group"><div class="field-label">Pixel ID (Клиенты)</div>
                <input type="text" name="pixel_id_clients" value="{pixel_clients}" placeholder="123456789012345"/></div>
              <div class="field-group"><div class="field-label">Access Token (сейчас: {masked_tok(token_clients)})</div>
                <input type="text" name="meta_token_clients" placeholder="Оставь пустым — не менять"/></div>
            </div>
          </div>
          <div style="margin-bottom:16px">
            <div style="font-size:.78rem;font-weight:700;color:var(--orange);text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px">👔 Сотрудники (Lead — вручную в чате)</div>
            <div class="grid-2">
              <div class="field-group"><div class="field-label">Pixel ID (Сотрудники)</div>
                <input type="text" name="pixel_id_staff" value="{pixel_staff}" placeholder="987654321098765"/></div>
              <div class="field-group"><div class="field-label">Access Token (сейчас: {masked_tok(token_staff)})</div>
                <input type="text" name="meta_token_staff" placeholder="Оставь пустым — не менять"/></div>
            </div>
          </div>
          <button class="btn">💾 Сохранить пиксели</button>
        </form>
      </div>
    </div>

    <div class="section">
      <div class="section-head"><h3>🔔 Уведомления</h3></div>
      <div class="section-body">
        <form method="post" action="/settings/notify">
          <div class="grid-2" style="margin-bottom:12px">
            <div class="field-group">
              <div class="field-label">Chat ID или ID канала для уведомлений</div>
              <input type="text" name="notify_chat_id" value="{notify_chat}" placeholder="Например: -1001234567890"/>
              <span style="font-size:.75rem;color:var(--text3);margin-top:4px;display:block">
                Личный чат: напиши <b>/start</b> боту @userinfobot и скопируй id.<br>
                Канал/группа: добавь бота как администратора → скопируй ID канала (начинается с -100).
              </span>
            </div>
            <div class="field-group">
              <div class="field-label">URL приложения (для кнопки "Открыть чат")</div>
              <input type="text" name="app_url" value="{app_url}" placeholder="https://web-production-xxx.up.railway.app"/>
            </div>
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
async def settings_pixel(request: Request,
                          pixel_id_clients: str = Form(""), meta_token_clients: str = Form(""),
                          pixel_id_staff: str   = Form(""), meta_token_staff: str   = Form("")):
    user, err = require_auth(request, role="admin")
    if err: return err
    if pixel_id_clients.strip():   db.set_setting("pixel_id_clients",   pixel_id_clients.strip())
    if meta_token_clients.strip(): db.set_setting("meta_token_clients", meta_token_clients.strip())
    if pixel_id_staff.strip():     db.set_setting("pixel_id_staff",     pixel_id_staff.strip())
    if meta_token_staff.strip():   db.set_setting("meta_token_staff",   meta_token_staff.strip())
    # Совместимость — дублируем в pixel_id/meta_token для старого кода
    if pixel_id_clients.strip():   db.set_setting("pixel_id",   pixel_id_clients.strip())
    if meta_token_clients.strip(): db.set_setting("meta_token", meta_token_clients.strip())
    return RedirectResponse("/settings?msg=Пиксели+сохранены", 303)


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
    return RedirectResponse("/landings_staff?msg=Текст+бота+сохранён", 303)


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
    staff_welcome = db.get_setting("staff_welcome", "Привет! Напиши своё имя и должность 👋")
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""
    welcome_block = f"""
    <div class="section" style="border-left:3px solid #f97316">
      <div class="section-head"><h3>👔 Текст бота сотрудников (/start)</h3></div>
      <div class="section-body">
        <form method="post" action="/settings/staff_welcome">
          <div class="field-group" style="margin-bottom:12px">
            <div class="field-label">Первое сообщение когда сотрудник пишет /start боту</div>
            <textarea name="staff_welcome" rows="4" style="min-height:90px">{staff_welcome}</textarea>
            <span style="font-size:.75rem;color:var(--text3);margin-top:4px;display:block">Это сообщение видит кандидат при первом контакте с ботом сотрудников</span>
          </div>
          <button class="btn-orange">💾 Сохранить текст</button>
        </form>
      </div>
    </div>
    {alert}"""
    page_content = _landings_page(ltype="staff", active="landings_staff", msg="", request=request)
    # Вставляем блок бота перед контентом страницы
    page_content = welcome_block + page_content
    return HTMLResponse(base(page_content, "landings_staff", request))


def _landings_page(ltype: str, active: str, msg: str, request: Request) -> str:
    landings = db.get_landings(ltype)
    if ltype == "staff":
        title = "Лендинги HR"
        sub   = "Лендинги для рекрутинга. Выбери шаблон, добавь кнопки контактов — и лендинг готов."
    else:
        title = "Шаблоны лендингов"
        sub   = "Создай несколько дизайнов. При создании кампании выбираешь какой шаблон использовать."
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""

    # Превью шаблонов для staff
    tpl_select = ""
    if ltype == "staff":
        tpl_select = """
        <div class="field-group" style="margin-bottom:14px">
          <div class="field-label">Шаблон дизайна</div>
          <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:6px" id="tpl-grid">
            <label style="cursor:pointer">
              <input type="radio" name="template" value="dark_hr" checked style="display:none">
              <div class="tpl-card" data-tpl="dark_hr" style="border:2px solid var(--orange);border-radius:8px;overflow:hidden;transition:all .15s">
                <div style="height:70px;background:linear-gradient(135deg,#0b0d0f,#12161a);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px">
                  <div style="width:40px;height:5px;background:#32d27f;border-radius:3px"></div>
                  <div style="width:60px;height:3px;background:#32d27f;opacity:.4;border-radius:3px"></div>
                  <div style="display:flex;gap:4px;margin-top:4px">
                    <div style="width:50px;height:14px;background:#26A5E4;border-radius:4px"></div>
                    <div style="width:50px;height:14px;background:#25D366;border-radius:4px"></div>
                  </div>
                </div>
                <div style="padding:6px 8px;background:var(--bg3)"><div style="font-size:.72rem;font-weight:600;color:var(--text)">Dark Spa</div><div style="font-size:.65rem;color:var(--text3)">Тёмный премиум</div></div>
              </div>
            </label>
            <label style="cursor:pointer">
              <input type="radio" name="template" value="light_clean" style="display:none">
              <div class="tpl-card" data-tpl="light_clean" style="border:2px solid var(--border);border-radius:8px;overflow:hidden;transition:all .15s">
                <div style="height:70px;background:linear-gradient(135deg,#f8f9fc,#e8edf5);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px">
                  <div style="width:40px;height:5px;background:#2563eb;border-radius:3px"></div>
                  <div style="width:60px;height:3px;background:#2563eb;opacity:.3;border-radius:3px"></div>
                  <div style="display:flex;gap:4px;margin-top:4px">
                    <div style="width:50px;height:14px;background:#2563eb;border-radius:4px"></div>
                    <div style="width:50px;height:14px;background:#25D366;border-radius:4px"></div>
                  </div>
                </div>
                <div style="padding:6px 8px;background:var(--bg3)"><div style="font-size:.72rem;font-weight:600;color:var(--text)">Light Clean</div><div style="font-size:.65rem;color:var(--text3)">Светлый минимал</div></div>
              </div>
            </label>
            <label style="cursor:pointer">
              <input type="radio" name="template" value="bold_cta" style="display:none">
              <div class="tpl-card" data-tpl="bold_cta" style="border:2px solid var(--border);border-radius:8px;overflow:hidden;transition:all .15s">
                <div style="height:70px;background:linear-gradient(135deg,#1a0a2e,#2d1257);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px">
                  <div style="width:40px;height:5px;background:#a855f7;border-radius:3px"></div>
                  <div style="width:60px;height:3px;background:#a855f7;opacity:.4;border-radius:3px"></div>
                  <div style="display:flex;gap:4px;margin-top:4px">
                    <div style="width:50px;height:14px;background:#a855f7;border-radius:4px"></div>
                    <div style="width:50px;height:14px;background:#25D366;border-radius:4px"></div>
                  </div>
                </div>
                <div style="padding:6px 8px;background:var(--bg3)"><div style="font-size:.72rem;font-weight:600;color:var(--text)">Bold Purple</div><div style="font-size:.65rem;color:var(--text3)">Яркий фиолетовый</div></div>
              </div>
            </label>
          </div>
        </div>
        <script>
        document.querySelectorAll('.tpl-card').forEach(function(card){
          card.addEventListener('click',function(){
            document.querySelectorAll('.tpl-card').forEach(function(c){c.style.borderColor='var(--border)'});
            card.style.borderColor='var(--orange)';
            var radio=document.querySelector('input[value="'+card.dataset.tpl+'"]');
            if(radio) radio.checked=true;
          });
        });
        </script>"""

    rows = ""
    for l in landings:
        import json as _json
        try:
            lcontent = _json.loads(l.get("content","{}"))
            tpl_name = {"dark_hr":"Dark Spa","light_clean":"Light Clean","bold_cta":"Bold Purple"}.get(lcontent.get("template","dark_hr"),"Dark Spa")
        except:
            tpl_name = "Dark Spa"
        slug_url = f"/l/{l['slug']}"
        rows += f"""<tr>
          <td><b>{l['name']}</b></td>
          <td><span class="badge-gray" style="font-size:.68rem">{tpl_name}</span></td>
          <td><a href="{slug_url}" target="_blank" class="link-box" style="display:inline-block">{slug_url}</a></td>
          <td><span class="{'badge-green' if l['active'] else 'badge-gray'}">{'Активен' if l['active'] else 'Скрыт'}</span></td>
          <td>
            <a href="/landings/edit?id={l['id']}" class="btn-gray btn-sm">✏️ Редакт.</a>
            <form method="post" action="/landings/delete" style="display:inline"><input type="hidden" name="id" value="{l['id']}"/><button class="del-btn btn-sm">✕</button></form>
          </td></tr>"""
    rows = rows or f'<tr><td colspan="5"><div class="empty">Нет шаблонов — создай первый</div></td></tr>'

    tpl_th = '<th>Шаблон</th>' if ltype == "staff" else ""

    return f"""<div class="page-wrap"><div class="page-title">{title}</div>
    <div class="page-sub">{sub}</div>{alert}
    <div class="section"><div class="section-head"><h3>➕ Создать лендинг</h3></div><div class="section-body">
    <form method="post" action="/landings/create"><input type="hidden" name="ltype" value="{ltype}"/>
    <input type="hidden" name="redirect" value="/landings{'_staff' if ltype=='staff' else ''}"/>
    {tpl_select}
    <div class="form-row">
      <div class="field-group"><div class="field-label">Название</div><input type="text" name="name" placeholder="{'HR — Массаж v2' if ltype=='staff' else 'NYC — стиль 2'}" required/></div>
      <div class="field-group" style="max-width:200px"><div class="field-label">URL slug</div><input type="text" name="slug" placeholder="{'hr-massage-v2' if ltype=='staff' else 'nyc-v2'}" required/></div>
      <div style="display:flex;align-items:flex-end"><button class="btn">Создать</button></div>
    </div></form></div></div>
    <div class="section"><div class="section-head"><h3>Шаблоны ({len(landings)})</h3></div>
    <table><thead><tr><th>Название</th>{tpl_th}<th>URL</th><th>Статус</th><th>Действия</th></tr></thead>
    <tbody>{rows}</tbody></table></div></div>"""


@app.post("/landings/create")
async def landings_create(request: Request, name: str = Form(...), slug: str = Form(...),
                           ltype: str = Form("client"), redirect: str = Form("/landings")):
    user, err = require_auth(request)
    if err: return err
    import re, json
    form = await request.form()
    clean_slug = re.sub(r'[^a-z0-9-]', '-', slug.lower().strip())
    template = form.get("template", "dark_hr") if ltype == "staff" else "relaxation"
    content = json.dumps({"type": ltype, "template": template})
    # Если slug занят — добавляем -2, -3, ...
    final_slug = clean_slug
    counter = 2
    while True:
        try:
            db.create_landing(name.strip(), ltype, final_slug, content)
            suffix = f" (slug: {final_slug})" if final_slug != clean_slug else ""
            return RedirectResponse(f"{redirect}?msg=Лендинг+создан{suffix.replace(' ','+')}".replace('(','').replace(')','').replace(':',''), 303)
        except Exception as e:
            if "duplicate key" in str(e) or "unique" in str(e).lower():
                final_slug = f"{clean_slug}-{counter}"
                counter += 1
                if counter > 20:
                    return RedirectResponse(f"{redirect}?msg=Ошибка:+slug+{clean_slug}+уже+занят", 303)
            else:
                return RedirectResponse(f"{redirect}?msg=Ошибка:+{str(e)[:60]}", 303)


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

    import json as _json
    try:
        lcontent = _json.loads(landing.get("content","{}"))
        cur_tpl = lcontent.get("template","dark_hr")
    except:
        cur_tpl = "dark_hr"

    tpl_names = {"dark_hr":"Dark Spa","light_clean":"Light Clean","bold_cta":"Bold Purple"}

    contact_rows = ""
    for c in contacts:
        type_icon = "📱" if c["type"] == "telegram" else ("💚" if c["type"] == "whatsapp" else "🔗")
        contact_rows += f"""<tr>
          <td>{type_icon} <span class="badge">{c['type']}</span></td>
          <td>{c['label']}</td>
          <td><a href="{c['url']}" target="_blank" style="color:var(--blue);font-size:.8rem">{c['url'][:50]}{'...' if len(c['url'])>50 else ''}</a></td>
          <td><form method="post" action="/landings/contact/delete"><input type="hidden" name="contact_id" value="{c['id']}"/><input type="hidden" name="landing_id" value="{id}"/><button class="del-btn">✕</button></form></td></tr>"""
    contact_rows = contact_rows or '<tr><td colspan="4"><div class="empty">Нет контактов — добавь кнопки</div></td></tr>'

    public_url = f"{app_url}/l/{landing['slug']}"
    back = "/landings_staff" if landing["type"] == "staff" else "/landings"

    # Блок смены шаблона (только для staff)
    tpl_block = ""
    if landing["type"] == "staff":
        tpl_opts = "".join(
            f'<option value="{k}" {"selected" if k==cur_tpl else ""}>{v}</option>'
            for k,v in tpl_names.items()
        )
        tpl_block = f"""
        <div class="section">
          <div class="section-head"><h3>Шаблон дизайна</h3>
            <span class="badge-gray" style="font-size:.7rem">Сейчас: {tpl_names.get(cur_tpl,'—')}</span>
          </div>
          <div class="section-body">
            <form method="post" action="/landings/set_template" style="display:flex;gap:10px;align-items:flex-end">
              <input type="hidden" name="landing_id" value="{id}"/>
              <div class="field-group" style="max-width:220px">
                <div class="field-label">Выбрать шаблон</div>
                <select name="template">{tpl_opts}</select>
              </div>
              <button class="btn-orange">Применить</button>
            </form>
            <div style="margin-top:12px;display:flex;gap:8px">
              <a href="{public_url}" target="_blank" class="btn btn-sm">Предпросмотр →</a>
            </div>
          </div>
        </div>"""

    content = f"""<div class="page-wrap">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px">
      <a href="{back}" class="btn-gray btn-sm">← Назад</a>
      <div class="page-title">{landing['name']}</div>
    </div>
    {alert}
    <div class="section"><div class="section-head"><h3>Публичная ссылка</h3></div>
    <div class="section-body">
      <div class="link-box">{public_url}</div>
      <a href="{public_url}" target="_blank" class="btn btn-sm" style="margin-top:10px;display:inline-flex">Открыть →</a>
    </div></div>
    {tpl_block}
    <div class="section"><div class="section-head"><h3>Добавить кнопку</h3><small style="color:var(--text3)">Кнопки появятся на лендинге</small></div>
    <div class="section-body"><form method="post" action="/landings/contact/add"><input type="hidden" name="landing_id" value="{id}"/>
    <div class="form-row">
      <div class="field-group" style="max-width:160px"><div class="field-label">Тип</div>
      <select name="ctype"><option value="telegram">📱 Telegram</option><option value="whatsapp">💚 WhatsApp</option><option value="other">🔗 Другое</option></select></div>
      <div class="field-group" style="max-width:200px"><div class="field-label">Текст кнопки</div><input type="text" name="label" placeholder="Написать в Telegram" required/></div>
      <div class="field-group"><div class="field-label">URL</div><input type="text" name="url" placeholder="https://t.me/username" required/></div>
      <div style="display:flex;align-items:flex-end"><button class="btn">Добавить</button></div>
    </div></form></div></div>
    <div class="section"><div class="section-head"><h3>Кнопки контактов ({len(contacts)})</h3></div>
    <table><thead><tr><th>Тип</th><th>Текст</th><th>URL</th><th></th></tr></thead>
    <tbody>{contact_rows}</tbody></table></div></div>"""
    return HTMLResponse(base(content, landing["type"] + "_landing", request))


@app.post("/landings/set_template")
async def landings_set_template(request: Request, landing_id: int = Form(...), template: str = Form(...)):
    user, err = require_auth(request)
    if err: return err
    import json as _json
    landing = db.get_landing(landing_id)
    if not landing: return RedirectResponse("/landings_staff", 303)
    try:
        lcontent = _json.loads(landing.get("content","{}"))
    except:
        lcontent = {}
    lcontent["template"] = template
    db.update_landing_content(landing_id, _json.dumps(lcontent))
    return RedirectResponse(f"/landings/edit?id={landing_id}&msg=Шаблон+изменён", 303)


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
    # Пиксели по направлениям
    pixel_clients = db.get_setting("pixel_id_clients") or db.get_setting("pixel_id", "")
    pixel_staff   = db.get_setting("pixel_id_staff", "")

    # Ищем как Campaign slug
    campaign = db.get_campaign_by_slug(slug)
    if campaign:
        channels = db.get_campaign_channels(campaign["id"])
        app_url  = db.get_setting("app_url", "").rstrip("/")
        pixel_id = pixel_clients  # Клиентские кампании

        # Строим /go ссылки для каждого канала
        btns = []
        for cc in channels:
            go_url = f"{app_url}/go?to={cc['invite_link']}&utm_campaign={campaign['name']}&utm_source={utm_source or 'facebook'}&utm_medium={utm_medium or 'paid'}"
            if fbclid:      go_url += f"&fbclid={fbclid}"
            if utm_content: go_url += f"&utm_content={utm_content}"
            btns.append({"url": go_url, "label": cc.get("channel_name") or "Вступить в группу"})

        if campaign.get("landing_id"):
            landing  = db.get_landing(campaign["landing_id"])
            contacts = db.get_landing_contacts(campaign["landing_id"]) if landing else []
            if landing:
                chan_contacts = [{"type": "telegram", "label": b["label"], "url": b["url"]} for b in btns]
                return HTMLResponse(_render_client_landing(landing, chan_contacts, pixel_id=pixel_id))

        return HTMLResponse(_render_campaign_landing(campaign, btns, pixel_id, fbclid))

    # Staff Landing slug
    landing = db.get_landing_by_slug(slug)
    if not landing: return HTMLResponse("<h2>Not found</h2>", 404)
    contacts = db.get_landing_contacts(landing["id"])
    return HTMLResponse(_render_staff_landing(landing, contacts, pixel_id=pixel_staff))


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
            btn_html += f'<a class="lnd-btn lnd-tg call-button" href="{c["url"]}" target="_blank"><svg viewBox="0 0 24 24" fill="currentColor" width="22" height="22"><path d="M9.036 15.28 8.87 18.64c.34 0 .49-.15.67-.33l1.6-1.54 3.31 2.43c.61.34 1.05.16 1.22-.56l2.2-10.3c.2-.9-.32-1.25-.92-1.03L3.9 10.01c-.88.34-.86.83-.15 1.05l3.29 1.02 7.64-4.82c.36-.23.69-.1.42.14z"/></svg>{c["label"]}</a>'
        elif c["type"] == "whatsapp":
            btn_html += f'<a class="lnd-btn lnd-wa call-button" href="{c["url"]}" target="_blank"><svg viewBox="0 0 24 24" fill="currentColor" width="22" height="22"><path d="M20 3.5A10 10 0 0 0 4.2 17.3L3 21l3.8-1.2A10 10 0 1 0 20 3.5Z"/></svg>{c["label"]}</a>'
        else:
            btn_html += f'<a class="lnd-btn call-button" href="{c["url"]}" target="_blank" style="background:rgba(255,255,255,.12)">{c["label"]}</a>'

    if not btn_html:
        btn_html = '<p style="color:rgba(255,255,255,.5);text-align:center">Контакты не настроены</p>'

    px = _pixel_js(pixel_id)

    return f"""<!DOCTYPE html><html lang="en"><head>
    <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Relaxation and Balance 🌿✨</title>
    {px}
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


def _pixel_js(pixel_id: str) -> str:
    """Корректный FB Pixel код с PageView + Contact tracking"""
    if not pixel_id:
        return ""
    return f"""<!-- Facebook Pixel -->
<script>
!function(f,b,e,v,n,t,s){{if(f.fbq)return;n=f.fbq=function(){{n.callMethod?
n.callMethod.apply(n,arguments):n.queue.push(arguments)}};
if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
n.queue=[];t=b.createElement(e);t.async=!0;
t.src=v;s=b.getElementsByTagName(e)[0];
s.parentNode.insertBefore(t,s)}}(window,document,'script',
'https://connect.facebook.net/en_US/fbevents.js');
fbq('init','{pixel_id}');
fbq('track','PageView');
document.addEventListener('click',function(e){{
  var btn=e.target.closest('.call-button');
  if(btn){{fbq('track','Contact');}}
}});
</script>
<noscript><img height="1" width="1" style="display:none"
  src="https://www.facebook.com/tr?id={pixel_id}&ev=PageView&noscript=1"/></noscript>
<!-- End Facebook Pixel -->"""


def _build_buttons(contacts: list) -> str:
    """Универсальная генерация кнопок контактов для всех шаблонов"""
    TG_SVG = '<svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M9.036 15.28 8.87 18.64c.34 0 .49-.15.67-.33l1.6-1.54 3.31 2.43c.61.34 1.05.16 1.22-.56l2.2-10.3c.2-.9-.32-1.25-.92-1.03L3.9 10.01c-.88.34-.86.83-.15 1.05l3.29 1.02 7.64-4.82c.36-.23.69-.1.42.14z"/></svg>'
    WA_SVG = '<svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M20 3.5A10 10 0 0 0 4.2 17.3L3 21l3.8-1.2A10 10 0 1 0 20 3.5ZM6.5 18.4l.1-.3-.1.3Zm10.4-3.8c-.2.6-1.1 1.1-1.6 1.2-.4.1-.9.1-1.5-.1-.3-.1-.7-.2-1.2-.5-2.2-1.2-3.6-3-4-3.4-.2-.2-.9-1.1-.9-2 0-.9.5-1.3.6-1.5.1-.2.3-.3.5-.3h.4c.1 0 .3 0 .4.3.2.6.6 1.6.7 1.7.1.2.1.3 0 .5-.2.3-.4.5-.5.6-.1.1-.3.3-.1.6.2.3.9 1.5 2.1 2.4 1.5 1.1 2.4 1.3 2.7 1.4.3.1.5.1.6-.1.2-.2.7-.8.9-1.1.2-.3.4-.2.6-.1.2.1 1.5.7 1.7.8.2.1.3.1.3.2 0 .1 0 .6-.2 1.2Z"/></svg>'
    html = ""
    for c in contacts:
        if c["type"] == "telegram":
            html += f'<a class="hr-btn hr-btn-tg call-button" href="{c["url"]}" target="_blank" rel="noopener">{TG_SVG}<span>{c["label"]}</span></a>'
        elif c["type"] == "whatsapp":
            html += f'<a class="hr-btn hr-btn-wa call-button" href="{c["url"]}" target="_blank" rel="noopener">{WA_SVG}<span>{c["label"]}</span></a>'
        else:
            html += f'<a class="hr-btn hr-btn-other call-button" href="{c["url"]}" target="_blank" rel="noopener"><span>{c["label"]}</span></a>'
    if not html:
        html = '<p style="text-align:center;opacity:.5;padding:12px 0">Контакты не настроены</p>'
    return html


def _render_staff_landing(landing: dict, contacts: list, pixel_id: str = "") -> str:
    """Диспетчер шаблонов HR лендингов"""
    import json as _json
    try:
        lcontent = _json.loads(landing.get("content","{}"))
        template = lcontent.get("template","dark_hr")
    except:
        template = "dark_hr"

    buttons = _build_buttons(contacts)
    px = _pixel_js(pixel_id)
    year = __import__('datetime').datetime.now().year
    name = landing.get("name","HR")

    if template == "light_clean":
        return _tpl_light_clean(name, buttons, px, year)
    elif template == "bold_cta":
        return _tpl_bold_cta(name, buttons, px, year)
    else:
        return _tpl_dark_hr(name, buttons, px, year)


def _tpl_dark_hr(name: str, buttons: str, pixel_js: str, year: int) -> str:
    return f"""<!DOCTYPE html><html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name}</title>
{pixel_js}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{{--bg:#0b0d0f;--card:#12161a;--text:#e7edf3;--muted:#a9b4bf;--accent:#32d27f;--tg:#26A5E4;--wa:#25D366}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{background:var(--bg);color:var(--text);font-family:'Montserrat',system-ui,sans-serif;min-height:100vh}}
a{{color:inherit;text-decoration:none}}
.wrap{{width:min(1080px,94vw);margin:0 auto}}
.hero{{position:relative;min-height:72vh;display:grid;place-items:center;text-align:center;overflow:hidden}}
.hero::before{{content:"";position:absolute;inset:0;background:url('https://images.unsplash.com/photo-1544161515-4ab6ce6db874?q=80&w=1920&auto=format&fit=crop') center/cover no-repeat;filter:brightness(.45)}}
.hero::after{{content:"";position:absolute;inset:0;background:linear-gradient(to top,rgba(11,13,15,1) 0%,rgba(11,13,15,.2) 50%,rgba(11,13,15,.5) 100%)}}
.hero-inner{{position:relative;z-index:1;padding:3rem 1rem}}
.chip{{display:inline-block;padding:.4rem .9rem;border-radius:999px;background:rgba(50,210,127,.15);border:1px solid rgba(50,210,127,.3);color:var(--accent);font-size:.85rem;font-weight:600;margin-bottom:1.2rem}}
.hero h1{{font-size:clamp(2rem,4vw+.8rem,3.4rem);font-weight:800;margin:0 0 .8rem;line-height:1.1}}
.hero p{{color:var(--muted);max-width:680px;margin:0 auto 1.8rem;font-size:1rem;font-weight:500}}
.section{{padding:56px 0}}
.grid{{display:grid;grid-template-columns:1.1fr .9fr;gap:20px;align-items:start}}
.card{{background:var(--card);border-radius:18px;padding:clamp(18px,3vw,28px)}}
.card h2{{font-size:clamp(1.1rem,1.6vw+.5rem,1.6rem);font-weight:700;margin:0 0 .6rem}}
.card p.lead{{color:var(--muted);margin:.2rem 0 1rem;font-size:.95rem}}
.card ul{{padding-left:1.1rem;line-height:1.8;color:var(--muted)}}
.card ul li{{margin:.2rem 0}}
.card ul li strong{{color:var(--text)}}
.note{{margin-top:1rem;background:rgba(50,210,127,.07);border:1px solid rgba(50,210,127,.2);padding:.85rem 1rem;border-radius:12px;color:#c6f6e0;font-size:.9rem}}
.cta-section{{padding:56px 0 80px;text-align:center}}
.cta-section h2{{font-size:clamp(1.4rem,2vw+.6rem,2rem);margin:0 0 .4rem}}
.cta-section p{{color:var(--muted);margin:0 auto 1.8rem;max-width:480px}}
.btns{{display:flex;flex-direction:column;gap:.75rem;width:100%;max-width:400px;margin:0 auto}}
.hr-btn{{display:inline-flex;align-items:center;justify-content:center;gap:.65rem;padding:.95rem 1.4rem;border-radius:14px;font-weight:700;font-size:1rem;width:100%;transition:transform .15s,opacity .15s}}
.hr-btn:hover{{transform:translateY(-2px);opacity:.92}}
.hr-btn-tg{{background:var(--tg);color:#fff}}
.hr-btn-wa{{background:var(--wa);color:#fff}}
.hr-btn-other{{background:rgba(255,255,255,.12);color:var(--text);border:1px solid rgba(255,255,255,.15)}}
footer{{text-align:center;padding:24px 0 40px;color:#576574;font-size:.85rem}}
@media(max-width:768px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body>
<header class="hero"><div class="hero-inner wrap">
  <div class="chip">Работа за рубежом</div>
  <h1>{name}</h1>
  <p>Высокооплачиваемая работа с обучением, жильём и гибким графиком. Присоединяйся и начни зарабатывать с первого дня.</p>
</div></header>
<section class="section"><div class="wrap"><div class="grid">
  <div class="card">
    <h2>Описание вакансии</h2>
    <p class="lead">Мы ищем активных и целеустремлённых сотрудников!</p>
    <ul>
      <li><strong>Высокий доход</strong> с первого рабочего дня</li>
      <li><strong>Обучение</strong> и постоянная поддержка команды</li>
      <li><strong>Жильё</strong> предоставляет компания</li>
      <li><strong>Документы и язык</strong> — не требуются</li>
      <li><strong>Гибкий график</strong> — выбираешь смены сам(а)</li>
      <li><strong>Множество локаций</strong> в крупных городах</li>
    </ul>
    <p class="note">Мы предоставляем пробную смену — оплачивается на общих основаниях 💵</p>
  </div>
  <div class="card" style="background:linear-gradient(135deg,rgba(38,165,228,.12),rgba(50,210,127,.12));display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;min-height:200px;gap:16px">
    <div style="font-size:2.5rem">💼</div>
    <p style="font-size:1.05rem;font-weight:600">Напиши нам — <br>ответим в течение часа</p>
  </div>
</div></div></section>
<section class="cta-section"><div class="wrap">
  <h2>Связаться с HR-менеджером</h2>
  <p>Выберите удобный канал связи — ответим быстро.</p>
  <div class="btns">{buttons}</div>
</div></section>
<footer>© {year} {name}. Все права защищены.</footer>
</body></html>"""


def _tpl_light_clean(name: str, buttons: str, pixel_js: str, year: int) -> str:
    return f"""<!DOCTYPE html><html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name}</title>
{pixel_js}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{{--bg:#f4f6fb;--white:#ffffff;--text:#111827;--muted:#6b7280;--accent:#2563eb;--tg:#26A5E4;--wa:#25D366;--border:#e5e7eb}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{background:var(--bg);color:var(--text);font-family:'Inter',system-ui,sans-serif;min-height:100vh}}
a{{color:inherit;text-decoration:none}}
.wrap{{width:min(1100px,94vw);margin:0 auto}}
nav{{background:var(--white);border-bottom:1px solid var(--border);padding:0 5vw}}
.nav-inner{{max-width:1100px;margin:0 auto;height:60px;display:flex;align-items:center;justify-content:space-between}}
.nav-logo{{font-weight:800;font-size:1.1rem;color:var(--accent)}}
.nav-cta{{background:var(--accent);color:#fff;padding:.5rem 1.2rem;border-radius:8px;font-weight:600;font-size:.9rem;transition:opacity .15s}}
.nav-cta:hover{{opacity:.88}}
.hero{{padding:80px 5vw 72px;text-align:center;background:var(--white)}}
.badge{{display:inline-block;padding:.35rem .9rem;border-radius:999px;background:#eff6ff;color:var(--accent);font-size:.82rem;font-weight:600;border:1px solid #bfdbfe;margin-bottom:1.2rem}}
.hero h1{{font-size:clamp(1.8rem,3.5vw+.8rem,3rem);font-weight:800;color:var(--text);margin:0 0 1rem;line-height:1.15}}
.hero h1 span{{color:var(--accent)}}
.hero p{{color:var(--muted);max-width:600px;margin:0 auto 2rem;font-size:1.05rem;line-height:1.7}}
.perks{{padding:56px 5vw;background:var(--bg)}}
.perks-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}}
.perk{{background:var(--white);border-radius:14px;padding:20px;border:1px solid var(--border)}}
.perk-icon{{font-size:1.6rem;margin-bottom:10px}}
.perk h3{{font-size:.95rem;font-weight:700;margin:0 0 5px}}
.perk p{{font-size:.84rem;color:var(--muted);line-height:1.6}}
.cta-section{{padding:64px 5vw 80px;text-align:center;background:var(--white)}}
.cta-section h2{{font-size:clamp(1.4rem,2.5vw+.5rem,2rem);font-weight:800;margin:0 0 .5rem}}
.cta-section p{{color:var(--muted);margin:0 auto 2rem;max-width:440px;font-size:.95rem}}
.btns{{display:flex;flex-direction:column;gap:.7rem;width:100%;max-width:380px;margin:0 auto}}
.hr-btn{{display:inline-flex;align-items:center;justify-content:center;gap:.6rem;padding:.9rem 1.4rem;border-radius:12px;font-weight:700;font-size:.95rem;width:100%;transition:transform .12s,opacity .15s}}
.hr-btn:hover{{transform:translateY(-2px);opacity:.9}}
.hr-btn-tg{{background:var(--tg);color:#fff}}
.hr-btn-wa{{background:var(--wa);color:#fff}}
.hr-btn-other{{background:var(--accent);color:#fff}}
footer{{background:var(--bg);border-top:1px solid var(--border);text-align:center;padding:24px;color:var(--muted);font-size:.84rem}}
@media(max-width:640px){{.perks-grid{{grid-template-columns:1fr}}}}
</style></head><body>
<nav><div class="nav-inner">
  <div class="nav-logo">{name}</div>
  <a href="#contact" class="nav-cta">Откликнуться →</a>
</div></nav>
<section class="hero"><div>
  <div class="badge">Открытый набор</div>
  <h1>Работа, которая <span>меняет жизнь</span></h1>
  <p>Стабильный доход, поддержка команды и карьерный рост. Узнай об условиях прямо сейчас.</p>
  <a href="#contact" class="hr-btn hr-btn-tg" style="display:inline-flex;width:auto;margin:0 auto">Узнать подробности →</a>
</div></section>
<section class="perks"><div class="wrap">
  <div class="perks-grid">
    <div class="perk"><div class="perk-icon">💰</div><h3>Высокий доход</h3><p>Конкурентная оплата с первого рабочего дня. Бонусы и премии.</p></div>
    <div class="perk"><div class="perk-icon">🎓</div><h3>Обучение</h3><p>Полная подготовка без опыта. Поддержка наставника на старте.</p></div>
    <div class="perk"><div class="perk-icon">🏠</div><h3>Жильё</h3><p>Компания предоставляет жильё или компенсирует расходы.</p></div>
    <div class="perk"><div class="perk-icon">🗓</div><h3>Гибкий график</h3><p>Выбираешь смены самостоятельно. Удобный режим работы.</p></div>
    <div class="perk"><div class="perk-icon">📍</div><h3>Множество локаций</h3><p>Работай в крупных городах — выбирай ближайший.</p></div>
    <div class="perk"><div class="perk-icon">🤝</div><h3>Простой старт</h3><p>Не требуем опыта, знания языка и специальных документов.</p></div>
  </div>
</div></section>
<section class="cta-section" id="contact"><div>
  <h2>Готов(а) к новой жизни?</h2>
  <p>Напиши нам — HR-менеджер ответит в течение часа и расскажет все детали.</p>
  <div class="btns">{buttons}</div>
</div></section>
<footer>© {year} {name}. Все права защищены.</footer>
</body></html>"""


def _tpl_bold_cta(name: str, buttons: str, pixel_js: str, year: int) -> str:
    return f"""<!DOCTYPE html><html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name}</title>
{pixel_js}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
:root{{--bg:#0d0618;--bg2:#150d28;--text:#f1f0ff;--muted:#9990c0;--accent:#a855f7;--accent2:#7c3aed;--tg:#26A5E4;--wa:#25D366}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{background:var(--bg);color:var(--text);font-family:'Inter',system-ui,sans-serif;min-height:100vh}}
a{{color:inherit;text-decoration:none}}
.wrap{{width:min(1060px,94vw);margin:0 auto}}
.hero{{min-height:100vh;display:flex;align-items:center;justify-content:center;text-align:center;position:relative;overflow:hidden;padding:80px 5vw}}
.hero::before{{content:"";position:absolute;inset:0;background:radial-gradient(ellipse 900px 600px at 50% 40%,rgba(168,85,247,.18),transparent 70%)}}
.hero-inner{{position:relative;z-index:1;max-width:760px}}
.badge{{display:inline-block;padding:.4rem 1rem;border-radius:999px;background:rgba(168,85,247,.15);border:1px solid rgba(168,85,247,.35);color:#d8b4fe;font-size:.83rem;font-weight:600;margin-bottom:1.4rem}}
h1{{font-size:clamp(2.2rem,5vw+.5rem,3.8rem);font-weight:900;line-height:1.05;margin:0 0 1.2rem;letter-spacing:-.02em}}
h1 span{{background:linear-gradient(135deg,#a855f7,#38bdf8);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
.sub{{color:var(--muted);font-size:1.05rem;line-height:1.7;max-width:540px;margin:0 auto 2.4rem}}
.stats{{display:flex;gap:28px;justify-content:center;flex-wrap:wrap;margin-bottom:2.8rem}}
.stat{{text-align:center}}
.stat-v{{font-size:2rem;font-weight:800;color:var(--accent)}}
.stat-l{{font-size:.78rem;color:var(--muted);margin-top:2px}}
.btns{{display:flex;flex-direction:column;gap:.8rem;width:100%;max-width:380px;margin:0 auto}}
.hr-btn{{display:inline-flex;align-items:center;justify-content:center;gap:.65rem;padding:1rem 1.6rem;border-radius:14px;font-weight:700;font-size:1rem;width:100%;transition:transform .15s,opacity .15s}}
.hr-btn:hover{{transform:translateY(-2px);opacity:.9}}
.hr-btn-tg{{background:var(--tg);color:#fff}}
.hr-btn-wa{{background:var(--wa);color:#fff}}
.hr-btn-other{{background:linear-gradient(135deg,var(--accent2),var(--accent));color:#fff}}
.features{{padding:64px 5vw;background:var(--bg2)}}
.features-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px}}
.feat{{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:14px;padding:20px}}
.feat-icon{{font-size:1.5rem;margin-bottom:10px}}
.feat h3{{font-size:.92rem;font-weight:700;margin:0 0 5px;color:var(--text)}}
.feat p{{font-size:.82rem;color:var(--muted);line-height:1.6}}
.cta2{{padding:64px 5vw 80px;text-align:center}}
.cta2 h2{{font-size:clamp(1.4rem,2.5vw+.4rem,2rem);font-weight:800;margin:0 0 .5rem}}
.cta2 p{{color:var(--muted);max-width:460px;margin:0 auto 2rem}}
footer{{text-align:center;padding:24px 0 40px;color:#3d3460;font-size:.83rem}}
@media(max-width:600px){{.stats{{gap:18px}}}}
</style></head><body>
<section class="hero"><div class="hero-inner">
  <div class="badge">Горячая вакансия</div>
  <h1>Работа, которую ты <span>искал(а)</span></h1>
  <p class="sub">Стабильный доход, дружная команда, жильё и обучение. Начни новую главу своей жизни уже сейчас.</p>
  <div class="stats">
    <div class="stat"><div class="stat-v">400$+</div><div class="stat-l">доход в день</div></div>
    <div class="stat"><div class="stat-v">100%</div><div class="stat-l">оформление</div></div>
    <div class="stat"><div class="stat-v">24/7</div><div class="stat-l">поддержка</div></div>
    <div class="stat"><div class="stat-v">1 час</div><div class="stat-l">ответ HR</div></div>
  </div>
  <div class="btns">{buttons}</div>
</div></section>
<section class="features"><div class="wrap">
  <div class="features-grid">
    <div class="feat"><div class="feat-icon">💰</div><h3>Высокий доход</h3><p>Зарабатывай конкурентно с первого дня без задержек.</p></div>
    <div class="feat"><div class="feat-icon">📚</div><h3>Обучение включено</h3><p>Полная подготовка под руководством наставника.</p></div>
    <div class="feat"><div class="feat-icon">🏠</div><h3>Жильё</h3><p>Компания обеспечивает жильём или компенсирует расходы.</p></div>
    <div class="feat"><div class="feat-icon">🗓</div><h3>Гибкий график</h3><p>Сам(а) составляешь расписание смен.</p></div>
    <div class="feat"><div class="feat-icon">🌍</div><h3>Работа за рубежом</h3><p>Множество локаций в крупнейших городах.</p></div>
    <div class="feat"><div class="feat-icon">✅</div><h3>Простой старт</h3><p>Без опыта, без языка, без сложных требований.</p></div>
  </div>
</div></section>
<section class="cta2" id="contact"><div class="wrap">
  <h2>Напиши нам прямо сейчас</h2>
  <p>HR-менеджер ответит в течение часа и расскажет все детали по вакансии.</p>
  <div class="btns">{buttons}</div>
</div></section>
<footer>© {year} {name}. Все права защищены.</footer>
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


@app.get("/api/wa_convs")
async def api_wa_convs(request: Request):
    """Список WA диалогов для авто-обновления"""
    user = check_session(request)
    if not user: return JSONResponse({"error": "unauthorized"}, 401)
    convs = db.get_wa_conversations()
    return JSONResponse({"convs": [
        {
            "id": c["id"],
            "visitor_name": c["visitor_name"],
            "wa_number": c["wa_number"],
            "last_message": c.get("last_message") or "",
            "last_message_at": (c.get("last_message_at") or c["created_at"])[:16].replace("T"," "),
            "unread_count": c.get("unread_count", 0),
            "status": c.get("status", "open"),
        } for c in convs
    ]})

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
        log.warning(f"[WA webhook] Wrong secret: {secret!r}")
        return JSONResponse({"error": "unauthorized"}, 401)
    try:
        body  = await request.json()
    except Exception as e:
        log.error(f"[WA webhook] Bad JSON: {e}")
        return JSONResponse({"ok": True})  # всегда 200 чтобы WA не ретраил

    event = body.get("event")
    data  = body.get("data", {})
    log.info(f"[WA webhook] event={event} keys={list(data.keys())}")

    try:
        if event == "message":
            wa_chat_id  = data.get("wa_chat_id") or data.get("chatId", "")
            wa_number   = data.get("wa_number")  or data.get("from", wa_chat_id).replace("@c.us","")
            sender_name = data.get("sender_name") or data.get("pushname") or wa_number

            raw_text  = data.get("body") or data.get("text") or ""
            media_url  = data.get("media_url")
            media_type = data.get("media_type", "")
            has_media  = data.get("hasMedia") or media_url

            if not raw_text and has_media:
                raw_text = "[фото]" if (media_type or "").startswith("image/") else "[файл]"
            text = (raw_text or "").strip() or "[сообщение]"

            if not wa_chat_id:
                log.warning(f"[WA webhook] no wa_chat_id in data: {data}")
                return JSONResponse({"ok": True})

            conv = db.get_or_create_wa_conversation(wa_chat_id, wa_number, sender_name)
            db.save_wa_message(conv["id"], wa_chat_id, "visitor", text,
                               media_url=media_url, media_type=media_type)
            db.update_wa_last_message(wa_chat_id, text, increment_unread=True)
            log.info(f"[WA webhook] saved msg conv={conv['id']} from={wa_number}: {text[:50]}")

            # Уведомление менеджеру — без Markdown чтобы спецсимволы не ломали
            notify_chat = db.get_setting("notify_chat_id")
            if notify_chat:
                bot = bot_manager.get_tracker_bot() or bot_manager.get_staff_bot()
                if bot:
                    try:
                        from aiogram import types as tg_types
                        preview = text[:80] + ("..." if len(text) > 80 else "")
                        # Используем HTML вместо Markdown — надёжнее
                        safe_name    = sender_name.replace("<","&lt;").replace(">","&gt;")
                        safe_preview = preview.replace("<","&lt;").replace(">","&gt;")
                        safe_number  = str(wa_number).replace("<","&lt;")
                        await bot.send_message(
                            int(notify_chat),
                            f"💚 <b>WhatsApp — новое сообщение</b>\n"
                            f"👤 {safe_name} (+{safe_number})\n\n"
                            f"{safe_preview}",
                            parse_mode="HTML",
                            reply_markup=tg_types.InlineKeyboardMarkup(inline_keyboard=[[
                                tg_types.InlineKeyboardButton(
                                    text="Открыть WA чат →",
                                    url=f"{db.get_setting('app_url','')}/wa/chat?conv_id={conv['id']}"
                                )
                            ]])
                        )
                    except Exception as e:
                        log.warning(f"[WA webhook] notify error: {e}")

        elif event == "ready":
            db.set_setting("wa_connected_number", data.get("number", ""))
            db.set_setting("wa_status", "ready")
            log.info(f"[WA webhook] ready, number={data.get('number')}")

        elif event == "disconnected":
            db.set_setting("wa_status", "disconnected")
            db.set_setting("wa_connected_number", "")
            log.info("[WA webhook] disconnected")

        elif event == "qr":
            db.set_setting("wa_qr", data.get("qr", ""))
            db.set_setting("wa_status", "qr")
            log.info("[WA webhook] QR received")

        else:
            log.info(f"[WA webhook] unknown event: {event}")

    except Exception as e:
        # Логируем но всегда возвращаем 200 — иначе WA сервис будет ретраить бесконечно
        log.error(f"[WA webhook] ERROR event={event}: {e}", exc_info=True)

    return JSONResponse({"ok": True})


@app.get("/wa/chat", response_class=HTMLResponse)
async def wa_chat_page(request: Request, conv_id: int = 0, status_filter: str = "open"):
    user, err = require_auth(request)
    if err: return err
    convs = db.get_wa_conversations(status=status_filter if status_filter != "all" else None)
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
                content_html = ""
                if m.get("media_url") and (m.get("media_type","") or "").startswith("image/"):
                    content_html = f'<img src="{m["media_url"]}" style="max-width:220px;max-height:220px;border-radius:8px;display:block;cursor:pointer" onclick="window.open(this.src)" />'
                    if m.get("content") and m["content"] not in ("[фото]","[медиафайл]"):
                        content_html += f'<div style="margin-top:4px">{(m["content"] or "").replace("<","&lt;")}</div>'
                elif m.get("media_url"):
                    content_html = f'<a href="{m["media_url"]}" target="_blank" style="color:#60a5fa">📎 Открыть файл</a>'
                else:
                    content_html = (m["content"] or "").replace("<","&lt;")
                messages_html += f"""<div class="msg {m['sender_type']}" data-id="{m['id']}">
                  <div class="msg-bubble">{content_html}</div>
                  <div class="msg-time">{t}</div></div>"""
            # Фото профиля WA
            wa_photo = active_conv.get("photo_url","")
            if wa_photo:
                wa_avatar = f'<img src="{wa_photo}" style="width:40px;height:40px;border-radius:50%;object-fit:cover;flex-shrink:0;border:2px solid #25d366" onerror="this.style.display=\'none\'">'
            else:
                wa_avatar = '<div style="width:40px;height:40px;border-radius:50%;background:#052e16;display:flex;align-items:center;justify-content:center;font-size:1.2rem;flex-shrink:0">💚</div>'

            fb_sent = active_conv.get("fb_event_sent")
            fb_btn  = '<span class="badge-green">✅ Lead отправлен</span>' if fb_sent else \
                      f'<form method="post" action="/wa/send_lead" style="display:inline"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-green btn-sm">📤 Lead → FB</button></form>'
            status_color = "#34d399" if active_conv["status"] == "open" else "#ef4444"
            close_btn = f'<form method="post" action="/wa/close"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-gray btn-sm">✓ Закрыть</button></form>' if active_conv["status"] == "open" else \
                        f'<form method="post" action="/wa/reopen"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-green btn-sm">↺ Открыть</button></form>'
            delete_wa_btn = f'<button class="btn-gray btn-sm" style="color:var(--red);border-color:#7f1d1d" onclick="deleteWaConv({conv_id})">🗑</button>'

            # Карточка сотрудника для WA
            wa_staff = db.get_staff_by_wa_conv(conv_id)
            if wa_staff:
                wa_card_link = f'<a href="/staff?edit={wa_staff["id"]}" style="color:#fbbf24;font-size:.74rem;text-decoration:none">Карточка →</a>'
            else:
                wa_card_link = f'<a href="/staff/create_from_wa?conv_id={conv_id}" style="color:var(--text3);font-size:.74rem;text-decoration:none">+ Создать карточку</a>'
            wa_utm_tags = ""
            utm_parts = []
            if active_conv.get("fbclid"):
                utm_parts.append('<span style="background:#1e3a5f;color:#60a5fa;padding:2px 8px;border-radius:5px;font-size:.72rem">🔵 Facebook</span>')
            elif active_conv.get("utm_source"):
                utm_parts.append(f'<span style="background:var(--border);color:var(--text2);padding:2px 8px;border-radius:5px;font-size:.72rem">{active_conv["utm_source"]}</span>')
            if active_conv.get("utm_campaign"):
                utm_parts.append(f'<span style="background:var(--border);color:var(--text2);padding:2px 8px;border-radius:5px;font-size:.72rem">🎯 {active_conv["utm_campaign"][:25]}</span>')
            if utm_parts:
                wa_utm_tags = '<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:5px">' + "".join(utm_parts) + '</div>'

            header_html = f"""<div class="chat-header">
              <div style="display:flex;align-items:flex-start;gap:12px;flex:1">
                {wa_avatar}
                <div style="flex:1">
                  <div style="font-weight:700;color:#fff">{active_conv['visitor_name']} <span style="color:{status_color};font-size:.74rem">●</span></div>
                  <div style="font-size:.79rem;color:var(--text3)">+{active_conv['wa_number']} · {wa_card_link}</div>
                  <div style="margin-top:6px">{fb_btn}</div>
                  {wa_utm_tags}
                </div>
              </div>
              <div style="display:flex;gap:6px;flex-shrink:0">
                <button class="btn-gray btn-sm" title="Обновить профиль" onclick="fetchWaProfile({conv_id})" style="font-size:.8rem">🔄</button>
                {close_btn} {delete_wa_btn}
              </div>
            </div>"""
    conv_items = ""
    for c in convs:
        cls = "conv-item active" if c["id"] == conv_id else "conv-item"
        t = (c.get("last_message_at") or c["created_at"])[:16].replace("T"," ")
        ucount = f'<span class="unread-num" style="background:#25d366">{c["unread_count"]}</span>' if c["unread_count"] > 0 else ""
        dot = "🟢" if c["status"] == "open" else "⚫"
        if c.get("fbclid"):
            src_badge = '<span class="source-badge source-fb">🔵 FB</span>'
        elif c.get("utm_source"):
            src_badge = f'<span class="source-badge source-tg">{c["utm_source"][:12]}</span>'
        else:
            src_badge = '<span class="source-badge source-organic">organic</span>'
        utm_line = f'<div class="conv-meta"><span class="utm-tag">🎯 {c["utm_campaign"][:22]}</span></div>' if c.get("utm_campaign") else ""
        conv_items += f"""<a href="/wa/chat?conv_id={c['id']}&status_filter={status_filter}"><div class="{cls}" data-conv-id="{c['id']}">
          <div class="conv-name"><span>{dot} {c['visitor_name']}</span>{ucount}</div>
          <div class="conv-preview">{c.get('last_message') or 'Нет сообщений'}</div>
          <div class="conv-time" style="display:flex;align-items:center;justify-content:space-between">💚 +{c['wa_number'][:10]} · {t[-5:]} {src_badge}</div>
          {utm_line}</div></a>"""
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

    def wa_stab(label, val):
        active_tab = "background:#25d366;color:#fff" if val == status_filter else "background:var(--bg3);color:var(--text3)"
        return f'<a href="/wa/chat?status_filter={val}" style="flex:1;text-align:center;padding:5px 0;border-radius:7px;font-size:.78rem;font-weight:600;text-decoration:none;{active_tab}">{label}</a>'
    status_tabs = f'<div style="display:flex;gap:4px;background:var(--bg2);border-radius:9px;padding:3px;margin-bottom:8px">{wa_stab("🟢 Открытые","open")}{wa_stab("⚫ Закрытые","closed")}{wa_stab("Все","all")}</div>'

    WA_CSS = "<style>.send-btn-green{background:#25d366;color:#fff;border:none;border-radius:10px;padding:10px 18px;cursor:pointer;font-size:.87rem;font-weight:600;height:42px;flex-shrink:0}.send-btn-green:hover{background:#128c7e}.btn-green{background:#059669;color:#fff;border:none;border-radius:8px;padding:9px 18px;cursor:pointer;font-size:.85rem;font-weight:600;white-space:nowrap}.btn-green:hover{background:#047857}</style>"
    right = f"""{header_html}
    <div class="chat-messages" id="wa-msgs">{messages_html}</div>
    <div class="chat-input"><div class="chat-input-row">
      <input type="file" id="wa-file-input" accept="image/*" style="display:none" onchange="sendWaFile(this)"/>
      <button class="send-btn-green" style="background:#374151;padding:10px 13px;font-size:1.1rem" onclick="document.getElementById('wa-file-input').click()" title="Отправить фото">📎</button>
      <textarea id="wa-reply" placeholder="Написать в WhatsApp… (Enter — отправить)" rows="1" onkeydown="handleWaKey(event)"></textarea>
      <button class="send-btn-green" onclick="sendWaMsg()">Отправить</button>
    </div></div>""" if active_conv and active_conv["status"] == "open" else (
        f"{header_html}<div class='no-conv'><div>Чат закрыт</div></div>" if active_conv else
        '<div class="no-conv"><div style="font-size:2.5rem">💚</div><div>Выбери диалог WhatsApp</div></div>'
    )
    content = f"""{WA_CSS}<div class="chat-layout">
      <div class="conv-list">
        <div class="conv-search">{status_bar}{status_tabs}<input type="text" placeholder="🔍 Поиск..." oninput="filterConvs(this.value)"/></div>
        <div id="conv-items">{conv_items}</div>
      </div>
      <div class="chat-window">{right}</div>
    </div>
    <script>
    const msgsEl=document.getElementById('wa-msgs');
    if(msgsEl) msgsEl.scrollTop=msgsEl.scrollHeight;
    const ACTIVE_CONV_ID = {conv_id or 0};

    async function sendWaMsg(){{
      const ta=document.getElementById('wa-reply');
      const text=ta.value.trim(); if(!text) return; ta.value='';
      await fetch('/wa/send',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},
        body:'conv_id={conv_id}&text='+encodeURIComponent(text)}});
      loadNewWaMsgs();
    }}

    async function sendWaFile(input){{
      const file=input.files[0]; if(!file) return;
      const btn=document.querySelector('button[onclick*="wa-file-input"]');
      btn.textContent='⏳'; btn.disabled=true;
      const fd=new FormData();
      fd.append('conv_id','{conv_id}');
      fd.append('file',file);
      try{{
        const res=await fetch('/wa/send_media',{{method:'POST',body:fd}});
        const data=await res.json();
        if(data.ok) loadNewWaMsgs();
        else alert('Ошибка отправки: '+(data.error||'неизвестно'));
      }}catch(e){{alert('Ошибка: '+e.message);}}
      btn.textContent='📎'; btn.disabled=false;
      input.value='';
    }}
    function handleWaKey(e){{if(e.key==='Enter'&&!e.shiftKey){{e.preventDefault();sendWaMsg();}}}}

    // Обновление сообщений в открытом чате
    {"setInterval(loadNewWaMsgs, 3000);" if active_conv else ""}

    async function loadNewWaMsgs(){{
      const msgs=document.querySelectorAll('#wa-msgs .msg[data-id]');
      const lastId=msgs.length?msgs[msgs.length-1].dataset.id:0;
      const res=await fetch('/api/wa_messages/{conv_id}?after='+lastId);
      const data=await res.json();
      if(data.messages&&data.messages.length>0){{
        const c=document.getElementById('wa-msgs');
        data.messages.forEach(m=>{{
          const d=document.createElement('div');
          d.className='msg '+m.sender_type;
          d.dataset.id=m.id;
          let contentHtml='';
          if(m.media_url && m.media_type && m.media_type.startsWith('image/')){{
            contentHtml='<img src="'+m.media_url+'" style="max-width:220px;max-height:220px;border-radius:8px;display:block;cursor:pointer" onclick="window.open(this.src)"/>';
            if(m.content && m.content!='[фото]' && m.content!='[медиафайл]') contentHtml+='<div style="margin-top:4px">'+esc(m.content)+'</div>';
          }} else if(m.media_url) {{
            contentHtml='<a href="'+m.media_url+'" target="_blank" style="color:#60a5fa">📎 Открыть файл</a>';
          }} else {{
            contentHtml=esc(m.content);
          }}
          d.innerHTML='<div class="msg-bubble">'+contentHtml+'</div><div class="msg-time">'+m.created_at.substring(11,16)+'</div>';
          c.appendChild(d);
        }});c.scrollTop=c.scrollHeight;}}
    }}

    // Авто-обновление списка диалогов каждые 4 сек
    let _knownConvIds = new Set([{','.join(str(c['id']) for c in (db.get_wa_conversations() if True else []))}]);
    setInterval(async function(){{
      try {{
        const res = await fetch('/api/wa_convs');
        const data = await res.json();
        if(!data.convs) return;
        const list = document.getElementById('conv-items');
        if(!list) return;

        // Если появился новый диалог — перерисовываем список
        const newIds = new Set(data.convs.map(c=>c.id));
        const hasNew = [...newIds].some(id=>!_knownConvIds.has(id));

        // Обновляем счётчики непрочитанных всегда
        data.convs.forEach(c=>{{
          const item = list.querySelector('[data-conv-id="'+c.id+'"]');
          if(item){{
            const badge = item.querySelector('.unread-badge');
            if(c.unread_count>0){{
              if(badge) badge.textContent=c.unread_count;
              else {{const b=document.createElement('span');b.className='unread-num unread-badge';b.style.background='#25d366';b.textContent=c.unread_count;item.querySelector('.conv-name')?.appendChild(b);}}
            }} else if(badge) badge.remove();
            const prev=item.querySelector('.conv-preview');
            if(prev) prev.textContent=c.last_message||'Нет сообщений';
          }}
        }});

        if(hasNew){{
          _knownConvIds = newIds;
          // Перерисовываем весь список
          list.innerHTML = data.convs.map(c=>{{
            const active = c.id===ACTIVE_CONV_ID ? ' active' : '';
            const dot = c.status==='open' ? '🟢' : '⚫';
            const badge = c.unread_count>0 ? '<span class="unread-num unread-badge" style="background:#25d366">'+c.unread_count+'</span>' : '';
            return '<a href="/wa/chat?conv_id='+c.id+'"><div class="conv-item'+active+'" data-conv-id="'+c.id+'">'
              +'<div class="conv-name"><span>'+dot+' '+esc(c.visitor_name)+'</span>'+badge+'</div>'
              +'<div class="conv-preview">'+esc(c.last_message||'Нет сообщений')+'</div>'
              +'<div class="conv-time">💚 +'+c.wa_number+' · '+c.last_message_at+'</div>'
              +'</div></a>';
          }}).join('') || '<div class="empty" style="padding:36px 14px">Нет WA диалогов.</div>';
        }}
      }} catch(e){{}}
    }}, 4000);

    function esc(t){{return(t||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\\n/g,'<br>');}}
    function filterConvs(q){{document.querySelectorAll('.conv-item').forEach(el=>{{
      const n=el.querySelector('.conv-name')?.textContent?.toLowerCase()||'';
      el.parentElement.style.display=n.includes(q.toLowerCase())?'':'none';}});}}
    async function deleteWaConv(id){{
      if(!confirm('Удалить WA чат и все сообщения? Это нельзя отменить.')) return;
      const r=await fetch('/wa/delete',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:'conv_id='+id}});
      const d=await r.json();
      if(d.ok) window.location.href='/wa/chat?status_filter={status_filter}';
      else alert('Ошибка удаления');
    }}
    async function fetchWaProfile(convId){{
      const btn=document.querySelector('button[onclick*="fetchWaProfile"]');
      if(btn){{btn.textContent='⏳';btn.disabled=true;}}
      const r=await fetch('/wa/fetch_profile',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:'conv_id='+convId}});
      const d=await r.json();
      if(d.ok) window.location.reload();
      else alert('Не удалось получить профиль: '+(d.error||''));
      if(btn){{btn.textContent='🔄';btn.disabled=false;}}
    }}
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
              <div style="color:var(--text3);font-size:.78rem;margin-top:6px">Обновление через <span id="cd">20</span>с
              <script>let t=20;setInterval(()=>{{const el=document.getElementById('cd');if(el)el.textContent=--t;if(t<=0)location.reload()}},1000)</script></div>
            </div>"""
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""
    err_alert = f'<div class="alert-red">❌ {err}<br><small>Проверь что WA сервис запущен на Railway</small></div>' if err else ""
    WA_BTN_CSS = "<style>.btn-green{background:#059669;color:#fff;border:none;border-radius:8px;padding:9px 18px;cursor:pointer;font-size:.85rem;font-weight:600}.btn-green:hover{background:#047857}</style>"
    if wa_status == "ready":
        status_html = f'<div style="color:#34d399;font-size:1rem;font-weight:600">💚 Подключён · +{wa_number}</div>'
        action_btn  = f"""<div style="margin-top:16px"><form method="post" action="/wa/disconnect">
            <button class="btn-red">🔄 Сменить номер (отключить)</button></form>
            <div style="font-size:.78rem;color:var(--text3);margin-top:6px">После отключения отсканируй QR новым номером</div></div>"""
    elif wa_status == "qr":
        status_html = '<div style="color:#fbbf24;font-size:1rem;font-weight:600">📱 Ожидает сканирования QR...</div>'
        action_btn  = ""
    else:
        status_html = '<div style="color:var(--red);font-size:1rem;font-weight:600">⚠️ Не подключён</div>'
        action_btn  = """<div style="margin-top:16px"><form method="post" action="/wa/connect">
            <button class="btn-green">💚 Подключить WhatsApp</button></form>
            <div style="font-size:.78rem;color:var(--text3);margin-top:6px">Появится QR-код для сканирования</div></div>"""
    content = f"""<div class="page-wrap">
    <div class="page-title">💚 WhatsApp — Управление</div>
    <div class="page-sub">Подключение и смена номера</div>{alert}{err_alert}
    <div class="section" style="border-left:3px solid #25d366">
      <div class="section-head"><h3>📱 Статус подключения</h3></div>
      <div class="section-body">{WA_BTN_CSS}{status_html}{qr_html}{action_btn}</div>
    </div>
    <div class="section"><div class="section-head"><h3>ℹ️ Как это работает</h3></div>
      <div class="section-body" style="font-size:.85rem;color:var(--text3);line-height:2">
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

    # Используем wa_chat_id напрямую — он уже содержит правильный формат от WA сервиса
    # wa_chat_id = "38088390742096@c.us" или "38088390742096@lid" для новых аккаунтов
    to = conv["wa_chat_id"]
    log.info(f"[WA send] to={to} conv_id={conv_id} text={text[:30]}")

    result = await wa_api("post", "/send", json={"to": to, "message": text})
    log.info(f"[WA send] result={result}")

    if not result.get("error"):
        db.save_wa_message(conv_id, conv["wa_chat_id"], "manager", text)
        db.update_wa_last_message(conv["wa_chat_id"], f"Вы: {text}", increment_unread=False)
    return JSONResponse({"ok": not result.get("error"), "error": result.get("error")})


@app.post("/wa/send_media")
async def wa_send_media(request: Request, conv_id: int = Form(...), file: UploadFile = File(...)):
    user, err = require_auth(request)
    if err: return JSONResponse({"error": "unauthorized"}, 401)
    conv = db.get_wa_conversation(conv_id)
    if not conv: return JSONResponse({"error": "not found"}, 404)

    import base64
    file_data = await file.read()
    b64 = base64.b64encode(file_data).decode()
    mimetype = file.content_type or "image/jpeg"
    filename = file.filename or "photo.jpg"

    to = conv["wa_chat_id"]
    log.info(f"[WA send_media] to={to} conv_id={conv_id} file={filename} mime={mimetype} size={len(file_data)}")

    result = await wa_api("post", "/send_media", json={
        "to": to,
        "data": b64,
        "mimetype": mimetype,
        "filename": filename,
        "caption": ""
    })
    log.info(f"[WA send_media] result={result}")

    if not result.get("error"):
        db.save_wa_message(conv_id, conv["wa_chat_id"], "manager", "[фото]",
                           media_url=None, media_type=mimetype)
        db.update_wa_last_message(conv["wa_chat_id"], "Вы: [фото]", increment_unread=False)
    return JSONResponse({"ok": not result.get("error"), "error": result.get("error")})


@app.post("/wa/delete")
async def wa_delete(request: Request, conv_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return JSONResponse({"error": "unauthorized"}, 401)
    try:
        db.delete_wa_conversation(conv_id)
        return JSONResponse({"ok": True})
    except Exception as e:
        log.error(f"[wa/delete] error: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/wa/fetch_profile")
async def wa_fetch_profile(request: Request, conv_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return JSONResponse({"error": "unauthorized"}, 401)
    conv = db.get_wa_conversation(conv_id)
    if not conv: return JSONResponse({"ok": False, "error": "not found"})
    try:
        result = await wa_api("post", "/contact_info", {"wa_chat_id": conv["wa_chat_id"]})
        if result.get("ok"):
            db.update_wa_conv_profile(
                conv_id,
                photo_url=result.get("photo_url"),
                bio=result.get("about")
            )
            # Обновляем имя если получили
            if result.get("name") and result["name"] != conv["visitor_name"]:
                with db._conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute("UPDATE wa_conversations SET visitor_name=%s WHERE id=%s",
                                    (result["name"], conv_id))
                    conn.commit()
        return JSONResponse({"ok": True})
    except Exception as e:
        log.error(f"[wa/fetch_profile] {e}")
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/wa/send_lead")
async def wa_send_lead(request: Request, conv_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    conv = db.get_wa_conversation(conv_id)
    if not conv: return RedirectResponse("/wa/chat", 303)
    if conv.get("fb_event_sent"):
        return RedirectResponse(f"/wa/chat?conv_id={conv_id}", 303)
    # Пиксель сотрудников
    pixel_id   = db.get_setting("pixel_id_staff") or db.get_setting("pixel_id")
    meta_token = db.get_setting("meta_token_staff") or db.get_setting("meta_token")
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
