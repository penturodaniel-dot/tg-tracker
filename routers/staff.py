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
            # История касаний
            notes_list = db.get_staff_notes(s['id'])
            _note_type_colors = {
                'note':    ('#1a1a3a','#818cf8','📝'),
                'call':    ('#1a2a3a','#5aaddd','📞'),
                'message': ('#1a2a35','#5cc87a','💬'),
                'meet':    ('#2a1a3a','#bb77ee','📅'),
                'status':  ('#2a1a0a','#f97316','🔄'),
            }
            notes_timeline_html = ""
            if notes_list:
                for n in notes_list:
                    _nt = n.get('type','note')
                    _bg, _col, _ico = _note_type_colors.get(_nt, ('#1a1a3a','#818cf8','📝'))
                    _ndate = (n.get('created_at') or '')[:16].replace('T',' ')
                    _remind = f'<span style="font-size:.7rem;color:#f97316;margin-left:6px">⏰ {n["remind_at"]}</span>' if n.get('remind_at') else ''
                    _nid = n['id']
                    _sid2 = s['id']
                    notes_timeline_html += (
                        f'<div style="display:flex;gap:10px;padding:10px 0;border-bottom:1px solid var(--border)">'
                        f'<div style="width:28px;height:28px;border-radius:50%;background:{_bg};display:flex;align-items:center;justify-content:center;font-size:13px;flex-shrink:0">{_ico}</div>'
                        f'<div style="flex:1">'
                        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;flex-wrap:wrap">'
                        f'<span style="font-size:.8rem;font-weight:600;color:{_col}">{n.get("manager_name") or "—"}</span>'
                        f'<span style="font-size:.72rem;color:var(--text3)">{_ndate}</span>'
                        f'<span style="font-size:.7rem;padding:1px 7px;border-radius:20px;background:{_bg};color:{_col}">{_nt}</span>'
                        f'{_remind}'
                        f'<button type="button" onclick="deleteStaffNote({_nid},{_sid2})" style="margin-left:auto;background:transparent;border:none;color:var(--text3);font-size:.7rem;cursor:pointer;padding:0 4px">✕</button>'
                        f'</div>'
                        f'<div style="font-size:.82rem;color:var(--text2);line-height:1.5">{n.get("text") or ""}</div>'
                        f'</div></div>'
                    )
            else:
                notes_timeline_html = '<div style="color:var(--text3);font-size:.82rem;padding:8px 0">Пока нет касаний — добавьте первую заметку</div>'
            # Последнее касание
            _days_ago = db.get_staff_no_contact_days(s['id'])
            if _days_ago < 0:
                last_contact_str = "касаний нет"
            elif _days_ago == 0:
                last_contact_str = "последнее касание: сегодня"
            elif _days_ago == 1:
                last_contact_str = "последнее касание: вчера"
            else:
                last_contact_str = f"последнее касание: {_days_ago} дн. назад"

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
                    <div class="field-label">📍 Город размещения</div>
                    <input type="text" name="city" value="{s.get('city') or ''}" placeholder="Los Angeles, Chicago..."/>
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
<!-- История касаний -->
<div class="section" style="margin-top:18px;border-left:3px solid #6366f1">
  <div class="section-head" style="display:flex;align-items:center;justify-content:space-between">
    <h3>💬 История касаний ({len(notes_list)})</h3>
    <span style="font-size:.75rem;color:var(--text3)">{last_contact_str}</span>
  </div>
  <div class="section-body">
    <!-- Форма добавления -->
    <div style="background:var(--bg3);border-radius:10px;padding:14px;margin-bottom:16px">
      <div style="display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap">
        <button type="button" onclick="setNoteType('note',this)" class="note-type-btn active-type" data-type="note" style="padding:4px 12px;border-radius:20px;font-size:.78rem;border:1px solid #6366f1;background:#1a1a3a;color:#818cf8;cursor:pointer">📝 Заметка</button>
        <button type="button" onclick="setNoteType('call',this)" class="note-type-btn" data-type="call" style="padding:4px 12px;border-radius:20px;font-size:.78rem;border:1px solid var(--border);background:transparent;color:var(--text3);cursor:pointer">📞 Звонок</button>
        <button type="button" onclick="setNoteType('message',this)" class="note-type-btn" data-type="message" style="padding:4px 12px;border-radius:20px;font-size:.78rem;border:1px solid var(--border);background:transparent;color:var(--text3);cursor:pointer">💬 Написали</button>
        <button type="button" onclick="setNoteType('meet',this)" class="note-type-btn" data-type="meet" style="padding:4px 12px;border-radius:20px;font-size:.78rem;border:1px solid var(--border);background:transparent;color:var(--text3);cursor:pointer">📅 Встреча</button>
      </div>
      <div style="display:flex;gap:8px;align-items:flex-start">
        <textarea id="note-text-{s['id']}" rows="2" placeholder="Написал в WA, ответил что подумает..." style="flex:1;background:var(--bg);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:.84rem;padding:8px 10px;resize:vertical"></textarea>
        <div style="display:flex;flex-direction:column;gap:6px;flex-shrink:0">
          <button type="button" onclick="addStaffNote({s['id']})" class="btn-orange btn-sm">Добавить</button>
          <div style="font-size:.7rem;color:var(--text3);text-align:center">⏰ напомнить</div>
          <input type="date" id="note-remind-{s['id']}" style="background:var(--bg);border:1px solid var(--border);border-radius:6px;color:var(--text3);font-size:.72rem;padding:3px 6px"/>
        </div>
      </div>
    </div>
    <!-- Таймлайн -->
    <div id="notes-timeline-{s['id']}">
      {notes_timeline_html}
    </div>
  </div>
</div>
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
function quickStatusChange(id, status) {{
  fetch('/staff/quick_status', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{id: id, status: status}})
  }}).then(r => r.json()).then(d => {{
    if (!d.ok) alert('Ошибка смены статуса');
  }});
}}
var _activeNoteType = 'note';
function setNoteType(type, btn) {{
  _activeNoteType = type;
  document.querySelectorAll('.note-type-btn').forEach(function(b) {{
    b.style.borderColor = 'var(--border)';
    b.style.background = 'transparent';
    b.style.color = 'var(--text3)';
  }});
  var colors = {{note:'#6366f1',call:'#5aaddd',message:'#5cc87a',meet:'#bb77ee'}};
  var bgs = {{note:'#1a1a3a',call:'#1a2a3a',message:'#1a2a35',meet:'#2a1a3a'}};
  btn.style.borderColor = colors[type] || '#6366f1';
  btn.style.background = bgs[type] || '#1a1a3a';
  btn.style.color = colors[type] || '#818cf8';
}}
async function addStaffNote(staffId) {{
  var text = document.getElementById('note-text-' + staffId);
  var remind = document.getElementById('note-remind-' + staffId);
  if (!text || !text.value.trim()) {{ alert('Введите текст заметки'); return; }}
  var payload = {{staff_id: staffId, type: _activeNoteType, text: text.value.trim(), remind_at: remind ? remind.value : ''}};
  try {{
    var r = await fetch('/staff/notes/add', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify(payload)}});
    var d = await r.json();
    if (d.ok) {{
      text.value = '';
      if (remind) remind.value = '';
      window.location.reload();
    }} else {{ alert('Ошибка: ' + (d.error || 'неизвестно')); }}
  }} catch(e) {{ alert('Ошибка соединения'); }}
}}
async function deleteStaffNote(noteId, staffId) {{
  if (!confirm('Удалить эту запись?')) return;
  var r = await fetch('/staff/notes/delete', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{note_id: noteId, staff_id: staffId}})}});
  var d = await r.json();
  if (d.ok) window.location.reload();
  else alert('Ошибка удаления');
}}
</script>"""

    def _status_opts_for(current):
        opts = ""
        for k, (ico, lbl, _) in STAFF_STATUSES.items():
            sel = "selected" if k == current else ""
            opts += f'<option value="{k}" {sel}>{ico} {lbl}</option>'
        return opts

    # Напоминания
    reminders = db.get_staff_reminders_due()
    reminders_html = ""
    if reminders:
        rem_items = ""
        for r in reminders:
            _overdue = r.get('remind_at','') < __import__('datetime').date.today().isoformat()
            _col = "#f97316" if _overdue else "#5aaddd"
            rem_items += (
                f'<a href="/staff/{r["staff_id"]}" target="_blank" style="text-decoration:none;display:flex;align-items:center;gap:10px;padding:8px 12px;background:var(--bg3);border:1px solid var(--border);border-radius:8px;margin-bottom:6px">'
                f'<span style="font-size:1.1rem">⏰</span>'
                f'<div style="flex:1"><div style="font-size:.85rem;font-weight:600;color:{_col}">{r.get("staff_name","?")}</div>'
                f'<div style="font-size:.75rem;color:var(--text3)">{r.get("text","")[:80]}</div></div>'
                f'<div style="font-size:.72rem;color:{_col};flex-shrink:0">{r.get("remind_at","")}</div>'
                f'</a>'
            )
        reminders_html = (
            f'<div class="section" style="margin-bottom:16px;border-left:3px solid #f97316">'
            f'<div class="section-head"><h3>⏰ Напоминания сегодня ({len(reminders)})</h3></div>'
            f'<div class="section-body">{rem_items}</div></div>'
        )

    cards = ""
    for s in staff_list:
        icon, label, badge_cls = STAFF_STATUSES.get(s.get("status","new"), ("🆕","Новый","badge-gray"))
        _sid   = s['id']
        _photo = s.get("photo_url") or ""
        _name  = s.get('name') or '—'
        _city  = s.get('city') or '—'
        _date  = (s.get('created_at') or '')[:10]
        _tg    = s.get('phone') or ''
        _wa    = s.get('email') or ''

        # Главное фото
        if _photo:
            photo_block = f'<img src="{_photo}" style="width:100%;height:100%;object-fit:cover;display:block" loading="lazy" />'
        else:
            initials = ''.join(w[0].upper() for w in _name.split()[:2]) if _name != '—' else '?'
            photo_block = f'<div style="width:100%;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;background:var(--bg3)"><div style="width:64px;height:64px;border-radius:50%;background:#1d3050;display:flex;align-items:center;justify-content:center;font-size:22px;font-weight:500;color:#5aaddd">{initials}</div><span style="font-size:11px;color:var(--text3)">Нет фото</span></div>'

        # Галерея (миниатюры под фото)
        gallery_items = db.get_staff_gallery(_sid)
        gallery_block = ""
        if gallery_items:
            thumbs = ""
            for gi in gallery_items[:3]:
                thumbs += f'<div style="width:38px;height:38px;border-radius:5px;overflow:hidden;border:1px solid var(--border);flex-shrink:0;cursor:pointer" onclick="openGalleryLightbox(\'{gi["photo_url"]}\',{gi["id"]})"><img src="{gi["photo_url"]}" style="width:100%;height:100%;object-fit:cover" loading="lazy"/></div>'
            extra = len(gallery_items) - 3
            if extra > 0:
                thumbs += f'<div style="width:38px;height:38px;border-radius:5px;background:var(--bg3);border:1px solid var(--border);display:flex;align-items:center;justify-content:center;font-size:11px;color:var(--text3);flex-shrink:0">+{extra}</div>'
            gallery_block = f'<div style="display:flex;gap:5px;padding:6px 8px;background:var(--bg2,var(--bg3));border-bottom:1px solid var(--border)">{thumbs}</div>'

        # Контакт
        if _tg:
            contact_html = f'<span style="color:#5aaddd;font-size:12px">💬 {_tg}</span>'
        elif _wa:
            contact_html = f'<span style="color:#86efac;font-size:12px">💚 {_wa}</span>'
        else:
            contact_html = '<span style="color:var(--text3);font-size:12px">— нет контакта</span>'

        # Быстрая смена статуса
        status_select = f'<select onchange="quickStatusChange({_sid}, this.value, this)" style="background:var(--bg3);border:1px solid var(--border);border-radius:6px;padding:2px 6px;color:var(--text);font-size:11px;cursor:pointer;width:100%">{_status_opts_for(s.get("status","new"))}</select>'

        # Кнопка чата
        chat_btn = ""
        if s.get("conversation_id"):
            chat_btn = f'<a href="/chat?conv_id={s["conversation_id"]}" style="text-decoration:none"><button class="btn-gray btn-sm" style="font-size:11px;padding:3px 7px">💬</button></a>'
        elif s.get("wa_conv_id"):
            chat_btn = f'<a href="/wa/chat?conv_id={s["wa_conv_id"]}" style="text-decoration:none"><button class="btn-gray btn-sm" style="font-size:11px;padding:3px 7px;color:#86efac;border-color:#166534">💚</button></a>'

        # Кнопка удаления (только admin)
        del_btn = ""
        if user and user.get("role") == "admin":
            del_btn = f'<form method="post" action="/staff/delete" style="display:inline;margin:0"><input type="hidden" name="staff_id" value="{_sid}"/><button class="btn-gray btn-sm" style="font-size:11px;padding:3px 7px;color:var(--red);border-color:#7f1d1d" onclick="return confirm(\'Удалить сотрудника полностью?\')">🗑</button></form>'

        cards += f"""<div style="background:var(--bg2,#23262f);border:1px solid var(--border);border-radius:12px;overflow:hidden;display:flex;flex-direction:column">
          <div style="position:relative;width:100%;aspect-ratio:3/4;overflow:hidden;background:var(--bg3)">
            {photo_block}
          </div>
          {gallery_block}
          <div style="padding:10px 12px 12px;display:flex;flex-direction:column;gap:5px;flex:1">
            <div style="font-size:14px;font-weight:500;color:var(--text)">{_name}</div>
            <div style="font-size:11px;color:var(--text3)">📅 {_date}</div>
            <div style="font-size:11px;color:#69c9d0">📍 {_city}</div>
            <div style="margin:2px 0">{status_select}</div>
            <div style="margin-top:2px">{contact_html}</div>
            <div style="border-top:1px solid var(--border);margin-top:6px;padding-top:8px;display:flex;gap:5px;justify-content:flex-end;flex-wrap:wrap;align-items:center">
              {chat_btn}
              <a href="/staff/{_sid}" target="_blank" style="text-decoration:none"><button class="btn-orange btn-sm" style="font-size:11px;padding:3px 7px">✏️ Открыть</button></a>
              {del_btn}
            </div>
          </div>
        </div>"""

    if not cards:
        cards = '<div class="empty" style="grid-column:1/-1">Нет сотрудников</div>'

    _qs_js = """<script>
function quickStatusChange(id, status, selectEl) {
  if (selectEl) { selectEl.disabled = true; selectEl.style.opacity = '0.6'; }
  fetch('/staff/quick_status', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({id: id, status: status})
  }).then(function(r) { return r.json(); }).then(function(d) {
    if (selectEl) { selectEl.disabled = false; selectEl.style.opacity = '1'; }
    if (d.ok) {
      if (selectEl) {
        selectEl.style.outline = '2px solid #22c55e';
        setTimeout(function() { selectEl.style.outline = ''; }, 1200);
      }
    } else {
      alert('Ошибка смены статуса');
      if (selectEl) location.reload();
    }
  }).catch(function() {
    if (selectEl) { selectEl.disabled = false; selectEl.style.opacity = '1'; }
    alert('Ошибка соединения');
  });
}
</script>"""

    content = (
        f'<div class="page-wrap">'
        f'<div class="page-title">🗂 База сотрудников</div>'
        f'<div class="page-sub">Все кто написал боту</div>'
        f'{alert}'
        f'{_action_btns}'
        f'{_date_filter_html}'
        f'{search_bar}'
        f'<div style="margin-bottom:16px">{filter_btns}</div>'
        f'{reminders_html}'
        f'{edit_form}'
        f'<div class="section">'
        f'<div class="section-head"><h3>📋 Сотрудники ({len(staff_list)})</h3></div>'
        f'<div class="section-body" style="padding:16px">'
        f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px">'
        f'{cards}'
        f'</div></div></div></div>'
        f'{_qs_js}'
    )
    return HTMLResponse(base(content, "staff", request))


@router.post("/staff/update")
async def staff_update(request: Request, staff_id: int = Form(...), name: str = Form(""),
                        phone: str = Form(""), email: str = Form(""), position: str = Form(""),
                        status: str = Form("new"), notes: str = Form(""), tags: str = Form(""),
                        manager_name: str = Form(""), city: str = Form(""),
                        created_at_manual: str = Form(""),
                        staff_photo: UploadFile = File(None)):
    user, err = require_auth(request)
    if err: return err
    db.update_staff(staff_id, name, phone, email, position, status, notes, tags,
                    manager_name=manager_name.strip(), city=city.strip())
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
    return RedirectResponse(f"/staff/{staff_id}?msg=Сохранено", 303)


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

    import datetime as _dt
    _today = _dt.datetime.utcnow().strftime('%Y-%m-%d')
    content = (
        '<div class="page-wrap">'
        '<div class="page-title">➕ Добавить сотрудника вручную</div>'
        '<div class="page-sub"><a href="/staff" style="color:var(--text3)">← База</a></div>'
        + alert +
        '<div class="section"><div class="section-head"><h3>Новая карточка</h3></div>'
        '<div class="section-body">'
        '<form method="post" action="/staff/create_manual" enctype="multipart/form-data">'

        '<div style="margin-bottom:16px">'
        '<div class="field-label" style="margin-bottom:6px">Главное фото</div>'
        '<input type="file" name="staff_photo" accept="image/*" style="font-size:.82rem;color:var(--text3)"/>'
        '<div style="font-size:.72rem;color:var(--text3);margin-top:4px">JPG, PNG до 5MB</div>'
        '</div>'

        '<div class="grid-3" style="margin-bottom:12px">'
        '<div class="field-group"><div class="field-label">Имя *</div>'
        '<input type="text" name="name" required placeholder="Анна Иванова"/></div>'

        '<div class="field-group"><div class="field-label">Telegram</div>'
        '<input type="text" name="phone" placeholder="@username или +номер"/></div>'

        '<div class="field-group"><div class="field-label">WhatsApp</div>'
        '<input type="text" name="email" placeholder="+1234567890"/></div>'

        '<div class="field-group"><div class="field-label">Должность</div>'
        '<input type="text" name="position" placeholder="Массажистка"/></div>'

        '<div class="field-group"><div class="field-label">Статус</div>'
        '<select name="status">' + status_opts + '</select></div>'
        '</div>'

        '<div class="field-group" style="margin-bottom:12px">'
        '<div class="field-label">Заметки</div>'
        '<textarea name="notes" rows="3" placeholder="Дополнительная информация..."></textarea>'
        '</div>'

        '<div class="field-group" style="margin-bottom:12px">'
        '<div class="field-label">👤 Закреплён за менеджером</div>'
        '<select name="manager_name" style="width:100%;padding:7px 10px;background:var(--bg3);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:.84rem">'
        + manager_opts +
        '</select></div>'

        '<div class="field-group" style="margin-bottom:12px">'
        '<div class="field-label">📍 Город размещения</div>'
        '<input type="text" name="city" placeholder="Los Angeles, Chicago..."/>'
        '</div>'

        '<div class="field-group" style="margin-bottom:12px">'
        '<div class="field-label">📅 Дата добавления анкеты</div>'
        '<input type="date" name="created_at_manual" value="' + _today + '"/>'
        '<span style="font-size:.72rem;color:var(--text3)">Измени если анкета поступила вне CRM</span>'
        '</div>'

        '<div style="display:flex;gap:8px;margin-top:16px">'
        '<button class="btn-orange">💾 Создать карточку</button>'
        '<a href="/staff"><button type="button" class="btn-gray">Отмена</button></a>'
        '</div>'
        '</form></div></div></div>'
    )

    return HTMLResponse(base(content, "staff", request))


@router.post("/staff/create_manual")
async def staff_create_manual(request: Request,
                               name: str = Form(...),
                               phone: str = Form(""), email: str = Form(""),
                               position: str = Form(""), status: str = Form("new"),
                               notes: str = Form(""), tags: str = Form(""),
                               manager_name: str = Form(""),
                               city: str = Form(""),
                               created_at_manual: str = Form(""),
                               staff_photo: UploadFile = File(None)):
    user, err = require_auth(request)
    if err: return err

    staff_id = db.create_staff_manual(
        name=name, phone=phone, email=email, position=position,
        status=status, notes=notes, tags=tags,
        username="", manager_name=manager_name,
        city=city.strip(),
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
            rate  = data["rate"]
            count = data["count"]
            rows_s += f"""<tr>
              <td style="padding:8px">{icon} {label or st}</td>
              <td style="text-align:center;font-weight:700;padding:8px">{count}</td>
              <td style="text-align:center;color:var(--text3);padding:8px">${rate:.2f}</td>
              <td style="text-align:center;color:#86efac;font-weight:700;padding:8px">${rate * count:.2f}</td>
            </tr>"""
        # Ставка менеджера — одна на все анкеты
        _flat_rate    = rates.get("__manager__", {}).get("rate", 0)
        _flat_amount  = _flat_rate * summary["total_count"]
        _grand_total  = summary["total_amount"] + _flat_amount

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
              <tfoot>
                <tr style="border-top:1px solid var(--border)">
                  <td colspan="3" style="padding:8px;color:#69c9d0">Ставка менеджера × {summary["total_count"]} анкет (${_flat_rate:.2f} × {summary["total_count"]})</td>
                  <td style="text-align:center;padding:8px;color:#69c9d0;font-weight:700">${_flat_amount:.2f}</td>
                </tr>
                <tr style="border-top:2px solid var(--border)">
                  <td style="padding:10px 8px;font-weight:700">ИТОГО</td>
                  <td style="text-align:center;padding:10px 8px;font-weight:700">{summary["total_count"]}</td>
                  <td></td>
                  <td style="text-align:center;padding:10px 8px;font-weight:700;color:#86efac;font-size:1.1rem">${_grand_total:.2f}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>"""

    # Форма ставок
    _flat_rate_val = rates.get("__manager__", {}).get("rate", 0)
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
          <tfoot>
            <tr style="border-top:2px solid var(--border)">
              <td style="padding:12px 8px;font-weight:600;color:#69c9d0">Ставка менеджера (за все анкеты)</td>
              <td style="padding:12px 8px">
                <div style="display:flex;align-items:center;gap:6px">
                  <span style="color:var(--text3)">$</span>
                  <input type="number" name="manager_flat_rate" value="{_flat_rate_val:.2f}"
                         min="0" step="0.5"
                         style="width:100px;background:var(--bg);border:1px solid #2a4060;border-radius:6px;padding:6px 10px;color:#69c9d0;font-size:.85rem"/>
                </div>
              </td>
            </tr>
          </tfoot>
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
    # Отдельная ставка менеджера (одна на все анкеты)
    try:
        flat = float(form.get("manager_flat_rate", 0))
        db.set_bonus_rate("__manager__", flat, "Ставка менеджера")
    except: pass
    return RedirectResponse("/staff/bonuses?msg=Ставки+сохранены", 303)


# ─── КАРТОЧКА СОТРУДНИКА (отдельная страница) ────────────────────────────────

@router.get("/staff/{staff_id}", response_class=HTMLResponse)
async def staff_card_page(request: Request, staff_id: int, msg: str = ""):
    user, err = require_auth(request)
    if err: return err

    s = db.get_staff_by_id(staff_id)
    if not s:
        return RedirectResponse("/staff", 303)

    alert = f'<div class="alert-green">✅ {msg}</div>' if msg else ""

    notes_list    = db.get_staff_notes(staff_id)
    gallery_items = db.get_staff_gallery(staff_id)
    _days_ago     = db.get_staff_no_contact_days(staff_id)
    import datetime as _dt2
    _total_days = 0
    try:
        _added = _dt2.datetime.fromisoformat((s.get("created_at") or "")[:19])
        _total_days = (_dt2.datetime.utcnow() - _added).days
    except Exception:
        pass
    if _days_ago < 0:    last_contact_str = "касаний нет"
    elif _days_ago == 0: last_contact_str = "сегодня"
    elif _days_ago == 1: last_contact_str = "вчера"
    else:                last_contact_str = f"{_days_ago} дн. назад"

    _photo = s.get("photo_url") or ""
    if _photo:
        photo_html = f'<img src="{_photo}" style="width:100%;height:100%;object-fit:cover;display:block"/>'
    else:
        initials = "".join(w[0].upper() for w in (s.get("name") or "?").split()[:2])
        photo_html = f'<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:42px;font-weight:500;color:#5aaddd">{initials}</div>'

    gallery_mini = ""
    for gi in gallery_items[:5]:
        gallery_mini += (
            f'<div onclick="openLightbox(\'{gi["photo_url"]}\')" '
            f'style="width:48px;height:48px;border-radius:6px;overflow:hidden;border:1px solid #2e3240;cursor:pointer;flex-shrink:0">'
            f'<img src="{gi["photo_url"]}" style="width:100%;height:100%;object-fit:cover" loading="lazy"/></div>'
        )
    if len(gallery_items) > 5:
        gallery_mini += f'<div style="width:48px;height:48px;border-radius:6px;background:#1e2130;border:1px solid #2e3240;display:flex;align-items:center;justify-content:center;font-size:12px;color:#666">+{len(gallery_items)-5}</div>'

    _tg = s.get("phone") or ""
    _wa = s.get("email") or ""
    tg_html = f'<span style="color:#5aaddd">{_tg}</span>' if _tg else '<span style="color:#444">—</span>'
    wa_html = f'<span style="color:#5cc87a">{_wa}</span>' if _wa else '<span style="color:#444">—</span>'

    chat_btn = ""
    if s.get("conversation_id"):
        chat_btn = f'<a href="/chat?conv_id={s["conversation_id"]}" style="text-decoration:none"><button style="padding:5px 12px;border-radius:7px;background:#1a2535;border:1px solid #2a4060;color:#5aaddd;font-size:12px;cursor:pointer">💬 TG чат</button></a>'
    elif s.get("wa_conv_id"):
        chat_btn = f'<a href="/wa/chat?conv_id={s["wa_conv_id"]}" style="text-decoration:none"><button style="padding:5px 12px;border-radius:7px;background:#1a3a22;border:1px solid #2a5a35;color:#5cc87a;font-size:12px;cursor:pointer">💚 WA чат</button></a>'

    status_opts_html = ""
    for k, (ico, lbl, _) in STAFF_STATUSES.items():
        sel = "selected" if k == s.get("status", "new") else ""
        status_opts_html += f'<option value="{k}" {sel}>{ico} {lbl}</option>'

    manager_opts_html = '<option value="">— не закреплён —</option>'
    for u in db.get_users():
        _un = u.get("display_name") or u["username"]
        sel = "selected" if s.get("manager_name") == _un else ""
        manager_opts_html += f'<option value="{_un}" {sel}>{_un} ({u["role"]})</option>'

    next_remind = next((n for n in reversed(notes_list) if n.get("remind_at")), None)
    remind_badge = ""
    if next_remind:
        remind_badge = (
            f'<div style="background:#2a1a0a;border:1px solid #f97316;border-radius:7px;padding:8px 12px;display:flex;align-items:center;gap:8px">'
            f'<span>⏰</span><div>'
            f'<div style="font-size:11px;font-weight:500;color:#f97316">Следующий контакт</div>'
            f'<div style="font-size:12px;color:#ddd;margin-top:1px">{next_remind["remind_at"]}</div>'
            f'</div></div>'
        )

    _note_meta = {
        "note":    ("#1a1a2e","#9a8aee","📝","заметка"),
        "call":    ("#1a2a3a","#5aaddd","📞","звонок"),
        "message": ("#1a2a35","#5cc87a","💬","написали"),
        "meet":    ("#2a1a3a","#bb77ee","📅","встреча"),
        "status":  ("#2a1a0a","#f97316","🔄","статус"),
    }
    timeline_html = ""
    for i, n in enumerate(notes_list):
        _nt2 = n.get("type", "note")
        _bg, _col, _ico, _lbl = _note_meta.get(_nt2, ("#1a1a2e","#9a8aee","📝","заметка"))
        _ndate = (n.get("created_at") or "")[:16].replace("T", " ")
        _rem_span = f'<span style="font-size:.7rem;color:#f97316;margin-left:4px">⏰ {n["remind_at"]}</span>' if n.get("remind_at") else ""
        _is_last = (i == len(notes_list) - 1)
        _line = "" if _is_last else '<div style="width:1px;background:#2e3240;flex:1;margin-top:4px;min-height:16px"></div>'
        timeline_html += (
            f'<div style="display:flex;gap:10px;padding:10px 0;border-bottom:{"none" if _is_last else "1px solid #1e2130"}">'
            f'<div style="display:flex;flex-direction:column;align-items:center;padding-top:2px">'
            f'<div style="width:28px;height:28px;border-radius:50%;background:{_bg};display:flex;align-items:center;justify-content:center;font-size:13px;flex-shrink:0">{_ico}</div>'
            f'{_line}</div>'
            f'<div style="flex:1">'
            f'<div style="display:flex;align-items:center;gap:7px;margin-bottom:4px;flex-wrap:wrap">'
            f'<span style="font-size:.8rem;font-weight:600;color:#ddd">{n.get("manager_name") or "—"}</span>'
            f'<span style="font-size:.72rem;color:#555">{_ndate}</span>'
            f'<span style="font-size:.7rem;padding:1px 7px;border-radius:20px;background:{_bg};color:{_col}">{_lbl}</span>'
            f'{_rem_span}'
            f'<button type="button" onclick="deleteNote({n["id"]},{staff_id})" style="margin-left:auto;background:transparent;border:none;color:#444;font-size:.72rem;cursor:pointer;padding:0 4px">✕</button>'
            f'</div>'
            f'<div style="font-size:.82rem;color:#aaa;line-height:1.5">{n.get("text") or ""}</div>'
            f'</div></div>'
        )
    if not timeline_html:
        timeline_html = '<div style="color:#444;font-size:.82rem;padding:8px 0">Пока нет касаний — добавьте первую заметку</div>'

    del_btn_html = ""
    if user and user.get("role") == "admin":
        del_btn_html = (
            f'<form method="post" action="/staff/delete" style="display:inline;margin:0">'
            f'<input type="hidden" name="staff_id" value="{staff_id}"/>'
            f'<button onclick="return confirm(\'Удалить сотрудника полностью?\')" '
            f'style="padding:5px 12px;border-radius:7px;background:transparent;border:1px solid #7f1d1d;color:#f87171;font-size:12px;cursor:pointer">🗑 Удалить</button>'
            f'</form>'
        )

    gallery_grid_html = ""
    for gi in gallery_items:
        gallery_grid_html += (
            f'<div style="position:relative;width:80px;height:80px;border-radius:7px;overflow:hidden;cursor:pointer" onclick="openLightbox(\'{gi["photo_url"]}\')" >'
            f'<img src="{gi["photo_url"]}" style="width:100%;height:100%;object-fit:cover"/>'
            f'<button onclick="event.stopPropagation();delGallery({gi["id"]},{staff_id})" style="position:absolute;top:2px;right:2px;width:18px;height:18px;border-radius:50%;background:rgba(0,0,0,.7);border:none;color:#fff;font-size:10px;cursor:pointer;display:flex;align-items:center;justify-content:center">✕</button></div>'
        )
    if not gallery_grid_html:
        gallery_grid_html = '<span style="color:#444;font-size:.82rem">Нет фото в галерее</span>'

    gallery_row = ""
    if gallery_items:
        gallery_row = f'<div style="display:flex;gap:6px;flex-wrap:wrap">{gallery_mini}</div>'

    css = (
        ".sc-page{background:#16181f;padding:16px}"
        ".sc-layout{display:grid;grid-template-columns:240px 1fr;gap:16px;max-width:1200px}"
        ".sc-left{display:flex;flex-direction:column;gap:12px}"
        ".sc-photo{width:100%;aspect-ratio:3/4;border-radius:10px;background:#1a2535;overflow:hidden}"
        ".sc-info{background:#1e2130;border:1px solid #2e3240;border-radius:10px;padding:12px}"
        ".sc-irow{display:flex;align-items:flex-start;gap:8px;margin-bottom:8px;font-size:12px}"
        ".sc-irow:last-child{margin-bottom:0}"
        ".sc-ilabel{color:#666;min-width:54px;flex-shrink:0}"
        ".sc-stats{display:flex;gap:8px}"
        ".sc-stat{flex:1;background:#13151c;border-radius:8px;padding:8px 10px;text-align:center}"
        ".sc-stat-n{font-size:18px;font-weight:500;color:#ddd}"
        ".sc-stat-l{font-size:11px;color:#555;margin-top:2px}"
        ".sc-right{display:flex;flex-direction:column;gap:12px}"
        ".sc-section{background:#1e2130;border:1px solid #2e3240;border-radius:10px}"
        ".sc-sh{padding:10px 14px;border-bottom:1px solid #2e3240;font-size:13px;font-weight:500;color:#ddd;display:flex;align-items:center;justify-content:space-between}"
        ".sc-sb{padding:12px 14px}"
        ".sc-inp{width:100%;background:#13151c;border:1px solid #2e3240;border-radius:7px;color:#ccc;font-size:.84rem;padding:6px 10px}"
        ".sc-inp:focus{outline:none;border-color:#f97316}"
        ".sc-sel{width:100%;background:#13151c;border:1px solid #2e3240;border-radius:7px;color:#ccc;font-size:.84rem;padding:6px 10px;cursor:pointer}"
        ".sc-ta{width:100%;background:#13151c;border:1px solid #2e3240;border-radius:7px;color:#ccc;font-size:.84rem;padding:8px 10px;resize:vertical;min-height:60px}"
        ".nt-btn{padding:3px 10px;border-radius:20px;font-size:.75rem;border:1px solid #2e3240;background:transparent;color:#666;cursor:pointer}"
    )

    name_val = (s.get("name") or "").replace('"', '&quot;')
    phone_val = (s.get("phone") or "").replace('"', '&quot;')
    email_val = (s.get("email") or "").replace('"', '&quot;')
    pos_val = (s.get("position") or "").replace('"', '&quot;')
    city_val = (s.get("city") or "").replace('"', '&quot;')
    date_val = (s.get("created_at") or "")[:10]
    notes_val = (s.get("notes") or "")

    content = (
        f'<style>{css}</style>'
        f'<div class="sc-page">'
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">'
        f'<a href="/staff" style="font-size:12px;color:#666;text-decoration:none">← База</a>'
        f'<span style="color:#333">/</span>'
        f'<span style="font-size:13px;color:#ddd">{s.get("name","—")}</span>'
        f'<span style="margin-left:auto;font-size:11px;color:#555">последнее касание: {last_contact_str}</span>'
        f'</div>{alert}'
        f'<div class="sc-layout">'
        f'<div class="sc-left">'
        f'<div class="sc-photo">{photo_html}</div>'
        f'{gallery_row}'
        f'<div class="sc-info">'
        f'<div class="sc-irow"><span class="sc-ilabel">Статус</span>'
        f'<select onchange="quickSave({staff_id},this.value,this)" style="background:#1e2130;border:1px solid #2e3240;border-radius:6px;color:#ccc;font-size:11px;padding:2px 6px;cursor:pointer">{status_opts_html}</select></div>'
        f'<div class="sc-irow"><span class="sc-ilabel">Город</span><span style="color:#69c9d0">{s.get("city") or "—"}</span></div>'
        f'<div class="sc-irow"><span class="sc-ilabel">TG</span>{tg_html}</div>'
        f'<div class="sc-irow"><span class="sc-ilabel">WA</span>{wa_html}</div>'
        f'<div class="sc-irow"><span class="sc-ilabel">Менеджер</span><span style="color:#f97316">{s.get("manager_name") or "—"}</span></div>'
        f'<div class="sc-irow"><span class="sc-ilabel">Добавлен</span><span style="color:#888">{date_val}</span></div>'
        f'</div>'
        f'<div class="sc-stats">'
        f'<div class="sc-stat"><div class="sc-stat-n">{len(notes_list)}</div><div class="sc-stat-l">касаний</div></div>'
        f'<div class="sc-stat"><div class="sc-stat-n">{_total_days}</div><div class="sc-stat-l">дней</div></div>'
        f'<div class="sc-stat"><div class="sc-stat-n">{"—" if _days_ago < 0 else _days_ago}</div><div class="sc-stat-l">дн. назад</div></div>'
        f'</div>{remind_badge}'
        f'<div style="display:flex;gap:6px;flex-wrap:wrap">{chat_btn}{del_btn_html}</div>'
        f'</div>'
        f'<div class="sc-right">'
        f'<div class="sc-section">'
        f'<div class="sc-sh"><span>💬 История касаний</span><span style="font-size:11px;color:#555">{len(notes_list)} записей</span></div>'
        f'<div class="sc-sb">'
        f'<div style="margin-bottom:12px">'
        f'<div style="display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap">'
        f'<button type="button" class="nt-btn" style="border-color:#818cf8;background:#1a1a3a;color:#818cf8" onclick="setNT(\'note\',this)">📝 Заметка</button>'
        f'<button type="button" class="nt-btn" onclick="setNT(\'call\',this)">📞 Звонок</button>'
        f'<button type="button" class="nt-btn" onclick="setNT(\'message\',this)">💬 Написали</button>'
        f'<button type="button" class="nt-btn" onclick="setNT(\'meet\',this)">📅 Встреча</button>'
        f'</div>'
        f'<div style="display:flex;gap:8px;align-items:flex-start">'
        f'<textarea id="nt-text" class="sc-ta" placeholder="Написал в WA, ответила что думает..."></textarea>'
        f'<div style="display:flex;flex-direction:column;gap:6px;flex-shrink:0">'
        f'<button type="button" onclick="addNote({staff_id})" style="padding:6px 14px;border-radius:7px;background:#f97316;border:none;color:#fff;font-size:12px;font-weight:500;cursor:pointer">Добавить</button>'
        f'<div style="font-size:10px;color:#444;text-align:center">⏰ напомнить</div>'
        f'<input type="date" id="nt-remind" style="background:#13151c;border:1px solid #2e3240;border-radius:6px;color:#888;font-size:10px;padding:3px 6px"/>'
        f'</div></div></div>'
        f'<div id="timeline">{timeline_html}</div>'
        f'</div></div>'
        f'<div class="sc-section">'
        f'<div class="sc-sh"><span>✏️ Редактировать карточку</span></div>'
        f'<div class="sc-sb">'
        f'<form method="post" action="/staff/update" enctype="multipart/form-data">'
        f'<input type="hidden" name="staff_id" value="{staff_id}"/>'
        f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:10px">'
        f'<div><div style="font-size:.72rem;color:#555;margin-bottom:4px;text-transform:uppercase">Имя</div><input class="sc-inp" type="text" name="name" value="{name_val}"/></div>'
        f'<div><div style="font-size:.72rem;color:#555;margin-bottom:4px;text-transform:uppercase">Telegram</div><input class="sc-inp" type="text" name="phone" value="{phone_val}"/></div>'
        f'<div><div style="font-size:.72rem;color:#555;margin-bottom:4px;text-transform:uppercase">WhatsApp</div><input class="sc-inp" type="text" name="email" value="{email_val}"/></div>'
        f'<div><div style="font-size:.72rem;color:#555;margin-bottom:4px;text-transform:uppercase">Должность</div><input class="sc-inp" type="text" name="position" value="{pos_val}"/></div>'
        f'<div><div style="font-size:.72rem;color:#555;margin-bottom:4px;text-transform:uppercase">Статус</div><select class="sc-sel" name="status">{status_opts_html}</select></div>'
        f'<div><div style="font-size:.72rem;color:#555;margin-bottom:4px;text-transform:uppercase">Менеджер</div><select class="sc-sel" name="manager_name">{manager_opts_html}</select></div>'
        f'<div><div style="font-size:.72rem;color:#555;margin-bottom:4px;text-transform:uppercase">Город</div><input class="sc-inp" type="text" name="city" value="{city_val}"/></div>'
        f'<div><div style="font-size:.72rem;color:#555;margin-bottom:4px;text-transform:uppercase">Дата анкеты</div><input class="sc-inp" type="date" name="created_at_manual" value="{date_val}"/></div>'
        f'</div>'
        f'<div style="margin-bottom:10px"><div style="font-size:.72rem;color:#555;margin-bottom:4px;text-transform:uppercase">Заметки</div><textarea class="sc-ta" name="notes">{notes_val}</textarea></div>'
        f'<div style="margin-bottom:10px"><div style="font-size:.72rem;color:#555;margin-bottom:4px;text-transform:uppercase">Главное фото</div><input type="file" name="staff_photo" accept="image/*" style="font-size:.82rem;color:#666"/></div>'
        f'<button type="submit" style="padding:7px 18px;border-radius:7px;background:#f97316;border:none;color:#fff;font-size:13px;font-weight:500;cursor:pointer">💾 Сохранить</button>'
        f'</form></div></div>'
        f'<div class="sc-section">'
        f'<div class="sc-sh"><span>🖼 Галерея ({len(gallery_items)})</span>'
        f'<label style="font-size:.78rem;color:#888;cursor:pointer;padding:3px 10px;border:1px solid #2e3240;border-radius:6px">'
        f'➕ Добавить<input type="file" accept="image/*" multiple style="display:none" onchange="uploadGallery(this,{staff_id})"/>'
        f'</label></div>'
        f'<div class="sc-sb"><div style="display:flex;gap:8px;flex-wrap:wrap">{gallery_grid_html}</div></div>'
        f'</div></div></div></div>'
        f'<div id="lightbox" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.9);z-index:9999;align-items:center;justify-content:center">'
        f'<button onclick="document.getElementById(\'lightbox\').style.display=\'none\'" style="position:absolute;top:16px;right:20px;background:rgba(255,255,255,.1);border:none;color:#fff;font-size:1.4rem;width:36px;height:36px;border-radius:50%;cursor:pointer">✕</button>'
        f'<img id="lb-img" style="max-width:90vw;max-height:90vh;border-radius:8px"/>'
        f'</div>'
        f'<script>'
        f'var _nt="note";'
        f'var _ntC={{note:["#818cf8","#1a1a3a"],call:["#5aaddd","#1a2a3a"],message:["#5cc87a","#1a2a35"],meet:["#bb77ee","#2a1a3a"]}};'
        f'function setNT(t,btn){{_nt=t;document.querySelectorAll(".nt-btn").forEach(function(b){{b.style.borderColor="#2e3240";b.style.background="transparent";b.style.color="#666"}});var c=_ntC[t]||_ntC.note;btn.style.borderColor=c[0];btn.style.background=c[1];btn.style.color=c[0];}}'
        f'async function addNote(sid){{var t=document.getElementById("nt-text"),r=document.getElementById("nt-remind");if(!t||!t.value.trim()){{alert("Введите текст");return;}}var res=await fetch("/staff/notes/add",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{staff_id:sid,type:_nt,text:t.value.trim(),remind_at:r?r.value:""}}) }});var d=await res.json();if(d.ok){{t.value="";if(r)r.value="";location.reload();}}else alert("Ошибка:"+(d.error||"?"));}}'
        f'async function deleteNote(nid,sid){{if(!confirm("Удалить запись?"))return;var res=await fetch("/staff/notes/delete",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{note_id:nid,staff_id:sid}})}});var d=await res.json();if(d.ok)location.reload();else alert("Ошибка");}}'
        f'async function quickSave(sid,val,el){{if(el){{el.disabled=true;el.style.opacity=".6";}}var res=await fetch("/staff/quick_status",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{id:sid,status:val}})}});var d=await res.json();if(el){{el.disabled=false;el.style.opacity="1";}}if(d.ok){{if(el){{el.style.outline="2px solid #22c55e";setTimeout(function(){{el.style.outline="";}},1200);}}}}else{{alert("Ошибка");if(el)location.reload();}}}}'
        f'function openLightbox(url){{document.getElementById("lb-img").src=url;document.getElementById("lightbox").style.display="flex";}}'
        f'document.getElementById("lightbox").addEventListener("click",function(e){{if(e.target===this)this.style.display="none";}});'
        f'document.addEventListener("keydown",function(e){{if(e.key==="Escape")document.getElementById("lightbox").style.display="none";}});'
        f'async function uploadGallery(inp,sid){{var files=Array.from(inp.files),ok=0;for(var i=0;i<files.length;i++){{var fd=new FormData();fd.append("staff_id",sid);fd.append("photo",files[i]);var r=await fetch("/staff/gallery/add",{{method:"POST",body:fd}});var d=await r.json();if(d.ok)ok++;}}if(ok>0)location.reload();else alert("Ошибка загрузки");}}'
        f'async function delGallery(pid,sid){{if(!confirm("Удалить фото?"))return;var fd=new FormData();fd.append("photo_id",pid);fd.append("staff_id",sid);var r=await fetch("/staff/gallery/delete",{{method:"POST",body:fd}});var d=await r.json();if(d.ok)location.reload();else alert("Ошибка");}}'
        f'</script>'
    )
    return HTMLResponse(base(content, "staff", request))



@router.post("/staff/notes/add")
async def staff_notes_add(request: Request):
    user, err = require_auth(request)
    if err: return JSONResponse({"ok": False, "error": "unauthorized"}, 401)
    try:
        data = await request.json()
        staff_id  = int(data.get("staff_id", 0))
        note_type = data.get("type", "note")
        text      = (data.get("text") or "").strip()
        remind_at = (data.get("remind_at") or "").strip() or None
        if not staff_id or not text:
            return JSONResponse({"ok": False, "error": "missing fields"})
        manager = (user.get("display_name") or user.get("username") or "—")
        note = db.add_staff_note(staff_id, manager, note_type, text, remind_at)
        return JSONResponse({"ok": True, "id": note["id"]})
    except Exception as ex:
        log.error(f"[staff/notes/add] {ex}")
        return JSONResponse({"ok": False, "error": str(ex)})


@router.post("/staff/notes/delete")
async def staff_notes_delete(request: Request):
    user, err = require_auth(request)
    if err: return JSONResponse({"ok": False, "error": "unauthorized"}, 401)
    try:
        data = await request.json()
        note_id  = int(data.get("note_id", 0))
        staff_id = int(data.get("staff_id", 0))
        ok = db.delete_staff_note(note_id, staff_id)
        return JSONResponse({"ok": ok})
    except Exception as ex:
        log.error(f"[staff/notes/delete] {ex}")
        return JSONResponse({"ok": False, "error": str(ex)})


@router.post("/staff/quick_status")
async def staff_quick_status(request: Request):
    user, err = require_auth(request)
    if err: return JSONResponse({"ok": False})
    try:
        data = await request.json()
        staff_id = int(data.get("id", 0))
        status = data.get("status", "")
        if not staff_id or not status:
            return JSONResponse({"ok": False})
        s = db.get_staff_by_id(staff_id)
        if not s:
            return JSONResponse({"ok": False})
        # Прямое обновление только статуса
        old_s = db.get_staff_by_id(staff_id)
        old_status = (old_s.get("status") or "new") if old_s else "?"
        db.update_staff_status_only(staff_id, status)
        # Автозапись в историю
        if old_status != status:
            manager = (user.get("display_name") or user.get("username") or "—")
            db.add_staff_note(staff_id, manager, "status",
                              f"Статус: {old_status} → {status}")
        return JSONResponse({"ok": True})
    except Exception as ex:
        log.error(f"[staff/quick_status] {ex}")
        return JSONResponse({"ok": False})
