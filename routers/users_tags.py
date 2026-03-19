"""
routers/users_tags.py — Пользователи CRM и теги

Подключается в main.py:
    users_tags_setup(db, log, require_auth, base, nav_html, _render_conv_tags_picker, check_session)
    app.include_router(users_tags_router)
"""

from fastapi import APIRouter, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

router = APIRouter()

# ── Зависимости ───────────────────────────────────────────────────────────────
db             = None
log            = None
require_auth   = None
base           = None
nav_html       = None
_render_conv_tags_picker = None
check_session  = None


def setup(_db, _log, _require_auth, _base, _nav_html, _render_conv_tags_picker_fn, _check_session):
    global db, log, require_auth, base, nav_html, _render_conv_tags_picker
    db             = _db
    log            = _log
    require_auth   = _require_auth
    base           = _base
    nav_html       = _nav_html
    _render_conv_tags_picker = _render_conv_tags_picker_fn
    global check_session
    check_session  = _check_session


# USERS (admin only)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/users", response_class=HTMLResponse)
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


@router.post("/users/security")
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


@router.post("/users/security")
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


@router.post("/users/add")
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


@router.post("/users/update")
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


@router.post("/users/delete")
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

@router.get("/tags", response_class=HTMLResponse)
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


@router.post("/tags/create")
async def tags_create(request: Request, name: str = Form(""), color: str = Form("#6366f1")):
    user, err = require_auth(request, role="admin")
    if err: return err
    if name.strip():
        try:
            db.create_tag(name.strip(), color)
        except Exception:
            return RedirectResponse("/tags?msg=Тег+с+таким+именем+уже+существует", 303)
    return RedirectResponse("/tags?msg=Тег+создан", 303)


@router.post("/tags/delete")
async def tags_delete(request: Request, tag_id: int = Form(...)):
    user, err = require_auth(request, role="admin")
    if err: return err
    db.delete_tag(tag_id)
    return RedirectResponse("/tags?msg=Тег+удалён", 303)


@router.post("/tags/update_color")
async def tags_update_color(request: Request):
    user, err = require_auth(request, role="admin")
    if err: return JSONResponse({"ok": False})
    body = await request.json()
    db.update_tag(body["tag_id"], "", body["color"])  # name пустой — обновим только цвет
    return JSONResponse({"ok": True})


# ── API: привязать / отвязать тег от чата ────────────────────────────────────

@router.post("/api/conv_tag/add")
async def api_conv_tag_add(request: Request):
    user = check_session(request)
    if not user: return JSONResponse({"ok": False}, 401)
    body = await request.json()
    ok = db.add_conv_tag(body["conv_type"], body["conv_id"], body["tag_id"])
    tag = next((t for t in db.get_all_tags() if t["id"] == body["tag_id"]), None)
    return JSONResponse({"ok": ok, "tag": tag})


@router.post("/api/conv_tag/remove")
async def api_conv_tag_remove(request: Request):
    user = check_session(request)
    if not user: return JSONResponse({"ok": False}, 401)
    body = await request.json()
    ok = db.remove_conv_tag(body["conv_type"], body["conv_id"], body["tag_id"])
    return JSONResponse({"ok": ok})


@router.get("/api/tags")
async def api_get_tags(request: Request):
    user = check_session(request)
    if not user: return JSONResponse({"ok": False}, 401)
    return JSONResponse({"tags": db.get_all_tags()})

