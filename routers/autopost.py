"""
autopost.py — Модуль автопостинга в Telegram каналы
Кампании → Боты → Каналы → Посты → Расписание
"""
import os, json, logging, asyncio
from datetime import datetime
from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

log = logging.getLogger(__name__)
router = APIRouter()

db = None
require_auth = None
base = None
bot_manager = None

US_TIMEZONES = [
    ("US/Eastern",  "Eastern (ET) — New York, Miami, Atlanta"),
    ("US/Central",  "Central (CT) — Chicago, Dallas, Houston"),
    ("US/Mountain", "Mountain (MT) — Denver, Phoenix"),
    ("US/Pacific",  "Pacific (PT) — LA, San Francisco, Seattle"),
    ("US/Alaska",   "Alaska (AKT) — Anchorage"),
    ("US/Hawaii",   "Hawaii (HT) — Honolulu"),
]


def setup(_db, _log, _require_auth, _base, _bot_manager=None, **kwargs):
    global db, require_auth, base, bot_manager
    db = _db
    require_auth = _require_auth
    base = _base
    bot_manager = _bot_manager


def _field(name, label, value="", placeholder="", textarea=False, rows=3, hint=""):
    val = str(value or "")
    inp = (
        f'<textarea name="{name}" rows="{rows}" placeholder="{placeholder}" '
        f'style="min-height:{rows*28}px">{val}</textarea>'
        if textarea else
        f'<input type="text" name="{name}" value="{val}" placeholder="{placeholder}"/>'
    )
    hint_html = f'<span style="font-size:.72rem;color:var(--text3)">{hint}</span>' if hint else ""
    return f'<div class="field-group"><div class="field-label">{label}</div>{inp}{hint_html}</div>'


# ─── СТРАНИЦА КАМПАНИЙ ────────────────────────────────────────────────────────

@router.get("/autopost", response_class=HTMLResponse)
async def autopost_page(request: Request, msg: str = "", err: str = ""):
    user, e = require_auth(request, role="admin")
    if e: return e

    campaigns = db.get_autopost_campaigns()
    alert = (f'<div class="alert-green">✅ {msg}</div>' if msg else
             f'<div class="alert-red">❌ {err}</div>' if err else "")

    rows = ""
    for c in campaigns:
        _status_color = "#34d399" if c["status"] == "active" else "#6b7280"
        _status_label = "▶ Активна" if c["status"] == "active" else "⏸ Пауза"
        _posts_count = db.get_autopost_posts_count(c["id"])
        _sent_count = db.get_autopost_sent_count(c["id"])
        _tz_short = (c.get("timezone") or "US/Eastern").split("/")[-1]
        rows += f"""<tr>
          <td><b>{c['name']}</b><div style="font-size:.7rem;color:var(--text3)">{_tz_short} · {c.get('windows_label','')}</div></td>
          <td><span style="color:{_status_color};font-weight:600">{_status_label}</span></td>
          <td style="text-align:center">{_posts_count}</td>
          <td style="text-align:center;color:#86efac">{_sent_count}</td>
          <td>
            <a href="/autopost/{c['id']}" class="btn-gray btn-sm">✏️ Настройки</a>
            <a href="/autopost/{c['id']}/posts" class="btn-gray btn-sm">📋 Посты</a>
            {'<form method="post" action="/autopost/pause" style="display:inline"><input type="hidden" name="id" value="'+str(c['id'])+'"/><button class="btn-gray btn-sm" style="color:#fbbf24">⏸</button></form>' if c['status']=='active' else
             '<form method="post" action="/autopost/resume" style="display:inline"><input type="hidden" name="id" value="'+str(c['id'])+'"/><button class="btn-gray btn-sm" style="color:#34d399">▶</button></form>'}
            <form method="post" action="/autopost/post_now" style="display:inline"><input type="hidden" name="id" value="{c['id']}"/><button class="btn-gray btn-sm" title="Отправить сейчас">⚡</button></form>
            <form method="post" action="/autopost/delete" style="display:inline"><input type="hidden" name="id" value="{c['id']}"/><button class="del-btn btn-sm">✕</button></form>
          </td></tr>"""

    rows = rows or '<tr><td colspan="5"><div class="empty">Нет кампаний — создай первую</div></td></tr>'

    content = f"""<div class="page-wrap">
    <div class="page-title">📣 Автопостинг</div>
    <div class="page-sub">Управление автоматической публикацией в Telegram каналы</div>
    {alert}
    <div class="section"><div class="section-head"><h3>➕ Новая кампания</h3></div>
    <div class="section-body">
      <form method="post" action="/autopost/create">
        <div class="form-row">
          <div class="field-group" style="flex:2">
            <div class="field-label">Название кампании</div>
            <input type="text" name="name" placeholder="Chicago Evening Posts" required/>
          </div>
          <div class="field-group" style="flex:1">
            <div class="field-label">Часовой пояс</div>
            <select name="timezone">
              {''.join(f'<option value="{v}">{l}</option>' for v,l in US_TIMEZONES)}
            </select>
          </div>
          <div style="display:flex;align-items:flex-end">
            <button class="btn">Создать</button>
          </div>
        </div>
      </form>
    </div></div>
    <div class="section"><div class="section-head"><h3>Кампании ({len(campaigns)})</h3></div>
    <table><thead><tr><th>Кампания</th><th>Статус</th><th>Постов</th><th>Отправлено</th><th>Действия</th></tr></thead>
    <tbody>{rows}</tbody></table></div></div>"""

    return HTMLResponse(base(content, "autopost", request))


# ─── СОЗДАНИЕ КАМПАНИИ ────────────────────────────────────────────────────────

@router.post("/autopost/create")
async def autopost_create(request: Request, name: str = Form(...), timezone: str = Form("US/Eastern")):
    user, e = require_auth(request, role="admin")
    if e: return e
    cid = db.create_autopost_campaign(name.strip(), timezone)
    return RedirectResponse(f"/autopost/{cid}?msg=Кампания+создана", 303)



# ─── МЕДИАТЕКА ────────────────────────────────────────────────────────────────

@router.get("/autopost/media", response_class=HTMLResponse)
async def autopost_media_page(request: Request, msg: str = "", err: str = ""):
    user, e = require_auth(request, role="admin")
    if e: return e

    media_list = db.get_autopost_media()
    alert = (f'<div class="alert-green">✅ {msg}</div>' if msg else
             f'<div class="alert-red">❌ {err}</div>' if err else "")

    items = ""
    for m in media_list:
        _prev = ""
        if m["media_type"] == "video":
            _prev = f'<div style="width:80px;height:80px;background:#1a1a2a;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:2rem">🎬</div>'
        else:
            _prev = f'<img src="{m["url"]}" style="width:80px;height:80px;object-fit:cover;border-radius:8px;border:1px solid var(--border)"/>'
        _size = f'{m["size_bytes"]//1024} KB' if m.get("size_bytes") else ""
        items += f"""<div style="display:flex;align-items:center;gap:12px;padding:10px;border-bottom:1px solid var(--border)">
          {_prev}
          <div style="flex:1">
            <div style="font-weight:600;font-size:.85rem">{m['name']}</div>
            <div style="font-size:.72rem;color:var(--text3)">{m['media_type']} · {_size}</div>
            <div style="font-size:.7rem;color:var(--text3);margin-top:2px;word-break:break-all">{m['url'][:60]}...</div>
          </div>
          <form method="post" action="/autopost/media/delete">
            <input type="hidden" name="id" value="{m['id']}"/>
            <button class="del-btn btn-sm">✕</button>
          </form>
        </div>"""

    items = items or '<div style="padding:20px;text-align:center;color:var(--text3)">Нет медиафайлов — загрузи первый</div>'

    content = f"""<div class="page-wrap">
    <div class="page-title">🖼 Медиатека</div>
    <div class="page-sub"><a href="/autopost" style="color:var(--text3)">← Автопостинг</a></div>
    {alert}

    <div class="section"><div class="section-head"><h3>⬆️ Загрузить файл</h3></div>
    <div class="section-body">
      <form method="post" action="/autopost/media/upload" enctype="multipart/form-data">
        <div class="form-row" style="gap:12px;flex-wrap:wrap">
          <div class="field-group" style="flex:1;min-width:200px">
            <div class="field-label">Название файла</div>
            <input type="text" name="name" placeholder="Фото Чикаго #1" required/>
          </div>
          <div class="field-group" style="flex:1;min-width:200px">
            <div class="field-label">Файл (фото или видео)</div>
            <input type="file" name="media" accept="image/*,video/*" required style="font-size:.85rem"/>
          </div>
          <div style="display:flex;align-items:flex-end">
            <button class="btn-orange">⬆️ Загрузить</button>
          </div>
        </div>
      </form>
    </div></div>

    <div class="section"><div class="section-head"><h3>Файлы ({len(media_list)})</h3></div>
    {items}
    </div></div>"""

    return HTMLResponse(base(content, "autopost", request))


@router.post("/autopost/media/upload")
async def autopost_media_upload(request: Request, name: str = Form(...),
                                 media: UploadFile = File(...)):
    user, e = require_auth(request, role="admin")
    if e: return e

    try:
        import cloudinary, cloudinary.uploader, base64
        # Сначала пробуем отдельные переменные, потом URL
        cld_name   = os.getenv("CLOUDINARY_CLOUD_NAME", "")
        cld_key    = os.getenv("CLOUDINARY_API_KEY", "")
        cld_secret = os.getenv("CLOUDINARY_API_SECRET", "")
        cld_url    = db.get_setting("cloudinary_url") or os.getenv("CLOUDINARY_URL", "")

        log.info(f"[Autopost media] cld_name={repr(cld_name)} cld_key={repr(cld_key[:5] if cld_key else '')} cld_url={repr(cld_url[:20] if cld_url else '')}")
        if cld_name and cld_key and cld_secret:
            cloudinary.config(cloud_name=cld_name.strip(), api_key=cld_key.strip(), api_secret=cld_secret.strip())
        elif cld_url:
            cloudinary.config(cloudinary_url=cld_url.strip())
        else:
            return RedirectResponse("/autopost/media?err=Cloudinary+не+настроен", 303)
        file_bytes = await media.read()
        mime = media.content_type or "image/jpeg"
        result = cloudinary.uploader.upload(
            f"data:{mime};base64,{base64.b64encode(file_bytes).decode()}",
            folder="autopost_media",
            resource_type="auto"
        )
        url = result.get("secure_url")
        media_type = "video" if "video" in mime else "image"
        size = len(file_bytes)
        db.add_autopost_media(name.strip(), url, media_type, size)
        return RedirectResponse(f"/autopost/media?msg=Загружено+{name}", 303)

    except Exception as ex:
        log.error(f"[Autopost media] upload error: {ex}")
        return RedirectResponse(f"/autopost/media?err=Ошибка+загрузки", 303)


@router.post("/autopost/media/delete")
async def autopost_media_delete(request: Request, id: int = Form(...)):
    user, e = require_auth(request, role="admin")
    if e: return e
    db.delete_autopost_media(id)
    return RedirectResponse("/autopost/media?msg=Удалено", 303)



# ─── НАСТРОЙКИ КАМПАНИИ ───────────────────────────────────────────────────────

@router.get("/autopost/{campaign_id}", response_class=HTMLResponse)
async def autopost_edit(request: Request, campaign_id: int, msg: str = "", err: str = ""):
    user, e = require_auth(request, role="admin")
    if e: return e

    c = db.get_autopost_campaign(campaign_id)
    if not c:
        return RedirectResponse("/autopost?err=Кампания+не+найдена", 303)

    alert = (f'<div class="alert-green">✅ {msg}</div>' if msg else
             f'<div class="alert-red">❌ {err}</div>' if err else "")

    # Окна постинга
    windows = json.loads(c.get("windows") or "[]") or [[8, 10], [18, 21]]
    windows_str = ", ".join(f"{s}-{e}" for s, e in windows)

    # Выбор часового пояса
    tz_opts = "".join(
        f'<option value="{v}" {"selected" if v == c.get("timezone","US/Eastern") else ""}>{l}</option>'
        for v, l in US_TIMEZONES
    )

    # Режим постинга
    mode = c.get("post_mode") or "loop"
    mode_loop = "selected" if mode == "loop" else ""
    mode_once = "selected" if mode == "once" else ""

    # Бот токен
    bot_token = c.get("bot_token") or ""
    bot_status = ""
    if bot_token:
        bot_status = '<span style="color:#34d399;font-size:.75rem">● Токен задан</span>'
    else:
        bot_status = '<span style="color:#fbbf24;font-size:.75rem">○ Токен не задан</span>'

    # Канал
    channel_id = c.get("channel_id") or ""

    content = f"""<div class="page-wrap">
    <div class="page-title">⚙️ {c['name']}</div>
    <div class="page-sub"><a href="/autopost" style="color:var(--text3)">← Автопостинг</a></div>
    {alert}

    <div class="section"><div class="section-head"><h3>🤖 Бот и канал</h3></div>
    <div class="section-body">
      <form method="post" action="/autopost/{campaign_id}/save">
        <div class="form-row" style="flex-wrap:wrap;gap:12px">
          <div class="field-group" style="flex:1;min-width:220px">
            <div class="field-label">Bot Token {bot_status}</div>
            <input type="text" name="bot_token" value="{bot_token}" placeholder="7711559280:AAG..."/>
            <span style="font-size:.72rem;color:var(--text3)">Токен бота который будет постить в канал</span>
          </div>
          <div class="field-group" style="flex:1;min-width:220px">
            <div class="field-label">Chat ID канала</div>
            <input type="text" name="channel_id" value="{channel_id}" placeholder="-1002643912551"/>
            <span style="font-size:.72rem;color:var(--text3)">ID канала (отрицательное число)</span>
          </div>
        </div>

        <div style="font-size:.72rem;font-weight:700;color:#3b82f6;text-transform:uppercase;letter-spacing:.08em;margin:14px 0 8px">
          ⏰ Расписание
        </div>
        <div class="form-row" style="flex-wrap:wrap;gap:12px">
          <div class="field-group" style="flex:1;min-width:180px">
            <div class="field-label">Часовой пояс</div>
            <select name="timezone">{tz_opts}</select>
          </div>
          <div class="field-group" style="flex:1;min-width:180px">
            <div class="field-label">Окна постинга</div>
            <input type="text" name="windows" value="{windows_str}" placeholder="8-10, 18-21"/>
            <span style="font-size:.72rem;color:var(--text3)">Через запятую, формат: 8-10, 18-21</span>
          </div>
          <div class="field-group" style="flex:1;min-width:140px">
            <div class="field-label">Постов за окно</div>
            <input type="number" name="max_posts" value="{c.get('max_posts',2)}" min="1" max="20"/>
          </div>
        </div>

        <div class="form-row" style="flex-wrap:wrap;gap:12px">
          <div class="field-group" style="flex:1;min-width:180px">
            <div class="field-label">Задержка между постами</div>
            <div style="display:flex;gap:8px;align-items:center">
              <input type="number" name="delay_min" value="{c.get('delay_min',5)}" min="1" style="width:80px"/> мин
              <span style="color:var(--text3)">–</span>
              <input type="number" name="delay_max" value="{c.get('delay_max',15)}" min="1" style="width:80px"/> мин
            </div>
          </div>
          <div class="field-group" style="flex:1;min-width:180px">
            <div class="field-label">Режим постинга</div>
            <select name="post_mode">
              <option value="loop" {mode_loop}>🔄 По кругу (бесконечно)</option>
              <option value="once" {mode_once}>1️⃣ До конца (один раз)</option>
            </select>
          </div>
        </div>

        <button class="btn-orange" style="margin-top:12px">💾 Сохранить настройки</button>
      </form>
    </div></div>

    <div class="section"><div class="section-head"><h3>🧪 Тест отправки</h3></div>
    <div class="section-body">
      <form method="post" action="/autopost/post_now">
        <input type="hidden" name="id" value="{campaign_id}"/>
        <button class="btn-gray">⚡ Отправить следующий пост сейчас</button>
      </form>
    </div></div>
    </div>"""

    return HTMLResponse(base(content, "autopost", request))


@router.post("/autopost/{campaign_id}/save")
async def autopost_save(request: Request, campaign_id: int,
                         bot_token: str = Form(""), channel_id: str = Form(""),
                         timezone: str = Form("US/Eastern"), windows: str = Form("8-10, 18-21"),
                         max_posts: int = Form(2), delay_min: int = Form(5),
                         delay_max: int = Form(15), post_mode: str = Form("loop")):
    user, e = require_auth(request, role="admin")
    if e: return e

    # Парсим окна
    parsed_windows = []
    for part in windows.split(","):
        part = part.strip()
        if "-" in part:
            try:
                s, en = part.split("-")
                parsed_windows.append([int(s.strip()), int(en.strip())])
            except: pass
    if not parsed_windows:
        parsed_windows = [[8, 10], [18, 21]]

    windows_label = ", ".join(f"{s}-{e}" for s, e in parsed_windows)

    db.update_autopost_campaign(campaign_id,
        bot_token=bot_token.strip(),
        channel_id=channel_id.strip(),
        timezone=timezone,
        windows=json.dumps(parsed_windows),
        windows_label=windows_label,
        max_posts=max_posts,
        delay_min=delay_min,
        delay_max=delay_max,
        post_mode=post_mode,
    )
    return RedirectResponse(f"/autopost/{campaign_id}?msg=Сохранено", 303)


# ─── ПОСТЫ КАМПАНИИ ───────────────────────────────────────────────────────────

@router.get("/autopost/{campaign_id}/posts", response_class=HTMLResponse)
async def autopost_posts(request: Request, campaign_id: int, msg: str = "", err: str = ""):
    user, e = require_auth(request, role="admin")
    if e: return e

    c = db.get_autopost_campaign(campaign_id)
    if not c:
        return RedirectResponse("/autopost", 303)

    posts = db.get_autopost_posts(campaign_id)
    alert = (f'<div class="alert-green">✅ {msg}</div>' if msg else
             f'<div class="alert-red">❌ {err}</div>' if err else "")

    # Медиатека для выбора
    _all_media = db.get_autopost_media()
    _media_opts = '<option value="">— без медиа —</option>'
    for m in _all_media:
        _ico = "🎬" if m["media_type"] == "video" else "🖼"
        _media_opts += f'<option value="{m["url"]}" data-type="{m["media_type"]}">{_ico} {m["name"]}</option>'
    _media_select_html = ('<select name="media_url" style="width:100%;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 12px;color:var(--text);font-size:.82rem">'  + _media_opts + '</select>')
    next_idx = db.get_autopost_next_index(campaign_id)

    rows = ""
    for p in posts:
        _sent = p.get("sent_count") or 0
        _last = p.get("last_sent_at") or "—"
        if _last != "—":
            _last = _last[:16].replace("T", " ")
        _is_next = "✅ " if p["position"] == next_idx else ""
        _media_preview = ""
        if p.get("media_url"):
            if (p.get("media_type") or "").startswith("image"):
                _media_preview = f'<img src="{p["media_url"]}" style="width:48px;height:48px;object-fit:cover;border-radius:6px;vertical-align:middle"/>'
            else:
                _media_preview = f'<span style="font-size:1.2rem">🎬</span>'
        _caption_short = (p.get("caption") or "")[:80]

        rows += f"""<tr>
          <td style="text-align:center;font-weight:700">{_is_next}{p['position']}</td>
          <td>{_media_preview}</td>
          <td style="max-width:300px;font-size:.8rem;color:var(--text2)">{_caption_short}{'...' if len(p.get('caption',''))>80 else ''}</td>
          <td style="text-align:center;font-size:.75rem;color:var(--text3)">{_sent}x<br>{_last}</td>
          <td>
            <a href="/autopost/{campaign_id}/posts/{p['id']}/edit" class="btn-gray btn-sm">✏️</a>
            <form method="post" action="/autopost/{campaign_id}/posts/{p['id']}/send_now" style="display:inline"><button class="btn-gray btn-sm" title="Отправить этот пост сейчас">⚡</button></form>
            <form method="post" action="/autopost/{campaign_id}/posts/{p['id']}/delete" style="display:inline"><button class="del-btn btn-sm">✕</button></form>
          </td></tr>"""

    rows = rows or '<tr><td colspan="5"><div class="empty">Нет постов — добавь первый</div></td></tr>'

    content = f"""<div class="page-wrap">
    <div class="page-title">📋 Посты: {c['name']}</div>
    <div class="page-sub"><a href="/autopost/{campaign_id}" style="color:var(--text3)">← Настройки</a> · Следующий пост: #{next_idx}</div>
    {alert}

    <div class="section"><div class="section-head"><h3>➕ Добавить пост</h3></div>
    <div class="section-body">
      <form method="post" action="/autopost/{campaign_id}/posts/add">
        <div class="form-row" style="flex-wrap:wrap;gap:12px">
          <div class="field-group" style="flex:2;min-width:280px">
            <div class="field-label">Текст поста (HTML)</div>
            <textarea name="caption" rows="5" placeholder="<b>Текст</b> поста...&#10;&#10;Поддерживается HTML: &lt;b&gt;, &lt;i&gt;, &lt;a href=&quot;...&quot;&gt;"></textarea>
            <span style="font-size:.72rem;color:var(--text3)">Поддерживается TG HTML: &lt;b&gt;bold&lt;/b&gt;, &lt;i&gt;italic&lt;/i&gt;, &lt;a href=&quot;url&quot;&gt;ссылка&lt;/a&gt;</span>
          </div>
          <div class="field-group" style="flex:1;min-width:200px">
            <div class="field-label">Медиафайл <a href="/autopost/media" target="_blank" style="font-size:.72rem;color:var(--orange)">+ загрузить в библиотеку</a></div>
            {_media_select_html}
            <div style="margin-top:8px">
              <div class="field-label">Позиция в очереди</div>
              <input type="number" name="position" value="{len(posts)+1}" min="1"/>
            </div>
          </div>
        </div>
        <button class="btn-orange">➕ Добавить пост</button>
      </form>
    </div></div>

    <div class="section"><div class="section-head">
      <h3>Очередь постов ({len(posts)})</h3>
      <form method="post" action="/autopost/{campaign_id}/posts/reset_index" style="display:inline">
        <button class="btn-gray btn-sm">↺ Сбросить на начало</button>
      </form>
    </div>
    <table><thead><tr><th>#</th><th>Медиа</th><th>Текст</th><th>Отправлено</th><th>Действия</th></tr></thead>
    <tbody>{rows}</tbody></table></div>
    </div>"""

    return HTMLResponse(base(content, "autopost", request))


@router.post("/autopost/{campaign_id}/posts/add")
async def autopost_add_post(request: Request, campaign_id: int,
                              caption: str = Form(""), position: int = Form(1),
                              media_url: str = Form(""), media_type: str = Form("")):
    user, e = require_auth(request, role="admin")
    if e: return e
    db.add_autopost_post(campaign_id, caption.strip(), position,
                         media_url.strip() or None, media_type.strip() or None)
    return RedirectResponse(f"/autopost/{campaign_id}/posts?msg=Пост+добавлен", 303)


@router.post("/autopost/{campaign_id}/posts/{post_id}/delete")
async def autopost_delete_post(request: Request, campaign_id: int, post_id: int):
    user, e = require_auth(request, role="admin")
    if e: return e
    db.delete_autopost_post(post_id)
    return RedirectResponse(f"/autopost/{campaign_id}/posts?msg=Пост+удалён", 303)


@router.post("/autopost/{campaign_id}/posts/reset_index")
async def autopost_reset_index(request: Request, campaign_id: int):
    user, e = require_auth(request, role="admin")
    if e: return e
    db.reset_autopost_index(campaign_id)
    return RedirectResponse(f"/autopost/{campaign_id}/posts?msg=Очередь+сброшена", 303)


@router.post("/autopost/{campaign_id}/posts/{post_id}/send_now")
async def autopost_send_post_now(request: Request, campaign_id: int, post_id: int):
    user, e = require_auth(request, role="admin")
    if e: return e
    result = await _send_post(campaign_id, post_id=post_id, advance_index=False)
    if result:
        return RedirectResponse(f"/autopost/{campaign_id}/posts?msg=Пост+отправлен", 303)
    return RedirectResponse(f"/autopost/{campaign_id}/posts?err=Ошибка+отправки", 303)


# ─── УПРАВЛЕНИЕ КАМПАНИЕЙ ─────────────────────────────────────────────────────

@router.post("/autopost/pause")
async def autopost_pause(request: Request, id: int = Form(...)):
    user, e = require_auth(request, role="admin")
    if e: return e
    db.set_autopost_status(id, "paused")
    return RedirectResponse("/autopost?msg=Кампания+приостановлена", 303)


@router.post("/autopost/resume")
async def autopost_resume(request: Request, id: int = Form(...)):
    user, e = require_auth(request, role="admin")
    if e: return e
    db.set_autopost_status(id, "active")
    return RedirectResponse("/autopost?msg=Кампания+запущена", 303)


@router.post("/autopost/delete")
async def autopost_delete(request: Request, id: int = Form(...)):
    user, e = require_auth(request, role="admin")
    if e: return e
    db.delete_autopost_campaign(id)
    return RedirectResponse("/autopost?msg=Кампания+удалена", 303)


@router.post("/autopost/post_now")
async def autopost_post_now(request: Request, id: int = Form(...)):
    user, e = require_auth(request, role="admin")
    if e: return e
    result = await _send_post(id)
    if result:
        return RedirectResponse("/autopost?msg=Пост+отправлен", 303)
    return RedirectResponse("/autopost?err=Ошибка+отправки+(нет+постов+или+бота)", 303)


# ─── ЛОГИКА ОТПРАВКИ ──────────────────────────────────────────────────────────

async def _send_post(campaign_id: int, post_id: int = None, advance_index: bool = True) -> bool:
    """Отправляет пост в канал. post_id=None → берёт следующий по очереди."""
    try:
        c = db.get_autopost_campaign(campaign_id)
        if not c:
            return False

        token = c.get("bot_token") or ""
        channel = c.get("channel_id") or ""
        if not token or not channel:
            log.warning(f"[Autopost] campaign={campaign_id} missing token or channel")
            return False

        if post_id:
            post = db.get_autopost_post(post_id)
        else:
            post = db.get_autopost_next_post(campaign_id)

        if not post:
            # Все посты отправлены
            mode = c.get("post_mode") or "loop"
            if mode == "loop":
                db.reset_autopost_index(campaign_id)
                post = db.get_autopost_next_post(campaign_id)
            if not post:
                log.info(f"[Autopost] campaign={campaign_id} no posts left")
                return False

        from aiogram import Bot
        bot = Bot(token=token)
        try:
            caption = post.get("caption") or ""
            media_url = post.get("media_url")
            media_type = post.get("media_type") or ""

            if media_url:
                # Передаём URL напрямую — Telegram сам скачает медиа
                if "video" in (media_type or ""):
                    await bot.send_video(int(channel), media_url, caption=caption, parse_mode="HTML", supports_streaming=True)
                else:
                    await bot.send_photo(int(channel), media_url, caption=caption, parse_mode="HTML")
            else:
                await bot.send_message(int(channel), caption, parse_mode="HTML")

            db.mark_autopost_sent(post["id"])
            if advance_index:
                db.advance_autopost_index(campaign_id)

            log.info(f"[Autopost] ✅ campaign={campaign_id} post={post['id']} pos={post['position']}")
            return True

        finally:
            await bot.session.close()

    except Exception as ex:
        log.error(f"[Autopost] ❌ campaign={campaign_id} error: {ex}")
        return False


# ─── ШЕДУЛЕР ──────────────────────────────────────────────────────────────────

_scheduler_task: asyncio.Task = None


async def scheduler_loop():
    """Фоновый цикл — каждые 5 минут проверяет расписание."""
    import pytz, random
    log.info("[Autopost] Scheduler started")
    while True:
        try:
            campaigns = db.get_autopost_campaigns(status="active")
            for c in campaigns:
                try:
                    tz_name = c.get("timezone") or "US/Eastern"
                    tz = pytz.timezone(tz_name)
                    now_hour = datetime.now(tz).hour
                    windows = json.loads(c.get("windows") or "[]")
                    max_posts = c.get("max_posts") or 2
                    delay_min = c.get("delay_min") or 5
                    delay_max = c.get("delay_max") or 15

                    active_window = None
                    for s, en in windows:
                        if s <= now_hour < en:
                            active_window = (s, en)
                            break

                    if not active_window:
                        db.reset_autopost_window(c["id"])
                        continue

                    # Проверяем сколько уже отправлено в этом окне
                    sent_in_window = db.get_autopost_window_count(c["id"], active_window)
                    if sent_in_window >= max_posts:
                        continue

                    # Отправляем
                    ok = await _send_post(c["id"])
                    if ok:
                        db.log_autopost_window(c["id"], active_window)
                        delay = random.randint(delay_min * 60, delay_max * 60)
                        await asyncio.sleep(delay)

                except Exception as ex:
                    log.error(f"[Autopost] scheduler campaign={c['id']} error: {ex}")

        except Exception as ex:
            log.error(f"[Autopost] scheduler loop error: {ex}")

        await asyncio.sleep(300)  # проверка каждые 5 минут


def start_scheduler():
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        return
    _scheduler_task = asyncio.create_task(scheduler_loop())
    log.info("[Autopost] Scheduler task created")
