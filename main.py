import asyncio
import logging
import os
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher, types
from aiogram.filters import ChatMemberUpdatedFilter, JOIN_TRANSITION
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import uvicorn

from database import Database
from meta_capi import send_lead_event

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── ENV ──────────────────────────────────────────────────────────────────────
BOT_TOKEN  = os.environ["BOT_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])
PIXEL_ID   = os.environ["PIXEL_ID"]
META_TOKEN = os.environ["META_TOKEN"]
SECRET     = os.getenv("DASHBOARD_PASSWORD", "changeme")

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher()
db  = Database()

# ── BOT: отслеживаем вступления ───────────────────────────────────────────────
@dp.chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def on_user_join(event: types.ChatMemberUpdated):
    if event.chat.id != CHANNEL_ID:
        return

    user         = event.new_chat_member.user
    raw_link     = event.invite_link.invite_link if event.invite_link else None
    campaign     = db.get_campaign_by_link(raw_link)
    campaign_name = campaign["name"] if campaign else "organic"

    db.log_join(user_id=user.id, invite_link=raw_link, campaign_name=campaign_name)
    log.info(f"JOIN user={user.id} campaign={campaign_name}")

    ok = await send_lead_event(
        pixel_id=PIXEL_ID,
        access_token=META_TOKEN,
        user_id=str(user.id),
        campaign=campaign_name,
    )
    log.info(f"Meta CAPI {'OK' if ok else 'ERROR'} campaign={campaign_name}")


# ── LIFESPAN: запускаем бота вместе с FastAPI ─────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(dp.start_polling(bot, allowed_updates=["chat_member"]))
    log.info("Bot polling started")
    yield
    await bot.session.close()


app = FastAPI(lifespan=lifespan)


# ── DASHBOARD ─────────────────────────────────────────────────────────────────
STYLE = """
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:system-ui,sans-serif;background:#0f1117;color:#e2e8f0;min-height:100vh;padding:32px 16px}
  .wrap{max-width:860px;margin:0 auto}
  h1{font-size:1.6rem;font-weight:700;margin-bottom:4px;color:#fff}
  .sub{color:#64748b;font-size:.85rem;margin-bottom:28px}
  .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:32px}
  .card{background:#1e2330;border:1px solid #2d3548;border-radius:12px;padding:20px}
  .card .val{font-size:2rem;font-weight:700;color:#60a5fa}
  .card .lbl{font-size:.8rem;color:#64748b;margin-top:4px}
  table{width:100%;border-collapse:collapse;background:#1e2330;border-radius:12px;overflow:hidden;border:1px solid #2d3548}
  th{background:#161b27;padding:12px 16px;text-align:left;font-size:.78rem;text-transform:uppercase;color:#64748b;letter-spacing:.05em}
  td{padding:12px 16px;border-top:1px solid #2d3548;font-size:.88rem}
  .badge{display:inline-block;padding:2px 10px;border-radius:20px;font-size:.75rem;background:#1e3a5f;color:#60a5fa}
  .form-row{display:flex;gap:10px;margin-bottom:32px}
  input[type=text]{flex:1;background:#1e2330;border:1px solid #2d3548;border-radius:8px;padding:10px 14px;color:#e2e8f0;font-size:.9rem;outline:none}
  input[type=text]:focus{border-color:#60a5fa}
  button{background:#3b82f6;color:#fff;border:none;border-radius:8px;padding:10px 22px;cursor:pointer;font-size:.9rem;font-weight:600}
  button:hover{background:#2563eb}
  .link-box{background:#161b27;border:1px solid #2d3548;border-radius:8px;padding:10px 14px;font-family:monospace;font-size:.82rem;word-break:break-all;color:#a5f3fc;margin-top:8px}
  .section-title{font-size:1rem;font-weight:600;color:#94a3b8;margin-bottom:12px;margin-top:32px}
  .empty{text-align:center;padding:32px;color:#475569;font-size:.9rem}
</style>
"""

def render_dashboard(campaigns, stats, new_link=None, error=None):
    total_joins   = sum(c["joins"] for c in campaigns)
    total_organic = db.get_organic_joins()

    rows = ""
    for c in campaigns:
        rows += f"""
        <tr>
          <td><span class="badge">{c['name']}</span></td>
          <td><div class="link-box">{c['invite_link']}</div></td>
          <td style="color:#34d399;font-weight:600">{c['joins']}</td>
          <td style="color:#94a3b8">{c['created_at'][:10]}</td>
        </tr>"""
    if not rows:
        rows = '<tr><td colspan="4"><div class="empty">Кампаний ещё нет — создай первую выше 👆</div></td></tr>'

    new_link_block = ""
    if new_link:
        new_link_block = f'<div style="margin-bottom:20px;padding:14px 18px;background:#052e16;border:1px solid #166534;border-radius:10px;color:#86efac">✅ Ссылка создана! Используй её в рекламе:<div class="link-box" style="margin-top:8px">{new_link}</div></div>'
    if error:
        new_link_block = f'<div style="margin-bottom:20px;padding:14px 18px;background:#2d0a0a;border:1px solid #7f1d1d;border-radius:10px;color:#fca5a5">❌ {error}</div>'

    last = ""
    for j in stats[:20]:
        last += f"<tr><td>{j['joined_at'][:16].replace('T',' ')}</td><td><span class='badge'>{j['campaign_name']}</span></td></tr>"
    if not last:
        last = '<tr><td colspan="2"><div class="empty">Подписчиков пока нет</div></td></tr>'

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>TG Tracker</title>{STYLE}</head><body>
<div class="wrap">
  <h1>📊 TG Tracker</h1>
  <div class="sub">Отслеживание подписок на Telegram-канал через Meta Ads</div>

  <div class="cards">
    <div class="card"><div class="val">{total_joins + total_organic}</div><div class="lbl">Всего подписчиков</div></div>
    <div class="card"><div class="val">{total_joins}</div><div class="lbl">Из рекламы</div></div>
    <div class="card"><div class="val">{total_organic}</div><div class="lbl">Органика</div></div>
    <div class="card"><div class="val">{len(campaigns)}</div><div class="lbl">Кампаний</div></div>
  </div>

  <div class="section-title">➕ Создать ссылку для кампании</div>
  {new_link_block}
  <form method="post" action="/campaign/create">
    <div class="form-row">
      <input type="text" name="name" placeholder="Название кампании (напр: FB_Broad_March)" required />
      <button type="submit">Создать ссылку</button>
    </div>
  </form>

  <div class="section-title">🔗 Кампании</div>
  <table>
    <thead><tr><th>Кампания</th><th>Invite Link (вставь в рекламу)</th><th>Подписчиков</th><th>Создана</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>

  <div class="section-title">🕐 Последние подписки</div>
  <table>
    <thead><tr><th>Время</th><th>Кампания</th></tr></thead>
    <tbody>{last}</tbody>
  </table>
</div></body></html>"""


@app.get("/", response_class=HTMLResponse)
async def dashboard(key: str = ""):
    if key != SECRET:
        return HTMLResponse("""<!DOCTYPE html><html><head><meta charset='utf-8'><title>Login</title>""" + STYLE + """</head>
        <body><div class='wrap' style='max-width:360px;padding-top:80px'>
        <h1 style='margin-bottom:20px'>🔐 TG Tracker</h1>
        <form method='get'><div class='form-row'>
        <input type='text' name='key' placeholder='Пароль' />
        <button>Войти</button></div></form></div></body></html>""", status_code=401)

    campaigns = db.get_campaigns()
    stats     = db.get_recent_joins()
    return render_dashboard(campaigns, stats)


@app.post("/campaign/create", response_class=HTMLResponse)
async def create_campaign(request: Request, name: str = Form(...)):
    key = request.query_params.get("key", "")
    campaigns = db.get_campaigns()
    stats     = db.get_recent_joins()
    try:
        link_obj = await bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            name=name[:32],
            creates_join_request=False,
        )
        db.save_campaign(name=name, invite_link=link_obj.invite_link)
        return HTMLResponse(render_dashboard(campaigns + [{"name": name, "invite_link": link_obj.invite_link, "joins": 0, "created_at": ""}],
                                             stats, new_link=link_obj.invite_link))
    except Exception as e:
        log.error(f"create_campaign error: {e}")
        return HTMLResponse(render_dashboard(campaigns, stats, error=str(e)))


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
