"""
routers/channels.py — Каналы и кампании

Подключается в main.py:
    channels_setup(db, log, require_auth, base, nav_html, _render_conv_tags_picker, bot_manager)
    app.include_router(channels_router)
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


def setup(_db, _log, _require_auth, _base, _nav_html, _render_conv_tags_picker_fn, _bot_manager):
    global db, log, require_auth, base, nav_html, _render_conv_tags_picker
    db             = _db
    log            = _log
    require_auth   = _require_auth
    base           = _base
    nav_html       = _nav_html
    _render_conv_tags_picker = _render_conv_tags_picker_fn
    global bot_manager
    bot_manager    = _bot_manager


# КАНАЛЫ / КАМПАНИИ / ЛЕНДИНГ / FLOW (без изменений логики)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/channels", response_class=HTMLResponse)
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


@router.get("/campaigns", response_class=HTMLResponse)
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


@router.post("/campaigns/create")
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


@router.post("/campaigns/channel/add")
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


@router.post("/campaigns/channel/delete")
async def campaigns_channel_delete(request: Request, cc_id: int = Form(...), campaign_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.remove_campaign_channel(cc_id)
    return RedirectResponse(f"/campaigns", 303)

