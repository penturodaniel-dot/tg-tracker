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
    all_projects = db.get_projects()  # [{id, name, utm_campaigns, ...}, ...]
    alert = ""
    if msg: alert = f'<div class="alert-green">✅ {msg}</div>'
    if err: alert = f'<div class="alert-red">⚠️ {err}</div>'

    # Собираем все UTM slugs из проектов: {slug -> project_name}
    import json as _json
    utm_map = {}
    for p in all_projects:
        for slug in (p.get("utm_campaigns") or "").split(","):
            slug = slug.strip()
            if slug:
                utm_map[slug] = p["name"]
    campaigns_js = _json.dumps([
        {"slug": slug, "name": pname} for slug, pname in utm_map.items()
    ])

    def _utm_picker(picker_id, current_utms_str):
        """Тег-пикер UTM кампаний. Скрытый input хранит comma-separated slugs."""
        return f"""
        <div class="utm-picker" id="picker-{picker_id}">
          <input type="hidden" name="utm_campaigns" id="utm-val-{picker_id}" value="{current_utms_str}"/>
          <div class="utm-tags-wrap" id="utm-tags-{picker_id}" style="display:flex;flex-wrap:wrap;gap:5px;min-height:28px;
               padding:5px 8px;border:1px solid var(--border);border-radius:8px;cursor:text;background:var(--bg2);"
               onclick="document.getElementById('utm-search-{picker_id}').focus()">
          </div>
          <div style="position:relative;margin-top:4px">
            <input type="text" id="utm-search-{picker_id}" placeholder="Поиск кампании..."
                   oninput="utmSearch('{picker_id}')" onfocus="utmShowDrop('{picker_id}')"
                   autocomplete="off"
                   style="width:100%;box-sizing:border-box;padding:5px 8px;border:1px solid var(--border);
                          border-radius:6px;background:var(--bg2);color:var(--text);font-size:.82rem"/>
            <div id="utm-drop-{picker_id}" style="display:none;position:absolute;top:100%;left:0;right:0;z-index:200;
                 background:var(--bg3);border:1px solid var(--border);border-radius:8px;
                 box-shadow:0 4px 16px rgba(0,0,0,.25);max-height:180px;overflow-y:auto;margin-top:2px">
            </div>
          </div>
        </div>"""

    def _cat_card(c):
        cid = c["id"]
        utms = c.get("utm_campaigns") or ""
        cat_name = c['name']
        cat_color = c['color']
        dot = f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{cat_color};margin-right:6px;vertical-align:middle"></span>'
        return f"""
        <div class="section" id="cat-{cid}" style="border-left:3px solid {cat_color};margin-bottom:10px;overflow:visible">
          <div class="acc-head" onclick="accToggle('acc-cat-{cid}')"
               style="cursor:pointer;display:flex;align-items:center;justify-content:space-between;padding:12px 18px;user-select:none;border-bottom:1px solid var(--border)">
            <div style="display:flex;align-items:center;gap:8px">
              <span class="acc-arrow" id="arrow-acc-cat-{cid}"
                    style="font-size:.8rem;color:var(--text3);transition:transform .2s">▶</span>
              {dot}<h3 style="margin:0">{cat_name}</h3>
            </div>
            <form method="post" action="/categories/delete" style="display:inline"
                  onsubmit="event.stopPropagation();return confirm('Удалить категорию {cat_name}?')">
              <input type="hidden" name="cat_id" value="{cid}"/>
              <button class="btn" onclick="event.stopPropagation()"
                      style="background:rgba(239,68,68,.15);color:#f87171;border:1px solid rgba(239,68,68,.3);font-size:.76rem;padding:3px 10px">
                &#x2715; Удалить
              </button>
            </form>
          </div>
          <div id="acc-cat-{cid}" style="display:none;padding:14px 18px;overflow:visible">
            <form method="post" action="/categories/update">
              <input type="hidden" name="cat_id" value="{cid}"/>
              <div style="display:grid;grid-template-columns:1fr auto auto;gap:12px;align-items:end;margin-bottom:12px">
                <div class="field-group">
                  <div class="field-label">Название</div>
                  <input type="text" name="name" value="{cat_name}" required/>
                </div>
                <div class="field-group" style="flex:none">
                  <div class="field-label">Цвет</div>
                  {_color_picker(cat_color)}
                </div>
                <div>
                  <button class="btn">&#x1F4BE; Сохранить</button>
                </div>
              </div>
              <div class="field-group" style="overflow:visible">
                <div class="field-label">UTM кампании <span style="color:var(--text3);font-weight:400">(из Проектов)</span></div>
                {_utm_picker(f'cat{cid}', utms)}
              </div>
            </form>
          </div>
        </div>"""

    cards = "".join(_cat_card(c) for c in cats) if cats else \
        '<div style="color:var(--text3);text-align:center;padding:32px 0">&#x041A;&#x0430;&#x0442;&#x0435;&#x0433;&#x043E;&#x0440;&#x0438;&#x0439; &#x043D;&#x0435;&#x0442; &mdash; &#x0441;&#x043E;&#x0437;&#x0434;&#x0430;&#x0439; &#x043F;&#x0435;&#x0440;&#x0432;&#x0443;&#x044E; &#x2193;</div>'

    color_new = _color_picker('#6366f1')
    picker_new = _utm_picker('new', '')

    # JS вне f-string — нет нужды в двойных {{ }} и проблем с экранированием
    js_code = (
        "var UTM_CAMPAIGNS = " + campaigns_js + ";\n"
        "function utmPickerInit(id){"
        "  var v=document.getElementById('utm-val-'+id);"
        "  if(!v)return;"
        "  var sel=v.value?v.value.split(',').map(function(s){return s.trim();}).filter(Boolean):[];"
        "  _utmRenderTags(id,sel);"
        "}"
        "function _utmGetSelected(id){"
        "  var v=document.getElementById('utm-val-'+id);"
        "  return v&&v.value?v.value.split(',').map(function(s){return s.trim();}).filter(Boolean):[];"
        "}"
        "function _utmSetSelected(id,arr){"
        "  document.getElementById('utm-val-'+id).value=arr.join(',');"
        "  _utmRenderTags(id,arr);"
        "}"
        "function _utmRenderTags(id,sel){"
        "  var wrap=document.getElementById('utm-tags-'+id);"
        "  if(!wrap)return;"
        "  wrap.innerHTML='';"
        "  if(!sel.length){wrap.innerHTML='<span style=\"color:var(--text3);font-size:.78rem\">&#x2014; не привязаны</span>';return;}"
        "  sel.forEach(function(slug){"
        "    var c=UTM_CAMPAIGNS.find(function(x){return x.slug===slug;});"
        "    var label=c?c.name+' ('+slug+')':slug;"
        "    var chip=document.createElement('span');"
        "    chip.className='utm-tag-chip';"
        "    chip.innerHTML=label+' <span class=\"rm\" onclick=\"utmRemove(\\''+id+'\\',\\''+slug+'\\')\">&times;</span>';"
        "    wrap.appendChild(chip);"
        "  });"
        "}"
        "function utmRemove(id,slug){"
        "  _utmSetSelected(id,_utmGetSelected(id).filter(function(s){return s!==slug;}));"
        "}"
        "function utmShowDrop(id){"
        "  utmSearch(id);"
        "  document.getElementById('utm-drop-'+id).style.display='block';"
        "}"
        "function utmSearch(id){"
        "  var q=(document.getElementById('utm-search-'+id).value||'').toLowerCase();"
        "  var sel=_utmGetSelected(id);"
        "  var drop=document.getElementById('utm-drop-'+id);"
        "  var items=UTM_CAMPAIGNS.filter(function(c){return !q||c.slug.indexOf(q)!==-1||c.name.toLowerCase().indexOf(q)!==-1;});"
        "  if(!items.length){drop.innerHTML='<div class=\"utm-drop-item\" style=\"color:var(--text3)\">&#x041D;&#x0435;&#x0442; &#x043A;&#x0430;&#x043C;&#x043F;&#x0430;&#x043D;&#x0438;&#x0439;</div>';}"
        "  else{drop.innerHTML=items.map(function(c){"
        "    var used=sel.indexOf(c.slug)!==-1;"
        "    return '<div class=\"utm-drop-item'+(used?' used':'')+'\" onclick=\"utmAdd(\\''+id+'\\',\\''+c.slug+'\\')\">'"
        "      +'<span style=\"color:var(--text3);font-size:.75rem\">'+c.slug+'</span>'"
        "      +'<span>'+c.name+'</span>'"
        "      +(used?'<span style=\"margin-left:auto;color:#22c55e\">&#10003;</span>':'')"
        "      +'</div>';"
        "  }).join('');}"
        "  drop.style.display='block';"
        "}"
        "function utmAdd(id,slug){"
        "  var sel=_utmGetSelected(id);"
        "  if(sel.indexOf(slug)===-1)sel.push(slug);"
        "  _utmSetSelected(id,sel);"
        "  document.getElementById('utm-search-'+id).value='';"
        "  document.getElementById('utm-drop-'+id).style.display='none';"
        "}"
        "document.addEventListener('mousedown',function(e){"
        "  document.querySelectorAll('[id^=\"utm-drop-\"]').forEach(function(drop){"
        "    var id=drop.id.replace('utm-drop-','');"
        "    var s=document.getElementById('utm-search-'+id);"
        "    if(!drop.contains(e.target)&&e.target!==s)drop.style.display='none';"
        "  });"
        "});"
        "function accToggle(id){"
        "  var b=document.getElementById(id);"
        "  var a=document.getElementById('arrow-'+id);"
        "  var open=b.style.display==='none';"
        "  b.style.display=open?'block':'none';"
        "  a.style.transform=open?'rotate(90deg)':'rotate(0deg)';"
        "  if(open)utmPickerInit(id.replace('acc-cat-','cat'));"
        "}"
        "utmPickerInit('new');"
    )

    content = f"""<div class="page-wrap">
    <div class="page-title">&#128194; Категории чатов</div>
    <div class="page-sub">Разделяй чаты по направлениям и управляй доступом менеджеров</div>
    {alert}
    <div style="background:rgba(99,102,241,.07);border:1px solid rgba(99,102,241,.2);border-radius:10px;
                padding:12px 16px;margin-bottom:20px;font-size:.82rem;color:var(--text2);line-height:1.7">
      &#128161; <b>Как работает:</b> привяжи UTM кампании к категории &mdash; чаты будут распределяться автоматически.
      В карточке менеджера отметь галочками к каким категориям он имеет доступ.
      Менеджер без категорий не видит ни одного чата.
    </div>
    <div style="margin-bottom:16px">
      <form method="post" action="/categories/backfill" style="display:inline">
        <button class="btn" style="background:rgba(99,102,241,.2);color:#818cf8;border:1px solid rgba(99,102,241,.4)">
          &#x1F504; Привязать существующие чаты по UTM
        </button>
      </form>
      <span style="color:var(--text3);font-size:.78rem;margin-left:10px">
        Разово пройдётся по всем чатам без категории и привяжет по UTM метке
      </span>
    </div>
    {cards}
    <div class="section" style="border-left:3px solid #22c55e;margin-top:16px;overflow:visible">
      <div class="section-head"><h3>&#x2795; Новая категория</h3></div>
      <div class="section-body" style="overflow:visible">
        <form method="post" action="/categories/create">
          <div style="display:grid;grid-template-columns:1fr auto auto;gap:12px;align-items:end;margin-bottom:12px">
            <div class="field-group">
              <div class="field-label">Название</div>
              <input type="text" name="name" placeholder="Например: Анкеты" required/>
            </div>
            <div class="field-group" style="flex:none">
              <div class="field-label">Цвет</div>
              {color_new}
            </div>
            <div>
              <button class="btn" style="background:#22c55e;color:#fff">&#x2795; Создать</button>
            </div>
          </div>
          <div class="field-group" style="overflow:visible">
            <div class="field-label">UTM кампании <span style="color:var(--text3);font-weight:400">(из Проектов)</span></div>
            {picker_new}
          </div>
        </form>
      </div>
    </div>
    </div>
    <style>
    .acc-section .section-head{{display:none}}
    .utm-tag-chip{{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:20px;
      font-size:.76rem;background:rgba(99,102,241,.18);color:#818cf8;border:1px solid rgba(99,102,241,.35);white-space:nowrap}}
    .utm-tag-chip .rm{{cursor:pointer;opacity:.65;font-size:.7rem;line-height:1}}
    .utm-tag-chip .rm:hover{{opacity:1}}
    .utm-drop-item{{padding:7px 12px;cursor:pointer;font-size:.82rem;display:flex;align-items:center;gap:8px}}
    .utm-drop-item:hover{{background:var(--bg2)}}
    .utm-drop-item.used{{opacity:.4;pointer-events:none}}
    </style>
    <script>{js_code}</script>"""

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


@router.post("/categories/backfill")
async def categories_backfill(request: Request):
    user, e = require_auth(request, role="admin")
    if e: return e
    updated = db.backfill_categories_by_utm()
    return RedirectResponse(f"/categories?msg=Привязано+{updated}+чатов", 303)

