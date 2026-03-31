"""
routers/staff.py — Управление сотрудниками

Подключается в main.py:
    staff_setup(db, log, require_auth, base, nav_html, _render_conv_tags_picker)
    app.include_router(staff_router)
"""

import os
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
STAFF_STATUSES = {}


def setup(_db, _log, _require_auth, _base, _nav_html, _render_conv_tags_picker_fn, _staff_statuses=None):
    global db, log, require_auth, base, nav_html, _render_conv_tags_picker, STAFF_STATUSES
    db             = _db
    log            = _log
    require_auth   = _require_auth
    base           = _base
    nav_html       = _nav_html
    _render_conv_tags_picker = _render_conv_tags_picker_fn
    if _staff_statuses: STAFF_STATUSES = _staff_statuses


# STAFF BASE
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/staff", response_class=HTMLResponse)
async def staff_page(request: Request, edit: int = 0, status_filter: str = "", msg: str = "", sort: str = "newest", search: str = "", date_from: str = "", date_to: str = ""):
    user, err = require_auth(request)
    if err: return err
    if date_from or date_to:
        staff_list = db.get_staff_filtered(
            date_from=date_from or None,
            date_to=date_to or None,
            status=status_filter or None
        )
        if search:
            _s = search.lower()
            staff_list = [s for s in staff_list if _s in (s.get('name') or '').lower()
                          or _s in (s.get('username') or '').lower()
                          or _s in (s.get('phone') or '').lower()]
    else:
        staff_list = db.get_staff(status_filter if status_filter else None, sort=sort, search=search)
    funnel = db.get_staff_funnel()
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""

    # Поиск и сортировка
    # Кнопки быстрых действий
    _action_btns = ('<div style="display:flex;gap:8px;margin-bottom:14px">'
        '<a href="/staff/new" style="text-decoration:none"><button class="btn-orange btn-sm">➕ Добавить вручную</button></a>'
        '<a href="/staff/calendar" style="text-decoration:none"><button class="btn-gray btn-sm">📅 Календарь</button></a>'
        '</div>')

    from datetime import date as _date, timedelta as _td
    _today = _date.today()
    _tw_s = (_today - _td(days=_today.weekday())).isoformat()
    _tw_e = (_today - _td(days=_today.weekday()) + _td(days=6)).isoformat()
    _lw_s = (_today - _td(days=_today.weekday()) - _td(weeks=1)).isoformat()
    _lw_e = (_today - _td(days=_today.weekday()) - _td(days=1)).isoformat()
    _sel_s = "background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:5px 8px;color:var(--text);font-size:.8rem"
    _active_week = (date_from == _tw_s and date_to == _tw_e)
    _active_lweek = (date_from == _lw_s and date_to == _lw_e)
    _w_style = "background:var(--orange);color:#fff;border-color:var(--orange)" if _active_week else ""
    _lw_style = "background:var(--orange);color:#fff;border-color:var(--orange)" if _active_lweek else ""
    _clr_btn = ('<a href="/staff?status_filter=' + status_filter + '"><button class="btn-gray btn-sm" type="button">✕</button></a>') if (date_from or date_to) else ""
    _date_filter_html = (
        '<form method="get" action="/staff" style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;margin-bottom:10px">'
        '<input type="hidden" name="status_filter" value="' + status_filter + '">'
        '<div style="display:flex;gap:6px;align-items:center">'
        '<span style="font-size:.78rem;color:var(--text3)">Период:</span>'
        '<input type="date" name="date_from" value="' + date_from + '" style="' + _sel_s + '">'
        '<span style="color:var(--text3)">—</span>'
        '<input type="date" name="date_to" value="' + date_to + '" style="' + _sel_s + '">'
        '<button class="btn btn-sm">OK</button>' + _clr_btn + '</div>'
        '<div style="display:flex;gap:4px">'
        '<a href="/staff?date_from=' + _tw_s + '&date_to=' + _tw_e + '&status_filter=' + status_filter + '" style="text-decoration:none"><button class="btn-gray btn-sm" style="' + _w_style + '">Эта неделя</button></a>'
        '<a href="/staff?date_from=' + _lw_s + '&date_to=' + _lw_e + '&status_filter=' + status_filter + '" style="text-decoration:none"><button class="btn-gray btn-sm" style="' + _lw_style + '">Прошлая</button></a>'
        '</div></form>'
    )

    from datetime import date as _date, timedelta as _td
    _today = _date.today()
    _tw_s = (_today - _td(days=_today.weekday())).isoformat()
    _tw_e = (_today - _td(days=_today.weekday()) + _td(days=6)).isoformat()
    _lw_s = (_today - _td(days=_today.weekday()) - _td(weeks=1)).isoformat()
    _lw_e = (_today - _td(days=_today.weekday()) - _td(days=1)).isoformat()

    _sel_style = "background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:5px 8px;color:var(--text);font-size:.8rem"
    _active_week = date_from == _tw_s and date_to == _tw_e
    _active_lweek = date_from == _lw_s and date_to == _lw_e
    _date_filter_html = (
        '<form method="get" action="/staff" style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;margin-bottom:10px">'
        '<input type="hidden" name="status_filter" value="' + status_filter + '"/>'
        '<div style="display:flex;gap:6px;align-items:center">'
        '<span style="font-size:.78rem;color:var(--text3)">Период:</span>'
        '<input type="date" name="date_from" value="' + date_from + '" style="' + _sel_style + '"/>'
        '<span style="color:var(--text3)">—</span>'
        '<input type="date" name="date_to" value="' + date_to + '" style="' + _sel_style + '"/>'
        '<button class="btn btn-sm">OK</button>'
        + ('<a href="/staff?status_filter=' + status_filter + '"><button class="btn-gray btn-sm" type="button">✕</button></a>' if date_from or date_to else '')
        + '</div>'
        '<div style="display:flex;gap:4px;align-items:center">'
        '<a href="/staff?date_from=' + _tw_s + '&date_to=' + _tw_e + '&status_filter=' + status_filter + '" style="text-decoration:none">'
        '<button class="btn-gray btn-sm" ' + ('style="background:var(--orange);color:#fff;border-color:var(--orange)"' if _active_week else '') + '>Эта неделя</button></a>'
        '<a href="/staff?date_from=' + _lw_s + '&date_to=' + _lw_e + '&status_filter=' + status_filter + '" style="text-decoration:none">'
        '<button class="btn-gray btn-sm" ' + ('style="background:var(--orange);color:#fff;border-color:var(--orange)"' if _active_lweek else '') + '>Прошлая</button></a>'
        '</div></form>'
    )

    search_bar = f'''<div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center">
      <form method="get" action="/staff" style="display:flex;gap:8px;flex:1;align-items:center;flex-wrap:wrap">
        <input type="hidden" name="status_filter" value="{status_filter}"/>
        <input type="text" name="search" value="{search}" placeholder="🔍 Поиск по имени, Telegram, WhatsApp..." 
               style="flex:1;min-width:200px;padding:6px 12px;background:var(--bg3);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:.84rem"/>
        <select name="sort" style="padding:6px 10px;background:var(--bg3);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:.84rem">
          <option value="newest" {"selected" if sort=="newest" else ""}>Сначала новые</option>
          <option value="oldest" {"selected" if sort=="oldest" else ""}>Сначала старые</option>
          <option value="name" {"selected" if sort=="name" else ""}>По имени А-Я</option>
          <option value="status" {"selected" if sort=="status" else ""}>По статусу</option>
        </select>
        <button class="btn btn-sm">Применить</button>
        {'<a href="/staff"><button class="btn-gray btn-sm" type="button">✕ Сбросить</button></a>' if search or sort != "newest" else ""}
      </form>
    </div>'''

    # Фильтр
    filter_btns = '<a href="/staff"><button class="btn-gray btn-sm" style="margin-right:4px">Все</button></a>'
    for s, (icon, label, _) in STAFF_STATUSES.items():
        active_style = "background:#1a2535;color:#fff;" if status_filter == s else ""
        cnt = funnel.get(s, 0)
        filter_btns += f'<a href="/staff?status_filter={s}"><button class="btn-gray btn-sm" style="margin-right:4px;{active_style}">{icon} {label} ({cnt})</button></a>'

    edit_form = ""
    if edit:
        s = db.get_staff_by_id(edit)
        if s:
            status_opts = "".join(f'<option value="{k}" {"selected" if s.get("status")==k else ""}>{icon} {label}</option>'
                                  for k, (icon, label, _) in STAFF_STATUSES.items())
            # Ссылка на чат (TG или WA)
            chat_link = ""
            if s.get("conversation_id"):
                chat_link = f'<a href="/chat?conv_id={s["conversation_id"]}" class="btn-gray btn-sm" style="text-decoration:none">💬 TG чат</a>'
            elif s.get("wa_conv_id"):
                chat_link = f'<a href="/wa/chat?conv_id={s["wa_conv_id"]}" class="btn-gray btn-sm" style="text-decoration:none;background:#052e16;border-color:#166534;color:#86efac">💚 WA чат</a>'
            manager_opts = "\n".join(
                '<option value="' + (u.get("display_name") or u["username"]) + '"'
                + (' selected' if s.get("manager_name") == (u.get("display_name") or u["username"]) else '')
                + '>' + (u.get("display_name") or u["username"]) + ' (' + u["role"] + ')</option>'
                for u in db.get_users()
            )
            if s.get("photo_url"):
                _purl = s["photo_url"]
                _pid  = s['id']
                photo_html = (
                    f'<div class="staff-photo-wrap" id="edit-photo-wrap">'
                    f'<img src="{_purl}" style="width:200px;height:200px;border-radius:12px;object-fit:cover;border:2px solid var(--border);display:block" />'
                    f'<div class="staff-photo-popup">'
                    f'<button class="spp-close" title="Закрыть" style="position:absolute;top:16px;right:20px;background:rgba(255,255,255,0.12);border:none;color:#fff;font-size:1.4rem;width:36px;height:36px;border-radius:50%;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:background .15s" onmouseover="this.style.background=\'rgba(255,255,255,0.25)\'" onmouseout="this.style.background=\'rgba(255,255,255,0.12)\'">✕</button>'
                    f'<img src="{_purl}" />'
                    f'<div class="staff-photo-popup-btns">'
                    f'<a href="{_purl}" download="photo_{_pid}.jpg">⬇ Скачать</a>'
                    f'</div></div></div>'
                )
            else:
                photo_html = '<div style="width:200px;height:200px;border-radius:12px;background:var(--bg3);border:2px dashed var(--border);display:flex;align-items:center;justify-content:center;font-size:3rem">👤</div>'
            # Галерея
            gallery_items = db.get_staff_gallery(s['id'])
            gallery_html = ""
            if gallery_items:
                gallery_html = '<div class="gallery-grid" id="staff-gallery">'
                for gi in gallery_items:
                    gi_id   = gi["id"]
                    gi_url  = gi["photo_url"]
                    s_id    = s["id"]
                    gallery_html += (
                        f'<div class="gallery-item" onclick="openGalleryLightbox(\'{gi_url}\',{gi_id})">'
                        f'<img src="{gi_url}" loading="lazy" />'
                        f'<button class="gallery-item-del" onclick="event.stopPropagation();deleteGalleryPhoto({gi_id},{s_id})" title="Удалить">✕</button>'
                        f'</div>'
                    )
                gallery_html += '</div>'
            else:
                gallery_html = '<div style="color:var(--text3);font-size:.82rem;padding:8px 0">Нет дополнительных фото</div>'
            edit_form = f"""<div class="section" style="margin-bottom:18px;border-left:3px solid #f97316">
              <div class="section-head"><h3>✏️ {s.get('name','Карточка')}</h3>{chat_link}</div>
              <div class="section-body">
                <form method="post" action="/staff/update" enctype="multipart/form-data">
                  <input type="hidden" name="staff_id" value="{s['id']}"/>
                  <div style="margin-bottom:16px;display:flex;align-items:flex-start;gap:16px;flex-wrap:wrap">
                    {photo_html}
                    <div style="display:flex;flex-direction:column;gap:10px">
                      <div>
                        <div class="field-label" style="margin-bottom:6px">Главное фото</div>
                        <input type="file" name="staff_photo" accept="image/*" style="font-size:.82rem;color:var(--text3)"/>
                        <div style="font-size:.72rem;color:var(--text3);margin-top:4px">JPG, PNG до 5MB</div>
                      </div>
                    </div>
                  </div>
                  <div class="grid-3" style="margin-bottom:12px">
                    <div class="field-group"><div class="field-label">Имя</div><input type="text" name="name" value="{s.get('name') or ''}"/></div>
                    <div class="field-group"><div class="field-label">Telegram</div><input type="text" name="phone" value="{s.get('phone') or ''}" placeholder="@username или +номер"/></div>
                    <div class="field-group"><div class="field-label">WhatsApp</div><input type="text" name="email" value="{s.get('email') or ''}" placeholder="+1234567890"/></div>
                    <div class="field-group"><div class="field-label">Должность</div><input type="text" name="position" value="{s.get('position') or ''}"/></div>
                    <div class="field-group"><div class="field-label">Статус</div><select name="status">{status_opts}</select></div>
                  </div>
                  <div class="field-group" style="margin-bottom:12px"><div class="field-label">Заметки</div><textarea name="notes">{s.get('notes') or ''}</textarea></div>
                  <div class="field-group" style="margin-bottom:12px">
                    <div class="field-label">👤 Закреплён за менеджером</div>
                    <select name="manager_name" style="width:100%;padding:7px 10px;background:var(--bg3);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:.84rem">
                      <option value="">— Не закреплён —</option>
                      {manager_opts}
                    </select>
                  </div>
                  <div class="field-group" style="margin-bottom:12px">
                    <div class="field-label">📅 Дата добавления анкеты</div>
                    <input type="date" name="created_at_manual" value="{(s.get('created_at') or '')[:10]}"/>
                    <span style="font-size:.72rem;color:var(--text3)">Измени если анкета поступила вне CRM</span>
                  </div>
                  <div style="display:flex;gap:8px">
                    <button class="btn-orange">💾 Сохранить</button>
                    <a href="/staff"><button class="btn-gray" type="button">Отмена</button></a>
                  </div>
                </form>
                <!-- Галерея -->
                <div style="margin-top:20px;padding-top:16px;border-top:1px solid var(--border)">
                  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
                    <div style="font-weight:600;font-size:.9rem">🖼 Галерея фото ({len(gallery_items)})</div>
                    <label style="background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:5px 12px;font-size:.78rem;cursor:pointer;color:var(--text2);transition:border-color .15s" onmouseover="this.style.borderColor='var(--orange)'" onmouseout="this.style.borderColor='var(--border)'">
                      ➕ Добавить фото
                      <input type="file" accept="image/*" multiple style="display:none" onchange="uploadGalleryPhotos(this,{s['id']})"/>
                    </label>
                  </div>
                  {gallery_html}
                </div>
              </div></div>
<!-- Lightbox для галереи -->
<div class="gallery-lightbox" id="gallery-lightbox">
  <span class="gallery-lightbox-close" onclick="closeGalleryLightbox()">✕</span>
  <img src="" id="lightbox-img" />
  <div class="gallery-lightbox-btns">
    <a id="lightbox-dl" href="#" download style="background:var(--orange);color:#fff;padding:8px 18px;border-radius:8px;font-size:.82rem;font-weight:600;text-decoration:none">⬇ Скачать</a>
    <button onclick="closeGalleryLightbox()" style="background:var(--bg3);color:var(--text);border:1px solid var(--border);border-radius:8px;padding:8px 18px;font-size:.82rem;cursor:pointer">Закрыть</button>
  </div>
</div>
<script>
function openGalleryLightbox(url, id) {{
  var lb = document.getElementById('gallery-lightbox');
  var img = document.getElementById('lightbox-img');
  var dl = document.getElementById('lightbox-dl');
  if (!lb || !img) return;
  img.src = url;
  dl.href = url;
  dl.download = 'photo_' + id + '.jpg';
  lb.classList.add('open');
}}
function closeGalleryLightbox() {{
  var lb = document.getElementById('gallery-lightbox');
  if (lb) lb.classList.remove('open');
}}
document.addEventListener('keydown', function(e) {{
  if (e.key === 'Escape') closeGalleryLightbox();
}});
async function uploadGalleryPhotos(input, staffId) {{
  if (!input.files || !input.files.length) return;
  var files = Array.from(input.files);
  var uploaded = 0;
  for (var i = 0; i < files.length; i++) {{
    var fd = new FormData();
    fd.append('staff_id', staffId);
    fd.append('photo', files[i]);
    try {{
      var r = await fetch('/staff/gallery/add', {{method:'POST', body: fd}});
      var d = await r.json();
      if (d.ok) uploaded++;
    }} catch(e) {{ console.error(e); }}
  }}
  if (uploaded > 0) window.location.reload();
  else alert('Ошибка загрузки фото');
}}
async function deleteGalleryPhoto(photoId, staffId) {{
  if (!confirm('Удалить фото из галереи?')) return;
  var fd = new FormData();
  fd.append('photo_id', photoId);
  fd.append('staff_id', staffId);
  var r = await fetch('/staff/gallery/delete', {{method:'POST', body: fd}});
  var d = await r.json();
  if (d.ok) window.location.reload();
  else alert('Ошибка удаления');
}}
</script>"""

    rows = ""
    for s in staff_list:
        icon, label, badge_cls = STAFF_STATUSES.get(s.get("status","new"), ("🆕","Новый","badge-gray"))
        fb = '<span class="badge-green" style="font-size:.7rem">FB ✓</span>' if s.get("fb_event_sent") else ""
        _photo = s.get("photo_url") or ""
        if _photo:
            _sid = s['id']
            _avatar = (
                f'<div class="staff-photo-wrap">'
                f'<img src="{_photo}" style="width:36px;height:36px;border-radius:8px;object-fit:cover;display:block" />'
                f'<div class="staff-photo-popup">'
                f'<button class="spp-close" title="Закрыть" style="position:absolute;top:16px;right:20px;background:rgba(255,255,255,0.12);border:none;color:#fff;font-size:1.4rem;width:36px;height:36px;border-radius:50%;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:background .15s" onmouseover="this.style.background=\'rgba(255,255,255,0.25)\'" onmouseout="this.style.background=\'rgba(255,255,255,0.12)\'">✕</button>'
                f'<img src="{_photo}" />'
                f'<div class="staff-photo-popup-btns">'
                f'<a href="{_photo}" download="photo_{_sid}.jpg">⬇ Скачать</a>'
                f'<a href="/staff?edit={_sid}" style="background:var(--bg3);color:var(--text);border:1px solid var(--border)">✏️ Карточка</a>'
                f'</div></div></div>'
            )
        else:
            _avatar = '<div style="width:36px;height:36px;border-radius:8px;background:var(--bg3);display:flex;align-items:center;justify-content:center;font-size:.9rem;flex-shrink:0">👤</div>'
        rows += f"""<tr>
            <td><div style="display:flex;align-items:center;gap:8px">
              {_avatar}
              <div>
                <div style="font-weight:600;color:#fff">{s['name'] or '—'}</div>
                <div style="font-size:.75rem;color:var(--text3)">@{s['username'] or '—'}</div>
              </div>
            </div></td>
            <td>{s.get('position') or '—'}</td>
            <td><span class="{badge_cls}">{icon} {label}</span></td>
            <td>{s.get('phone') or '—'}</td>
            <td style="font-size:.8rem;color:#86efac">{s.get('email') or '—'}</td>
            <td style="font-size:.8rem;color:var(--orange)">{s.get('manager_name') or '—'}</td>
            <td>{fb}</td>
            <td>{s['created_at'][:10]}</td>
            <td style="white-space:nowrap">
              <a href="/staff?edit={s['id']}"><button class="btn-orange btn-sm">✏️</button></a>
              {'<a href="/chat?conv_id=' + str(s.get("conversation_id","")) + '"><button class="btn-gray btn-sm" style="margin-left:4px">💬</button></a>' if s.get("conversation_id") else ''}
              {('<form method="post" action="/staff/delete" style="display:inline"><input type="hidden" name="staff_id" value="' + str(s["id"]) + '"/><button class="btn-gray btn-sm" style="color:var(--red);border-color:#7f1d1d;margin-left:4px" onclick="return confirm(''Удалить сотрудника полностью?'')">🗑</button></form>') if user and user.get("role") == "admin" else ""}
            </td></tr>"""

    if not rows:
        rows = '<tr><td colspan="7"><div class="empty">Нет сотрудников</div></td></tr>'

    content = f"""<div class="page-wrap">
    <div class="page-title">🗂 База сотрудников</div>
    <div class="page-sub">Все кто написал боту</div>
    {alert}
    {_action_btns}
    {_date_filter_html}
    {search_bar}
    <div style="margin-bottom:16px">{filter_btns}</div>
    {edit_form}
    <div class="section">
      <div class="section-head"><h3>📋 Сотрудники ({len(staff_list)})</h3></div>
      <table><thead><tr><th>Имя</th><th>Должность</th><th>Статус</th><th>Telegram</th><th>WhatsApp</th><th>Менеджер</th><th>FB</th><th>Добавлен</th><th></th></tr></thead>
      <tbody>{rows}</tbody></table>
    </div></div>"""
    return HTMLResponse(base(content, "staff", request))


@router.post("/staff/update")
async def staff_update(request: Request, staff_id: int = Form(...), name: str = Form(""),
                        phone: str = Form(""), email: str = Form(""), position: str = Form(""),
                        status: str = Form("new"), notes: str = Form(""), tags: str = Form(""),
                        manager_name: str = Form(""), created_at_manual: str = Form(""),
                        staff_photo: UploadFile = File(None)):
    user, err = require_auth(request)
    if err: return err
    db.update_staff(staff_id, name, phone, email, position, status, notes, tags, manager_name=manager_name.strip())
    if created_at_manual.strip():
        db.update_staff_created_at(staff_id, created_at_manual.strip())
    # Загрузка фото если прислали
    if staff_photo and staff_photo.filename:
        try:
            import cloudinary, cloudinary.uploader, base64 as _b64
            photo_data = await staff_photo.read()
            cld_url = db.get_setting("cloudinary_url") or os.getenv("CLOUDINARY_URL", "")
            photo_url = None
            if cld_url:
                cloudinary.config(cloudinary_url=cld_url)
                b64 = _b64.b64encode(photo_data).decode()
                mime = staff_photo.content_type or "image/jpeg"
                result = cloudinary.uploader.upload(
                    f"data:{mime};base64,{b64}",
                    folder="staff_photos", resource_type="image"
                )
                photo_url = result.get("secure_url")
            else:
                mime = staff_photo.content_type or "image/jpeg"
                photo_url = f"data:{mime};base64,{_b64.b64encode(photo_data).decode()}"
            if photo_url:
                db.update_staff_photo(staff_id, photo_url)
        except Exception as e:
            log.error(f"[staff/update] photo upload error: {e}")
    return RedirectResponse(f"/staff?msg=Сохранено", 303)


@router.post("/staff/delete")
async def staff_delete(request: Request, staff_id: int = Form(...)):
    user, err = require_auth(request, role="admin")
    if err: return err
    db.delete_staff_full(staff_id)
    return RedirectResponse("/staff?msg=Сотрудник+удалён+полностью", 303)


@router.post("/staff/gallery/add")
async def staff_gallery_add(request: Request, staff_id: int = Form(...), photo: UploadFile = File(...)):
    """Добавить фото в галерею сотрудника"""
    user, err = require_auth(request)
    if err: return JSONResponse({"ok": False, "error": "unauthorized"}, 401)
    if not photo or not photo.filename:
        return JSONResponse({"ok": False, "error": "no file"})
    try:
        import cloudinary, cloudinary.uploader, base64 as _b64
        photo_data = await photo.read()
        cld_url = db.get_setting("cloudinary_url") or os.getenv("CLOUDINARY_URL", "")
        photo_url = None
        if cld_url:
            cloudinary.config(cloudinary_url=cld_url)
            mime = photo.content_type or "image/jpeg"
            b64 = _b64.b64encode(photo_data).decode()
            result = cloudinary.uploader.upload(
                f"data:{mime};base64,{b64}",
                folder="staff_gallery", resource_type="image"
            )
            photo_url = result.get("secure_url")
        else:
            mime = photo.content_type or "image/jpeg"
            photo_url = f"data:{mime};base64,{_b64.b64encode(photo_data).decode()}"
        if not photo_url:
            return JSONResponse({"ok": False, "error": "upload failed"})
        gi = db.add_staff_gallery_photo(staff_id, photo_url)
        return JSONResponse({"ok": True, "id": gi["id"], "photo_url": photo_url})
    except Exception as e:
        log.error(f"[gallery/add] error: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


@router.post("/staff/gallery/delete")
async def staff_gallery_delete(request: Request, photo_id: int = Form(...), staff_id: int = Form(...)):
    """Удалить фото из галереи"""
    user, err = require_auth(request)
    if err: return JSONResponse({"ok": False, "error": "unauthorized"}, 401)
    ok = db.delete_staff_gallery_photo(photo_id, staff_id)
    return JSONResponse({"ok": ok})


@router.get("/staff/create_from_conv")
async def staff_create_from_conv(request: Request, conv_id: int = 0):
    user, err = require_auth(request)
    if err: return err
    if not conv_id:
        return RedirectResponse("/chat", 303)
    conv = db.get_conversation(conv_id)
    if not conv:
        return RedirectResponse("/chat", 303)
    # Создаём или находим карточку
    existing = db.get_staff_by_conv(conv_id)
    if existing:
        return RedirectResponse(f"/staff?edit={existing['id']}", 303)
    # Создаём новую карточку
    staff = db.get_or_create_staff(
        tg_chat_id=conv.get("tg_chat_id"),
        name=conv.get("visitor_name","Новый"),
        username=conv.get("username",""),
        conv_id=conv_id
    )
    return RedirectResponse(f"/staff?edit={staff['id']}", 303)


@router.get("/staff/create_from_wa")
async def staff_create_from_wa(request: Request, conv_id: int = 0):
    user, err = require_auth(request)
    if err: return err
    if not conv_id:
        return RedirectResponse("/wa/chat", 303)
    conv = db.get_wa_conversation(conv_id)
    if not conv:
        return RedirectResponse("/wa/chat", 303)
    existing = db.get_staff_by_wa_conv(conv_id)
    if existing:
        return RedirectResponse(f"/staff?edit={existing['id']}", 303)
    staff = db.get_or_create_wa_staff(
        wa_conv_id=conv_id,
        name=conv.get("visitor_name","Новый"),
        wa_number=conv.get("wa_number","")
    )
    return RedirectResponse(f"/staff?edit={staff['id']}", 303)


@router.get("/staff/create_from_tga")
async def staff_create_from_tga(request: Request, conv_id: int = 0):
    """Создать карточку сотрудника из TG аккаунт чата"""
    user, err = require_auth(request)
    if err: return err
    if not conv_id:
        return RedirectResponse("/tg_account/chat", 303)
    conv = db.get_tg_account_conversation(conv_id)
    if not conv:
        return RedirectResponse("/tg_account/chat", 303)
    existing = db.get_staff_by_tg_account_conv(conv_id)
    if existing:
        return RedirectResponse(f"/staff?edit={existing['id']}", 303)
    staff = db.get_or_create_tga_staff(
        tga_conv_id=conv_id,
        name=conv.get("visitor_name", "Новый"),
        username=conv.get("username", "")
    )
    return RedirectResponse(f"/staff?edit={staff['id']}", 303)



# ─── РУЧНОЕ СОЗДАНИЕ СОТРУДНИКА ───────────────────────────────────────────────

@router.get("/staff/new", response_class=HTMLResponse)
async def staff_new_page(request: Request, msg: str = "", err: str = ""):
    user, err_auth = require_auth(request)
    if err_auth: return err_auth

    alert = (f'<div class="alert-green">✅ {msg}</div>' if msg else
             f'<div class="alert-red">❌ {err}</div>' if err else "")

    status_opts = "".join(
        f'<option value="{k}" {"selected" if k=="new" else ""}>{icon} {label}</option>'
        for k, (icon, label, _) in STAFF_STATUSES.items()
    )
    manager_opts = "<option value=''>— не назначен —</option>" + "\n".join(
        f'<option value="{u.get("display_name") or u["username"]}">'
        f'{u.get("display_name") or u["username"]} ({u["role"]})</option>'
        for u in db.get_users()
    )

    content = f"""<div class="page-wrap">
    <div class="page-title">➕ Добавить сотрудника вручную</div>
    <div class="page-sub"><a href="/staff" style="color:var(--text3)">← База</a></div>
    {alert}

    <div class="section"><div class="section-head"><h3>Новая карточка</h3></div>
    <div class="section-body">
      <form method="post" action="/staff/create_manual" enctype="multipart/form-data">
        <div class="form-row" style="flex-wrap:wrap;gap:12px">
          <div class="field-group" style="flex:1;min-width:200px">
            <div class="field-label">Имя *</div>
            <input type="text" name="name" required placeholder="Анна Иванова"/>
          </div>
          <div class="field-group" style="flex:1;min-width:200px">
            <div class="field-label">Telegram username</div>
            <input type="text" name="username" placeholder="@username"/>
          </div>
          <div class="field-group" style="flex:1;min-width:200px">
            <div class="field-label">Телефон</div>
            <input type="text" name="phone" placeholder="+1 234 567 8900"/>
          </div>
        </div>
        <div class="form-row" style="flex-wrap:wrap;gap:12px;margin-top:10px">
          <div class="field-group" style="flex:1;min-width:200px">
            <div class="field-label">Email</div>
            <input type="email" name="email" placeholder="anna@email.com"/>
          </div>
          <div class="field-group" style="flex:1;min-width:200px">
            <div class="field-label">Должность</div>
            <input type="text" name="position" placeholder="Массажист"/>
          </div>
          <div class="field-group" style="flex:1;min-width:160px">
            <div class="field-label">Статус</div>
            <select name="status">{status_opts}</select>
          </div>
        </div>
        <div class="form-row" style="flex-wrap:wrap;gap:12px;margin-top:10px">
          <div class="field-group" style="flex:1;min-width:200px">
            <div class="field-label">Менеджер</div>
            <select name="manager_name">{manager_opts}</select>
          </div>
          <div class="field-group" style="flex:1;min-width:200px">
            <div class="field-label">Теги (через запятую)</div>
            <input type="text" name="tags" placeholder="LA, опыт, english"/>
          </div>
          <div class="field-group" style="flex:1;min-width:200px">
            <div class="field-label">📅 Дата добавления анкеты</div>
            <input type="date" name="created_at_manual" value="{__import__('datetime').datetime.utcnow().strftime('%Y-%m-%d')}"/>
            <span style="font-size:.72rem;color:var(--text3)">Если анкета поступила вне CRM</span>
          </div>
        </div>
        <div class="form-row" style="flex-wrap:wrap;gap:12px;margin-top:10px">
          <div class="field-group" style="flex:1;min-width:200px">
            <div class="field-label">Фото</div>
            <input type="file" name="staff_photo" accept="image/*" style="font-size:.82rem"/>
          </div>
        </div>
        <div class="field-group" style="margin-top:10px">
          <div class="field-label">Заметки</div>
          <textarea name="notes" rows="3" placeholder="Дополнительная информация..."></textarea>
        </div>
        <div style="display:flex;gap:8px;margin-top:16px">
          <button class="btn-orange">💾 Создать карточку</button>
          <a href="/staff"><button type="button" class="btn-gray">Отмена</button></a>
        </div>
      </form>
    </div></div>
    </div>"""

    return HTMLResponse(base(content, "staff", request))


@router.post("/staff/create_manual")
async def staff_create_manual(request: Request,
                               name: str = Form(...), username: str = Form(""),
                               phone: str = Form(""), email: str = Form(""),
                               position: str = Form(""), status: str = Form("new"),
                               notes: str = Form(""), tags: str = Form(""),
                               manager_name: str = Form(""),
                               created_at_manual: str = Form(""),
                               staff_photo: UploadFile = File(None)):
    user, err = require_auth(request)
    if err: return err

    staff_id = db.create_staff_manual(
        name=name, phone=phone, email=email, position=position,
        status=status, notes=notes, tags=tags,
        username=username.lstrip("@"), manager_name=manager_name,
        created_at_override=created_at_manual.strip() or None
    )

    # Загрузка фото
    if staff_photo and staff_photo.filename:
        try:
            import cloudinary, cloudinary.uploader, base64 as _b64
            cld_name = os.getenv("CLOUDINARY_CLOUD_NAME", "")
            cld_key  = os.getenv("CLOUDINARY_API_KEY", "")
            cld_sec  = os.getenv("CLOUDINARY_API_SECRET", "")
            cld_url  = db.get_setting("cloudinary_url") or os.getenv("CLOUDINARY_URL", "")
            if cld_name and cld_key and cld_sec:
                cloudinary.config(cloud_name=cld_name, api_key=cld_key, api_secret=cld_sec)
            elif cld_url:
                cloudinary.config(cloudinary_url=cld_url)
            photo_data = await staff_photo.read()
            mime = staff_photo.content_type or "image/jpeg"
            result = cloudinary.uploader.upload(
                f"data:{mime};base64,{_b64.b64encode(photo_data).decode()}",
                folder="staff_photos", resource_type="image"
            )
            photo_url = result.get("secure_url")
            if photo_url:
                db.update_staff_photo(staff_id, photo_url)
        except Exception as e:
            log.error(f"[staff/create_manual] photo error: {e}")

    return RedirectResponse(f"/staff?edit={staff_id}&msg=Сотрудник+добавлен", 303)


# ─── КАЛЕНДАРЬ СОТРУДНИКОВ ────────────────────────────────────────────────────

@router.get("/staff/calendar", response_class=HTMLResponse)
async def staff_calendar(request: Request, year: int = 0, month: int = 0, view: str = "month"):
    user, err = require_auth(request)
    if err: return err

    from datetime import datetime, date
    import calendar as _cal

    now = datetime.utcnow()
    if not year:  year  = now.year
    if not month: month = now.month

    # Навигация
    prev_month = month - 1 if month > 1 else 12
    prev_year  = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year  = year if month < 12 else year + 1

    month_name = ["", "Январь","Февраль","Март","Апрель","Май","Июнь",
                  "Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"][month]

    # Все сотрудники месяца
    staff_list = db.get_staff_by_month(year, month)

    # Группируем по дню
    by_day = {}
    for s in staff_list:
        try:
            d = s["created_at"][:10]  # YYYY-MM-DD
            day = int(d.split("-")[2])
            if day not in by_day:
                by_day[day] = []
            by_day[day].append(s)
        except: pass

    # Строим сетку месяца
    cal = _cal.monthcalendar(year, month)
    days_header = "<tr>" + "".join(
        f'<th style="padding:8px;font-size:.75rem;color:var(--text3);font-weight:600;text-align:center">{d}</th>'
        for d in ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]
    ) + "</tr>"

    today = date.today()
    rows = ""
    for week in cal:
        rows += "<tr>"
        for day in week:
            if day == 0:
                rows += '<td style="background:var(--bg3);min-height:80px;padding:4px;border:1px solid var(--border)"></td>'
            else:
                is_today = (date(year, month, day) == today)
                today_style = "background:rgba(249,115,22,.08);border-color:var(--orange);" if is_today else ""
                day_staff = by_day.get(day, [])
                day_label = f'<div style="font-weight:700;font-size:.8rem;{"color:var(--orange)" if is_today else "color:var(--text3)"};margin-bottom:4px">{day}</div>'
                cards = ""
                for s in day_staff[:3]:
                    _sicon = STAFF_STATUSES.get(s.get("status","new"), ("🆕","",""))[0]
                    cards += (
                        f'<a href="/staff?edit={s["id"]}" style="display:block;text-decoration:none;'
                        f'background:var(--bg3);border:1px solid var(--border);border-radius:5px;'
                        f'padding:3px 6px;margin-bottom:2px;font-size:.7rem;color:var(--text);'
                        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'
                        f'{_sicon} {s.get("name") or "—"}</a>'
                    )
                if len(day_staff) > 3:
                    cards += f'<div style="font-size:.68rem;color:var(--text3);padding:2px 4px">+{len(day_staff)-3} ещё</div>'
                rows += (
                    f'<td style="vertical-align:top;min-height:80px;height:90px;padding:6px;'
                    f'border:1px solid var(--border);{today_style}">'
                    f'{day_label}{cards}</td>'
                )
        rows += "</tr>"

    # Статистика месяца
    total = len(staff_list)
    by_status = {}
    for s in staff_list:
        st = s.get("status","new")
        by_status[st] = by_status.get(st, 0) + 1

    stat_items = ""
    for st, cnt in by_status.items():
        icon, label, _ = STAFF_STATUSES.get(st, ("","",""))
        stat_items += f'<span style="background:var(--bg3);border:1px solid var(--border);border-radius:6px;padding:4px 10px;font-size:.78rem">{icon} {label}: <b>{cnt}</b></span>'

    content = f"""<div class="page-wrap">
    <div class="page-title">📅 Календарь сотрудников</div>
    <div class="page-sub"><a href="/staff" style="color:var(--text3)">← База</a></div>

    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:8px">
      <div style="display:flex;align-items:center;gap:12px">
        <a href="/staff/calendar?year={prev_year}&month={prev_month}">
          <button class="btn-gray btn-sm">← </button></a>
        <div style="font-size:1.1rem;font-weight:700;min-width:160px;text-align:center">{month_name} {year}</div>
        <a href="/staff/calendar?year={next_year}&month={next_month}">
          <button class="btn-gray btn-sm"> →</button></a>
        <a href="/staff/calendar?year={now.year}&month={now.month}">
          <button class="btn-gray btn-sm">Сегодня</button></a>
      </div>
      <div style="font-size:.82rem;color:var(--text3)">Добавлено в этом месяце: <b style="color:var(--text)">{total}</b></div>
    </div>

    {f'<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px">{stat_items}</div>' if stat_items else ''}

    <div class="section" style="overflow-x:auto">
      <table style="width:100%;border-collapse:collapse;min-width:600px">
        <thead>{days_header}</thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    </div>"""

    return HTMLResponse(base(content, "staff", request))


# ─── ВКЛАДКА БОНУСЫ ──────────────────────────────────────────────────────────

@router.get("/staff/bonuses", response_class=HTMLResponse)
async def staff_bonuses_page(request: Request,
                              date_from: str = "", date_to: str = "",
                              manager_filter: str = "", msg: str = ""):
    user, err = require_auth(request)
    if err: return err

    from datetime import datetime, timedelta, date

    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""
    rates = db.get_bonus_rates()
    today = date.today()

    # Быстрые диапазоны дат
    def week_range(offset=0):
        start = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
        end = start + timedelta(days=6)
        return start.isoformat(), end.isoformat()

    def month_range(offset=0):
        import calendar
        d = date(today.year, today.month, 1)
        if offset < 0:
            d = date(d.year if d.month > 1 else d.year-1, d.month-1 if d.month > 1 else 12, 1)
        last = calendar.monthrange(d.year, d.month)[1]
        return d.isoformat(), date(d.year, d.month, last).isoformat()

    tw_s, tw_e = week_range(0)
    lw_s, lw_e = week_range(-1)
    tm_s, tm_e = month_range(0)
    lm_s, lm_e = month_range(-1)

    def _qbtn(label, df, dt, color="#1e3a5f"):
        active = "background:var(--orange);color:#fff;border-color:var(--orange)" if (date_from==df and date_to==dt) else f"background:{color};color:var(--text)"
        return f'<a href="/staff/bonuses?date_from={df}&date_to={dt}&manager_filter={manager_filter}" style="text-decoration:none"><button class="btn-gray btn-sm" style="{active}">{label}</button></a>'

    quick_btns = (
        _qbtn("Эта неделя", tw_s, tw_e) +
        _qbtn("Прошлая неделя", lw_s, lw_e) +
        _qbtn("Этот месяц", tm_s, tm_e) +
        _qbtn("Прошлый месяц", lm_s, lm_e)
    )

    # Менеджеры для фильтра
    managers = [u.get("display_name") or u["username"] for u in db.get_users()]
    mgr_opts = "<option value=''>Все менеджеры</option>" + "".join(
        f'<option value="{m}" {"selected" if manager_filter==m else ""}>{m}</option>'
        for m in managers
    )

    # Итоги за период
    summary = None
    period_label = ""
    if date_from or date_to:
        summary = db.get_staff_bonus_summary(
            date_from=date_from or None,
            date_to=date_to or None,
            manager=manager_filter or None
        )
        df_fmt = date_from[5:] if date_from else "начало"
        dt_fmt = date_to[5:] if date_to else "сейчас"
        period_label = f"{df_fmt.replace('-','.')} — {dt_fmt.replace('-','.')}"

    # Таблица итогов
    summary_html = ""
    if summary:
        rows_s = ""
        for st, data in summary["by_status"].items():
            icon, label, _ = STAFF_STATUSES.get(st, ("","",""))
            rate = data["rate"]
            count = data["count"]
            amount = data["amount"]
            rows_s += f"""<tr>
              <td>{icon} {label or st}</td>
              <td style="text-align:center;font-weight:700">{count}</td>
              <td style="text-align:center;color:var(--text3)">${rate:.2f}</td>
              <td style="text-align:center;color:#86efac;font-weight:700">${amount:.2f}</td>
            </tr>"""

        summary_html = f"""
        <div class="section" style="border-left:3px solid #86efac">
          <div class="section-head"><h3>💰 Итого за период: {period_label}</h3></div>
          <div class="section-body">
            <table style="width:100%;border-collapse:collapse">
              <thead><tr>
                <th style="text-align:left;padding:8px;font-size:.78rem;color:var(--text3)">Статус</th>
                <th style="text-align:center;padding:8px;font-size:.78rem;color:var(--text3)">Анкет</th>
                <th style="text-align:center;padding:8px;font-size:.78rem;color:var(--text3)">Ставка</th>
                <th style="text-align:center;padding:8px;font-size:.78rem;color:var(--text3)">Сумма</th>
              </tr></thead>
              <tbody>{rows_s}</tbody>
              <tfoot><tr style="border-top:2px solid var(--border)">
                <td style="padding:10px 8px;font-weight:700">ИТОГО</td>
                <td style="text-align:center;padding:10px 8px;font-weight:700">{summary['total_count']}</td>
                <td></td>
                <td style="text-align:center;padding:10px 8px;font-weight:700;color:#86efac;font-size:1.1rem">${summary['total_amount']:.2f}</td>
              </tr></tfoot>
            </table>
          </div>
        </div>"""

    # Форма ставок
    rate_rows = ""
    for st, (icon, label, _) in STAFF_STATUSES.items():
        cur_rate = rates.get(st, {}).get("rate", 0)
        rate_rows += f"""<tr>
          <td style="padding:10px 8px">{icon} {label}</td>
          <td style="padding:10px 8px">
            <div style="display:flex;align-items:center;gap:6px">
              <span style="color:var(--text3)">$</span>
              <input type="number" name="rate_{st}" value="{cur_rate:.2f}"
                     min="0" step="0.5"
                     style="width:100px;background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:6px 10px;color:var(--text);font-size:.85rem"/>
            </div>
          </td>
        </tr>"""

    content = f"""<div class="page-wrap">
    <div class="page-title">💰 Бонусы</div>
    <div class="page-sub"><a href="/staff" style="color:var(--text3)">← База</a></div>
    {alert}

    <div class="section"><div class="section-head"><h3>📊 Отчёт за период</h3></div>
    <div class="section-body">
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px">{quick_btns}</div>
      <form method="get" action="/staff/bonuses">
        <div class="form-row" style="flex-wrap:wrap;gap:10px;align-items:flex-end">
          <div class="field-group" style="flex:1;min-width:140px">
            <div class="field-label">С даты</div>
            <input type="date" name="date_from" value="{date_from}"/>
          </div>
          <div class="field-group" style="flex:1;min-width:140px">
            <div class="field-label">По дату</div>
            <input type="date" name="date_to" value="{date_to}"/>
          </div>
          <div class="field-group" style="flex:1;min-width:160px">
            <div class="field-label">Менеджер</div>
            <select name="manager_filter">{mgr_opts}</select>
          </div>
          <div style="display:flex;align-items:flex-end;gap:6px">
            <button class="btn-orange">📊 Показать</button>
            <a href="/staff/bonuses"><button type="button" class="btn-gray">✕</button></a>
          </div>
        </div>
      </form>
    </div></div>

    {summary_html}

    <div class="section"><div class="section-head"><h3>⚙️ Ставки оплаты</h3></div>
    <div class="section-body">
      <form method="post" action="/staff/bonuses/save_rates">
        <table style="width:100%;border-collapse:collapse">
          <thead><tr>
            <th style="text-align:left;padding:8px;font-size:.78rem;color:var(--text3)">Статус анкеты</th>
            <th style="text-align:left;padding:8px;font-size:.78rem;color:var(--text3)">Ставка за анкету</th>
          </tr></thead>
          <tbody>{rate_rows}</tbody>
        </table>
        <button class="btn-orange" style="margin-top:12px">💾 Сохранить ставки</button>
      </form>
    </div></div>
    </div>"""

    return HTMLResponse(base(content, "staff", request))


@router.post("/staff/bonuses/save_rates")
async def staff_bonuses_save(request: Request):
    user, err = require_auth(request, role="admin")
    if err: return err
    form = await request.form()
    for key, val in form.items():
        if key.startswith("rate_"):
            status = key[5:]
            try:
                rate = float(val)
                _, label, _ = STAFF_STATUSES.get(status, ("", status, ""))
                db.set_bonus_rate(status, rate, label)
            except: pass
    return RedirectResponse("/staff/bonuses?msg=Ставки+сохранены", 303)
