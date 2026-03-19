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
from landing_templates import (
    _render_campaign_landing,
    _render_client_landing,
    _render_staff_landing,
    _pixel_js,
    _tiktok_pixel_js,
    _t,
    _tshow,
    _build_buttons,
    _tpl_dark_hr,
    _tpl_light_clean,
    _tpl_bold_cta,
    _tpl_massage_job,
    _tpl_tiktok_spa,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

SECRET             = os.getenv("DASHBOARD_PASSWORD", "changeme")

# ── Security: rate limiting для /login ───────────────────────────────────────
import time as _time
_login_attempts: dict = {}   # ip -> [timestamp, ...]
_SESSION_TIMEOUT = 12 * 3600  # 12 часов
_MAX_ATTEMPTS    = 5
_BLOCK_WINDOW    = 600        # 10 минут

def _check_rate_limit(ip: str) -> bool:
    """True = можно войти, False = заблокирован"""
    now = _time.time()
    attempts = _login_attempts.get(ip, [])
    # Убираем старые попытки
    attempts = [t for t in attempts if now - t < _BLOCK_WINDOW]
    _login_attempts[ip] = attempts
    return len(attempts) < _MAX_ATTEMPTS

def _record_attempt(ip: str):
    now = _time.time()
    _login_attempts.setdefault(ip, []).append(now)

def _clear_attempts(ip: str):
    _login_attempts.pop(ip, None)
DEFAULT_BOT1_TOKEN = os.getenv("BOT_TOKEN", "")
DEFAULT_BOT2_TOKEN = os.getenv("BOT2_TOKEN", "")
DEFAULT_PIXEL_ID   = os.getenv("PIXEL_ID", "")
DEFAULT_META_TOKEN = os.getenv("META_TOKEN", "")
APP_URL            = os.getenv("APP_URL", "")
WA_URL             = os.getenv("WA_SERVICE_URL", "").rstrip("/")
TG_SVC_URL         = os.getenv("TG_SERVICE_URL", "").rstrip("/")
TG_SVC_SECRET      = os.getenv("TG_API_SECRET", "changeme")
TG_WH_SECRET       = os.getenv("TG_WEBHOOK_SECRET", "changeme")
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
    # Загружаем настройки безопасности из БД при старте
    global _SESSION_TIMEOUT, _MAX_ATTEMPTS
    try: _SESSION_TIMEOUT = int(db.get_setting("session_timeout_hours") or 12) * 3600
    except: pass
    try: _MAX_ATTEMPTS = int(db.get_setting("login_max_attempts") or 5)
    except: pass
    await bot_manager.start_tracker_bot(db.get_setting("bot1_token"))
    await bot_manager.start_staff_bot(db.get_setting("bot2_token"))
    yield
    await bot_manager.stop_tracker_bot()
    await bot_manager.stop_staff_bot()


app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Middleware: кастомные домены для лендингов ────────────────────────────────
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import HTMLResponse as _HTMLResponse

class CustomDomainMiddleware(BaseHTTPMiddleware):
    """Если запрос пришёл с кастомного домена — показываем нужный лендинг."""
    # Системные домены — не трогаем
    _SYSTEM = ("railway.app", "localhost", "127.0.0.1", "0.0.0.0")

    async def dispatch(self, request, call_next):
        host = request.headers.get("host", "").split(":")[0].lower()
        if host.startswith("www."):
            host = host[4:]

        # Системный домен — обычная обработка
        if not host or any(host.endswith(s) for s in self._SYSTEM):
            return await call_next(request)

        path = request.url.path

        # На корневом пути "/" — ищем лендинг по домену
        if path in ("/", ""):
            landing = db.get_landing_by_domain(host)
            if landing:
                try:
                    qp = dict(request.query_params)
                    fbclid      = qp.get("fbclid", "")
                    utm_source  = qp.get("utm_source", "")
                    utm_medium  = qp.get("utm_medium", "")
                    utm_campaign= qp.get("utm_campaign", "")
                    utm_content = qp.get("utm_content", "")
                    utm_term    = qp.get("utm_term", "")
                    cookie_fbp  = request.cookies.get("_fbp", "")

                    contacts    = db.get_landing_contacts(landing["id"])
                    pixel_staff = db.get_setting("pixel_id_staff", "") or db.get_setting("pixel_id", "")
                    app_url     = db.get_setting("app_url", "").rstrip("/")

                    # Строим tracked_contacts с UTM — как в /l/{slug}
                    import urllib.parse as _up, secrets as _sec
                    tracked_contacts = []
                    for c in contacts:
                        if c.get("url"):
                            c_type = c.get("type", "")
                            if not c_type:
                                if "wa.me" in c["url"] or "whatsapp" in c["url"].lower():
                                    c_type = "whatsapp"
                                elif "t.me" in c["url"] or "telegram" in c["url"].lower():
                                    c_type = "telegram"
                            ref_id = _sec.token_urlsafe(10)
                            db.save_staff_click(
                                ref_id, c["url"], c_type, landing["slug"],
                                fbclid=fbclid, fbp=cookie_fbp,
                                utm_source=utm_source or "facebook",
                                utm_medium=utm_medium or "paid",
                                utm_campaign=utm_campaign,
                                utm_content=utm_content,
                                utm_term=utm_term,
                            )
                            go_url = f"{app_url}/go-staff?ref={ref_id}"
                            tracked_contacts.append({**c, "url": go_url, "type": c_type})
                        else:
                            tracked_contacts.append(c)

                    html = _render_staff_landing(landing, tracked_contacts, pixel_id=pixel_staff, db=db)
                    return _HTMLResponse(html)
                except Exception as e:
                    log.error(f"[CustomDomain] render error: {e}")

        return await call_next(request)

app.add_middleware(CustomDomainMiddleware)

# ══════════════════════════════════════════════════════════════════════════════
# AUTH helpers
# ══════════════════════════════════════════════════════════════════════════════

def check_session(request: Request) -> dict | None:
    """Возвращает user dict если сессия валидна, иначе None"""
    token = request.cookies.get("session")
    if not token: return None
    # token = sha256(username + SECRET + login_ts)
    # Поддержка старого формата (без ts) для обратной совместимости
    for u in db.get_users():
        # Новый формат с таймстампом
        login_ts = request.cookies.get("session_ts", "")
        if login_ts:
            try:
                ts = float(login_ts)
                if _time.time() - ts > _SESSION_TIMEOUT:
                    return None  # Сессия истекла
                expected = hashlib.sha256(f"{u['username']}{SECRET}{login_ts}".encode()).hexdigest()
                if token == expected:
                    return u
            except Exception:
                pass
        # Старый формат (обратная совместимость)
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
*::-webkit-scrollbar{width:4px;height:4px}
*::-webkit-scrollbar-track{background:transparent}
*::-webkit-scrollbar-thumb{background:var(--border2);border-radius:99px}
*::-webkit-scrollbar-thumb:hover{background:var(--text3)}
*{scrollbar-width:thin;scrollbar-color:var(--border2) transparent}
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
.chat-window{display:flex;flex-direction:column;height:calc(100vh - 64px);overflow:hidden}
.chat-header{padding:14px 18px;border-bottom:1px solid var(--border);background:var(--bg2);display:flex;align-items:flex-start;justify-content:space-between;flex-shrink:0;gap:10px}
.tga-avatar-wrap{position:relative;flex-shrink:0;cursor:pointer}
.tga-avatar-wrap:hover .tga-avatar-zoom{display:block}
.tga-avatar-zoom{display:none;position:absolute;top:48px;left:0;z-index:999;width:100px;height:100px;border-radius:10px;overflow:hidden;box-shadow:0 8px 24px rgba(0,0,0,.6);border:2px solid var(--orange)}
.tga-avatar-zoom img{width:100%;height:100%;object-fit:cover}

/* ── STAFF PHOTO HOVER ────────────────────────────── */
.staff-photo-wrap{position:relative;display:inline-block;flex-shrink:0}
.staff-photo-popup{display:none;position:fixed;z-index:9999;pointer-events:none;
  align-items:center;justify-content:center;flex-direction:column;gap:12px}
.staff-photo-popup.visible{display:flex;pointer-events:auto}
.staff-photo-popup img{width:500px;height:500px;object-fit:cover;border-radius:16px;
  box-shadow:0 16px 64px rgba(0,0,0,.8);border:2px solid var(--border2)}
.staff-photo-popup-btns{display:flex;gap:10px}
.staff-photo-popup-btns a{padding:8px 18px;border-radius:8px;font-size:.82rem;font-weight:600;text-decoration:none;cursor:pointer;background:var(--orange);color:#fff}

/* ── STAFF GALLERY ─────────────────────────────────── */
.gallery-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:10px;margin-top:10px}
.gallery-item{position:relative;border-radius:10px;overflow:hidden;aspect-ratio:1;background:var(--bg3);cursor:pointer;border:2px solid transparent;transition:border-color .15s}
.gallery-item:hover{border-color:var(--orange)}
.gallery-item img{width:100%;height:100%;object-fit:cover;display:block}
.gallery-item-del{position:absolute;top:4px;right:4px;background:rgba(0,0,0,.7);color:#fff;border:none;border-radius:5px;width:22px;height:22px;font-size:.75rem;cursor:pointer;display:none;align-items:center;justify-content:center;line-height:1}
.gallery-item:hover .gallery-item-del{display:flex}
.gallery-lightbox{display:none;position:fixed;z-index:9999;top:0;left:0;width:100vw;height:100vh;background:rgba(0,0,0,.88);align-items:center;justify-content:center;flex-direction:column;gap:14px}
.gallery-lightbox.open{display:flex}
.gallery-lightbox img{max-width:min(500px,90vw);max-height:min(500px,80vh);object-fit:contain;border-radius:14px;box-shadow:0 16px 64px rgba(0,0,0,.8);border:2px solid var(--border2)}
.gallery-lightbox-btns{display:flex;gap:10px;align-items:center}
.gallery-lightbox-close{position:absolute;top:20px;right:24px;color:#fff;font-size:1.6rem;cursor:pointer;opacity:.7;line-height:1}
.gallery-lightbox-close:hover{opacity:1}

/* ── CONV TAGS ─────────────────────────────────────── */
.conv-tag{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:99px;font-size:.68rem;font-weight:600;cursor:default;white-space:nowrap;border:1px solid transparent}
.conv-tag-del{background:none;border:none;color:inherit;cursor:pointer;padding:0;font-size:.75rem;opacity:.6;line-height:1;margin-left:2px}
.conv-tag-del:hover{opacity:1}
.tags-row{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}
.tag-picker{position:relative;display:inline-block}
.tag-picker-btn{background:var(--bg3);border:1px dashed var(--border2);border-radius:99px;padding:2px 10px;font-size:.7rem;color:var(--text3);cursor:pointer;transition:all .15s}
.tag-picker-btn:hover{border-color:var(--orange);color:var(--orange)}
.tag-picker-dropdown{display:none;position:absolute;top:calc(100% + 4px);left:0;z-index:500;background:var(--bg2);border:1px solid var(--border2);border-radius:10px;padding:6px;min-width:180px;box-shadow:0 8px 24px rgba(0,0,0,.4);max-height:260px;overflow-y:auto}
.tag-picker-dropdown.open{display:block}
.tag-picker-item{display:flex;align-items:center;gap:8px;padding:5px 8px;border-radius:7px;cursor:pointer;font-size:.8rem;transition:background .1s}
.tag-picker-item:hover{background:var(--bg3)}
.tag-picker-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.tag-picker-empty{padding:8px;color:var(--text3);font-size:.78rem;text-align:center}
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
.avatar{width:38px;height:38px;border-radius:50%;background:#431407;display:flex;align-items:center;justify-content:center;font-size:.88rem;flex-shrink:0;font-weight:700;color:#fb923c}.avatar-zoom{display:none}.avatar-zoom.show{display:block!important}
input[type=date]{background:var(--bg3);color:var(--text);border:1px solid var(--border);border-radius:8px;padding:6px 10px;font-family:'Inter',sans-serif;font-size:.85rem;cursor:pointer;color-scheme:dark}
input[type=date]::-webkit-calendar-picker-indicator{filter:invert(1);opacity:.6;cursor:pointer}
input[type=date]::-webkit-calendar-picker-indicator:hover{opacity:1}
input[type=date]:focus{outline:none;border-color:var(--orange);box-shadow:0 0 0 2px rgba(249,115,22,.15)}

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
    tga_unread = stats.get("tga_unread", 0)
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
        {item("🏷️", "Теги", "tags", "blue")}
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
      {item("📱", "TG Чаты", "tg_account_chat", "orange", badge_count=tga_unread, url="/tg_account/chat", badge_id="nav-tga-badge")}
      {item("💚", "WA Чаты", "wa_chat", "orange", badge_count=wa_unread, url="/wa/chat", badge_id="nav-wa-badge")}
      {item("🗂", "База", "staff", "orange")}
      {item("🌐", "Лендинги HR", "landings_staff", "orange")}
      {item("📊", "Статистика", "analytics_staff", "orange", url="/analytics/staff")}
      {admin_section}
      <div class="sidebar-footer">
        <div class="bot-status"><div class="dot {'dot-green' if b1 else 'dot-red'}"></div><span>{b1_name}</span></div>
        <div class="bot-status"><div class="dot {'dot-green' if b2 else 'dot-red'}"></div><span>{b2_name}</span></div>
        <div class="bot-status"><div class="dot {wa_dot}"></div><span id="nav-wa-status">WhatsApp {'✓' if wa_status == 'ready' else ('QR...' if wa_status == 'qr' else '✗')}</span></div>
        <div class="bot-status"><div class="dot {'dot-green' if db.get_setting('tg_account_status') == 'connected' else 'dot-red'}" id="nav-tg-dot"></div><span id="nav-tg-status">TG {'✓' if db.get_setting('tg_account_status') == 'connected' else '✗'}</span></div>
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
    let _lastTgUnread = {unread}, _lastWaUnread = {wa_unread}, _lastTgaUnread = {tga_unread};
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
        updateBadge('nav-tga-badge', d.tga_unread || 0);
        if(d.unread > _lastTgUnread) showToast('💬 Новое сообщение', 'TG чаты', 'tg-toast', '/chat');
        if(d.wa_unread > _lastWaUnread) showToast('💚 Новое сообщение', 'WhatsApp чаты', 'wa-toast', '/wa/chat');
        if(d.tga_unread > _lastTgaUnread) showToast('📱 Новое сообщение', 'TG Чаты', 'tga-toast', '/tg_account/chat');
        _lastTgUnread = d.unread || 0; _lastWaUnread = d.wa_unread || 0; _lastTgaUnread = d.tga_unread || 0;
        // Задача 2: обновляем статус в сайдбаре
        var waDot=document.querySelector('#nav-wa-status');
        if(waDot && d.wa_status!==undefined){{
          waDot.textContent=d.wa_status==='ready'?'WhatsApp ✓':(d.wa_status==='qr'?'WhatsApp QR...':'WhatsApp ✗');
          var waDotEl=waDot.previousElementSibling;
          if(waDotEl){{waDotEl.className='dot '+(d.wa_status==='ready'?'dot-green':'dot-red');}}
        }}
        var tgDot=document.querySelector('#nav-tg-dot');
        if(tgDot && d.tg_status!==undefined){{
          tgDot.className='dot '+(d.tg_status==='connected'?'dot-green':'dot-red');
          var tgSt=document.querySelector('#nav-tg-status');
          if(tgSt)tgSt.textContent=d.tg_status==='connected'?'TG ✓':'TG ✗';
        }}
      }}catch(e){{}}
    }}
    setInterval(pollUnread, 5000);

    // ── Staff photo hover popup ──────────────────────────────────────────────
    (function(){{
      var _popup = null;
      var _hideTimer = null;

      function showPopup(wrap){{
        var popup = wrap.querySelector('.staff-photo-popup');
        if(!popup) return;
        if(_hideTimer){{ clearTimeout(_hideTimer); _hideTimer = null; }}
        popup.style.top = '0';
        popup.style.left = '0';
        popup.style.width = '100vw';
        popup.style.height = '100vh';
        popup.style.background = 'rgba(0,0,0,0.78)';
        popup.classList.add('visible');
        _popup = popup;
      }}

      function hidePopupNow(popup){{
        if(!popup) return;
        if(_hideTimer){{ clearTimeout(_hideTimer); _hideTimer = null; }}
        popup.classList.remove('visible');
        if(_popup === popup) _popup = null;
      }}

      function hidePopup(popup){{
        if(!popup) return;
        _hideTimer = setTimeout(function(){{
          popup.classList.remove('visible');
          if(_popup === popup) _popup = null;
          _hideTimer = null;
        }}, 80);
      }}

      // Закрытие по клику на фон или крестик
      document.addEventListener('click', function(e){{
        if(!_popup) return;
        var onClose = e.target.closest('.spp-close');
        if(onClose) {{ hidePopupNow(_popup); return; }}
        var onImg  = e.target.closest('.staff-photo-popup img');
        var onBtns = e.target.closest('.staff-photo-popup-btns');
        if(onImg || onBtns) return;
        if(_popup.classList.contains('visible')) hidePopupNow(_popup);
      }});

      document.addEventListener('mouseover', function(e){{
        var wrap = e.target.closest('.staff-photo-wrap');
        if(wrap){{ showPopup(wrap); return; }}
        var popup = e.target.closest('.staff-photo-popup');
        if(popup){{ if(_hideTimer){{ clearTimeout(_hideTimer); _hideTimer = null; }} return; }}
        if(_popup && !_popup.contains(e.target)){{
          var onWrap = e.target.closest('.staff-photo-wrap');
          if(!onWrap) hidePopup(_popup);
        }}
      }});

      document.addEventListener('mouseout', function(e){{
        if(!_popup) return;
        var to = e.relatedTarget;
        if(!to) {{ hidePopup(_popup); return; }}
        var onWrap  = to.closest('.staff-photo-wrap');
        var onPopup = to.closest('.staff-photo-popup');
        if(!onWrap && !onPopup) hidePopup(_popup);
      }});

      // Escape закрывает
      document.addEventListener('keydown', function(e){{
        if(e.key === 'Escape' && _popup) hidePopupNow(_popup);
      }});
    }})();
    </script>"""


def _render_conv_tags_picker(active_tags: list, all_tags: list, active_ids: set, conv_type: str, conv_id: int) -> str:
    """Рендерит строку тегов + кнопку пикера для открытого чата"""
    # Активные теги с кнопкой удаления
    tags_html = ""
    for tg in active_tags:
        tags_html += (
            f'<span class="conv-tag" style="background:{tg["color"]}22;color:{tg["color"]};border-color:{tg["color"]}55" data-tag-id="{tg["id"]}">'
            f'{tg["name"]}'
            f'<button class="conv-tag-del" onclick="removeConvTag(\'{conv_type}\',{conv_id},{tg["id"]},this)" title="Убрать тег">✕</button>'
            f'</span>'
        )
    # Пикер — список доступных тегов (которые ещё не добавлены)
    picker_items = ""
    available = [t for t in all_tags if t["id"] not in active_ids]
    if available:
        for tg in available:
            picker_items += (
                f'<div class="tag-picker-item" onclick="addConvTag(\'{conv_type}\',{conv_id},{tg["id"]},this)">'
                f'<span class="tag-picker-dot" style="background:{tg["color"]}"></span>'
                f'{tg["name"]}'
                f'</div>'
            )
    else:
        picker_items = '<div class="tag-picker-empty">Все теги добавлены</div>'

    manage_link = '<a href="/tags" style="display:block;padding:6px 8px;font-size:.74rem;color:var(--text3);text-decoration:none;border-top:1px solid var(--border);margin-top:4px" onmouseover="this.style.color=\'var(--orange)\'" onmouseout="this.style.color=\'var(--text3)\'">⚙️ Управление тегами</a>'

    picker_html = (
        f'<div class="tag-picker" id="tag-picker-{conv_type}-{conv_id}">'
        f'<button class="tag-picker-btn" onclick="event.stopPropagation();toggleTagPicker(\'{conv_type}\',{conv_id})">＋ Тег</button>'
        f'<div class="tag-picker-dropdown" id="tpd-{conv_type}-{conv_id}">'
        f'{picker_items}'
        f'{manage_link}'
        f'</div></div>'
    )

    return f'<div class="tags-row" id="tags-row-{conv_type}-{conv_id}" style="margin-top:6px">{tags_html}{picker_html}</div>'


def base(content: str, active: str, request: Request) -> str:
    return f'''<!DOCTYPE html><html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TGTracker</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
{CSS}
</head><body>{nav_html(active, request)}<div class="main">{content}</div>
<script>
// ── Глобальные функции пикера тегов ─────────────────────────────────────────
function toggleTagPicker(ct, cid) {{
  var dd = document.getElementById('tpd-' + ct + '-' + cid);
  if (!dd) return;
  var isOpen = dd.classList.contains('open');
  // Закрываем все открытые пикеры
  document.querySelectorAll('.tag-picker-dropdown.open').forEach(function(d) {{ d.classList.remove('open'); }});
  // Открываем текущий если он был закрыт
  if (!isOpen) dd.classList.add('open');
}}
document.addEventListener('click', function(e) {{
  if (!e.target.closest('.tag-picker')) {{
    document.querySelectorAll('.tag-picker-dropdown.open').forEach(function(d) {{ d.classList.remove('open'); }});
  }}
}});
async function addConvTag(ct, cid, tagId, el) {{
  var r = await fetch('/api/conv_tag/add', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{conv_type:ct,conv_id:cid,tag_id:tagId}})}});
  var d = await r.json();
  if (d.ok && d.tag) {{
    var tg = d.tag;
    var row = document.getElementById('tags-row-' + ct + '-' + cid);
    var picker = document.getElementById('tag-picker-' + ct + '-' + cid);
    if (row && picker) {{
      var span = document.createElement('span');
      span.className = 'conv-tag';
      span.setAttribute('data-tag-id', tg.id);
      span.style.cssText = 'background:' + tg.color + '22;color:' + tg.color + ';border-color:' + tg.color + '55';
      span.innerHTML = tg.name + '<button class="conv-tag-del" onclick="removeConvTag(\\\'' + ct + '\\\',' + cid + ',' + tg.id + ',this)" title="Убрать тег">✕</button>';
      row.insertBefore(span, picker);
    }}
    if (el) el.closest('.tag-picker-item').style.display = 'none';
    document.getElementById('tpd-' + ct + '-' + cid)?.classList.remove('open');
  }}
}}
async function removeConvTag(ct, cid, tagId, btn) {{
  var r = await fetch('/api/conv_tag/remove', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{conv_type:ct,conv_id:cid,tag_id:tagId}})}});
  var d = await r.json();
  if (d.ok) {{
    if (btn) btn.closest('.conv-tag').remove();
    // Показываем тег обратно в пикере
    var dd = document.getElementById('tpd-' + ct + '-' + cid);
    if (dd) dd.querySelectorAll('.tag-picker-item').forEach(function(item) {{
      if (item.getAttribute('onclick') && item.getAttribute('onclick').includes(',' + tagId + ',')) item.style.display = '';
    }});
  }}
}}
</script>
</body></html>'''


STAFF_STATUSES = {
    "new":         ("🆕", "Новый",          "badge-gray"),
    "review":      ("👀", "Инструктаж",      "badge-yellow"),
    "interview":   ("🔍", "Верификация",     "badge"),
    "hired":       ("💼", "В работе",        "badge-green"),
    "rejected":    ("🚫", "Слив",            "badge-red"),
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
async def login_submit(request: Request):
    try:
        form = await request.form()
        username = form.get("username", "").strip()
        password = form.get("password", "").strip()
    except Exception:
        return RedirectResponse("/login?error=Ошибка+формы.+Попробуйте+снова.", 303)
    if not username or not password:
        return RedirectResponse("/login?error=Введите+логин+и+пароль.", 303)
    ip = request.client.host if request.client else "unknown"

    # Rate limiting
    if not _check_rate_limit(ip):
        return RedirectResponse("/login?error=Слишком+много+попыток.+Подождите+10+минут.", 303)

    user = db.verify_user(username, password)
    if not user:
        _record_attempt(ip)
        remaining = _MAX_ATTEMPTS - len(_login_attempts.get(ip, []))
        return RedirectResponse(f"/login?error=Неверный+логин+или+пароль.+Осталось+попыток:+{max(0,remaining)}", 303)

    _clear_attempts(ip)
    login_ts = str(_time.time())
    token = hashlib.sha256(f"{user['username']}{SECRET}{login_ts}".encode()).hexdigest()
    resp = RedirectResponse("/overview", 303)
    resp.set_cookie("session", token, max_age=_SESSION_TIMEOUT, httponly=True, samesite="lax")
    resp.set_cookie("session_ts", login_ts, max_age=_SESSION_TIMEOUT, httponly=True, samesite="lax")

    # Уведомление в Telegram при входе
    try:
        notify_chat = db.get_setting("notify_chat_id")
        bot2 = bot_manager.get_staff_bot()
        if notify_chat and bot2:
            import datetime as _dt
            now_str = _dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
            msg_text = (
                "🔐 Вход в CRM\n"
                f"👤 Пользователь: {user['username']} ({user['role']})\n"
                f"🌐 IP: {ip}\n"
                f"🕐 Время: {now_str}"
            )
            await bot2.send_message(notify_chat, msg_text)
    except Exception as e:
        log.warning(f"[login] TG notify error: {e}")

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
        ("interview", "🔍 Верификация"),
        ("hired", "💼 В работе"),
        ("rejected", "🚫 Слив"),
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
    tga_day    = db.get_tga_messages_by_day(days=days, date_from=df, date_to=dt)
    msg_sum    = db.get_messages_summary(days=days, date_from=df, date_to=dt)
    tga_sum    = db.get_tga_messages_summary(days=days, date_from=df, date_to=dt)
    wa_stats   = db.get_wa_stats()
    tga_stats  = db.get_tga_stats()
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
        ("s_interview", "🔍 Верификация", "#f59e0b"),
        ("s_hired",     "💼 В работе",    "#34d399"),
        ("s_rejected",  "🚫 Слив",        "#f87171"),
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
      {kpi(summary['s_hired'], 'В работе', f'{conv_hire}% конверсия', '#34d399')}
      {kpi(summary['s_interview'], 'На интервью', '', '#f59e0b')}
      {kpi(summary['s_rejected'], 'Сливов', '', '#f87171')}
      {kpi(msg_sum['total'], 'Сообщений TG бот', f"{msg_sum['incoming']} вх / {msg_sum['outgoing']} исх")}
      {kpi(msg_sum['active_convos'], 'Активных TG бот чатов', '')}
      {kpi(tga_stats.get('total_convs', 0), 'TG аккаунт чатов', f"{tga_stats.get('open_convs',0)} открытых", '#2ca5e0')}
      {kpi(tga_stats.get('total_msgs', 0), 'Сообщений TG акк', f"{tga_stats.get('incoming',0)} вх / {tga_stats.get('outgoing',0)} исх", '#2ca5e0')}
      {kpi(tga_stats.get('fb_convs', 0), 'TG акк с FB', 'с fbclid', '#1877f2')}
      {kpi(wa_stats.get('total_convs', 0), 'WA чатов всего', f"{wa_stats.get('open_convs',0)} открытых", '#25d366')}
      {kpi(wa_stats.get('total_msgs', 0), 'Сообщений WA', f"{wa_stats.get('incoming',0)} вх / {wa_stats.get('outgoing',0)} исх", '#25d366')}
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
      <div class="section">
        <div class="section-head"><h3>📈 Новые лиды по дням</h3></div>
        <div class="section-body">{sparkline(by_day, 'cnt', '#f97316')}</div>
      </div>
      <div class="section">
        <div class="section-head"><h3>💬 Сообщения TG бот по дням</h3></div>
        <div class="section-body">{sparkline(msg_day, 'total', '#60a5fa')}</div>
      </div>
      <div class="section">
        <div class="section-head"><h3>📱 Сообщения TG аккаунт по дням</h3></div>
        <div class="section-body">{sparkline(tga_day, 'total', '#2ca5e0')}</div>
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

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px">
      <div class="section">
        <div class="section-head"><h3>📱 TG Аккаунт — сводка за период</h3></div>
        <div class="section-body">
          <div style="display:flex;flex-direction:column;gap:8px">
            <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
              <span style="color:var(--text3)">Сообщений всего</span>
              <span style="font-weight:700;color:#2ca5e0">{tga_sum['total']}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
              <span style="color:var(--text3)">Входящих</span>
              <span style="font-weight:700">{tga_sum['incoming']}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
              <span style="color:var(--text3)">Исходящих</span>
              <span style="font-weight:700">{tga_sum['outgoing']}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:8px 0">
              <span style="color:var(--text3)">Активных диалогов</span>
              <span style="font-weight:700">{tga_sum['active_convos']}</span>
            </div>
          </div>
        </div>
      </div>
      <div class="section">
        <div class="section-head"><h3>💚 WhatsApp — сводка за период</h3></div>
        <div class="section-body">
          <div style="display:flex;flex-direction:column;gap:8px">
            <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
              <span style="color:var(--text3)">Сообщений всего</span>
              <span style="font-weight:700;color:#25d366">{wa_stats.get('total_msgs', 0)}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
              <span style="color:var(--text3)">Входящих</span>
              <span style="font-weight:700">{wa_stats.get('incoming', 0)}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
              <span style="color:var(--text3)">Исходящих</span>
              <span style="font-weight:700">{wa_stats.get('outgoing', 0)}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:8px 0">
              <span style="color:var(--text3)">Открытых чатов</span>
              <span style="font-weight:700">{wa_stats.get('open_convs', 0)}</span>
            </div>
          </div>
        </div>
      </div>
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
                sender_label = ""
                if m["sender_type"] == "manager" and m.get("sender_name"):
                    sender_label = f'<div style="font-size:.68rem;color:var(--orange);margin-bottom:2px;text-align:right;opacity:.8">{m["sender_name"]}</div>'
                messages_html += f'<div class="msg {m["sender_type"]}" data-id="{m["id"]}">{sender_label}{bubble}<div class="msg-time">{t}</div></div>'

            # Приоритет: username > visitor_name > tg_chat_id
            _username = active_conv.get('username')
            _vname    = active_conv.get('visitor_name','')
            uname = f"@{_username}" if _username else active_conv.get('tg_chat_id','')
            # Если visitor_name выглядит как числовой ID — заменяем на username
            if _vname and _vname.isdigit() and _username:
                pass  # display_name ниже подставит username
            display_name = _username if (_vname.isdigit() and _username) else (_vname or uname)
            status_color = "var(--green)" if active_conv["status"] == "open" else "var(--red)"
            # Аватарка
            photo_url = active_conv.get("photo_url","")
            if photo_url:
                avatar_html = f'<div style="position:relative;flex-shrink:0;cursor:pointer" onclick="this.querySelector(\'.avatar-zoom\').classList.toggle(\'show\')">'                              f'<img src="{photo_url}" style="width:40px;height:40px;border-radius:50%;object-fit:cover;transition:transform .2s" '                              f'onmouseover="this.style.transform=\'scale(1.1)\'" onmouseout="this.style.transform=\'scale(1)\'" '                              f'onerror="this.style.display=\'none\';this.nextSibling.style.display=\'flex\'" />'                              f'<div class="avatar" style="display:none">{active_conv["visitor_name"][0].upper()}</div>'                              f'<div class="avatar-zoom" style="display:none;position:absolute;top:48px;left:0;z-index:999;border-radius:12px;box-shadow:0 8px 32px rgba(0,0,0,.5);overflow:hidden">'                              f'<img src="{photo_url}" style="width:200px;height:200px;object-fit:cover;display:block" /></div>'                              f'</div>'
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
            is_lead = (staff and staff.get("fb_event_sent")) or active_conv.get("fb_event_sent")
            lead_badge = '<span class="badge-green" style="font-size:.7rem;padding:2px 8px">✅ Lead отправлен</span>' if is_lead else \
                         f'<form method="post" action="/chat/send_lead" style="display:inline"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn btn-sm" style="font-size:.73rem;background:#1e3a5f;border:1px solid #3b5998;color:#93c5fd">📤 Lead → FB</button></form>'

            tg_number = active_conv.get("tg_chat_id","")
            _uname = active_conv.get('username')
            if _uname:
                call_url = f"https://t.me/{_uname}"
            elif tg_number:
                call_url = f"tg://user?id={tg_number}"
            else:
                call_url = None
            call_btn = f'<a href="{call_url}" target="_blank" class="btn-gray btn-sm" style="display:inline-flex;align-items:center;gap:4px;padding:5px 10px;border-radius:7px;font-size:.74rem;border:1px solid var(--border);text-decoration:none">📞 Звонок</a>' if call_url else ""

            close_btn = (f'<form method="post" action="/chat/close"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-gray btn-sm">✓ Закрыть</button></form>'
                        if active_conv["status"] == "open"
                        else f'<form method="post" action="/chat/reopen"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-orange btn-sm">↺ Открыть</button></form>')

            delete_btn = f'<button class="btn-gray btn-sm" style="color:var(--red);border-color:#7f1d1d" onclick="deleteConv({conv_id})">🗑</button>' if user and user.get("role") == "admin" else ""

            staff_link = f'<a href="/staff?edit={staff["id"]}" style="color:var(--orange);font-size:.74rem;text-decoration:none">Карточка →</a>' if staff else \
                         f'<a href="/staff/create_from_conv?conv_id={conv_id}" style="color:var(--text3);font-size:.74rem;text-decoration:none">+ Создать карточку</a>'

            header_html = f"""<div class="chat-header">
              <div style="display:flex;align-items:flex-start;gap:12px;flex:1">
                {avatar_html}
                <div style="flex:1">
                  <div style="font-weight:700;color:var(--text)">{display_name} <span style="color:{status_color};font-size:.72rem">●</span></div>
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
        _utm_src = c.get("utm_source", "")
        if c.get("fbclid") or _utm_src in ("facebook","fb"):
            src_badge = '<span class="source-badge source-fb">🔵 FB</span>'
        elif _utm_src in ("tiktok","tt","tik_tok"):
            src_badge = '<span class="source-badge" style="background:#ff2d55;color:#fff">🎵 TikTok</span>'
        elif c.get("utm_source"):
            src_badge = f'<span class="source-badge source-tg">{c["utm_source"][:12]}</span>'
        else:
            src_badge = '<span class="source-badge source-organic">organic</span>'
        utm_line = ""
        utm_parts = []
        if c.get("utm_campaign"):  utm_parts.append(f'<span class="utm-tag" title="Кампания">🎯 {c["utm_campaign"][:30]}</span>')
        if c.get("utm_content"):   utm_parts.append(f'<span class="utm-tag" style="background:#1a2a1a;color:#86efac" title="Объявление">📌 {c["utm_content"][:20]}</span>')
        if c.get("utm_term"):      utm_parts.append(f'<span class="utm-tag" style="background:#1a1a2a;color:#a5b4fc" title="Адсет">📂 {c["utm_term"][:20]}</span>')
        if utm_parts:
            utm_line = '<div class="conv-meta" style="display:flex;flex-wrap:wrap;gap:3px;margin-top:2px">' + "".join(utm_parts) + '</div>'
        conv_items += f"""<a href="/chat?conv_id={c['id']}&status_filter={status_filter}"><div class="{cls}">
          <div class="conv-name"><span>{dot} {c.get('username') if (c.get('visitor_name','') or '').isdigit() and c.get('username') else c.get('visitor_name') or c.get('username') or c.get('tg_chat_id','')}</span>{ucount}</div>
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
        manager_name = user.get("display_name") or user.get("username") or "Менеджер"
        db.save_message(conv_id, conv["tg_chat_id"], "manager", text, sender_name=manager_name)
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
    # Берём utm из таблицы utm_tracking если есть, иначе из conversations
    utm = db.get_utm_by_conv(conv_id)
    fbclid   = (utm.get("fbclid") if utm else None) or conv.get("fbclid")
    fbp      = (utm.get("fbp") if utm else None) or conv.get("fbp")
    campaign = (utm.get("utm_campaign") if utm else None) or conv.get("utm_campaign") or "telegram"
    utm_src  = (utm.get("utm_source") if utm else None) or conv.get("utm_source") or "telegram"
    test_event_code = db.get_setting("test_event_code") or None
    sent = await meta_capi.send_lead_event(
        pixel_id, meta_token,
        user_id=conv.get("tg_chat_id", ""),
        campaign=campaign,
        fbclid=fbclid,
        fbp=fbp,
        utm_source=utm_src,
        utm_campaign=campaign,
        test_event_code=test_event_code,
    )
    if sent and staff:
        db.set_staff_fb_event(staff["id"], "Lead")
    elif sent:
        db.set_conv_fb_event(conv_id, "Lead")
    # TikTok Lead
    tt_pixel = db.get_setting("tt_pixel_id")
    tt_token = db.get_setting("tt_access_token")
    if tt_pixel and tt_token:
        await send_tiktok_event(tt_pixel, tt_token, "SubmitForm",
            user_id=conv.get("tg_chat_id", ""),
            ip=request.client.host if request.client else None)
    return RedirectResponse(f"/chat?conv_id={conv_id}", 303)


# ══════════════════════════════════════════════════════════════════════════════
# STAFF BASE
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/staff", response_class=HTMLResponse)
async def staff_page(request: Request, edit: int = 0, status_filter: str = "", msg: str = "", sort: str = "newest", search: str = ""):
    user, err = require_auth(request)
    if err: return err
    staff_list = db.get_staff(status_filter if status_filter else None, sort=sort, search=search)
    funnel = db.get_staff_funnel()
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""

    # Поиск и сортировка
    search_bar = f'''<div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center">
      <form method="get" action="/staff" style="display:flex;gap:8px;flex:1;align-items:center;flex-wrap:wrap">
        <input type="hidden" name="status_filter" value="{status_filter}"/>
        <input type="text" name="search" value="{search}" placeholder="🔍 Поиск по имени, Telegram, WhatsApp..." 
               style="flex:1;min-width:200px;padding:6px 12px;background:var(--bg3);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:.84rem"/>
        <select name="sort" style="padding:6px 10px;background:var(--bg3);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:.84rem">
          <option value="newest" {"selected" if sort=="newest" else ""}>Сначала новые</option>
          <option value="oldest" {"selected" if sort=="oldest" else ""}>Сначала старые</option>
          <option value="name" {"selected" if sort=="name" else ""}>По имени А-Я</option>
          <option value="status" {"selected" if sort=="status" else ""}>По статусу</option>
        </select>
        <button class="btn btn-sm">Применить</button>
        {'<a href="/staff"><button class="btn-gray btn-sm" type="button">✕ Сбросить</button></a>' if search or sort != "newest" else ""}
      </form>
    </div>'''

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
            manager_opts = "\n".join(
                '<option value="' + (u.get("display_name") or u["username"]) + '"'
                + (' selected' if s.get("manager_name") == (u.get("display_name") or u["username"]) else '')
                + '>' + (u.get("display_name") or u["username"]) + ' (' + u["role"] + ')</option>'
                for u in db.get_users()
            )
            if s.get("photo_url"):
                _purl = s["photo_url"]
                _pid  = s['id']
                photo_html = (
                    f'<div class="staff-photo-wrap" id="edit-photo-wrap">'
                    f'<img src="{_purl}" style="width:200px;height:200px;border-radius:12px;object-fit:cover;border:2px solid var(--border);display:block" />'
                    f'<div class="staff-photo-popup">'
                    f'<button class="spp-close" title="Закрыть" style="position:absolute;top:16px;right:20px;background:rgba(255,255,255,0.12);border:none;color:#fff;font-size:1.4rem;width:36px;height:36px;border-radius:50%;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:background .15s" onmouseover="this.style.background=\'rgba(255,255,255,0.25)\'" onmouseout="this.style.background=\'rgba(255,255,255,0.12)\'">✕</button>'
                    f'<img src="{_purl}" />'
                    f'<div class="staff-photo-popup-btns">'
                    f'<a href="{_purl}" download="photo_{_pid}.jpg">⬇ Скачать</a>'
                    f'</div></div></div>'
                )
            else:
                photo_html = '<div style="width:200px;height:200px;border-radius:12px;background:var(--bg3);border:2px dashed var(--border);display:flex;align-items:center;justify-content:center;font-size:3rem">👤</div>'
            # Галерея
            gallery_items = db.get_staff_gallery(s['id'])
            gallery_html = ""
            if gallery_items:
                gallery_html = '<div class="gallery-grid" id="staff-gallery">'
                for gi in gallery_items:
                    gi_id   = gi["id"]
                    gi_url  = gi["photo_url"]
                    s_id    = s["id"]
                    gallery_html += (
                        f'<div class="gallery-item" onclick="openGalleryLightbox(\'{gi_url}\',{gi_id})">'
                        f'<img src="{gi_url}" loading="lazy" />'
                        f'<button class="gallery-item-del" onclick="event.stopPropagation();deleteGalleryPhoto({gi_id},{s_id})" title="Удалить">✕</button>'
                        f'</div>'
                    )
                gallery_html += '</div>'
            else:
                gallery_html = '<div style="color:var(--text3);font-size:.82rem;padding:8px 0">Нет дополнительных фото</div>'
            edit_form = f"""<div class="section" style="margin-bottom:18px;border-left:3px solid #f97316">
              <div class="section-head"><h3>✏️ {s.get('name','Карточка')}</h3>{chat_link}</div>
              <div class="section-body">
                <form method="post" action="/staff/update" enctype="multipart/form-data">
                  <input type="hidden" name="staff_id" value="{s['id']}"/>
                  <div style="margin-bottom:16px;display:flex;align-items:flex-start;gap:16px;flex-wrap:wrap">
                    {photo_html}
                    <div style="display:flex;flex-direction:column;gap:10px">
                      <div>
                        <div class="field-label" style="margin-bottom:6px">Главное фото</div>
                        <input type="file" name="staff_photo" accept="image/*" style="font-size:.82rem;color:var(--text3)"/>
                        <div style="font-size:.72rem;color:var(--text3);margin-top:4px">JPG, PNG до 5MB</div>
                      </div>
                    </div>
                  </div>
                  <div class="grid-3" style="margin-bottom:12px">
                    <div class="field-group"><div class="field-label">Имя</div><input type="text" name="name" value="{s.get('name') or ''}"/></div>
                    <div class="field-group"><div class="field-label">Telegram</div><input type="text" name="phone" value="{s.get('phone') or ''}" placeholder="@username или +номер"/></div>
                    <div class="field-group"><div class="field-label">WhatsApp</div><input type="text" name="email" value="{s.get('email') or ''}" placeholder="+1234567890"/></div>
                    <div class="field-group"><div class="field-label">Должность</div><input type="text" name="position" value="{s.get('position') or ''}"/></div>
                    <div class="field-group"><div class="field-label">Статус</div><select name="status">{status_opts}</select></div>
                  </div>
                  <div class="field-group" style="margin-bottom:12px"><div class="field-label">Заметки</div><textarea name="notes">{s.get('notes') or ''}</textarea></div>
                  <div class="field-group" style="margin-bottom:12px">
                    <div class="field-label">👤 Закреплён за менеджером</div>
                    <select name="manager_name" style="width:100%;padding:7px 10px;background:var(--bg3);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:.84rem">
                      <option value="">— Не закреплён —</option>
                      {manager_opts}
                    </select>
                  </div>
                  <div style="display:flex;gap:8px">
                    <button class="btn-orange">💾 Сохранить</button>
                    <a href="/staff"><button class="btn-gray" type="button">Отмена</button></a>
                  </div>
                </form>
                <!-- Галерея -->
                <div style="margin-top:20px;padding-top:16px;border-top:1px solid var(--border)">
                  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
                    <div style="font-weight:600;font-size:.9rem">🖼 Галерея фото ({len(gallery_items)})</div>
                    <label style="background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:5px 12px;font-size:.78rem;cursor:pointer;color:var(--text2);transition:border-color .15s" onmouseover="this.style.borderColor='var(--orange)'" onmouseout="this.style.borderColor='var(--border)'">
                      ➕ Добавить фото
                      <input type="file" accept="image/*" multiple style="display:none" onchange="uploadGalleryPhotos(this,{s['id']})"/>
                    </label>
                  </div>
                  {gallery_html}
                </div>
              </div></div>
<!-- Lightbox для галереи -->
<div class="gallery-lightbox" id="gallery-lightbox">
  <span class="gallery-lightbox-close" onclick="closeGalleryLightbox()">✕</span>
  <img src="" id="lightbox-img" />
  <div class="gallery-lightbox-btns">
    <a id="lightbox-dl" href="#" download style="background:var(--orange);color:#fff;padding:8px 18px;border-radius:8px;font-size:.82rem;font-weight:600;text-decoration:none">⬇ Скачать</a>
    <button onclick="closeGalleryLightbox()" style="background:var(--bg3);color:var(--text);border:1px solid var(--border);border-radius:8px;padding:8px 18px;font-size:.82rem;cursor:pointer">Закрыть</button>
  </div>
</div>
<script>
function openGalleryLightbox(url, id) {{
  var lb = document.getElementById('gallery-lightbox');
  var img = document.getElementById('lightbox-img');
  var dl = document.getElementById('lightbox-dl');
  if (!lb || !img) return;
  img.src = url;
  dl.href = url;
  dl.download = 'photo_' + id + '.jpg';
  lb.classList.add('open');
}}
function closeGalleryLightbox() {{
  var lb = document.getElementById('gallery-lightbox');
  if (lb) lb.classList.remove('open');
}}
document.addEventListener('keydown', function(e) {{
  if (e.key === 'Escape') closeGalleryLightbox();
}});
async function uploadGalleryPhotos(input, staffId) {{
  if (!input.files || !input.files.length) return;
  var files = Array.from(input.files);
  var uploaded = 0;
  for (var i = 0; i < files.length; i++) {{
    var fd = new FormData();
    fd.append('staff_id', staffId);
    fd.append('photo', files[i]);
    try {{
      var r = await fetch('/staff/gallery/add', {{method:'POST', body: fd}});
      var d = await r.json();
      if (d.ok) uploaded++;
    }} catch(e) {{ console.error(e); }}
  }}
  if (uploaded > 0) window.location.reload();
  else alert('Ошибка загрузки фото');
}}
async function deleteGalleryPhoto(photoId, staffId) {{
  if (!confirm('Удалить фото из галереи?')) return;
  var fd = new FormData();
  fd.append('photo_id', photoId);
  fd.append('staff_id', staffId);
  var r = await fetch('/staff/gallery/delete', {{method:'POST', body: fd}});
  var d = await r.json();
  if (d.ok) window.location.reload();
  else alert('Ошибка удаления');
}}
</script>"""

    rows = ""
    for s in staff_list:
        icon, label, badge_cls = STAFF_STATUSES.get(s.get("status","new"), ("🆕","Новый","badge-gray"))
        fb = '<span class="badge-green" style="font-size:.7rem">FB ✓</span>' if s.get("fb_event_sent") else ""
        _photo = s.get("photo_url") or ""
        if _photo:
            _sid = s['id']
            _avatar = (
                f'<div class="staff-photo-wrap">'
                f'<img src="{_photo}" style="width:36px;height:36px;border-radius:8px;object-fit:cover;display:block" />'
                f'<div class="staff-photo-popup">'
                f'<button class="spp-close" title="Закрыть" style="position:absolute;top:16px;right:20px;background:rgba(255,255,255,0.12);border:none;color:#fff;font-size:1.4rem;width:36px;height:36px;border-radius:50%;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:background .15s" onmouseover="this.style.background=\'rgba(255,255,255,0.25)\'" onmouseout="this.style.background=\'rgba(255,255,255,0.12)\'">✕</button>'
                f'<img src="{_photo}" />'
                f'<div class="staff-photo-popup-btns">'
                f'<a href="{_photo}" download="photo_{_sid}.jpg">⬇ Скачать</a>'
                f'<a href="/staff?edit={_sid}" style="background:var(--bg3);color:var(--text);border:1px solid var(--border)">✏️ Карточка</a>'
                f'</div></div></div>'
            )
        else:
            _avatar = '<div style="width:36px;height:36px;border-radius:8px;background:var(--bg3);display:flex;align-items:center;justify-content:center;font-size:.9rem;flex-shrink:0">👤</div>'
        rows += f"""<tr>
            <td><div style="display:flex;align-items:center;gap:8px">
              {_avatar}
              <div>
                <div style="font-weight:600;color:#fff">{s['name'] or '—'}</div>
                <div style="font-size:.75rem;color:var(--text3)">@{s['username'] or '—'}</div>
              </div>
            </div></td>
            <td>{s.get('position') or '—'}</td>
            <td><span class="{badge_cls}">{icon} {label}</span></td>
            <td>{s.get('phone') or '—'}</td>
            <td style="font-size:.8rem;color:#86efac">{s.get('email') or '—'}</td>
            <td style="font-size:.8rem;color:var(--orange)">{s.get('manager_name') or '—'}</td>
            <td>{fb}</td>
            <td>{s['created_at'][:10]}</td>
            <td style="white-space:nowrap">
              <a href="/staff?edit={s['id']}"><button class="btn-orange btn-sm">✏️</button></a>
              {'<a href="/chat?conv_id=' + str(s.get("conversation_id","")) + '"><button class="btn-gray btn-sm" style="margin-left:4px">💬</button></a>' if s.get("conversation_id") else ''}
              {('<form method="post" action="/staff/delete" style="display:inline"><input type="hidden" name="staff_id" value="' + str(s["id"]) + '"/><button class="btn-gray btn-sm" style="color:var(--red);border-color:#7f1d1d;margin-left:4px" onclick="return confirm(''Удалить сотрудника полностью?'')">🗑</button></form>') if user and user.get("role") == "admin" else ""}
            </td></tr>"""

    if not rows:
        rows = '<tr><td colspan="7"><div class="empty">Нет сотрудников</div></td></tr>'

    content = f"""<div class="page-wrap">
    <div class="page-title">🗂 База сотрудников</div>
    <div class="page-sub">Все кто написал боту</div>
    {alert}
    {search_bar}
    <div style="margin-bottom:16px">{filter_btns}</div>
    {edit_form}
    <div class="section">
      <div class="section-head"><h3>📋 Сотрудники ({len(staff_list)})</h3></div>
      <table><thead><tr><th>Имя</th><th>Должность</th><th>Статус</th><th>Telegram</th><th>WhatsApp</th><th>Менеджер</th><th>FB</th><th>Добавлен</th><th></th></tr></thead>
      <tbody>{rows}</tbody></table>
    </div></div>"""
    return HTMLResponse(base(content, "staff", request))


@app.post("/staff/update")
async def staff_update(request: Request, staff_id: int = Form(...), name: str = Form(""),
                        phone: str = Form(""), email: str = Form(""), position: str = Form(""),
                        status: str = Form("new"), notes: str = Form(""), tags: str = Form(""),
                        manager_name: str = Form(""), staff_photo: UploadFile = File(None)):
    user, err = require_auth(request)
    if err: return err
    db.update_staff(staff_id, name, phone, email, position, status, notes, tags, manager_name=manager_name.strip())
    # Загрузка фото если прислали
    if staff_photo and staff_photo.filename:
        try:
            import cloudinary, cloudinary.uploader, base64 as _b64
            photo_data = await staff_photo.read()
            cld_url = db.get_setting("cloudinary_url") or os.getenv("CLOUDINARY_URL", "")
            photo_url = None
            if cld_url:
                cloudinary.config(cloudinary_url=cld_url)
                b64 = _b64.b64encode(photo_data).decode()
                mime = staff_photo.content_type or "image/jpeg"
                result = cloudinary.uploader.upload(
                    f"data:{mime};base64,{b64}",
                    folder="staff_photos", resource_type="image"
                )
                photo_url = result.get("secure_url")
            else:
                mime = staff_photo.content_type or "image/jpeg"
                photo_url = f"data:{mime};base64,{_b64.b64encode(photo_data).decode()}"
            if photo_url:
                db.update_staff_photo(staff_id, photo_url)
        except Exception as e:
            log.error(f"[staff/update] photo upload error: {e}")
    return RedirectResponse(f"/staff?msg=Сохранено", 303)


@app.post("/staff/delete")
async def staff_delete(request: Request, staff_id: int = Form(...)):
    user, err = require_auth(request, role="admin")
    if err: return err
    db.delete_staff_full(staff_id)
    return RedirectResponse("/staff?msg=Сотрудник+удалён+полностью", 303)


@app.post("/staff/gallery/add")
async def staff_gallery_add(request: Request, staff_id: int = Form(...), photo: UploadFile = File(...)):
    """Добавить фото в галерею сотрудника"""
    user, err = require_auth(request)
    if err: return JSONResponse({"ok": False, "error": "unauthorized"}, 401)
    if not photo or not photo.filename:
        return JSONResponse({"ok": False, "error": "no file"})
    try:
        import cloudinary, cloudinary.uploader, base64 as _b64
        photo_data = await photo.read()
        cld_url = db.get_setting("cloudinary_url") or os.getenv("CLOUDINARY_URL", "")
        photo_url = None
        if cld_url:
            cloudinary.config(cloudinary_url=cld_url)
            mime = photo.content_type or "image/jpeg"
            b64 = _b64.b64encode(photo_data).decode()
            result = cloudinary.uploader.upload(
                f"data:{mime};base64,{b64}",
                folder="staff_gallery", resource_type="image"
            )
            photo_url = result.get("secure_url")
        else:
            mime = photo.content_type or "image/jpeg"
            photo_url = f"data:{mime};base64,{_b64.b64encode(photo_data).decode()}"
        if not photo_url:
            return JSONResponse({"ok": False, "error": "upload failed"})
        gi = db.add_staff_gallery_photo(staff_id, photo_url)
        return JSONResponse({"ok": True, "id": gi["id"], "photo_url": photo_url})
    except Exception as e:
        log.error(f"[gallery/add] error: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


@app.post("/staff/gallery/delete")
async def staff_gallery_delete(request: Request, photo_id: int = Form(...), staff_id: int = Form(...)):
    """Удалить фото из галереи"""
    user, err = require_auth(request)
    if err: return JSONResponse({"ok": False, "error": "unauthorized"}, 401)
    ok = db.delete_staff_gallery_photo(photo_id, staff_id)
    return JSONResponse({"ok": ok})


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


@app.get("/staff/create_from_tga")
async def staff_create_from_tga(request: Request, conv_id: int = 0):
    """Создать карточку сотрудника из TG аккаунт чата"""
    user, err = require_auth(request)
    if err: return err
    if not conv_id:
        return RedirectResponse("/tg_account/chat", 303)
    conv = db.get_tg_account_conversation(conv_id)
    if not conv:
        return RedirectResponse("/tg_account/chat", 303)
    existing = db.get_staff_by_tg_account_conv(conv_id)
    if existing:
        return RedirectResponse(f"/staff?edit={existing['id']}", 303)
    staff = db.get_or_create_tga_staff(
        tga_conv_id=conv_id,
        name=conv.get("visitor_name", "Новый"),
        username=conv.get("username", "")
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
    sec_notify_chat = db.get_setting("notify_chat_id", "")
    sec_session_hours = db.get_setting("session_timeout_hours", "12")
    sec_max_attempts = db.get_setting("login_max_attempts", "5")

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
        if eu:
            eu_perms = eu.get("permissions") or ""
            edit_form = f"""<div class="section" style="border-left:3px solid #f97316;margin-bottom:20px">
              <div class="section-head"><h3>✏️ Редактировать: {eu['username']}</h3></div>
              <div class="section-body">
                <form method="post" action="/users/update">
                  <input type="hidden" name="user_id" value="{eu['id']}"/>
                  <div class="grid-2" style="margin-bottom:12px">
                    <div class="field-group"><div class="field-label">Имя (отображается в чатах)</div>
                      <input type="text" name="display_name" value="{eu.get('display_name') or ''}" placeholder="Например: Анна"/></div>
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
        is_self = u["username"] == user["username"]
        self_badge = ' <span style="font-size:.7rem;color:var(--orange)">(вы)</span>' if is_self else ""
        edit_btn = f'<a href="/users?edit={u["id"]}"><button class="btn-gray btn-sm">✏️</button></a>'

        del_btn  = f'<form method="post" action="/users/delete" style="display:inline"><input type="hidden" name="user_id" value="{u["id"]}"/><button class="del-btn btn-sm">✕</button></form>' if u["username"] != user["username"] else ""
        rows += f"""<tr>
            <td>{u.get('display_name') or '—'}</td>
            <td><b>{u['username']}</b>{self_badge}</td>
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
    <div class="section" style="border-left:3px solid #7c3aed">
      <div class="section-head"><h3>🛡 Безопасность & Уведомления</h3></div>
      <div class="section-body">
        <form method="post" action="/users/security">
          <div class="grid-2" style="margin-bottom:14px">
            <div class="field-group">
              <div class="field-label">Telegram Chat ID для уведомлений о входе</div>
              <input type="text" name="notify_chat_id" value="{sec_notify_chat}" placeholder="Например: -1001234567890"/>
              <div style="font-size:.74rem;color:var(--text3);margin-top:4px">Напишите /start боту @userinfobot чтобы узнать свой ID</div>
            </div>
            <div class="field-group">
              <div class="field-label">Время сессии (часов)</div>
              <input type="number" name="session_timeout_hours" value="{sec_session_hours}" min="1" max="72" placeholder="12"/>
              <div style="font-size:.74rem;color:var(--text3);margin-top:4px">После скольких часов неактивности выходить автоматически</div>
            </div>
            <div class="field-group">
              <div class="field-label">Макс. попыток входа до блокировки IP</div>
              <input type="number" name="login_max_attempts" value="{sec_max_attempts}" min="1" max="20" placeholder="5"/>
              <div style="font-size:.74rem;color:var(--text3);margin-top:4px">IP блокируется на 10 минут после N неудачных попыток</div>
            </div>
          </div>
          <button class="btn" style="background:#7c3aed">🛡 Сохранить настройки безопасности</button>
        </form>
      </div>
    </div>

    <div class="section"><div class="section-head"><h3>➕ Добавить пользователя</h3></div>
    <div class="section-body">
      <form method="post" action="/users/add">
        <div class="grid-2" style="margin-bottom:12px">
          <div class="field-group"><div class="field-label">Имя (отображается в чатах)</div><input type="text" name="display_name" placeholder="Например: Анна"/></div>
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
    <table><thead><tr><th>Имя</th><th>Логин</th><th>Роль</th><th>Доступы</th><th>Создан</th><th></th></tr></thead>
    <tbody>{rows}</tbody></table></div></div>"""
    return HTMLResponse(base(content, "users", request))


@app.post("/users/security")
async def users_security(request: Request,
                          notify_chat_id: str = Form(""),
                          session_timeout_hours: str = Form("12"),
                          login_max_attempts: str = Form("5")):
    user, err = require_auth(request, role="admin")
    if err: return err
    db.set_setting("notify_chat_id", notify_chat_id.strip())
    db.set_setting("session_timeout_hours", session_timeout_hours.strip() or "12")
    db.set_setting("login_max_attempts", login_max_attempts.strip() or "5")
    # Обновляем глобальные переменные в памяти
    global _SESSION_TIMEOUT, _MAX_ATTEMPTS
    try: _SESSION_TIMEOUT = int(session_timeout_hours) * 3600
    except: pass
    try: _MAX_ATTEMPTS = int(login_max_attempts)
    except: pass
    return RedirectResponse("/users?msg=Настройки+безопасности+сохранены", 303)


@app.post("/users/security")
async def users_security(request: Request,
                          notify_chat_id: str = Form(""),
                          session_timeout_hours: str = Form("12"),
                          login_max_attempts: str = Form("5")):
    user, err = require_auth(request, role="admin")
    if err: return err
    db.set_setting("notify_chat_id", notify_chat_id.strip())
    db.set_setting("session_timeout_hours", session_timeout_hours.strip() or "12")
    db.set_setting("login_max_attempts", login_max_attempts.strip() or "5")
    # Обновляем глобальные переменные в памяти
    global _SESSION_TIMEOUT, _MAX_ATTEMPTS
    try: _SESSION_TIMEOUT = int(session_timeout_hours) * 3600
    except: pass
    try: _MAX_ATTEMPTS = int(login_max_attempts)
    except: pass
    return RedirectResponse("/users?msg=Настройки+безопасности+сохранены", 303)


@app.post("/users/add")
async def users_add(request: Request, username: str = Form(...), password: str = Form(...), role: str = Form("manager"), display_name: str = Form("")):
    user, err = require_auth(request, role="admin")
    if err: return err
    ALL_TAB_IDS = ["overview","channels","campaigns","landings","analytics_clients",
                   "chat","wa_chat","staff","landings_staff","analytics_staff"]
    form = await request.form()
    checked = [t for t in ALL_TAB_IDS if form.get(f"perm_{t}")]
    perms = "" if len(checked) == len(ALL_TAB_IDS) else ",".join(checked)
    try:
        db.create_user(username.strip(), password, role, perms, display_name.strip())
        return RedirectResponse("/users?msg=Пользователь+добавлен", 303)
    except:
        return RedirectResponse("/users?msg=Такой+логин+уже+существует", 303)


@app.post("/users/update")
async def users_update(request: Request, user_id: int = Form(...), username: str = Form(...),
                        role: str = Form("manager"), new_password: str = Form(""), display_name: str = Form("")):
    user, err = require_auth(request, role="admin")
    if err: return err
    ALL_TAB_IDS = ["overview","channels","campaigns","landings","analytics_clients",
                   "chat","wa_chat","staff","landings_staff","analytics_staff"]
    form = await request.form()
    checked = [t for t in ALL_TAB_IDS if form.get(f"perm_{t}")]
    perms = "" if len(checked) == len(ALL_TAB_IDS) else ",".join(checked)
    db.update_user(user_id, username.strip(), role, perms, new_password.strip() or None, display_name.strip())
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
# ТЕГИ
# ══════════════════════════════════════════════════════════════════════════════

TAG_COLORS = [
    "#6366f1","#f97316","#22c55e","#ec4899","#3b82f6",
    "#a855f7","#14b8a6","#f59e0b","#ef4444","#64748b",
]

@app.get("/tags", response_class=HTMLResponse)
async def tags_page(request: Request, msg: str = ""):
    user, err = require_auth(request, role="admin")
    if err: return err
    all_tags = db.get_all_tags()
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""

    color_opts = "".join(
        f'<span onclick="document.getElementById(\'tag-color\').value=\'{c}\';this.parentNode.querySelectorAll(\'span\').forEach(s=>s.style.outline=\'none\');this.style.outline=\'3px solid #fff\'" '
        f'style="display:inline-block;width:22px;height:22px;border-radius:50%;background:{c};cursor:pointer;transition:outline .1s"></span>'
        for c in TAG_COLORS
    )

    rows = ""
    for t in all_tags:
        _tname  = t['name']
        _tcolor = t['color']
        _tid    = t['id']
        rows += f"""<tr>
            <td><span class="conv-tag" style="background:{_tcolor}22;color:{_tcolor};border-color:{_tcolor}55">⬤ {_tname}</span></td>
            <td><input type="color" value="{_tcolor}" onchange="updateTagColor({_tid},this.value)" style="width:32px;height:28px;border:none;background:none;cursor:pointer;padding:0"/></td>
            <td>
              <form method="post" action="/tags/delete" style="display:inline">
                <input type="hidden" name="tag_id" value="{_tid}"/>
                <button class="btn-gray btn-sm" style="color:var(--red);border-color:#7f1d1d" onclick="return confirm('Удалить тег «{_tname}»? Он отвяжется от всех чатов.')">🗑 Удалить</button>
              </form>
            </td></tr>"""
    if not rows:
        rows = '<tr><td colspan="3"><div class="empty">Тегов пока нет</div></td></tr>'

    content = f"""<div class="page-wrap">
    <div class="page-title">🏷️ Управление тегами</div>
    <div class="page-sub">Создавай теги и добавляй их к чатам TG и WhatsApp</div>
    {alert}
    <div class="section" style="margin-bottom:18px">
      <div class="section-head"><h3>➕ Создать тег</h3></div>
      <div class="section-body">
        <form method="post" action="/tags/create" style="display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap">
          <div class="field-group" style="max-width:220px">
            <div class="field-label">Название</div>
            <input type="text" name="name" placeholder="Например: Массаж, VIP, США..." required maxlength="32"/>
          </div>
          <div class="field-group">
            <div class="field-label">Цвет</div>
            <div style="display:flex;align-items:center;gap:8px">
              <input type="color" name="color" id="tag-color" value="#6366f1" style="width:36px;height:36px;border:none;background:none;cursor:pointer;padding:0"/>
              <div style="display:flex;gap:5px;flex-wrap:wrap;max-width:200px">{color_opts}</div>
            </div>
          </div>
          <button class="btn">Создать</button>
        </form>
      </div>
    </div>
    <div class="section">
      <div class="section-head"><h3>📋 Все теги ({len(all_tags)})</h3></div>
      <table><thead><tr><th>Тег</th><th>Цвет</th><th></th></tr></thead>
      <tbody>{rows}</tbody></table>
    </div>
    </div>
    <script>
    async function updateTagColor(tagId, color) {{
      await fetch('/tags/update_color', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{tag_id:tagId,color:color}})}});
    }}
    </script>"""
    return HTMLResponse(base(content, "tags", request))


@app.post("/tags/create")
async def tags_create(request: Request, name: str = Form(""), color: str = Form("#6366f1")):
    user, err = require_auth(request, role="admin")
    if err: return err
    if name.strip():
        try:
            db.create_tag(name.strip(), color)
        except Exception:
            return RedirectResponse("/tags?msg=Тег+с+таким+именем+уже+существует", 303)
    return RedirectResponse("/tags?msg=Тег+создан", 303)


@app.post("/tags/delete")
async def tags_delete(request: Request, tag_id: int = Form(...)):
    user, err = require_auth(request, role="admin")
    if err: return err
    db.delete_tag(tag_id)
    return RedirectResponse("/tags?msg=Тег+удалён", 303)


@app.post("/tags/update_color")
async def tags_update_color(request: Request):
    user, err = require_auth(request, role="admin")
    if err: return JSONResponse({"ok": False})
    body = await request.json()
    db.update_tag(body["tag_id"], "", body["color"])  # name пустой — обновим только цвет
    return JSONResponse({"ok": True})


# ── API: привязать / отвязать тег от чата ────────────────────────────────────

@app.post("/api/conv_tag/add")
async def api_conv_tag_add(request: Request):
    user = check_session(request)
    if not user: return JSONResponse({"ok": False}, 401)
    body = await request.json()
    ok = db.add_conv_tag(body["conv_type"], body["conv_id"], body["tag_id"])
    tag = next((t for t in db.get_all_tags() if t["id"] == body["tag_id"]), None)
    return JSONResponse({"ok": ok, "tag": tag})


@app.post("/api/conv_tag/remove")
async def api_conv_tag_remove(request: Request):
    user = check_session(request)
    if not user: return JSONResponse({"ok": False}, 401)
    body = await request.json()
    ok = db.remove_conv_tag(body["conv_type"], body["conv_id"], body["tag_id"])
    return JSONResponse({"ok": ok})


@app.get("/api/tags")
async def api_get_tags(request: Request):
    user = check_session(request)
    if not user: return JSONResponse({"ok": False}, 401)
    return JSONResponse({"tags": db.get_all_tags()})


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
    test_event_code = db.get_setting("test_event_code", "")

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
    {bot_card("🟠 Бот 2 — Уведомления (авторизация)", "orange", b2_info, "bot2_token", "settings/bot2")}

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

    <div class="section" style="border-left:3px solid #2563eb">
      <div class="section-head"><h3>📱 Telegram Аккаунт</h3>
        <span style="font-size:.82rem">
          {'<span style="color:#34d399">● Подключён · @' + db.get_setting("tg_account_username","") + '</span>'
           if db.get_setting("tg_account_status") == "connected"
           else '<span style="color:var(--red)">● Не подключён</span>'}
        </span>
      </div>
      <div class="section-body">
        <a href="/tg_account/setup" class="btn" style="background:#2563eb;display:inline-flex;align-items:center;gap:8px;text-decoration:none">
          📱 Открыть подключение Telegram аккаунта
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
        <form method="post" action="/settings/tiktok_pixel" style="margin-top:20px;padding-top:16px;border-top:1px solid var(--border)">
          <div style="font-size:.78rem;font-weight:700;color:#ff2d55;text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px">🎵 TikTok Pixel & Events API</div>
          <div class="grid-2" style="margin-bottom:12px">
            <div class="field-group"><div class="field-label">TikTok Pixel ID</div>
              <input type="text" name="tt_pixel_id" value="{db.get_setting('tt_pixel_id','')}" placeholder="CXXXXXXXXXXXXXXX"/></div>
            <div class="field-group"><div class="field-label">TikTok Access Token (Events API)</div>
              <input type="text" name="tt_access_token" placeholder="Оставь пустым — не менять"/></div>
          </div>
          <button class="btn" style="background:#ff2d55">🎵 Сохранить TikTok</button>
        </form>
        <form method="post" action="/settings/test_event_code" style="margin-top:20px;padding-top:16px;border-top:1px solid var(--border)">
          <div style="font-size:.78rem;font-weight:700;color:#a78bfa;text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px">🧪 Тест событий Facebook</div>
          <div class="grid-2" style="margin-bottom:12px">
            <div class="field-group">
              <div class="field-label">Test Event Code (оставь пустым чтобы отключить)</div>
              <input type="text" name="test_event_code" value="{test_event_code}" placeholder="TEST12345 — только для теста, потом очисти"/>
            </div>
          </div>
          <button class="btn" style="background:var(--purple,#7c3aed)">🧪 Сохранить тест-код</button>
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


@app.post("/settings/tiktok_pixel")
async def settings_tiktok_pixel(request: Request, tt_pixel_id: str = Form(""), tt_access_token: str = Form("")):
    user, err = require_auth(request, role="admin")
    if err: return err
    db.set_setting("tt_pixel_id", tt_pixel_id.strip())
    if tt_access_token.strip():
        db.set_setting("tt_access_token", tt_access_token.strip())
    return RedirectResponse("/settings?msg=TikTok+пиксель+сохранён", 303)


@app.post("/settings/test_event_code")
async def settings_test_event_code(request: Request, test_event_code: str = Form("")):
    user, err = require_auth(request, role="admin")
    if err: return err
    db.set_setting("test_event_code", test_event_code.strip())
    return RedirectResponse("/settings?msg=Тест-код+сохранён", 303)


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
          <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:6px" id="tpl-grid">
            <label style="cursor:pointer">
              <input type="radio" name="template" value="massage_job" checked style="display:none">
              <div class="tpl-card" data-tpl="massage_job" style="border:2px solid var(--orange);border-radius:8px;overflow:hidden;transition:all .15s">
                <div style="height:70px;background:linear-gradient(135deg,hsl(340,50%,93%),hsl(300,40%,92%));display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px">
                  <div style="width:40px;height:5px;background:linear-gradient(135deg,#F4209B,#DA27BD);border-radius:3px"></div>
                  <div style="width:60px;height:3px;background:#DA27BD;opacity:.4;border-radius:3px"></div>
                  <div style="display:flex;gap:4px;margin-top:4px">
                    <div style="width:50px;height:14px;background:linear-gradient(135deg,#F4209B,#C32EDB);border-radius:4px"></div>
                    <div style="width:50px;height:14px;background:#25D366;border-radius:4px"></div>
                  </div>
                </div>
                <div style="padding:6px 8px;background:var(--bg3)"><div style="font-size:.72rem;font-weight:600;color:var(--text)">Massage Job</div><div style="font-size:.65rem;color:var(--text3)">Светлый + 3 языка</div></div>
              </div>
            </label>
            <label style="cursor:pointer">
              <input type="radio" name="template" value="dark_hr" style="display:none">
              <div class="tpl-card" data-tpl="dark_hr" style="border:2px solid var(--border);border-radius:8px;overflow:hidden;transition:all .15s">
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
            <label style="cursor:pointer">
              <input type="radio" name="template" value="tiktok_spa" style="display:none">
              <div class="tpl-card" data-tpl="tiktok_spa" style="border:2px solid var(--border);border-radius:8px;overflow:hidden;transition:all .15s">
                <div style="height:70px;background:#0d0d0d;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;position:relative;overflow:hidden">
                  <div style="position:absolute;top:0;left:50%;transform:translateX(-50%);width:100px;height:100px;background:radial-gradient(ellipse,rgba(218,39,189,.35),transparent 70%);pointer-events:none"></div>
                  <div style="font-size:.6rem;font-weight:900;color:#fff;font-family:monospace;letter-spacing:.05em">$1500/ДЕНЬ</div>
                  <div style="width:80px;height:20px;background:linear-gradient(135deg,#DA27BD,#9333ea);border-radius:6px;margin-top:4px"></div>
                  <div style="font-size:.5rem;color:rgba(255,255,255,.4);margin-top:2px">📱 TikTok · Mobile-first</div>
                </div>
                <div style="padding:6px 8px;background:var(--bg3)"><div style="font-size:.72rem;font-weight:600;color:var(--text)">🎵 TikTok Spa</div><div style="font-size:.65rem;color:var(--text3)">Под TikTok трафик</div></div>
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
        _cdomain = l.get("custom_domain") or ""
        _domain_badge = f'<div style="margin-top:4px"><span style="font-family:monospace;font-size:.68rem;background:#052e16;color:#86efac;border:1px solid #166534;border-radius:4px;padding:1px 6px">🌐 {_cdomain}</span></div>' if _cdomain else ""
        rows += f"""<tr>
          <td><b>{l['name']}</b>{_domain_badge}</td>
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

    tpl_names = {"massage_job":"Massage Job USA","dark_hr":"Dark Spa","light_clean":"Light Clean","bold_cta":"Bold Purple","tiktok_spa":"🎵 TikTok Spa"}

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
    cur_domain = landing.get("custom_domain") or ""
    _app_host = app_url.replace("https://", "").replace("http://", "")
    _domain_prefix = cur_domain.split(".")[0] if "." in cur_domain else "@"
    _domain_or_placeholder = cur_domain or "твой-домен.com"

    # Тексты из content
    import json as _json
    try:
        _lcontent = _json.loads(landing.get("content","{}"))
    except:
        _lcontent = {}
    _texts = _lcontent.get("texts", {})

    def _tf(key, placeholder="", label="", textarea=False, rows=2):
        """Хелпер поля текста с placeholder из дефолтного значения"""
        val = _texts.get(key, "")
        _esc = val.replace('"', '&quot;')
        if textarea:
            return (f'<div class="field-group"><div class="field-label">{label}</div>'
                    f'<textarea name="txt_{key}" rows="{rows}" placeholder="{placeholder}" '
                    f'style="width:100%;background:var(--bg3);border:1px solid var(--border);border-radius:8px;'
                    f'padding:8px 10px;color:var(--text);font-size:.83rem;font-family:inherit;resize:vertical">'
                    f'{_esc}</textarea></div>')
        return (f'<div class="field-group"><div class="field-label">{label}</div>'
                f'<input type="text" name="txt_{key}" value="{_esc}" placeholder="{placeholder}" /></div>')

    # Строим блок текстов в зависимости от шаблона
    _texts_fields = ""
    if cur_tpl in ("dark_hr", "light_clean", "bold_cta", "tiktok_spa"):
        # Общие поля для всех шаблонов
        _hero_fields = (
            _tf("hero_title",    "Заголовок героя",         "Заголовок героя") +
            _tf("hero_subtitle", "Подзаголовок / описание", "Подзаголовок", textarea=True, rows=2)
        )
        # Преимущества (6 карточек)
        _ben_fields = "".join(
            f'<div style="border:1px solid var(--border);border-radius:8px;padding:12px;margin-bottom:8px">'
            f'<div style="font-size:.75rem;color:var(--orange);font-weight:600;margin-bottom:6px">Карточка {i+1}</div>'
            + _tf(f"ben_{i}_title", f"Преимущество {i+1}", "Заголовок")
            + _tf(f"ben_{i}_text", f"Описание преимущества {i+1}", "Описание")
            + '</div>'
            for i in range(6)
        )
        # Шаги (3 шага)
        _steps_fields = "".join(
            f'<div style="border:1px solid var(--border);border-radius:8px;padding:12px;margin-bottom:8px">'
            f'<div style="font-size:.75rem;color:var(--orange);font-weight:600;margin-bottom:6px">Шаг {i+1}</div>'
            + _tf(f"step_{i}_title", f"Шаг {i+1} заголовок", "Заголовок шага")
            + _tf(f"step_{i}_text", f"Шаг {i+1} описание", "Описание шага")
            + '</div>'
            for i in range(3)
        )
        # Отзывы (4 отзыва)
        _rev_fields = "".join(
            f'<div style="border:1px solid var(--border);border-radius:8px;padding:12px;margin-bottom:8px">'
            f'<div style="font-size:.75rem;color:var(--orange);font-weight:600;margin-bottom:6px">Отзыв {i+1}</div>'
            + _tf(f"rev_{i}_name", f"Имя, например: Анна", "Имя")
            + _tf(f"rev_{i}_from", f"Откуда, например: из Украины", "Откуда")
            + _tf(f"rev_{i}_earn", f"+$35,000", "Заработок")
            + _tf(f"rev_{i}_text", f"Текст отзыва", "Отзыв", textarea=True, rows=2)
            + '</div>'
            for i in range(4)
        )
        # FAQ (5 вопросов)
        _faq_fields = "".join(
            f'<div style="border:1px solid var(--border);border-radius:8px;padding:12px;margin-bottom:8px">'
            f'<div style="font-size:.75rem;color:var(--orange);font-weight:600;margin-bottom:6px">Вопрос {i+1}</div>'
            + _tf(f"faq_{i}_q", f"Вопрос {i+1}", "Вопрос")
            + _tf(f"faq_{i}_a", f"Ответ на вопрос {i+1}", "Ответ", textarea=True, rows=2)
            + '</div>'
            for i in range(5)
        )
        # CTA, badge, кнопки и футер
        _cta_fields = (
            _tf("cta_title",   "Заголовок CTA секции",  "Заголовок CTA") +
            _tf("cta_subtitle","Подзаголовок CTA",       "Подзаголовок CTA") +
            _tf("badge_text",  "Текст badge (например: Відкритий набір)", "Badge текст") +
            ('<div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--border)">'
             '<div style="font-size:.75rem;font-weight:600;color:var(--orange);margin-bottom:8px">Кнопки навигации</div>' if cur_tpl == "light_clean" else "") +
            (_tf("nav_btn",   "Відкликнутися →",  "Кнопка в шапке (nav)") +
             _tf("hero_btn",  "Дізнатися більше →","Кнопка в герое") +
             '</div>' if cur_tpl == "light_clean" else "") +
            ('<div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--border)">'
             '<div style="font-size:.75rem;font-weight:600;color:var(--orange);margin-bottom:8px">Футер</div>'
             + _tf("footer_text", f"© {__import__('datetime').datetime.now().year} {landing.get('name','')}. Усі права захищені.", "Текст футера (год, компания, права)")
             + '</div>')
        )
        # Цифры доверия (только для tiktok_spa и bold_cta)
        _trust_fields = ""
        if cur_tpl in ("tiktok_spa", "bold_cta"):
            _trust_fields = (
                '<div style="font-size:.78rem;font-weight:600;color:var(--text2);margin:8px 0 4px">Цифры доверия</div>' +
                _tf("trust_0_val", "500+",         "Цифра 1") +
                _tf("trust_0_lbl", "девушек работают", "Подпись 1") +
                _tf("trust_1_val", "$1500",        "Цифра 2") +
                _tf("trust_1_lbl", "средний доход в день", "Подпись 2") +
                _tf("trust_2_val", "50+",          "Цифра 3") +
                _tf("trust_2_lbl", "городов по всей США",  "Подпись 3")
            )

        def _tab_btn(tab_id, label, active=False):
            _a = "background:var(--orange);color:#fff" if active else "background:var(--bg3);color:var(--text3)"
            return f'<button type="button" onclick="showTab(\'{tab_id}\')" id="tab-btn-{tab_id}" style="{_a};border:none;padding:6px 14px;border-radius:7px;font-size:.78rem;font-weight:600;cursor:pointer;font-family:inherit">{label}</button>'

        def _tab_div(tab_id, content, active=False):
            _d = "block" if active else "none"
            return f'<div id="tab-{tab_id}" style="display:{_d};margin-top:14px">{content}</div>'

        _has_steps = cur_tpl == "tiktok_spa"
        _step_btn  = _tab_btn("steps", "👣 Шаги") if _has_steps else ""
        _step_div  = _tab_div("steps", _steps_fields) if _has_steps else ""
        _texts_fields = f"""
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:4px">
          {_tab_btn("hero",  "🎯 Герой",        True)}
          {_tab_btn("ben",   "✨ Преимущества")}
          {_step_btn}
          {_tab_btn("rev",   "⭐ Отзывы")}
          {_tab_btn("faq",   "❓ FAQ")}
          {_tab_btn("cta",   "🔔 CTA")}
          {''+_tab_btn("trust","🔢 Цифры") if _trust_fields else ''}
        </div>
        {_tab_div("hero",  _hero_fields,  True)}
        {_tab_div("ben",   _ben_fields)}
        {_step_div}
        {_tab_div("rev",   _rev_fields)}
        {_tab_div("faq",   _faq_fields)}
        {_tab_div("cta",   _cta_fields)}
        {_tab_div("trust", _trust_fields) if _trust_fields else ''}
        <script>
        function showTab(id) {{
          ['hero','ben','steps','rev','faq','cta','trust'].forEach(function(t) {{
            var d=document.getElementById('tab-'+t);
            var b=document.getElementById('tab-btn-'+t);
            if(d) d.style.display=(t===id)?'block':'none';
            if(b) b.style.cssText=b.style.cssText.replace(/(background:[^;]+)/,t===id?'background:var(--orange)':'background:var(--bg3)').replace(/(color:[^;]+)/,t===id?'color:#fff':'color:var(--text3)');
          }});
        }}
        </script>"""

    texts_block = ""
    if _texts_fields:
        texts_block = f"""
    <div class="section" style="margin-bottom:18px">
      <div class="section-head"><h3>✏️ Тексты лендинга</h3>
        <small style="color:var(--text3);font-size:.72rem">Оставь поле пустым — элемент скроется на лендинге</small>
      </div>
      <div class="section-body">
        <form method="post" action="/landings/save_texts">
          <input type="hidden" name="landing_id" value="{id}"/>
          {_texts_fields}
          <div style="margin-top:16px;display:flex;gap:8px">
            <button class="btn-orange">💾 Сохранить тексты</button>
            <a href="{public_url}" target="_blank" class="btn-gray btn-sm" style="display:inline-flex;align-items:center">👁 Предпросмотр</a>
          </div>
        </form>
      </div>
    </div>"""

    # Блок кастомного домена
    domain_status = ""
    if cur_domain:
        domain_status = f'<div style="display:inline-flex;align-items:center;gap:6px;background:#052e16;border:1px solid #166534;border-radius:6px;padding:4px 10px;font-size:.78rem;color:#86efac;margin-top:8px">✅ Активен: <b>{cur_domain}</b></div>'
    _clear_btn = '<button type="submit" class="btn-gray" onclick="this.form.elements.custom_domain.value=\'\'">Очистить</button>' if cur_domain else ""
    domain_block = (
        '<div class="section">'
        '<div class="section-head"><h3>🌐 Кастомный домен</h3></div>'
        '<div class="section-body">'
        f'<form method="post" action="/landings/set_domain" style="display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap">'
        f'<input type="hidden" name="landing_id" value="{id}"/>'
        '<div class="field-group" style="max-width:320px">'
        '<div class="field-label">Домен (без https:// и www.)</div>'
        f'<input type="text" name="custom_domain" value="{cur_domain}" placeholder="job.example.com" style="font-family:monospace"/>'
        '</div>'
        '<div style="display:flex;align-items:flex-end;gap:6px">'
        '<button class="btn">Сохранить</button>'
        f'{_clear_btn}'
        '</div></form>'
        f'{domain_status}'
        '<div style="margin-top:16px;padding:14px 16px;background:var(--bg3);border-radius:10px;border:1px solid var(--border)">'
        '<div style="font-weight:600;font-size:.85rem;margin-bottom:10px">📋 Инструкция по подключению домена</div>'
        '<div style="font-size:.82rem;color:var(--text2);line-height:1.8">'
        '<b>Шаг 1.</b> Зайди в настройки DNS своего домена (Cloudflare, Namecheap, GoDaddy и др.)<br>'
        '<b>Шаг 2.</b> Добавь <b>CNAME запись:</b><br>'
        '<div style="margin:8px 0 8px 16px;font-family:monospace;background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:8px 12px;font-size:.8rem">'
        f'Имя: <b>{_domain_prefix}</b> &nbsp;→&nbsp; Значение: <b>{_app_host}</b>'
        '</div>'
        f'<b>Шаг 3.</b> В Railway → твой сервис <b>web</b> → Settings → <b>Custom Domain</b> → добавь <b>{_domain_or_placeholder}</b><br>'
        '<b>Шаг 4.</b> Подожди 5-15 минут пока DNS обновится ✅'
        '</div>'
        '<div style="margin-top:10px;padding:8px 12px;background:#1c1a00;border:1px solid #713f12;border-radius:6px;font-size:.78rem;color:#fde047">'
        '⚠️ Важно: кастомный домен нужно добавить в Railway иначе он не будет работать даже при правильном DNS'
        '</div></div></div></div>'
    )

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
    {texts_block}
    {domain_block}
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


@app.post("/landings/set_domain")
async def landings_set_domain(request: Request, landing_id: int = Form(...), custom_domain: str = Form("")):
    """Сохранить или очистить кастомный домен лендинга"""
    user, err = require_auth(request)
    if err: return err
    domain = custom_domain.strip().lower()
    # Убираем протокол если вставили полный URL
    for prefix in ("https://", "http://"):
        if domain.startswith(prefix):
            domain = domain[len(prefix):]
    # Убираем слэш в конце и path
    domain = domain.split("/")[0].strip()
    if domain.startswith("www."):
        domain = domain[4:]
    db.set_landing_custom_domain(landing_id, domain)
    msg = f"Домен {'сохранён: ' + domain if domain else 'очищен'}"
    return RedirectResponse(f"/landings/edit?id={landing_id}&msg={msg}", 303)


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


@app.post("/landings/save_texts")
async def landings_save_texts(request: Request):
    """Сохранить редактируемые тексты лендинга"""
    user, err = require_auth(request)
    if err: return err
    import json as _json
    form = await request.form()
    landing_id = int(form.get("landing_id", 0))
    if not landing_id:
        return RedirectResponse("/landings_staff", 303)
    landing = db.get_landing(landing_id)
    if not landing:
        return RedirectResponse("/landings_staff", 303)
    try:
        lcontent = _json.loads(landing.get("content","{}"))
    except:
        lcontent = {}
    # Собираем все поля texts из формы
    texts = {}
    for key, val in form.items():
        if key.startswith("txt_"):
            field = key[4:]  # убираем префикс txt_
            texts[field] = val.strip()
    lcontent["texts"] = texts
    db.update_landing_content(landing_id, _json.dumps(lcontent, ensure_ascii=False))
    return RedirectResponse(f"/landings/edit?id={landing_id}&msg=Тексты+сохранены", 303)


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
    app_url       = db.get_setting("app_url", "").rstrip("/")

    # fbp из cookie
    cookie_fbp = request.cookies.get("_fbp", "")

    # Ищем как Campaign slug
    campaign = db.get_campaign_by_slug(slug)
    if campaign:
        channels = db.get_campaign_channels(campaign["id"])
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
                tt_pixel = db.get_setting("tiktok_pixel_id", "") or ""
                return HTMLResponse(_render_client_landing(landing, chan_contacts, pixel_id=pixel_id, tt_pixel=tt_pixel, db=db))

        tt_pixel = db.get_setting("tiktok_pixel_id", "") or ""
        return HTMLResponse(_render_campaign_landing(campaign, btns, pixel_id, fbclid, tt_pixel))

    # Staff Landing slug
    landing = db.get_landing_by_slug(slug)
    if not landing: return HTMLResponse("<h2>Not found</h2>", 404)

    # Строим /go-staff ссылки — с UTM трекингом
    raw_contacts = db.get_landing_contacts(landing["id"])
    utm_params = dict(
        fbclid=fbclid, fbp=cookie_fbp,
        utm_source=utm_source or "facebook",
        utm_medium=utm_medium or "paid",
        utm_campaign=utm_campaign or "",
        utm_content=utm_content or "",
        utm_term=utm_term or "",
        landing_slug=slug,
    )
    tracked_contacts = []
    for c in raw_contacts:
        if c.get("url"):
            import urllib.parse as _up
            ref_id = __import__("secrets").token_urlsafe(10)
            # Определяем тип контакта
            c_type = c.get("type", "")
            if not c_type:
                if "wa.me" in c["url"] or "whatsapp" in c["url"].lower():
                    c_type = "whatsapp"
                elif "t.me" in c["url"] or "telegram" in c["url"].lower():
                    c_type = "telegram"
            # Сохраняем клик
            db.save_staff_click(ref_id, c["url"], c_type, slug, **{k:v for k,v in utm_params.items() if k!='landing_slug'})
            go_url = f"{app_url}/go-staff?ref={ref_id}"
            tracked_contacts.append({**c, "url": go_url, "type": c_type})
        else:
            tracked_contacts.append(c)

    return HTMLResponse(_render_staff_landing(landing, tracked_contacts, pixel_id=pixel_staff, db=db))


@app.get("/go-staff")
async def go_staff_redirect(request: Request, ref: str = ""):
    """Редирект с HR лендинга — сохраняет UTM и добавляет ref код в WA/TG ссылку"""
    if not ref:
        return HTMLResponse("<h2>Invalid link</h2>", 400)

    click = db.get_staff_click(ref)
    if not click:
        return HTMLResponse("<h2>Link expired</h2>", 404)

    target_url = click.get("target_url", "")
    target_type = click.get("target_type", "wa")

    # Добавляем ref код только для TG (через ?start=), для WA - редиректим напрямую
    destination = target_url
    if target_type == "telegram" or "t.me" in target_url:
        # t.me/username → t.me/username?start=ref_XXX
        sep = "&" if "?" in target_url else "?"
        destination = f"{target_url}{sep}start=ref_{ref}"
    # Для WA — просто редиректим без ref в тексте (трекинг по времени в webhook)

    log.info(f"[/go-staff] ref={ref} type={target_type} utm={click.get('utm_campaign')} fbclid={'✓' if click.get('fbclid') else '—'}")

    return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <meta http-equiv="refresh" content="0;url={destination}">
    <script>
      if (!document.cookie.includes('_fbp')) {{
        var fbp = 'fb.1.' + Date.now() + '.' + Math.random().toString(36).substr(2,9);
        document.cookie = '_fbp=' + fbp + ';max-age=7776000;path=/;SameSite=Lax';
      }}
      setTimeout(function(){{ window.location.href = '{destination}'; }}, 80);
    </script>
    </head><body style="background:#060a0f;color:#e8f0f8;display:flex;align-items:center;justify-content:center;min-height:100vh;font-family:system-ui">
    <div style="text-align:center"><div style="font-size:2rem;margin-bottom:12px">📡</div>
    <div>Перенаправляем...</div></div></body></html>""")


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
    stats = db.get_stats()
    stats["wa_status"] = db.get_setting("wa_status", "disconnected")
    stats["tg_status"] = db.get_setting("tg_account_status", "disconnected")
    return JSONResponse(stats)


@app.get("/api/wa_chat_panel", response_class=HTMLResponse)
async def api_wa_chat_panel(request: Request, conv_id: int = 0, status_filter: str = "open"):
    """SPA: возвращает только HTML правой панели WA чата"""
    user, err = require_auth(request)
    if err: return HTMLResponse("<div style='padding:20px;color:var(--red)'>Нет доступа</div>", 401)
    if not conv_id:
        return HTMLResponse('<div class="no-conv"><div style="font-size:2.5rem">💚</div><div>Выбери диалог WhatsApp</div></div>')
    active_conv = db.get_wa_conversation(conv_id)
    if not active_conv:
        return HTMLResponse('<div style="padding:20px;color:var(--text3)">Диалог не найден</div>')
    db.mark_wa_read(conv_id)
    msgs = db.get_wa_messages(conv_id)
    wa_status = db.get_setting("wa_status", "disconnected")
    messages_html = ""
    for m in msgs:
        t = m["created_at"][11:16]
        if m.get("media_url") and (m.get("media_type") or "").startswith("image/"):
            content_html = f'<img src="{m["media_url"]}" style="max-width:220px;max-height:220px;border-radius:8px;display:block;cursor:pointer" onclick="window.open(this.src)" />'
            if m.get("content") and m["content"] not in ("[фото]","[медиафайл]"):
                content_html += f'<div style="margin-top:4px">{(m["content"] or "").replace("<","&lt;")}</div>'
        elif m.get("media_url"):
            content_html = f'<a href="{m["media_url"]}" target="_blank" style="color:#60a5fa">📎 Открыть файл</a>'
        else:
            content_html = (m.get("content") or "").replace("<", "&lt;")
        wa_sender_label = ""
        if m.get("sender_name") and m["sender_type"] == "manager":
            wa_sender_label = f'<div style="font-size:.68rem;color:var(--orange);margin-bottom:2px;text-align:right;opacity:.8">{m["sender_name"]}</div>'
        messages_html += f'<div class="msg {m["sender_type"]}" data-id="{m["id"]}">{wa_sender_label}<div class="msg-bubble">{content_html}</div><div class="msg-time">{t}</div></div>'
    # Карточка
    wa_staff = db.get_staff_by_wa_conv(conv_id)
    if wa_staff:
        wa_card_link = f'<a href="/staff?edit={wa_staff["id"]}" style="display:inline-flex;align-items:center;gap:4px;background:#052e16;color:#86efac;border:1px solid #166534;border-radius:6px;padding:2px 8px;font-size:.73rem;text-decoration:none">✅ В базе · {wa_staff.get("name","") or "Карточка"} →</a>'
    else:
        wa_card_link = f'<a href="/staff/create_from_wa?conv_id={conv_id}" style="display:inline-flex;align-items:center;gap:4px;background:var(--bg3);color:var(--text3);border:1px solid var(--border);border-radius:6px;padding:2px 8px;font-size:.73rem;text-decoration:none">+ Создать карточку</a>'
    # UTM теги
    _is_fb = bool(active_conv.get("fbclid") or active_conv.get("utm_source") in ("facebook","fb"))
    utm_parts = []
    if _is_fb:
        utm_parts.append('<span style="background:#1e3a5f;color:#60a5fa;padding:2px 8px;border-radius:5px;font-size:.72rem">🔵 Facebook</span>')
    elif active_conv.get("utm_source"):
        utm_parts.append(f'<span style="background:var(--border);color:var(--text2);padding:2px 8px;border-radius:5px;font-size:.72rem">{active_conv["utm_source"]}</span>')
    if active_conv.get("utm_campaign"): utm_parts.append(f'<span class="utm-tag">🎯 {active_conv["utm_campaign"][:25]}</span>')
    if active_conv.get("utm_content"):  utm_parts.append(f'<span class="utm-tag" style="background:#1a2a1a;color:#86efac">📌 {active_conv["utm_content"][:20]}</span>')
    if active_conv.get("utm_term"):     utm_parts.append(f'<span class="utm-tag" style="background:#1a1a2a;color:#a5b4fc">📂 {active_conv["utm_term"][:20]}</span>')
    if active_conv.get("fbclid"):       utm_parts.append('<span class="utm-tag badge-green">fbclid ✓</span>')
    wa_utm_tags = '<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:5px">' + "".join(utm_parts) + '</div>' if utm_parts else ""
    # Теги
    all_tags_wa      = db.get_all_tags()
    active_wa_ctags  = db.get_conv_tags("wa", conv_id)
    active_wa_tag_ids = {tg["id"] for tg in active_wa_ctags}
    wa_tags_html = _render_conv_tags_picker(active_wa_ctags, all_tags_wa, active_wa_tag_ids, "wa", conv_id)
    # Кнопки
    fb_sent = active_conv.get("fb_event_sent")
    fb_btn = '<span class="badge-green">✅ Lead отправлен</span>' if fb_sent else \
             f'<form method="post" action="/wa/send_lead" style="display:inline"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn btn-sm" style="font-size:.73rem;background:#1e3a5f;border:1px solid #3b5998;color:#93c5fd">📤 Lead → FB</button></form>'
    status_color = "#34d399" if active_conv["status"] == "open" else "#ef4444"
    close_btn = f'<form method="post" action="/wa/close"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-gray btn-sm">✓ Закрыть</button></form>' if active_conv["status"] == "open" else \
                f'<form method="post" action="/wa/reopen"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-green btn-sm">↺ Открыть</button></form>'
    delete_wa_btn = f'<button class="btn-gray btn-sm" style="color:var(--red);border-color:#7f1d1d" onclick="deleteWaConv({conv_id})">🗑</button>' if user and user.get("role") == "admin" else ""
    # Аватар
    wa_photo = active_conv.get("photo_url","")
    if wa_photo:
        wa_avatar = (f'<div class="staff-photo-wrap">'
                     f'<img src="{wa_photo}" style="width:40px;height:40px;border-radius:50%;object-fit:cover;border:2px solid #25d366;display:block"/>'
                     f'<div class="staff-photo-popup"><img src="{wa_photo}"/>'
                     f'<div class="staff-photo-popup-btns"><a href="{wa_photo}" download>⬇ Скачать</a></div></div></div>')
    else:
        wa_avatar = '<div class="avatar" style="background:#052e16;color:#86efac">W</div>'

    return HTMLResponse(f"""
    <div class="chat-header">
      <div style="display:flex;align-items:flex-start;gap:12px;flex:1">
        {wa_avatar}
        <div style="flex:1">
          <div style="font-weight:700;color:#fff">{active_conv['visitor_name']} <span style="color:{status_color};font-size:.74rem">●</span></div>
          <div style="font-size:.79rem;color:var(--text3)">+{active_conv['wa_number']} · {wa_card_link}</div>
          <div style="margin-top:6px">{fb_btn}</div>
          {wa_utm_tags}
          {wa_tags_html}
        </div>
      </div>
      <div style="display:flex;gap:6px;flex-shrink:0">
        <button class="btn-gray btn-sm" title="Обновить профиль" onclick="fetchWaProfile({conv_id})" style="font-size:.8rem">🔄</button>
        {close_btn} {delete_wa_btn}
      </div>
    </div>
    <div class="chat-messages" id="wa-msgs">{messages_html}</div>
    <div id="wa-send-error" style="display:none;padding:8px 18px;background:#2d0a0a;border-top:1px solid #7f1d1d;font-size:.8rem;color:#fca5a5;align-items:center;justify-content:space-between;gap:8px">
      <span id="wa-send-error-text"></span>
      <button onclick="document.getElementById('wa-send-error').style.display='none'" style="background:none;border:none;color:#fca5a5;cursor:pointer;font-size:1rem">✕</button>
    </div>
    <div class="chat-input">
      <div id="wa-disconnected-banner" style="display:{'none' if wa_status == 'ready' else 'flex'};align-items:center;justify-content:space-between;padding:8px 12px;background:#1c1a00;border:1px solid #713f12;border-radius:8px;margin-bottom:8px;font-size:.8rem;color:#fde047;gap:8px">
        <span>⚠️ WhatsApp не подключён — сообщения не будут доставлены</span>
        <a href="/wa/setup" style="color:#fde047;font-weight:600;white-space:nowrap;text-decoration:underline">Подключить →</a>
      </div>
      <div class="chat-input-row">
        <input type="file" id="wa-file-input" accept="image/*" style="display:none" onchange="sendWaFile(this)"/>
        <button class="send-btn-green" style="background:#374151;padding:10px 13px;font-size:1.1rem" onclick="document.getElementById('wa-file-input').click()" title="Отправить фото">📎</button>
        <textarea id="wa-reply" placeholder="Написать в WhatsApp… (Enter — отправить)" rows="1" onkeydown="handleWaKey(event)"></textarea>
        <button class="send-btn-green" onclick="sendWaMsg()">Отправить</button>
      </div>
    </div>
    <script>
    window.ACTIVE_CONV_ID = {conv_id};
    const msgsEl = document.getElementById('wa-msgs');
    if(msgsEl) msgsEl.scrollTop = msgsEl.scrollHeight;
    </script>""")


@app.get("/api/wa_convs")
async def api_wa_convs(request: Request, status: str = "open"):
    """Список WA диалогов для авто-обновления"""
    user = check_session(request)
    if not user: return JSONResponse({"error": "unauthorized"}, 401)
    status_arg = status if status != "all" else None
    convs = db.get_wa_conversations(status=status_arg)
    wa_in_staff = db.get_wa_conv_ids_in_staff()
    wa_tags_map = db.get_all_conv_tags_map("wa")
    return JSONResponse({"convs": [
        {
            "id": c["id"],
            "visitor_name": c["visitor_name"],
            "wa_number": c["wa_number"],
            "last_message": c.get("last_message") or "",
            "last_message_at": (c.get("last_message_at") or c["created_at"])[:16].replace("T"," "),
            "unread_count": c.get("unread_count", 0),
            "status": c.get("status", "open"),
            "utm_source":   c.get("utm_source") or "",
            "utm_campaign": c.get("utm_campaign") or "",
            "utm_content":  c.get("utm_content") or "",
            "utm_term":     c.get("utm_term") or "",
            "fbclid":       bool(c.get("fbclid")),
            "in_staff":     bool(wa_in_staff.get(c["id"])),
            "tags":         wa_tags_map.get(c["id"], []),
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


# ── Хелпер вызова TG аккаунт сервиса ─────────────────────────────────────────
async def tg_api(method: str, path: str, **kwargs) -> dict:
    if not TG_SVC_URL:
        return {"error": "TG_SERVICE_URL not configured"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await getattr(client, method)(
                f"{TG_SVC_URL}{path}",
                headers={"X-Api-Secret": TG_SVC_SECRET},
                **kwargs
            )
            return resp.json()
    except Exception as e:
        log.error(f"TG API error: {e}")
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

            raw_text    = data.get("body") or data.get("text") or ""
            media_url   = data.get("media_url")
            media_type  = data.get("media_type", "")
            media_b64   = data.get("media_base64")
            has_media   = data.get("hasMedia") or media_url or media_b64

            # Загружаем base64 медиа на Cloudinary если пришло от WA сервиса
            if media_b64 and not media_url:
                try:
                    import cloudinary
                    import cloudinary.uploader
                    import base64 as _b64
                    cld_url  = db.get_setting("cloudinary_url") or os.getenv("CLOUDINARY_URL", "")
                    if cld_url:
                        cloudinary.config(cloudinary_url=cld_url)
                        mime = media_type or "image/jpeg"
                        data_uri = f"data:{mime};base64,{media_b64}"
                        result = cloudinary.uploader.upload(
                            data_uri,
                            folder="wa_media",
                            resource_type="auto",
                        )
                        media_url = result.get("secure_url")
                        log.info(f"[WA webhook] media uploaded to Cloudinary: {media_url}")
                    else:
                        # Cloudinary не настроен — сохраняем как data URI (только для картинок)
                        if (media_type or "").startswith("image/"):
                            media_url = f"data:{media_type};base64,{media_b64}"
                except Exception as e:
                    log.error(f"[WA webhook] Cloudinary upload error: {e}")

            if not raw_text and has_media:
                raw_text = "[фото]" if (media_type or "").startswith("image/") else "[файл]"
            text = (raw_text or "").strip() or "[сообщение]"

            if not wa_chat_id:
                log.warning(f"[WA webhook] no wa_chat_id in data: {data}")
                return JSONResponse({"ok": True})

            conv = db.get_or_create_wa_conversation(wa_chat_id, wa_number, sender_name)
            is_new_conv = not conv.get("utm_source") and not conv.get("fbclid")

            # ── Трекинг UTM: сначала ref: код (TG-стиль), потом временное окно ──
            import re as _re
            ref_match = _re.search(r'\bref:([A-Za-z0-9_\-]{8,20})\b', text)
            if ref_match:
                # Явный ref код в тексте (на случай если пользователь скопировал)
                ref_id = ref_match.group(1)
                click_data = db.get_staff_click(ref_id)
                if click_data and not click_data.get("used"):
                    db.apply_utm_to_wa_conv(conv["id"],
                        fbclid=click_data.get("fbclid"), fbp=click_data.get("fbp"),
                        utm_source=click_data.get("utm_source"),
                        utm_medium=click_data.get("utm_medium"),
                        utm_campaign=click_data.get("utm_campaign"),
                        utm_content=click_data.get("utm_content"),
                        utm_term=click_data.get("utm_term"))
                    db.mark_staff_click_used(ref_id)
                    conv = db.get_wa_conversation(conv["id"]) or conv
                    log.info(f"[WA webhook] UTM by ref:{ref_id} utm={click_data.get('utm_campaign')}")
            elif is_new_conv:
                # Трекинг по временному окну — ищем последний клик за 30 минут
                click_data = db.get_staff_click_recent_any(minutes=30)
                if click_data:
                    db.apply_utm_to_wa_conv(conv["id"],
                        fbclid=click_data.get("fbclid"), fbp=click_data.get("fbp"),
                        utm_source=click_data.get("utm_source"),
                        utm_medium=click_data.get("utm_medium"),
                        utm_campaign=click_data.get("utm_campaign"),
                        utm_content=click_data.get("utm_content"),
                        utm_term=click_data.get("utm_term"))
                    db.mark_staff_click_used(click_data["ref_id"])
                    conv = db.get_wa_conversation(conv["id"]) or conv
                    log.info(f"[WA webhook] UTM by time-window utm={click_data.get('utm_campaign')} fbclid={'✓' if click_data.get('fbclid') else '—'}")

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
                wa_sender_label = ""
                if m["sender_type"] == "manager" and m.get("sender_name"):
                    wa_sender_label = f'<div style="font-size:.68rem;color:var(--orange);margin-bottom:2px;text-align:right;opacity:.8">{m["sender_name"]}</div>'
                messages_html += f"""<div class="msg {m['sender_type']}" data-id="{m['id']}">
                  {wa_sender_label}<div class="msg-bubble">{content_html}</div>
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
            delete_wa_btn = f'<button class="btn-gray btn-sm" style="color:var(--red);border-color:#7f1d1d" onclick="deleteWaConv({conv_id})">🗑</button>' if user and user.get("role") == "admin" else ""

            # Карточка сотрудника для WA
            wa_staff = db.get_staff_by_wa_conv(conv_id)
            if wa_staff:
                wa_card_link = f'<a href="/staff?edit={wa_staff["id"]}" style="display:inline-flex;align-items:center;gap:4px;background:#052e16;color:#86efac;border:1px solid #166534;border-radius:6px;padding:2px 8px;font-size:.73rem;text-decoration:none">✅ В базе · {wa_staff.get("name","") or "Карточка"} →</a>'
            else:
                wa_card_link = f'<a href="/staff/create_from_wa?conv_id={conv_id}" style="display:inline-flex;align-items:center;gap:4px;background:var(--bg3);color:var(--text3);border:1px solid var(--border);border-radius:6px;padding:2px 8px;font-size:.73rem;text-decoration:none">+ Создать карточку</a>'
            wa_utm_tags = ""
            _is_wa_fb = bool(active_conv.get("fbclid") or active_conv.get("utm_source") in ("facebook", "fb"))
            utm_parts = []
            if _is_wa_fb:
                utm_parts.append('<span style="background:#1e3a5f;color:#60a5fa;padding:2px 8px;border-radius:5px;font-size:.72rem">🔵 Facebook</span>')
            elif active_conv.get("utm_source"):
                utm_parts.append(f'<span style="background:var(--border);color:var(--text2);padding:2px 8px;border-radius:5px;font-size:.72rem">{active_conv["utm_source"]}</span>')
            if active_conv.get("utm_campaign"):
                utm_parts.append(f'<span class="utm-tag" title="Кампания">🎯 {active_conv["utm_campaign"][:25]}</span>')
            if active_conv.get("utm_content"):
                utm_parts.append(f'<span class="utm-tag" style="background:#1a2a1a;color:#86efac" title="Объявление">📌 {active_conv["utm_content"][:20]}</span>')
            if active_conv.get("utm_term"):
                utm_parts.append(f'<span class="utm-tag" style="background:#1a1a2a;color:#a5b4fc" title="Адсет">📂 {active_conv["utm_term"][:20]}</span>')
            if active_conv.get("fbclid"):
                utm_parts.append('<span class="utm-tag badge-green">fbclid ✓</span>')
            if utm_parts:
                wa_utm_tags = '<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:5px">' + "".join(utm_parts) + '</div>'
            # Теги WA чата
            all_tags_wa      = db.get_all_tags()
            active_wa_ctags  = db.get_conv_tags("wa", conv_id)
            active_wa_tag_ids = {tg["id"] for tg in active_wa_ctags}
            wa_tags_html = _render_conv_tags_picker(active_wa_ctags, all_tags_wa, active_wa_tag_ids, "wa", conv_id)

            header_html = f"""<div class="chat-header">
              <div style="display:flex;align-items:flex-start;gap:12px;flex:1">
                {wa_avatar}
                <div style="flex:1">
                  <div style="font-weight:700;color:#fff">{active_conv['visitor_name']} <span style="color:{status_color};font-size:.74rem">●</span></div>
                  <div style="font-size:.79rem;color:var(--text3)">+{active_conv['wa_number']} · {wa_card_link}</div>
                  <div style="margin-top:6px">{fb_btn}</div>
                  {wa_utm_tags}
                  {wa_tags_html}
                </div>
              </div>
              <div style="display:flex;gap:6px;flex-shrink:0">
                <button class="btn-gray btn-sm" title="Обновить профиль" onclick="fetchWaProfile({conv_id})" style="font-size:.8rem">🔄</button>
                {close_btn} {delete_wa_btn}
              </div>
            </div>"""
    conv_items = ""
    wa_in_staff  = db.get_wa_conv_ids_in_staff()
    wa_tags_map  = db.get_all_conv_tags_map("wa")
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
        _wa_is_fb = bool(c.get("fbclid") or c.get("utm_source") in ("facebook", "fb"))
        wa_utm_parts = []
        if _wa_is_fb:  # Задача 14: UTM только если не органика
            if c.get("utm_campaign"):  wa_utm_parts.append(f'<span class="utm-tag" title="Кампания">🎯 {c["utm_campaign"][:30]}</span>')
            if c.get("utm_content"):   wa_utm_parts.append(f'<span class="utm-tag" style="background:#1a2a1a;color:#86efac" title="Объявление">📌 {c["utm_content"][:20]}</span>')
            if c.get("utm_term"):      wa_utm_parts.append(f'<span class="utm-tag" style="background:#1a1a2a;color:#a5b4fc" title="Адсет">📂 {c["utm_term"][:20]}</span>')
        utm_line = '<div class="conv-meta" style="display:flex;flex-wrap:wrap;gap:3px;margin-top:2px">' + "".join(wa_utm_parts) + '</div>' if wa_utm_parts else ""
        # Задача 5: отметка "уже в базе"
        wa_staff_info = wa_in_staff.get(c["id"])
        wa_in_base = f'<span style="background:#052e16;color:#86efac;border:1px solid #166534;border-radius:5px;font-size:.65rem;padding:1px 6px;margin-left:4px;white-space:nowrap">✅ в базе</span>' if wa_staff_info else ""
        wa_display_name = c.get('username') if (c.get('visitor_name','') or '').isdigit() and c.get('username') else c.get('visitor_name') or c.get('username') or c.get('tg_chat_id','')
        # Теги
        wctags = wa_tags_map.get(c["id"], [])
        wa_tags_line = ""
        if wctags:
            wt_html = "".join(f'<span class="conv-tag" style="background:{tg["color"]}22;color:{tg["color"]};border-color:{tg["color"]}55">{tg["name"]}</span>' for tg in wctags)
            wa_tags_line = f'<div class="tags-row">{wt_html}</div>'
        conv_items += f"""<a href="/wa/chat?conv_id={c['id']}&status_filter={status_filter}"><div class="{cls}" data-conv-id="{c['id']}">
          <div class="conv-name"><span>{dot} {wa_display_name}</span>{ucount}{wa_in_base}</div>
          <div class="conv-preview">{c.get('last_message') or 'Нет сообщений'}</div>
          <div class="conv-time" style="display:flex;align-items:center;justify-content:space-between">💚 +{c['wa_number'][:10]} · {t[-5:]} {src_badge}</div>
          {utm_line}{wa_tags_line}</div></a>"""
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
    <div id="wa-send-error" style="display:none;padding:8px 18px;background:#2d0a0a;border-top:1px solid #7f1d1d;font-size:.8rem;color:#fca5a5;align-items:center;justify-content:space-between;gap:8px">
      <span id="wa-send-error-text"></span>
      <button onclick="document.getElementById('wa-send-error').style.display='none'" style="background:none;border:none;color:#fca5a5;cursor:pointer;font-size:1rem;line-height:1">✕</button>
    </div>
    <div class="chat-input">
      <div id="wa-disconnected-banner" style="display:{'none' if wa_status == 'ready' else 'flex'};align-items:center;justify-content:space-between;padding:8px 12px;background:#1c1a00;border:1px solid #713f12;border-radius:8px;margin-bottom:8px;font-size:.8rem;color:#fde047;gap:8px">
        <span>⚠️ WhatsApp не подключён — сообщения не будут доставлены</span>
        <a href="/wa/setup" style="color:#fde047;font-weight:600;white-space:nowrap;text-decoration:underline">Подключить →</a>
      </div>
      <div class="chat-input-row">
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
      try{{
        const r=await fetch('/wa/send',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},
          body:'conv_id={conv_id}&text='+encodeURIComponent(text)}});
        const d=await r.json();
        if(d.ok) loadNewWaMsgs(); else showWaError(d.error||'');
      }}catch(e){{showWaError(e.message);}}
    }}

    function showWaError(msg){{
      var errDiv=document.getElementById('wa-send-error');
      var errTxt=document.getElementById('wa-send-error-text');
      if(!errDiv||!errTxt)return;
      var isDisconn=msg&&(msg.toLowerCase().includes('not connect')||msg.toLowerCase().includes('503'));
      if(isDisconn){{
        errTxt.innerHTML='⚠️ WhatsApp не подключён. <a href="/wa/setup" style="color:#fca5a5;text-decoration:underline;font-weight:600">Подключить →</a>';
        var banner=document.getElementById('wa-disconnected-banner');
        if(banner) banner.style.display='flex';
      }}else{{
        errTxt.textContent='Ошибка: '+(msg||'неизвестная ошибка');
      }}
      errDiv.style.display='flex';
      setTimeout(function(){{errDiv.style.display='none';}},6000);
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
        if(data.ok) loadNewWaMsgs(); else showWaError(data.error||'');
      }}catch(e){{showWaError(e.message);}}
      btn.textContent='📎'; btn.disabled=false;
      input.value='';
    }}
    function handleWaKey(e){{if(e.key==='Enter'&&!e.shiftKey){{e.preventDefault();sendWaMsg();}}}}

    // Polling статуса WA — обновляем баннер автоматически
    setInterval(async function(){{
      try{{
        var r=await fetch('/api/stats');if(!r.ok)return;
        var d=await r.json();
        var banner=document.getElementById('wa-disconnected-banner');
        if(banner) banner.style.display=(d.wa_status==='ready')?'none':'flex';
      }}catch(e){{}}
    }},5000);

    // Обновление сообщений в открытом чате
    {"setInterval(loadNewWaMsgs, 3000);" if active_conv else ""}

    var _waLoadingMsgs=false;
    async function loadNewWaMsgs(){{
      if(_waLoadingMsgs)return;
      _waLoadingMsgs=true;
      try{{
        const msgs=document.querySelectorAll('#wa-msgs .msg[data-id]');
        const lastId=msgs.length?msgs[msgs.length-1].dataset.id:0;
        const res=await fetch('/api/wa_messages/{conv_id}?after='+lastId);
        const data=await res.json();
        if(data.messages&&data.messages.length>0){{
          const c=document.getElementById('wa-msgs');
          data.messages.forEach(m=>{{
            if(c.querySelector('[data-id="'+m.id+'"]'))return;
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
      }}catch(e){{}}finally{{_waLoadingMsgs=false;}}
    }}

    // Авто-обновление списка диалогов каждые 4 сек
    var WA_SF = '{status_filter}';
    let _knownConvIds = new Set([{','.join(str(c['id']) for c in (db.get_wa_conversations() if True else []))}]);
    setInterval(async function(){{
      try {{
        const res = await fetch('/api/wa_convs?status='+encodeURIComponent(WA_SF));
        const data = await res.json();
        if(!data.convs) return;
        const list = document.getElementById('conv-items');
        if(!list) return;

        const newIds = new Set(data.convs.map(c=>c.id));
        const hasNew = [...newIds].some(id=>!_knownConvIds.has(id));

        // Обновляем существующие элементы (badge + preview)
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
          // Добавляем только новые чаты — не перерисовываем весь список
          data.convs.forEach(c=>{{
            if(list.querySelector('[data-conv-id="'+c.id+'"]')) return;
            const isFb=!!(c.fbclid||(c.utm_source&&(c.utm_source==='facebook'||c.utm_source==='fb')));
            const srcBadge=isFb?'<span class="source-badge source-fb">🔵 FB</span>':'<span class="source-badge source-organic">organic</span>';
            const inBase=c.in_staff?'<span style="background:#052e16;color:#86efac;border:1px solid #166534;border-radius:5px;font-size:.65rem;padding:1px 6px;margin-left:4px;white-space:nowrap">✅ в базе</span>':'';
            const bdg=c.unread_count>0?'<span class="unread-num unread-badge" style="background:#25d366">'+c.unread_count+'</span>':'';
            let utmHtml='';
            if(isFb){{
              if(c.utm_campaign)utmHtml+='<span class="utm-tag">🎯 '+esc(c.utm_campaign.substring(0,25))+'</span>';
              if(c.utm_content)utmHtml+='<span class="utm-tag" style="background:#1a2a1a;color:#86efac">📌 '+esc(c.utm_content.substring(0,20))+'</span>';
              if(c.utm_term)utmHtml+='<span class="utm-tag" style="background:#1a1a2a;color:#a5b4fc">📂 '+esc(c.utm_term.substring(0,20))+'</span>';
            }}
            const utmLine=utmHtml?'<div class="conv-meta" style="display:flex;flex-wrap:wrap;gap:3px;margin-top:2px">'+utmHtml+'</div>':'';
            let tagsHtml='';
            if(c.tags&&c.tags.length){{c.tags.forEach(function(tg){{tagsHtml+='<span class="conv-tag" style="background:'+tg.color+'22;color:'+tg.color+';border-color:'+tg.color+'55">'+esc(tg.name)+'</span>';}});}}
            const tagsLine=tagsHtml?'<div class="tags-row">'+tagsHtml+'</div>':'';
            const dot=c.status==='open'?'🟢':'⚫';
            const el=document.createElement('div');
            el.innerHTML='<a href="/wa/chat?conv_id='+c.id+'&status_filter='+WA_SF+'"><div class="conv-item" data-conv-id="'+c.id+'">'
              +'<div class="conv-name"><span>'+dot+' '+esc(c.visitor_name)+'</span>'+bdg+inBase+'</div>'
              +'<div class="conv-preview">'+esc(c.last_message||'Нет сообщений')+'</div>'
              +'<div class="conv-time" style="display:flex;align-items:center;justify-content:space-between">💚 +'+c.wa_number.substring(0,10)+' · '+c.last_message_at.substring(11,16)+' '+srcBadge+'</div>'
              +utmLine+tagsLine
              +'</div></a>';
            list.insertBefore(el.firstChild, list.firstChild);
          }});
        }}
      }} catch(e){{}}
    }}, 4000);

    // SPA навигация для WA чатов
    var _waPageLoading = false;
    document.getElementById('conv-items')?.addEventListener('click', function(e){{
      const link = e.target.closest('a[href*="/wa/chat?conv_id="]');
      if(!link) return;
      e.preventDefault();
      const url = new URL(link.href);
      const cid = parseInt(url.searchParams.get('conv_id'));
      const sf  = url.searchParams.get('status_filter') || WA_SF;
      if(cid) loadWaChat(cid, sf);
    }});
    async function loadWaChat(convId, sfParam){{
      if(_waPageLoading) return;
      _waPageLoading = true;
      const chatWin = document.querySelector('.chat-window');
      if(chatWin) chatWin.style.opacity='0.5';
      try{{
        const r = await fetch('/api/wa_chat_panel?conv_id='+convId+'&status_filter='+(sfParam||WA_SF));
        if(!r.ok) throw new Error(r.status);
        const html = await r.text();
        if(chatWin){{ chatWin.innerHTML=html; chatWin.style.opacity='1'; }}
        document.querySelectorAll('#conv-items .conv-item').forEach(function(el){{
          const isActive = el.dataset.convId == String(convId);
          el.classList.toggle('active', isActive);
          if(isActive){{ const b=el.querySelector('.unread-badge'); if(b) b.remove(); }}
        }});
        history.pushState(null,'','/wa/chat?conv_id='+convId+'&status_filter='+(sfParam||WA_SF));
        window.ACTIVE_CONV_ID = convId;
        WA_SF = sfParam || WA_SF;
      }}catch(e){{ if(chatWin) chatWin.style.opacity='1'; }}
      _waPageLoading = false;
    }}

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
    return HTMLResponse(f'<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WA Чаты</title><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">{CSS}</head><body>{nav_html("wa_chat",request)}<div class="main">{content}</div></body></html>')


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
        manager_name = user.get("display_name") or user.get("username") or "Менеджер"
        db.save_wa_message(conv_id, conv["wa_chat_id"], "manager", text, sender_name=manager_name)
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
        "base64": b64,
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
        result = await wa_api("post", "/contact_info", json={"wa_chat_id": conv["wa_chat_id"]})
        log.info(f"[wa/fetch_profile] result={result}")
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
    fbclid   = conv.get("fbclid")
    fbp      = conv.get("fbp")
    campaign = conv.get("utm_campaign") or "whatsapp"
    utm_src  = conv.get("utm_source") or "whatsapp"
    test_event_code = db.get_setting("test_event_code") or None
    wa_number = conv.get("wa_number", "")
    sent = await meta_capi.send_lead_event(
        pixel_id, meta_token,
        user_id=wa_number,
        campaign=campaign,
        fbclid=fbclid,
        fbp=fbp,
        utm_source=utm_src,
        utm_campaign=campaign,
        test_event_code=test_event_code,
        event_source_url=f"https://wa.me/{wa_number}" if wa_number else "https://wa.me/",
    )
    if sent:
        db.set_wa_fb_event(conv_id, "Lead")
    # TikTok Lead
    tt_pixel = db.get_setting("tt_pixel_id")
    tt_token = db.get_setting("tt_access_token")
    if tt_pixel and tt_token:
        await send_tiktok_event(tt_pixel, tt_token, "SubmitForm",
            user_id=conv.get("wa_number", ""),
            ip=request.client.host if request.client else None)
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


# ══════════════════════════════════════════════════════════════════════════════
# TG АККАУНТ — роуты
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/tg_account/chat", response_class=HTMLResponse)
async def tg_account_chat_page(request: Request, conv_id: int = 0, status_filter: str = "open"):
    user, err = require_auth(request)
    if err: return err

    convs = db.get_tg_account_conversations(status=status_filter if status_filter != "all" else None)

    tg_status   = db.get_setting("tg_account_status", "disconnected")
    tg_username = db.get_setting("tg_account_username", "")
    tg_phone    = db.get_setting("tg_account_phone", "")

    if tg_status == "connected":
        conn_badge = f'<div style="background:#052e16;border:1px solid #166534;border-radius:7px;padding:6px 12px;font-size:.8rem;color:#86efac;margin-bottom:8px">📱 Подключён · @{tg_username} · +{tg_phone}</div>'
    else:
        conn_badge = '<div style="background:#2d0a0a;border:1px solid #7f1d1d;border-radius:7px;padding:6px 12px;font-size:.8rem;color:#fca5a5;margin-bottom:8px">⚠️ TG аккаунт не подключён → <a href="/tg_account/setup" style="color:#fca5a5;text-decoration:underline">Подключить</a></div>'

    def tab(val, label):
        active = "background:var(--orange);color:#fff" if val == status_filter else "background:var(--bg3);color:var(--text3)"
        return f'<a href="/tg_account/chat?status_filter={val}" style="flex:1;text-align:center;padding:5px 0;border-radius:7px;font-size:.78rem;font-weight:600;text-decoration:none;{active}">{label}</a>'
    tabs_html = f'<div style="display:flex;gap:4px;margin-bottom:8px">{tab("open","Открытые")}{tab("closed","Закрытые")}{tab("all","Все")}</div>'

    conv_items = ""
    tga_in_staff = db.get_tga_conv_ids_in_staff()
    tga_tags_map = db.get_all_conv_tags_map("tga")
    for c in convs:
        cls = "conv-item active" if c["id"] == conv_id else "conv-item"
        t = (c.get("last_message_at") or c["created_at"])[:16].replace("T", " ")
        ucount = f'<span class="unread-num">{c["unread_count"]}</span>' if c.get("unread_count", 0) > 0 else ""
        dot = "🟢" if c["status"] == "open" else "⚫"
        # Задача 3: FB только если fbclid или utm_source=facebook
        is_fb = bool(c.get("fbclid") or c.get("utm_source") in ("facebook", "fb"))
        src_badge = '<span class="source-badge source-fb">🔵 FB</span>' if is_fb else '<span class="source-badge source-organic">organic</span>'
        # Задача 14: UTM только если не органика
        utm_parts = []
        if is_fb:
            if c.get("utm_campaign"): utm_parts.append(f'<span class="utm-tag" title="Кампания">🎯 {c["utm_campaign"][:25]}</span>')
            if c.get("utm_content"):  utm_parts.append(f'<span class="utm-tag" style="background:#1a2a1a;color:#86efac" title="Объявление">📌 {c["utm_content"][:20]}</span>')
            if c.get("utm_term"):     utm_parts.append(f'<span class="utm-tag" style="background:#1a1a2a;color:#a5b4fc" title="Адсет">📂 {c["utm_term"][:20]}</span>')
        utm_line = '<div class="conv-meta" style="display:flex;flex-wrap:wrap;gap:3px;margin-top:2px">' + "".join(utm_parts) + '</div>' if utm_parts else ""
        tg_uname = c.get("username") or ""
        uname_str = ("@" + tg_uname) if tg_uname else str(c.get("tg_user_id", ""))
        # Задача 5: отметка "уже в базе"
        staff_info = tga_in_staff.get(c["id"])
        in_base_badge = f'<span style="background:#052e16;color:#86efac;border:1px solid #166534;border-radius:5px;font-size:.65rem;padding:1px 6px;margin-left:4px;white-space:nowrap">✅ в базе</span>' if staff_info else ""
        # Теги
        ctags = tga_tags_map.get(c["id"], [])
        tags_line = ""
        if ctags:
            tags_html = "".join(f'<span class="conv-tag" style="background:{tg["color"]}22;color:{tg["color"]};border-color:{tg["color"]}55">{tg["name"]}</span>' for tg in ctags)
            tags_line = f'<div class="tags-row">{tags_html}</div>'
        # Задача 6: порядок как в WA
        conv_items += (f'<a href="/tg_account/chat?conv_id={c["id"]}&status_filter={status_filter}">' + f'<div class="{cls}" data-conv-id="{c["id"]}">' + f'<div class="conv-name"><span>{dot} {c["visitor_name"]}</span>{ucount}{in_base_badge}</div>' + f'<div class="conv-preview">{(c.get("last_message") or "Нет сообщений")[:50]}</div>' + f'<div class="conv-time" style="display:flex;align-items:center;justify-content:space-between">📱 {uname_str} · {t[-5:]} {src_badge}</div>' + utm_line + tags_line + '</div></a>')

    if not conv_items:
        conv_items = '<div style="padding:20px;text-align:center;color:var(--text3);font-size:.85rem">Нет диалогов</div>'

    chat_area = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text3);font-size:.9rem">Выберите диалог</div>'

    if conv_id:
        active_conv = db.get_tg_account_conversation(conv_id)
        if active_conv:
            db.mark_tg_account_conv_read(conv_id)
            msgs = db.get_tg_account_messages(conv_id)
            messages_html = ""
            for m in msgs:
                t = m["created_at"][11:16]
                if m.get("media_url") and (m.get("media_type") or "").startswith("image/"):
                    ch = f'<img src="{m["media_url"]}" style="max-width:220px;border-radius:8px;display:block;cursor:pointer" onclick="window.open(this.src)" />'
                elif m.get("media_url"):
                    ch = f'<a href="{m["media_url"]}" target="_blank" style="color:#60a5fa">📎 Открыть файл</a>'
                else:
                    ch = (m["content"] or "").replace("<", "&lt;")
                sl = f'<div style="font-size:.68rem;color:var(--orange);margin-bottom:2px;text-align:right;opacity:.8">{m["sender_name"]}</div>' if m.get("sender_name") and m["sender_type"] == "manager" else ""
                messages_html += f'<div class="msg {m["sender_type"]}" data-id="{m["id"]}">{sl}<div class="msg-bubble">{ch}</div><div class="msg-time">{t}</div></div>'

            uname = f"@{active_conv['username']}" if active_conv.get("username") else active_conv.get("tg_user_id", "")
            # Задача 7: Карточка сотрудника для TG
            tga_staff = db.get_staff_by_tg_account_conv(conv_id)
            if tga_staff:
                tga_card_link = f'<a href="/staff?edit={tga_staff["id"]}" style="display:inline-flex;align-items:center;gap:4px;background:#052e16;color:#86efac;border:1px solid #166534;border-radius:6px;padding:2px 8px;font-size:.73rem;text-decoration:none">✅ В базе · {tga_staff.get("name","") or "Карточка"} →</a>'
            else:
                tga_card_link = f'<a href="/staff/create_from_tga?conv_id={conv_id}" style="display:inline-flex;align-items:center;gap:4px;background:var(--bg3);color:var(--text3);border:1px solid var(--border);border-radius:6px;padding:2px 8px;font-size:.73rem;text-decoration:none">+ Создать карточку</a>'
            # Теги чата
            all_tags     = db.get_all_tags()
            active_ctags = db.get_conv_tags("tga", conv_id)
            active_tag_ids = {tg["id"] for tg in active_ctags}
            tga_tags_html = _render_conv_tags_picker(active_ctags, all_tags, active_tag_ids, "tga", conv_id)
            fb_sent = active_conv.get("fb_event_sent")
            lead_btn = '<span class="badge-green">✅ Lead отправлен</span>' if fb_sent else \
                       f'<form method="post" action="/tg_account/send_lead" style="display:inline"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn btn-sm" style="font-size:.73rem;background:#1e3a5f;border:1px solid #3b5998;color:#93c5fd">📤 Lead → FB</button></form>'
            status_color = "#34d399" if active_conv["status"] == "open" else "#ef4444"
            close_btn = f'<form method="post" action="/tg_account/close"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-gray btn-sm">✓ Закрыть</button></form>' if active_conv["status"] == "open" else \
                        f'<form method="post" action="/tg_account/reopen"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-orange btn-sm">↺ Открыть</button></form>'
            delete_btn = f'<button class="btn-gray btn-sm" style="color:#fff;background:#7f1d1d;border-color:#7f1d1d;font-size:.78rem;padding:5px 10px" onclick="deleteTgAccConv({conv_id})" title="Удалить диалог">🗑 Удалить</button>' if user and user.get("role") == "admin" else ""
            call_url = f"https://t.me/{active_conv['username']}" if active_conv.get("username") else f"tg://user?id={active_conv.get('tg_user_id','')}"
            tags = []
            if active_conv.get("fbclid"): tags.append('<span class="utm-tag" style="background:#1e3a5f;color:#60a5fa">🔵 Facebook</span>')
            if active_conv.get("utm_campaign"): tags.append(f'<span class="utm-tag">🎯 {active_conv["utm_campaign"][:25]}</span>')
            if active_conv.get("utm_content"): tags.append(f'<span class="utm-tag" style="background:#1a2a1a;color:#86efac">📌 {active_conv["utm_content"][:20]}</span>')
            if active_conv.get("utm_term"): tags.append(f'<span class="utm-tag" style="background:#1a1a2a;color:#a5b4fc">📂 {active_conv["utm_term"][:20]}</span>')
            if active_conv.get("fbclid"): tags.append('<span class="utm-tag badge-green">fbclid ✓</span>')
            utm_tags = '<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:6px">' + "".join(tags) + '</div>' if tags else ""
            _tga_photo = active_conv.get("photo_url") or ""
            if _tga_photo:
                _tga_avatar = (
                    '<div class="tga-avatar-wrap">'
                    + '<img src="' + _tga_photo + '" style="width:42px;height:42px;border-radius:50%;object-fit:cover;border:2px solid var(--orange)" />'
                    + '<div class="tga-avatar-zoom"><img src="' + _tga_photo + '" /></div>'
                    + '</div>')
            else:
                _tga_avatar = '<div class="avatar">T</div>'
                _tga_avatar = '<div class="avatar">T</div>'
            chat_area = f"""
            <div class="chat-header">
              <div style="display:flex;align-items:flex-start;gap:12px;flex:1">
                {_tga_avatar}
                <div style="flex:1">
                  <div style="font-weight:700;color:var(--text)">{active_conv['visitor_name']} <span style="color:{status_color};font-size:.72rem">●</span></div>
                  <div style="font-size:.78rem;color:var(--text3)">{uname} · {tga_card_link}</div>
                  <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:6px;align-items:center">
                    {lead_btn}
                    <a href="{call_url}" target="_blank" class="btn-gray btn-sm" style="display:inline-flex;align-items:center;gap:4px;padding:5px 10px;border-radius:7px;font-size:.74rem;border:1px solid var(--border);text-decoration:none">📞 Открыть в TG</a>
                  </div>
                  {utm_tags}
                  {tga_tags_html}
                </div>
              </div>
              <div style="display:flex;gap:6px;flex-shrink:0">{close_btn} {delete_btn}</div>
            </div>
            <div class="chat-messages" id="tga-msgs">{messages_html}</div>
            <div id="tga-send-error" style="display:none;padding:8px 18px;background:#2d0a0a;border-top:1px solid #7f1d1d;font-size:.8rem;color:#fca5a5;align-items:center;justify-content:space-between;gap:8px">
              <span id="tga-send-error-text"></span>
              <button onclick="document.getElementById('tga-send-error').style.display='none'" style="background:none;border:none;color:#fca5a5;cursor:pointer;font-size:1rem;line-height:1">✕</button>
            </div>
            <div class="chat-input" id="tga-chat-input">
              <div id="tga-disconnected-banner" style="display:{'none' if tg_status == 'connected' else 'flex'};align-items:center;justify-content:space-between;padding:8px 12px;background:#1c1a00;border:1px solid #713f12;border-radius:8px;margin-bottom:8px;font-size:.8rem;color:#fde047;gap:8px">
                <span>⚠️ TG аккаунт не подключён — сообщения не будут доставлены</span>
                <a href="/tg_account/setup" style="color:#fde047;font-weight:600;white-space:nowrap;text-decoration:underline">Подключить →</a>
              </div>
              <div class="chat-input-row">
                <div style="position:relative;flex:1">
                  <textarea id="tga-inp" placeholder="Написать в Telegram... (Enter — отправить)"
                    style="width:100%;resize:none;background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:10px 44px 10px 14px;color:var(--text);font-size:.9rem;font-family:inherit;min-height:44px;max-height:120px"
                    rows="1" onkeydown="if(event.key==='Enter'&&!event.shiftKey){{event.preventDefault();sendTgAccMsg()}}"></textarea>
                  <label style="position:absolute;right:10px;bottom:10px;cursor:pointer;opacity:.6">
                    📎<input type="file" id="tga-file" style="display:none" onchange="sendTgAccFile(this)"/>
                  </label>
                </div>
                <button class="btn-orange" onclick="sendTgAccMsg()" style="height:44px;padding:0 18px;flex-shrink:0">Отправить</button>
              </div>
            </div>
            <script>
            var TGA_CONV_ID={conv_id};
            var TGA_SF='{status_filter}';
            var tgaMsgBox=document.getElementById('tga-msgs');
            if(tgaMsgBox) tgaMsgBox.scrollTop=tgaMsgBox.scrollHeight;
            var lastTgAId=(function(){{var m=document.querySelectorAll('#tga-msgs .msg[data-id]');return m.length?m[m.length-1].dataset.id:0;}})();
            function escTga(t){{return(t||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}}
            function showTgaError(msg){{
              var errDiv=document.getElementById('tga-send-error');
              var errTxt=document.getElementById('tga-send-error-text');
              if(!errDiv||!errTxt) return;
              var isDisconn = msg&&(msg.toLowerCase().includes('not connected')||msg.toLowerCase().includes('503')||msg.toLowerCase().includes('disconnect'));
              if(isDisconn){{
                errTxt.innerHTML='⚠️ TG аккаунт не подключён. <a href="/tg_account/setup" style="color:#fca5a5;text-decoration:underline;font-weight:600">Подключить новый аккаунт →</a>';
                var banner=document.getElementById('tga-disconnected-banner');
                if(banner) banner.style.display='flex';
              }} else {{
                errTxt.textContent='Ошибка отправки: '+(msg||'неизвестная ошибка');
              }}
              errDiv.style.display='flex';
              setTimeout(function(){{errDiv.style.display='none';}}, 6000);
            }}
            async function sendTgAccMsg(){{
              var inp=document.getElementById('tga-inp');
              var text=inp.value.trim();if(!text)return;inp.value='';
              try{{
                var r=await fetch('/tg_account/send',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:'conv_id='+TGA_CONV_ID+'&text='+encodeURIComponent(text)}});
                var d=await r.json();if(!d.ok)showTgaError(d.error||'');else loadNewTgAccMsgs();
              }}catch(e){{showTgaError(e.message);}}
            }}
            async function sendTgAccFile(input){{
              if(!input.files[0])return;
              var fd=new FormData();fd.append('conv_id',TGA_CONV_ID);fd.append('file',input.files[0]);
              try{{
                var r=await fetch('/tg_account/send_media',{{method:'POST',body:fd}});
                var d=await r.json();if(!d.ok)showTgaError(d.error||'');else loadNewTgAccMsgs();
              }}catch(e){{showTgaError(e.message);}}
              input.value='';
            }}
            var _tgaLoadingMsgs=false;
            async function loadNewTgAccMsgs(){{
              if(_tgaLoadingMsgs)return;
              _tgaLoadingMsgs=true;
              try{{
                var res=await fetch('/api/tg_account_messages/{conv_id}?after='+lastTgAId);
                if(!res.ok){{_tgaLoadingMsgs=false;return;}}var data=await res.json();
                if(!data.messages||!data.messages.length){{_tgaLoadingMsgs=false;return;}}
                data.messages.forEach(function(m){{
                  if(tgaMsgBox.querySelector('[data-id="'+m.id+'"]'))return;
                  var d=document.createElement('div');d.className='msg '+m.sender_type;d.dataset.id=m.id;
                  var inner=m.media_url&&m.media_type&&m.media_type.startsWith('image/')
                    ?'<img src="'+m.media_url+'" style="max-width:220px;border-radius:8px;display:block;cursor:pointer" onclick="window.open(this.src)"/>'
                    :m.media_url?'<a href="'+m.media_url+'" target="_blank" style="color:#60a5fa">Открыть файл</a>':escTga(m.content||'');
                  var sl=m.sender_name&&m.sender_type==='manager'?'<div style="font-size:.68rem;color:var(--orange);margin-bottom:2px;text-align:right;opacity:.8">'+escTga(m.sender_name)+'</div>':'';
                  d.innerHTML=sl+'<div class="msg-bubble">'+inner+'</div><div class="msg-time">'+m.created_at.substring(11,16)+'</div>';
                  tgaMsgBox.appendChild(d);lastTgAId=m.id;
                }});
                tgaMsgBox.scrollTop=tgaMsgBox.scrollHeight;
              }}catch(e){{}}finally{{_tgaLoadingMsgs=false;}}
            }}
            async function deleteTgAccConv(id){{
              var btn=document.querySelector('[onclick*="deleteTgAccConv"]');
              if(btn){{btn.textContent='...';btn.disabled=true;}}
              try{{
                var r=await fetch('/tg_account/delete',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:'conv_id='+id}});
                var d=await r.json();
                if(d.ok) window.location.href='/tg_account/chat?status_filter='+TGA_SF;
                else{{alert('Ошибка: '+(d.error||r.status));if(btn){{btn.textContent='Удалить';btn.disabled=false;}}}}
              }}catch(e){{showTgaError(e.message);if(btn){{btn.textContent='Удалить';btn.disabled=false;}}}}
            }}
            setInterval(loadNewTgAccMsgs,3000);
            // Polling статуса TG — обновляем баннер при подключении/отключении
            setInterval(async function(){{
              try{{
                var r=await fetch('/api/stats');
                if(!r.ok)return;
                var d=await r.json();
                var banner=document.getElementById('tga-disconnected-banner');
                if(!banner)return;
                banner.style.display=(d.tg_status==='connected')?'none':'flex';
              }}catch(e){{}}
            }},5000);
            // ── SPA навигация по чатам ──────────────────────────────────────
            var _tgaChatLoading = false;
            async function loadTgaChat(convId, sfParam) {{
              if(_tgaChatLoading) return;
              _tgaChatLoading = true;
              var chatWin = document.querySelector('.chat-window') || document.getElementById('tg-chat-area');
              if(chatWin) chatWin.style.opacity = '0.5';
              try {{
                var url = '/api/tga_chat_panel?conv_id=' + convId + '&status_filter=' + (sfParam||'open');
                var r = await fetch(url);
                if(!r.ok) throw new Error(r.status);
                var html = await r.text();
                if(chatWin) {{ chatWin.innerHTML = html; chatWin.style.opacity = '1'; }}
                // Обновляем активный элемент в списке
                document.querySelectorAll('#tg-conv-items .conv-item').forEach(function(el){{
                  var isActive = el.dataset.convId == String(convId);
                  el.classList.toggle('active', isActive);
                  // Мгновенно убираем бейдж непрочитанных на активном чате
                  if(isActive) {{
                    var badge = el.querySelector('.unread-num');
                    if(badge) badge.remove();
                  }}
                }});
                // Обновляем URL без перезагрузки
                history.pushState(null, '', '/tg_account/chat?conv_id=' + convId + '&status_filter=' + (sfParam||'open'));
                // Обновляем глобальные переменные для polling
                if(typeof TGA_CONV_ID !== 'undefined') window.TGA_CONV_ID = convId;
                ACTIVE_TGA_CONV_ID = convId;
              }} catch(e) {{ if(chatWin) chatWin.style.opacity = '1'; }}
              _tgaChatLoading = false;
            }}
            // Перехватываем клики по чатам в списке
            document.getElementById('tg-conv-items').addEventListener('click', function(e) {{
              var link = e.target.closest('a[href*="/tg_account/chat?conv_id="]');
              if(!link) return;
              e.preventDefault();
              var url = new URL(link.href);
              var cid = parseInt(url.searchParams.get('conv_id'));
              var sf  = url.searchParams.get('status_filter') || 'open';
              if(cid) loadTgaChat(cid, sf);
            }});
            function filterTgConvs(q){{
              var items=document.querySelectorAll('#tg-conv-items .conv-item');
              items.forEach(function(el){{
                var txt=(el.textContent||'').toLowerCase();
                el.parentElement.style.display=txt.includes(q.toLowerCase())?'':'none';
              }});
            }}
            var ACTIVE_TGA_CONV_ID={conv_id};
            var _knownTgIds=new Set([{','.join(str(c['id']) for c in convs)}]);
            setInterval(async function(){{
              try{{
                var res=await fetch('/api/tg_account_convs?status='+encodeURIComponent(TGA_SF));
                var data=await res.json();
                if(!data.convs)return;
                var list=document.getElementById('tg-conv-items');
                if(!list)return;
                var newIds=new Set(data.convs.map(function(c){{return c.id;}}));
                var hasNew=[...newIds].some(function(id){{return!_knownTgIds.has(id);}});
                data.convs.forEach(function(c){{
                  var item=list.querySelector('[data-conv-id="'+c.id+'"]');
                  if(item){{
                    var badge=item.querySelector('.unread-badge');
                    if(c.unread_count>0){{
                      if(badge)badge.textContent=c.unread_count;
                      else{{var b=document.createElement('span');b.className='unread-num unread-badge';b.textContent=c.unread_count;var nm=item.querySelector('.conv-name');if(nm)nm.appendChild(b);}}
                    }}else if(badge)badge.remove();
                    var prev=item.querySelector('.conv-preview');
                    if(prev)prev.textContent=c.last_message||'Нет сообщений';
                  }}
                }});
                if(hasNew){{
                  _knownTgIds=newIds;
                  list.innerHTML=data.convs.map(function(c){{
                    var active=c.id===ACTIVE_TGA_CONV_ID?' active':'';
                    var dot=c.status==='open'?'🟢':'⚫';
                    var bdg=c.unread_count>0?'<span class="unread-num unread-badge">'+c.unread_count+'</span>':'';
                    var inBase=c.in_staff?'<span style="background:#052e16;color:#86efac;border:1px solid #166534;border-radius:5px;font-size:.65rem;padding:1px 6px;margin-left:4px;white-space:nowrap">✅ в базе</span>':'';
                    var isFb=!!(c.fbclid||(c.utm_source&&(c.utm_source==='facebook'||c.utm_source==='fb')));
                    var src=isFb?'<span class="source-badge source-fb">🔵 FB</span>':'<span class="source-badge source-organic">organic</span>';
                    var uname=c.username?'@'+escTga(c.username):'';
                    var utm='';
                    if(isFb){{
                      if(c.utm_campaign)utm+='<span class="utm-tag" title="Кампания">🎯 '+escTga(c.utm_campaign.substring(0,25))+'</span>';
                      if(c.utm_content)utm+='<span class="utm-tag" style="background:#1a2a1a;color:#86efac" title="Объявление">📌 '+escTga(c.utm_content.substring(0,20))+'</span>';
                      if(c.utm_term)utm+='<span class="utm-tag" style="background:#1a1a2a;color:#a5b4fc" title="Адсет">📂 '+escTga(c.utm_term.substring(0,20))+'</span>';
                    }}
                    var utmLine=utm?'<div class="conv-meta" style="display:flex;flex-wrap:wrap;gap:3px;margin-top:2px">'+utm+'</div>':'';
                    return '<a href="/tg_account/chat?conv_id='+c.id+'"><div class="conv-item'+active+'" data-conv-id="'+c.id+'">'
                      +'<div class="conv-name"><span>'+dot+' '+escTga(c.visitor_name)+'</span>'+bdg+inBase+'</div>'
                      +'<div class="conv-preview">'+escTga((c.last_message||'Нет сообщений').substring(0,50))+'</div>'
                      +'<div class="conv-time" style="display:flex;align-items:center;justify-content:space-between">📱 '+uname+' · '+c.last_message_at.substring(11,16)+' '+src+'</div>'
                      +utmLine+'</div></a>';
                  }}).join('')||'<div style="padding:20px;text-align:center;color:var(--text3)">Нет диалогов</div>';
                  if(ACTIVE_TGA_CONV_ID===0&&data.convs.length>0){{
                    window.location.href='/tg_account/chat?conv_id='+data.convs[0].id;
                  }}
                }}
              }}catch(e){{}}
            }},4000);
            </script>"""

    content_html = f"""<div class="chat-layout">
      <div class="conv-list">
        <div class="conv-search">{conn_badge}{tabs_html}<input type="text" placeholder="🔍 Поиск..." oninput="filterTgConvs(this.value)" style="width:100%;margin-top:6px"/></div>
        <div id="tg-conv-items" style="overflow-y:auto;flex:1">{conv_items}</div>
      </div>
      <div class="chat-window">{chat_area}</div>
    </div>"""
    return HTMLResponse(base(content_html, "tg_account_chat", request))


@app.get("/tg_account/setup", response_class=HTMLResponse)
async def tg_account_setup(request: Request, msg: str = ""):
    user, err = require_auth(request, role="admin")
    if err: return err
    tg_status   = db.get_setting("tg_account_status", "disconnected")
    tg_username = db.get_setting("tg_account_username", "")
    tg_phone    = db.get_setting("tg_account_phone", "")
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""

    if tg_status == "connected":
        body_html = f"""
          <div style="background:#052e16;border:1px solid #166534;border-radius:12px;padding:16px;margin-bottom:20px">
            <div style="font-weight:700;color:#86efac;margin-bottom:4px">✅ Telegram аккаунт подключён</div>
            <div style="font-size:.85rem;color:#6ee7b7">@{tg_username} · +{tg_phone}</div>
          </div>
          <form method="post" action="/tg_account/disconnect">
            <button class="btn-gray" style="color:var(--red);border-color:#7f1d1d">🔌 Отключить аккаунт</button>
          </form>"""
    else:
        svc = await tg_api("get", "/status")
        svc_state = svc.get("status", "disconnected") if not svc.get("error") else "disconnected"
        # Состояние из БД имеет приоритет для awaiting_code / awaiting_2fa
        # TG сервис может вернуть "disconnected" даже когда код уже отправлен
        if tg_status in ("awaiting_code", "awaiting_2fa"):
            svc_state = tg_status
        if svc_state == "awaiting_code":
            body_html = """<div style="background:#1c1a00;border:1px solid #713f12;border-radius:12px;padding:16px;margin-bottom:20px">
                <div style="font-weight:700;color:#fde047">📱 Введите код из SMS</div></div>
              <form method="post" action="/tg_account/sign_in" style="display:flex;flex-direction:column;gap:12px;max-width:360px">
                <div class="field-group"><div class="field-label">Код из SMS / Telegram</div>
                  <input type="text" name="code" placeholder="12345" autofocus required style="letter-spacing:.2em;font-size:1.1rem"/></div>
                <button class="btn">✅ Войти</button></form>"""
        elif svc_state == "awaiting_2fa":
            body_html = """<div style="background:#1c1a00;border:1px solid #713f12;border-radius:12px;padding:16px;margin-bottom:20px">
                <div style="font-weight:700;color:#fde047">🔐 Требуется пароль 2FA</div></div>
              <form method="post" action="/tg_account/sign_in_2fa" style="display:flex;flex-direction:column;gap:12px;max-width:360px">
                <div class="field-group"><div class="field-label">Пароль 2FA</div>
                  <input type="password" name="password" autofocus required/></div>
                <button class="btn">🔓 Подтвердить</button></form>"""
        else:
            # Читаем сохранённые api_id/api_hash из БД
            saved_api_id   = db.get_setting("tg_api_id", "")
            saved_api_hash = db.get_setting("tg_api_hash", "")
            has_creds = bool(saved_api_id and saved_api_hash)
            _api_id_short = saved_api_id[:4] if saved_api_id else ""
            creds_badge = (
                f'<div style="background:#052e16;border:1px solid #166534;border-radius:8px;padding:8px 12px;font-size:.8rem;color:#86efac;margin-bottom:12px">'
                f'✅ API credentials сохранены (App ID: {_api_id_short}...)</div>'
                if has_creds else
                '<div style="background:#1c1a00;border:1px solid #713f12;border-radius:8px;padding:8px 12px;font-size:.8rem;color:#fde047;margin-bottom:12px">'
                '⚠️ Введите API credentials с my.telegram.org</div>'
            )
            body_html = f"""<div style="background:#2d0a0a;border:1px solid #7f1d1d;border-radius:12px;padding:16px;margin-bottom:20px">
                <div style="font-weight:700;color:#fca5a5">⚠️ Не подключён</div></div>
              {creds_badge}
              <form method="post" action="/tg_account/send_code" style="display:flex;flex-direction:column;gap:14px;max-width:400px">
                <div style="background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:14px">
                  <div style="font-size:.78rem;font-weight:700;color:var(--orange);text-transform:uppercase;margin-bottom:10px">🔑 API Credentials (my.telegram.org)</div>
                  <div class="grid-2" style="gap:10px">
                    <div class="field-group">
                      <div class="field-label">App api_id</div>
                      <input type="text" name="api_id" value="{saved_api_id}" placeholder="12345678" required/>
                    </div>
                    <div class="field-group">
                      <div class="field-label">App api_hash</div>
                      <input type="text" name="api_hash" value="{saved_api_hash}" placeholder="abc123def456..."/>
                    </div>
                  </div>
                  <div style="font-size:.72rem;color:var(--text3);margin-top:8px">
                    Получи на <a href="https://my.telegram.org" target="_blank" style="color:var(--orange)">my.telegram.org</a> → API development tools
                  </div>
                </div>
                <div class="field-group">
                  <div class="field-label">Номер телефона (с кодом страны)</div>
                  <input type="text" name="phone" placeholder="+79001234567" required/>
                </div>
                <button class="btn">📱 Отправить код</button>
              </form>"""

    content_html = f"""<div class="page-wrap">
      <div class="page-title">📱 TG Аккаунт — Подключение</div>
      {alert}
      <div class="section"><div class="section-head"><h3>🔗 Управление подключением</h3></div>
        <div class="section-body">{body_html}</div></div></div>"""
    return HTMLResponse(base(content_html, "tg_account_setup", request))


@app.post("/tg_account/send_code")
async def tg_account_send_code(request: Request, phone: str = Form(...),
                                 api_id: str = Form(""), api_hash: str = Form("")):
    user, err = require_auth(request, role="admin")
    if err: return err
    # Сохраняем credentials в БД
    if api_id.strip():   db.set_setting("tg_api_id",   api_id.strip())
    if api_hash.strip(): db.set_setting("tg_api_hash", api_hash.strip())
    # Берём из БД если не пришли в форме
    final_api_id   = api_id.strip()   or db.get_setting("tg_api_id", "")
    final_api_hash = api_hash.strip() or db.get_setting("tg_api_hash", "")
    result = await tg_api("post", "/auth/send_code", json={
        "phone":    phone.strip(),
        "api_id":   final_api_id,
        "api_hash": final_api_hash,
    })
    if result.get("error"):
        db.set_setting("tg_account_status", "disconnected")
        return RedirectResponse(f"/tg_account/setup?msg=Ошибка:+{result['error']}", 303)
    # Сохраняем в БД: ждём ввода кода
    db.set_setting("tg_account_status", "awaiting_code")
    db.set_setting("tg_account_phone",  phone.strip())
    return RedirectResponse("/tg_account/setup?msg=Код+отправлен", 303)


@app.post("/tg_account/sign_in")
async def tg_account_sign_in(request: Request, code: str = Form(...)):
    user, err = require_auth(request, role="admin")
    if err: return err
    result = await tg_api("post", "/auth/sign_in", json={"code": code.strip()})
    if result.get("error") == "2fa_required":
        db.set_setting("tg_account_status", "awaiting_2fa")
        return RedirectResponse("/tg_account/setup", 303)
    if result.get("error"):
        db.set_setting("tg_account_status", "disconnected")
        return RedirectResponse(f"/tg_account/setup?msg=Ошибка: {result['error']}", 303)
    # Успешный вход — статус придёт через webhook, но сбрасываем awaiting_code на всякий случай
    db.set_setting("tg_account_status", "connected")
    return RedirectResponse("/tg_account/setup?msg=Аккаунт+подключён", 303)


@app.post("/tg_account/sign_in_2fa")
async def tg_account_sign_in_2fa(request: Request, password: str = Form(...)):
    user, err = require_auth(request, role="admin")
    if err: return err
    result = await tg_api("post", "/auth/sign_in", json={"password": password})
    if result.get("error"):
        return RedirectResponse(f"/tg_account/setup?msg=Ошибка: {result['error']}", 303)
    return RedirectResponse("/tg_account/setup?msg=Аккаунт+подключён", 303)


@app.post("/tg_account/disconnect")
async def tg_account_disconnect(request: Request):
    user, err = require_auth(request, role="admin")
    if err: return err
    await tg_api("post", "/auth/sign_out")
    db.set_setting("tg_account_status", "disconnected")
    db.set_setting("tg_account_username", "")
    db.set_setting("tg_account_phone", "")
    return RedirectResponse("/tg_account/setup?msg=Аккаунт+отключён", 303)


@app.post("/tg/webhook")
async def tg_account_webhook(request: Request):
    secret = request.headers.get("X-TG-Secret", "")
    if secret != TG_WH_SECRET:
        return JSONResponse({"error": "unauthorized"}, 401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": True})

    event = body.get("event")
    data  = body.get("data", {})
    log.info(f"[TG webhook] event={event} keys={list(data.keys())}")

    try:
        if event == "ready":
            db.set_setting("tg_account_status", "connected")
            db.set_setting("tg_account_username", data.get("username", ""))
            db.set_setting("tg_account_phone", data.get("phone", ""))
            db.set_setting("tg_account_name", data.get("name", ""))

        elif event == "disconnected":
            db.set_setting("tg_account_status", "disconnected")
            db.set_setting("tg_account_username", "")

        elif event == "message":
            tg_user_id  = data.get("tg_user_id", "")
            username    = data.get("username", "")
            sender_name = data.get("sender_name") or username or tg_user_id
            raw_text    = data.get("body") or ""
            has_media   = data.get("has_media", False)
            media_b64   = data.get("media_base64")
            media_type  = data.get("media_type", "")

            media_url = None
            if media_b64:
                try:
                    import cloudinary, cloudinary.uploader, base64 as _b64
                    cld_url = db.get_setting("cloudinary_url") or os.getenv("CLOUDINARY_URL", "")
                    if cld_url:
                        cloudinary.config(cloudinary_url=cld_url)
                        mime = media_type or "image/jpeg"
                        result = cloudinary.uploader.upload(f"data:{mime};base64,{media_b64}", folder="tg_account_media", resource_type="auto")
                        media_url = result.get("secure_url")
                    elif media_type and media_type.startswith("image/"):
                        media_url = f"data:{media_type};base64,{media_b64}"
                except Exception as e:
                    log.error(f"[TG webhook] media upload error: {e}")

            if not raw_text and has_media:
                raw_text = "[фото]" if (media_type or "").startswith("image/") else "[файл]"
            text = (raw_text or "").strip() or "[сообщение]"

            conv = db.get_or_create_tg_account_conversation(tg_user_id, sender_name, username)
            # Подтягиваем фото профиля если ещё не загружено
            if not conv.get("photo_url"):
                try:
                    contact_info = await tg_api("get", f"/contact/{tg_user_id}")
                    if contact_info.get("ok") and contact_info.get("photo_url"):
                        db.update_tg_account_contact_info(conv["id"],
                            photo_url=contact_info.get("photo_url"),
                            about=contact_info.get("about",""))
                        conv = db.get_tg_account_conversation(conv["id"]) or conv
                except Exception as _e:
                    log.warning(f"[TG webhook] photo fetch error: {_e}")
            is_new = not conv.get("utm_source") and not conv.get("fbclid")
            if is_new:
                click_data = db.get_staff_click_recent_any(minutes=30)
                if click_data:
                    db.apply_utm_to_tg_conv(conv["id"],
                        fbclid=click_data.get("fbclid"), fbp=click_data.get("fbp"),
                        utm_source=click_data.get("utm_source"), utm_medium=click_data.get("utm_medium"),
                        utm_campaign=click_data.get("utm_campaign"), utm_content=click_data.get("utm_content"),
                        utm_term=click_data.get("utm_term"))
                    db.mark_staff_click_used(click_data["ref_id"])
                    conv = db.get_tg_account_conversation(conv["id"]) or conv

            db.save_tg_account_message(conv["id"], tg_user_id, "visitor", text, media_url=media_url, media_type=media_type)
            db.update_tg_account_last_message(tg_user_id, text, increment_unread=True)

            notify_chat = db.get_setting("notify_chat_id")
            bot2 = bot_manager.get_staff_bot()
            if notify_chat and bot2:
                try:
                    ustr = f"@{username}" if username else tg_user_id
                    short = text[:80] + ("..." if len(text) > 80 else "")
                    await bot2.send_message(int(notify_chat),
                        f"📱 TG Аккаунт — новое сообщение\n👤 {sender_name} ({ustr})\n✉️ {short}")
                except Exception as e:
                    log.warning(f"[TG webhook] notify error: {e}")
    except Exception as e:
        log.error(f"[TG webhook] error: {e}", exc_info=True)
    return JSONResponse({"ok": True})


@app.post("/tg_account/send")
async def tg_account_send(request: Request, conv_id: int = Form(...), text: str = Form(...)):
    user, err = require_auth(request)
    if err: return JSONResponse({"error": "unauthorized"}, 401)
    conv = db.get_tg_account_conversation(conv_id)
    if not conv: return JSONResponse({"error": "not found"}, 404)
    result = await tg_api("post", "/send", json={"to": conv["tg_user_id"], "message": text})
    if not result.get("error"):
        manager_name = user.get("display_name") or user.get("username") or "Менеджер"
        db.save_tg_account_message(conv_id, conv["tg_user_id"], "manager", text, sender_name=manager_name)
        db.update_tg_account_last_message(conv["tg_user_id"], f"Вы: {text}", increment_unread=False)
    return JSONResponse({"ok": not result.get("error"), "error": result.get("error")})


@app.post("/tg_account/send_media")
async def tg_account_send_media(request: Request, conv_id: int = Form(...), file: UploadFile = File(...)):
    user, err = require_auth(request)
    if err: return JSONResponse({"error": "unauthorized"}, 401)
    conv = db.get_tg_account_conversation(conv_id)
    if not conv: return JSONResponse({"error": "not found"}, 404)
    import base64 as _b64
    file_data = await file.read()
    b64 = _b64.b64encode(file_data).decode()
    mimetype = file.content_type or "image/jpeg"
    filename = file.filename or "file"
    result = await tg_api("post", "/send_media", json={"to": conv["tg_user_id"], "base64": b64, "mimetype": mimetype, "filename": filename})
    if not result.get("error"):
        manager_name = user.get("display_name") or user.get("username") or "Менеджер"
        db.save_tg_account_message(conv_id, conv["tg_user_id"], "manager", "[файл]", media_type=mimetype, sender_name=manager_name)
        db.update_tg_account_last_message(conv["tg_user_id"], "Вы: [файл]", increment_unread=False)
    return JSONResponse({"ok": not result.get("error"), "error": result.get("error")})


@app.post("/tg_account/send_lead")
async def tg_account_send_lead(request: Request, conv_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    conv = db.get_tg_account_conversation(conv_id)
    if not conv: return RedirectResponse("/tg_account/chat", 303)
    if conv.get("fb_event_sent"):
        return RedirectResponse(f"/tg_account/chat?conv_id={conv_id}", 303)
    pixel_id   = db.get_setting("pixel_id_staff") or db.get_setting("pixel_id")
    meta_token = db.get_setting("meta_token_staff") or db.get_setting("meta_token")
    test_event_code = db.get_setting("test_event_code") or None
    sent = await meta_capi.send_lead_event(
        pixel_id, meta_token,
        user_id=conv.get("tg_user_id", ""),
        campaign=conv.get("utm_campaign") or "telegram_account",
        fbclid=conv.get("fbclid"), fbp=conv.get("fbp"),
        utm_source=conv.get("utm_source") or "telegram",
        utm_campaign=conv.get("utm_campaign"),
        test_event_code=test_event_code,
        event_source_url="https://t.me/",
    )
    if sent:
        db.set_tg_account_fb_event(conv_id, "Lead")
    return RedirectResponse(f"/tg_account/chat?conv_id={conv_id}", 303)


@app.post("/tg_account/close")
async def tg_account_close(request: Request, conv_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.close_tg_account_conv(conv_id)
    return RedirectResponse(f"/tg_account/chat?conv_id={conv_id}", 303)


@app.post("/tg_account/reopen")
async def tg_account_reopen(request: Request, conv_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.reopen_tg_account_conv(conv_id)
    return RedirectResponse(f"/tg_account/chat?conv_id={conv_id}", 303)


@app.post("/tg_account/delete")
async def tg_account_delete(request: Request, conv_id: int = Form(...)):
    user, err = require_auth(request, role="admin")
    if err: return JSONResponse({"error": "unauthorized"}, 401)
    db.delete_tg_account_conversation(conv_id)
    return JSONResponse({"ok": True})


@app.get("/api/tg_account_messages/{conv_id}")
async def api_tg_account_messages(request: Request, conv_id: int, after: int = 0):
    user, err = require_auth(request)
    if err: return JSONResponse({"error": "unauthorized"}, 401)
    msgs = db.get_new_tg_account_messages(conv_id, after)
    return JSONResponse({"messages": msgs})


@app.get("/api/tga_chat_panel", response_class=HTMLResponse)
async def api_tga_chat_panel(request: Request, conv_id: int = 0, status_filter: str = "open"):
    """SPA: возвращает только HTML правой панели TGA чата"""
    user, err = require_auth(request)
    if err: return HTMLResponse("<div style='padding:20px;color:var(--red)'>Нет доступа</div>", 401)
    if not conv_id:
        return HTMLResponse('<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text3);font-size:.9rem">Выберите диалог</div>')
    # Переиспользуем логику из tg_account_chat_page — только active_conv часть
    tg_status = db.get_setting("tg_account_status", "disconnected")
    active_conv = db.get_tg_account_conversation(conv_id)
    if not active_conv:
        return HTMLResponse('<div style="padding:20px;color:var(--text3)">Диалог не найден</div>')
    db.mark_tg_account_conv_read(conv_id)
    msgs = db.get_tg_account_messages(conv_id)
    messages_html = ""
    for m in msgs:
        t = m["created_at"][11:16]
        if m.get("media_url") and (m.get("media_type") or "").startswith("image/"):
            ch = f'<img src="{m["media_url"]}" style="max-width:220px;max-height:220px;border-radius:8px;display:block;cursor:pointer" onclick="window.open(this.src)" />'
        elif m.get("media_url"):
            ch = f'<a href="{m["media_url"]}" target="_blank" style="color:#60a5fa">📎 Открыть файл</a>'
        else:
            ch = (m["content"] or "").replace("<", "&lt;")
        sl = f'<div style="font-size:.68rem;color:var(--orange);margin-bottom:2px;text-align:right;opacity:.8">{m["sender_name"]}</div>' if m.get("sender_name") and m["sender_type"] == "manager" else ""
        messages_html += f'<div class="msg {m["sender_type"]}" data-id="{m["id"]}">{sl}<div class="msg-bubble">{ch}</div><div class="msg-time">{t}</div></div>'
    uname = f"@{active_conv['username']}" if active_conv.get("username") else active_conv.get("tg_user_id", "")
    tga_staff = db.get_staff_by_tg_account_conv(conv_id)
    if tga_staff:
        tga_card_link = f'<a href="/staff?edit={tga_staff["id"]}" style="display:inline-flex;align-items:center;gap:4px;background:#052e16;color:#86efac;border:1px solid #166534;border-radius:6px;padding:2px 8px;font-size:.73rem;text-decoration:none">✅ В базе · {tga_staff.get("name","") or "Карточка"} →</a>'
    else:
        tga_card_link = f'<a href="/staff/create_from_tga?conv_id={conv_id}" style="display:inline-flex;align-items:center;gap:4px;background:var(--bg3);color:var(--text3);border:1px solid var(--border);border-radius:6px;padding:2px 8px;font-size:.73rem;text-decoration:none">+ Создать карточку</a>'
    all_tags     = db.get_all_tags()
    active_ctags = db.get_conv_tags("tga", conv_id)
    active_tag_ids = {tg["id"] for tg in active_ctags}
    tga_tags_html = _render_conv_tags_picker(active_ctags, all_tags, active_tag_ids, "tga", conv_id)
    fb_sent = active_conv.get("fb_event_sent")
    lead_btn = '<span class="badge-green">✅ Lead отправлен</span>' if fb_sent else \
               f'<form method="post" action="/tg_account/send_lead" style="display:inline"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn btn-sm" style="font-size:.73rem;background:#1e3a5f;border:1px solid #3b5998;color:#93c5fd">📤 Lead → FB</button></form>'
    status_color = "#34d399" if active_conv["status"] == "open" else "#ef4444"
    close_btn = f'<form method="post" action="/tg_account/close"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-gray btn-sm">✓ Закрыть</button></form>' if active_conv["status"] == "open" else \
                f'<form method="post" action="/tg_account/reopen"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-orange btn-sm">↺ Открыть</button></form>'
    delete_btn = f'<button class="btn-gray btn-sm" style="color:#fff;background:#7f1d1d;border-color:#7f1d1d;font-size:.78rem;padding:5px 10px" onclick="deleteTgAccConv({conv_id})" title="Удалить диалог">🗑 Удалить</button>' if user and user.get("role") == "admin" else ""
    call_url = f"https://t.me/{active_conv['username']}" if active_conv.get("username") else f"tg://user?id={active_conv.get('tg_user_id','')}"
    tags = []
    if active_conv.get("fbclid"): tags.append('<span class="utm-tag" style="background:#1e3a5f;color:#60a5fa">🔵 Facebook</span>')
    if active_conv.get("utm_campaign"): tags.append(f'<span class="utm-tag">🎯 {active_conv["utm_campaign"][:25]}</span>')
    if active_conv.get("utm_content"): tags.append(f'<span class="utm-tag" style="background:#1a2a1a;color:#86efac">📌 {active_conv["utm_content"][:20]}</span>')
    if active_conv.get("utm_term"): tags.append(f'<span class="utm-tag" style="background:#1a1a2a;color:#a5b4fc">📂 {active_conv["utm_term"][:20]}</span>')
    if active_conv.get("fbclid"): tags.append('<span class="utm-tag badge-green">fbclid ✓</span>')
    utm_tags = '<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:6px">' + "".join(tags) + '</div>' if tags else ""
    _tga_photo = active_conv.get("photo_url") or ""
    if _tga_photo:
        _tga_avatar = '<div class="tga-avatar-wrap"><img src="' + _tga_photo + '" style="width:42px;height:42px;border-radius:50%;object-fit:cover;border:2px solid var(--orange)" /><div class="tga-avatar-zoom"><img src="' + _tga_photo + '" /></div></div>'
    else:
        _tga_avatar = '<div class="avatar">T</div>'
    return HTMLResponse(f"""
    <div class="chat-header">
      <div style="display:flex;align-items:flex-start;gap:12px;flex:1">
        {_tga_avatar}
        <div style="flex:1">
          <div style="font-weight:700;color:var(--text)">{active_conv['visitor_name']} <span style="color:{status_color};font-size:.72rem">●</span></div>
          <div style="font-size:.78rem;color:var(--text3)">{uname} · {tga_card_link}</div>
          <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:6px;align-items:center">
            {lead_btn}
            <a href="{call_url}" target="_blank" class="btn-gray btn-sm" style="display:inline-flex;align-items:center;gap:4px;padding:5px 10px;border-radius:7px;font-size:.74rem;border:1px solid var(--border);text-decoration:none">📞 Открыть в TG</a>
          </div>
          {utm_tags}{tga_tags_html}
        </div>
      </div>
      <div style="display:flex;gap:6px;flex-shrink:0">{close_btn} {delete_btn}</div>
    </div>
    <div class="chat-messages" id="tga-msgs">{messages_html}</div>
    <div id="tga-send-error" style="display:none;padding:8px 18px;background:#2d0a0a;border-top:1px solid #7f1d1d;font-size:.8rem;color:#fca5a5;align-items:center;justify-content:space-between;gap:8px">
      <span id="tga-send-error-text"></span>
      <button onclick="document.getElementById('tga-send-error').style.display='none'" style="background:none;border:none;color:#fca5a5;cursor:pointer;font-size:1rem">✕</button>
    </div>
    <div class="chat-input">
      <div id="tga-disconnected-banner" style="display:{'none' if tg_status == 'connected' else 'flex'};align-items:center;justify-content:space-between;padding:8px 12px;background:#1c1a00;border:1px solid #713f12;border-radius:8px;margin-bottom:8px;font-size:.8rem;color:#fde047;gap:8px">
        <span>⚠️ TG аккаунт не подключён — сообщения не будут доставлены</span>
        <a href="/tg_account/setup" style="color:#fde047;font-weight:600;white-space:nowrap;text-decoration:underline">Подключить →</a>
      </div>
      <div class="chat-input-row">
        <div style="position:relative;flex:1">
          <textarea id="tga-inp" placeholder="Написать в Telegram... (Enter — отправить)"
            style="width:100%;resize:none;background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:10px 44px 10px 14px;color:var(--text);font-size:.9rem;font-family:inherit;min-height:44px;max-height:120px"
            rows="1" onkeydown="if(event.key==='Enter'&&!event.shiftKey){{event.preventDefault();sendTgAccMsg()}}"></textarea>
          <label style="position:absolute;right:10px;bottom:10px;cursor:pointer;opacity:.6">
            📎<input type="file" id="tga-file" style="display:none" onchange="sendTgAccFile(this)"/>
          </label>
        </div>
        <button class="btn-orange" onclick="sendTgAccMsg()" style="height:44px;padding:0 18px;flex-shrink:0">Отправить</button>
      </div>
    </div>
    <script>
    var TGA_CONV_ID={conv_id};
    var TGA_SF='{status_filter}';
    var tgaMsgBox=document.getElementById('tga-msgs');
    if(tgaMsgBox) tgaMsgBox.scrollTop=tgaMsgBox.scrollHeight;
    var lastTgAId=(function(){{var m=document.querySelectorAll('#tga-msgs .msg[data-id]');return m.length?m[m.length-1].dataset.id:0;}})();
    </script>""")


@app.get("/api/tg_account_convs")
async def api_tg_account_convs(request: Request, status: str = "open"):
    """Список TG диалогов для авто-обновления"""
    user = check_session(request)
    if not user: return JSONResponse({"error": "unauthorized"}, 401)
    # Фильтруем по статусу как на странице
    status_arg = status if status != "all" else None
    convs = db.get_tg_account_conversations(status=status_arg)
    tga_in_staff = db.get_tga_conv_ids_in_staff()
    return JSONResponse({"convs": [
        {
            "id": c["id"],
            "visitor_name": c.get("visitor_name") or c.get("username") or str(c.get("tg_user_id", "")),
            "username": c.get("username") or "",
            "last_message": c.get("last_message") or "",
            "last_message_at": (c.get("last_message_at") or c["created_at"])[:16].replace("T", " "),
            "unread_count": c.get("unread_count", 0),
            "status": c.get("status", "open"),
            "utm_campaign": c.get("utm_campaign") or "",
            "utm_content":  c.get("utm_content") or "",
            "utm_term":     c.get("utm_term") or "",
            "utm_source":   c.get("utm_source") or "",
            "fbclid":       bool(c.get("fbclid")),
            "in_staff":     bool(tga_in_staff.get(c["id"])),
        } for c in convs
    ]})
