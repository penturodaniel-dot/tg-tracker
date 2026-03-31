
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
import tiktok_capi
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
from routers.chat_wa     import router as wa_router,       setup as wa_setup
from routers.chat_tga    import router as tga_router,      setup as tga_setup
from routers.analytics   import router as analytics_router, setup as analytics_setup
from routers.staff       import router as staff_router,     setup as staff_setup
from routers.users_tags  import router as users_tags_router, setup as users_tags_setup
from routers.settings    import router as settings_router,  setup as settings_setup
from routers.channels    import router as channels_router,  setup as channels_setup
from routers.autopost    import router as autopost_router,  setup as autopost_setup, start_scheduler as autopost_start_scheduler
from routers.projects    import router as projects_router,  setup as projects_setup
from routers.scripts     import router as scripts_router,   setup as scripts_setup

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
    await bot_manager.start_autopost_bot(db.get_setting("bot3_token") or "")
    # Запускаем шедулер автопостинга как фоновый task
    import asyncio as _asyncio
    from routers.autopost import scheduler_loop as _autopost_scheduler_loop
    async def _keep_scheduler():
        """Перезапускает шедулер если он упал"""
        while True:
            try:
                print("[Autopost] Scheduler starting...", flush=True)
                await _autopost_scheduler_loop()
            except _asyncio.CancelledError:
                break
            except Exception as ex:
                print(f"[Autopost] Scheduler crashed: {ex}, restarting in 60s", flush=True)
                await _asyncio.sleep(60)
    _sched_task = _asyncio.create_task(_keep_scheduler())
    print("[Autopost] Scheduler task created", flush=True)
    yield
    _sched_task.cancel()
    try: await _sched_task
    except: pass
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
                    # Пиксель из проекта лендинга или глобальный
                    _pid = landing.get("project_id")
                    if _pid:
                        _proj = db.get_project(int(_pid))
                        pixel_staff = (_proj.get("fb_pixel_id") if _proj else None) or db.get_setting("pixel_id_staff", "") or db.get_setting("pixel_id", "")
                    else:
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
                            # fbc генерируем в момент клика
                            _fbc_mid = None
                            if fbclid:
                                import time as _time_mid
                                _fbc_mid = f"fb.1.{int(_time_mid.time()*1000)}.{fbclid}"
                            db.save_staff_click(
                                ref_id, c["url"], c_type, landing["slug"],
                                fbclid=fbclid, fbp=cookie_fbp, fbc=_fbc_mid,
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
.conv-list{background:var(--bg2);border-right:1px solid var(--border);overflow:hidden;display:flex;flex-direction:column}
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
.chat-window{display:flex;flex-direction:column;overflow:hidden}
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
.utm-tag{background:#0c1e38;border:1px solid #1e3a5f;border-radius:4px;padding:2px 8px;font-size:.72rem;color:#7dd3fc;font-family:inherit;font-weight:500}
.source-badge{display:inline-flex;align-items:center;padding:2px 8px;border-radius:4px;font-size:.72rem;font-weight:600;white-space:nowrap;border:1px solid transparent}
.source-fb{background:#1e3a5f;color:#60a5fa;border-color:#1e3a5f}
.source-organic{background:var(--bg3);color:var(--text3);border-color:var(--border)}
.source-tg{background:#0d2137;color:#7dd3fc;border-color:#1e3a5f}

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
    wa_unread  = stats.get("wa_unread", 0)
    tga_unread = stats.get("tga_unread", 0)
    b2 = bot_manager.get_staff_bot()
    b2_name = db.get_setting("bot2_name", "Уведомления")
    wa_status  = db.get_setting("wa_status", "disconnected")
    role = user["role"] if user else "manager"

    perms_str = (user.get("permissions", "") or "") if user else ""
    allowed_tabs = [p.strip() for p in perms_str.split(",") if p.strip()]
    def can(tab):
        if role == "admin": return True
        # backward compat: старое "chat" разрешает tg_account_chat
        effective = set(allowed_tabs)
        if "chat" in effective: effective.add("tg_account_chat")
        return not effective or tab in effective

    def item(icon, label, page, section_color="blue", badge_count=0, url=None, badge_id=None):
        if not can(page): return ""
        href = url or f"/{page}"
        act  = page == active or (url and url.strip("/") == active)
        cls  = f"nav-item active {section_color}" if act else "nav-item"
        bid  = f' id="{badge_id}"' if badge_id else ""
        hide = ' style="display:none"' if badge_count == 0 else ""
        bdg  = f'<span class="badge-count"{bid}{hide}>{badge_count if badge_count else ""}</span>'
        return f'<a href="{href}"><div class="{cls}"><span class="nav-label">{icon} {label}</span>{bdg}</div></a>'

    # Определяем какой аккордеон активен
    clients_pages  = ["channels","campaigns","landings","analytics_clients"]
    staff_pages    = ["tg_account_chat","wa_chat","staff","scripts","landings_staff","analytics_staff"]
    settings_pages = ["tags","users","projects","settings"]
    is_clients  = active in clients_pages or (active and any(active.startswith(p) for p in clients_pages))
    is_staff    = active in staff_pages   or (active and any(active.startswith(p) for p in staff_pages))
    is_settings = active in settings_pages

    # Аккордеон-секция
    def accordion(section_id, icon, title, color, items_html, open_by_default=False):
        is_open = open_by_default
        arrow_style = "transform:rotate(0deg)" if is_open else "transform:rotate(-90deg)"
        body_style  = "" if is_open else "display:none"
        return f"""
        <div class="acc-section" id="acc-{section_id}">
          <div class="acc-header" onclick="toggleAcc('{section_id}')" style="display:flex;align-items:center;justify-content:space-between;padding:8px 12px 6px;cursor:pointer;user-select:none">
            <span style="font-size:.65rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--text3)">{icon} {title}</span>
            <span id="acc-arrow-{section_id}" style="font-size:.6rem;color:var(--text3);transition:transform .2s;{arrow_style}">▼</span>
          </div>
          <div id="acc-body-{section_id}" style="{body_style}">{items_html}</div>
        </div>"""

    # Блок Клиенты
    clients_items = (
        item("📡", "Каналы",      "channels",          "blue") +
        item("🔗", "Кампании",    "campaigns",         "blue") +
        item("📣", "Автопостинг", "autopost",           "blue", url="/autopost") +
        item("📝", "Шаблоны постов", "autopost_tpl",  "blue", url="/autopost/templates") +
        item("🎨", "Шаблоны",     "landings",          "blue") +
        item("📈", "Статистика",  "analytics_clients", "blue", url="/analytics/clients")
    )
    show_clients = bool(clients_items.strip())  # скрываем если все пункты недоступны

    # Блок Сотрудники
    staff_items = (
        item("📱", "TG Чаты",     "tg_account_chat", "orange", badge_count=tga_unread, url="/tg_account/chat", badge_id="nav-tga-badge") +
        item("💚", "WA Чаты",     "wa_chat",         "orange", badge_count=wa_unread,  url="/wa/chat",         badge_id="nav-wa-badge") +
        item("🗂",  "База",        "staff",            "orange") +
        item("💰", "Бонусы",      "staff_bonuses",    "orange", url="/staff/bonuses") +
        item("📝", "Скрипты",     "scripts",          "orange", url="/scripts") +
        item("🌐", "Лендинги HR", "landings_staff",   "orange") +
        item("📊", "Статистика",  "analytics_staff",  "orange", url="/analytics/staff")
    )

    # Блок Настройки (только admin)
    settings_items = ""
    if role == "admin":
        settings_items = (
            item("🏷️", "Теги",         "tags",      "blue") +
            item("🔐", "Пользователи", "users",     "blue") +
            item("🎯", "Проекты",      "projects",  "blue") +
            item("⚙️", "Настройки",   "settings",  "blue")
        )

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

      {accordion("clients",  "📋", "Клиенты",     "blue",   clients_items,  open_by_default=is_clients) if show_clients else ""}
      <div class="nav-divider"></div>
      {accordion("staff",    "👥", "Сотрудники",  "orange", staff_items,    open_by_default=True)}
      {'<div class="nav-divider"></div>' + accordion("settings", "⚙️", "Настройки", "blue", settings_items, open_by_default=is_settings) if role == "admin" and settings_items else ''}

      <div class="sidebar-footer">
        <div class="bot-status"><div class="dot {'dot-green' if b2 else 'dot-red'}"></div><span>{b2_name}</span></div>
        <div class="bot-status"><div class="dot {wa_dot}"></div><span id="nav-wa-status">WhatsApp {'✓' if wa_status == 'ready' else ('QR...' if wa_status == 'qr' else '✗')}</span></div>
        <div class="bot-status"><div class="dot {'dot-green' if db.get_setting('tg_account_status') == 'connected' else 'dot-red'}" id="nav-tg-dot"></div><span id="nav-tg-status">TG {'✓' if db.get_setting('tg_account_status') == 'connected' else '✗'}</span></div>
        <a href="/logout"><div style="padding:6px 8px;margin-top:4px;font-size:.73rem;color:var(--text3);cursor:pointer;border-radius:6px;transition:color .12s" onmouseover="this.style.color='var(--text)'" onmouseout="this.style.color='var(--text3)'">⬅ Выйти</div></a>
      </div>
    </div>
    <div id="toast-container"></div>
    <script>
    function toggleAcc(id){{
      var body  = document.getElementById('acc-body-' + id);
      var arrow = document.getElementById('acc-arrow-' + id);
      if(!body) return;
      var isOpen = body.style.display !== 'none';
      body.style.display  = isOpen ? 'none' : '';
      if(arrow) arrow.style.transform = isOpen ? 'rotate(-90deg)' : 'rotate(0deg)';
      try{{ localStorage.setItem('acc_' + id, isOpen ? '0' : '1'); }}catch(e){{}}
    }}
    // Восстанавливаем состояние аккордеонов из localStorage
    (function(){{
      ['clients','settings'].forEach(function(id){{
        var saved = localStorage.getItem('acc_' + id);
        if(saved === null) return; // не трогаем — управляется сервером
        var body  = document.getElementById('acc-body-' + id);
        var arrow = document.getElementById('acc-arrow-' + id);
        if(!body) return;
        var open = saved === '1';
        body.style.display  = open ? '' : 'none';
        if(arrow) arrow.style.transform = open ? 'rotate(0deg)' : 'rotate(-90deg)';
      }});
    }})();
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
    let _lastWaUnread = {wa_unread}, _lastTgaUnread = {tga_unread};
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
        updateBadge('nav-wa-badge', d.wa_unread || 0);
        updateBadge('nav-tga-badge', d.tga_unread || 0);
        if(d.wa_unread > _lastWaUnread) showToast('💚 Новое сообщение', 'WhatsApp чаты', 'wa-toast', '/wa/chat');
        if(d.tga_unread > _lastTgaUnread) showToast('📱 Новое сообщение', 'TG Чаты', 'tga-toast', '/tg_account/chat');
        _lastWaUnread = d.wa_unread || 0; _lastTgaUnread = d.tga_unread || 0;
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
    </script>
"""

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
    </script>
</script>
</body></html>'''


STAFF_STATUSES = {
    "new":         ("🆕", "Новый",          "badge-gray"),
    "review":      ("👀", "Инструктаж",      "badge-yellow"),
    "interview":   ("🔍", "Верификация",     "badge"),
    "hired":       ("💼", "В работе",        "badge-green"),
    "rejected":    ("🚫", "Слив",            "badge-red"),
}

# ── Подключение роутеров ──────────────────────────────────────────────────────
analytics_setup(db, log, require_auth, base, nav_html, _render_conv_tags_picker)
app.include_router(analytics_router)

staff_setup(db, log, require_auth, base, nav_html, _render_conv_tags_picker, STAFF_STATUSES)
app.include_router(staff_router)

users_tags_setup(db, log, require_auth, base, nav_html, _render_conv_tags_picker, check_session)
app.include_router(users_tags_router)

settings_setup(db, log, require_auth, base, nav_html, _render_conv_tags_picker, bot_manager, SECRET)
app.include_router(settings_router)

channels_setup(db, log, require_auth, base, nav_html, _render_conv_tags_picker, bot_manager)
autopost_setup(db, log, require_auth, base, bot_manager=bot_manager)
app.include_router(channels_router)
app.include_router(autopost_router)

projects_setup(db, log, require_auth, base, nav_html, _render_conv_tags_picker)
app.include_router(projects_router)

scripts_setup(db, log, require_auth, base, nav_html, _render_conv_tags_picker)
app.include_router(scripts_router)

wa_setup(
    db, log, bot_manager, meta_capi,
    WA_URL, WA_SECRET, WA_WH_SECRET,
    TG_SVC_URL, TG_SVC_SECRET,
    check_session, require_auth, base, nav_html, _render_conv_tags_picker,
    _css=CSS,
    _tiktok_capi=tiktok_capi,
)
app.include_router(wa_router)

tga_setup(
    db, log, bot_manager, meta_capi,
    TG_WH_SECRET, TG_SVC_URL, TG_SVC_SECRET,
    check_session, require_auth, base, nav_html, _render_conv_tags_picker,
    _tiktok_capi=tiktok_capi,
)
app.include_router(tga_router)


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
    resp = RedirectResponse("/tg_account/chat", 303)
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
async def root_redirect(request: Request):
    return RedirectResponse("/tg_account/chat", 303)


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
      <div class="card c-orange"><div class="val orange">{s['staff']}</div><div class="lbl">Сотрудников</div></div>
    </div>

    <div class="section">
      <div class="section-head"><h3>Последние подписки</h3><span class="tag">Pixel: {pixel}</span></div>
      <table><thead><tr><th>Время</th><th>Канал</th><th>Кампания</th><th>UTM</th></tr></thead>
      <tbody>{rows}</tbody></table>
    </div></div>"""
    return HTMLResponse(base(content, "overview", request))


@app.get("/landings", response_class=HTMLResponse)
async def landings_client(request: Request, msg: str = ""):
    user, err = require_auth(request)
    if err: return err
    return HTMLResponse(base(_landings_page(ltype="client", active="landings", msg=msg, request=request), "landings", request))


@app.get("/landings_staff", response_class=HTMLResponse)
async def landings_staff_page(request: Request, msg: str = ""):
    user, err = require_auth(request)
    if err: return err
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""
    page_content = _landings_page(ltype="staff", active="landings_staff", msg=msg, request=request)
    return HTMLResponse(base(alert + page_content, "landings_staff", request))


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

    app_url_base = db.get_setting("app_url", "").rstrip("/")
    rows = ""
    for l in landings:
        import json as _json
        try:
            lcontent = _json.loads(l.get("content","{}"))
            tpl_name = {"dark_hr":"Dark Spa","light_clean":"Light Clean","bold_cta":"Bold Purple"}.get(lcontent.get("template","dark_hr"),"Dark Spa")
        except:
            tpl_name = "Dark Spa"
        slug_url = f"/l/{l['slug']}"
        full_url = f"{app_url_base}/l/{l['slug']}"
        _cdomain = l.get("custom_domain") or ""
        _domain_badge = f'<div style="margin-top:4px"><span style="font-family:monospace;font-size:.68rem;background:#052e16;color:#86efac;border:1px solid #166534;border-radius:4px;padding:1px 6px">🌐 {_cdomain}</span></div>' if _cdomain else ""

        # UTM ссылки
        _proj = db.get_project(int(l["project_id"])) if l.get("project_id") else None
        _utm_links_html = ""
        if _proj:
            _src = (_proj.get("traffic_source") or "").lower()
            _utms = [u.strip() for u in (_proj.get("utm_campaigns") or "").split(",") if u.strip()]
            _utm_val = _utms[0] if _utms else "campaign"
            _tt_u = full_url + "?utm_source=tiktok&utm_medium=paid&utm_campaign=" + _utm_val + "&utm_content=__CID__&utm_term=__AID__&ttclid=__CLICKID__"
            _fb_u = full_url + "?utm_source=facebook&utm_medium=paid&utm_campaign=" + _utm_val + "&utm_content={ad.name}&utm_term={adset.name}&fbclid={fbclid}"
            _tt_row = ("<div style=\"margin-top:3px;display:flex;gap:3px\">"
                + "<span style=\"color:#69c9d0;font-size:.65rem\">🎵</span>"
                + "<input readonly value=\"" + _tt_u + "\" onclick=\"this.select()\""
                + " style=\"flex:1;min-width:0;background:var(--bg);border:1px solid #2a2a4a;border-radius:4px;padding:2px 5px;color:#69c9d0;font-size:.6rem;font-family:monospace\"/>"
                + "<button onclick=\"navigator.clipboard.writeText(this.previousElementSibling.value);this.textContent='✓'\""
                + " style=\"padding:1px 5px;background:#1a1a2a;color:#69c9d0;border:1px solid #2a2a4a;border-radius:4px;cursor:pointer;font-size:.65rem\">📋</button></div>")
            _fb_row = ("<div style=\"margin-top:3px;display:flex;gap:3px\">"
                + "<span style=\"color:#60a5fa;font-size:.65rem\">🔵</span>"
                + "<input readonly value=\"" + _fb_u + "\" onclick=\"this.select()\""
                + " style=\"flex:1;min-width:0;background:var(--bg);border:1px solid #1e3a5f;border-radius:4px;padding:2px 5px;color:#60a5fa;font-size:.6rem;font-family:monospace\"/>"
                + "<button onclick=\"navigator.clipboard.writeText(this.previousElementSibling.value);this.textContent='✓'\""
                + " style=\"padding:1px 5px;background:#1e3a5f;color:#60a5fa;border:1px solid #3b5998;border-radius:4px;cursor:pointer;font-size:.65rem\">📋</button></div>")
            if _src == "tiktok": _utm_links_html = _tt_row
            elif _src == "facebook": _utm_links_html = _fb_row
            else: _utm_links_html = _tt_row + _fb_row
        rows += f"""<tr>
          <td><b>{l['name']}</b>{_domain_badge}</td>
          <td><span class="badge-gray" style="font-size:.68rem">{tpl_name}</span></td>
          <td><a href="{slug_url}" target="_blank" class="link-box" style="display:inline-block">{slug_url}</a>{_utm_links_html}</td>
          <td><span class="{'badge-green' if l['active'] else 'badge-gray'}">{'Активен' if l['active'] else 'Скрыт'}</span></td>
          <td>
            <a href="/landings/edit?id={l['id']}" class="btn-gray btn-sm">✏️ Редакт.</a>
            <button onclick="copyLanding({l['id']},'{l['name']}')" class="btn-gray btn-sm" style="background:#1a2a1a;border-color:#166534;color:#86efac">📋 Копия</button>
            <form method="post" action="/landings/delete" style="display:inline"><input type="hidden" name="id" value="{l['id']}"/><button class="del-btn btn-sm">✕</button></form>
          </td></tr>"""
    rows = rows or f'<tr><td colspan="5"><div class="empty">Нет шаблонов — создай первый</div></td></tr>'

    tpl_th = '<th>Шаблон</th>' if ltype == "staff" else ""

    _copy_modal = '''<div id="copy-landing-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:1000;align-items:center;justify-content:center">
      <div style="background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:24px;min-width:320px;max-width:400px">
        <div style="font-weight:700;margin-bottom:16px">📋 Копировать лендинг</div>
        <div style="margin-bottom:10px"><label style="font-size:.8rem;color:var(--text3)">Название новой копии</label>
          <input id="copy-name" type="text" style="width:100%;margin-top:4px;background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:8px 10px;color:var(--text)"/></div>
        <div style="margin-bottom:16px"><label style="font-size:.8rem;color:var(--text3)">Slug (url)</label>
          <input id="copy-slug" type="text" style="width:100%;margin-top:4px;background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:8px 10px;color:var(--text)"/></div>
        <div style="display:flex;gap:8px">
          <button onclick="submitCopyLanding()" style="flex:1;padding:9px;background:var(--orange);color:#fff;border:none;border-radius:7px;font-weight:600;cursor:pointer">Создать копию</button>
          <button onclick="document.getElementById('copy-landing-modal').style.display='none'" style="padding:9px 16px;background:var(--bg3);color:var(--text);border:1px solid var(--border);border-radius:7px;cursor:pointer">Отмена</button>
        </div>
      </div>
    </div>
    <script>
    var _copyLandingId=0;
    function copyLanding(id,name){_copyLandingId=id;document.getElementById('copy-name').value=name+' (копия)';document.getElementById('copy-slug').value='';document.getElementById('copy-landing-modal').style.display='flex';}
    function submitCopyLanding(){var n=document.getElementById('copy-name').value.trim();var s=document.getElementById('copy-slug').value.trim();if(!n||!s){alert('Заполни название и slug');return;}
    fetch('/landings/copy',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:_copyLandingId,name:n,slug:s})})
    .then(r=>r.json()).then(d=>{if(d.ok){window.location.reload();}else{alert(d.error||'Ошибка');}});}
    </script>'''
    return (f"""<div class="page-wrap"><div class="page-title">{title}</div>
    <div class="page-sub">{sub}</div>""" + _copy_modal + f"""{alert}
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
    <tbody>{rows}</tbody></table></div></div>""")


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


@app.post("/landings/copy")
async def landings_copy(request: Request):
    user = check_session(request)
    if not user: return JSONResponse({"error": "unauthorized"}, 401)
    try:
        data = await request.json()
        landing_id = int(data.get("id", 0))
        new_name = data.get("name", "").strip()
        new_slug = data.get("slug", "").strip()
        if not landing_id or not new_name or not new_slug:
            return JSONResponse({"ok": False, "error": "Не заполнены поля"})
        # Проверяем что slug не занят
        existing = db.get_landing_by_slug(new_slug)
        if existing:
            return JSONResponse({"ok": False, "error": f"Slug '{new_slug}' уже занят"})
        new_id = db.copy_landing(landing_id, new_name, new_slug)
        return JSONResponse({"ok": True, "id": new_id})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


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

        # Поля заголовков секций и попапа (только tiktok_spa)
        _tt_extra_fields = ""
        _tt_extra_btn = ""
        _tt_extra_div = ""
        if cur_tpl == "tiktok_spa":
            _tt_extra_fields = (
                '<div style="font-size:.78rem;font-weight:600;color:var(--text2);margin:8px 0 6px">Заголовки секций</div>' +
                _tf("sec_benefits_title", "Заголовок секции преимуществ", "Что ты получаешь") +
                _tf("sec_steps_title",    "Заголовок секции шагов",       "Как начать за 3 шага") +
                _tf("sec_reviews_title",  "Заголовок секции отзывов",     "Девушки о работе с нами") +
                '<div style="font-size:.78rem;font-weight:600;color:var(--text2);margin:12px 0 6px">Попап выбора мессенджера</div>' +
                _tf("popup_title",    "Заголовок попапа",    "Выберите мессенджер") +
                _tf("popup_subtitle", "Подзаголовок попапа", "Мы ответим в течение 5 минут ⚡")
            )
            _tt_extra_btn = _tab_btn("ttextra", "🎵 Попап")
            _tt_extra_div = _tab_div("ttextra", _tt_extra_fields)
        _texts_fields = f"""
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:4px">
          {_tab_btn("hero",  "🎯 Герой",        True)}
          {_tab_btn("ben",   "✨ Преимущества")}
          {_step_btn}
          {_tab_btn("rev",   "⭐ Отзывы")}
          {_tab_btn("faq",   "❓ FAQ")}
          {_tab_btn("cta",   "🔔 CTA")}
          {''+_tab_btn("trust","🔢 Цифры") if _trust_fields else ''}
          {_tt_extra_btn}
        </div>
        {_tab_div("hero",  _hero_fields,  True)}
        {_tab_div("ben",   _ben_fields)}
        {_step_div}
        {_tab_div("rev",   _rev_fields)}
        {_tab_div("faq",   _faq_fields)}
        {_tab_div("cta",   _cta_fields)}
        {_tab_div("trust", _trust_fields) if _trust_fields else ''}
        {_tt_extra_div}
        <script>
        function showTab(id) {{
          ['hero','ben','steps','rev','faq','cta','trust','ttextra'].forEach(function(t) {{
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

    # Блок привязки проекта
    projects = db.get_projects()
    cur_project_id = landing.get("project_id")
    proj_opts = '<option value="">— Глобальные пиксели (из Настроек) —</option>'
    for p in projects:
        sel = " selected" if cur_project_id and int(cur_project_id) == p["id"] else ""
        fb_ok = "✓ FB" if p.get("fb_pixel_id") else "✗ FB"
        tt_ok = "✓ TT" if p.get("tt_pixel_id") else ""
        badges = f" [{fb_ok}{', ' + tt_ok if tt_ok else ''}]"
        proj_opts += f'<option value="{p["id"]}"{sel}>{p["name"]}{badges}</option>'
    cur_proj_name = next((p["name"] for p in projects if cur_project_id and int(cur_project_id) == p["id"]), None)
    proj_status = f'<span style="color:#34d399;font-size:.8rem">● {cur_proj_name}</span>' if cur_proj_name else '<span style="color:var(--text3);font-size:.8rem">глобальные пиксели</span>'

    project_block = f"""
    <div class="section" style="border-left:3px solid #6366f1">
      <div class="section-head"><h3>🎯 Проект (пиксели)</h3>{proj_status}</div>
      <div class="section-body">
        <form method="post" action="/landings/set_project" style="display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap">
          <input type="hidden" name="landing_id" value="{id}"/>
          <div class="field-group" style="flex:1;min-width:220px">
            <div class="field-label">Привязать к проекту</div>
            <select name="project_id">{proj_opts}</select>
          </div>
          <button class="btn">💾 Сохранить</button>
        </form>
        <div style="margin-top:8px;font-size:.76rem;color:var(--text3)">
          Пиксель этого проекта будет использоваться на лендинге и при отправке Lead из чата
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
    {project_block}
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


@app.post("/landings/set_project")
async def landings_set_project(request: Request, landing_id: int = Form(...), project_id: str = Form("")):
    user, err = require_auth(request)
    if err: return err
    pid = int(project_id) if project_id.strip() else None
    db.set_landing_project(landing_id, pid)
    msg = "Проект привязан" if pid else "Проект отвязан"
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
                          utm_content: str = None, utm_term: str = None,
                          ttclid: str = None, tt_test_id: str = None):
    # Глобальные пиксели (fallback)
    pixel_clients = db.get_setting("pixel_id_clients") or db.get_setting("pixel_id", "")
    pixel_staff   = db.get_setting("pixel_id_staff", "")
    app_url       = db.get_setting("app_url", "").rstrip("/")

    # fbp из cookie
    cookie_fbp = request.cookies.get("_fbp", "")

    def _get_landing_pixels(landing: dict) -> tuple:
        """Возвращает (fb_pixel, tt_pixel) для лендинга — из проекта или глобальные."""
        pid = landing.get("project_id")
        if pid:
            project = db.get_project(int(pid))
            if project:
                fb = project.get("fb_pixel_id") or pixel_clients
                tt = project.get("tt_pixel_id") or db.get_setting("tiktok_pixel_id", "") or ""
                return fb, tt
        return pixel_clients, db.get_setting("tiktok_pixel_id", "") or ""

    # Ищем как Campaign slug
    campaign = db.get_campaign_by_slug(slug)
    if campaign:
        channels = db.get_campaign_channels(campaign["id"])

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
                fb_pixel, tt_pixel = _get_landing_pixels(landing)
                return HTMLResponse(_render_client_landing(landing, chan_contacts, pixel_id=fb_pixel, tt_pixel=tt_pixel, db=db))

        tt_pixel = db.get_setting("tiktok_pixel_id", "") or ""
        return HTMLResponse(_render_campaign_landing(campaign, btns, pixel_clients, fbclid, tt_pixel))

    # Staff Landing slug
    landing = db.get_landing_by_slug(slug)
    if not landing: return HTMLResponse("<h2>Not found</h2>", 404)

    # Пиксели из проекта лендинга или глобальные
    fb_pixel_staff, tt_pixel_staff = _get_landing_pixels(landing)
    # Для staff лендингов — приоритет pixel_staff если нет проекта
    if not landing.get("project_id"):
        fb_pixel_staff = pixel_staff or pixel_clients

    # Строим /go-staff ссылки — с UTM трекингом
    raw_contacts = db.get_landing_contacts(landing["id"])
    utm_params = dict(
        fbclid=fbclid, fbp=cookie_fbp,
        utm_source=utm_source or "",
        utm_medium=utm_medium or "",
        utm_campaign=utm_campaign or "",
        utm_content=utm_content or "",
        utm_term=utm_term or "",
        landing_slug=slug,
    )
    # TikTok click ID — для CAPI matching
    _ttclid = ttclid or request.query_params.get("ttclid", "")
    _ttp = request.cookies.get("_ttp", "")
    tracked_contacts = []
    for c in raw_contacts:
        if c.get("url"):
            import urllib.parse as _up
            ref_id = __import__("secrets").token_urlsafe(10)
            c_type = c.get("type", "")
            if not c_type:
                if "wa.me" in c["url"] or "whatsapp" in c["url"].lower():
                    c_type = "whatsapp"
                elif "t.me" in c["url"] or "telegram" in c["url"].lower():
                    c_type = "telegram"
            # fbc = fb.1.{timestamp_клика}.{fbclid} — генерируем в момент клика
            _fbc = None
            if utm_params.get("fbclid"):
                import time as _time
                _fbc = f"fb.1.{int(_time.time()*1000)}.{utm_params['fbclid']}"
            db.save_staff_click(ref_id, c["url"], c_type, slug,
                fbc=_fbc, ttclid=_ttclid, ttp=_ttp,
                **{k:v for k,v in utm_params.items() if k!='landing_slug'})
            go_url = f"{app_url}/go-staff?ref={ref_id}"
            tracked_contacts.append({**c, "url": go_url, "type": c_type})
        else:
            tracked_contacts.append(c)

    return HTMLResponse(_render_staff_landing(landing, tracked_contacts, pixel_id=fb_pixel_staff, tt_pixel=tt_pixel_staff, db=db))


@app.get("/go-staff")
async def go_staff_redirect(request: Request, ref: str = ""):
    """Редирект с HR лендинга — сохраняет UTM и добавляет ref код в WA/TG ссылку"""
    if not ref:
        return HTMLResponse("<h2>Invalid link</h2>", 400)

    click = db.get_staff_click(ref)
    if not click:
        return HTMLResponse("<h2>Link expired</h2>", 404)

    # Читаем fbp из cookie — к этому моменту пиксель уже успел его установить
    cookie_fbp = request.cookies.get("_fbp", "")
    if cookie_fbp and not click.get("fbp"):
        try:
            with db._conn() as _conn:
                with _conn.cursor() as _cur:
                    _cur.execute("UPDATE staff_clicks SET fbp=%s WHERE ref_id=%s", (cookie_fbp, ref))
                _conn.commit()
            log.info(f"[/go-staff] fbp сохранён для ref={ref}")
        except Exception as _e:
            log.warning(f"[/go-staff] fbp update error: {_e}")

    target_url = click.get("target_url", "")
    target_type = click.get("target_type", "wa")

    # Добавляем ref код в ссылку — точный матчинг клика к пользователю
    destination = target_url
    if target_type == "telegram" or "t.me" in target_url:
        # t.me/username?start=ref_XXX — Telethon передаёт это как первое сообщение
        sep = "&" if "?" in target_url else "?"
        destination = f"{target_url}{sep}start=ref_{ref}"
    elif target_type == "whatsapp" or "wa.me" in target_url:
        # wa.me/number?text=ref:XXX — предзаполненный текст, парсится в WA webhook
        import urllib.parse as _urlparse
        sep = "&" if "?" in target_url else "?"
        pre_text = _urlparse.quote(f"ref:{ref} Приветствую! Я по поводу работы. Увидела ваше объявление, подскажите, пожалуйста, какие условия работы?")
        destination = f"{target_url}{sep}text={pre_text}"

    log.info(f"[/go-staff] ref={ref} type={target_type} src={click.get('utm_source')} utm={click.get('utm_campaign')} fbclid={'✓' if click.get('fbclid') else '—'} ttclid={'✓' if click.get('ttclid') else '—'} ttp={'✓' if click.get('ttp') else '—'}")

    # TikTok CAPI — Subscribe событие при клике на кнопку лендинга
    try:
        _landing_slug = click.get('landing_slug', '')
        _landing_obj = db.get_landing_by_slug(_landing_slug) if _landing_slug else None
        _tt_pixel, _tt_token = '', ''
        if _landing_obj and _landing_obj.get('project_id'):
            _proj = db.get_project(int(_landing_obj['project_id']))
            if _proj:
                _tt_pixel = _proj.get('tt_pixel_id', '') or ''
                _tt_token = _proj.get('tt_token', '') or ''
        if not _tt_pixel:
            _tt_pixel = db.get_setting('tiktok_pixel_id', '') or ''
            _tt_token = db.get_setting('tt_access_token', '') or ''
        if _tt_pixel and _tt_token:
            import asyncio as _asyncio
            _app_url_tt = db.get_setting('app_url', '').rstrip('/')
            _asyncio.create_task(tiktok_capi.send_event(
                pixel_id=_tt_pixel,
                access_token=_tt_token,
                event_name='Subscribe',
                user_id=str(click.get('ref_id', '')),
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get('user-agent', ''),
                ttclid=click.get('ttclid') or '',
                ttp=click.get('ttp') or '',
                utm_source=click.get('utm_source') or '',
                utm_campaign=click.get('utm_campaign') or '',
                event_source_url=f"{_app_url_tt}/l/{_landing_slug}" if _landing_slug else '',
            ))
            log.info(f"[/go-staff] TT CAPI Subscribe queued pixel={_tt_pixel[:8]}...")
    except Exception as _tt_err:
        log.warning(f"[/go-staff] TT CAPI error: {_tt_err}")

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


@app.get("/api/stats")
async def api_stats(request: Request):
    user = check_session(request)
    if not user: return JSONResponse({"error": "unauthorized"}, 401)
    stats = db.get_stats()
    stats["wa_status"] = db.get_setting("wa_status", "disconnected")
    stats["tg_status"] = db.get_setting("tg_account_status", "disconnected")
    return JSONResponse(stats)


@app.get("/api/projects_list")
async def api_projects_list(request: Request):
    user = check_session(request)
    if not user: return JSONResponse({"error": "unauthorized"}, 401)
    projects = db.get_projects()
    return JSONResponse({"projects": [{"id": p["id"], "name": p["name"]} for p in projects]})


@app.get("/api/tga_conv_project")
async def api_tga_conv_project(request: Request, conv_id: int = 0):
    user = check_session(request)
    if not user: return JSONResponse({"error": "unauthorized"}, 401)
    if not conv_id: return JSONResponse({"project_id": 0})
    conv = db.get_tg_account_conversation(conv_id)
    return JSONResponse({"project_id": (conv or {}).get("project_id") or 0})


@app.get("/api/wa_conv_project")
async def api_wa_conv_project(request: Request, conv_id: int = 0):
    user = check_session(request)
    if not user: return JSONResponse({"error": "unauthorized"}, 401)
    if not conv_id: return JSONResponse({"project_id": 0})
    conv = db.get_wa_conversation(conv_id)
    return JSONResponse({"project_id": (conv or {}).get("project_id") or 0})


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
    // После SPA-навигации перезапускаем polling сообщений для нового чата
    if(window._waMsgsInterval) clearInterval(window._waMsgsInterval);
    window._waMsgsInterval = setInterval(function(){{
      if(typeof loadNewWaMsgs === 'function') loadNewWaMsgs();
    }}, 3000);
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




@app.get("/api/search_wa")
async def api_search_wa(request: Request, q: str = "", status: str = "open"):
    user = check_session(request)
    if not user: return JSONResponse({"error": "unauthorized"}, 401)
    if not q.strip(): return JSONResponse({"convs": []})
    convs = db.search_wa_conversations(q.strip(), status if status != "all" else None)
    return JSONResponse({"convs": [
        {"id": c["id"], "visitor_name": c.get("visitor_name",""),
         "wa_number": c.get("wa_number",""), "last_message": c.get("last_message",""),
         "unread_count": c.get("unread_count",0), "status": c.get("status","open"),
         "utm_campaign": c.get("utm_campaign",""), "fbclid": bool(c.get("fbclid")),
         "utm_source": c.get("utm_source","")}
        for c in convs
    ]})


@app.get("/api/search_tga")
async def api_search_tga(request: Request, q: str = "", status: str = "open"):
    user = check_session(request)
    if not user: return JSONResponse({"error": "unauthorized"}, 401)
    if not q.strip(): return JSONResponse({"convs": []})
    convs = db.search_tg_account_conversations(q.strip(), status if status != "all" else None)
    return JSONResponse({"convs": [
        {"id": c["id"], "visitor_name": c.get("visitor_name",""),
         "username": c.get("username",""), "last_message": c.get("last_message",""),
         "unread_count": c.get("unread_count",0), "status": c.get("status","open"),
         "utm_campaign": c.get("utm_campaign",""), "fbclid": bool(c.get("fbclid")),
         "utm_source": c.get("utm_source","")}
        for c in convs
    ]})

@app.get("/health")
async def health():
    return {"status": "ok", "version": "5.0",
            "bot1": bool(bot_manager.get_tracker_bot()),
            "bot2": bool(bot_manager.get_staff_bot())}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
