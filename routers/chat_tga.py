"""
routers/chat_tga.py — Telegram Account чат роуты

Подключается в main.py:
    from routers.chat_tga import router as tga_router, setup as tga_setup
    tga_setup(db, log, bot_manager, meta_capi,
              TG_WH_SECRET, TG_SVC_URL, TG_SVC_SECRET,
              check_session, require_auth, base, nav_html, _render_conv_tags_picker)
    app.include_router(tga_router)
"""

import httpx
from datetime import datetime
from fastapi import APIRouter, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

router = APIRouter()

# ── Зависимости — инициализируются через setup() ──────────────────────────────
db             = None
log            = None
bot_manager    = None
meta_capi      = None
tiktok_capi    = None
TG_WH_SECRET   = ""
TG_SVC_URL     = ""
TG_SVC_SECRET  = ""
check_session            = None
require_auth             = None
base                     = None
nav_html                 = None
_render_conv_tags_picker = None


def setup(_db, _log, _bot_manager, _meta_capi,
          _tg_wh_secret, _tg_svc_url, _tg_svc_secret,
          _check_session, _require_auth, _base, _nav_html, _render_conv_tags_picker_fn,
          _tiktok_capi=None):
    global db, log, bot_manager, meta_capi, tiktok_capi
    global TG_WH_SECRET, TG_SVC_URL, TG_SVC_SECRET
    global check_session, require_auth, base, nav_html, _render_conv_tags_picker
    db             = _db
    log            = _log
    bot_manager    = _bot_manager
    meta_capi      = _meta_capi
    TG_WH_SECRET   = _tg_wh_secret
    TG_SVC_URL     = _tg_svc_url
    TG_SVC_SECRET  = _tg_svc_secret
    check_session  = _check_session
    require_auth   = _require_auth
    base           = _base
    nav_html       = _nav_html
    _render_conv_tags_picker = _render_conv_tags_picker_fn
    tiktok_capi    = _tiktok_capi


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
        "fb_pixel":           fb_pixel,
        "fb_token":           fb_token,
        "tt_pixel":           tt_pixel,
        "tt_token":           tt_token,
        "test_event_code":    (project.get("test_event_code") if project else None) or db.get_setting("test_event_code") or None,
        "tt_test_event_code": (project.get("tt_test_event_code") if project else None) or db.get_setting("tt_test_event_code") or None,
        "project_name":       proj_name,
    }



@router.get("/tg_account/chat", response_class=HTMLResponse)
async def tg_account_chat_page(request: Request, conv_id: int = 0, status_filter: str = "open"):
    user, err = require_auth(request)
    if err: return err

    convs = db.get_tg_account_conversations(status=status_filter if status_filter != "all" else None)

    tg_status   = db.get_setting("tg_account_status", "disconnected")
    tg_username = db.get_setting("tg_account_username", "")
    tg_phone    = db.get_setting("tg_account_phone", "")

    if tg_status == "connected":
        conn_badge = f'<div style="background:#052e16;border:1px solid #166534;border-radius:7px;padding:6px 12px;font-size:.8rem;color:#86efac;margin-bottom:8px">📱 Подключён · @{tg_username} · +{tg_phone}</div>'
    else:
        conn_badge = '<div style="background:#2d0a0a;border:1px solid #7f1d1d;border-radius:7px;padding:6px 12px;font-size:.8rem;color:#fca5a5;margin-bottom:8px">⚠️ TG аккаунт не подключён → <a href="/tg_account/setup" style="color:#fca5a5;text-decoration:underline">Подключить</a></div>'

    def tab(val, label):
        active = "background:var(--orange);color:#fff" if val == status_filter else "background:var(--bg3);color:var(--text3)"
        return f'<a href="/tg_account/chat?status_filter={val}" style="flex:1;text-align:center;padding:5px 0;border-radius:7px;font-size:.78rem;font-weight:600;text-decoration:none;{active}">{label}</a>'
    tabs_html = f'<div style="display:flex;gap:4px;margin-bottom:8px">{tab("open","Открытые")}{tab("closed","Закрытые")}{tab("all","Все")}</div>'

    # Панель фильтрации по тегам
    all_tags = db.get_all_tags()
    if all_tags:
        tag_btns = ''.join(
            f'<button onclick="filterByTag({tg["id"]},this)" '
            f'data-tag-id="{tg["id"]}" data-color="{tg["color"]}" '
            f'data-bg="{tg["color"]}22" data-border="{tg["color"]}55" '
            f'style="flex-shrink:0;padding:3px 10px;border-radius:20px;border:1px solid {tg["color"]}55;background:{tg["color"]}22;color:{tg["color"]};font-size:.72rem;font-weight:500;cursor:pointer;transition:all .15s;white-space:nowrap;opacity:.55">#{tg["name"]}</button>'
            for tg in all_tags
        )
        tag_filter_html = f'''<div id="tag-filter-bar" style="display:flex;gap:5px;overflow-x:auto;scrollbar-width:none;-webkit-overflow-scrolling:touch;padding:6px 12px 8px;border-bottom:1px solid var(--border);box-sizing:border-box">
            <button onclick="filterByTag(0,this)" id="tag-all-btn" style="flex-shrink:0;padding:3px 10px;border-radius:20px;border:1px solid var(--border);background:var(--orange);color:#fff;font-size:.72rem;font-weight:600;cursor:pointer;white-space:nowrap">Все</button>
            {tag_btns}
        </div>'''
    else:
        tag_filter_html = ''


    conv_items = ""
    tga_in_staff = db.get_tga_conv_ids_in_staff()
    tga_tags_map = db.get_all_conv_tags_map("tga")
    for c in convs:
        cls = "conv-item active" if c["id"] == conv_id else "conv-item"
        t = (c.get("last_message_at") or c["created_at"])[:16].replace("T", " ")
        ucount = f'<span class="unread-num unread-badge">{c["unread_count"]}</span>' if c.get("unread_count", 0) > 0 else ""
        dot = "🟢" if c["status"] == "open" else "⚫"
        is_fb = bool(c.get("fbclid") or (c.get("utm_source") or "") in ("facebook", "fb"))
        is_tt = bool((c.get("utm_source") or "") in ("tiktok", "tt"))
        if is_fb:
            src_badge = '<span class="source-badge source-fb">🔵 FB</span>'
        elif is_tt:
            src_badge = '<span class="source-badge" style="background:#1a1a2a;color:#69c9d0;border:1px solid #2a2a4a">🎵 TT</span>'
        else:
            src_badge = '<span class="source-badge source-organic">organic</span>'
        utm_line = ""  # UTM скрыты из списка — видны внутри чата
        tg_uname = c.get("username") or ""
        uname_str = ("@" + tg_uname) if tg_uname else str(c.get("tg_user_id", ""))
        # Задача 5: отметка "уже в базе"
        staff_info = tga_in_staff.get(c["id"])
        in_base_badge = f'<span style="background:#052e16;color:#86efac;border:1px solid #166534;border-radius:5px;font-size:.65rem;padding:1px 6px;margin-left:4px;white-space:nowrap">✅ в базе</span>' if staff_info else ""
        # Теги
        ctags = tga_tags_map.get(c["id"], [])
        tags_line = ""
        if ctags:
            tags_html = "".join(f'<span class="conv-tag" style="background:{tg["color"]}22;color:{tg["color"]};border-color:{tg["color"]}55">{tg["name"]}</span>' for tg in ctags)
            tags_line = f'<div class="tags-row">{tags_html}</div>'
        # Задача 6: порядок как в WA
        conv_items += (f'<a href="/tg_account/chat?conv_id={c["id"]}&status_filter={status_filter}">' + f'<div class="{cls}" data-conv-id="{c["id"]}" data-tags="{"|".join(str(tg["id"]) for tg in ctags)}">' + f'<div class="conv-name"><span>{dot} {c["visitor_name"]}</span>{ucount}{in_base_badge}</div>' + f'<div class="conv-preview">{(c.get("last_message") or "Нет сообщений")[:50]}</div>' + f'<div class="conv-time" style="display:flex;align-items:center;justify-content:space-between">📱 {uname_str} · {t[3:10].replace("-",".")} {t[-5:]} {src_badge}</div>' + utm_line + tags_line + '</div></a>')

    if not conv_items:
        conv_items = '<div style="padding:20px;text-align:center;color:var(--text3);font-size:.85rem">Нет диалогов</div>'

    chat_area = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text3);font-size:.9rem">Выберите диалог</div>'

    if conv_id:
        active_conv = db.get_tg_account_conversation(conv_id)
        if active_conv:
            db.mark_tg_account_conv_read(conv_id)
            msgs = db.get_tg_account_messages(conv_id)
            messages_html = ""
            for m in msgs:
                _dt = m["created_at"] or ""
                _date = _dt[:10].replace("-",".")[2:] if len(_dt) >= 10 else ""
                _time = _dt[11:16] if len(_dt) >= 16 else ""
                t = f"{_date} {_time}".strip()
                if m.get("media_url") and (m.get("media_type") or "").startswith("image/"):
                    ch = f'<img src="{m["media_url"]}" style="max-width:220px;border-radius:8px;display:block;cursor:pointer" onclick="window.open(this.src)" />'
                elif m.get("media_url"):
                    ch = f'<a href="{m["media_url"]}" target="_blank" style="color:#60a5fa">📎 Открыть файл</a>'
                else:
                    ch = (m["content"] or "").replace("<", "&lt;")
                sl = f'<div style="font-size:.68rem;color:var(--orange);margin-bottom:2px;text-align:right;opacity:.8">{m["sender_name"]}</div>' if m.get("sender_name") and m["sender_type"] == "manager" else ""
                messages_html += f'<div class="msg {m["sender_type"]}" data-id="{m["id"]}">{sl}<div class="msg-bubble">{ch}</div><div class="msg-time">{t}</div></div>'

            uname = f"@{active_conv['username']}" if active_conv.get("username") else active_conv.get("tg_user_id", "")
            # Задача 7: Карточка сотрудника для TG
            tga_staff = db.get_staff_by_tg_account_conv(conv_id)
            if tga_staff:
                tga_card_link = f'<a href="/staff?edit={tga_staff["id"]}" style="display:inline-flex;align-items:center;gap:4px;background:#052e16;color:#86efac;border:1px solid #166534;border-radius:6px;padding:2px 8px;font-size:.73rem;text-decoration:none">✅ В базе · {tga_staff.get("name","") or "Карточка"} →</a>'
            else:
                tga_card_link = f'<a href="/staff/create_from_tga?conv_id={conv_id}" style="display:inline-flex;align-items:center;gap:4px;background:var(--bg3);color:var(--text3);border:1px solid var(--border);border-radius:6px;padding:2px 8px;font-size:.73rem;text-decoration:none">+ Создать карточку</a>'
            # Теги чата
            all_tags     = db.get_all_tags()
            active_ctags = db.get_conv_tags("tga", conv_id)
            active_tag_ids = {tg["id"] for tg in active_ctags}
            tga_tags_html = _render_conv_tags_picker(active_ctags, all_tags, active_tag_ids, "tga", conv_id)
            fb_sent = active_conv.get("fb_event_sent")
            lead_btn = (
                '<span class="badge-green">✅ Lead отправлен (авто)</span>'
                if fb_sent else (
                    '<span style="color:var(--text3);font-size:.73rem;opacity:.7">⏳ Ждём первого сообщения...</span>'
                    if (active_conv.get("fbclid") or (active_conv.get("utm_source") or "").lower() in ("facebook","fb","tiktok","tt"))
                    else f'<form method="post" action="/tg_account/send_lead" style="display:inline"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn btn-sm" style="font-size:.73rem;background:#1e3a5f;border:1px solid #3b5998;color:#93c5fd">📤 Lead → FB</button></form>'
                )
            )
            status_color = "#34d399" if active_conv["status"] == "open" else "#ef4444"
            close_btn = f'<form method="post" action="/tg_account/close"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-gray btn-sm">✓ Закрыть</button></form>' if active_conv["status"] == "open" else \
                        f'<form method="post" action="/tg_account/reopen"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-orange btn-sm">↺ Открыть</button></form>'
            delete_btn = f'<button class="btn-gray btn-sm" style="color:#fff;background:#7f1d1d;border-color:#7f1d1d;font-size:.78rem;padding:5px 10px" onclick="deleteTgAccConv({conv_id})" title="Удалить диалог">🗑 Удалить</button>' if user and user.get("role") == "admin" else ""
            call_url = f"https://t.me/{active_conv['username']}" if active_conv.get("username") else f"tg://user?id={active_conv.get('tg_user_id','')}"
            tags = []
            _tga_src = (active_conv.get("utm_source") or "").lower()
            if active_conv.get("fbclid") or _tga_src in ("facebook","fb"):
                tags.append('<span class="utm-tag" style="background:#1e3a5f;color:#60a5fa">🔵 Facebook</span>')
            elif _tga_src in ("tiktok","tt"):
                tags.append('<span class="utm-tag" style="background:#1a1a2a;color:#69c9d0;border:1px solid #2a2a4a">🎵 TikTok</span>')
            if active_conv.get("utm_campaign"): tags.append(f'<span class="utm-tag">🎯 {active_conv["utm_campaign"][:25]}</span>')
            if active_conv.get("utm_content"): tags.append(f'<span class="utm-tag" style="background:#1a2a1a;color:#86efac">📌 {active_conv["utm_content"][:20]}</span>')
            if active_conv.get("utm_term"): tags.append(f'<span class="utm-tag" style="background:#1a1a2a;color:#a5b4fc">📂 {active_conv["utm_term"][:20]}</span>')
            if active_conv.get("fbclid"): tags.append('<span class="utm-tag badge-green">fbclid ✓</span>')
            utm_tags = '<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:6px">' + "".join(tags) + '</div>' if tags else ""
            _tga_photo = active_conv.get("photo_url") or ""
            if _tga_photo:
                _tga_avatar = (
                    '<div class="tga-avatar-wrap">'
                    + '<img src="' + _tga_photo + '" style="width:42px;height:42px;border-radius:50%;object-fit:cover;border:2px solid var(--orange)" />'
                    + '<div class="tga-avatar-zoom"><img src="' + _tga_photo + '" /></div>'
                    + '</div>')
            else:
                _tga_avatar = '<div class="avatar">T</div>'
                _tga_avatar = '<div class="avatar">T</div>'
            chat_area = f"""
            <div class="chat-header">
              <div style="display:flex;align-items:flex-start;gap:12px;flex:1">
                {_tga_avatar}
                <div style="flex:1">
                  <div style="font-weight:700;color:var(--text)">{active_conv['visitor_name']} <span style="color:{status_color};font-size:.72rem">●</span></div>
                  <div style="font-size:.78rem;color:var(--text3)">{uname} · {tga_card_link}</div>
                  <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:6px;align-items:center">
                    {lead_btn}
                    <a href="{call_url}" target="_blank" class="btn-gray btn-sm" style="display:inline-flex;align-items:center;gap:4px;padding:5px 10px;border-radius:7px;font-size:.74rem;border:1px solid var(--border);text-decoration:none">📞 Открыть в TG</a>
                  </div>
                  {utm_tags}
                  {tga_tags_html}
                </div>
              </div>
              <div style="display:flex;gap:6px;flex-shrink:0">{close_btn} {delete_btn}</div>
            </div>
            <div class="chat-messages" id="tga-msgs">{messages_html}</div>
            <div id="tga-send-error" style="display:none;padding:8px 18px;background:#2d0a0a;border-top:1px solid #7f1d1d;font-size:.8rem;color:#fca5a5;align-items:center;justify-content:space-between;gap:8px">
              <span id="tga-send-error-text"></span>
              <button onclick="document.getElementById('tga-send-error').style.display='none'" style="background:none;border:none;color:#fca5a5;cursor:pointer;font-size:1rem;line-height:1">✕</button>
            </div>
            <div class="chat-input" id="tga-chat-input">
              <div id="tga-disconnected-banner" style="display:{'none' if tg_status == 'connected' else 'flex'};align-items:center;justify-content:space-between;padding:8px 12px;background:#1c1a00;border:1px solid #713f12;border-radius:8px;margin-bottom:8px;font-size:.8rem;color:#fde047;gap:8px">
                <span>⚠️ TG аккаунт не подключён — сообщения не будут доставлены</span>
                <a href="/tg_account/setup" style="color:#fde047;font-weight:600;white-space:nowrap;text-decoration:underline">Подключить →</a>
              </div>
              <div class="chat-input-row">
                <div style="position:relative;flex:1">
                  <textarea id="tga-inp" placeholder="Написать в Telegram... (Enter — отправить)"
                    style="width:100%;resize:none;background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:10px 44px 10px 14px;color:var(--text);font-size:.9rem;font-family:inherit;min-height:44px;max-height:120px"
                    rows="1" onkeydown="if(event.key==='Enter'&&!event.shiftKey){{event.preventDefault();sendTgAccMsg()}}"></textarea>
                  <label style="position:absolute;right:10px;bottom:10px;cursor:pointer;opacity:.6">
                    📎<input type="file" id="tga-file" style="display:none" onchange="sendTgAccFile(this)"/>
                  </label>
                </div>
                <button class="btn-orange" onclick="sendTgAccMsg()" style="height:44px;padding:0 18px;flex-shrink:0">Отправить</button>
              </div>
            </div>
            <script>
            var TGA_CONV_ID={conv_id};
            var TGA_SF='{status_filter}';
            var tgaMsgBox=document.getElementById('tga-msgs');
            if(tgaMsgBox) tgaMsgBox.scrollTop=tgaMsgBox.scrollHeight;
            var lastTgAId=(function(){{var m=document.querySelectorAll('#tga-msgs .msg[data-id]');return m.length?m[m.length-1].dataset.id:0;}})();
            function escTga(t){{return(t||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}}

    var _activeTagFilter=0;
    function filterByTag(tagId,btn){{
      _activeTagFilter=tagId;
      var bar=document.getElementById('tag-filter-bar');
      if(!bar)return;
      bar.querySelectorAll('button').forEach(function(b){{
        var isActive=(tagId===0&&b.id==='tag-all-btn')||(String(tagId)===String(b.dataset.tagId));
        if(isActive){{
          b.style.opacity='1';
          b.style.fontWeight='700';
          if(b.id==='tag-all-btn'){{b.style.background='var(--orange)';b.style.color='#fff';}}
          else{{b.style.background=b.getAttribute('data-color');b.style.color='#fff';b.style.borderColor=b.getAttribute('data-color');}}
        }}else{{
          b.style.opacity='0.55';b.style.fontWeight='500';
          if(b.id==='tag-all-btn'){{b.style.background='';b.style.color='var(--text3)';}}
          else{{b.style.background=b.getAttribute('data-bg');b.style.color=b.getAttribute('data-color');b.style.borderColor=b.getAttribute('data-border');}}
        }}
      }});
      document.querySelectorAll('#conv-list .conv-item').forEach(function(el){{
        var wrap=el.closest('a')||el.parentElement;
        if(tagId===0){{wrap.style.display='';return;}}
        var tags=(el.dataset.tags||'').split('|').filter(Boolean);
        wrap.style.display=tags.indexOf(String(tagId))>=0?'':'none';
      }});
    }}
            function showTgaError(msg){{
              var errDiv=document.getElementById('tga-send-error');
              var errTxt=document.getElementById('tga-send-error-text');
              if(!errDiv||!errTxt) return;
              var isDisconn = msg&&(msg.toLowerCase().includes('not connected')||msg.toLowerCase().includes('503')||msg.toLowerCase().includes('disconnect'));
              if(isDisconn){{
                errTxt.innerHTML='⚠️ TG аккаунт не подключён. <a href="/tg_account/setup" style="color:#fca5a5;text-decoration:underline;font-weight:600">Подключить новый аккаунт →</a>';
                var banner=document.getElementById('tga-disconnected-banner');
                if(banner) banner.style.display='flex';
              }} else {{
                errTxt.textContent='Ошибка отправки: '+(msg||'неизвестная ошибка');
              }}
              errDiv.style.display='flex';
              setTimeout(function(){{errDiv.style.display='none';}}, 6000);
            }}
            async function sendTgAccMsg(){{
              var inp=document.getElementById('tga-inp');
              var text=inp.value.trim();if(!text)return;inp.value='';
              try{{
                var r=await fetch('/tg_account/send',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:'conv_id='+TGA_CONV_ID+'&text='+encodeURIComponent(text)}});
                var d=await r.json();if(!d.ok)showTgaError(d.error||'');else loadNewTgAccMsgs();
              }}catch(e){{showTgaError(e.message);}}
            }}
            async function sendTgAccFile(input){{
              if(!input.files[0])return;
              var fd=new FormData();fd.append('conv_id',TGA_CONV_ID);fd.append('file',input.files[0]);
              try{{
                var r=await fetch('/tg_account/send_media',{{method:'POST',body:fd}});
                var d=await r.json();if(!d.ok)showTgaError(d.error||'');else loadNewTgAccMsgs();
              }}catch(e){{showTgaError(e.message);}}
              input.value='';
            }}
            var _tgaLoadingMsgs=false;
            async function loadNewTgAccMsgs(){{
              if(_tgaLoadingMsgs)return;
              _tgaLoadingMsgs=true;
              try{{
                var res=await fetch('/api/tg_account_messages/'+TGA_CONV_ID+'?after='+lastTgAId);
                if(!res.ok){{_tgaLoadingMsgs=false;return;}}var data=await res.json();
                if(!data.messages||!data.messages.length){{_tgaLoadingMsgs=false;return;}}
                data.messages.forEach(function(m){{
                  if(tgaMsgBox.querySelector('[data-id="'+m.id+'"]'))return;
                  var d=document.createElement('div');d.className='msg '+m.sender_type;d.dataset.id=m.id;
                  var inner=m.media_url&&m.media_type&&m.media_type.startsWith('image/')
                    ?'<img src="'+m.media_url+'" style="max-width:220px;border-radius:8px;display:block;cursor:pointer" onclick="window.open(this.src)"/>'
                    :m.media_url?'<a href="'+m.media_url+'" target="_blank" style="color:#60a5fa">Открыть файл</a>':escTga(m.content||'');
                  var sl=m.sender_name&&m.sender_type==='manager'?'<div style="font-size:.68rem;color:var(--orange);margin-bottom:2px;text-align:right;opacity:.8">'+escTga(m.sender_name)+'</div>':'';
                  d.innerHTML=sl+'<div class="msg-bubble">'+inner+'</div><div class="msg-time">'+m.created_at.substring(11,16)+'</div>';
                  tgaMsgBox.appendChild(d);lastTgAId=m.id;
                }});
                tgaMsgBox.scrollTop=tgaMsgBox.scrollHeight;
              }}catch(e){{}}finally{{_tgaLoadingMsgs=false;}}
            }}
            async function deleteTgAccConv(id){{
              var btn=document.querySelector('[onclick*="deleteTgAccConv"]');
              if(btn){{btn.textContent='...';btn.disabled=true;}}
              try{{
                var r=await fetch('/tg_account/delete',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:'conv_id='+id}});
                var d=await r.json();
                if(d.ok) window.location.href='/tg_account/chat?status_filter='+TGA_SF;
                else{{alert('Ошибка: '+(d.error||r.status));if(btn){{btn.textContent='Удалить';btn.disabled=false;}}}}
              }}catch(e){{showTgaError(e.message);if(btn){{btn.textContent='Удалить';btn.disabled=false;}}}}
            }}
            setInterval(loadNewTgAccMsgs,3000);
            // При возврате на вкладку — сразу опрашиваем, не ждём следующего интервала
            document.addEventListener('visibilitychange', function(){{
              if(document.visibilityState === 'visible') loadNewTgAccMsgs();
            }});
            // Polling статуса TG — обновляем баннер при подключении/отключении
            setInterval(async function(){{
              try{{
                var r=await fetch('/api/stats');
                if(!r.ok)return;
                var d=await r.json();
                var banner=document.getElementById('tga-disconnected-banner');
                if(!banner)return;
                banner.style.display=(d.tg_status==='connected')?'none':'flex';
              }}catch(e){{}}
            }},5000);
            // ── SPA навигация по чатам ──────────────────────────────────────
            var _tgaChatLoading = false;
            async function loadTgaChat(convId, sfParam) {{
              if(_tgaChatLoading) return;
              _tgaChatLoading = true;
              var chatWin = document.querySelector('.chat-window') || document.getElementById('tg-chat-area');
              if(chatWin) chatWin.style.opacity = '0.5';
              try {{
                var url = '/api/tga_chat_panel?conv_id=' + convId + '&status_filter=' + (sfParam||'open');
                var r = await fetch(url);
                if(!r.ok) throw new Error(r.status);
                var html = await r.text();
                if(chatWin) {{ chatWin.innerHTML = html; chatWin.style.opacity = '1'; }}
                // Выполняем <script> теги (браузер не запускает их через innerHTML)
                if(chatWin) {{
                  chatWin.querySelectorAll('script').forEach(function(oldScript) {{
                    var newScript = document.createElement('script');
                    newScript.textContent = oldScript.textContent;
                    document.body.appendChild(newScript);
                    document.body.removeChild(newScript);
                  }});
                }}
                // Обновляем активный элемент в списке
                document.querySelectorAll('#tg-conv-items .conv-item').forEach(function(el){{
                  var isActive = el.dataset.convId == String(convId);
                  el.classList.toggle('active', isActive);
                  if(isActive) {{
                    var badge = el.querySelector('.unread-num');
                    if(badge) badge.remove();
                  }}
                }});
                // Обновляем URL без перезагрузки
                history.pushState(null, '', '/tg_account/chat?conv_id=' + convId + '&status_filter=' + (sfParam||'open'));
                // Обновляем глобальные переменные для polling
                if(typeof TGA_CONV_ID !== 'undefined') window.TGA_CONV_ID = convId;
                ACTIVE_TGA_CONV_ID = convId;
                // Перезагружаем скрипты в панели для нового чата
                if(typeof loadTgaScripts === 'function') loadTgaScripts(_tgaScriptsProjectId);
              }} catch(e) {{ if(chatWin) chatWin.style.opacity = '1'; }}
              _tgaChatLoading = false;
            }}
            // Перехватываем клики по чатам в списке
            document.getElementById('tg-conv-items').addEventListener('click', function(e) {{
              var link = e.target.closest('a[href*="/tg_account/chat?conv_id="]');
              if(!link) return;
              e.preventDefault();
              var url = new URL(link.href);
              var cid = parseInt(url.searchParams.get('conv_id'));
              var sf  = url.searchParams.get('status_filter') || 'open';
              if(cid) loadTgaChat(cid, sf);
            }});
            // ── Кэш всех диалогов для фронтенд поиска ──────────────────


            function renderTgConvList(list, convs){{
              if(!list)return;
              list.innerHTML=convs.map(function(c){{
                var active=c.id===ACTIVE_TGA_CONV_ID?' active':'';
                var dot=c.status==='open'?'🟢':'⚫';
                var bdg=c.unread_count>0?'<span class="unread-num unread-badge">'+c.unread_count+'</span>':'';
                var inBase=c.in_staff?'<span style="background:#052e16;color:#86efac;border:1px solid #166534;border-radius:5px;font-size:.65rem;padding:1px 6px;margin-left:4px;white-space:nowrap">✅ в базе</span>':'';
                var isFb=!!(c.fbclid||(c.utm_source&&(c.utm_source==='facebook'||c.utm_source==='fb')));
                var isTt=!!(c.utm_source&&(c.utm_source==='tiktok'||c.utm_source==='tt'));var src=isFb?'<span class="source-badge source-fb">🔵 FB</span>':isTt?'<span class="source-badge" style="background:#1a1a2a;color:#69c9d0;border:1px solid #2a2a4a">🎵 TT</span>':'<span class="source-badge source-organic">organic</span>';
                var uname=c.username?'@'+escTga(c.username):'';
                var utm='';
                if(isFb){{
                  if(c.utm_campaign)utm+='<span class="utm-tag" title="Кампания">🎯 '+escTga(c.utm_campaign.substring(0,25))+'</span>';
                  if(c.utm_content)utm+='<span class="utm-tag" style="background:#1a2a1a;color:#86efac" title="Объявление">📌 '+escTga(c.utm_content.substring(0,20))+'</span>';
                  if(c.utm_term)utm+='<span class="utm-tag" style="background:#1a1a2a;color:#a5b4fc" title="Адсет">📂 '+escTga(c.utm_term.substring(0,20))+'</span>';
                }}
                var utmLine=utm?'<div class="conv-meta" style="display:flex;flex-wrap:wrap;gap:3px;margin-top:2px">'+utm+'</div>':'';
                return '<a href="/tg_account/chat?conv_id='+c.id+'"><div class="conv-item'+active+'" data-conv-id="'+c.id+'">'
                  +'<div class="conv-name"><span>'+dot+' '+escTga(c.visitor_name)+'</span>'+bdg+inBase+'</div>'
                  +'<div class="conv-preview">'+escTga((c.last_message||'Нет сообщений').substring(0,50))+'</div>'
                  +'<div class="conv-time" style="display:flex;align-items:center;justify-content:space-between">📱 '+uname+' · '+(c.last_message_at?c.last_message_at.substring(5,10).replace(/-/g,'.')+' ':'')+( c.last_message_at||'').substring(11,16)+' '+src+'</div>'
                  +'</div></a>';
              }}).join('')||'<div style="padding:20px;text-align:center;color:var(--text3)">Нет диалогов</div>';
            }}


            // ── Infinite scroll ──────────────────────────────────────
            var _tgaOffset = {len(convs)};
            var _tgaLoading = false;
            var _tgaHasMore = {str(len(convs) == 30).lower()};

            function _tgaLoadMore() {{
              if(_tgaLoading || !_tgaHasMore) return;
              _tgaLoading = true;
              fetch('/api/tg_account_convs?status='+encodeURIComponent(TGA_SF)+'&offset='+_tgaOffset)
                .then(r=>r.json())
                .then(function(d){{
                  if(!d.convs||!d.convs.length){{ _tgaHasMore=false; _tgaLoading=false; return; }}
                  var list=document.getElementById('tg-conv-items');
                  var sentinel=document.getElementById('tga-scroll-sentinel');
                  var isFb=function(c){{return !!(c.fbclid||(c.utm_source&&(c.utm_source==='facebook'||c.utm_source==='fb')));}}
                  d.convs.forEach(function(c){{
                    if(list.querySelector('[data-conv-id="'+c.id+'"]'))return;
                    var dot=c.status==='open'?'🟢':'⚫';
                    var bdg=c.unread_count>0?'<span class="unread-num unread-badge">'+c.unread_count+'</span>':'';
                    var uname=c.username?'@'+escTga(c.username):'';
                    var src=isFb(c)?'<span class="source-badge source-fb">🔵 FB</span>':'<span class="source-badge source-organic">organic</span>';
                    var utm='';
                    if(isFb(c)){{
                      if(c.utm_campaign)utm+='<span class="utm-tag">🎯 '+escTga(c.utm_campaign.substring(0,25))+'</span>';
                      if(c.utm_content)utm+='<span class="utm-tag" style="background:#1a2a1a;color:#86efac">📌 '+escTga(c.utm_content.substring(0,20))+'</span>';
                    }}
                    var el=document.createElement('a');
                    el.href='/tg_account/chat?conv_id='+c.id+'&status_filter='+encodeURIComponent(TGA_SF);
                    el.innerHTML='<div class="conv-item" data-conv-id="'+c.id+'">'
                      +'<div class="conv-name"><span>'+dot+' '+escTga(c.visitor_name)+'</span>'+bdg+'</div>'
                      +'<div class="conv-preview">'+escTga((c.last_message||'Нет сообщений').substring(0,50))+'</div>'
                      +'<div class="conv-time" style="display:flex;align-items:center;justify-content:space-between">📱 '+uname+' · '+(c.last_message_at?c.last_message_at.substring(5,10).replace(/-/g,'.')+' ':'')+c.last_message_at.substring(11,16)+' '+src+'</div>'
                      +(utm?'<div class="conv-meta">'+utm+'</div>':'')
                      +'</div>';
                    list.insertBefore(el, sentinel);
                  }});
                  _tgaOffset += d.convs.length;
                  _tgaHasMore = d.has_more;
                  _tgaLoading = false;
                }})
                .catch(function(){{ _tgaLoading=false; }});
            }}

            // IntersectionObserver — грузим когда дошли до конца списка
            (function(){{
              var sentinel=document.getElementById('tga-scroll-sentinel');
              if(!sentinel||!window.IntersectionObserver)return;
              var obs=new IntersectionObserver(function(entries){{
                if(entries[0].isIntersecting)_tgaLoadMore();
              }},{{threshold:0.1}});
              obs.observe(sentinel);
            }})();

            var ACTIVE_TGA_CONV_ID={conv_id};
            var _knownTgIds=new Set([{','.join(str(c['id']) for c in convs)}]);
            setInterval(async function(){{
              try{{
                var res=await fetch('/api/tg_account_convs?status='+encodeURIComponent(TGA_SF));
                var data=await res.json();
                if(!data.convs)return;
                var list=document.getElementById('tg-conv-items');
                if(!list)return;
                var newIds=new Set(data.convs.map(function(c){{return c.id;}}));
                var hasNew=[...newIds].some(function(id){{return!_knownTgIds.has(id);}});
                data.convs.forEach(function(c){{
                  var item=list.querySelector('[data-conv-id="'+c.id+'"]');
                  if(item){{
                    var badge=item.querySelector('.unread-badge');
                    if(c.unread_count>0){{
                      if(badge)badge.textContent=c.unread_count;
                      else{{var b=document.createElement('span');b.className='unread-num unread-badge';b.textContent=c.unread_count;var nm=item.querySelector('.conv-name');if(nm)nm.appendChild(b);}}
                    }}else if(badge)badge.remove();
                    var prev=item.querySelector('.conv-preview');
                    if(prev)prev.textContent=c.last_message||'Нет сообщений';
                  }}
                }});
                // Не перерисовываем список если идёт поиск
                var _searchInput=document.querySelector('#tg-conv-items')?.closest('.conv-list-wrap')?.querySelector('input[oninput]');
                var _isSearching=_searchInput&&_searchInput.value.trim()!=='';
                if(hasNew && !_isSearching){{
                  _knownTgIds=newIds;
                  list.innerHTML=data.convs.map(function(c){{
                    var active=c.id===ACTIVE_TGA_CONV_ID?' active':'';
                    var dot=c.status==='open'?'🟢':'⚫';
                    var bdg=c.unread_count>0?'<span class="unread-num unread-badge">'+c.unread_count+'</span>':'';
                    var inBase=c.in_staff?'<span style="background:#052e16;color:#86efac;border:1px solid #166534;border-radius:5px;font-size:.65rem;padding:1px 6px;margin-left:4px;white-space:nowrap">✅ в базе</span>':'';
                    var isFb=!!(c.fbclid||(c.utm_source&&(c.utm_source==='facebook'||c.utm_source==='fb')));
                    var isTt=!!(c.utm_source&&(c.utm_source==='tiktok'||c.utm_source==='tt'));var src=isFb?'<span class="source-badge source-fb">🔵 FB</span>':isTt?'<span class="source-badge" style="background:#1a1a2a;color:#69c9d0;border:1px solid #2a2a4a">🎵 TT</span>':'<span class="source-badge source-organic">organic</span>';
                    var uname=c.username?'@'+escTga(c.username):'';
                    var utm='';
                    if(isFb){{
                      if(c.utm_campaign)utm+='<span class="utm-tag" title="Кампания">🎯 '+escTga(c.utm_campaign.substring(0,25))+'</span>';
                      if(c.utm_content)utm+='<span class="utm-tag" style="background:#1a2a1a;color:#86efac" title="Объявление">📌 '+escTga(c.utm_content.substring(0,20))+'</span>';
                      if(c.utm_term)utm+='<span class="utm-tag" style="background:#1a1a2a;color:#a5b4fc" title="Адсет">📂 '+escTga(c.utm_term.substring(0,20))+'</span>';
                    }}
                    var utmLine=utm?'<div class="conv-meta" style="display:flex;flex-wrap:wrap;gap:3px;margin-top:2px">'+utm+'</div>':'';
                    return '<a href="/tg_account/chat?conv_id='+c.id+'"><div class="conv-item'+active+'" data-conv-id="'+c.id+'">'
                      +'<div class="conv-name"><span>'+dot+' '+escTga(c.visitor_name)+'</span>'+bdg+inBase+'</div>'
                      +'<div class="conv-preview">'+escTga((c.last_message||'Нет сообщений').substring(0,50))+'</div>'
                      +'<div class="conv-time" style="display:flex;align-items:center;justify-content:space-between">📱 '+uname+' · '+(c.last_message_at?c.last_message_at.substring(5,10).replace(/-/g,'.')+' ':'')+c.last_message_at.substring(11,16)+' '+src+'</div>'
                      +'</div></a>';
                  }}).join('')||'<div style="padding:20px;text-align:center;color:var(--text3)">Нет диалогов</div>';
                  if(ACTIVE_TGA_CONV_ID===0&&data.convs.length>0){{
                    window.location.href='/tg_account/chat?conv_id='+data.convs[0].id;
                  }}
                }}
              }}catch(e){{}}
            }},4000);

            // Автозапуск — на случай если поле не пустое после перезагрузки
            (function(){{
              var inp=document.getElementById('tga-search-input');
              if(inp&&inp.value.trim())filterTgConvs(inp.value);
            }})();
                        </script>"""

    _tga_tag_wrap = tag_filter_html  # без wrapper - стили прямо на tag-filter-bar
    content_html = f"""<div class="chat-layout" style="grid-template-columns:300px 1fr 260px">
      <div class="conv-list" id="conv-list">
        <div class="conv-search">{conn_badge}{tabs_html}<input type="text" id="tga-search-input" placeholder="🔍 Поиск..." oninput="filterTgConvs(this.value)" style="width:100%;margin-top:6px"/></div>
        {_tga_tag_wrap}
        <div id="tg-conv-items" style="overflow-y:auto;flex:1">{conv_items}<div id="tga-scroll-sentinel" style="height:1px"></div></div>
      </div>
      <div class="chat-window">{chat_area}</div>
      <div id="tga-scripts-panel" style="background:var(--bg2);border-left:1px solid var(--border);display:flex;flex-direction:column;height:100vh;overflow:hidden">
        <div style="padding:10px 12px 8px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;flex-shrink:0">
          <span style="font-weight:700;font-size:.85rem;color:var(--text)">📝 Скрипты</span>
          <button onclick="toggleTgaScriptsPanel()" style="background:none;border:none;color:var(--text3);cursor:pointer;font-size:1rem;padding:2px 4px" title="Свернуть">✕</button>
        </div>
        <div style="padding:8px 10px;border-bottom:1px solid var(--border);flex-shrink:0">
          <input type="text" id="tga-script-search" placeholder="🔍 Поиск скрипта..." oninput="filterTgaScripts(this.value)"
            style="width:100%;background:var(--bg3);border:1px solid var(--border);border-radius:7px;padding:6px 10px;color:var(--text);font-size:.8rem;box-sizing:border-box"/>
        </div>
        <div id="tga-scripts-list" style="overflow-y:auto;flex:1;padding:8px 6px">
          <div style="color:var(--text3);font-size:.8rem;text-align:center;padding:20px">Загрузка...</div>
        </div>
        <div style="padding:8px 10px;border-top:1px solid var(--border);flex-shrink:0">
          <a href="/scripts" target="_blank" style="font-size:.75rem;color:var(--text3);text-decoration:none;display:block;text-align:center">⚙️ Управление скриптами</a>
        </div>
      </div>
      <button id="tga-scripts-toggle-btn" onclick="toggleTgaScriptsPanel()"
        style="position:fixed;right:0;top:50%;transform:translateY(-50%);background:var(--bg2);border:1px solid var(--border);border-right:none;border-radius:8px 0 0 8px;padding:12px 6px;cursor:pointer;color:var(--text3);font-size:.8rem;writing-mode:vertical-rl;display:none;z-index:10">
        📝 Скрипты
      </button>
    </div>"""
    # Загружаем все проекты и скрипты для боковой панели
    _all_projects = db.get_projects()
    _all_scripts_data = []
    for _p in _all_projects:
        _scripts = db.get_scripts(_p["id"])
        if _scripts:
            _all_scripts_data.append({"project": _p["name"], "scripts": _scripts})
    import json as _json
    _scripts_json = _json.dumps(_all_scripts_data, ensure_ascii=False)

    _tga_scripts_js = ("""
    <style>.script-item:hover{background:var(--bg)!important;}</style>
    <script>
    function filterTgConvs(q){
      var list=document.getElementById('tg-conv-items');
      if(!list)return;
      var qLow=(q||'').trim().toLowerCase().replace(/^@/,'');
      list.querySelectorAll('a').forEach(function(a){
        a.style.display=qLow===''||a.textContent.toLowerCase().includes(qLow)?'':'none';
      });
    }
    var _tgaScriptsPanelOpen = true;
    var _tgaAllScripts = TGA_SCRIPTS_JSON_PLACEHOLDER;
    function toggleTgaScriptsPanel() {
      var panel=document.getElementById('tga-scripts-panel');
      var btn=document.getElementById('tga-scripts-toggle-btn');
      var layout=document.querySelector('.chat-layout');
      _tgaScriptsPanelOpen=!_tgaScriptsPanelOpen;
      if(_tgaScriptsPanelOpen){panel.style.display='flex';btn.style.display='none';if(layout)layout.style.gridTemplateColumns='300px 1fr 260px';}
      else{panel.style.display='none';btn.style.display='block';if(layout)layout.style.gridTemplateColumns='300px 1fr 0';}
    }
    function injectTgaScript(el) {
      var body=el.getAttribute('data-body-full');
      if(!body)return;
      var inp=document.getElementById('tga-inp');
      if(!inp)return;
      inp.value=body; inp.focus(); inp.dispatchEvent(new Event('input'));
    }
    function renderTgaScripts(data) {
      var box=document.getElementById('tga-scripts-list');
      if(!box)return;
      if(!data||!data.length){
        box.innerHTML='<div style="padding:20px;text-align:center;color:var(--text3);font-size:.8rem">\u041d\u0435\u0442 \u0441\u043a\u0440\u0438\u043f\u0442\u043e\u0432.<br><a href="/scripts" target="_blank" style="color:var(--orange)">\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c</a></div>';
        return;
      }
      var html='';
      data.forEach(function(proj){
        // Заголовок проекта
        html+='<div style="margin-bottom:14px">'
          +'<div style="font-size:.72rem;font-weight:700;color:var(--orange);padding:6px 8px 4px;border-bottom:1px solid var(--border);margin-bottom:4px">\u25B8 '+proj.project+'</div>';
        // Группируем по категориям
        var cats={};
        proj.scripts.forEach(function(s){(cats[s.category]=cats[s.category]||[]).push(s);});
        Object.keys(cats).sort().forEach(function(cat){
          html+='<div style="margin-bottom:6px">'
            +'<div style="font-size:.65rem;font-weight:600;color:var(--text3);text-transform:uppercase;letter-spacing:.05em;padding:2px 8px">'+cat+'</div>';
          cats[cat].forEach(function(s){
            var st=(s.title||'').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
            var sp=(s.body||'').substring(0,55).replace(/</g,'&lt;').replace(/>/g,'&gt;');
            var sb=(s.body||'').replace(/"/g,'&quot;');
            html+='<div class="script-item tga-script-item"'
              +' data-title="'+(s.title||'').toLowerCase().replace(/"/g,'&quot;')+'"'
              +' data-body-full="'+sb+'"'
              +' onclick="injectTgaScript(this)"'
              +' style="cursor:pointer;padding:7px 10px;border-radius:7px;margin:2px 4px;border:1px solid var(--border);background:var(--bg3)">'
              +'<div style="font-size:.79rem;font-weight:600;color:var(--text);margin-bottom:1px">'+st+'</div>'
              +'<div style="font-size:.71rem;color:var(--text3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'+sp+(s.body&&s.body.length>55?'\u2026':'')+'</div>'
              +'</div>';
          });
          html+='</div>';
        });
        html+='</div>';
      });
      box.innerHTML=html;
    }
    function filterTgaScripts(q){
      var items=document.querySelectorAll('#tga-scripts-list .tga-script-item');
      var qLow=(q||'').toLowerCase();
      items.forEach(function(el){
        var match=!qLow||(el.dataset.title||'').includes(qLow)||(el.getAttribute('data-body-full')||'').toLowerCase().includes(qLow);
        el.style.display=match?'':'none';
      });
      document.querySelectorAll('#tga-scripts-list > div').forEach(function(c){
        c.style.display=Array.from(c.querySelectorAll('.tga-script-item')).some(function(i){return i.style.display!=='none';})?'':'none';
      });
    }
    document.addEventListener("DOMContentLoaded", function(){ renderTgaScripts(_tgaAllScripts); });
    </script>""").replace("TGA_SCRIPTS_JSON_PLACEHOLDER", _scripts_json)
    tga_search_script = _tga_scripts_js
    return HTMLResponse(base(tga_search_script + content_html, "tg_account_chat", request))


@router.get("/tg_account/setup", response_class=HTMLResponse)
async def tg_account_setup(request: Request, msg: str = ""):
    user, err = require_auth(request, role="admin")
    if err: return err
    tg_status   = db.get_setting("tg_account_status", "disconnected")
    tg_username = db.get_setting("tg_account_username", "")
    tg_phone    = db.get_setting("tg_account_phone", "")
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""

    if tg_status == "connected":
        body_html = f"""
          <div style="background:#052e16;border:1px solid #166534;border-radius:12px;padding:16px;margin-bottom:20px">
            <div style="font-weight:700;color:#86efac;margin-bottom:4px">✅ Telegram аккаунт подключён</div>
            <div style="font-size:.85rem;color:#6ee7b7">@{tg_username} · +{tg_phone}</div>
          </div>
          <form method="post" action="/tg_account/disconnect">
            <button class="btn-gray" style="color:var(--red);border-color:#7f1d1d">🔌 Отключить аккаунт</button>
          </form>"""
    else:
        svc = await tg_api("get", "/status")
        svc_state = svc.get("status", "disconnected") if not svc.get("error") else "disconnected"
        # Состояние из БД имеет приоритет для awaiting_code / awaiting_2fa
        # TG сервис может вернуть "disconnected" даже когда код уже отправлен
        if tg_status in ("awaiting_code", "awaiting_2fa"):
            svc_state = tg_status
        if svc_state == "awaiting_code":
            body_html = """<div style="background:#1c1a00;border:1px solid #713f12;border-radius:12px;padding:16px;margin-bottom:20px">
                <div style="font-weight:700;color:#fde047">📱 Введите код из SMS</div></div>
              <form method="post" action="/tg_account/sign_in" style="display:flex;flex-direction:column;gap:12px;max-width:360px">
                <div class="field-group"><div class="field-label">Код из SMS / Telegram</div>
                  <input type="text" name="code" placeholder="12345" autofocus required style="letter-spacing:.2em;font-size:1.1rem"/></div>
                <button class="btn">✅ Войти</button></form>"""
        elif svc_state == "awaiting_2fa":
            body_html = """<div style="background:#1c1a00;border:1px solid #713f12;border-radius:12px;padding:16px;margin-bottom:20px">
                <div style="font-weight:700;color:#fde047">🔐 Требуется пароль 2FA</div></div>
              <form method="post" action="/tg_account/sign_in_2fa" style="display:flex;flex-direction:column;gap:12px;max-width:360px">
                <div class="field-group"><div class="field-label">Пароль 2FA</div>
                  <input type="password" name="password" autofocus required/></div>
                <button class="btn">🔓 Подтвердить</button></form>"""
        else:
            # Читаем сохранённые api_id/api_hash из БД
            saved_api_id   = db.get_setting("tg_api_id", "")
            saved_api_hash = db.get_setting("tg_api_hash", "")
            has_creds = bool(saved_api_id and saved_api_hash)
            _api_id_short = saved_api_id[:4] if saved_api_id else ""
            creds_badge = (
                f'<div style="background:#052e16;border:1px solid #166534;border-radius:8px;padding:8px 12px;font-size:.8rem;color:#86efac;margin-bottom:12px">'
                f'✅ API credentials сохранены (App ID: {_api_id_short}...)</div>'
                if has_creds else
                '<div style="background:#1c1a00;border:1px solid #713f12;border-radius:8px;padding:8px 12px;font-size:.8rem;color:#fde047;margin-bottom:12px">'
                '⚠️ Введите API credentials с my.telegram.org</div>'
            )
            body_html = f"""<div style="background:#2d0a0a;border:1px solid #7f1d1d;border-radius:12px;padding:16px;margin-bottom:20px">
                <div style="font-weight:700;color:#fca5a5">⚠️ Не подключён</div></div>
              {creds_badge}
              <form method="post" action="/tg_account/send_code" style="display:flex;flex-direction:column;gap:14px;max-width:400px">
                <div style="background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:14px">
                  <div style="font-size:.78rem;font-weight:700;color:var(--orange);text-transform:uppercase;margin-bottom:10px">🔑 API Credentials (my.telegram.org)</div>
                  <div class="grid-2" style="gap:10px">
                    <div class="field-group">
                      <div class="field-label">App api_id</div>
                      <input type="text" name="api_id" value="{saved_api_id}" placeholder="12345678" required/>
                    </div>
                    <div class="field-group">
                      <div class="field-label">App api_hash</div>
                      <input type="text" name="api_hash" value="{saved_api_hash}" placeholder="abc123def456..."/>
                    </div>
                  </div>
                  <div style="font-size:.72rem;color:var(--text3);margin-top:8px">
                    Получи на <a href="https://my.telegram.org" target="_blank" style="color:var(--orange)">my.telegram.org</a> → API development tools
                  </div>
                </div>
                <div class="field-group">
                  <div class="field-label">Номер телефона (с кодом страны)</div>
                  <input type="text" name="phone" placeholder="+79001234567" required/>
                </div>
                <button class="btn">📱 Отправить код</button>
              </form>"""

    content_html = f"""<div class="page-wrap">
      <div class="page-title">📱 TG Аккаунт — Подключение</div>
      {alert}
      <div class="section"><div class="section-head"><h3>🔗 Управление подключением</h3></div>
        <div class="section-body">{body_html}</div></div></div>"""
    return HTMLResponse(base(content_html, "tg_account_setup", request))


@router.post("/tg_account/send_code")
async def tg_account_send_code(request: Request, phone: str = Form(...),
                                 api_id: str = Form(""), api_hash: str = Form("")):
    user, err = require_auth(request, role="admin")
    if err: return err
    # Сохраняем credentials в БД
    if api_id.strip():   db.set_setting("tg_api_id",   api_id.strip())
    if api_hash.strip(): db.set_setting("tg_api_hash", api_hash.strip())
    # Берём из БД если не пришли в форме
    final_api_id   = api_id.strip()   or db.get_setting("tg_api_id", "")
    final_api_hash = api_hash.strip() or db.get_setting("tg_api_hash", "")
    result = await tg_api("post", "/auth/send_code", json={
        "phone":    phone.strip(),
        "api_id":   final_api_id,
        "api_hash": final_api_hash,
    })
    if result.get("error"):
        db.set_setting("tg_account_status", "disconnected")
        return RedirectResponse(f"/tg_account/setup?msg=Ошибка:+{result['error']}", 303)
    # Сохраняем в БД: ждём ввода кода
    db.set_setting("tg_account_status", "awaiting_code")
    db.set_setting("tg_account_phone",  phone.strip())
    return RedirectResponse("/tg_account/setup?msg=Код+отправлен", 303)


@router.post("/tg_account/sign_in")
async def tg_account_sign_in(request: Request, code: str = Form(...)):
    user, err = require_auth(request, role="admin")
    if err: return err
    result = await tg_api("post", "/auth/sign_in", json={"code": code.strip()})
    if result.get("error") == "2fa_required":
        db.set_setting("tg_account_status", "awaiting_2fa")
        return RedirectResponse("/tg_account/setup", 303)
    if result.get("error"):
        db.set_setting("tg_account_status", "disconnected")
        return RedirectResponse(f"/tg_account/setup?msg=Ошибка: {result['error']}", 303)
    # Успешный вход — статус придёт через webhook, но сбрасываем awaiting_code на всякий случай
    db.set_setting("tg_account_status", "connected")
    return RedirectResponse("/tg_account/setup?msg=Аккаунт+подключён", 303)


@router.post("/tg_account/sign_in_2fa")
async def tg_account_sign_in_2fa(request: Request, password: str = Form(...)):
    user, err = require_auth(request, role="admin")
    if err: return err
    result = await tg_api("post", "/auth/sign_in", json={"password": password})
    if result.get("error"):
        return RedirectResponse(f"/tg_account/setup?msg=Ошибка: {result['error']}", 303)
    return RedirectResponse("/tg_account/setup?msg=Аккаунт+подключён", 303)


@router.post("/tg_account/disconnect")
async def tg_account_disconnect(request: Request):
    user, err = require_auth(request, role="admin")
    if err: return err
    await tg_api("post", "/auth/sign_out")
    db.set_setting("tg_account_status", "disconnected")
    db.set_setting("tg_account_username", "")
    db.set_setting("tg_account_phone", "")
    return RedirectResponse("/tg_account/setup?msg=Аккаунт+отключён", 303)


@router.post("/tg/webhook")
async def tg_account_webhook(request: Request):
    secret = request.headers.get("X-TG-Secret", "")
    if secret != TG_WH_SECRET:
        return JSONResponse({"error": "unauthorized"}, 401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": True})

    event = body.get("event")
    data  = body.get("data", {})
    log.info(f"[TG webhook] event={event} keys={list(data.keys())}")

    try:
        if event == "ready":
            db.set_setting("tg_account_status", "connected")
            db.set_setting("tg_account_username", data.get("username", ""))
            db.set_setting("tg_account_phone", data.get("phone", ""))
            db.set_setting("tg_account_name", data.get("name", ""))

        elif event == "disconnected":
            db.set_setting("tg_account_status", "disconnected")
            db.set_setting("tg_account_username", "")

        elif event == "message":
            tg_user_id  = data.get("tg_user_id", "")
            username    = data.get("username", "")
            sender_name = data.get("sender_name") or username or tg_user_id
            raw_text    = data.get("body") or ""
            has_media   = data.get("has_media", False)
            media_b64   = data.get("media_base64")
            media_type  = data.get("media_type", "")

            media_url = None
            if media_b64:
                try:
                    import cloudinary, cloudinary.uploader, base64 as _b64
                    cld_url = db.get_setting("cloudinary_url") or os.getenv("CLOUDINARY_URL", "")
                    if cld_url:
                        cloudinary.config(cloudinary_url=cld_url)
                        mime = media_type or "image/jpeg"
                        result = cloudinary.uploader.upload(f"data:{mime};base64,{media_b64}", folder="tg_account_media", resource_type="auto")
                        media_url = result.get("secure_url")
                    else:
                        # Fallback: data URL для всех типов медиа
                        mime = media_type or "application/octet-stream"
                        media_url = f"data:{mime};base64,{media_b64}"
                except Exception as e:
                    log.error(f"[TG webhook] media upload error: {e}")
                    # Последний fallback
                    if media_b64:
                        mime = media_type or "application/octet-stream"
                        media_url = f"data:{mime};base64,{media_b64}"

            if not raw_text and has_media:
                raw_text = "[фото]" if (media_type or "").startswith("image/") else "[файл]"
            text = (raw_text or "").strip() or "[сообщение]"

            conv = db.get_or_create_tg_account_conversation(tg_user_id, sender_name, username)
            # Подтягиваем фото профиля если ещё не загружено
            if not conv.get("photo_url"):
                try:
                    contact_info = await tg_api("get", f"/contact/{tg_user_id}")
                    if contact_info.get("ok") and contact_info.get("photo_url"):
                        db.update_tg_account_contact_info(conv["id"],
                            photo_url=contact_info.get("photo_url"),
                            about=contact_info.get("about",""))
                        conv = db.get_tg_account_conversation(conv["id"]) or conv
                except Exception as _e:
                    log.warning(f"[TG webhook] photo fetch error: {_e}")
            is_new = not conv.get("utm_source") and not conv.get("fbclid")
            if is_new:
                # Шаг 1: точный матчинг по ref_XXX из текста сообщения (/start ref_XXX)
                import re as _re
                _ref_match = _re.search(r'ref_([A-Za-z0-9_\-]{8,20})', raw_text)
                click_data = None
                if _ref_match:
                    _ref_id = _ref_match.group(1)
                    click_data = db.get_staff_click(_ref_id)
                    if click_data:
                        log.info(f"[TG webhook] UTM by ref_code: ref={_ref_id} utm={click_data.get('utm_campaign')} fbclid={'✓' if click_data.get('fbclid') else '—'}")
                # Шаг 2: fallback — ищем любой клик за последние 15 минут
                if not click_data:
                    click_data = db.get_staff_click_recent_any(minutes=15, target_type="telegram")
                    if click_data:
                        log.info(f"[TG webhook] UTM by time-window utm={click_data.get('utm_campaign')} fbclid={'✓' if click_data.get('fbclid') else '—'}")
                if click_data and not click_data.get("used"):
                    log.info(f"[TG webhook] Applying UTM: src={click_data.get('utm_source')} campaign={click_data.get('utm_campaign')} ttclid={'✓' if click_data.get('ttclid') else '—'}")
                    db.apply_utm_to_tg_conv(conv["id"],
                        fbclid=click_data.get("fbclid"), fbp=click_data.get("fbp"),
                        fbc=click_data.get("fbc"),
                        utm_source=click_data.get("utm_source"), utm_medium=click_data.get("utm_medium"),
                        utm_campaign=click_data.get("utm_campaign"), utm_content=click_data.get("utm_content"),
                        utm_term=click_data.get("utm_term"),
                        ttclid=click_data.get("ttclid"), ttp=click_data.get("ttp"))
                    db.mark_staff_click_used(click_data["ref_id"])
                    conv = db.get_tg_account_conversation(conv["id"]) or conv

            db.save_tg_account_message(conv["id"], tg_user_id, "visitor", text, media_url=media_url, media_type=media_type)
            db.update_tg_account_last_message(tg_user_id, text, increment_unread=True)

            # ── Авто-отправка Lead при первом сообщении (только FB/TikTok трафик) ──
            _is_paid_traffic = bool(
                conv.get("fbclid") or
                (conv.get("utm_source") or "").lower() in ("facebook", "fb", "tiktok", "tt")
            )
            _is_fb_traffic = _is_paid_traffic  # оставляем имя для совместимости
            _fresh_conv = db.get_tg_account_conversation(conv["id"]) or conv
            _is_first_msg = (_fresh_conv.get("unread_count") or 0) == 1
            if _is_fb_traffic and _is_first_msg and not _fresh_conv.get("fb_event_sent"):
                try:
                    px = _resolve_pixels(_fresh_conv)
                    _campaign = _fresh_conv.get("utm_campaign") or "telegram_account"
                    _utm_src  = _fresh_conv.get("utm_source") or "telegram"
                    _fbclid   = _fresh_conv.get("fbclid")
                    _fbp      = _fresh_conv.get("fbp")
                    _created_at = _fresh_conv.get("created_at", "")
                    _event_time = None
                    if _created_at:
                        try:
                            from datetime import timezone as _tz
                            _event_time = int(datetime.fromisoformat(_created_at.replace("Z","")).replace(tzinfo=_tz.utc).timestamp())
                        except Exception:
                            pass
                    log.info(f"[AutoLead/TGA] conv={conv['id']} pixel={px['fb_pixel'][:8] if px['fb_pixel'] else 'NONE'} project={px['project_name'] or 'global'} utm={_campaign} fbp={'✓' if _fbp else '—'} fbc={'✓' if _fbclid else '—'}")
                    _fb_sent = await meta_capi.send_lead_event(
                        px["fb_pixel"], px["fb_token"],
                        user_id=str(tg_user_id), campaign=_campaign,
                        fbclid=_fbclid, fbp=_fbp,
                        fbc=_fresh_conv.get("fbc") or None,
                        utm_source=_utm_src, utm_campaign=_campaign,
                        test_event_code=px["test_event_code"],
                        event_source_url="https://t.me/",
                        event_time=_event_time,
                    )
                    if _fb_sent:
                        db.set_tg_account_fb_event(conv["id"], "Lead")
                        log.info(f"[AutoLead/TGA] ✅ Lead sent conv={conv['id']}")
                    # TikTok
                    if px["tt_pixel"] and px["tt_token"] and tiktok_capi:
                        await tiktok_capi.send_lead_event(
                            px["tt_pixel"], px["tt_token"],
                            user_id=str(tg_user_id),
                            utm_source=_utm_src, utm_campaign=_campaign,
                            ttclid=_fresh_conv.get("ttclid") or _fbclid or None,
                            ttp=_fresh_conv.get("ttp") or None,
                            event_source_url="https://t.me/",
                            test_event_code=px["tt_test_event_code"],
                        )
                except Exception as _e:
                    log.error(f"[AutoLead/TGA] error: {_e}")

            notify_chat = db.get_setting("notify_chat_id")
            bot2 = bot_manager.get_staff_bot()
            if notify_chat and bot2:
                try:
                    ustr = f"@{username}" if username else tg_user_id
                    short = text[:80] + ("..." if len(text) > 80 else "")
                    _app_url = db.get_setting("app_url", "").rstrip("/")
                    _tg_kwargs = {}
                    if _app_url:
                        from aiogram import types as _tg_t
                        _tg_kwargs["reply_markup"] = _tg_t.InlineKeyboardMarkup(inline_keyboard=[[
                            _tg_t.InlineKeyboardButton(
                                text="Открыть TG чат →",
                                url=f"{_app_url}/tg_account/chat?conv_id={conv['id']}"
                            )
                        ]])
                    await bot2.send_message(int(notify_chat),
                        f"📱 TG Аккаунт — новое сообщение\n👤 {sender_name} ({ustr})\n✉️ {short}",
                        **_tg_kwargs)
                except Exception as e:
                    log.warning(f"[TG webhook] notify error: {e}")
    except Exception as e:
        log.error(f"[TG webhook] error: {e}", exc_info=True)
    return JSONResponse({"ok": True})


@router.post("/tg_account/send")
async def tg_account_send(request: Request, conv_id: int = Form(...), text: str = Form(...)):
    user, err = require_auth(request)
    if err: return JSONResponse({"error": "unauthorized"}, 401)
    conv = db.get_tg_account_conversation(conv_id)
    if not conv: return JSONResponse({"error": "not found"}, 404)
    result = await tg_api("post", "/send", json={"to": conv["tg_user_id"], "message": text})
    if not result.get("error"):
        manager_name = user.get("display_name") or user.get("username") or "Менеджер"
        db.save_tg_account_message(conv_id, conv["tg_user_id"], "manager", text, sender_name=manager_name)
        db.update_tg_account_last_message(conv["tg_user_id"], f"Вы: {text}", increment_unread=False)
    return JSONResponse({"ok": not result.get("error"), "error": result.get("error")})


@router.post("/tg_account/send_media")
async def tg_account_send_media(request: Request, conv_id: int = Form(...), file: UploadFile = File(...)):
    user, err = require_auth(request)
    if err: return JSONResponse({"error": "unauthorized"}, 401)
    conv = db.get_tg_account_conversation(conv_id)
    if not conv: return JSONResponse({"error": "not found"}, 404)
    import base64 as _b64
    file_data = await file.read()
    b64 = _b64.b64encode(file_data).decode()
    mimetype = file.content_type or "image/jpeg"
    filename = file.filename or "file"
    result = await tg_api("post", "/send_media", json={"to": conv["tg_user_id"], "base64": b64, "mimetype": mimetype, "filename": filename})
    if not result.get("error"):
        manager_name = user.get("display_name") or user.get("username") or "Менеджер"
        db.save_tg_account_message(conv_id, conv["tg_user_id"], "manager", "[файл]", media_type=mimetype, sender_name=manager_name)
        db.update_tg_account_last_message(conv["tg_user_id"], "Вы: [файл]", increment_unread=False)
    return JSONResponse({"ok": not result.get("error"), "error": result.get("error")})


@router.post("/tg_account/send_lead")
async def tg_account_send_lead(request: Request, conv_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    conv = db.get_tg_account_conversation(conv_id)
    if not conv: return RedirectResponse("/tg_account/chat", 303)
    if conv.get("fb_event_sent"):
        return RedirectResponse(f"/tg_account/chat?conv_id={conv_id}", 303)
    # Определяем пиксели — проект по utm_campaign или глобальные
    px       = _resolve_pixels(conv)
    campaign = conv.get("utm_campaign") or "telegram_account"
    utm_src  = conv.get("utm_source")   or "telegram"
    fbclid   = conv.get("fbclid")
    fbp      = conv.get("fbp")
    log.info(f"[Lead/TGA] pixel={px['fb_pixel'][:8] if px['fb_pixel'] else 'NONE'} project={px['project_name'] or 'global'} utm={campaign} test_code={px['test_event_code'] or 'NONE'} fbp={'✓' if fbp else '—'} fbc={'✓' if fbclid else '—'}")
    # Передаём время первого контакта — Facebook лучше атрибутирует к рекламному клику
    _created_at = conv.get("created_at", "")
    _event_time = None
    if _created_at:
        try:
            from datetime import timezone
            _event_time = int(datetime.fromisoformat(_created_at.replace("Z","")).replace(tzinfo=timezone.utc).timestamp())
        except Exception:
            _event_time = None
    sent = await meta_capi.send_lead_event(
        px["fb_pixel"], px["fb_token"],
        user_id=conv.get("tg_user_id", ""),
        campaign=campaign, fbclid=fbclid, fbp=fbp,
        fbc=conv.get("fbc") or None,
        utm_source=utm_src, utm_campaign=campaign,
        test_event_code=px["test_event_code"],
        event_source_url="https://t.me/",
        event_time=_event_time,
    )
    if sent:
        db.set_tg_account_fb_event(conv_id, "Lead")
    # TikTok Lead
    if px["tt_pixel"] and px["tt_token"] and tiktok_capi:
        await tiktok_capi.send_lead_event(
            px["tt_pixel"], px["tt_token"],
            user_id=str(conv.get("tg_user_id", "")),
            ip=request.client.host if request.client else None,
            utm_source=utm_src, utm_campaign=campaign,
            ttclid=conv.get("ttclid") or fbclid or None,
            event_source_url="https://t.me/",
            test_event_code=px["tt_test_event_code"],
        )
    return RedirectResponse(f"/tg_account/chat?conv_id={conv_id}", 303)


@router.post("/tg_account/close")
async def tg_account_close(request: Request, conv_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.close_tg_account_conv(conv_id)
    return RedirectResponse(f"/tg_account/chat?conv_id={conv_id}", 303)


@router.post("/tg_account/reopen")
async def tg_account_reopen(request: Request, conv_id: int = Form(...)):
    user, err = require_auth(request)
    if err: return err
    db.reopen_tg_account_conv(conv_id)
    return RedirectResponse(f"/tg_account/chat?conv_id={conv_id}", 303)


@router.post("/tg_account/delete")
async def tg_account_delete(request: Request, conv_id: int = Form(...)):
    user, err = require_auth(request, role="admin")
    if err: return JSONResponse({"error": "unauthorized"}, 401)
    db.delete_tg_account_conversation(conv_id)
    return JSONResponse({"ok": True})


@router.get("/api/tg_account_messages/{conv_id}")
async def api_tg_account_messages(request: Request, conv_id: int, after: int = 0):
    user, err = require_auth(request)
    if err: return JSONResponse({"error": "unauthorized"}, 401)
    msgs = db.get_new_tg_account_messages(conv_id, after)
    return JSONResponse({"messages": msgs})


@router.get("/api/tga_chat_panel", response_class=HTMLResponse)
async def api_tga_chat_panel(request: Request, conv_id: int = 0, status_filter: str = "open"):
    """SPA: возвращает только HTML правой панели TGA чата"""
    user, err = require_auth(request)
    if err: return HTMLResponse("<div style='padding:20px;color:var(--red)'>Нет доступа</div>", 401)
    if not conv_id:
        return HTMLResponse('<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text3);font-size:.9rem">Выберите диалог</div>')
    # Переиспользуем логику из tg_account_chat_page — только active_conv часть
    tg_status = db.get_setting("tg_account_status", "disconnected")
    active_conv = db.get_tg_account_conversation(conv_id)
    if not active_conv:
        return HTMLResponse('<div style="padding:20px;color:var(--text3)">Диалог не найден</div>')
    db.mark_tg_account_conv_read(conv_id)
    msgs = db.get_tg_account_messages(conv_id)
    messages_html = ""
    for m in msgs:
        _dt2 = m["created_at"] or ""
        _date2 = _dt2[:10].replace("-",".")[2:] if len(_dt2) >= 10 else ""
        _time2 = _dt2[11:16] if len(_dt2) >= 16 else ""
        t = f"{_date2} {_time2}".strip()
        if m.get("media_url") and (m.get("media_type") or "").startswith("image/"):
            ch = f'<img src="{m["media_url"]}" style="max-width:220px;max-height:220px;border-radius:8px;display:block;cursor:pointer" onclick="window.open(this.src)" />'
        elif m.get("media_url"):
            ch = f'<a href="{m["media_url"]}" target="_blank" style="color:#60a5fa">📎 Открыть файл</a>'
        else:
            ch = (m["content"] or "").replace("<", "&lt;")
        sl = f'<div style="font-size:.68rem;color:var(--orange);margin-bottom:2px;text-align:right;opacity:.8">{m["sender_name"]}</div>' if m.get("sender_name") and m["sender_type"] == "manager" else ""
        messages_html += f'<div class="msg {m["sender_type"]}" data-id="{m["id"]}">{sl}<div class="msg-bubble">{ch}</div><div class="msg-time">{t}</div></div>'
    uname = f"@{active_conv['username']}" if active_conv.get("username") else active_conv.get("tg_user_id", "")
    tga_staff = db.get_staff_by_tg_account_conv(conv_id)
    if tga_staff:
        tga_card_link = f'<a href="/staff?edit={tga_staff["id"]}" style="display:inline-flex;align-items:center;gap:4px;background:#052e16;color:#86efac;border:1px solid #166534;border-radius:6px;padding:2px 8px;font-size:.73rem;text-decoration:none">✅ В базе · {tga_staff.get("name","") or "Карточка"} →</a>'
    else:
        tga_card_link = f'<a href="/staff/create_from_tga?conv_id={conv_id}" style="display:inline-flex;align-items:center;gap:4px;background:var(--bg3);color:var(--text3);border:1px solid var(--border);border-radius:6px;padding:2px 8px;font-size:.73rem;text-decoration:none">+ Создать карточку</a>'
    all_tags     = db.get_all_tags()
    active_ctags = db.get_conv_tags("tga", conv_id)
    active_tag_ids = {tg["id"] for tg in active_ctags}
    tga_tags_html = _render_conv_tags_picker(active_ctags, all_tags, active_tag_ids, "tga", conv_id)
    fb_sent = active_conv.get("fb_event_sent")
    _is_fb_tga = bool(active_conv.get("fbclid") or (active_conv.get("utm_source") or "").lower() in ("facebook","fb","tiktok","tt"))
    if fb_sent:
        lead_btn = '<span class="badge-green">✅ Lead отправлен (авто)</span>'
    elif _is_fb_tga:
        lead_btn = '<span style="color:var(--text3);font-size:.73rem;opacity:.7">⏳ Ждём первого сообщения...</span>'
    else:
        lead_btn = f'<form method="post" action="/tg_account/send_lead" style="display:inline"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn btn-sm" style="font-size:.73rem;background:#1e3a5f;border:1px solid #3b5998;color:#93c5fd">📤 Lead → FB</button></form>'
    status_color = "#34d399" if active_conv["status"] == "open" else "#ef4444"
    close_btn = f'<form method="post" action="/tg_account/close"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-gray btn-sm">✓ Закрыть</button></form>' if active_conv["status"] == "open" else \
                f'<form method="post" action="/tg_account/reopen"><input type="hidden" name="conv_id" value="{conv_id}"/><button class="btn-orange btn-sm">↺ Открыть</button></form>'
    delete_btn = f'<button class="btn-gray btn-sm" style="color:#fff;background:#7f1d1d;border-color:#7f1d1d;font-size:.78rem;padding:5px 10px" onclick="deleteTgAccConv({conv_id})" title="Удалить диалог">🗑 Удалить</button>' if user and user.get("role") == "admin" else ""
    call_url = f"https://t.me/{active_conv['username']}" if active_conv.get("username") else f"tg://user?id={active_conv.get('tg_user_id','')}"
    tags = []
    _tga_src2 = (active_conv.get("utm_source") or "").lower()
    if active_conv.get("fbclid") or _tga_src2 in ("facebook","fb"):
        tags.append('<span class="utm-tag" style="background:#1e3a5f;color:#60a5fa">🔵 Facebook</span>')
    elif _tga_src2 in ("tiktok","tt"):
        tags.append('<span class="utm-tag" style="background:#1a1a2a;color:#69c9d0;border:1px solid #2a2a4a">🎵 TikTok</span>')
    if active_conv.get("utm_campaign"): tags.append(f'<span class="utm-tag">🎯 {active_conv["utm_campaign"][:25]}</span>')
    if active_conv.get("utm_content"): tags.append(f'<span class="utm-tag" style="background:#1a2a1a;color:#86efac">📌 {active_conv["utm_content"][:20]}</span>')
    if active_conv.get("utm_term"): tags.append(f'<span class="utm-tag" style="background:#1a1a2a;color:#a5b4fc">📂 {active_conv["utm_term"][:20]}</span>')
    if active_conv.get("fbclid"): tags.append('<span class="utm-tag badge-green">fbclid ✓</span>')
    utm_tags = '<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:6px">' + "".join(tags) + '</div>' if tags else ""
    _tga_photo = active_conv.get("photo_url") or ""
    if _tga_photo:
        _tga_avatar = '<div class="tga-avatar-wrap"><img src="' + _tga_photo + '" style="width:42px;height:42px;border-radius:50%;object-fit:cover;border:2px solid var(--orange)" /><div class="tga-avatar-zoom"><img src="' + _tga_photo + '" /></div></div>'
    else:
        _tga_avatar = '<div class="avatar">T</div>'
    return HTMLResponse(f"""
    <div class="chat-header">
      <div style="display:flex;align-items:flex-start;gap:12px;flex:1">
        {_tga_avatar}
        <div style="flex:1">
          <div style="font-weight:700;color:var(--text)">{active_conv['visitor_name']} <span style="color:{status_color};font-size:.72rem">●</span></div>
          <div style="font-size:.78rem;color:var(--text3)">{uname} · {tga_card_link}</div>
          <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:6px;align-items:center">
            {lead_btn}
            <a href="{call_url}" target="_blank" class="btn-gray btn-sm" style="display:inline-flex;align-items:center;gap:4px;padding:5px 10px;border-radius:7px;font-size:.74rem;border:1px solid var(--border);text-decoration:none">📞 Открыть в TG</a>
          </div>
          {utm_tags}{tga_tags_html}
        </div>
      </div>
      <div style="display:flex;gap:6px;flex-shrink:0">{close_btn} {delete_btn}</div>
    </div>
    <div class="chat-messages" id="tga-msgs">{messages_html}</div>
    <div id="tga-send-error" style="display:none;padding:8px 18px;background:#2d0a0a;border-top:1px solid #7f1d1d;font-size:.8rem;color:#fca5a5;align-items:center;justify-content:space-between;gap:8px">
      <span id="tga-send-error-text"></span>
      <button onclick="document.getElementById('tga-send-error').style.display='none'" style="background:none;border:none;color:#fca5a5;cursor:pointer;font-size:1rem">✕</button>
    </div>
    <div class="chat-input">
      <div id="tga-disconnected-banner" style="display:{'none' if tg_status == 'connected' else 'flex'};align-items:center;justify-content:space-between;padding:8px 12px;background:#1c1a00;border:1px solid #713f12;border-radius:8px;margin-bottom:8px;font-size:.8rem;color:#fde047;gap:8px">
        <span>⚠️ TG аккаунт не подключён — сообщения не будут доставлены</span>
        <a href="/tg_account/setup" style="color:#fde047;font-weight:600;white-space:nowrap;text-decoration:underline">Подключить →</a>
      </div>
      <div class="chat-input-row">
        <div style="position:relative;flex:1">
          <textarea id="tga-inp" placeholder="Написать в Telegram... (Enter — отправить)"
            style="width:100%;resize:none;background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:10px 44px 10px 14px;color:var(--text);font-size:.9rem;font-family:inherit;min-height:44px;max-height:120px"
            rows="1" onkeydown="if(event.key==='Enter'&&!event.shiftKey){{event.preventDefault();sendTgAccMsg()}}"></textarea>
          <label style="position:absolute;right:10px;bottom:10px;cursor:pointer;opacity:.6">
            📎<input type="file" id="tga-file" style="display:none" onchange="sendTgAccFile(this)"/>
          </label>
        </div>
        <button class="btn-orange" onclick="sendTgAccMsg()" style="height:44px;padding:0 18px;flex-shrink:0">Отправить</button>
      </div>
    </div>
    <script>
    var TGA_CONV_ID={conv_id};
    var TGA_SF='{status_filter}';
    var tgaMsgBox=document.getElementById('tga-msgs');
    if(tgaMsgBox) tgaMsgBox.scrollTop=tgaMsgBox.scrollHeight;
    var lastTgAId=(function(){{var m=document.querySelectorAll('#tga-msgs .msg[data-id]');return m.length?m[m.length-1].dataset.id:0;}})();
    // После SPA-навигации перезапускаем polling сообщений для нового чата
    if(window._tgaMsgsInterval) clearInterval(window._tgaMsgsInterval);
    window._tgaMsgsInterval = setInterval(function(){{
      if(typeof loadNewTgAccMsgs === 'function') loadNewTgAccMsgs();
    }}, 3000);
    </script>""")


@router.get("/api/tg_account_convs")
async def api_tg_account_convs(request: Request, status: str = "open", offset: int = 0):
    """Список TG диалогов для авто-обновления и пагинации"""
    user = check_session(request)
    if not user: return JSONResponse({"error": "unauthorized"}, 401)
    status_arg = status if status != "all" else None
    convs = db.get_tg_account_conversations(status=status_arg, limit=30, offset=offset)
    tga_in_staff = db.get_tga_conv_ids_in_staff()
    return JSONResponse({"convs": [
        {
            "id": c["id"],
            "visitor_name": c.get("visitor_name") or c.get("username") or str(c.get("tg_user_id", "")),
            "username": c.get("username") or "",
            "last_message": c.get("last_message") or "",
            "last_message_at": (c.get("last_message_at") or c["created_at"])[:16].replace("T", " "),
            "unread_count": c.get("unread_count", 0),
            "status": c.get("status", "open"),
            "utm_campaign": c.get("utm_campaign") or "",
            "utm_content":  c.get("utm_content") or "",
            "utm_term":     c.get("utm_term") or "",
            "utm_source":   c.get("utm_source") or "",
            "fbclid":       bool(c.get("fbclid")),
            "in_staff":     bool(tga_in_staff.get(c["id"])),
        } for c in convs
    ], "has_more": len(convs) == 30, "offset": offset})
