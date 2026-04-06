"""
routers/channels.py — Каналы и кампании
"""

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter()

db                       = None
log                      = None
require_auth             = None
base                     = None
nav_html                 = None
_render_conv_tags_picker = None
bot_manager              = None


def setup(_db, _log, _require_auth, _base, _nav_html, _render_conv_tags_picker_fn, _bot_manager):
    global db, log, require_auth, base, nav_html, _render_conv_tags_picker, bot_manager
    db                       = _db
    log                      = _log
    require_auth             = _require_auth
    base                     = _base
    nav_html                 = _nav_html
    _render_conv_tags_picker = _render_conv_tags_picker_fn
    bot_manager              = _bot_manager


# ══════════════════════════════════════════════════════════════════════════════
# КАНАЛЫ
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/channels", response_class=HTMLResponse)
async def channels_page(request: Request, msg: str = "", err_msg: str = ""):
    msg     = request.query_params.get("msg", msg) or ""
    err_msg = request.query_params.get("err_msg", err_msg) or ""
    err_msg = err_msg.split("\n")[0][:120]
    msg     = msg.split("\n")[0][:120]
    user, err = require_auth(request)
    if err: return err
    channels = db.get_channels()
    b1 = bot_manager.get_tracker_bot()
    bot_link     = (await b1.get_me()).username if b1 else "—"
    bot_link_url = f"https://t.me/{bot_link}" if b1 else "—"
    rows = "".join(
        f"""<tr>
          <td><b>{c['name']}</b></td>
          <td><span class="tag">{c['channel_id']}</span></td>
          <td style="color:#34d399;font-weight:600">{c['total_joins']}</td>
          <td>{c['created_at'][:10]}</td>
          <td><form method="post" action="/channels/delete">
            <input type="hidden" name="channel_id" value="{c['channel_id']}"/>
            <button class="del-btn">✕</button>
          </form></td>
        </tr>"""
        for c in channels
    ) or '<tr><td colspan="5"><div class="empty">Каналов нет</div></td></tr>'

    alert = (f'<div class="alert-green">✅ {msg}</div>' if msg
             else f'<div class="alert-red">❌ {err_msg}</div>' if err_msg else "")

    content = f"""<div class="page-wrap">
    <div class="page-title">📡 Каналы</div>
    <div class="page-sub">Telegram-каналы для трекинга подписок</div>
    <div class="section">
      <div class="section-head"><h3>🤖 Бот трекер — добавь как администратора в каждый канал</h3></div>
      <div class="section-body"><div class="link-box">{bot_link_url}</div></div>
    </div>
    <div class="section">
      <div class="section-head"><h3>➕ Добавить канал</h3></div>
      <div class="section-body">
        {alert}
        <form method="post" action="/channels/add"><div class="form-row">
          <div class="field-group"><div class="field-label">Название</div>
            <input type="text" name="name" placeholder="Phoenix" required/></div>
          <div class="field-group"><div class="field-label">ID канала</div>
            <input type="text" name="channel_id" placeholder="-1003835844880" required/></div>
          <div style="display:flex;align-items:flex-end"><button class="btn">Добавить</button></div>
        </div></form>
      </div>
    </div>
    <div class="section">
      <div class="section-head"><h3>📋 Каналы ({len(channels)})</h3></div>
      <table><thead><tr><th>Название</th><th>ID</th><th>Подписчиков</th><th>Добавлен</th><th></th></tr></thead>
      <tbody>{rows}</tbody></table>
    </div>
    </div>"""
    return HTMLResponse(base(content, "channels", request))


@router.post("/channels/add")
async def channels_add(request: Request, name: str = Form(...), channel_id: str = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.add_channel(name.strip(), channel_id.strip())
    return RedirectResponse("/channels?msg=%D0%9A%D0%B0%D0%BD%D0%B0%D0%BB+%D0%B4%D0%BE%D0%B1%D0%B0%D0%B2%D0%BB%D0%B5%D0%BD", 303)


@router.post("/channels/delete")
async def channels_delete(request: Request, channel_id: str = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.delete_channel(channel_id)
    return RedirectResponse("/channels?msg=%D0%A3%D0%B4%D0%B0%D0%BB%D1%91%D0%BD", 303)


# ══════════════════════════════════════════════════════════════════════════════
# КАМПАНИИ
# ══════════════════════════════════════════════════════════════════════════════

def _build_utm_block(slug_url: str, camp_name: str, app_url: str, db_ref,
                     project_id=None) -> str:
    """Генерирует блок UTM ссылок для Facebook и TikTok."""
    # Приоритет: проект привязанный к кампании
    _proj = db_ref.get_project(int(project_id)) if project_id else None
    if not _proj:
        _src = "both"
        _utm_val = camp_name
    else:
        _src = (_proj.get("traffic_source") or "both").lower()
        _utms = [u.strip() for u in (_proj.get("utm_campaigns") or "").split(",") if u.strip()]
        _utm_val = _utms[0] if _utms else camp_name

    _tt_u = (slug_url + "?utm_source=tiktok&utm_medium=paid"
             "&utm_campaign=" + _utm_val +
             "&utm_content=__CID__&utm_term=__AID__&ttclid=__CLICKID__")
    _fb_u = (slug_url + "?utm_source=facebook&utm_medium=paid"
             "&utm_campaign=" + _utm_val +
             "&utm_content={{ad.name}}&utm_term={{adset.name}}&fbclid={{fbclid}}")

    def _row(icon_color, icon, url, btn_color, btn_border):
        uid = "utm_" + str(abs(hash(url)) % 99999)
        js_onclick = (
            "var i=document.getElementById('" + uid + "');"
            "navigator.clipboard.writeText(i.value);"
            "this.textContent='\u2713';"
            "setTimeout(()=>this.textContent='\U0001f4cb',1500)"
        )
        return (
            '<div style="margin-top:6px;display:flex;gap:4px;align-items:center">'
            + '<span style="color:' + icon_color + ';font-size:.7rem;flex-shrink:0">' + icon + '</span>'
            + '<input id="' + uid + '" readonly value="' + url + '" onclick="this.select()"'
            + ' style="flex:1;min-width:0;background:var(--bg);border:1px solid ' + btn_border + ';'
            + 'border-radius:5px;padding:3px 8px;color:' + icon_color + ';font-size:.65rem;'
            + 'font-family:monospace;cursor:pointer"/>'
            + '<button onclick="' + js_onclick + '"'
            + ' style="padding:2px 8px;background:' + btn_color + ';color:' + icon_color + ';'
            + 'border:1px solid ' + btn_border + ';border-radius:5px;cursor:pointer;'
            + 'font-size:.75rem;flex-shrink:0">\U0001f4cb</button>'
            + '</div>'
        )

    tt_row = _row("#69c9d0", "🎵 TikTok", _tt_u, "#1a1a2a", "#2a2a4a")
    fb_row = _row("#60a5fa", "🔵 Facebook", _fb_u, "#1e3a5f", "#3b5998")

    if _src == "tiktok":
        rows_html = tt_row
    elif _src == "facebook":
        rows_html = fb_row
    else:
        rows_html = tt_row + fb_row

    return (
        f'<div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--border)">'
        f'<div style="font-size:.7rem;color:var(--text3);font-weight:600;margin-bottom:2px">'
        f'📊 UTM ссылки для рекламы</div>'
        f'{rows_html}'
        f'</div>'
    )


def _build_campaign_card(c: dict, cchans: list, templates: list,
                          channels: list, app_url: str) -> str:
    """
    Карточка кампании.
    Город и телефон — прямо в строке каждого канала (inline).
    Отдельная секция телефонов убрана.
    """
    slug_url  = f"{app_url}/l/{c.get('slug', '')}"
    utm_block = _build_utm_block(slug_url, c['name'], app_url, db, c.get('project_id'))
    camp_id   = c["id"]
    camp_name = c["name"]
    total_joins = c["total_joins"]

    # ── Шаблон лендинга ───────────────────────────────────────────────────────
    tpl = next((t for t in templates if t["id"] == c.get("landing_id")), None)
    tpl_badge = (
        f'<span class="badge-green" style="font-size:.71rem">🎨 {tpl["name"]}</span>' if tpl
        else '<span class="badge-gray" style="font-size:.71rem">🎨 Дефолтный</span>'
    )
    tpl_select_opts = '<option value="">— Дефолтный —</option>' + "".join(
        f'<option value="{t["id"]}" {"selected" if t["id"] == c.get("landing_id") else ""}>{t["name"]}</option>'
        for t in templates
    )
    tpl_switch = (
        f'<form method="post" action="/campaigns/set_template"'
        f' style="display:flex;gap:6px;align-items:center">'
        f'<input type="hidden" name="campaign_id" value="{camp_id}"/>'
        f'<select name="landing_id" style="font-size:.77rem;padding:4px 8px;border-radius:7px;width:auto">'
        f'{tpl_select_opts}</select>'
        f'<button class="btn btn-sm" style="font-size:.74rem;padding:5px 10px">Сменить шаблон</button>'
        f'</form>'
    )

    # ── Выбор проекта (пиксель) ───────────────────────────────────────────────
    _projects = db.get_projects()
    _cur_proj_id = c.get('project_id')
    _cur_proj = next((p for p in _projects if p['id'] == _cur_proj_id), None)
    _proj_badge = (
        f'<span class="badge-green" style="font-size:.71rem">🎯 {_cur_proj["name"]}</span>'
        if _cur_proj else
        '<span class="badge-gray" style="font-size:.71rem">🎯 Проект не выбран</span>'
    )
    _proj_opts = '<option value="">— Без проекта (глобальный пиксель) —</option>' + ''.join(
        f'<option value="{p["id"]}" {"selected" if p["id"] == _cur_proj_id else ""}'
        f'>{p["name"]} [{"FB✓" if p.get("fb_pixel_id") else "FB✗"}'  
        f'{" TT✓" if p.get("tt_pixel_id") else ""}]</option>'
        for p in _projects
    )
    _proj_switch = (
        f'<form method="post" action="/campaigns/set_project"'
        f' style="display:flex;gap:6px;align-items:center;margin-top:6px">'
        f'<input type="hidden" name="campaign_id" value="{camp_id}"/>'
        f'<select name="project_id" style="font-size:.77rem;padding:4px 8px;border-radius:7px;width:auto">'
        f'{_proj_opts}</select>'
        f'<button class="btn btn-sm" style="font-size:.74rem;padding:5px 10px">Применить</button>'
        f'</form>'
    )

    # ── Строки каналов — город и телефон inline ───────────────────────────────
    # Строим map phone_id по городу из cchans для быстрого доступа
    chan_rows = ""
    for cc in cchans:
        cc_id     = cc["id"]
        city_val  = cc.get("city") or ""
        phone_val = cc.get("phone") or ""

        # Получаем доп. поля
        address_val    = cc.get("address") or ""
        tg_label_val   = cc.get("tg_label") or ""
        phone_label_val= cc.get("phone_label") or ""

        # Inline форма — город + телефон + кнопка деталей
        detail_filled = any([address_val, tg_label_val, phone_label_val])
        detail_badge  = '<span style="color:var(--green);font-size:.65rem;margin-left:2px">●</span>' if detail_filled else ""
        inline_form = (
            f'<form method="post" action="/campaigns/channel/location"'
            f' style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">'
            f'<input type="hidden" name="cc_id" value="{cc_id}"/>'
            f'<input type="hidden" name="campaign_id" value="{camp_id}"/>'
            f'<input type="hidden" name="address" value="{address_val}"/>'
            f'<input type="hidden" name="tg_label" value="{tg_label_val}"/>'
            f'<input type="hidden" name="phone_label" value="{phone_label_val}"/>'
            f'<input type="text" name="city" value="{city_val}" placeholder="New York"'
            f' style="width:105px;background:var(--bg);border:1px solid var(--border);'
            f'border-radius:5px;padding:3px 7px;color:var(--text);font-size:.75rem"/>'
            f'<input type="text" name="phone" value="{phone_val}" placeholder="+1 212 555-0100"'
            f' style="width:135px;background:var(--bg);border:1px solid var(--border);'
            f'border-radius:5px;padding:3px 7px;color:var(--text);font-size:.75rem;font-family:monospace"/>'
            f'<button class="btn-gray btn-sm" style="padding:3px 10px;font-size:.72rem">✓</button>'
            + '<button type="button" onclick="openLocDetail(' + str(cc_id) + ')"'
            + ' class="btn-gray btn-sm" style="padding:3px 8px;font-size:.72rem;background:var(--bg3)"'
            + ' title="Адрес и заголовки">\u2699\ufe0f' + detail_badge + '</button>'
            + '</form>'
            f'</form>'
        )

        # Бейдж города если заполнен
        city_badge = ""
        if city_val:
            city_badge = (
                f'<span style="background:rgba(59,130,246,.12);color:#93c5fd;border:1px solid rgba(59,130,246,.25);'
                f'border-radius:4px;padding:1px 6px;font-size:.68rem;font-weight:600;margin-left:6px">'
                f'📍 {city_val}</span>'
            )

        _refresh_btn = ""
        _ch_name_val = cc.get("channel_name") or ""
        if not _ch_name_val or _ch_name_val.lstrip('-').isdigit():
            _refresh_btn = (
                f'<form method="post" action="/campaigns/channel/refresh_name" style="display:inline">'
                f'<input type="hidden" name="cc_id" value="{cc_id}"/>'
                f'<input type="hidden" name="channel_id" value="{cc["channel_id"]}"/>'
                f'<input type="hidden" name="campaign_id" value="{camp_id}"/>'
                f'<button class="btn-gray btn-sm" style="padding:1px 5px;font-size:.7rem;margin-left:4px"'
                f' title="Обновить название">🔄</button></form>'
            )

        chan_rows += (
            f'<tr>'
            f'<td style="font-weight:600">'
            f'{cc.get("channel_name") or cc["channel_id"]}{city_badge}{_refresh_btn}'
            f'</td>'
            f'<td><div class="link-box" style="font-size:.69rem;padding:5px 9px">'
            f'{cc["invite_link"][:48]}...</div></td>'
            f'<td>{inline_form}</td>'
            f'<td style="color:var(--green);font-weight:700">{cc["joins"]}</td>'
            f'<td><form method="post" action="/campaigns/channel/delete" style="display:inline">'
            f'<input type="hidden" name="cc_id" value="{cc_id}"/>'
            f'<input type="hidden" name="campaign_id" value="{camp_id}"/>'
            f'<button class="del-btn btn-sm">✕</button></form></td>'
            f'</tr>'
        )
    if not chan_rows:
        chan_rows = '<tr><td colspan="5"><div class="empty" style="padding:12px">Нет каналов — добавь ниже</div></td></tr>'

    # ── Select для добавления канала ──────────────────────────────────────────
    ch_opts = "".join(
        f'<option value="{ch["channel_id"]}">{ch["name"]}</option>'
        for ch in channels
    )

    _acc_id = f"acc-camp-{camp_id}"
    return f"""
    <div class="section acc-section" style="border-left:3px solid var(--accent);margin-bottom:12px">
      <div class="acc-head" onclick="accToggle('{_acc_id}')"
           style="cursor:pointer;display:flex;align-items:center;justify-content:space-between;padding:10px 0;user-select:none">
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
          <span class="acc-arrow" id="arrow-{_acc_id}"
                style="font-size:.8rem;color:var(--text3);transition:transform .2s;display:inline-block">▶</span>
          <h3 style="margin:0">🎯 {camp_name}</h3>
          <span class="badge" style="font-size:.72rem">{total_joins} подписок</span>
          {tpl_badge}
          {_proj_badge}
        </div>
        <div style="display:flex;gap:8px;align-items:center" onclick="event.stopPropagation()">
          <a href="{slug_url}" target="_blank" class="btn-gray btn-sm">🌐 Лендинг</a>
          <form method="post" action="/campaigns/delete">
            <input type="hidden" name="campaign_id" value="{camp_id}"/>
            <button class="del-btn">✕</button>
          </form>
        </div>
      </div>
      <div class="acc-body" id="{_acc_id}" style="display:none">
      <div class="section-body">

        <!-- Ссылка в рекламу + UTM + смена шаблона -->
        <div style="margin-bottom:16px;padding:10px 14px;background:var(--bg3);
                    border-radius:9px;border:1px solid var(--border)">
          <div style="font-size:.74rem;color:var(--text3);margin-bottom:5px;font-weight:700;
                      text-transform:uppercase;letter-spacing:.05em">🔗 Ссылка в рекламу</div>
          <div class="link-box">{slug_url}</div>
          {utm_block}
          <div style="margin-top:10px">{tpl_switch}</div>
          <div style="margin-top:4px;display:flex;align-items:center;gap:8px;flex-wrap:wrap">
            <span style="font-size:.72rem;color:var(--text3);font-weight:600">🎯 Пиксель:</span>
            {_proj_switch}
          </div>
        </div>

        <!-- Каналы с inline город + телефон -->
        <div style="font-size:.74rem;font-weight:700;text-transform:uppercase;
                    letter-spacing:.05em;color:var(--text3);margin-bottom:6px">
          📡 Каналы
          <span style="font-size:.68rem;font-weight:400;margin-left:6px">
            Укажи город и телефон — пользователь выберет город и увидит нужный канал
          </span>
        </div>
        <table style="margin-bottom:14px">
          <thead><tr>
            <th>Канал</th>
            <th>Invite Link</th>
            <th>Город · Телефон</th>
            <th>Подписок</th>
            <th></th>
          </tr></thead>
          <tbody>{chan_rows}</tbody>
        </table>

        <!-- Добавить канал -->
        <form method="post" action="/campaigns/channel/add">
          <input type="hidden" name="campaign_id" value="{camp_id}"/>
          <input type="hidden" name="campaign_name" value="{camp_name}"/>
          <div class="form-row">
            <div class="field-group">
              <div class="field-label">Добавить канал</div>
              <select name="channel_id">{ch_opts}</select>
            </div>
            <div style="display:flex;align-items:flex-end">
              <button class="btn btn-sm">+ Добавить и создать ссылку</button>
            </div>
          </div>
        </form>

      </div>
      </div>
    </div>"""


@router.get("/campaigns", response_class=HTMLResponse)
async def campaigns_page(request: Request, msg: str = "", err_msg: str = ""):
    # Берём напрямую из query_params чтобы избежать Pydantic валидации спецсимволов
    msg     = request.query_params.get("msg", msg) or ""
    err_msg = request.query_params.get("err_msg", err_msg) or ""
    # Обрезаем до первой строки если есть перенос
    err_msg = err_msg.split("\n")[0].split("%0A")[0][:120]
    msg     = msg.split("\n")[0][:120]
    user, err = require_auth(request)
    if err: return err

    channels  = db.get_channels()
    campaigns = db.get_campaigns()
    templates = db.get_landings(ltype="client")
    app_url   = db.get_setting("app_url", "").rstrip("/")

    tpl_opts = '<option value="">— Дефолтный (Relaxation) —</option>' + "".join(
        f'<option value="{t["id"]}">{t["name"]}</option>' for t in templates
    )

    campaign_cards = ""
    for c in campaigns:
        cchans = db.get_campaign_channels(c["id"])
        campaign_cards += _build_campaign_card(c, cchans, templates, channels, app_url)

    if not campaign_cards:
        campaign_cards = '<div class="empty" style="padding:40px">Кампаний нет — создай первую</div>'

    tpl_hint = ""
    if not templates:
        tpl_hint = (
            '<div style="font-size:.8rem;color:var(--text3);margin-top:6px">'
            '💡 Нет кастомных шаблонов — '
            '<a href="/landings" style="color:var(--accent)">создай шаблон →</a>'
            ' или будет использован дефолтный дизайн</div>'
        )

    alert = (f'<div class="alert-green">✅ {msg}</div>' if msg
             else f'<div class="alert-red">❌ {err_msg}</div>' if err_msg else "")

    content = f"""<div class="page-wrap">
    <div class="page-title">🔗 Кампании</div>
    <div class="page-sub">Кампания = каналы + шаблон лендинга. Ставишь ссылку /l/slug в рекламу — пользователь подписывается — фиксируется Subscribe в FB CAPI.</div>
    {alert}
    <div class="section">
      <div class="section-head"><h3>➕ Создать кампанию</h3></div>
      <div class="section-body">
        <form method="post" action="/campaigns/create"><div class="form-row">
          <div class="field-group">
            <div class="field-label">Название (будет в UTM)</div>
            <input type="text" name="name" placeholder="FB_Broad_March_NYC" required/>
          </div>
          <div class="field-group" style="max-width:200px">
            <div class="field-label">URL slug</div>
            <input type="text" name="slug" placeholder="march-nyc"/>
          </div>
          <div class="field-group" style="max-width:240px">
            <div class="field-label">🎨 Шаблон лендинга</div>
            <select name="landing_id">{tpl_opts}</select>
          </div>
          <div style="display:flex;align-items:flex-end">
            <button class="btn">Создать</button>
          </div>
        </div></form>
        {tpl_hint}
      </div>
    </div>
    {campaign_cards}
    </div>"""
    # Попап для адреса и заголовков (один на всю страницу)
    popup_html = """
<div id="loc-detail-popup" style="display:none;position:fixed;inset:0;z-index:9000;align-items:center;justify-content:center">
  <div onclick="closeLocDetail()" style="position:absolute;inset:0;background:rgba(0,0,0,.6)"></div>
  <div style="position:relative;z-index:1;background:var(--bg2);border:1px solid var(--border);border-radius:14px;padding:24px;width:min(420px,94vw);max-height:80vh;overflow-y:auto">
    <div style="font-weight:700;font-size:.95rem;margin-bottom:16px">⚙ Детали локации — <span id="loc-city-title"></span></div>
    <form method="post" action="/campaigns/channel/location" id="loc-detail-form">
      <input type="hidden" name="cc_id" id="loc-cc-id"/>
      <input type="hidden" name="campaign_id" id="loc-camp-id"/>
      <input type="hidden" name="city" id="loc-city"/>
      <input type="hidden" name="phone" id="loc-phone"/>
      <div class="field-group" style="margin-bottom:12px">
        <div class="field-label">📍 Адрес локации</div>
        <textarea name="address" id="loc-address" rows="3"
                  placeholder="123 Main St, New York, NY 10001&#10;456 Broadway, New York, NY 10013"
                  style="width:100%;background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:8px 10px;color:var(--text);font-size:.85rem;font-family:inherit;resize:vertical"></textarea>
        <div style="font-size:.72rem;color:var(--text3);margin-top:3px">Каждый адрес с новой строки — все покажутся в попапе</div>
      </div>
      <div class="field-group" style="margin-bottom:12px">
        <div class="field-label">💬 Заголовок перед Telegram кнопкой</div>
        <input type="text" name="tg_label" id="loc-tg-label" placeholder="Write to our manager:"
               style="width:100%;background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:8px 10px;color:var(--text);font-size:.85rem"/>
      </div>
      <div class="field-group" style="margin-bottom:16px">
        <div class="field-label">📞 Заголовок перед телефоном</div>
        <input type="text" name="phone_label" id="loc-phone-label" placeholder="Or call us:"
               style="width:100%;background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:8px 10px;color:var(--text);font-size:.85rem"/>
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn-orange" style="flex:1">💾 Сохранить</button>
        <button type="button" onclick="closeLocDetail()" class="btn-gray">Отмена</button>
      </div>
    </form>
  </div>
</div>
<script>
// Данные каналов для попапа
var _ccData = {};
</script>"""

    # Собираем данные каналов для JS
    all_cc_data = {}
    for c in campaigns:
        for cc in db.get_campaign_channels(c["id"]):
            all_cc_data[cc["id"]] = {
                "camp_id":     c["id"],
                "city":        cc.get("city") or "",
                "phone":       cc.get("phone") or "",
                "address":     cc.get("address") or "",
                "tg_label":    cc.get("tg_label") or "",
                "phone_label": cc.get("phone_label") or "",
            }
    import json as _j
    cc_data_js = f"<script>var _ccData = {_j.dumps(all_cc_data)};</script>"

    open_js = """<script>
function openLocDetail(ccId, city) {
  var d = _ccData[ccId] || {};
  document.getElementById('loc-cc-id').value       = ccId;
  document.getElementById('loc-camp-id').value      = d.camp_id || '';
  document.getElementById('loc-city').value         = d.city || city || '';
  document.getElementById('loc-phone').value        = d.phone || '';
  document.getElementById('loc-address').value      = d.address || '';
  document.getElementById('loc-tg-label').value     = d.tg_label || '';
  document.getElementById('loc-phone-label').value  = d.phone_label || '';
  document.getElementById('loc-city-title').textContent = d.city || city || '';
  document.getElementById('loc-detail-popup').style.display = 'flex';
  document.body.style.overflow = 'hidden';
}
function closeLocDetail() {
  document.getElementById('loc-detail-popup').style.display = 'none';
  document.body.style.overflow = '';
}
</script>"""

    content = popup_html + cc_data_js + open_js + content
    acc_js = """
<style>
.acc-section .section-head { display:none }
.acc-head { border-radius:var(--radius-sm) }
.acc-head:hover h3 { color:var(--orange) }
</style>
<script>
function accToggle(id) {
  var body  = document.getElementById(id);
  var arrow = document.getElementById('arrow-' + id);
  if (!body) return;
  var open = body.style.display === 'none';
  body.style.display    = open ? 'block' : 'none';
  arrow.style.transform = open ? 'rotate(90deg)' : 'rotate(0deg)';
}
</script>"""
    content = acc_js + content
    return HTMLResponse(base(content, "campaigns", request))


# ── CRUD маршруты кампаний ────────────────────────────────────────────────────

@router.post("/campaigns/create")
async def campaigns_create(request: Request, name: str = Form(...),
                            slug: str = Form(""), landing_id: str = Form("")):
    user, err = require_auth(request)
    if err: return err
    import re, secrets as _sec
    if not slug.strip():
        slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') + "-" + _sec.token_hex(3)
    lid = int(landing_id) if landing_id.strip().isdigit() else None
    try:
        db.create_campaign(name.strip(), slug.strip(), landing_id=lid)
        from urllib.parse import quote_plus as _qp
        return RedirectResponse(f"/campaigns?msg={_qp(f'Кампания {name} создана')}", 303)
    except Exception as e:
        return RedirectResponse(f"/campaigns?err_msg={str(e)[:60].encode('ascii','replace').decode()}", 303)


@router.post("/campaigns/set_project")
async def campaigns_set_project(request: Request, campaign_id: int = Form(...),
                                 project_id: str = Form("")):
    """Привязать проект (пиксель) к кампании."""
    user, err = require_auth(request)
    if err: return err
    pid = int(project_id) if project_id.strip().isdigit() else None
    db.set_campaign_project(campaign_id, pid)
    msg = "Проект привязан" if pid else "Проект отвязан"
    from urllib.parse import quote_plus as _qp
    return RedirectResponse(f"/campaigns?msg={_qp(msg)}", 303)


@router.post("/campaigns/set_template")
async def campaigns_set_template(request: Request, campaign_id: int = Form(...),
                                  landing_id: str = Form("")):
    user, err = require_auth(request)
    if err: return err
    lid = int(landing_id) if landing_id.strip().isdigit() else None
    db.update_campaign_landing(campaign_id, lid)
    return RedirectResponse("/campaigns?msg=%D0%A8%D0%B0%D0%B1%D0%BB%D0%BE%D0%BD+%D0%BE%D0%B1%D0%BD%D0%BE%D0%B2%D0%BB%D1%91%D0%BD", 303)


@router.post("/campaigns/delete")
async def campaigns_delete(request: Request, campaign_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.delete_campaign(campaign_id)
    return RedirectResponse("/campaigns", 303)


# ── Каналы внутри кампании ────────────────────────────────────────────────────

@router.post("/campaigns/channel/add")
async def campaigns_channel_add(request: Request, campaign_id: int = Form(...),
                                 campaign_name: str = Form(...), channel_id: str = Form(...)):
    user, err = require_auth(request)
    if err: return err
    try:
        b1 = bot_manager.get_tracker_bot()
        if not b1:
            return RedirectResponse("/campaigns?err_msg=%D0%91%D0%BE%D1%82+1+%D0%BD%D0%B5+%D0%B7%D0%B0%D0%BF%D1%83%D1%89%D0%B5%D0%BD", 303)
        link_name = f"{campaign_name[:20]}_{channel_id[-6:]}"
        link_obj  = await b1.create_chat_invite_link(chat_id=int(channel_id), name=link_name[:32])
        try:
            chat    = await b1.get_chat(int(channel_id))
            ch_name = chat.title or channel_id
        except Exception:
            ch_name = channel_id
        db.add_campaign_channel(campaign_id, channel_id, ch_name, link_obj.invite_link)
        return RedirectResponse("/campaigns?msg=%D0%9A%D0%B0%D0%BD%D0%B0%D0%BB+%D0%B4%D0%BE%D0%B1%D0%B0%D0%B2%D0%BB%D0%B5%D0%BD+%D0%B2+%D0%BA%D0%B0%D0%BC%D0%BF%D0%B0%D0%BD%D0%B8%D1%8E", 303)
    except Exception as e:
        return RedirectResponse(f"/campaigns?err_msg={str(e)[:60].encode('ascii','replace').decode()}", 303)


@router.post("/campaigns/channel/refresh_name")
async def campaigns_channel_refresh_name(request: Request, cc_id: int = Form(...),
                                          channel_id: str = Form(...), campaign_id: int = Form(...)):
    """Обновить название канала через бота."""
    user, err = require_auth(request)
    if err: return err
    try:
        b1 = bot_manager.get_tracker_bot()
        if not b1:
            return RedirectResponse("/campaigns?err_msg=%D0%91%D0%BE%D1%82+%D0%BD%D0%B5+%D0%B7%D0%B0%D0%BF%D1%83%D1%89%D0%B5%D0%BD", 303)
        chat    = await b1.get_chat(int(channel_id))
        ch_name = chat.title or channel_id
        with db._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE campaign_channels SET channel_name=%s WHERE id=%s",
                            (ch_name, cc_id))
            conn.commit()
        from urllib.parse import quote_plus as _qp
        return RedirectResponse(f"/campaigns?msg={_qp(f'Название обновлено: {ch_name}')}", 303)
    except Exception as e:
        return RedirectResponse(f"/campaigns?err_msg={str(e)[:80]}", 303)


@router.post("/campaigns/channel/delete")
async def campaigns_channel_delete(request: Request, cc_id: int = Form(...),
                                    campaign_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.remove_campaign_channel(cc_id)
    return RedirectResponse("/campaigns", 303)


@router.post("/campaigns/channel/location")
async def campaigns_channel_location(request: Request, cc_id: int = Form(...),
                                      campaign_id: int = Form(...),
                                      city: str = Form(""), phone: str = Form(""),
                                      address: str = Form(""), tg_label: str = Form(""),
                                      phone_label: str = Form("")):
    """Сохранить город, телефон, адрес и заголовки для канала."""
    user, err = require_auth(request)
    if err: return err
    db.set_campaign_channel_location(
        cc_id, city.strip(), phone.strip(),
        address.strip(), tg_label.strip(), phone_label.strip()
    )
    return RedirectResponse("/campaigns?msg=%D0%9B%D0%BE%D0%BA%D0%B0%D1%86%D0%B8%D1%8F+%D1%81%D0%BE%D1%85%D1%80%D0%B0%D0%BD%D0%B5%D0%BD%D0%B0", 303)
