"""
routers/chat_wa.py — WhatsApp чат роуты

Подключается в main.py:
    from routers.chat_wa import router as wa_router, setup as wa_setup
    wa_setup(db, log, bot_manager, meta_capi,
             WA_URL, WA_SECRET, WA_WH_SECRET,
             TG_SVC_URL, TG_SVC_SECRET,
             check_session, require_auth, base, nav_html, _render_conv_tags_picker)
    app.include_router(wa_router)
"""

import httpx
from fastapi import APIRouter, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter()

# ── Зависимости — инициализируются через setup() ──────────────────────────────
db             = None
log            = None
bot_manager    = None
meta_capi      = None
WA_URL         = ""
WA_SECRET      = ""
WA_WH_SECRET   = ""
TG_SVC_URL     = ""
TG_SVC_SECRET  = ""
check_session         = None
require_auth          = None
base                  = None
nav_html              = None
_render_conv_tags_picker = None


def setup(_db, _log, _bot_manager, _meta_capi,
          _wa_url, _wa_secret, _wa_wh_secret,
          _tg_svc_url, _tg_svc_secret,
          _check_session, _require_auth, _base, _nav_html, _render_conv_tags_picker_fn):
    global db, log, bot_manager, meta_capi
    global WA_URL, WA_SECRET, WA_WH_SECRET
    global TG_SVC_URL, TG_SVC_SECRET
    global check_session, require_auth, base, nav_html, _render_conv_tags_picker
    db             = _db
    log            = _log
    bot_manager    = _bot_manager
    meta_capi      = _meta_capi
    WA_URL         = _wa_url
    WA_SECRET      = _wa_secret
    WA_WH_SECRET   = _wa_wh_secret
    TG_SVC_URL     = _tg_svc_url
    TG_SVC_SECRET  = _tg_svc_secret
    check_session  = _check_session
    require_auth   = _require_auth
    base           = _base
    nav_html       = _nav_html
    _render_conv_tags_picker = _render_conv_tags_picker_fn

async def wa_api(method: str, path: str, **kwargs) -> dict:
    if not WA_URL:
        return {"error": "WA_SERVICE_URL not configured"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await getattr(client, method)(
                f"{WA_URL}{path}",
                headers={"X-Api-Secret": WA_SECRET},
                **kwargs
            )
            return resp.json()
    except Exception as e:
        log.error(f"WA API error: {e}")
        return {"error": str(e)}


# ── Хелпер вызова TG аккаунт сервиса ─────────────────────────────────────────
async def tg_api(method: str, path: str, **kwargs) -> dict:
    if not TG_SVC_URL:
        return {"error": "TG_SERVICE_URL not configured"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await getattr(client, method)(
                f"{TG_SVC_URL}{path}",
                headers={"X-Api-Secret": TG_SVC_SECRET},
                **kwargs
            )
            return resp.json()
    except Exception as e:
        log.error(f"TG API error: {e}")
        return {"error": str(e)}


@router.post("/wa/webhook")
async def wa_webhook(request: Request):
    secret = request.headers.get("X-WA-Secret", "")
    if secret != WA_WH_SECRET:
        log.warning(f"[WA webhook] Wrong secret: {secret!r}")
        return JSONResponse({"error": "unauthorized"}, 401)
    try:
        body  = await request.json()
    except Exception as e:
        log.error(f"[WA webhook] Bad JSON: {e}")
        return JSONResponse({"ok": True})  # всегда 200 чтобы WA не ретраил

    event = body.get("event")
    data  = body.get("data", {})
    log.info(f"[WA webhook] event={event} keys={list(data.keys())}")

    try:
        if event == "message":
            wa_chat_id  = data.get("wa_chat_id") or data.get("chatId", "")
            wa_number   = data.get("wa_number")  or data.get("from", wa_chat_id).replace("@c.us","")
            sender_name = data.get("sender_name") or data.get("pushname") or wa_number

            raw_text    = data.get("body") or data.get("text") or ""
            media_url   = data.get("media_url")
            media_type  = data.get("media_type", "")
            media_b64   = data.get("media_base64")
            has_media   = data.get("hasMedia") or media_url or media_b64

            # Загружаем base64 медиа на Cloudinary если пришло от WA сервиса
            if media_b64 and not media_url:
                try:
                    import cloudinary
                    import cloudinary.uploader
                    import base64 as _b64
                    cld_url  = db.get_setting("cloudinary_url") or os.getenv("CLOUDINARY_URL", "")
                    if cld_url:
                        cloudinary.config(cloudinary_url=cld_url)
                        mime = media_type or "image/jpeg"
                        data_uri = f"data:{mime};base64,{media_b64}"
                        result = cloudinary.uploader.upload(
                            data_uri,
                            folder="wa_media",
                            resource_type="auto",
                        )
                        media_url = result.get("secure_url")
                        log.info(f"[WA webhook] media uploaded to Cloudinary: {media_url}")
                    else:
                        # Cloudinary не настроен — сохраняем как data URI (только для картинок)
                        if (media_type or "").startswith("image/"):
                            media_url = f"data:{media_type};base64,{media_b64}"
                except Exception as e:
                    log.error(f"[WA webhook] Cloudinary upload error: {e}")

            if not raw_text and has_media:
                raw_text = "[фото]" if (media_type or "").startswith("image/") else "[файл]"
            text = (raw_text or "").strip() or "[сообщение]"

            if not wa_chat_id:
                log.warning(f"[WA webhook] no wa_chat_id in data: {data}")
                return JSONResponse({"ok": True})

            conv = db.get_or_create_wa_conversation(wa_chat_id, wa_number, sender_name)
            is_new_conv = not conv.get("utm_source") and not conv.get("fbclid")

            # ── Трекинг UTM: сначала ref: код (TG-стиль), потом временное окно ──
            import re as _re
            ref_match = _re.search(r'\bref:([A-Za-z0-9_\-]{8,20})\b', text)
            if ref_match:
                # Явный ref код в тексте (на случай если пользователь скопировал)
                ref_id = ref_match.group(1)
                click_data = db.get_staff_click(ref_id)
                if click_data and not click_data.get("used"):
                    db.apply_utm_to_wa_conv(conv["id"],
                        fbclid=click_data.get("fbclid"), fbp=click_data.get("fbp"),
                        utm_source=click_data.get("utm_source"),
                        utm_medium=click_data.get("utm_medium"),
                        utm_campaign=click_data.get("utm_campaign"),
                        utm_content=click_data.get("utm_content"),
                        utm_term=click_data.get("utm_term"))
                    db.mark_staff_click_used(ref_id)
                    conv = db.get_wa_conversation(conv["id"]) or conv
                    log.info(f"[WA webhook] UTM by ref:{ref_id} utm={click_data.get('utm_campaign')}")
            elif is_new_conv:
                # Трекинг по временному окну — ищем последний клик за 30 минут
                click_data = db.get_staff_click_recent_any(minutes=30)
                if click_data:
                    db.apply_utm_to_wa_conv(conv["id"],
                        fbclid=click_data.get("fbclid"), fbp=click_data.get("fbp"),
                        utm_source=click_data.get("utm_source"),
                        utm_medium=click_data.get("utm_medium"),
                        utm_campaign=click_data.get("utm_campaign"),
                        utm_content=click_data.get("utm_content"),
                        utm_term=click_data.get("utm_term"))
                    db.mark_staff_click_used(click_data["ref_id"])
                    conv = db.get_wa_conversation(conv["id"]) or conv
                    log.info(f"[WA webhook] UTM by time-window utm={click_data.get('utm_campaign')} fbclid={'✓' if click_data.get('fbclid') else '—'}")

            db.save_wa_message(conv["id"], wa_chat_id, "visitor", text,
                               media_url=media_url, media_type=media_type)
            db.update_wa_last_message(wa_chat_id, text, increment_unread=True)
            log.info(f"[WA webhook] saved msg conv={conv['id']} from={wa_number}: {text[:50]}")

            # Уведомление менеджеру — без Markdown чтобы спецсимволы не ломали
            notify_chat = db.get_setting("notify_chat_id")
            if notify_chat:
                bot = bot_manager.get_tracker_bot() or bot_manager.get_staff_bot()
                if bot:
                    try:
                        from aiogram import types as tg_types
                        preview = text[:80] + ("..." if len(text) > 80 else "")
                        # Используем HTML вместо Markdown — надёжнее
                        safe_name    = sender_name.replace("<","&lt;").replace(">","&gt;")
                        safe_preview = preview.replace("<","&lt;").replace(">","&gt;")
                        safe_number  = str(wa_number).replace("<","&lt;")
                        await bot.send_message(
                            int(notify_chat),
                            f"💚 <b>WhatsApp — новое сообщение</b>\n"
                            f"👤 {safe_name} (+{safe_number})\n\n"
                            f"{safe_preview}",
                            parse_mode="HTML",
                            reply_markup=tg_types.InlineKeyboardMarkup(inline_keyboard=[[
                                tg_types.InlineKeyboardButton(
                                    text="Открыть WA чат →",
                                    url=f"{db.get_setting('app_url','')}/wa/chat?conv_id={conv['id']}"
                                )
                            ]])
                        )
                    except Exception as e:
                        log.warning(f"[WA webhook] notify error: {e}")

        elif event == "ready":
            db.set_setting("wa_connected_number", data.get("number", ""))
            db.set_setting("wa_status", "ready")
            log.info(f"[WA webhook] ready, number={data.get('number')}")

        elif event == "disconnected":
            db.set_setting("wa_status", "disconnected")
            db.set_setting("wa_connected_number", "")
            log.info("[WA webhook] disconnected")

        elif event == "qr":
            db.set_setting("wa_qr", data.get("qr", ""))
            db.set_setting("wa_status", "qr")
            log.info("[WA webhook] QR received")

        else:
            log.info(f"[WA webhook] unknown event: {event}")

    except Exception as e:
        # Логируем но всегда возвращаем 200 — иначе WA сервис будет ретраить бесконечно
        log.error(f"[WA webhook] ERROR event={event}: {e}", exc_info=True)

    return JSONResponse({"ok": True})


@router.get("/wa/chat", response_class=HTMLResponse)
async def wa_chat_page(request: Request, conv_id: int = 0, status_filter: str = "open"):
    user, err = require_auth(request)
    if err: return err
    convs = db.get_wa_conversations(status=status_filter if status_filter != "all" else None)
    messages_html = ""
    header_html   = ""
    active_conv   = None
    if conv_id:
        active_conv = db.get_wa_conversation(conv_id)
        if active_conv:
            db.mark_wa_read(conv_id)
            msgs = db.get_wa_messages(conv_id)
            for m in msgs:
                t = m["created_at"][11:16]
                content_html = ""
                if m.get("media_url") and (m.get("media_type","") or "").startswith("image/"):
                    content_html = f'<img src="{m["media_url"]}" style="max-width:220px;max-height:220px;border-radius:8px;display:block;cursor:pointer" onclick="window.open(this.src)" />'
                    if m.get("content") and m["content"] not in ("[фото]","[медиафайл]"):
                        content_html += f'<div style="margin-top:4px">{(m["content"] or "").replace("<","&lt;")}</div>'
                elif m.get("media_url"):
                    content_html = f'<a href="{m["media_url"]}" target="_blank" style="color:#60a5fa">📎 Открыть файл</a>'
                else:
                    content_html = (m["content"] or "").replace("<","&lt;")
                wa_sender_label = ""
                if m["sender_type"] == "manager" and m.get("sender_name"):
                    wa_sender_label = f'<div style="font-size:.68rem;color:var(--orange);margin-bottom:2px;text-align:right;opacity:.8">{m["sender_name"]}</div>'
                messages_html += f"""<div class="msg {m['sender_type']}" data-id="{m['id']}">
                  {wa_sender_label}<div class="msg-bubble">{content_html}</div>
                  <div class="msg-time">{t}</div></div>"""
            # Фото профиля WA
            wa_photo = active_conv.get("photo_url","")
            if wa_photo:
                wa_avatar = f'<img src="{wa_photo}" style="width:40px;height:40px;border-radius:50%;object-fit:cover;flex-shrink:0;border:2px solid #25d366" onerror="this.style.display=\'none\'">'
            else:
                wa_avatar = '<div style="width:40px;height:40px;border-radius:50%;background:#052e16;display:flex;align-items:center;justify-content:center;font-size:1.2rem;flex-shrink:0">💚</div>'

            fb_sent = active_conv.get("fb_event_sent")
            fb_btn  = '<span class="badge-green">✅ Lead отправлен</span>' if fb_sent else \
                      f'<form method="post" action="/wa/send_lead" style="display:inline"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-green btn-sm">📤 Lead → FB</button></form>'
            status_color = "#34d399" if active_conv["status"] == "open" else "#ef4444"
            close_btn = f'<form method="post" action="/wa/close"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-gray btn-sm">✓ Закрыть</button></form>' if active_conv["status"] == "open" else \
                        f'<form method="post" action="/wa/reopen"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-green btn-sm">↺ Открыть</button></form>'
            delete_wa_btn = f'<button class="btn-gray btn-sm" style="color:var(--red);border-color:#7f1d1d" onclick="deleteWaConv({conv_id})">🗑</button>' if user and user.get("role") == "admin" else ""

            # Карточка сотрудника для WA
            wa_staff = db.get_staff_by_wa_conv(conv_id)
            if wa_staff:
                wa_card_link = f'<a href="/staff?edit={wa_staff["id"]}" style="display:inline-flex;align-items:center;gap:4px;background:#052e16;color:#86efac;border:1px solid #166534;border-radius:6px;padding:2px 8px;font-size:.73rem;text-decoration:none">✅ В базе · {wa_staff.get("name","") or "Карточка"} →</a>'
            else:
                wa_card_link = f'<a href="/staff/create_from_wa?conv_id={conv_id}" style="display:inline-flex;align-items:center;gap:4px;background:var(--bg3);color:var(--text3);border:1px solid var(--border);border-radius:6px;padding:2px 8px;font-size:.73rem;text-decoration:none">+ Создать карточку</a>'
            wa_utm_tags = ""
            _is_wa_fb = bool(active_conv.get("fbclid") or active_conv.get("utm_source") in ("facebook", "fb"))
            utm_parts = []
            if _is_wa_fb:
                utm_parts.append('<span style="background:#1e3a5f;color:#60a5fa;padding:2px 8px;border-radius:5px;font-size:.72rem">🔵 Facebook</span>')
            elif active_conv.get("utm_source"):
                utm_parts.append(f'<span style="background:var(--border);color:var(--text2);padding:2px 8px;border-radius:5px;font-size:.72rem">{active_conv["utm_source"]}</span>')
            if active_conv.get("utm_campaign"):
                utm_parts.append(f'<span class="utm-tag" title="Кампания">🎯 {active_conv["utm_campaign"][:25]}</span>')
            if active_conv.get("utm_content"):
                utm_parts.append(f'<span class="utm-tag" style="background:#1a2a1a;color:#86efac" title="Объявление">📌 {active_conv["utm_content"][:20]}</span>')
            if active_conv.get("utm_term"):
                utm_parts.append(f'<span class="utm-tag" style="background:#1a1a2a;color:#a5b4fc" title="Адсет">📂 {active_conv["utm_term"][:20]}</span>')
            if active_conv.get("fbclid"):
                utm_parts.append('<span class="utm-tag badge-green">fbclid ✓</span>')
            if utm_parts:
                wa_utm_tags = '<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:5px">' + "".join(utm_parts) + '</div>'
            # Теги WA чата
            all_tags_wa      = db.get_all_tags()
            active_wa_ctags  = db.get_conv_tags("wa", conv_id)
            active_wa_tag_ids = {tg["id"] for tg in active_wa_ctags}
            wa_tags_html = _render_conv_tags_picker(active_wa_ctags, all_tags_wa, active_wa_tag_ids, "wa", conv_id)

            header_html = f"""<div class="chat-header">
              <div style="display:flex;align-items:flex-start;gap:12px;flex:1">
                {wa_avatar}
                <div style="flex:1">
                  <div style="font-weight:700;color:#fff">{active_conv['visitor_name']} <span style="color:{status_color};font-size:.74rem">●</span></div>
                  <div style="font-size:.79rem;color:var(--text3)">+{active_conv['wa_number']} · {wa_card_link}</div>
                  <div style="margin-top:6px">{fb_btn}</div>
                  {wa_utm_tags}
                  {wa_tags_html}
                </div>
              </div>
              <div style="display:flex;gap:6px;flex-shrink:0">
                <button class="btn-gray btn-sm" title="Обновить профиль" onclick="fetchWaProfile({conv_id})" style="font-size:.8rem">🔄</button>
                {close_btn} {delete_wa_btn}
              </div>
            </div>"""
    conv_items = ""
    wa_in_staff  = db.get_wa_conv_ids_in_staff()
    wa_tags_map  = db.get_all_conv_tags_map("wa")
    for c in convs:
        cls = "conv-item active" if c["id"] == conv_id else "conv-item"
        t = (c.get("last_message_at") or c["created_at"])[:16].replace("T"," ")
        ucount = f'<span class="unread-num" style="background:#25d366">{c["unread_count"]}</span>' if c["unread_count"] > 0 else ""
        dot = "🟢" if c["status"] == "open" else "⚫"
        if c.get("fbclid"):
            src_badge = '<span class="source-badge source-fb">🔵 FB</span>'
        elif c.get("utm_source"):
            src_badge = f'<span class="source-badge source-tg">{c["utm_source"][:12]}</span>'
        else:
            src_badge = '<span class="source-badge source-organic">organic</span>'
        _wa_is_fb = bool(c.get("fbclid") or c.get("utm_source") in ("facebook", "fb"))
        wa_utm_parts = []
        if _wa_is_fb:  # Задача 14: UTM только если не органика
            if c.get("utm_campaign"):  wa_utm_parts.append(f'<span class="utm-tag" title="Кампания">🎯 {c["utm_campaign"][:30]}</span>')
            if c.get("utm_content"):   wa_utm_parts.append(f'<span class="utm-tag" style="background:#1a2a1a;color:#86efac" title="Объявление">📌 {c["utm_content"][:20]}</span>')
            if c.get("utm_term"):      wa_utm_parts.append(f'<span class="utm-tag" style="background:#1a1a2a;color:#a5b4fc" title="Адсет">📂 {c["utm_term"][:20]}</span>')
        utm_line = '<div class="conv-meta" style="display:flex;flex-wrap:wrap;gap:3px;margin-top:2px">' + "".join(wa_utm_parts) + '</div>' if wa_utm_parts else ""
        # Задача 5: отметка "уже в базе"
        wa_staff_info = wa_in_staff.get(c["id"])
        wa_in_base = f'<span style="background:#052e16;color:#86efac;border:1px solid #166534;border-radius:5px;font-size:.65rem;padding:1px 6px;margin-left:4px;white-space:nowrap">✅ в базе</span>' if wa_staff_info else ""
        wa_display_name = c.get('username') if (c.get('visitor_name','') or '').isdigit() and c.get('username') else c.get('visitor_name') or c.get('username') or c.get('tg_chat_id','')
        # Теги
        wctags = wa_tags_map.get(c["id"], [])
        wa_tags_line = ""
        if wctags:
            wt_html = "".join(f'<span class="conv-tag" style="background:{tg["color"]}22;color:{tg["color"]};border-color:{tg["color"]}55">{tg["name"]}</span>' for tg in wctags)
            wa_tags_line = f'<div class="tags-row">{wt_html}</div>'
        conv_items += f"""<a href="/wa/chat?conv_id={c['id']}&status_filter={status_filter}"><div class="{cls}" data-conv-id="{c['id']}">
          <div class="conv-name"><span>{dot} {wa_display_name}</span>{ucount}{wa_in_base}</div>
          <div class="conv-preview">{c.get('last_message') or 'Нет сообщений'}</div>
          <div class="conv-time" style="display:flex;align-items:center;justify-content:space-between">💚 +{c['wa_number'][:10]} · {t[-5:]} {src_badge}</div>
          {utm_line}{wa_tags_line}</div></a>"""
    if not conv_items:
        conv_items = '<div class="empty" style="padding:36px 14px">Нет WA диалогов.<br><br>Подключи WhatsApp<br>в разделе WA Настройка</div>'
    wa_status = db.get_setting("wa_status", "disconnected")
    wa_number = db.get_setting("wa_connected_number", "")
    if wa_status == "ready":
        status_bar = f'<div style="background:#052e16;border:1px solid #166534;border-radius:7px;padding:8px 12px;font-size:.8rem;color:#86efac;margin-bottom:8px">💚 Подключён · +{wa_number}</div>'
    elif wa_status == "qr":
        status_bar = f'<div style="background:#422006;border:1px solid #92400e;border-radius:7px;padding:8px 12px;font-size:.8rem;color:#fbbf24;margin-bottom:8px">📱 Ожидает QR → <a href="/wa/setup" style="color:#fbbf24;text-decoration:underline">Открыть</a></div>'
    else:
        status_bar = f'<div style="background:#2d0a0a;border:1px solid #7f1d1d;border-radius:7px;padding:8px 12px;font-size:.8rem;color:#fca5a5;margin-bottom:8px">⚠️ Не подключён → <a href="/wa/setup" style="color:#fca5a5;text-decoration:underline">Подключить</a></div>'

    def wa_stab(label, val):
        active_tab = "background:#25d366;color:#fff" if val == status_filter else "background:var(--bg3);color:var(--text3)"
        return f'<a href="/wa/chat?status_filter={val}" style="flex:1;text-align:center;padding:5px 0;border-radius:7px;font-size:.78rem;font-weight:600;text-decoration:none;{active_tab}">{label}</a>'
    status_tabs = f'<div style="display:flex;gap:4px;background:var(--bg2);border-radius:9px;padding:3px;margin-bottom:8px">{wa_stab("🟢 Открытые","open")}{wa_stab("⚫ Закрытые","closed")}{wa_stab("Все","all")}</div>'

    WA_CSS = "<style>.send-btn-green{background:#25d366;color:#fff;border:none;border-radius:10px;padding:10px 18px;cursor:pointer;font-size:.87rem;font-weight:600;height:42px;flex-shrink:0}.send-btn-green:hover{background:#128c7e}.btn-green{background:#059669;color:#fff;border:none;border-radius:8px;padding:9px 18px;cursor:pointer;font-size:.85rem;font-weight:600;white-space:nowrap}.btn-green:hover{background:#047857}</style>"
    right = f"""{header_html}
    <div class="chat-messages" id="wa-msgs">{messages_html}</div>
    <div id="wa-send-error" style="display:none;padding:8px 18px;background:#2d0a0a;border-top:1px solid #7f1d1d;font-size:.8rem;color:#fca5a5;align-items:center;justify-content:space-between;gap:8px">
      <span id="wa-send-error-text"></span>
      <button onclick="document.getElementById('wa-send-error').style.display='none'" style="background:none;border:none;color:#fca5a5;cursor:pointer;font-size:1rem;line-height:1">✕</button>
    </div>
    <div class="chat-input">
      <div id="wa-disconnected-banner" style="display:{'none' if wa_status == 'ready' else 'flex'};align-items:center;justify-content:space-between;padding:8px 12px;background:#1c1a00;border:1px solid #713f12;border-radius:8px;margin-bottom:8px;font-size:.8rem;color:#fde047;gap:8px">
        <span>⚠️ WhatsApp не подключён — сообщения не будут доставлены</span>
        <a href="/wa/setup" style="color:#fde047;font-weight:600;white-space:nowrap;text-decoration:underline">Подключить →</a>
      </div>
      <div class="chat-input-row">
        <input type="file" id="wa-file-input" accept="image/*" style="display:none" onchange="sendWaFile(this)"/>
        <button class="send-btn-green" style="background:#374151;padding:10px 13px;font-size:1.1rem" onclick="document.getElementById('wa-file-input').click()" title="Отправить фото">📎</button>
        <textarea id="wa-reply" placeholder="Написать в WhatsApp… (Enter — отправить)" rows="1" onkeydown="handleWaKey(event)"></textarea>
        <button class="send-btn-green" onclick="sendWaMsg()">Отправить</button>
      </div></div>""" if active_conv and active_conv["status"] == "open" else (
        f"{header_html}<div class='no-conv'><div>Чат закрыт</div></div>" if active_conv else
        '<div class="no-conv"><div style="font-size:2.5rem">💚</div><div>Выбери диалог WhatsApp</div></div>'
    )
    content = f"""{WA_CSS}<div class="chat-layout">
      <div class="conv-list">
        <div class="conv-search">{status_bar}{status_tabs}<input type="text" placeholder="🔍 Поиск..." oninput="filterConvs(this.value)"/></div>
        <div id="conv-items">{conv_items}</div>
      </div>
      <div class="chat-window">{right}</div>
    </div>
    <script>
    const msgsEl=document.getElementById('wa-msgs');
    if(msgsEl) msgsEl.scrollTop=msgsEl.scrollHeight;
    const ACTIVE_CONV_ID = {conv_id or 0};

    async function sendWaMsg(){{
      const ta=document.getElementById('wa-reply');
      const text=ta.value.trim(); if(!text) return; ta.value='';
      try{{
        const r=await fetch('/wa/send',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},
          body:'conv_id={conv_id}&text='+encodeURIComponent(text)}});
        const d=await r.json();
        if(d.ok) loadNewWaMsgs(); else showWaError(d.error||'');
      }}catch(e){{showWaError(e.message);}}
    }}

    function showWaError(msg){{
      var errDiv=document.getElementById('wa-send-error');
      var errTxt=document.getElementById('wa-send-error-text');
      if(!errDiv||!errTxt)return;
      var isDisconn=msg&&(msg.toLowerCase().includes('not connect')||msg.toLowerCase().includes('503'));
      if(isDisconn){{
        errTxt.innerHTML='⚠️ WhatsApp не подключён. <a href="/wa/setup" style="color:#fca5a5;text-decoration:underline;font-weight:600">Подключить →</a>';
        var banner=document.getElementById('wa-disconnected-banner');
        if(banner) banner.style.display='flex';
      }}else{{
        errTxt.textContent='Ошибка: '+(msg||'неизвестная ошибка');
      }}
      errDiv.style.display='flex';
      setTimeout(function(){{errDiv.style.display='none';}},6000);
    }}

    async function sendWaFile(input){{
      const file=input.files[0]; if(!file) return;
      const btn=document.querySelector('button[onclick*="wa-file-input"]');
      btn.textContent='⏳'; btn.disabled=true;
      const fd=new FormData();
      fd.append('conv_id','{conv_id}');
      fd.append('file',file);
      try{{
        const res=await fetch('/wa/send_media',{{method:'POST',body:fd}});
        const data=await res.json();
        if(data.ok) loadNewWaMsgs(); else showWaError(data.error||'');
      }}catch(e){{showWaError(e.message);}}
      btn.textContent='📎'; btn.disabled=false;
      input.value='';
    }}
    function handleWaKey(e){{if(e.key==='Enter'&&!e.shiftKey){{e.preventDefault();sendWaMsg();}}}}

    // Polling статуса WA — обновляем баннер автоматически
    setInterval(async function(){{
      try{{
        var r=await fetch('/api/stats');if(!r.ok)return;
        var d=await r.json();
        var banner=document.getElementById('wa-disconnected-banner');
        if(banner) banner.style.display=(d.wa_status==='ready')?'none':'flex';
      }}catch(e){{}}
    }},5000);

    // Обновление сообщений в открытом чате
    {"setInterval(loadNewWaMsgs, 3000);" if active_conv else ""}

    var _waLoadingMsgs=false;
    async function loadNewWaMsgs(){{
      if(_waLoadingMsgs)return;
      _waLoadingMsgs=true;
      try{{
        const msgs=document.querySelectorAll('#wa-msgs .msg[data-id]');
        const lastId=msgs.length?msgs[msgs.length-1].dataset.id:0;
        const res=await fetch('/api/wa_messages/{conv_id}?after='+lastId);
        const data=await res.json();
        if(data.messages&&data.messages.length>0){{
          const c=document.getElementById('wa-msgs');
          data.messages.forEach(m=>{{
            if(c.querySelector('[data-id="'+m.id+'"]'))return;
            const d=document.createElement('div');
            d.className='msg '+m.sender_type;
            d.dataset.id=m.id;
            let contentHtml='';
            if(m.media_url && m.media_type && m.media_type.startsWith('image/')){{
              contentHtml='<img src="'+m.media_url+'" style="max-width:220px;max-height:220px;border-radius:8px;display:block;cursor:pointer" onclick="window.open(this.src)"/>';
              if(m.content && m.content!='[фото]' && m.content!='[медиафайл]') contentHtml+='<div style="margin-top:4px">'+esc(m.content)+'</div>';
            }} else if(m.media_url) {{
              contentHtml='<a href="'+m.media_url+'" target="_blank" style="color:#60a5fa">📎 Открыть файл</a>';
            }} else {{
              contentHtml=esc(m.content);
            }}
            d.innerHTML='<div class="msg-bubble">'+contentHtml+'</div><div class="msg-time">'+m.created_at.substring(11,16)+'</div>';
            c.appendChild(d);
          }});c.scrollTop=c.scrollHeight;}}
      }}catch(e){{}}finally{{_waLoadingMsgs=false;}}
    }}

    // Авто-обновление списка диалогов каждые 4 сек
    var WA_SF = '{status_filter}';
    let _knownConvIds = new Set([{','.join(str(c['id']) for c in (db.get_wa_conversations() if True else []))}]);
    setInterval(async function(){{
      try {{
        const res = await fetch('/api/wa_convs?status='+encodeURIComponent(WA_SF));
        const data = await res.json();
        if(!data.convs) return;
        const list = document.getElementById('conv-items');
        if(!list) return;

        const newIds = new Set(data.convs.map(c=>c.id));
        const hasNew = [...newIds].some(id=>!_knownConvIds.has(id));

        // Обновляем существующие элементы (badge + preview)
        data.convs.forEach(c=>{{
          const item = list.querySelector('[data-conv-id="'+c.id+'"]');
          if(item){{
            const badge = item.querySelector('.unread-badge');
            if(c.unread_count>0){{
              if(badge) badge.textContent=c.unread_count;
              else {{const b=document.createElement('span');b.className='unread-num unread-badge';b.style.background='#25d366';b.textContent=c.unread_count;item.querySelector('.conv-name')?.appendChild(b);}}
            }} else if(badge) badge.remove();
            const prev=item.querySelector('.conv-preview');
            if(prev) prev.textContent=c.last_message||'Нет сообщений';
          }}
        }});

        if(hasNew){{
          _knownConvIds = newIds;
          // Добавляем только новые чаты — не перерисовываем весь список
          data.convs.forEach(c=>{{
            if(list.querySelector('[data-conv-id="'+c.id+'"]')) return;
            const isFb=!!(c.fbclid||(c.utm_source&&(c.utm_source==='facebook'||c.utm_source==='fb')));
            const srcBadge=isFb?'<span class="source-badge source-fb">🔵 FB</span>':'<span class="source-badge source-organic">organic</span>';
            const inBase=c.in_staff?'<span style="background:#052e16;color:#86efac;border:1px solid #166534;border-radius:5px;font-size:.65rem;padding:1px 6px;margin-left:4px;white-space:nowrap">✅ в базе</span>':'';
            const bdg=c.unread_count>0?'<span class="unread-num unread-badge" style="background:#25d366">'+c.unread_count+'</span>':'';
            let utmHtml='';
            if(isFb){{
              if(c.utm_campaign)utmHtml+='<span class="utm-tag">🎯 '+esc(c.utm_campaign.substring(0,25))+'</span>';
              if(c.utm_content)utmHtml+='<span class="utm-tag" style="background:#1a2a1a;color:#86efac">📌 '+esc(c.utm_content.substring(0,20))+'</span>';
              if(c.utm_term)utmHtml+='<span class="utm-tag" style="background:#1a1a2a;color:#a5b4fc">📂 '+esc(c.utm_term.substring(0,20))+'</span>';
            }}
            const utmLine=utmHtml?'<div class="conv-meta" style="display:flex;flex-wrap:wrap;gap:3px;margin-top:2px">'+utmHtml+'</div>':'';
            let tagsHtml='';
            if(c.tags&&c.tags.length){{c.tags.forEach(function(tg){{tagsHtml+='<span class="conv-tag" style="background:'+tg.color+'22;color:'+tg.color+';border-color:'+tg.color+'55">'+esc(tg.name)+'</span>';}});}}
            const tagsLine=tagsHtml?'<div class="tags-row">'+tagsHtml+'</div>':'';
            const dot=c.status==='open'?'🟢':'⚫';
            const el=document.createElement('div');
            el.innerHTML='<a href="/wa/chat?conv_id='+c.id+'&status_filter='+WA_SF+'"><div class="conv-item" data-conv-id="'+c.id+'">'
              +'<div class="conv-name"><span>'+dot+' '+esc(c.visitor_name)+'</span>'+bdg+inBase+'</div>'
              +'<div class="conv-preview">'+esc(c.last_message||'Нет сообщений')+'</div>'
              +'<div class="conv-time" style="display:flex;align-items:center;justify-content:space-between">💚 +'+c.wa_number.substring(0,10)+' · '+c.last_message_at.substring(11,16)+' '+srcBadge+'</div>'
              +utmLine+tagsLine
              +'</div></a>';
            list.insertBefore(el.firstChild, list.firstChild);
          }});
        }}
      }} catch(e){{}}
    }}, 4000);

    // SPA навигация для WA чатов
    var _waPageLoading = false;
    document.getElementById('conv-items')?.addEventListener('click', function(e){{
      const link = e.target.closest('a[href*="/wa/chat?conv_id="]');
      if(!link) return;
      e.preventDefault();
      const url = new URL(link.href);
      const cid = parseInt(url.searchParams.get('conv_id'));
      const sf  = url.searchParams.get('status_filter') || WA_SF;
      if(cid) loadWaChat(cid, sf);
    }});
    async function loadWaChat(convId, sfParam){{
      if(_waPageLoading) return;
      _waPageLoading = true;
      const chatWin = document.querySelector('.chat-window');
      if(chatWin) chatWin.style.opacity='0.5';
      try{{
        const r = await fetch('/api/wa_chat_panel?conv_id='+convId+'&status_filter='+(sfParam||WA_SF));
        if(!r.ok) throw new Error(r.status);
        const html = await r.text();
        if(chatWin){{ chatWin.innerHTML=html; chatWin.style.opacity='1'; }}
        document.querySelectorAll('#conv-items .conv-item').forEach(function(el){{
          const isActive = el.dataset.convId == String(convId);
          el.classList.toggle('active', isActive);
          if(isActive){{ const b=el.querySelector('.unread-badge'); if(b) b.remove(); }}
        }});
        history.pushState(null,'','/wa/chat?conv_id='+convId+'&status_filter='+(sfParam||WA_SF));
        window.ACTIVE_CONV_ID = convId;
        WA_SF = sfParam || WA_SF;
      }}catch(e){{ if(chatWin) chatWin.style.opacity='1'; }}
      _waPageLoading = false;
    }}

    function esc(t){{return(t||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\\n/g,'<br>');}}
    function filterConvs(q){{document.querySelectorAll('.conv-item').forEach(el=>{{
      const n=el.querySelector('.conv-name')?.textContent?.toLowerCase()||'';
      el.parentElement.style.display=n.includes(q.toLowerCase())?'':'none';}});}}
    async function deleteWaConv(id){{
      if(!confirm('Удалить WA чат и все сообщения? Это нельзя отменить.')) return;
      const r=await fetch('/wa/delete',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:'conv_id='+id}});
      const d=await r.json();
      if(d.ok) window.location.href='/wa/chat?status_filter={status_filter}';
      else alert('Ошибка удаления');
    }}
    async function fetchWaProfile(convId){{
      const btn=document.querySelector('button[onclick*="fetchWaProfile"]');
      if(btn){{btn.textContent='⏳';btn.disabled=true;}}
      const r=await fetch('/wa/fetch_profile',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:'conv_id='+convId}});
      const d=await r.json();
      if(d.ok) window.location.reload();
      else alert('Не удалось получить профиль: '+(d.error||''));
      if(btn){{btn.textContent='🔄';btn.disabled=false;}}
    }}
    </script>"""
    return HTMLResponse(f'<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WA Чаты</title><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">{CSS}</head><body>{nav_html("wa_chat",request)}<div class="main">{content}</div></body></html>')


@router.get("/wa/setup", response_class=HTMLResponse)
async def wa_setup_page(request: Request, msg: str = "", err: str = ""):
    user, err_auth = require_auth(request, role="admin")
    if err_auth: return err_auth
    wa_data   = await wa_api("get", "/status")
    wa_status = wa_data.get("status", "disconnected")
    wa_number = wa_data.get("number", "")
    db.set_setting("wa_status", wa_status)
    if wa_number: db.set_setting("wa_connected_number", wa_number)
    qr_html = ""
    if wa_status == "qr":
        qr_data = await wa_api("get", "/qr")
        qr = qr_data.get("qr", "")
        if qr:
            qr_html = f"""<div style="text-align:center;padding:20px">
              <img src="{qr}" style="width:220px;height:220px;border-radius:12px;border:2px solid #25d366"/>
              <div style="color:#86efac;margin-top:12px;font-size:.88rem">Открой WhatsApp → Связанные устройства → Привязать устройство</div>
              <div style="color:var(--text3);font-size:.78rem;margin-top:6px">Обновление через <span id="cd">20</span>с
              <script>let t=20;setInterval(()=>{{const el=document.getElementById('cd');if(el)el.textContent=--t;if(t<=0)location.reload()}},1000)</script></div>
            </div>"""
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""
    err_alert = f'<div class="alert-red">❌ {err}<br><small>Проверь что WA сервис запущен на Railway</small></div>' if err else ""
    WA_BTN_CSS = "<style>.btn-green{background:#059669;color:#fff;border:none;border-radius:8px;padding:9px 18px;cursor:pointer;font-size:.85rem;font-weight:600}.btn-green:hover{background:#047857}</style>"
    if wa_status == "ready":
        status_html = f'<div style="color:#34d399;font-size:1rem;font-weight:600">💚 Подключён · +{wa_number}</div>'
        action_btn  = f"""<div style="margin-top:16px"><form method="post" action="/wa/disconnect">
            <button class="btn-red">🔄 Сменить номер (отключить)</button></form>
            <div style="font-size:.78rem;color:var(--text3);margin-top:6px">После отключения отсканируй QR новым номером</div></div>"""
    elif wa_status == "qr":
        status_html = '<div style="color:#fbbf24;font-size:1rem;font-weight:600">📱 Ожидает сканирования QR...</div>'
        action_btn  = ""
    else:
        status_html = '<div style="color:var(--red);font-size:1rem;font-weight:600">⚠️ Не подключён</div>'
        action_btn  = """<div style="margin-top:16px"><form method="post" action="/wa/connect">
            <button class="btn-green">💚 Подключить WhatsApp</button></form>
            <div style="font-size:.78rem;color:var(--text3);margin-top:6px">Появится QR-код для сканирования</div></div>"""
    content = f"""<div class="page-wrap">
    <div class="page-title">💚 WhatsApp — Управление</div>
    <div class="page-sub">Подключение и смена номера</div>{alert}{err_alert}
    <div class="section" style="border-left:3px solid #25d366">
      <div class="section-head"><h3>📱 Статус подключения</h3></div>
      <div class="section-body">{WA_BTN_CSS}{status_html}{qr_html}{action_btn}</div>
    </div>
    <div class="section"><div class="section-head"><h3>ℹ️ Как это работает</h3></div>
      <div class="section-body" style="font-size:.85rem;color:var(--text3);line-height:2">
        <div>1. Нажми "Подключить WhatsApp" — появится QR-код</div>
        <div>2. Открой WhatsApp → Связанные устройства → Привязать устройство</div>
        <div>3. Отсканируй QR — подключение займёт ~10 секунд</div>
        <div>4. Если номер заблокировали → "Сменить номер" → подключи новый</div>
        <div style="margin-top:8px;color:#fbbf24">⚠️ Используй отдельный номер, не основной</div>
      </div></div></div>"""
    return HTMLResponse(base(content, "wa_setup", request))


@router.post("/wa/connect")
async def wa_connect(request: Request):
    user, err = require_auth(request, role="admin")
    if err: return err
    if not WA_URL:
        return RedirectResponse("/wa/setup?err=WA_SERVICE_URL+не+настроен+в+переменных", 303)
    result = await wa_api("post", "/connect")
    if result.get("error"):
        return RedirectResponse(f"/wa/setup?err={result['error']}", 303)
    return RedirectResponse("/wa/setup?msg=Подключение+запущено+—+ожидай+QR", 303)


@router.post("/wa/disconnect")
async def wa_disconnect(request: Request):
    user, err = require_auth(request, role="admin")
    if err: return err
    await wa_api("post", "/disconnect")
    db.set_setting("wa_status", "disconnected")
    db.set_setting("wa_connected_number", "")
    return RedirectResponse("/wa/setup?msg=Отключено+—+подключи+новый+номер", 303)


@router.post("/wa/send")
async def wa_send(request: Request, conv_id: int = Form(...), text: str = Form(...)):
    user, err = require_auth(request)
    if err: return JSONResponse({"error": "unauthorized"}, 401)
    conv = db.get_wa_conversation(conv_id)
    if not conv: return JSONResponse({"error": "not found"}, 404)

    # Используем wa_chat_id напрямую — он уже содержит правильный формат от WA сервиса
    # wa_chat_id = "38088390742096@c.us" или "38088390742096@lid" для новых аккаунтов
    to = conv["wa_chat_id"]
    log.info(f"[WA send] to={to} conv_id={conv_id} text={text[:30]}")

    result = await wa_api("post", "/send", json={"to": to, "message": text})
    log.info(f"[WA send] result={result}")

    if not result.get("error"):
        manager_name = user.get("display_name") or user.get("username") or "Менеджер"
        db.save_wa_message(conv_id, conv["wa_chat_id"], "manager", text, sender_name=manager_name)
        db.update_wa_last_message(conv["wa_chat_id"], f"Вы: {text}", increment_unread=False)
    return JSONResponse({"ok": not result.get("error"), "error": result.get("error")})


@router.post("/wa/send_media")
async def wa_send_media(request: Request, conv_id: int = Form(...), file: UploadFile = File(...)):
    user, err = require_auth(request)
    if err: return JSONResponse({"error": "unauthorized"}, 401)
    conv = db.get_wa_conversation(conv_id)
    if not conv: return JSONResponse({"error": "not found"}, 404)

    import base64
    file_data = await file.read()
    b64 = base64.b64encode(file_data).decode()
    mimetype = file.content_type or "image/jpeg"
    filename = file.filename or "photo.jpg"

    to = conv["wa_chat_id"]
    log.info(f"[WA send_media] to={to} conv_id={conv_id} file={filename} mime={mimetype} size={len(file_data)}")

    result = await wa_api("post", "/send_media", json={
        "to": to,
        "base64": b64,
        "mimetype": mimetype,
        "filename": filename,
        "caption": ""
    })
    log.info(f"[WA send_media] result={result}")

    if not result.get("error"):
        db.save_wa_message(conv_id, conv["wa_chat_id"], "manager", "[фото]",
                           media_url=None, media_type=mimetype)
        db.update_wa_last_message(conv["wa_chat_id"], "Вы: [фото]", increment_unread=False)
    return JSONResponse({"ok": not result.get("error"), "error": result.get("error")})


@router.post("/wa/delete")
async def wa_delete(request: Request, conv_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return JSONResponse({"error": "unauthorized"}, 401)
    try:
        db.delete_wa_conversation(conv_id)
        return JSONResponse({"ok": True})
    except Exception as e:
        log.error(f"[wa/delete] error: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


@router.post("/wa/fetch_profile")
async def wa_fetch_profile(request: Request, conv_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return JSONResponse({"error": "unauthorized"}, 401)
    conv = db.get_wa_conversation(conv_id)
    if not conv: return JSONResponse({"ok": False, "error": "not found"})
    try:
        result = await wa_api("post", "/contact_info", json={"wa_chat_id": conv["wa_chat_id"]})
        log.info(f"[wa/fetch_profile] result={result}")
        if result.get("ok"):
            db.update_wa_conv_profile(
                conv_id,
                photo_url=result.get("photo_url"),
                bio=result.get("about")
            )
            # Обновляем имя если получили
            if result.get("name") and result["name"] != conv["visitor_name"]:
                with db._conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute("UPDATE wa_conversations SET visitor_name=%s WHERE id=%s",
                                    (result["name"], conv_id))
                    conn.commit()
        return JSONResponse({"ok": True})
    except Exception as e:
        log.error(f"[wa/fetch_profile] {e}")
        return JSONResponse({"ok": False, "error": str(e)})


@router.post("/wa/send_lead")
async def wa_send_lead(request: Request, conv_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    conv = db.get_wa_conversation(conv_id)
    if not conv: return RedirectResponse("/wa/chat", 303)
    if conv.get("fb_event_sent"):
        return RedirectResponse(f"/wa/chat?conv_id={conv_id}", 303)
    # Пиксель сотрудников
    pixel_id   = db.get_setting("pixel_id_staff") or db.get_setting("pixel_id")
    meta_token = db.get_setting("meta_token_staff") or db.get_setting("meta_token")
    fbclid   = conv.get("fbclid")
    fbp      = conv.get("fbp")
    campaign = conv.get("utm_campaign") or "whatsapp"
    utm_src  = conv.get("utm_source") or "whatsapp"
    test_event_code = db.get_setting("test_event_code") or None
    wa_number = conv.get("wa_number", "")
    sent = await meta_capi.send_lead_event(
        pixel_id, meta_token,
        user_id=wa_number,
        campaign=campaign,
        fbclid=fbclid,
        fbp=fbp,
        utm_source=utm_src,
        utm_campaign=campaign,
        test_event_code=test_event_code,
        event_source_url=f"https://wa.me/{wa_number}" if wa_number else "https://wa.me/",
    )
    if sent:
        db.set_wa_fb_event(conv_id, "Lead")
    # TikTok Lead
    tt_pixel = db.get_setting("tt_pixel_id")
    tt_token = db.get_setting("tt_access_token")
    if tt_pixel and tt_token:
        await send_tiktok_event(tt_pixel, tt_token, "SubmitForm",
            user_id=conv.get("wa_number", ""),
            ip=request.client.host if request.client else None)
    return RedirectResponse(f"/wa/chat?conv_id={conv_id}", 303)


@router.post("/wa/close")
async def wa_close(request: Request, conv_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.close_wa_conversation(conv_id)
    return RedirectResponse(f"/wa/chat?conv_id={conv_id}", 303)


@router.post("/wa/reopen")
async def wa_reopen(request: Request, conv_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.reopen_wa_conversation(conv_id)
    return RedirectResponse(f"/wa/chat?conv_id={conv_id}", 303)


@router.get("/api/wa_messages/{conv_id}")
async def api_wa_messages(request: Request, conv_id: int, after: int = 0):
    user = check_session(request)
    if not user: return JSONResponse({"error": "unauthorized"}, 401)
    return JSONResponse({"messages": db.get_new_wa_messages(conv_id, after)})
