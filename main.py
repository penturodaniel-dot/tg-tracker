import asyncio
import logging
import os
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher, types
from aiogram.filters import ChatMemberUpdatedFilter, JOIN_TRANSITION
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
import uvicorn

from database import Database
from meta_capi import send_subscribe_event

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
SECRET    = os.getenv("DASHBOARD_PASSWORD", "changeme")

# Pixel из env — только начальные значения, потом берём из БД
DEFAULT_PIXEL_ID   = os.getenv("PIXEL_ID", "")
DEFAULT_META_TOKEN = os.getenv("META_TOKEN", "")

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher()
db  = Database()

# Инициализируем настройки из env если БД пустая
if not db.get_setting("pixel_id") and DEFAULT_PIXEL_ID:
    db.set_setting("pixel_id", DEFAULT_PIXEL_ID)
if not db.get_setting("meta_token") and DEFAULT_META_TOKEN:
    db.set_setting("meta_token", DEFAULT_META_TOKEN)


# ── BOT HANDLERS ─────────────────────────────────────────────────────────────

@dp.chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def on_user_join(event: types.ChatMemberUpdated):
    channel_ids = db.get_channel_ids()
    cid = str(event.chat.id)
    if cid not in channel_ids:
        return

    user         = event.new_chat_member.user
    raw_link     = event.invite_link.invite_link if event.invite_link else None
    campaign     = db.get_campaign_by_link(raw_link)
    campaign_name = campaign["name"] if campaign else "organic"

    db.log_join(user_id=user.id, channel_id=cid, invite_link=raw_link, campaign_name=campaign_name)
    log.info(f"JOIN user={user.id} channel={cid} campaign={campaign_name}")

    # Отправляем в Meta
    pixel_id    = db.get_setting("pixel_id")
    meta_token  = db.get_setting("meta_token")
    await send_subscribe_event(pixel_id, meta_token, str(user.id), campaign_name)

    # Message Flow — шаг 0 (сразу после вступления)
    asyncio.create_task(send_flow_messages(user.id, cid))


async def send_flow_messages(user_id: int, channel_id: str):
    flows = db.get_flows(channel_id)
    for flow in flows:
        if not flow["active"]:
            continue
        if db.was_flow_sent(user_id, channel_id, flow["step"]):
            continue
        if flow["delay_min"] > 0:
            await asyncio.sleep(flow["delay_min"] * 60)
        try:
            await bot.send_message(user_id, flow["message"])
            db.log_flow_sent(user_id, channel_id, flow["step"])
            log.info(f"Flow sent user={user_id} step={flow['step']}")
        except Exception as e:
            log.warning(f"Flow send error user={user_id}: {e}")


# ── LIFESPAN ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(dp.start_polling(bot, allowed_updates=["chat_member"]))
    log.info("Bot polling started")
    yield
    await bot.session.close()


app = FastAPI(lifespan=lifespan)


# ══════════════════════════════════════════════════════════════════════════════
# HTML HELPERS
# ══════════════════════════════════════════════════════════════════════════════

CSS = """
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:#0a0d14;color:#e2e8f0;min-height:100vh}
a{color:inherit;text-decoration:none}
.sidebar{position:fixed;top:0;left:0;width:220px;height:100vh;background:#0f1219;border-right:1px solid #1e2535;padding:24px 0;z-index:10}
.sidebar .logo{padding:0 20px 24px;font-size:1.1rem;font-weight:700;color:#fff;border-bottom:1px solid #1e2535}
.sidebar .logo span{color:#3b82f6}
.nav-item{display:flex;align-items:center;gap:10px;padding:11px 20px;font-size:.88rem;color:#94a3b8;cursor:pointer;transition:all .15s}
.nav-item:hover,.nav-item.active{background:#1a2030;color:#fff}
.nav-item.active{border-right:2px solid #3b82f6}
.main{margin-left:220px;padding:32px}
.page-title{font-size:1.4rem;font-weight:700;color:#fff;margin-bottom:6px}
.page-sub{font-size:.85rem;color:#64748b;margin-bottom:28px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin-bottom:32px}
.card{background:#111827;border:1px solid #1e2535;border-radius:12px;padding:20px}
.card .val{font-size:1.9rem;font-weight:700;color:#60a5fa}
.card .lbl{font-size:.78rem;color:#64748b;margin-top:4px}
.section{background:#111827;border:1px solid #1e2535;border-radius:12px;margin-bottom:20px;overflow:hidden}
.section-head{padding:16px 20px;border-bottom:1px solid #1e2535;display:flex;justify-content:space-between;align-items:center}
.section-head h3{font-size:.95rem;font-weight:600;color:#e2e8f0}
.section-body{padding:20px}
table{width:100%;border-collapse:collapse}
th{padding:10px 14px;text-align:left;font-size:.75rem;text-transform:uppercase;color:#64748b;letter-spacing:.05em;border-bottom:1px solid #1e2535}
td{padding:11px 14px;font-size:.86rem;border-bottom:1px solid #0f1219}
tr:last-child td{border-bottom:none}
.badge{display:inline-block;padding:2px 10px;border-radius:20px;font-size:.75rem;background:#1e3a5f;color:#60a5fa}
.badge-green{background:#052e16;color:#34d399}
.badge-red{background:#2d0a0a;color:#f87171}
.form-row{display:flex;gap:10px;flex-wrap:wrap}
input[type=text],input[type=number],select,textarea{background:#0a0d14;border:1px solid #1e2535;border-radius:8px;padding:9px 14px;color:#e2e8f0;font-size:.88rem;outline:none;width:100%}
input[type=text]:focus,input[type=number]:focus,select:focus,textarea:focus{border-color:#3b82f6}
textarea{resize:vertical;min-height:80px;font-family:system-ui}
.btn{background:#3b82f6;color:#fff;border:none;border-radius:8px;padding:9px 20px;cursor:pointer;font-size:.88rem;font-weight:600;white-space:nowrap}
.btn:hover{background:#2563eb}
.btn-red{background:#dc2626}.btn-red:hover{background:#b91c1c}
.btn-gray{background:#1e2535;color:#94a3b8}.btn-gray:hover{background:#2d3748;color:#fff}
.link-box{background:#0a0d14;border:1px solid #1e2535;border-radius:6px;padding:8px 12px;font-family:monospace;font-size:.8rem;word-break:break-all;color:#a5f3fc}
.alert-green{background:#052e16;border:1px solid #166534;border-radius:8px;padding:12px 16px;color:#86efac;margin-bottom:16px;font-size:.88rem}
.alert-red{background:#2d0a0a;border:1px solid #7f1d1d;border-radius:8px;padding:12px 16px;color:#fca5a5;margin-bottom:16px;font-size:.88rem}
.empty{text-align:center;padding:28px;color:#475569;font-size:.88rem}
.tag{display:inline-block;background:#1e2535;border-radius:4px;padding:2px 8px;font-size:.75rem;color:#94a3b8;font-family:monospace}
.del-btn{background:none;border:none;cursor:pointer;color:#ef4444;font-size:.88rem;padding:4px 8px;border-radius:4px}
.del-btn:hover{background:#2d0a0a}
.field-group{display:flex;flex-direction:column;gap:6px;flex:1}
.field-label{font-size:.78rem;color:#64748b;font-weight:500}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:700px){.sidebar{width:100%;height:auto;position:relative}.main{margin-left:0}.grid-2{grid-template-columns:1fr}}
</style>
"""

NAV = [
    ("📊", "Обзор",       "overview"),
    ("📡", "Каналы",      "channels"),
    ("🔗", "Кампании",    "campaigns"),
    ("🌐", "Лендинг",     "landing"),
    ("💬", "Message Flow","flow"),
    ("⚙️",  "Настройки",  "settings"),
]

def nav_html(active: str, key: str) -> str:
    items = ""
    for icon, label, page in NAV:
        cls = "nav-item active" if page == active else "nav-item"
        items += f'<a href="/{page}?key={key}" class="{cls}">{icon} {label}</a>'
    return f"""
    <div class="sidebar">
      <div class="logo">📡 TG<span>Tracker</span></div>
      {items}
    </div>"""

def base(content: str, active: str, key: str) -> str:
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>TG Tracker</title>{CSS}</head>
    <body>{nav_html(active, key)}<div class="main">{content}</div></body></html>"""

def auth_check(key: str):
    if key != SECRET:
        return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Login</title>{CSS}</head>
        <body><div style="max-width:340px;margin:80px auto">
        <div class="page-title" style="margin-bottom:20px">🔐 TG Tracker</div>
        <form method="get"><div class="form-row"><input type="text" name="key" placeholder="Пароль"/>
        <button class="btn" type="submit">Войти</button></div></form></div></body></html>""", status_code=401)
    return None


# ══════════════════════════════════════════════════════════════════════════════
# PAGES
# ══════════════════════════════════════════════════════════════════════════════

# ── OVERVIEW ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
@app.get("/overview", response_class=HTMLResponse)
async def overview(key: str = ""):
    err = auth_check(key)
    if err: return err

    s = db.get_stats()
    joins = db.get_recent_joins(30)

    rows = "".join(f"""<tr>
        <td>{j['joined_at'][:16].replace('T',' ')}</td>
        <td><span class="tag">{j.get('channel_id','—')}</span></td>
        <td><span class="badge">{j['campaign_name']}</span></td>
    </tr>""" for j in joins) or f'<tr><td colspan="3"><div class="empty">Подписчиков пока нет</div></td></tr>'

    pixel = db.get_setting("pixel_id", "—")

    content = f"""
    <div class="page-title">📊 Обзор</div>
    <div class="page-sub">Статистика по всем каналам</div>
    <div class="cards">
      <div class="card"><div class="val">{s['total']}</div><div class="lbl">Всего подписчиков</div></div>
      <div class="card"><div class="val">{s['from_ads']}</div><div class="lbl">Из рекламы</div></div>
      <div class="card"><div class="val">{s['organic']}</div><div class="lbl">Органика</div></div>
      <div class="card"><div class="val">{s['channels']}</div><div class="lbl">Каналов</div></div>
      <div class="card"><div class="val">{s['campaigns']}</div><div class="lbl">Кампаний</div></div>
    </div>
    <div class="section">
      <div class="section-head"><h3>🕐 Последние подписки</h3><span class="tag">Pixel: {pixel}</span></div>
      <table><thead><tr><th>Время</th><th>Канал ID</th><th>Кампания</th></tr></thead>
      <tbody>{rows}</tbody></table>
    </div>"""
    return HTMLResponse(base(content, "overview", key))


# ── CHANNELS ──────────────────────────────────────────────────────────────────

@app.get("/channels", response_class=HTMLResponse)
async def channels_page(key: str = "", msg: str = "", err: str = ""):
    r = auth_check(key)
    if r: return r

    channels = db.get_channels()
    bot_info = await bot.get_me()
    bot_link = f"https://t.me/{bot_info.username}"

    rows = "".join(f"""<tr>
        <td><b>{c['name']}</b></td>
        <td><span class="tag">{c['channel_id']}</span></td>
        <td style="color:#34d399;font-weight:600">{c['total_joins']}</td>
        <td>{c['created_at'][:10]}</td>
        <td><form method="post" action="/channels/delete?key={key}" style="display:inline">
            <input type="hidden" name="channel_id" value="{c['channel_id']}"/>
            <button class="del-btn" type="submit">✕ Удалить</button></form></td>
    </tr>""" for c in channels) or '<tr><td colspan="5"><div class="empty">Каналов ещё нет — добавь первый ниже 👇</div></td></tr>'

    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else (f'<div class="alert-red">❌ {err}</div>' if err else "")

    content = f"""
    <div class="page-title">📡 Каналы</div>
    <div class="page-sub">Управление Telegram-каналами</div>

    <div class="section">
      <div class="section-head"><h3>🤖 Ссылка на бота</h3></div>
      <div class="section-body">
        <p style="color:#94a3b8;font-size:.88rem;margin-bottom:10px">
          Добавь этого бота в каждый канал как <b style="color:#fff">Администратора</b> (достаточно права видеть участников):
        </p>
        <div class="link-box">{bot_link}</div>
      </div>
    </div>

    <div class="section">
      <div class="section-head"><h3>➕ Добавить канал</h3></div>
      <div class="section-body">
        {alert}
        <form method="post" action="/channels/add?key={key}">
          <div class="form-row">
            <div class="field-group">
              <div class="field-label">Название канала</div>
              <input type="text" name="name" placeholder="Например: Phoenix" required/>
            </div>
            <div class="field-group">
              <div class="field-label">ID канала (со знаком минус)</div>
              <input type="text" name="channel_id" placeholder="-1003835844880" required/>
            </div>
            <div style="display:flex;align-items:flex-end">
              <button class="btn" type="submit">Добавить</button>
            </div>
          </div>
        </form>
        <p style="color:#475569;font-size:.8rem;margin-top:10px">
          💡 Узнать ID канала: перешли любое сообщение из канала боту <b>@userinfobot</b>
        </p>
      </div>
    </div>

    <div class="section">
      <div class="section-head"><h3>📋 Мои каналы ({len(channels)})</h3></div>
      <table><thead><tr><th>Название</th><th>ID канала</th><th>Подписчиков</th><th>Добавлен</th><th></th></tr></thead>
      <tbody>{rows}</tbody></table>
    </div>"""
    return HTMLResponse(base(content, "channels", key))


@app.post("/channels/add")
async def channels_add(key: str = "", name: str = Form(...), channel_id: str = Form(...)):
    if key != SECRET: return RedirectResponse(f"/?key={key}", 303)
    try:
        db.add_channel(name.strip(), channel_id.strip())
        return RedirectResponse(f"/channels?key={key}&msg=Канал+добавлен", 303)
    except Exception as e:
        return RedirectResponse(f"/channels?key={key}&err={str(e)}", 303)


@app.post("/channels/delete")
async def channels_delete(key: str = "", channel_id: str = Form(...)):
    if key != SECRET: return RedirectResponse(f"/?key={key}", 303)
    db.delete_channel(channel_id)
    return RedirectResponse(f"/channels?key={key}&msg=Канал+удалён", 303)


# ── CAMPAIGNS ─────────────────────────────────────────────────────────────────

@app.get("/campaigns", response_class=HTMLResponse)
async def campaigns_page(key: str = "", msg: str = "", err: str = ""):
    r = auth_check(key)
    if r: return r

    channels  = db.get_channels()
    campaigns = db.get_campaigns()

    ch_opts = "".join(f'<option value="{c["channel_id"]}">{c["name"]} ({c["channel_id"]})</option>' for c in channels)
    if not ch_opts:
        ch_opts = '<option disabled>Сначала добавь каналы</option>'

    rows = "".join(f"""<tr>
        <td><span class="badge">{c['name']}</span></td>
        <td><span class="tag" style="font-size:.7rem">{c['channel_id']}</span></td>
        <td><div class="link-box" style="max-width:280px">{c['invite_link']}</div></td>
        <td style="color:#34d399;font-weight:600">{c['joins']}</td>
        <td>{c['created_at'][:10]}</td>
    </tr>""" for c in campaigns) or '<tr><td colspan="5"><div class="empty">Кампаний нет — создай первую 👆</div></td></tr>'

    new_link = msg if msg.startswith("https://") else ""
    alert = f'<div class="alert-green">✅ Ссылка создана! Вставь в рекламу:<div class="link-box" style="margin-top:8px">{new_link}</div></div>' if new_link else (f'<div class="alert-red">❌ {err}</div>' if err else "")

    content = f"""
    <div class="page-title">🔗 Кампании</div>
    <div class="page-sub">Создавай отдельную ссылку под каждую рекламную кампанию</div>
    {alert}
    <div class="section">
      <div class="section-head"><h3>➕ Создать ссылку</h3></div>
      <div class="section-body">
        <form method="post" action="/campaigns/create?key={key}">
          <div class="form-row">
            <div class="field-group">
              <div class="field-label">Канал</div>
              <select name="channel_id" required>{ch_opts}</select>
            </div>
            <div class="field-group">
              <div class="field-label">Название кампании</div>
              <input type="text" name="name" placeholder="FB_Broad_March" required/>
            </div>
            <div style="display:flex;align-items:flex-end">
              <button class="btn" type="submit">Создать</button>
            </div>
          </div>
        </form>
      </div>
    </div>
    <div class="section">
      <div class="section-head"><h3>📋 Все кампании ({len(campaigns)})</h3></div>
      <table><thead><tr><th>Кампания</th><th>Канал</th><th>Invite Link</th><th>Подписчиков</th><th>Создана</th></tr></thead>
      <tbody>{rows}</tbody></table>
    </div>"""
    return HTMLResponse(base(content, "campaigns", key))


@app.post("/campaigns/create")
async def campaigns_create(key: str = "", channel_id: str = Form(...), name: str = Form(...)):
    if key != SECRET: return RedirectResponse(f"/?key={key}", 303)
    try:
        link_obj = await bot.create_chat_invite_link(chat_id=int(channel_id), name=name[:32])
        db.save_campaign(name=name, channel_id=channel_id, invite_link=link_obj.invite_link)
        return RedirectResponse(f"/campaigns?key={key}&msg={link_obj.invite_link}", 303)
    except Exception as e:
        return RedirectResponse(f"/campaigns?key={key}&err={str(e)}", 303)


# ── LANDING ───────────────────────────────────────────────────────────────────

@app.get("/landing", response_class=HTMLResponse)
async def landing_admin(key: str = "", msg: str = ""):
    r = auth_check(key)
    if r: return r

    links = db.get_landing_links()
    preview_url = f"/page"

    rows = "".join(f"""<tr>
        <td style="font-size:1.3rem">{l['emoji']}</td>
        <td><b>{l['title']}</b></td>
        <td><a href="{l['tg_link']}" target="_blank" style="color:#60a5fa">{l['tg_link']}</a></td>
        <td><form method="post" action="/landing/delete?key={key}" style="display:inline">
            <input type="hidden" name="link_id" value="{l['id']}"/>
            <button class="del-btn">✕</button></form></td>
    </tr>""" for l in links) or '<tr><td colspan="4"><div class="empty">Ссылок нет — добавь первую</div></td></tr>'

    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""

    content = f"""
    <div class="page-title">🌐 Лендинг</div>
    <div class="page-sub">Публичная страница с кнопками на твои каналы</div>

    <div class="section">
      <div class="section-head"><h3>👁 Публичная страница</h3></div>
      <div class="section-body">
        <p style="color:#94a3b8;font-size:.88rem;margin-bottom:10px">Рекламируй эту ссылку — люди увидят все твои каналы:</p>
        <div class="link-box">{preview_url}</div>
        <a href="/page" target="_blank"><button class="btn btn-gray" style="margin-top:10px">Открыть страницу →</button></a>
      </div>
    </div>

    <div class="section">
      <div class="section-head"><h3>➕ Добавить ссылку</h3></div>
      <div class="section-body">
        {alert}
        <form method="post" action="/landing/add?key={key}">
          <div class="form-row">
            <div class="field-group" style="max-width:80px">
              <div class="field-label">Эмодзи</div>
              <input type="text" name="emoji" value="📢" style="text-align:center"/>
            </div>
            <div class="field-group">
              <div class="field-label">Название кнопки</div>
              <input type="text" name="title" placeholder="Канал Phoenix" required/>
            </div>
            <div class="field-group">
              <div class="field-label">Ссылка на канал</div>
              <input type="text" name="tg_link" placeholder="https://t.me/+xxxxxxxx" required/>
            </div>
            <div style="display:flex;align-items:flex-end">
              <button class="btn" type="submit">Добавить</button>
            </div>
          </div>
        </form>
      </div>
    </div>

    <div class="section">
      <div class="section-head"><h3>🔗 Кнопки ({len(links)} / 10)</h3></div>
      <table><thead><tr><th></th><th>Название</th><th>Ссылка</th><th></th></tr></thead>
      <tbody>{rows}</tbody></table>
    </div>"""
    return HTMLResponse(base(content, "landing", key))


@app.post("/landing/add")
async def landing_add(key: str = "", title: str = Form(...), tg_link: str = Form(...), emoji: str = Form("📢")):
    if key != SECRET: return RedirectResponse(f"/landing?key={key}", 303)
    links = db.get_landing_links()
    if len(links) >= 10:
        return RedirectResponse(f"/landing?key={key}&msg=Максимум+10+ссылок", 303)
    db.add_landing_link(title.strip(), tg_link.strip(), emoji.strip() or "📢")
    return RedirectResponse(f"/landing?key={key}&msg=Ссылка+добавлена", 303)


@app.post("/landing/delete")
async def landing_delete(key: str = "", link_id: int = Form(...)):
    if key != SECRET: return RedirectResponse(f"/landing?key={key}", 303)
    db.delete_landing_link(link_id)
    return RedirectResponse(f"/landing?key={key}&msg=Удалено", 303)


# ── PUBLIC LANDING PAGE ───────────────────────────────────────────────────────

@app.get("/page", response_class=HTMLResponse)
async def public_page():
    links = db.get_landing_links()
    site_title = db.get_setting("landing_title", "Наши каналы")
    site_sub   = db.get_setting("landing_subtitle", "Подписывайся и будь в курсе")

    btns = "".join(f"""
    <a href="{l['tg_link']}" target="_blank" class="ch-btn">
      <span class="ch-emoji">{l['emoji']}</span>
      <span class="ch-title">{l['title']}</span>
      <span class="ch-arrow">→</span>
    </a>""" for l in links) or '<p style="color:#555;text-align:center">Каналов пока нет</p>'

    return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>{site_title}</title>
    <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{background:#0a0d14;color:#e2e8f0;min-height:100vh;display:flex;align-items:center;justify-content:center;font-family:system-ui,sans-serif;padding:24px}}
    .wrap{{width:100%;max-width:420px}}
    h1{{font-size:1.6rem;font-weight:700;text-align:center;color:#fff;margin-bottom:8px}}
    .sub{{text-align:center;color:#64748b;font-size:.9rem;margin-bottom:32px}}
    .ch-btn{{display:flex;align-items:center;gap:14px;background:#111827;border:1px solid #1e2535;border-radius:14px;padding:16px 20px;margin-bottom:12px;transition:all .2s;cursor:pointer}}
    .ch-btn:hover{{background:#1a2030;border-color:#3b82f6;transform:translateY(-2px)}}
    .ch-emoji{{font-size:1.6rem;flex-shrink:0}}
    .ch-title{{flex:1;font-size:1rem;font-weight:600;color:#fff}}
    .ch-arrow{{color:#3b82f6;font-size:1.2rem}}
    </style></head><body>
    <div class="wrap">
      <h1>{site_title}</h1>
      <p class="sub">{site_sub}</p>
      {btns}
    </div></body></html>""")


# ── SETTINGS for landing title/subtitle ───────────────────────────────────────

@app.post("/landing/settings")
async def landing_settings(key: str = "", landing_title: str = Form(""), landing_subtitle: str = Form("")):
    if key != SECRET: return RedirectResponse(f"/landing?key={key}", 303)
    if landing_title: db.set_setting("landing_title", landing_title)
    if landing_subtitle: db.set_setting("landing_subtitle", landing_subtitle)
    return RedirectResponse(f"/landing?key={key}&msg=Настройки+сохранены", 303)


# ── MESSAGE FLOW ──────────────────────────────────────────────────────────────

@app.get("/flow", response_class=HTMLResponse)
async def flow_page(key: str = "", msg: str = ""):
    r = auth_check(key)
    if r: return r

    channels = db.get_channels()
    flows    = db.get_flows()

    ch_opts = "".join(f'<option value="{c["channel_id"]}">{c["name"]}</option>' for c in channels)
    if not ch_opts:
        ch_opts = '<option disabled>Сначала добавь каналы</option>'

    ch_map = {c["channel_id"]: c["name"] for c in channels}

    rows = "".join(f"""<tr>
        <td><span class="badge">{ch_map.get(f['channel_id'], f['channel_id'])}</span></td>
        <td>Шаг {f['step']}</td>
        <td>{f['delay_min']} мин</td>
        <td style="max-width:300px;word-break:break-word">{f['message'][:80]}{'…' if len(f['message'])>80 else ''}</td>
        <td><form method="post" action="/flow/delete?key={key}" style="display:inline">
            <input type="hidden" name="flow_id" value="{f['id']}"/>
            <button class="del-btn">✕</button></form></td>
    </tr>""" for f in flows) or '<tr><td colspan="5"><div class="empty">Нет шагов — добавь первый</div></td></tr>'

    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""

    content = f"""
    <div class="page-title">💬 Message Flow</div>
    <div class="page-sub">Автоматические сообщения новым подписчикам</div>

    <div class="section">
      <div class="section-head"><h3>ℹ️ Как работает</h3></div>
      <div class="section-body" style="color:#94a3b8;font-size:.88rem;line-height:1.8">
        Когда человек вступает в канал — бот отправляет ему личное сообщение.<br>
        Можно настроить серию: сразу, через 30 мин, через 1 час, через 24 часа.<br>
        <b style="color:#fbbf24">⚠️ Важно:</b> бот может писать только тем, кто первым написал боту (/start).
      </div>
    </div>

    <div class="section">
      <div class="section-head"><h3>➕ Добавить шаг</h3></div>
      <div class="section-body">
        {alert}
        <form method="post" action="/flow/add?key={key}">
          <div class="form-row" style="margin-bottom:12px">
            <div class="field-group">
              <div class="field-label">Канал</div>
              <select name="channel_id" required>{ch_opts}</select>
            </div>
            <div class="field-group" style="max-width:100px">
              <div class="field-label">Шаг №</div>
              <input type="number" name="step" value="0" min="0" max="20"/>
            </div>
            <div class="field-group" style="max-width:140px">
              <div class="field-label">Задержка (минуты)</div>
              <input type="number" name="delay_min" value="0" min="0"/>
            </div>
          </div>
          <div class="field-group" style="margin-bottom:12px">
            <div class="field-label">Текст сообщения</div>
            <textarea name="message" placeholder="Привет! Спасибо что подписался 👋&#10;&#10;Вот что тебя ждёт в канале..." required></textarea>
          </div>
          <button class="btn" type="submit">Добавить шаг</button>
        </form>
      </div>
    </div>

    <div class="section">
      <div class="section-head"><h3>📋 Шаги ({len(flows)})</h3></div>
      <table><thead><tr><th>Канал</th><th>Шаг</th><th>Задержка</th><th>Сообщение</th><th></th></tr></thead>
      <tbody>{rows}</tbody></table>
    </div>"""
    return HTMLResponse(base(content, "flow", key))


@app.post("/flow/add")
async def flow_add(key: str = "", channel_id: str = Form(...), step: int = Form(0),
                   delay_min: int = Form(0), message: str = Form(...)):
    if key != SECRET: return RedirectResponse(f"/flow?key={key}", 303)
    db.add_flow_step(channel_id, step, delay_min, message)
    return RedirectResponse(f"/flow?key={key}&msg=Шаг+добавлен", 303)


@app.post("/flow/delete")
async def flow_delete(key: str = "", flow_id: int = Form(...)):
    if key != SECRET: return RedirectResponse(f"/flow?key={key}", 303)
    db.delete_flow_step(flow_id)
    return RedirectResponse(f"/flow?key={key}&msg=Удалено", 303)


# ── SETTINGS ──────────────────────────────────────────────────────────────────

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(key: str = "", msg: str = ""):
    r = auth_check(key)
    if r: return r

    pixel_id   = db.get_setting("pixel_id")
    meta_token = db.get_setting("meta_token")
    land_title = db.get_setting("landing_title", "Наши каналы")
    land_sub   = db.get_setting("landing_subtitle", "Подписывайся и будь в курсе")
    bot_info   = await bot.get_me()

    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""

    masked_token = meta_token[:12] + "..." + meta_token[-6:] if len(meta_token) > 20 else meta_token

    content = f"""
    <div class="page-title">⚙️ Настройки</div>
    <div class="page-sub">Пиксель, токены и параметры лендинга</div>
    {alert}

    <div class="section">
      <div class="section-head"><h3>📡 Meta Pixel & CAPI</h3></div>
      <div class="section-body">
        <form method="post" action="/settings/pixel?key={key}">
          <div class="grid-2" style="margin-bottom:12px">
            <div class="field-group">
              <div class="field-label">Pixel ID</div>
              <input type="text" name="pixel_id" value="{pixel_id}" placeholder="876260075247607"/>
            </div>
            <div class="field-group">
              <div class="field-label">Access Token (текущий: {masked_token})</div>
              <input type="text" name="meta_token" placeholder="Вставь новый токен (оставь пустым чтобы не менять)"/>
            </div>
          </div>
          <button class="btn" type="submit">💾 Сохранить пиксель</button>
        </form>
      </div>
    </div>

    <div class="section">
      <div class="section-head"><h3>🌐 Настройки лендинга</h3></div>
      <div class="section-body">
        <form method="post" action="/settings/landing?key={key}">
          <div class="grid-2" style="margin-bottom:12px">
            <div class="field-group">
              <div class="field-label">Заголовок страницы</div>
              <input type="text" name="landing_title" value="{land_title}"/>
            </div>
            <div class="field-group">
              <div class="field-label">Подзаголовок</div>
              <input type="text" name="landing_subtitle" value="{land_sub}"/>
            </div>
          </div>
          <button class="btn" type="submit">💾 Сохранить</button>
        </form>
      </div>
    </div>

    <div class="section">
      <div class="section-head"><h3>🤖 Информация о боте</h3></div>
      <div class="section-body" style="color:#94a3b8;font-size:.88rem;line-height:2">
        <b style="color:#fff">Имя:</b> {bot_info.full_name}<br>
        <b style="color:#fff">Username:</b> @{bot_info.username}<br>
        <b style="color:#fff">ID:</b> {bot_info.id}
      </div>
    </div>"""
    return HTMLResponse(base(content, "settings", key))


@app.post("/settings/pixel")
async def settings_pixel(key: str = "", pixel_id: str = Form(""), meta_token: str = Form("")):
    if key != SECRET: return RedirectResponse(f"/settings?key={key}", 303)
    if pixel_id.strip():  db.set_setting("pixel_id",   pixel_id.strip())
    if meta_token.strip(): db.set_setting("meta_token", meta_token.strip())
    return RedirectResponse(f"/settings?key={key}&msg=Пиксель+обновлён", 303)


@app.post("/settings/landing")
async def settings_landing(key: str = "", landing_title: str = Form(""), landing_subtitle: str = Form("")):
    if key != SECRET: return RedirectResponse(f"/settings?key={key}", 303)
    if landing_title:    db.set_setting("landing_title",    landing_title)
    if landing_subtitle: db.set_setting("landing_subtitle", landing_subtitle)
    return RedirectResponse(f"/settings?key={key}&msg=Лендинг+обновлён", 303)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
