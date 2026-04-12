"""
routers/settings.py — Настройки CRM

Подключается в main.py:
    settings_setup(db, log, require_auth, base, nav_html, _render_conv_tags_picker, bot_manager, SECRET)
    app.include_router(settings_router)
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
bot_manager    = None
SECRET         = ""


def setup(_db, _log, _require_auth, _base, _nav_html, _render_conv_tags_picker_fn, _bot_manager, _secret):
    global db, log, require_auth, base, nav_html, _render_conv_tags_picker
    db             = _db
    log            = _log
    require_auth   = _require_auth
    base           = _base
    nav_html       = _nav_html
    _render_conv_tags_picker = _render_conv_tags_picker_fn
    global bot_manager, SECRET
    bot_manager    = _bot_manager
    SECRET         = _secret


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, msg: str = ""):
    user, err = require_auth(request, role="admin")
    if err: return err

    b1_info = await bot_manager.get_bot_info(bot_manager.get_tracker_bot())
    b2_info = await bot_manager.get_bot_info(bot_manager.get_staff_bot())
    b3_info = await bot_manager.get_bot_info(bot_manager.get_autopost_bot())
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
        border = "#3b82f6" if color == "blue" else ("#f97316" if color == "orange" else "#9333ea")
        btn = "btn" if color == "blue" else ("btn-orange" if color == "orange" else "btn")
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
    {bot_card("🟣 Бот 3 — Автопостинг в каналы", "purple", b3_info, "bot3_token", "settings/bot3")}

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

    <div class="section" style="border-left:3px solid #6366f1">
      <div class="section-head"><h3>🗂 Категории чатов</h3>
        <a href="/categories" class="btn btn-sm" style="background:rgba(99,102,241,.15);color:#818cf8;border:1px solid rgba(99,102,241,.3)">Управление →</a>
      </div>
      <div class="section-body" style="color:var(--text2);font-size:.84rem">
        Категории позволяют разделить чаты по направлениям и ограничить доступ менеджеров.
        Категория назначается автоматически по UTM кампании или вручную в чате.
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



@router.post("/settings/bot1")
async def settings_bot1(request: Request, bot1_token: str = Form("")):
    user, err = require_auth(request, role="admin")
    if err: return err
    if bot1_token.strip():
        db.set_setting("bot1_token", bot1_token.strip())
        await bot_manager.start_tracker_bot(bot1_token.strip())
        info = await bot_manager.get_bot_info(bot_manager.get_tracker_bot())
        if info.get("username"): db.set_setting("bot1_name", f"@{info['username']}")
    return RedirectResponse("/settings?msg=Бот+1+обновлён", 303)


@router.post("/settings/bot2")
async def settings_bot2(request: Request, bot2_token: str = Form("")):
    user, err = require_auth(request, role="admin")
    if err: return err
    if bot2_token.strip():
        db.set_setting("bot2_token", bot2_token.strip())
        await bot_manager.start_staff_bot(bot2_token.strip())
        info = await bot_manager.get_bot_info(bot_manager.get_staff_bot())
        if info.get("username"): db.set_setting("bot2_name", f"@{info['username']}")
    return RedirectResponse("/settings?msg=Бот+2+обновлён", 303)


@router.post("/settings/bot3")
async def settings_bot3(request: Request, bot3_token: str = Form("")):
    user, err = require_auth(request, role="admin")
    if err: return err
    if bot3_token.strip():
        db.set_setting("bot3_token", bot3_token.strip())
        await bot_manager.start_autopost_bot(bot3_token.strip())
        info = await bot_manager.get_bot_info(bot_manager.get_autopost_bot())
        if info.get("username"): db.set_setting("bot3_name", f"@{info['username']}")
    return RedirectResponse("/settings?msg=Бот+3+обновлён", 303)


@router.post("/settings/tiktok_pixel")
async def settings_tiktok_pixel(request: Request, tt_pixel_id: str = Form(""), tt_access_token: str = Form("")):
    user, err = require_auth(request, role="admin")
    if err: return err
    db.set_setting("tt_pixel_id", tt_pixel_id.strip())
    if tt_access_token.strip():
        db.set_setting("tt_access_token", tt_access_token.strip())
    return RedirectResponse("/settings?msg=TikTok+пиксель+сохранён", 303)


@router.post("/settings/test_event_code")
async def settings_test_event_code(request: Request, test_event_code: str = Form("")):
    user, err = require_auth(request, role="admin")
    if err: return err
    db.set_setting("test_event_code", test_event_code.strip())
    return RedirectResponse("/settings?msg=Тест-код+сохранён", 303)


@router.post("/settings/pixel")
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


@router.post("/settings/notify")
async def settings_notify(request: Request, notify_chat_id: str = Form(""), app_url: str = Form("")):
    user, err = require_auth(request, role="admin")
    if err: return err
    db.set_setting("notify_chat_id", notify_chat_id.strip())
    db.set_setting("app_url", app_url.strip())
    db.set_setting("dashboard_password", SECRET)
    return RedirectResponse("/settings?msg=Уведомления+настроены", 303)


@router.post("/settings/staff_welcome")
async def settings_staff_welcome(request: Request, staff_welcome: str = Form("")):
    user, err = require_auth(request, role="admin")
    if err: return err
    if staff_welcome: db.set_setting("staff_welcome", staff_welcome)
    return RedirectResponse("/landings_staff?msg=Текст+бота+сохранён", 303)


@router.post("/settings/landing")
async def settings_landing(request: Request, landing_title: str = Form(""), landing_subtitle: str = Form("")):
    user, err = require_auth(request, role="admin")
    if err: return err
    if landing_title:    db.set_setting("landing_title", landing_title)
    if landing_subtitle: db.set_setting("landing_subtitle", landing_subtitle)
    return RedirectResponse("/settings?msg=Лендинг+обновлён", 303)


# ── Категории чатов ────────────────────────────────────────────────────────────

CATEGORY_COLORS = [
    ("#6366f1", "Фиолетовый"), ("#3b82f6", "Синий"), ("#22c55e", "Зелёный"),
    ("#f97316", "Оранжевый"),  ("#ef4444", "Красный"), ("#eab308", "Жёлтый"),
    ("#ec4899", "Розовый"),    ("#14b8a6", "Бирюзовый"), ("#8b5cf6", "Лиловый"),
]


def _color_picker(selected):
    opts = ""
    for hex_color, name in CATEGORY_COLORS:
        sel = 'selected' if hex_color == selected else ''
        opts += f'<option value="{hex_color}" {sel}>{name}</option>'
    return f'<select name="color" style="background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 10px;color:var(--text);font-size:.82rem">{opts}</select>'


@router.get("/categories", response_class=HTMLResponse)
async def categories_page(request: Request, msg: str = "", err: str = ""):
    user, e = require_auth(request, role="admin")
    if e: return e

    cats = db.get_categories()
    alert = ""
    if msg: alert = f'<div class="alert-green">✅ {msg}</div>'
    if err: alert = f'<div class="alert-red">⚠️ {err}</div>'

    def _cat_card(c):
        cid = c["id"]
        utms = c.get("utm_campaigns") or ""
        utm_tags = "".join(
            f'<span class="badge" style="margin-right:4px">{u.strip()}</span>'
            for u in utms.split(",") if u.strip()
        ) or '<span style="color:var(--text3);font-size:.78rem">не привязаны</span>'
        dot = f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{c["color"]};margin-right:6px;vertical-align:middle"></span>'
        return f"""
        <div class="section" id="cat-{cid}" style="border-left:3px solid {c['color']};margin-bottom:10px">
          <div class="acc-head" onclick="accToggle('acc-cat-{cid}')"
               style="cursor:pointer;display:flex;align-items:center;justify-content:space-between;padding:8px 0;user-select:none">
            <div style="display:flex;align-items:center;gap:8px">
              <span class="acc-arrow" id="arrow-acc-cat-{cid}"
                    style="font-size:.8rem;color:var(--text3);transition:transform .2s">▶</span>
              {dot}<h3 style="margin:0">{c['name']}</h3>
            </div>
            <form method="post" action="/categories/delete" style="display:inline"
                  onsubmit="event.stopPropagation();return confirm('Удалить категорию {c[\'name\']}?')">
              <input type="hidden" name="cat_id" value="{cid}"/>
              <button class="btn" onclick="event.stopPropagation()"
                      style="background:rgba(239,68,68,.15);color:#f87171;border:1px solid rgba(239,68,68,.3);font-size:.76rem;padding:3px 10px">
                ✕ Удалить
              </button>
            </form>
          </div>
          <div class="acc-body" id="acc-cat-{cid}" style="display:none;padding-top:4px">
            <form method="post" action="/categories/update">
              <input type="hidden" name="cat_id" value="{cid}"/>
              <div class="form-row" style="flex-wrap:wrap;gap:12px;align-items:flex-end">
                <div class="field-group" style="flex:1;min-width:160px">
                  <div class="field-label">Название</div>
                  <input type="text" name="name" value="{c['name']}" required/>
                </div>
                <div class="field-group" style="flex:0">
                  <div class="field-label">Цвет</div>
                  {_color_picker(c['color'])}
                </div>
                <div class="field-group" style="flex:2;min-width:220px">
                  <div class="field-label">UTM кампании <span style="color:var(--text3);font-weight:400">(через запятую)</span></div>
                  <input type="text" name="utm_campaigns" value="{utms}" placeholder="usa_ankety_fb, ankety_usa_v2"/>
                  <div style="margin-top:6px">{utm_tags}</div>
                </div>
                <div style="display:flex;align-items:flex-end">
                  <button class="btn">💾 Сохранить</button>
                </div>
              </div>
            </form>
          </div>
        </div>"""

    cards = "".join(_cat_card(c) for c in cats) if cats else \
        '<div style="color:var(--text3);text-align:center;padding:32px 0">Категорий нет — создай первую ↓</div>'

    content = f"""<div class="page-wrap">
    <div class="page-title">🗂 Категории чатов</div>
    <div class="page-sub">Разделяй чаты по направлениям и управляй доступом менеджеров</div>
    {alert}

    <div style="background:rgba(99,102,241,.07);border:1px solid rgba(99,102,241,.2);border-radius:10px;
                padding:12px 16px;margin-bottom:20px;font-size:.82rem;color:var(--text2);line-height:1.7">
      💡 <b>Как работает:</b> привяжи UTM кампании к категории — чаты будут распределяться автоматически.
      В карточке менеджера отметь галочками к каким категориям он имеет доступ.
      Менеджер без категорий не видит ни одного чата.
    </div>

    {cards}

    <div class="section" style="border-left:3px solid #22c55e;margin-top:16px">
      <div class="section-head"><h3>➕ Новая категория</h3></div>
      <div class="section-body">
        <form method="post" action="/categories/create">
          <div class="form-row" style="flex-wrap:wrap;gap:12px;align-items:flex-end">
            <div class="field-group" style="flex:1;min-width:160px">
              <div class="field-label">Название</div>
              <input type="text" name="name" placeholder="Например: Анкеты" required/>
            </div>
            <div class="field-group" style="flex:0">
              <div class="field-label">Цвет</div>
              {_color_picker('#6366f1')}
            </div>
            <div class="field-group" style="flex:2;min-width:220px">
              <div class="field-label">UTM кампании <span style="color:var(--text3);font-weight:400">(через запятую, можно добавить потом)</span></div>
              <input type="text" name="utm_campaigns" placeholder="usa_ankety_fb, ankety_usa_v2"/>
            </div>
            <div style="display:flex;align-items:flex-end">
              <button class="btn" style="background:#22c55e;color:#fff">➕ Создать</button>
            </div>
          </div>
        </form>
      </div>
    </div>
    </div>

    <style>.acc-section .section-head{{display:none}}</style>
    <script>
    function accToggle(id) {{
      var b = document.getElementById(id);
      var a = document.getElementById('arrow-' + id);
      var open = b.style.display === 'none';
      b.style.display = open ? 'block' : 'none';
      a.style.transform = open ? 'rotate(90deg)' : 'rotate(0deg)';
    }}
    </script>"""

    return HTMLResponse(base(content, "categories", request))


@router.post("/categories/create")
async def categories_create(request: Request, name: str = Form(...),
                             color: str = Form("#6366f1"), utm_campaigns: str = Form("")):
    user, e = require_auth(request, role="admin")
    if e: return e
    db.create_category(name.strip(), color, utm_campaigns.strip())
    return RedirectResponse("/categories?msg=Категория+создана", 303)


@router.post("/categories/update")
async def categories_update(request: Request, cat_id: int = Form(...),
                             name: str = Form(""), color: str = Form("#6366f1"),
                             utm_campaigns: str = Form("")):
    user, e = require_auth(request, role="admin")
    if e: return e
    db.update_category(cat_id, name.strip(), color, utm_campaigns.strip())
    return RedirectResponse(f"/categories?msg=Сохранено#cat-{cat_id}", 303)


@router.post("/categories/delete")
async def categories_delete(request: Request, cat_id: int = Form(...)):
    user, e = require_auth(request, role="admin")
    if e: return e
    db.delete_category(cat_id)
    return RedirectResponse("/categories?msg=Категория+удалена", 303)

