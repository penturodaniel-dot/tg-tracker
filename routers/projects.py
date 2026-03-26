"""
routers/projects.py — Управление проектами (мультипиксель)

Подключается в main.py:
    from routers.projects import router as projects_router, setup as projects_setup
    projects_setup(db, log, require_auth, base, nav_html, _render_conv_tags_picker)
    app.include_router(projects_router)
"""

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

router = APIRouter()

db           = None
log          = None
require_auth = None
base         = None
nav_html     = None
_render_conv_tags_picker = None


def setup(_db, _log, _require_auth, _base, _nav_html, _render_conv_tags_picker_fn):
    global db, log, require_auth, base, nav_html, _render_conv_tags_picker
    db             = _db
    log            = _log
    require_auth   = _require_auth
    base           = _base
    nav_html       = _nav_html
    _render_conv_tags_picker = _render_conv_tags_picker_fn


# ── Helpers ───────────────────────────────────────────────────────────────────

def _masked(t: str) -> str:
    if not t: return "—"
    return t[:8] + "..." + t[-4:] if len(t) > 14 else t


def _project_card(p: dict, msg: str = "", err: str = "") -> str:
    pid = p["id"]
    alert = ""
    if msg: alert = f'<div class="alert-green" style="margin-bottom:12px">✅ {msg}</div>'
    if err: alert = f'<div class="alert-red"   style="margin-bottom:12px">⚠️ {err}</div>'

    fb_status  = f'<span style="color:#34d399">● {_masked(p["fb_pixel_id"])}</span>' if p.get("fb_pixel_id") else '<span style="color:var(--red)">● не настроен</span>'
    tt_status  = f'<span style="color:#34d399">● {_masked(p["tt_pixel_id"])}</span>' if p.get("tt_pixel_id") else '<span style="color:var(--red)">● не настроен</span>'
    utms = p.get("utm_campaigns") or ""
    utm_tags = "".join(f'<span class="badge" style="margin-right:4px">{u.strip()}</span>' for u in utms.split(",") if u.strip()) or '<span style="color:var(--text3);font-size:.78rem">не привязаны</span>'

    return f"""
    <div class="section" id="project-{pid}" style="border-left:3px solid #6366f1;margin-bottom:16px">
      <div class="section-head">
        <h3>🎯 {p['name']}</h3>
        <form method="post" action="/projects/delete" style="display:inline" onsubmit="return confirm('Удалить проект {p["name"]}?')">
          <input type="hidden" name="project_id" value="{pid}"/>
          <button class="btn" style="background:rgba(239,68,68,.15);color:#f87171;border:1px solid rgba(239,68,68,.3);font-size:.76rem;padding:3px 10px">✕ Удалить</button>
        </form>
      </div>
      {alert}
      <div class="section-body">
        <form method="post" action="/projects/update">
          <input type="hidden" name="project_id" value="{pid}"/>
          <div class="form-row" style="flex-wrap:wrap;gap:12px">

            <div class="field-group" style="flex:1;min-width:200px">
              <div class="field-label">Название проекта</div>
              <input type="text" name="name" value="{p['name']}" placeholder="USA Massage"/>
            </div>

            <div class="field-group" style="flex:1;min-width:220px">
              <div class="field-label">UTM кампании <span style="color:var(--text3);font-weight:400">(через запятую)</span></div>
              <input type="text" name="utm_campaigns" value="{utms}" placeholder="usa_massage, massage_usa, us_spa"/>
              <div style="margin-top:6px">{utm_tags}</div>
            </div>

            <div class="field-group" style="flex:1;min-width:180px">
              <div class="field-label">📢 Площадка трафика</div>
              <select name="traffic_source" style="width:100%;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 12px;color:var(--text);font-size:.82rem">
                <option value="" {'selected' if not p.get('traffic_source') else ''}>🌐 Все / Не указано</option>
                <option value="facebook" {'selected' if p.get('traffic_source') == 'facebook' else ''}>🔵 Facebook</option>
                <option value="tiktok" {'selected' if p.get('traffic_source') == 'tiktok' else ''}>🎵 TikTok</option>
                <option value="organic" {'selected' if p.get('traffic_source') == 'organic' else ''}>🌿 Органика</option>
              </select>
              <div style="font-size:.72rem;color:var(--text3);margin-top:3px">Определяет какой CAPI использовать</div>
            </div>
          </div>

          <div style="font-size:.72rem;font-weight:700;color:#3b82f6;text-transform:uppercase;letter-spacing:.08em;margin:14px 0 8px">
            Facebook CAPI &nbsp; {fb_status}
          </div>
          <div class="form-row" style="flex-wrap:wrap;gap:12px">
            <div class="field-group" style="flex:1;min-width:200px">
              <div class="field-label">Pixel ID</div>
              <input type="text" name="fb_pixel_id" value="{p.get('fb_pixel_id','')}" placeholder="123456789012345"/>
            </div>
            <div class="field-group" style="flex:1;min-width:200px">
              <div class="field-label">Access Token <span style="color:var(--text3);font-weight:400">(пусто = не менять)</span></div>
              <input type="text" name="fb_token" placeholder="EAAxxxxxxx..."/>
            </div>
          </div>

          <div style="font-size:.72rem;font-weight:700;color:#f97316;text-transform:uppercase;letter-spacing:.08em;margin:14px 0 8px">
            TikTok Events API &nbsp; {tt_status}
          </div>
          <div class="form-row" style="flex-wrap:wrap;gap:12px">
            <div class="field-group" style="flex:1;min-width:200px">
              <div class="field-label">Pixel Code</div>
              <input type="text" name="tt_pixel_id" value="{p.get('tt_pixel_id','')}" placeholder="CXXXXXXXXXXXXXXX"/>
            </div>
            <div class="field-group" style="flex:1;min-width:200px">
              <div class="field-label">Access Token <span style="color:var(--text3);font-weight:400">(пусто = не менять)</span></div>
              <input type="text" name="tt_token" placeholder="Оставь пустым чтобы не менять"/>
            </div>
          </div>

          <div style="font-size:.72rem;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:.08em;margin:14px 0 8px">
            🧪 Тестирование
          </div>
          <div class="form-row" style="flex-wrap:wrap;gap:12px">
            <div class="field-group" style="flex:1;min-width:200px">
              <div class="field-label">Facebook Test Event Code <span style="color:var(--text3);font-weight:400">(пусто = отключено)</span></div>
              <input type="text" name="test_event_code" value="{p.get('test_event_code','')}" placeholder="TEST12345"/>
              <div style="font-size:.72rem;color:var(--text3);margin-top:4px">Найди в Events Manager → Test Events → скопируй код</div>
            </div>
            <div class="field-group" style="flex:1;min-width:200px">
              <div class="field-label">🎵 TikTok Test Event Code <span style="color:var(--text3);font-weight:400">(пусто = отключено)</span></div>
              <input type="text" name="tt_test_event_code" value="{p.get('tt_test_event_code','')}" placeholder="Вставь tt_test_id"/>
              <div style="font-size:.72rem;color:var(--text3);margin-top:4px">Найди в Events Manager → Test Events → скопируй tt_test_id</div>
            </div>
          </div>

          <div style="margin-top:14px">
            <button class="btn">💾 Сохранить</button>
          </div>
        </form>
      </div>
    </div>"""


@router.get("/projects", response_class=HTMLResponse)
async def projects_page(request: Request, msg: str = "", err: str = ""):
    user, e = require_auth(request, role="admin")
    if e: return e

    projects = db.get_projects()
    alert = ""
    if msg: alert = f'<div class="alert-green">✅ {msg}</div>'
    if err: alert = f'<div class="alert-red">⚠️ {err}</div>'

    cards = "".join(_project_card(p) for p in projects) if projects else \
        '<div class="empty" style="padding:40px 0;text-align:center;color:var(--text3)">Проектов нет — создай первый ↓</div>'

    content = f"""<div class="page-wrap">
    <div class="page-title">🎯 Проекты</div>
    <div class="page-sub">Мультипиксельные проекты — каждый проект привязан к своим UTM кампаниям и пикселям</div>
    {alert}

    <div style="background:rgba(99,102,241,.07);border:1px solid rgba(99,102,241,.2);border-radius:10px;padding:12px 16px;margin-bottom:20px;font-size:.82rem;color:var(--text2);line-height:1.7">
      💡 <b>Как работает:</b> когда менеджер нажимает «📤 Lead» в чате — система автоматически определяет проект
      по <code>utm_campaign</code> лида и отправляет событие в пиксели этого проекта.
      Если лид не совпадает ни с одним проектом — используются глобальные пиксели из Настроек.
    </div>

    {cards}

    <div class="section" style="border-left:3px solid #22c55e">
      <div class="section-head"><h3>➕ Новый проект</h3></div>
      <div class="section-body">
        <form method="post" action="/projects/create">
          <div class="form-row">
            <div class="field-group" style="flex:1">
              <div class="field-label">Название проекта</div>
              <input type="text" name="name" placeholder="Например: USA Massage или UA Operators" required/>
            </div>
            <div style="display:flex;align-items:flex-end">
              <button class="btn" style="background:#22c55e;color:#fff">➕ Создать</button>
            </div>
          </div>
        </form>
      </div>
    </div>
    </div>"""

    return HTMLResponse(base(content, "projects", request))


@router.post("/projects/create")
async def projects_create(request: Request, name: str = Form(...)):
    user, e = require_auth(request, role="admin")
    if e: return e
    if not name.strip():
        return RedirectResponse("/projects?err=Введи+название", 303)
    try:
        db.create_project(name.strip())
    except Exception as ex:
        return RedirectResponse(f"/projects?err=Ошибка:+{str(ex)[:60]}", 303)
    return RedirectResponse("/projects?msg=Проект+создан", 303)


@router.post("/projects/update")
async def projects_update(request: Request,
                          project_id: int = Form(...),
                          name: str = Form(""),
                          fb_pixel_id: str = Form(""),
                          fb_token: str = Form(""),
                          tt_pixel_id: str = Form(""),
                          tt_token: str = Form(""),
                          utm_campaigns: str = Form(""),
                          test_event_code: str = Form(""),
                          tt_test_event_code: str = Form(""),
                          traffic_source: str = Form("")):
    user, e = require_auth(request, role="admin")
    if e: return e
    kwargs = dict(
        name=name or None,
        fb_pixel_id=fb_pixel_id,
        tt_pixel_id=tt_pixel_id,
        utm_campaigns=utm_campaigns,
        test_event_code=test_event_code,
        tt_test_event_code=tt_test_event_code,
        traffic_source=traffic_source,
    )
    if fb_token.strip():  kwargs["fb_token"]  = fb_token.strip()
    if tt_token.strip():  kwargs["tt_token"]  = tt_token.strip()
    db.update_project(project_id, **kwargs)
    return RedirectResponse(f"/projects?msg=Сохранено#project-{project_id}", 303)


@router.post("/projects/delete")
async def projects_delete(request: Request, project_id: int = Form(...)):
    user, e = require_auth(request, role="admin")
    if e: return e
    db.delete_project(project_id)
    return RedirectResponse("/projects?msg=Проект+удалён", 303)


@router.get("/api/projects")
async def api_projects(request: Request):
    """JSON список проектов для выпадашки в чатах"""
    from fastapi.responses import JSONResponse as _J
    user, e = require_auth(request)
    if e: return JSONResponse({"error": "unauthorized"}, 401)
    projects = db.get_projects()
    return JSONResponse([{"id": p["id"], "name": p["name"],
                          "has_fb": bool(p.get("fb_pixel_id")),
                          "has_tt": bool(p.get("tt_pixel_id"))} for p in projects])
