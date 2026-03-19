"""
routers/staff.py — Управление сотрудниками

Подключается в main.py:
    staff_setup(db, log, require_auth, base, nav_html, _render_conv_tags_picker)
    app.include_router(staff_router)
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
async def staff_page(request: Request, edit: int = 0, status_filter: str = "", msg: str = "", sort: str = "newest", search: str = ""):
    user, err = require_auth(request)
    if err: return err
    staff_list = db.get_staff(status_filter if status_filter else None, sort=sort, search=search)
    funnel = db.get_staff_funnel()
    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""

    # Поиск и сортировка
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
                        manager_name: str = Form(""), staff_photo: UploadFile = File(None)):
    user, err = require_auth(request)
    if err: return err
    db.update_staff(staff_id, name, phone, email, position, status, notes, tags, manager_name=manager_name.strip())
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

