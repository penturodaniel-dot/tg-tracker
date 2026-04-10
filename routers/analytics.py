"""
routers/analytics.py — Аналитика клиентов и сотрудников

Подключается в main.py:
    analytics_setup(db, log, require_auth, base, nav_html, _render_conv_tags_picker)
    app.include_router(analytics_router)
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


def setup(_db, _log, _require_auth, _base, _nav_html, _render_conv_tags_picker_fn):
    global db, log, require_auth, base, nav_html, _render_conv_tags_picker
    db             = _db
    log            = _log
    require_auth   = _require_auth
    base           = _base
    nav_html       = _nav_html
    _render_conv_tags_picker = _render_conv_tags_picker_fn


# ANALYTICS
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/analytics/clients/reset_stats")
async def analytics_reset_stats(request: Request):
    """Установить дату начала отсчёта статистики на сегодня."""
    user, err = require_auth(request)
    if err: return err
    from datetime import date
    db.set_setting("stats_reset_date", date.today().isoformat())
    return RedirectResponse("/analytics/clients?msg=reset", 303)


@router.post("/analytics/clients/clear_reset")
async def analytics_clear_reset(request: Request):
    """Убрать дату сброса — показывать всю статистику."""
    user, err = require_auth(request)
    if err: return err
    db.set_setting("stats_reset_date", "")
    return RedirectResponse("/analytics/clients", 303)


@router.get("/analytics/clients", response_class=HTMLResponse)
async def analytics_clients(request: Request,
    date_from: str = "", date_to: str = "", period: str = "30"):
    user, err = require_auth(request)
    if err: return err

    # Дата сброса статистики — если установлена, используем как date_from
    reset_date = db.get_setting("stats_reset_date", "")
    if reset_date and not date_from:
        date_from = reset_date

    days = int(period) if period.isdigit() else 30
    df   = date_from or None
    dt   = date_to   or None

    joins_day   = db.get_joins_by_day(days=days, date_from=df, date_to=dt)
    clicks_day  = db.get_clicks_by_day(days=days, date_from=df, date_to=dt)
    summary     = db.get_joins_summary(days=days, date_from=df, date_to=dt)
    cl_summary  = db.get_clicks_summary(days=days, date_from=df, date_to=dt)
    by_channel  = db.get_joins_by_channel(days=days, date_from=df, date_to=dt)
    by_campaign = db.get_joins_by_campaign(days=days, date_from=df, date_to=dt)
    funnel      = db.get_campaign_funnel(days=days, date_from=df, date_to=dt)
    utm_src     = db.get_utm_sources(days=days, date_from=df, date_to=dt)
    recent      = db.get_recent_joins_detailed(50, days=days, date_from=df, date_to=dt)

    # Конверсия клики → подписки
    cr = round(summary["total"] / cl_summary["total"] * 100, 1) if cl_summary["total"] else 0

    def sparkline(data, key, color="#60a5fa"):
        if not data: return '<div style="color:var(--text3);font-size:.8rem">Нет данных</div>'
        mx = max((d[key] for d in data), default=1) or 1
        bars = ""
        for d in data:
            h = max(3, int(d[key] / mx * 80))
            tip = f"{d.get('day','')}: {d[key]}"
            bars += f'<div style="display:flex;flex-direction:column;align-items:center;gap:2px;flex:1;min-width:0">' \
                    f'<div title="{tip}" style="width:100%;background:{color};border-radius:3px 3px 0 0;height:{h}px;min-height:3px;cursor:default"></div>' \
                    f'<div style="font-size:.55rem;color:var(--text3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:28px">{str(d.get("day",""))[-5:]}</div></div>'
        return f'<div style="display:flex;align-items:flex-end;gap:2px;height:100px;padding:10px 0 0">{bars}</div>'

    def kpi(val, label, sub="", color="var(--accent)"):
        return f'''<div class="kpi-card">
            <div class="kpi-val" style="color:{color}">{val}</div>
            <div class="kpi-label">{label}</div>
            {"<div class='kpi-sub'>"+sub+"</div>" if sub else ""}
        </div>'''

    # Таблица каналов
    ch_rows = ""
    for c in by_channel:
        pct = round(c["joins"] / summary["total"] * 100) if summary["total"] else 0
        ch_rows += f"""<tr>
            <td style="font-weight:600">{c['channel_name']}</td>
            <td><div style="display:flex;align-items:center;gap:8px">
                <div style="flex:1;background:var(--bg3);border-radius:4px;height:6px">
                    <div style="width:{pct}%;background:var(--accent);border-radius:4px;height:6px"></div>
                </div>
                <span style="font-weight:700;color:var(--accent);min-width:28px">{c['joins']}</span>
            </div></td>
            <td style="color:var(--orange)">{c['from_ads']}</td>
            <td style="color:var(--text3);font-size:.8rem">{c['last_join'][:10] if c.get('last_join') else '—'}</td>
        </tr>"""
    ch_rows = ch_rows or '<tr><td colspan="4"><div class="empty">Нет данных</div></td></tr>'

    # Воронка по кампаниям
    camp_rows = ""
    for c in funnel:
        _cr_color = "#34d399" if c["cr"] >= 10 else ("#f97316" if c["cr"] >= 3 else "#f87171")
        _cr_str   = f'{c["cr"]}%' if c["clicks"] else "—"
        _fb_str   = f'{c["fb_joins"]} / {c["fb_clicks"]}' if c["clicks"] else "—"
        _cities   = c.get("cities", [])
        _city_badges = " ".join(
            f'<span style="background:rgba(99,102,241,.12);color:#a5b4fc;border-radius:4px;'
            f'padding:1px 5px;font-size:.65rem;font-weight:600">{ci["city"]} {ci["joins"]}</span>'
            for ci in _cities[:5] if ci["city"] and ci["city"] != "—"
        ) or '<span style="color:var(--text3);font-size:.72rem">нет данных</span>'
        _cr_bar = (
            f'<div style="display:flex;align-items:center;gap:6px">'
            f'<div style="flex:1;background:var(--bg3);border-radius:3px;height:5px;max-width:60px">'
            f'<div style="width:{min(c["cr"],100)}%;background:{_cr_color};border-radius:3px;height:5px"></div>'
            f'</div>'
            f'<span style="font-weight:700;color:{_cr_color};font-size:.82rem">{_cr_str}</span>'
            f'</div>'
        )
        camp_rows += f"""<tr>
            <td><span class="badge">{c['campaign_name']}</span>
                <div style="margin-top:4px">{_city_badges}</div></td>
            <td style="font-weight:700;color:var(--accent)">{c['clicks']}</td>
            <td style="font-weight:700;color:#34d399">{c['joins']}</td>
            <td>{_cr_bar}</td>
            <td style="color:#60a5fa;font-size:.8rem">{_fb_str}</td>
            <td style="color:var(--text3);font-size:.78rem">{str(c['last_join'])[:10] if c.get('last_join') else '—'}</td>
        </tr>"""
    camp_rows = camp_rows or '<tr><td colspan="6"><div class="empty">Нет данных за период</div></td></tr>'

    # UTM источники
    utm_rows = ""
    for u in utm_src:
        utm_rows += f"""<tr>
            <td><span class="badge-gray">{u['source']}</span></td>
            <td style="color:var(--text3)">{u['medium']}</td>
            <td style="font-weight:600">{u['clicks']}</td>
        </tr>"""
    utm_rows = utm_rows or '<tr><td colspan="3"><div class="empty">Нет данных</div></td></tr>'

    # Последние подписки
    recent_rows = ""
    for j in recent[:30]:
        src_icon = "📘" if j.get("utm_source") in ("facebook","fb") else ("🔗" if j.get("utm_source") else "🌿")
        recent_rows += f"""<tr>
            <td style="color:var(--text3);font-size:.78rem">{str(j['joined_at'])[:16].replace('T',' ')}</td>
            <td style="font-weight:600">{j.get('channel_name','—')}</td>
            <td><span class="badge" style="font-size:.7rem">{j['campaign_name']}</span></td>
            <td title="{j.get('utm_source','') or ''}">{src_icon} {j.get('utm_source') or 'organic'}</td>
            <td>{"✅" if j.get('fbclid') else "—"}</td>
        </tr>"""
    recent_rows = recent_rows or '<tr><td colspan="5"><div class="empty">Нет подписок за период</div></td></tr>'

    sel_period = lambda v,l: f'<option value="{v}" {"selected" if period==v else ""}>{l}</option>'

    # Баннер сброса статистики
    reset_date  = db.get_setting("stats_reset_date", "")
    reset_banner = ""
    if reset_date:
        reset_banner = f"""<div style="background:rgba(251,146,60,.1);border:1px solid #f97316;
            border-radius:10px;padding:10px 16px;margin-bottom:16px;
            display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
          <span style="color:#fb923c;font-size:.88rem">
            🔁 Статистика считается с <b>{reset_date}</b> (новый запуск кампании)
          </span>
          <form method="post" action="/analytics/clients/clear_reset" style="margin:0">
            <button class="btn-gray" style="font-size:.78rem;padding:4px 10px">✕ Показать всё</button>
          </form>
        </div>"""

    content = f"""<div class="page-wrap">
    <div class="page-title">📈 Статистика Клиентов</div>
    <div class="page-sub">Подписки, клики, кампании, конверсия</div>

    <div style="display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap;margin-bottom:16px">
      <form method="get" action="/analytics/clients" style="display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap">
        <div class="field-group" style="max-width:150px">
          <div class="field-label">Период</div>
          <select name="period" onchange="this.form.submit()">
            {sel_period("7","7 дней")}
            {sel_period("14","14 дней")}
            {sel_period("30","30 дней")}
            {sel_period("60","60 дней")}
            {sel_period("90","90 дней")}
          </select>
        </div>
        <div class="field-group"><div class="field-label">С даты</div>
          <input type="date" name="date_from" value="{date_from}"/></div>
        <div class="field-group"><div class="field-label">По дату</div>
          <input type="date" name="date_to" value="{date_to}"/></div>
        <div style="display:flex;align-items:flex-end;gap:6px">
          <button class="btn">Применить</button>
          <a href="/analytics/clients" class="btn-gray">Сбросить фильтр</a>
        </div>
      </form>
      <form method="post" action="/analytics/clients/reset_stats"
            style="display:flex;align-items:flex-end"
            onsubmit="return confirm('Начать отсчёт статистики с сегодня? Старые данные сохранятся, просто не будут показываться по умолчанию.')">
        <button class="btn" style="background:rgba(249,115,22,.15);border-color:#f97316;color:#fb923c;font-size:.82rem"
          title="Сбросить счётчик — статистика будет считаться с сегодня (при запуске новой кампании)">
          🔁 Новый запуск
        </button>
      </form>
    </div>

    {reset_banner}

    <div class="kpi-grid">
      {kpi(summary['total'], 'Подписок всего', f"{summary['from_ads']} из рекламы / {summary['organic']} organic")}
      {kpi(cl_summary['total'], 'Кликов /go', f"{cl_summary['from_fb']} FB · только отслеживаемые переходы")}
      {kpi(f"{cr}%", 'CR /go→подписка', 'только tracked клики', "#34d399" if cr>10 else "#f97316")}
      {kpi(cl_summary['has_fbp'], 'С fbp cookie', 'для FB CAPI matching')}
      {kpi(summary['channels_active'], 'Активных каналов', '')}
      {kpi(summary['campaigns_active'], 'Кампаний', '')}
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
      <div class="section">
        <div class="section-head"><h3>📡 По каналам</h3></div>
        <table><thead><tr><th>Канал</th><th>Подписок</th><th>Реклама</th><th>Последняя</th></tr></thead>
        <tbody>{ch_rows}</tbody></table>
      </div>
      <div class="section">
        <div class="section-head"><h3>🔗 Источники трафика</h3></div>
        <table><thead><tr><th>Источник</th><th>Medium</th><th>Кликов</th></tr></thead>
        <tbody>{utm_rows}</tbody></table>
      </div>
    </div>

    <div class="section">
      <div class="section-head">
        <h3>🎯 Воронка по кампаниям</h3>
        <span style="font-size:.75rem;color:var(--text3)">
          подписки → конверсия · <span title="Клики считаются только по переходам через /go/ссылку лендинга">👆 клики = только /go переходы</span>
        </span>
      </div>
      <table>
        <thead><tr>
          <th>Кампания / Города</th>
          <th title="Переходов через /go лендинг (отслеживаемые клики)">👆 /go клики</th>
          <th title="Подписок на каналы (все источники)">✅ Подписки</th>
          <th title="Конверсия: /go клики → подписки (только tracked)">📊 CR</th>
          <th title="FB подписки / FB клики">📘 FB</th>
          <th>Последняя</th>
        </tr></thead>
        <tbody>{camp_rows}</tbody>
      </table>
    </div>

    <div class="section">
      <div class="section-head"><h3>⏱ Последние подписки</h3></div>
      <table><thead><tr><th>Время</th><th>Канал</th><th>Кампания</th><th>Источник</th><th>fbclid</th></tr></thead>
      <tbody>{recent_rows}</tbody></table>
    </div>
    </div>"""
    return HTMLResponse(base(content + _analytics_css(), "analytics_clients", request))


@router.get("/analytics/staff", response_class=HTMLResponse)
async def analytics_staff(request: Request,
    date_from: str = "", date_to: str = "", period: str = "30"):
    user, err = require_auth(request)
    if err: return err

    days = int(period) if period.isdigit() else 30
    df   = date_from or None
    dt   = date_to   or None

    summary    = db.get_staff_summary(days=days, date_from=df, date_to=dt)
    by_day     = db.get_staff_by_day(days=days, date_from=df, date_to=dt)
    msg_day    = db.get_messages_by_day(days=days, date_from=df, date_to=dt)
    wa_day     = db.get_wa_messages_by_day(days=days, date_from=df, date_to=dt)
    tga_day    = db.get_tga_messages_by_day(days=days, date_from=df, date_to=dt)
    msg_sum    = db.get_messages_summary(days=days, date_from=df, date_to=dt)
    tga_sum    = db.get_tga_messages_summary(days=days, date_from=df, date_to=dt)
    wa_stats   = db.get_wa_stats()
    tga_stats  = db.get_tga_stats()
    funnel     = db.get_staff_funnel(date_from=df, date_to=dt)
    resp_stats = db.get_staff_response_stats(days=days, date_from=df, date_to=dt)

    def kpi(val, label, sub="", color="var(--accent)"):
        return f'''<div class="kpi-card">
            <div class="kpi-val" style="color:{color}">{val}</div>
            <div class="kpi-label">{label}</div>
            {"<div class='kpi-sub'>"+sub+"</div>" if sub else ""}
        </div>'''

    def sparkline(data, key, color="#f97316"):
        if not data: return '<div style="color:var(--text3);font-size:.8rem">Нет данных</div>'
        mx = max((d[key] for d in data), default=1) or 1
        bars = ""
        for d in data:
            h = max(3, int(d[key] / mx * 80))
            bars += f'<div style="display:flex;flex-direction:column;align-items:center;gap:2px;flex:1;min-width:0">' \
                    f'<div title="{d.get("day","")}: {d[key]}" style="width:100%;background:{color};border-radius:3px 3px 0 0;height:{h}px;min-height:3px;cursor:default"></div>' \
                    f'<div style="font-size:.55rem;color:var(--text3);white-space:nowrap;overflow:hidden;max-width:28px">{str(d.get("day",""))[-5:]}</div></div>'
        return f'<div style="display:flex;align-items:flex-end;gap:2px;height:100px;padding:10px 0 0">{bars}</div>'

    # Воронка
    fn_total  = summary["total"] or 1
    fn_steps  = [
        ("s_new",       "🆕 Новые",     "#60a5fa"),
        ("s_review",    "👀 Смотрим",   "#a78bfa"),
        ("s_interview", "🔍 Верификация", "#f59e0b"),
        ("s_hired",     "💼 В работе",    "#34d399"),
        ("s_rejected",  "🚫 Слив",        "#f87171"),
    ]
    funnel_html = ""
    for key, label, color in fn_steps:
        val = summary.get(key, 0)
        pct = round(val / fn_total * 100)
        funnel_html += f"""<div class="funnel-item">
            <div style="display:flex;justify-content:space-between;margin-bottom:4px">
                <span style="font-size:.85rem;font-weight:600">{label}</span>
                <span style="font-weight:700;color:{color}">{val} <span style="color:var(--text3);font-size:.75rem">({pct}%)</span></span>
            </div>
            <div style="background:var(--bg3);border-radius:6px;height:8px">
                <div style="width:{pct}%;background:{color};border-radius:6px;height:8px;transition:width .3s"></div>
            </div>
        </div>"""

    # Конверсия найм
    conv_hire = funnel.get("conversion_hired", 0)

    # Таблица активности сотрудников
    staff_rows = ""
    status_colors = {"new":"var(--accent)","review":"#a78bfa","interview":"#f59e0b","hired":"#34d399","rejected":"#f87171"}
    for s in resp_stats:
        sc = status_colors.get(s.get("status","new"), "var(--text3)")
        last_msg = str(s.get("last_message_at",""))[:16].replace("T"," ") if s.get("last_message_at") else "—"
        staff_rows += f"""<tr>
            <td style="font-weight:600">{s.get('name') or '—'}</td>
            <td><span style="color:{sc};font-weight:600;font-size:.8rem">{s.get('status','—')}</span></td>
            <td style="color:var(--accent);font-weight:700">{s['msg_count']}</td>
            <td style="color:var(--text3);font-size:.78rem">{last_msg}</td>
            <td style="color:var(--text3);font-size:.78rem">{str(s.get('created_at',''))[:10]}</td>
        </tr>"""
    staff_rows = staff_rows or '<tr><td colspan="5"><div class="empty">Нет данных</div></td></tr>'

    sel_period = lambda v,l: f'<option value="{v}" {"selected" if period==v else ""}>{l}</option>'
    content = f"""<div class="page-wrap">
    <div class="page-title">📊 Статистика Сотрудников</div>
    <div class="page-sub">Лиды, воронка найма, активность переписки</div>

    <form method="get" action="/analytics/staff" style="display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap;margin-bottom:24px">
      <div class="field-group" style="max-width:150px">
        <div class="field-label">Период</div>
        <select name="period" onchange="this.form.submit()">
          {sel_period("7","7 дней")}
          {sel_period("14","14 дней")}
          {sel_period("30","30 дней")}
          {sel_period("60","60 дней")}
          {sel_period("90","90 дней")}
        </select>
      </div>
      <div class="field-group"><div class="field-label">С даты</div>
        <input type="date" name="date_from" value="{date_from}"/></div>
      <div class="field-group"><div class="field-label">По дату</div>
        <input type="date" name="date_to" value="{date_to}"/></div>
      <div style="display:flex;align-items:flex-end;gap:6px">
        <button class="btn">Применить</button>
        <a href="/analytics/staff" class="btn-gray">Сбросить</a>
      </div>
    </form>

    <div class="kpi-grid">
      {kpi(summary['total'], 'Новых лидов', f"за период")}
      {kpi(summary['s_hired'], 'В работе', f'{conv_hire}% конверсия', '#34d399')}
      {kpi(summary['s_interview'], 'На интервью', '', '#f59e0b')}
      {kpi(summary['s_rejected'], 'Сливов', '', '#f87171')}
      {kpi(msg_sum['total'], 'Сообщений TG бот', f"{msg_sum['incoming']} вх / {msg_sum['outgoing']} исх")}
      {kpi(msg_sum['active_convos'], 'Активных TG бот чатов', '')}
      {kpi(tga_stats.get('total_convs', 0), 'TG аккаунт чатов', f"{tga_stats.get('open_convs',0)} открытых", '#2ca5e0')}
      {kpi(tga_stats.get('total_msgs', 0), 'Сообщений TG акк', f"{tga_stats.get('incoming',0)} вх / {tga_stats.get('outgoing',0)} исх", '#2ca5e0')}
      {kpi(tga_stats.get('fb_convs', 0), 'TG акк с FB', 'с fbclid', '#1877f2')}
      {kpi(wa_stats.get('total_convs', 0), 'WA чатов всего', f"{wa_stats.get('open_convs',0)} открытых", '#25d366')}
      {kpi(wa_stats.get('total_msgs', 0), 'Сообщений WA', f"{wa_stats.get('incoming',0)} вх / {wa_stats.get('outgoing',0)} исх", '#25d366')}
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
      <div class="section">
        <div class="section-head"><h3>📈 Новые лиды по дням</h3></div>
        <div class="section-body">{sparkline(by_day, 'cnt', '#f97316')}</div>
      </div>
      <div class="section">
        <div class="section-head"><h3>💬 Сообщения TG бот по дням</h3></div>
        <div class="section-body">{sparkline(msg_day, 'total', '#60a5fa')}</div>
      </div>
      <div class="section">
        <div class="section-head"><h3>📱 Сообщения TG аккаунт по дням</h3></div>
        <div class="section-body">{sparkline(tga_day, 'total', '#2ca5e0')}</div>
      </div>
      <div class="section">
        <div class="section-head"><h3>💚 Сообщения WA по дням</h3></div>
        <div class="section-body">{sparkline(wa_day, 'total', '#25d366')}</div>
      </div>
    </div>

    <div class="section">
      <div class="section-head"><h3>🎯 Воронка найма</h3></div>
      <div class="section-body"><div style="display:flex;flex-direction:column;gap:12px;max-width:500px">{funnel_html}</div></div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px">
      <div class="section">
        <div class="section-head"><h3>📱 TG Аккаунт — сводка за период</h3></div>
        <div class="section-body">
          <div style="display:flex;flex-direction:column;gap:8px">
            <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
              <span style="color:var(--text3)">Сообщений всего</span>
              <span style="font-weight:700;color:#2ca5e0">{tga_sum['total']}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
              <span style="color:var(--text3)">Входящих</span>
              <span style="font-weight:700">{tga_sum['incoming']}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
              <span style="color:var(--text3)">Исходящих</span>
              <span style="font-weight:700">{tga_sum['outgoing']}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:8px 0">
              <span style="color:var(--text3)">Активных диалогов</span>
              <span style="font-weight:700">{tga_sum['active_convos']}</span>
            </div>
          </div>
        </div>
      </div>
      <div class="section">
        <div class="section-head"><h3>💚 WhatsApp — сводка за период</h3></div>
        <div class="section-body">
          <div style="display:flex;flex-direction:column;gap:8px">
            <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
              <span style="color:var(--text3)">Сообщений всего</span>
              <span style="font-weight:700;color:#25d366">{wa_stats.get('total_msgs', 0)}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
              <span style="color:var(--text3)">Входящих</span>
              <span style="font-weight:700">{wa_stats.get('incoming', 0)}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border)">
              <span style="color:var(--text3)">Исходящих</span>
              <span style="font-weight:700">{wa_stats.get('outgoing', 0)}</span>
            </div>
            <div style="display:flex;justify-content:space-between;padding:8px 0">
              <span style="color:var(--text3)">Открытых чатов</span>
              <span style="font-weight:700">{wa_stats.get('open_convs', 0)}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="section">
      <div class="section-head"><h3>👥 Активность по сотрудникам</h3></div>
      <table><thead><tr><th>Имя</th><th>Статус</th><th>Сообщений</th><th>Последнее сообщение</th><th>Добавлен</th></tr></thead>
      <tbody>{staff_rows}</tbody></table>
    </div>
    </div>"""
    return HTMLResponse(base(content + _analytics_css(), "analytics_staff", request))


def _dual_sparkline(joins_day, clicks_day):
    """График подписок + кликов на одной шкале"""
    if not joins_day and not clicks_day:
        return '<div class="empty">Нет данных за период</div>'
    # Объединяем дни
    days_set = sorted(set(
        [d["day"] for d in joins_day] + [d["day"] for d in clicks_day]
    ))
    j_map = {d["day"]: d["cnt"] for d in joins_day}
    c_map = {d["day"]: d["clicks"] for d in clicks_day}
    mx = max([j_map.get(d,0) for d in days_set] + [c_map.get(d,0) for d in days_set] + [1])
    bars = ""
    for day in days_set[-40:]:
        jh = max(2, int(j_map.get(day,0) / mx * 90))
        ch = max(2, int(c_map.get(day,0) / mx * 90))
        label = str(day)[-5:]
        bars += f'''<div style="display:flex;flex-direction:column;align-items:center;gap:1px;flex:1;min-width:0">
            <div style="width:100%;display:flex;align-items:flex-end;gap:1px;height:92px">
                <div title="{day} подписок: {j_map.get(day,0)}" style="flex:1;background:#60a5fa;border-radius:2px 2px 0 0;height:{jh}px"></div>
                <div title="{day} кликов: {c_map.get(day,0)}" style="flex:1;background:rgba(249,115,22,.5);border-radius:2px 2px 0 0;height:{ch}px"></div>
            </div>
            <div style="font-size:.52rem;color:var(--text3);max-width:28px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{label}</div>
        </div>'''
    legend = '''<div style="display:flex;gap:16px;margin-top:10px;font-size:.78rem;color:var(--text3)">
        <span><span style="display:inline-block;width:10px;height:10px;background:#60a5fa;border-radius:2px;margin-right:4px"></span>Подписки</span>
        <span><span style="display:inline-block;width:10px;height:10px;background:rgba(249,115,22,.5);border-radius:2px;margin-right:4px"></span>Клики</span>
    </div>'''
    return f'<div style="display:flex;align-items:flex-end;gap:2px;height:110px">{bars}</div>{legend}'


def _analytics_css():
    return """<style>
    .kpi-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;margin-bottom:24px}
    .kpi-card{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:16px;text-align:center}
    .kpi-val{font-size:1.8rem;font-weight:800;line-height:1.1;margin-bottom:4px}
    .kpi-label{font-size:.78rem;font-weight:600;color:var(--text3);text-transform:uppercase;letter-spacing:.04em}
    .kpi-sub{font-size:.72rem;color:var(--text3);margin-top:4px}
    .funnel-item{margin-bottom:8px}
    @media(max-width:640px){.kpi-grid{grid-template-columns:repeat(2,1fr)}}
    </style>"""

