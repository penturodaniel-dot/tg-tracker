"""
routers/scripts.py — Управление скриптами общения (шаблонные сообщения по категориям)

Подключается в main.py:
    from routers.scripts import router as scripts_router, setup as scripts_setup
    scripts_setup(db, log, require_auth, base, nav_html, _render_conv_tags_picker)
    app.include_router(scripts_router)
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


# ── Страница управления скриптами ────────────────────────────────────────────
@router.get("/scripts", response_class=HTMLResponse)
async def scripts_page(request: Request, project_id: int = 0):
    user, err = require_auth(request)
    if err: return err

    projects = db.get_projects()
    if not projects:
        return HTMLResponse(base(
            '<div class="page-wrap"><div class="section"><p style="color:var(--text3)">Сначала создайте хотя бы один проект в разделе Настройки → Проекты.</p></div></div>',
            "scripts", request
        ))

    # Определяем активный проект
    if not project_id and projects:
        project_id = projects[0]["id"]
    cur_project = next((p for p in projects if p["id"] == project_id), projects[0])

    scripts = db.get_scripts(project_id)

    # Группируем по категориям
    cats: dict[str, list] = {}
    for s in scripts:
        cats.setdefault(s["category"], []).append(s)

    def esc(t):
        return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    # Список скриптов по категориям
    scripts_html = ""
    if not scripts:
        scripts_html = '<div style="padding:40px;text-align:center;color:var(--text3)">Нет скриптов. Добавьте первый скрипт →</div>'
    else:
        for cat, items in cats.items():
            scripts_html += f"""
            <div class="script-category-block" style="margin-bottom:24px">
              <div style="font-size:.8rem;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px;padding:0 2px">
                📂 {esc(cat)}
              </div>
              <div style="display:flex;flex-direction:column;gap:6px">
            """
            for s in items:
                preview = esc(s["body"])[:80] + ("…" if len(s["body"]) > 80 else "")
                scripts_html += f"""
                <div class="script-card" style="background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:12px 14px;display:flex;align-items:flex-start;gap:10px">
                  <div style="flex:1;min-width:0">
                    <div style="font-weight:600;color:var(--text);margin-bottom:3px">{esc(s['title'])}</div>
                    <div style="font-size:.8rem;color:var(--text3);white-space:pre-wrap;word-break:break-word">{preview}</div>
                  </div>
                  <div style="display:flex;gap:6px;flex-shrink:0">
                    <button onclick="openEditScript({s['id']}, {repr(s['category'])}, {repr(s['title'])}, {repr(s['body'])}, {s['sort_order']})"
                      class="btn-gray btn-sm">✏️</button>
                    <button onclick="deleteScript({s['id']})"
                      class="btn-gray btn-sm" style="color:var(--red)">🗑</button>
                  </div>
                </div>
                """
            scripts_html += "</div></div>"

    # Табы проектов
    proj_tabs = ""
    for p in projects:
        active_style = "background:var(--orange);color:#fff" if p["id"] == project_id else "background:var(--bg2);color:var(--text2)"
        proj_tabs += f'<a href="/scripts?project_id={p["id"]}" style="padding:6px 14px;border-radius:8px;font-size:.82rem;font-weight:600;text-decoration:none;{active_style}">{esc(p["name"])}</a>'

    content_html = f"""
    <div class="page-wrap">
      <div class="section">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
          <div>
            <div class="section-title">📝 Скрипты общения</div>
            <div style="font-size:.82rem;color:var(--text3);margin-top:2px">Шаблонные сообщения для менеджеров — подставляются в чат одним кликом</div>
          </div>
          <button class="btn-orange" onclick="openAddScript()">+ Добавить скрипт</button>
        </div>

        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:20px">{proj_tabs}</div>

        <div id="scripts-list">{scripts_html}</div>
      </div>
    </div>

    <!-- Модалка добавления/редактирования -->
    <div id="script-modal" style="display:none;position:fixed;inset:0;z-index:1000;background:rgba(0,0,0,.6);align-items:center;justify-content:center">
      <div style="background:var(--bg2);border:1px solid var(--border);border-radius:14px;padding:24px;width:100%;max-width:520px;margin:20px">
        <div style="font-weight:700;font-size:1.05rem;color:var(--text);margin-bottom:16px" id="modal-title">Новый скрипт</div>
        <input type="hidden" id="script-id" value="0"/>
        <div style="margin-bottom:12px">
          <label style="font-size:.8rem;color:var(--text3);display:block;margin-bottom:5px">Категория</label>
          <input id="script-cat" type="text" placeholder="Например: Приветствие, Оплата, Возражения…"
            style="width:100%;background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:9px 12px;color:var(--text);font-size:.9rem;box-sizing:border-box"/>
          <div id="cat-suggestions" style="display:flex;flex-wrap:wrap;gap:5px;margin-top:6px"></div>
        </div>
        <div style="margin-bottom:12px">
          <label style="font-size:.8rem;color:var(--text3);display:block;margin-bottom:5px">Название скрипта</label>
          <input id="script-title" type="text" placeholder="Краткое название"
            style="width:100%;background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:9px 12px;color:var(--text);font-size:.9rem;box-sizing:border-box"/>
        </div>
        <div style="margin-bottom:12px">
          <label style="font-size:.8rem;color:var(--text3);display:block;margin-bottom:5px">Текст сообщения</label>
          <textarea id="script-body" rows="5" placeholder="Текст который подставится в поле отправки…"
            style="width:100%;background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:9px 12px;color:var(--text);font-size:.9rem;resize:vertical;font-family:inherit;box-sizing:border-box"></textarea>
        </div>
        <div style="margin-bottom:18px">
          <label style="font-size:.8rem;color:var(--text3);display:block;margin-bottom:5px">Порядок сортировки</label>
          <input id="script-order" type="number" value="0" min="0"
            style="width:80px;background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:9px 12px;color:var(--text);font-size:.9rem"/>
        </div>
        <div style="display:flex;gap:8px;justify-content:flex-end">
          <button class="btn-gray" onclick="closeScriptModal()">Отмена</button>
          <button class="btn-orange" onclick="saveScript()">Сохранить</button>
        </div>
      </div>
    </div>

    <script>
    var SCRIPT_PROJECT_ID = {project_id};
    var _existingCats = {[esc(c) for c in cats.keys()]};

    function openAddScript() {{
      document.getElementById('script-id').value = '0';
      document.getElementById('modal-title').textContent = 'Новый скрипт';
      document.getElementById('script-cat').value = '';
      document.getElementById('script-title').value = '';
      document.getElementById('script-body').value = '';
      document.getElementById('script-order').value = '0';
      renderCatSuggestions('');
      document.getElementById('script-modal').style.display = 'flex';
      setTimeout(function(){{ document.getElementById('script-cat').focus(); }}, 50);
    }}

    function openEditScript(id, cat, title, body, order) {{
      document.getElementById('script-id').value = id;
      document.getElementById('modal-title').textContent = 'Редактировать скрипт';
      document.getElementById('script-cat').value = cat;
      document.getElementById('script-title').value = title;
      document.getElementById('script-body').value = body;
      document.getElementById('script-order').value = order;
      renderCatSuggestions(cat);
      document.getElementById('script-modal').style.display = 'flex';
    }}

    function closeScriptModal() {{
      document.getElementById('script-modal').style.display = 'none';
    }}

    function renderCatSuggestions(current) {{
      var box = document.getElementById('cat-suggestions');
      box.innerHTML = _existingCats
        .filter(function(c){{ return c !== current; }})
        .map(function(c){{
          return '<span onclick="document.getElementById(\\'script-cat\\').value=this.textContent;renderCatSuggestions(this.textContent)" '
            + 'style="cursor:pointer;background:var(--bg3);border:1px solid var(--border);border-radius:6px;padding:2px 8px;font-size:.78rem;color:var(--text2)">'
            + c + '</span>';
        }}).join('');
    }}

    document.getElementById('script-cat').addEventListener('input', function(){{
      renderCatSuggestions(this.value);
    }});

    async function saveScript() {{
      var id    = document.getElementById('script-id').value;
      var cat   = document.getElementById('script-cat').value.trim();
      var title = document.getElementById('script-title').value.trim();
      var body  = document.getElementById('script-body').value;
      var order = document.getElementById('script-order').value;
      if(!cat || !title) {{ alert('Заполните категорию и название'); return; }}
      var url   = id === '0' ? '/api/scripts' : '/api/scripts/' + id;
      var method = id === '0' ? 'POST' : 'PUT';
      var r = await fetch(url, {{
        method: method,
        headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
        body: 'project_id=' + SCRIPT_PROJECT_ID
          + '&category=' + encodeURIComponent(cat)
          + '&title=' + encodeURIComponent(title)
          + '&body=' + encodeURIComponent(body)
          + '&sort_order=' + encodeURIComponent(order)
      }});
      var d = await r.json();
      if(d.ok) {{ closeScriptModal(); window.location.reload(); }}
      else alert('Ошибка: ' + (d.error || r.status));
    }}

    async function deleteScript(id) {{
      if(!confirm('Удалить скрипт?')) return;
      var r = await fetch('/api/scripts/' + id, {{method: 'DELETE'}});
      var d = await r.json();
      if(d.ok) window.location.reload();
      else alert('Ошибка удаления');
    }}

    // Закрытие по клику вне модалки
    document.getElementById('script-modal').addEventListener('click', function(e){{
      if(e.target === this) closeScriptModal();
    }});
    </script>
    """

    return HTMLResponse(base(content_html, "scripts", request))


# ── API ───────────────────────────────────────────────────────────────────────
@router.get("/api/scripts")
async def api_get_scripts(request: Request, project_id: int = 0):
    user, err = require_auth(request)
    if err: return JSONResponse({"ok": False, "error": "auth"}, status_code=401)
    if not project_id:
        return JSONResponse({"ok": False, "error": "project_id required"}, status_code=400)
    scripts = db.get_scripts(project_id)
    return JSONResponse({"ok": True, "scripts": scripts})


@router.post("/api/scripts")
async def api_create_script(
    request: Request,
    project_id: int = Form(...),
    category: str = Form(...),
    title: str = Form(...),
    body: str = Form(""),
    sort_order: int = Form(0),
):
    user, err = require_auth(request)
    if err: return JSONResponse({"ok": False, "error": "auth"}, status_code=401)
    new_id = db.create_script(project_id, category, title, body, sort_order)
    return JSONResponse({"ok": True, "id": new_id})


@router.put("/api/scripts/{script_id}")
async def api_update_script(
    script_id: int,
    request: Request,
    category: str = Form(...),
    title: str = Form(...),
    body: str = Form(""),
    sort_order: int = Form(0),
):
    user, err = require_auth(request)
    if err: return JSONResponse({"ok": False, "error": "auth"}, status_code=401)
    s = db.get_script(script_id)
    if not s:
        return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
    db.update_script(script_id, category, title, body, sort_order)
    return JSONResponse({"ok": True})


@router.delete("/api/scripts/{script_id}")
async def api_delete_script(script_id: int, request: Request):
    user, err = require_auth(request)
    if err: return JSONResponse({"ok": False, "error": "auth"}, status_code=401)
    db.delete_script(script_id)
    return JSONResponse({"ok": True})
