"""
routers/chat_bot.py — TG бот чат (/chat роуты)

Подключается в main.py:
    chat_bot_setup(db, log, require_auth, base, nav_html, _render_conv_tags_picker, bot_manager, meta_capi)
    app.include_router(chat_bot_router)
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
bot_manager   = None
meta_capi     = None
tiktok_capi   = None


def setup(_db, _log, _require_auth, _base, _nav_html, _render_conv_tags_picker_fn, _bot_manager, _meta_capi, _tiktok_capi=None):
    global db, log, require_auth, base, nav_html, _render_conv_tags_picker
    db             = _db
    log            = _log
    require_auth   = _require_auth
    base           = _base
    nav_html       = _nav_html
    _render_conv_tags_picker = _render_conv_tags_picker_fn
    global bot_manager, meta_capi, tiktok_capi
    bot_manager    = _bot_manager
    meta_capi      = _meta_capi
    tiktok_capi    = _tiktok_capi


# CHAT
# ══════════════════════════════════════════════════════════════════════════════

def _resolve_pixels(conv: dict) -> dict:
    """
    Определяет пиксели для отправки Lead события.
    Приоритет: проект по utm_campaign → глобальные настройки.
    Возвращает dict с ключами: fb_pixel, fb_token, tt_pixel, tt_token, test_event_code, project_name
    """
    utm_campaign = conv.get("utm_campaign") or ""
    project = db.get_project_by_utm(utm_campaign) if utm_campaign else None

    if project:
        fb_pixel  = project.get("fb_pixel_id") or db.get_setting("pixel_id_staff") or db.get_setting("pixel_id")
        fb_token  = project.get("fb_token")    or db.get_setting("meta_token_staff") or db.get_setting("meta_token")
        tt_pixel  = project.get("tt_pixel_id") or db.get_setting("tt_pixel_id")
        tt_token  = project.get("tt_token")    or db.get_setting("tt_access_token")
        proj_name = project.get("name", "")
    else:
        fb_pixel  = db.get_setting("pixel_id_staff") or db.get_setting("pixel_id")
        fb_token  = db.get_setting("meta_token_staff") or db.get_setting("meta_token")
        tt_pixel  = db.get_setting("tt_pixel_id")
        tt_token  = db.get_setting("tt_access_token")
        proj_name = ""

    return {
        "fb_pixel":        fb_pixel,
        "fb_token":        fb_token,
        "tt_pixel":        tt_pixel,
        "tt_token":        tt_token,
        "test_event_code": db.get_setting("test_event_code") or None,
        "project_name":    proj_name,
    }



@router.get("/chat", response_class=HTMLResponse)
async def chat_panel(request: Request, conv_id: int = 0, status_filter: str = "open"):
    user, err = require_auth(request)
    if err: return err

    convs = db.get_conversations(status=status_filter if status_filter != "all" else None)
    messages_html = ""
    header_html = ""
    active_conv = None

    if conv_id:
        active_conv = db.get_conversation(conv_id)
        if active_conv:
            db.mark_conversation_read(conv_id)
            msgs = db.get_messages(conv_id)
            staff = db.get_staff_by_conv(conv_id)
            utm = db.get_utm_by_conv(conv_id)
            for m in msgs:
                t = m["created_at"][11:16]
                if m.get("media_url") and m.get("media_type","").startswith("image"):
                    bubble = f'<img src="{m["media_url"]}" class="msg-img" onclick="window.open(this.src)" />'
                else:
                    bubble = f'<div class="msg-bubble">{(m["content"] or "").replace("<","&lt;").replace(chr(10),"<br>")}</div>'
                sender_label = ""
                if m["sender_type"] == "manager" and m.get("sender_name"):
                    sender_label = f'<div style="font-size:.68rem;color:var(--orange);margin-bottom:2px;text-align:right;opacity:.8">{m["sender_name"]}</div>'
                messages_html += f'<div class="msg {m["sender_type"]}" data-id="{m["id"]}">{sender_label}{bubble}<div class="msg-time">{t}</div></div>'

            # Приоритет: username > visitor_name > tg_chat_id
            _username = active_conv.get('username')
            _vname    = active_conv.get('visitor_name','')
            uname = f"@{_username}" if _username else active_conv.get('tg_chat_id','')
            # Если visitor_name выглядит как числовой ID — заменяем на username
            if _vname and _vname.isdigit() and _username:
                pass  # display_name ниже подставит username
            display_name = _username if (_vname.isdigit() and _username) else (_vname or uname)
            status_color = "var(--green)" if active_conv["status"] == "open" else "var(--red)"
            # Аватарка
            photo_url = active_conv.get("photo_url","")
            if photo_url:
                avatar_html = f'<div style="position:relative;flex-shrink:0;cursor:pointer" onclick="this.querySelector(\'.avatar-zoom\').classList.toggle(\'show\')">'                              f'<img src="{photo_url}" style="width:40px;height:40px;border-radius:50%;object-fit:cover;transition:transform .2s" '                              f'onmouseover="this.style.transform=\'scale(1.1)\'" onmouseout="this.style.transform=\'scale(1)\'" '                              f'onerror="this.style.display=\'none\';this.nextSibling.style.display=\'flex\'" />'                              f'<div class="avatar" style="display:none">{active_conv["visitor_name"][0].upper()}</div>'                              f'<div class="avatar-zoom" style="display:none;position:absolute;top:48px;left:0;z-index:999;border-radius:12px;box-shadow:0 8px 32px rgba(0,0,0,.5);overflow:hidden">'                              f'<img src="{photo_url}" style="width:200px;height:200px;object-fit:cover;display:block" /></div>'                              f'</div>'
            else:
                avatar_html = f'<div class="avatar">{active_conv["visitor_name"][0].upper()}</div>'

            # Доп инфо из профиля TG
            profile_info = ""
            if active_conv.get("phone"):
                profile_info += f'<span style="font-size:.75rem;color:#60a5fa">📱 {active_conv["phone"]}</span> '
            if active_conv.get("bio"):
                profile_info += f'<div style="font-size:.74rem;color:var(--text3);margin-top:2px;font-style:italic">{active_conv["bio"][:80]}</div>'

            # UTM и источник
            utm_tags = ""
            if utm or active_conv.get("utm_source") or active_conv.get("fbclid"):
                src = utm.get("utm_source") if utm else active_conv.get("utm_source","")
                campaign = utm.get("utm_campaign") if utm else active_conv.get("utm_campaign","")
                fbclid = utm.get("fbclid") if utm else active_conv.get("fbclid","")
                utm_medium = utm.get("utm_medium","") if utm else ""
                utm_content = utm.get("utm_content","") if utm else ""
                utm_term = utm.get("utm_term","") if utm else ""

                tags = []
                if fbclid or src in ("facebook","fb","instagram"):
                    tags.append('<span class="utm-tag" style="background:#1e3a5f;color:#60a5fa">🔵 Facebook</span>')
                elif src:
                    tags.append(f'<span class="utm-tag">{src}</span>')
                if campaign: tags.append(f'<span class="utm-tag" title="campaign">🎯 {campaign[:25]}</span>')
                if utm_content: tags.append(f'<span class="utm-tag" title="ad">📌 {utm_content[:20]}</span>')
                if utm_term: tags.append(f'<span class="utm-tag" title="adset">{utm_term[:20]}</span>')
                if fbclid: tags.append('<span class="utm-tag badge-green">fbclid ✓</span>')
                if tags:
                    utm_tags = '<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:6px">' + "".join(tags) + '</div>'

            # Lead статус
            is_lead = (staff and staff.get("fb_event_sent")) or active_conv.get("fb_event_sent")
            lead_badge = '<span class="badge-green" style="font-size:.7rem;padding:2px 8px">✅ Lead отправлен</span>' if is_lead else \
                         f'<form method="post" action="/chat/send_lead" style="display:inline"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn btn-sm" style="font-size:.73rem;background:#1e3a5f;border:1px solid #3b5998;color:#93c5fd">📤 Lead → FB</button></form>'

            tg_number = active_conv.get("tg_chat_id","")
            _uname = active_conv.get('username')
            if _uname:
                call_url = f"https://t.me/{_uname}"
            elif tg_number:
                call_url = f"tg://user?id={tg_number}"
            else:
                call_url = None
            call_btn = f'<a href="{call_url}" target="_blank" class="btn-gray btn-sm" style="display:inline-flex;align-items:center;gap:4px;padding:5px 10px;border-radius:7px;font-size:.74rem;border:1px solid var(--border);text-decoration:none">📞 Звонок</a>' if call_url else ""

            close_btn = (f'<form method="post" action="/chat/close"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-gray btn-sm">✓ Закрыть</button></form>'
                        if active_conv["status"] == "open"
                        else f'<form method="post" action="/chat/reopen"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-orange btn-sm">↺ Открыть</button></form>')

            delete_btn = f'<button class="btn-gray btn-sm" style="color:var(--red);border-color:#7f1d1d" onclick="deleteConv({conv_id})">🗑</button>' if user and user.get("role") == "admin" else ""

            staff_link = f'<a href="/staff?edit={staff["id"]}" style="color:var(--orange);font-size:.74rem;text-decoration:none">Карточка →</a>' if staff else \
                         f'<a href="/staff/create_from_conv?conv_id={conv_id}" style="color:var(--text3);font-size:.74rem;text-decoration:none">+ Создать карточку</a>'

            header_html = f"""<div class="chat-header">
              <div style="display:flex;align-items:flex-start;gap:12px;flex:1">
                {avatar_html}
                <div style="flex:1">
                  <div style="font-weight:700;color:var(--text)">{display_name} <span style="color:{status_color};font-size:.72rem">●</span></div>
                  <div style="font-size:.78rem;color:var(--text3)">{uname} {staff_link}</div>
                  {profile_info}
                  <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:6px;align-items:center">
                    {lead_badge} {call_btn}
                  </div>
                  {utm_tags}
                </div>
              </div>
              <div style="display:flex;gap:6px;flex-shrink:0">{close_btn} {delete_btn}</div>
            </div>"""

    conv_items = ""
    for c in convs:
        cls = "conv-item active" if c["id"] == conv_id else "conv-item"
        t = (c.get("last_message_at") or c["created_at"])[:16].replace("T"," ")
        ucount = f'<span class="unread-num">{c["unread_count"]}</span>' if c["unread_count"] > 0 else ""
        dot = "🟢" if c["status"] == "open" else "⚫"
        # Source badge
        _utm_src = c.get("utm_source", "")
        if c.get("fbclid") or _utm_src in ("facebook","fb"):
            src_badge = '<span class="source-badge source-fb">🔵 FB</span>'
        elif _utm_src in ("tiktok","tt","tik_tok"):
            src_badge = '<span class="source-badge" style="background:#ff2d55;color:#fff">🎵 TikTok</span>'
        elif c.get("utm_source"):
            src_badge = f'<span class="source-badge source-tg">{c["utm_source"][:12]}</span>'
        else:
            src_badge = '<span class="source-badge source-organic">organic</span>'
        utm_line = ""
        utm_parts = []
        if c.get("utm_campaign"):  utm_parts.append(f'<span class="utm-tag" title="Кампания">🎯 {c["utm_campaign"][:30]}</span>')
        if c.get("utm_content"):   utm_parts.append(f'<span class="utm-tag" style="background:#1a2a1a;color:#86efac" title="Объявление">📌 {c["utm_content"][:20]}</span>')
        if c.get("utm_term"):      utm_parts.append(f'<span class="utm-tag" style="background:#1a1a2a;color:#a5b4fc" title="Адсет">📂 {c["utm_term"][:20]}</span>')
        if utm_parts:
            utm_line = '<div class="conv-meta" style="display:flex;flex-wrap:wrap;gap:3px;margin-top:2px">' + "".join(utm_parts) + '</div>'
        conv_items += f"""<a href="/chat?conv_id={c['id']}&status_filter={status_filter}"><div class="{cls}">
          <div class="conv-name"><span>{dot} {c.get('username') if (c.get('visitor_name','') or '').isdigit() and c.get('username') else c.get('visitor_name') or c.get('username') or c.get('tg_chat_id','')}</span>{ucount}</div>
          <div class="conv-preview">{c.get('last_message') or 'Нет сообщений'}</div>
          <div class="conv-time" style="display:flex;align-items:center;justify-content:space-between">{t} {src_badge}</div>
          {utm_line}</div></a>"""

    if not conv_items:
        conv_items = '<div class="empty" style="padding:36px 14px">Диалогов нет</div>'

    b2 = bot_manager.get_staff_bot()
    bot_warn = "" if b2 else '<div style="background:rgba(249,115,22,.1);border:1px solid rgba(249,115,22,.3);border-radius:8px;padding:9px 12px;font-size:.79rem;color:var(--orange);margin-bottom:8px">⚠️ Бот не запущен — <a href="/settings" style="color:var(--orange);text-decoration:underline">Настройки</a></div>'

    # Табы фильтра статуса
    def stab(label, val):
        active_tab = "background:var(--orange);color:#fff" if val == status_filter else "background:var(--bg3);color:var(--text3)"
        return f'<a href="/chat?status_filter={val}" style="flex:1;text-align:center;padding:5px 0;border-radius:7px;font-size:.78rem;font-weight:600;text-decoration:none;{active_tab}">{label}</a>'

    status_tabs = f'<div style="display:flex;gap:4px;background:var(--bg2);border-radius:9px;padding:3px;margin-bottom:8px">{stab("🟢 Открытые","open")}{stab("⚫ Закрытые","closed")}{stab("Все","all")}</div>'

    right = f"""{header_html}
    <div class="chat-messages" id="msgs">{messages_html}</div>
    <div class="chat-input"><div class="chat-input-row">
      <input type="file" id="tg-file-input" accept="image/*,video/*,.pdf,.doc,.docx" style="display:none" onchange="sendTgFile(this)"/>
      <button class="send-btn-orange" style="background:#374151;padding:10px 13px;font-size:1.1rem" onclick="document.getElementById('tg-file-input').click()" title="Отправить файл">📎</button>
      <textarea id="reply-text" placeholder="Ответить… (Enter — отправить)" rows="1" onkeydown="handleKey(event)"></textarea>
      <button class="send-btn-orange" onclick="sendMsg()">Отправить</button>
    </div></div>""" if active_conv else '<div class="no-conv"><div style="font-size:2.5rem">👔</div><div>Выбери диалог</div></div>'

    content = f"""<div class="chat-layout">
      <div class="conv-list">
        <div class="conv-search">{bot_warn}{status_tabs}<input type="text" placeholder="🔍 Поиск..." oninput="filterConvs(this.value)"/></div>
        <div id="conv-items">{conv_items}</div>
      </div>
      <div class="chat-window">{right}</div>
    </div>
    <script>
    const msgsEl=document.getElementById('msgs');
    if(msgsEl) msgsEl.scrollTop=msgsEl.scrollHeight;
    async function sendMsg(){{
      const ta=document.getElementById('reply-text');
      const text=ta.value.trim(); if(!text) return; ta.value='';
      await fetch('/chat/send',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:'conv_id={conv_id}&text='+encodeURIComponent(text)}});
      loadNewMsgs();
    }}
    function handleKey(e){{if(e.key==='Enter'&&!e.shiftKey){{e.preventDefault();sendMsg();}}}}
    async function sendTgFile(input){{
      const file=input.files[0]; if(!file) return;
      const btn=document.querySelector('button[onclick*="tg-file-input"]');
      btn.textContent='⏳'; btn.disabled=true;
      const fd=new FormData(); fd.append('conv_id','{conv_id}'); fd.append('file',file);
      try{{
        const res=await fetch('/chat/send_media',{{method:'POST',body:fd}});
        const data=await res.json();
        if(data.ok) loadNewMsgs();
        else alert('Ошибка: '+(data.error||'неизвестно'));
      }}catch(e){{alert('Ошибка: '+e.message);}}
      btn.textContent='📎'; btn.disabled=false; input.value='';
    }}
    async function deleteConv(id){{
      if(!confirm('Удалить чат и все сообщения? Это действие нельзя отменить.')) return;
      const r=await fetch('/chat/delete',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:'conv_id='+id}});
      const d=await r.json();
      if(d.ok) window.location.href='/chat?status_filter={status_filter}';
      else alert('Ошибка удаления');
    }}
    {"setInterval(loadNewMsgs,3000);" if active_conv else ""}
    async function loadNewMsgs(){{
      const msgs=document.querySelectorAll('#msgs .msg[data-id]');
      const lastId=msgs.length?msgs[msgs.length-1].dataset.id:0;
      const res=await fetch('/api/messages/{conv_id}?after='+lastId);
      const data=await res.json();
      if(data.messages&&data.messages.length>0){{
        const c=document.getElementById('msgs');
        data.messages.forEach(m=>{{const d=document.createElement('div');d.className='msg '+m.sender_type;d.dataset.id=m.id;
          let inner = m.media_url && (m.media_type||'').startsWith('image') ?
            '<img src="'+m.media_url+'" class="msg-img" onclick="window.open(this.src)"/>' :
            '<div class="msg-bubble">'+esc(m.content||'')+'</div>';
          d.innerHTML=inner+'<div class="msg-time">'+m.created_at.substring(11,16)+'</div>';
          c.appendChild(d);}});c.scrollTop=c.scrollHeight;}}
    }}
    function esc(t){{return(t||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\\n/g,'<br>');}}
    function filterConvs(q){{document.querySelectorAll('.conv-item').forEach(el=>{{
      const n=el.querySelector('.conv-name')?.textContent?.toLowerCase()||'';
      el.parentElement.style.display=n.includes(q.toLowerCase())?'':'none';}});}}
    </script>"""

    return HTMLResponse(base(content, "chat", request))


@router.post("/chat/send")
async def chat_send(request: Request, conv_id: int = Form(...), text: str = Form(...)):
    user, err = require_auth(request)
    if err: return JSONResponse({"error": "unauthorized"}, 401)
    conv = db.get_conversation(conv_id)
    if not conv: return JSONResponse({"error": "not found"}, 404)
    ok = await bot_manager.send_staff_message(conv["tg_chat_id"], text)
    if ok:
        manager_name = user.get("display_name") or user.get("username") or "Менеджер"
        db.save_message(conv_id, conv["tg_chat_id"], "manager", text, sender_name=manager_name)
        db.update_conversation_last_message(conv["tg_chat_id"], f"Вы: {text}", increment_unread=False)
    return JSONResponse({"ok": ok})


@router.post("/chat/send_media")
async def chat_send_media(request: Request, conv_id: int = Form(...), file: UploadFile = File(...)):
    user, err = require_auth(request)
    if err: return JSONResponse({"error": "unauthorized"}, 401)
    conv = db.get_conversation(conv_id)
    if not conv: return JSONResponse({"error": "not found"}, 404)

    import io
    from aiogram.types import BufferedInputFile
    file_data = await file.read()
    mimetype  = file.content_type or "application/octet-stream"
    filename  = file.filename or "file"
    tg_chat_id = conv["tg_chat_id"]

    bot = bot_manager.get_staff_bot()
    if not bot:
        return JSONResponse({"ok": False, "error": "Bot not connected"})

    try:
        buf = BufferedInputFile(file_data, filename=filename)
        if mimetype.startswith("image/"):
            sent = await bot.send_photo(int(tg_chat_id), buf)
            text = "[фото]"
        elif mimetype.startswith("video/"):
            sent = await bot.send_video(int(tg_chat_id), buf)
            text = "[видео]"
        else:
            sent = await bot.send_document(int(tg_chat_id), buf)
            text = f"[файл: {filename}]"

        # Сохраняем ссылку через Telegram file_id
        bot_token = db.get_setting("bot2_token") or ""
        media_url = None
        if bot_token:
            try:
                if mimetype.startswith("image/") and sent.photo:
                    tg_file = await bot.get_file(sent.photo[-1].file_id)
                elif mimetype.startswith("video/") and sent.video:
                    tg_file = await bot.get_file(sent.video.file_id)
                elif sent.document:
                    tg_file = await bot.get_file(sent.document.file_id)
                else:
                    tg_file = None
                if tg_file:
                    media_url = f"https://api.telegram.org/file/bot{bot_token}/{tg_file.file_path}"
            except Exception: pass

        db.save_message(conv_id, tg_chat_id, "manager", text, media_url=media_url, media_type=mimetype)
        db.update_conversation_last_message(tg_chat_id, f"Вы: {text}", increment_unread=False)
        return JSONResponse({"ok": True})
    except Exception as e:
        log.error(f"[chat/send_media] error: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


@router.post("/chat/delete")
async def chat_delete(request: Request, conv_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return JSONResponse({"error": "unauthorized"}, 401)
    try:
        db.delete_conversation(conv_id)
        return JSONResponse({"ok": True})
    except Exception as e:
        log.error(f"[chat/delete] error: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


@router.post("/chat/close")
async def chat_close(request: Request, conv_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.close_conversation(conv_id)
    return RedirectResponse(f"/chat?conv_id={conv_id}", 303)


@router.post("/chat/reopen")
async def chat_reopen(request: Request, conv_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.reopen_conversation(conv_id)
    return RedirectResponse(f"/chat?conv_id={conv_id}", 303)


@router.post("/chat/send_lead")
async def chat_send_lead(request: Request, conv_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    conv  = db.get_conversation(conv_id)
    staff = db.get_staff_by_conv(conv_id) if conv else None
    if not conv: return RedirectResponse("/chat", 303)
    if staff and staff.get("fb_event_sent"):
        return RedirectResponse(f"/chat?conv_id={conv_id}", 303)
    # Определяем пиксели — проект по utm_campaign или глобальные
    utm = db.get_utm_by_conv(conv_id)
    fbclid   = (utm.get("fbclid") if utm else None) or conv.get("fbclid")
    fbp      = (utm.get("fbp") if utm else None) or conv.get("fbp")
    campaign = (utm.get("utm_campaign") if utm else None) or conv.get("utm_campaign") or "telegram"
    utm_src  = (utm.get("utm_source") if utm else None) or conv.get("utm_source") or "telegram"
    px = _resolve_pixels(conv)
    if px["project_name"]:
        log.info(f"[Lead] проект: {px['project_name']} utm={campaign}")
    sent = await meta_capi.send_lead_event(
        px["fb_pixel"], px["fb_token"],
        user_id=conv.get("tg_chat_id", ""),
        campaign=campaign, fbclid=fbclid, fbp=fbp,
        utm_source=utm_src, utm_campaign=campaign,
        test_event_code=px["test_event_code"],
    )
    if sent and staff:
        db.set_staff_fb_event(staff["id"], "Lead")
    elif sent:
        db.set_conv_fb_event(conv_id, "Lead")
    # TikTok Lead
    if px["tt_pixel"] and px["tt_token"] and tiktok_capi:
        await tiktok_capi.send_lead_event(
            px["tt_pixel"], px["tt_token"],
            user_id=conv.get("tg_chat_id", ""),
            ip=request.client.host if request.client else None,
            utm_source=utm_src, utm_campaign=campaign,
            ttclid=conv.get("ttclid") or fbclid or None,
        )
    return RedirectResponse(f"/chat?conv_id={conv_id}", 303)

