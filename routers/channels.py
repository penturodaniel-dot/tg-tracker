"""
routers/channels.py — Каналы и кампании

Подключается в main.py:
    channels_setup(db, log, require_auth, base, nav_html, _render_conv_tags_picker, bot_manager)
    app.include_router(channels_router)
"""

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter()

# ── Зависимости ───────────────────────────────────────────────────────────────
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
    return RedirectResponse("/channels?msg=Канал+добавлен", 303)


@router.post("/channels/delete")
async def channels_delete(request: Request, channel_id: str = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.delete_channel(channel_id)
    return RedirectResponse("/channels?msg=Удалён", 303)


# ══════════════════════════════════════════════════════════════════════════════
# КАМПАНИИ
# ══════════════════════════════════════════════════════════════════════════════

def _build_campaign_card(c: dict, cchans: list, cphones: list, templates: list,
                          channels: list, app_url: str) -> str:
    """Строит HTML-карточку одной кампании."""
    slug_url = f"{app_url}/l/{c.get('slug', '')}"

    # ── Текущий шаблон ────────────────────────────────────────────────────────
    tpl = next((t for t in templates if t["id"] == c.get("landing_id")), None)
    tpl_badge = (
        f'<span class="badge-green" style="font-size:.71rem">🎨 {tpl["name"]}</span>' if tpl
        else '<span class="badge-gray" style="font-size:.71rem">🎨 Дефолтный</span>'
    )
    tpl_select_opts = '<option value="">— Дефолтный —</option>' + "".join(
        f'<option value="{t["id"]}" {"selected" if t["id"] == c.get("landing_id") else ""}>{t["name"]}</option>'
        for t in templates
    )
    tpl_switch = f"""<form method="post" action="/campaigns/set_template"
        style="display:flex;gap:6px;align-items:center">
      <input type="hidden" name="campaign_id" value="{c['id']}"/>
      <select name="landing_id" style="font-size:.77rem;padding:4px 8px;border-radius:7px;width:auto">
        {tpl_select_opts}
      </select>
      <button class="btn btn-sm" style="font-size:.74rem;padding:5px 10px">Сменить шаблон</button>
    </form>"""

    # ── Строки таблицы каналов ────────────────────────────────────────────────
    chan_rows = ""
    for cc in cchans:
        city_val = cc.get("city") or ""
        cc_id    = cc["id"]
        camp_id  = c["id"]
        city_form = (
            f'<form method="post" action="/campaigns/channel/city"'
            f' style="display:flex;gap:4px;align-items:center">'
            f'<input type="hidden" name="cc_id" value="{cc_id}"/>'
            f'<input type="hidden" name="campaign_id" value="{camp_id}"/>'
            f'<input type="text" name="city" value="{city_val}" placeholder="New York"'
            f' style="width:110px;background:var(--bg);border:1px solid var(--border);'
            f'border-radius:5px;padding:3px 7px;color:var(--text);font-size:.75rem"/>'
            f'<button class="btn-gray btn-sm" style="padding:3px 8px;font-size:.72rem"'
            f' title="Сохранить город">✓</button>'
            f'</form>'
        )
        chan_rows += (
            f'<tr>'
            f'<td style="font-weight:600">{cc.get("channel_name") or cc["channel_id"]}</td>'
            f'<td><div class="link-box" style="font-size:.69rem;padding:5px 9px">'
            f'{cc["invite_link"][:50]}...</div></td>'
            f'<td>{city_form}</td>'
            f'<td style="color:var(--green);font-weight:700">{cc["joins"]}</td>'
            f'<td><form method="post" action="/campaigns/channel/delete" style="display:inline">'
            f'<input type="hidden" name="cc_id" value="{cc_id}"/>'
            f'<input type="hidden" name="campaign_id" value="{camp_id}"/>'
            f'<button class="del-btn btn-sm">✕</button></form></td>'
            f'</tr>'
        )
    if not chan_rows:
        chan_rows = '<tr><td colspan="5"><div class="empty" style="padding:12px">Нет каналов — добавь ниже</div></td></tr>'

    # ── Локации (телефоны) ────────────────────────────────────────────────────
    phones_rows = ""
    for ph in cphones:
        ph_id   = ph["id"]
        camp_id = c["id"]
        phones_rows += (
            f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;'
            f'padding:7px 12px;background:var(--bg3);border-radius:8px;border:1px solid var(--border)">'
            f'<span style="min-width:130px;font-size:.83rem;color:var(--text2);font-weight:600">'
            f'📍 {ph["city"]}</span>'
            f'<span style="font-size:.85rem;font-family:monospace;color:#a5f3fc;flex:1">'
            f'{ph["phone"]}</span>'
            f'<form method="post" action="/campaigns/phone/delete" style="margin:0;flex-shrink:0">'
            f'<input type="hidden" name="phone_id" value="{ph_id}"/>'
            f'<input type="hidden" name="campaign_id" value="{camp_id}"/>'
            f'<button class="del-btn btn-sm" style="padding:2px 7px">✕</button>'
            f'</form></div>'
        )
    if not phones_rows:
        phones_rows = '<div style="color:var(--text3);font-size:.8rem;padding:4px 0">Нет локаций — добавь ниже</div>'

    # ── Опции для select добавления канала ────────────────────────────────────
    ch_opts = "".join(
        f'<option value="{ch["channel_id"]}">{ch["name"]}</option>'
        for ch in channels
    )

    camp_id = c["id"]
    camp_name = c["name"]
    total_joins = c["total_joins"]

    return f"""
    <div class="section" style="border-left:3px solid var(--accent)">
      <div class="section-head">
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
          <h3>🎯 {camp_name}</h3>
          <span class="badge" style="font-size:.72rem">{total_joins} подписок</span>
          {tpl_badge}
        </div>
        <div style="display:flex;gap:8px;align-items:center">
          <a href="{slug_url}" target="_blank" class="btn-gray btn-sm">🌐 Лендинг</a>
          <form method="post" action="/campaigns/delete">
            <input type="hidden" name="campaign_id" value="{camp_id}"/>
            <button class="del-btn">✕</button>
          </form>
        </div>
      </div>
      <div class="section-body">

        <!-- Ссылка в рекламу + смена шаблона -->
        <div style="margin-bottom:16px;padding:10px 14px;background:var(--bg3);
                    border-radius:9px;border:1px solid var(--border)">
          <div style="font-size:.74rem;color:var(--text3);margin-bottom:5px;font-weight:700;
                      text-transform:uppercase;letter-spacing:.05em">🔗 Ссылка в рекламу</div>
          <div class="link-box">{slug_url}</div>
          <div style="margin-top:10px">{tpl_switch}</div>
        </div>

        <!-- Таблица каналов с городами -->
        <div style="font-size:.74rem;font-weight:700;text-transform:uppercase;
                    letter-spacing:.05em;color:var(--text3);margin-bottom:8px">
          📡 Каналы
          <span style="font-size:.68rem;font-weight:400;margin-left:6px;color:var(--text3)">
            Укажи город рядом с каждым каналом — пользователь выберет город и увидит нужный канал
          </span>
        </div>
        <table style="margin-bottom:14px">
          <thead><tr>
            <th>Канал</th><th>Invite Link</th>
            <th>Город (попап)</th><th>Подписок</th><th></th>
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

        <!-- Секция локаций (телефоны) -->
        <div style="margin-top:20px;padding-top:16px;border-top:1px solid var(--border)">
          <div style="font-size:.74rem;font-weight:700;text-transform:uppercase;
                      letter-spacing:.05em;color:var(--text3);margin-bottom:4px">
            📞 Локации — телефоны
          </div>
          <div style="font-size:.73rem;color:var(--text3);margin-bottom:12px;line-height:1.5">
            Пользователь выбирает город в попапе → видит телефон и каналы этого города.
            Город в телефоне должен совпадать с городом у канала выше.
          </div>
          <div style="margin-bottom:12px">{phones_rows}</div>
          <form method="post" action="/campaigns/phone/add">
            <input type="hidden" name="campaign_id" value="{camp_id}"/>
            <div class="form-row">
              <div class="field-group" style="max-width:180px">
                <div class="field-label">Город</div>
                <input type="text" name="city" placeholder="New York" required
                       style="font-size:.83rem"/>
              </div>
              <div class="field-group" style="max-width:220px">
                <div class="field-label">Телефон</div>
                <input type="text" name="phone" placeholder="+1 212 555-0100" required
                       style="font-size:.83rem"/>
              </div>
              <div style="display:flex;align-items:flex-end">
                <button class="btn btn-sm">+ Добавить локацию</button>
              </div>
            </div>
          </form>
        </div>

      </div>
    </div>"""


@router.get("/campaigns", response_class=HTMLResponse)
async def campaigns_page(request: Request, msg: str = "", err_msg: str = ""):
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
        cchans  = db.get_campaign_channels(c["id"])
        cphones = db.get_campaign_phones(c["id"])
        campaign_cards += _build_campaign_card(c, cchans, cphones, templates, channels, app_url)

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
        return RedirectResponse(f"/campaigns?msg=Кампания+{name}+создана", 303)
    except Exception as e:
        return RedirectResponse(f"/campaigns?err_msg={str(e)}", 303)


@router.post("/campaigns/set_template")
async def campaigns_set_template(request: Request, campaign_id: int = Form(...),
                                  landing_id: str = Form("")):
    user, err = require_auth(request)
    if err: return err
    lid = int(landing_id) if landing_id.strip().isdigit() else None
    db.update_campaign_landing(campaign_id, lid)
    return RedirectResponse("/campaigns?msg=Шаблон+обновлён", 303)


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
            return RedirectResponse("/campaigns?err_msg=Бот+1+не+запущен", 303)
        link_name = f"{campaign_name[:20]}_{channel_id[-6:]}"
        link_obj  = await b1.create_chat_invite_link(chat_id=int(channel_id), name=link_name[:32])
        try:
            chat    = await b1.get_chat(int(channel_id))
            ch_name = chat.title or channel_id
        except Exception:
            ch_name = channel_id
        db.add_campaign_channel(campaign_id, channel_id, ch_name, link_obj.invite_link)
        return RedirectResponse("/campaigns?msg=Канал+добавлен+в+кампанию", 303)
    except Exception as e:
        return RedirectResponse(f"/campaigns?err_msg={str(e)}", 303)


@router.post("/campaigns/channel/delete")
async def campaigns_channel_delete(request: Request, cc_id: int = Form(...),
                                    campaign_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.remove_campaign_channel(cc_id)
    return RedirectResponse("/campaigns", 303)


@router.post("/campaigns/channel/city")
async def campaigns_channel_city(request: Request, cc_id: int = Form(...),
                                  campaign_id: int = Form(...), city: str = Form("")):
    """Сохранить город для канала внутри кампании."""
    user, err = require_auth(request)
    if err: return err
    db.set_campaign_channel_city(cc_id, city.strip())
    return RedirectResponse("/campaigns?msg=Город+сохранён", 303)


# ── Телефоны / локации кампании ───────────────────────────────────────────────

@router.post("/campaigns/phone/add")
async def campaigns_phone_add(request: Request, campaign_id: int = Form(...),
                               city: str = Form(...), phone: str = Form(...)):
    """Добавить локацию (город + телефон) к кампании."""
    user, err = require_auth(request)
    if err: return err
    db.add_campaign_phone(campaign_id, city.strip(), phone.strip())
    return RedirectResponse("/campaigns?msg=Локация+добавлена", 303)


@router.post("/campaigns/phone/delete")
async def campaigns_phone_delete(request: Request, phone_id: int = Form(...),
                                  campaign_id: int = Form(...)):
    """Удалить локацию из кампании."""
    user, err = require_auth(request)
    if err: return err
    db.delete_campaign_phone(phone_id)
    return RedirectResponse("/campaigns?msg=Локация+удалена", 303)
