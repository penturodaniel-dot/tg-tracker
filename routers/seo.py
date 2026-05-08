"""
routers/seo.py
SEO-модуль: публичный диспетчер запросов и админка.

Этот модуль НЕ модифицирует поведение существующих роутеров (chat_*,
analytics, staff, channels, projects и т.д.). Он только добавляет
новые маршруты под /seo/* и предоставляет функцию dispatch_seo_request,
которую вызовет CustomDomainMiddleware (Коммит 4) при заходе на SEO-домен.

Экспортируется:
- dispatch_seo_request(request, site, preview=False) — точка входа из middleware
- router (APIRouter)  — админка под /seo/*
- setup(...)          — инициализатор зависимостей
"""
import json as _json
import logging
from html import escape as _esc
from urllib.parse import unquote

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response

import seo_templates as tpl

log = logging.getLogger(__name__)

router = APIRouter()

_db = None
_log = None
_require_auth = None
_base = None
_nav_html = None
_app_url: str = ""


def setup(db, log_obj, require_auth_fn, base_fn, nav_html_fn, *, app_url: str = ""):
    global _db, _log, _require_auth, _base, _nav_html, _app_url
    _db = db
    _log = log_obj
    _require_auth = require_auth_fn
    _base = base_fn
    _nav_html = nav_html_fn
    _app_url = (app_url or "").rstrip("/")


# ── Хелперы ──────────────────────────────────────────────────────────────────

def _menu_pages_for(site: dict) -> list:
    """Опубликованные страницы с show_in_menu=1, отсортированные по position."""
    if not _db:
        return []
    pages = _db.get_seo_pages(site["id"], status="published")
    return [p for p in pages if p.get("show_in_menu")]


def _check_redirect(site: dict, path: str):
    """Возвращает (to_path, status_code) если есть редирект для path. Иначе None."""
    if not _db:
        return None
    rec = _db.get_seo_redirect(site["id"], path)
    if rec:
        try:
            _db.log_seo_redirect_hit(rec["id"])
        except Exception:
            pass
        return (rec["to_path"], int(rec.get("status_code") or 301))
    return None


def _normalize_path(path: str) -> str:
    """Нормализуем путь: декодируем, убираем trailing slash (кроме корня)."""
    p = unquote(path or "/")
    if not p.startswith("/"):
        p = "/" + p
    if len(p) > 1 and p.endswith("/"):
        p = p.rstrip("/")
    return p


# ── Диспетчер ────────────────────────────────────────────────────────────────

async def dispatch_seo_request(request: Request, site: dict, *,
                                preview: bool = False, preview_path: str = None) -> Response:
    """Главная точка входа из CustomDomainMiddleware.

    Принимает уже сматченный сайт (по домену) и текущий request,
    возвращает Response (HTML / XML / redirect / 404).

    preview=True переключает режим: статус сайта/контента не проверяется
    (можно смотреть draft/unpublished). Используется админкой /seo/preview/...
    preview_path — переопределяет путь (когда диспетчер вызван из preview-роута).

    Внутри ловим все исключения и при ошибках возвращаем 500 без падения
    middleware — чтобы баги в SEO-модуле не задели остальной траффик.
    """
    if not _db:
        return PlainTextResponse("SEO module not initialized", status_code=500)

    try:
        raw_path = preview_path if preview_path is not None else request.url.path
        path = _normalize_path(raw_path)

        # Только опубликованные сайты обслуживаем (preview обходит)
        if not preview and site.get("status") != "live":
            return PlainTextResponse("Site not yet published", status_code=404)

        # Системные маршруты
        if path == "/sitemap.xml":
            urls = _db.get_seo_sitemap_urls(site["id"])
            xml = tpl.render_sitemap_xml(site, urls)
            return Response(content=xml, media_type="application/xml")

        if path == "/robots.txt":
            txt = tpl.render_robots_txt(site)
            return PlainTextResponse(txt)

        # Редиректы
        red = _check_redirect(site, path)
        if red:
            to_path, code = red
            return RedirectResponse(to_path, status_code=code)

        # В preview — НЕ фильтруем по статусу публикации
        list_status = None if preview else "published"
        menu_pages = _menu_pages_for(site)

        # Корень — главная сайта
        if path == "/" or path == "":
            locations = _db.get_seo_locations(site["id"], status=list_status)
            articles = _db.get_seo_articles(site["id"], status=list_status, limit=6)
            html = tpl.render_seo_home(site, locations, articles, menu_pages)
            return HTMLResponse(html)

        # Блог-индекс
        if path == "/blog":
            articles = _db.get_seo_articles(site["id"], status=list_status, limit=50)
            categories = _db.get_seo_categories(site["id"])
            html = tpl.render_seo_blog_index(site, articles, categories, menu_pages)
            return HTMLResponse(html)

        # Блог по категории: /blog/category/<slug>
        if path.startswith("/blog/category/"):
            cat_slug = path[len("/blog/category/"):].split("/", 1)[0]
            category = _db.get_seo_category_by_slug(site["id"], cat_slug)
            if not category:
                return _render_404(site, menu_pages)
            articles = _db.get_seo_articles(site["id"], status=list_status,
                                             category_id=category["id"], limit=50)
            categories = _db.get_seo_categories(site["id"])
            html = tpl.render_seo_blog_index(site, articles, categories,
                                              menu_pages, category=category)
            return HTMLResponse(html)

        # Статья: /blog/<slug>
        if path.startswith("/blog/"):
            slug = path[len("/blog/"):].split("/", 1)[0]
            if not slug:
                return _render_404(site, menu_pages)
            article = _db.get_seo_article_by_slug(site["id"], slug)
            if not article or (not preview and article.get("status") != "published"):
                return _render_404(site, menu_pages)
            author = None
            if article.get("author_id"):
                author = _db.get_seo_author(article["author_id"])
            category = None
            if article.get("category_id"):
                category = _db.get_seo_category(article["category_id"])
            related = _db.get_seo_articles(
                site["id"], status=list_status,
                category_id=article.get("category_id"), limit=4
            )
            related = [r for r in related if r["id"] != article["id"]][:3]
            if not preview:
                try:
                    _db.increment_seo_article_views(article["id"])
                except Exception:
                    pass
            html = tpl.render_seo_article(site, article, author=author,
                                           category=category, related=related,
                                           menu_pages=menu_pages)
            return HTMLResponse(html)

        # Произвольный slug — может быть локацией или страницей
        slug = path.lstrip("/").split("/", 1)[0]

        # Сначала ищем среди локаций (они приоритетнее, обычно их слаги короче)
        location = _db.get_seo_location_by_slug(site["id"], slug)
        if location and (preview or location.get("status") == "published"):
            contacts = _db.get_seo_location_contacts(location["id"], only_active=True)
            html = tpl.render_seo_location(site, location, contacts, menu_pages)
            return HTMLResponse(html)

        # Затем — статические страницы
        page = _db.get_seo_page_by_slug(site["id"], slug)
        if page and (preview or page.get("status") == "published"):
            html = tpl.render_seo_page(site, page, menu_pages)
            return HTMLResponse(html)

        # Не нашли — 404
        return _render_404(site, menu_pages)

    except Exception as e:
        log.error(f"[SEO] dispatch error host={request.headers.get('host')} path={request.url.path}: {e}", exc_info=True)
        return PlainTextResponse("Internal error", status_code=500)


def _render_404(site: dict, menu_pages: list) -> HTMLResponse:
    try:
        html = tpl.render_404(site, menu_pages)
        return HTMLResponse(html, status_code=404)
    except Exception:
        return PlainTextResponse("Not Found", status_code=404)


# ════════════════════════════════════════════════════════════════════════════
# АДМИНКА /seo/* — управление сайтами / локациями / страницами / статьями
# ════════════════════════════════════════════════════════════════════════════

def _admin_check(request: Request):
    """Возвращает (user, err_response). Доступ только админам."""
    if not _require_auth:
        return None, PlainTextResponse("not initialized", status_code=500)
    user, err = _require_auth(request)
    if err:
        return None, err
    if user.get("role") != "admin":
        return None, PlainTextResponse("forbidden", status_code=403)
    return user, None


def _safe_int(v, default=0):
    try:
        return int(v)
    except Exception:
        return default


def _site_or_404(site_id: int):
    s = _db.get_seo_site(site_id)
    if not s:
        return None, PlainTextResponse("Site not found", status_code=404)
    return s, None


# ── Layout / общие куски HTML ────────────────────────────────────────────────

_ADMIN_CSS = """<style>
.seo-wrap{padding:20px 28px;max-width:1280px}
.seo-h1{font-size:1.6rem;font-weight:700;margin-bottom:18px;color:var(--text)}
.seo-h2{font-size:1.15rem;font-weight:600;margin:18px 0 10px;color:var(--text)}
.seo-tabs{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:18px;border-bottom:1px solid var(--border);padding-bottom:0}
.seo-tabs a{padding:8px 14px;color:var(--text2);text-decoration:none;border-bottom:2px solid transparent;font-size:.9rem;font-weight:500}
.seo-tabs a.active{color:#fde047;border-bottom-color:#fde047}
.seo-tabs a:hover{color:var(--text)}
.seo-grid{display:grid;gap:14px}
.seo-grid-2{grid-template-columns:1fr 1fr}
.seo-grid-3{grid-template-columns:1fr 1fr 1fr}
@media(max-width:900px){.seo-grid-2,.seo-grid-3{grid-template-columns:1fr}}
.seo-card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px}
.seo-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px;border:1px solid var(--border);border-radius:8px;background:var(--surface);margin-bottom:8px}
.seo-row .meta{font-size:.78rem;color:var(--text3)}
.seo-form .field{margin-bottom:12px}
.seo-form label{display:block;font-size:.78rem;color:var(--text2);margin-bottom:4px;font-weight:600}
.seo-form input[type=text],.seo-form input[type=url],.seo-form input[type=email],.seo-form input[type=number],.seo-form select,.seo-form textarea{width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font:inherit;font-size:.9rem}
.seo-form textarea{font-family:'SF Mono',Menlo,monospace;font-size:.82rem;line-height:1.5;resize:vertical;min-height:120px}
.seo-form input:focus,.seo-form select:focus,.seo-form textarea:focus{outline:none;border-color:#fde047}
.seo-form .hint{font-size:.72rem;color:var(--text3);margin-top:4px}
.seo-form .checkbox{display:flex;align-items:center;gap:8px;font-size:.85rem;color:var(--text2)}
.seo-btn{display:inline-block;padding:8px 16px;border:none;border-radius:6px;background:#fde047;color:#1a1a1a;font-weight:600;cursor:pointer;text-decoration:none;font-size:.85rem;font-family:inherit}
.seo-btn:hover{background:#fcd34d}
.seo-btn.secondary{background:transparent;border:1px solid var(--border);color:var(--text2)}
.seo-btn.secondary:hover{border-color:#fde047;color:#fde047}
.seo-btn.danger{background:#7f1d1d;color:#fca5a5}
.seo-btn.danger:hover{background:#991b1b;color:#fff}
.seo-btn.sm{padding:5px 10px;font-size:.78rem}
.seo-pill{display:inline-block;padding:2px 8px;border-radius:999px;font-size:.7rem;font-weight:600}
.seo-pill.live{background:#064e3b;color:#34d399}
.seo-pill.draft{background:#374151;color:#9ca3af}
.seo-pill.published{background:#064e3b;color:#34d399}
.seo-actions{display:flex;gap:8px;flex-wrap:wrap}
.seo-bar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px;flex-wrap:wrap}
.seo-table{width:100%;border-collapse:collapse;font-size:.88rem}
.seo-table th{text-align:left;padding:10px;font-weight:600;color:var(--text2);border-bottom:1px solid var(--border);font-size:.78rem;text-transform:uppercase;letter-spacing:.05em}
.seo-table td{padding:10px;border-bottom:1px solid var(--border);color:var(--text)}
.seo-table tr:hover td{background:var(--surface)}
.seo-flash{padding:10px 14px;border-radius:8px;margin-bottom:14px;font-size:.88rem}
.seo-flash.ok{background:#064e3b;color:#34d399;border:1px solid #047857}
.seo-flash.err{background:#7f1d1d;color:#fca5a5;border:1px solid #991b1b}
.seo-color-pair{display:flex;gap:8px}
.seo-color-pair input[type=text]{flex:1}
.seo-color-pair input[type=color]{width:42px;padding:0;border:1px solid var(--border);border-radius:6px;background:none;cursor:pointer}
</style>"""


def _flash(request: Request) -> str:
    msg = request.query_params.get("msg", "")
    err = request.query_params.get("err", "")
    out = ""
    if msg:
        out += f'<div class="seo-flash ok">{_esc(msg[:200])}</div>'
    if err:
        out += f'<div class="seo-flash err">{_esc(err[:200])}</div>'
    return out


def _site_subnav(site_id: int, active: str) -> str:
    items = [
        ("settings",  "Настройки",        f"/seo/sites/{site_id}"),
        ("locations", "Локации",          f"/seo/sites/{site_id}/locations"),
        ("pages",     "Страницы",         f"/seo/sites/{site_id}/pages"),
        ("articles",  "Статьи",           f"/seo/sites/{site_id}/articles"),
        ("categories","Рубрики",          f"/seo/sites/{site_id}/categories"),
        ("authors",   "Авторы",           f"/seo/sites/{site_id}/authors"),
        ("redirects", "Редиректы",        f"/seo/sites/{site_id}/redirects"),
        ("import",    "📥 Импорт JSON",   f"/seo/sites/{site_id}/import"),
        ("preview",   "Превью",           f"/seo/preview/{site_id}/"),
    ]
    out = '<div class="seo-tabs">'
    for k, lbl, href in items:
        cls = "active" if k == active else ""
        out += f'<a href="{_esc(href)}" class="{cls}">{_esc(lbl)}</a>'
    out += '</div>'
    return out


def _layout(content: str, request: Request, *, breadcrumb: str = "SEO") -> str:
    flash = _flash(request)
    body = f'<div class="seo-wrap">{_ADMIN_CSS}<div style="font-size:.78rem;color:var(--text3);margin-bottom:6px">{breadcrumb}</div>{flash}{content}</div>'
    return _base(body, "seo", request)


def _redirect_to(url: str, msg: str = None, err: str = None) -> RedirectResponse:
    from urllib.parse import quote_plus as _qp
    qs = []
    if msg: qs.append(f"msg={_qp(msg)}")
    if err: qs.append(f"err={_qp(err)}")
    sep = "?" if "?" not in url else "&"
    full = url + (sep + "&".join(qs) if qs else "")
    return RedirectResponse(full, status_code=303)


# ── Field helpers ────────────────────────────────────────────────────────────

def _f_text(label, name, value="", *, type="text", hint="", required=False):
    req = " required" if required else ""
    h = f'<div class="hint">{_esc(hint)}</div>' if hint else ""
    return f'<div class="field"><label>{_esc(label)}</label><input type="{type}" name="{name}" value="{_esc(value)}"{req}>{h}</div>'

def _f_textarea(label, name, value="", *, rows=6, hint=""):
    h = f'<div class="hint">{_esc(hint)}</div>' if hint else ""
    return f'<div class="field"><label>{_esc(label)}</label><textarea name="{name}" rows="{rows}">{_esc(value)}</textarea>{h}</div>'

def _f_select(label, name, value, options, hint=""):
    opts = ""
    for v, lbl in options:
        sel = " selected" if str(v) == str(value or "") else ""
        opts += f'<option value="{_esc(v)}"{sel}>{_esc(lbl)}</option>'
    h = f'<div class="hint">{_esc(hint)}</div>' if hint else ""
    return f'<div class="field"><label>{_esc(label)}</label><select name="{name}">{opts}</select>{h}</div>'

def _f_checkbox(label, name, value, hint=""):
    chk = " checked" if value else ""
    h = f'<div class="hint">{_esc(hint)}</div>' if hint else ""
    return f'<div class="field"><label class="checkbox"><input type="checkbox" name="{name}" value="1"{chk}> {_esc(label)}</label>{h}</div>'

def _f_color(label, name, value):
    val = value or "#7A9B76"
    return (f'<div class="field"><label>{_esc(label)}</label><div class="seo-color-pair">'
            f'<input type="text" name="{name}" value="{_esc(val)}">'
            f'<input type="color" value="{_esc(val)}" oninput="this.previousElementSibling.value=this.value">'
            f'</div></div>')


# ════════════════════════════════════════════════════════════════════════════
# SITES
# ════════════════════════════════════════════════════════════════════════════

@router.get("/seo", response_class=HTMLResponse)
async def seo_index(request: Request):
    user, err = _admin_check(request)
    if err: return err
    sites = _db.get_seo_sites()
    rows = ""
    for s in sites:
        status_pill = '<span class="seo-pill live">live</span>' if s.get("status") == "live" else '<span class="seo-pill draft">draft</span>'
        rows += f"""<tr>
<td><a href="/seo/sites/{s['id']}" style="color:#fde047;font-weight:600">{_esc(s.get('name') or '')}</a><div style="font-size:.75rem;color:var(--text3);margin-top:2px">{_esc(s.get('domain') or '')}</div></td>
<td>{_esc((s.get('site_type') or '').title())}</td>
<td>{_esc((s.get('language') or '').upper())}</td>
<td>{status_pill}</td>
<td>{_esc((s.get('updated_at') or '')[:10])}</td>
<td><a href="/seo/sites/{s['id']}" class="seo-btn sm secondary">Открыть</a>
<form method="post" action="/seo/sites/{s['id']}/delete" style="display:inline" onsubmit="return confirm('Удалить сайт «{_esc(s.get('name') or '')}» со всем контентом?')"><button class="seo-btn sm danger">✕</button></form></td>
</tr>"""
    if not rows:
        rows = '<tr><td colspan="6" style="text-align:center;color:var(--text3);padding:32px">Сайтов пока нет. Создайте первый ниже.</td></tr>'

    create_form = """<div class="seo-card">
<div class="seo-h2">Новый сайт</div>
<form class="seo-form" method="post" action="/seo/sites/new">
<div class="seo-grid seo-grid-2">
""" + _f_text("Название (внутреннее)", "name", "", required=True, hint="Например: RelaxTouch (Clients)") + _f_text("Домен", "domain", "", required=True, hint="Например: relaxtouchtoday.com (без https://)") + """</div>
<div class="seo-grid seo-grid-3">
""" + _f_select("Тип", "site_type", "client", [("client","Клиенты"),("staff","Сотрудники"),("other","Другое")]) + _f_select("Язык", "language", "en", [("en","English"),("ru","Русский"),("uk","Українська"),("es","Español")]) + _f_text("Бренд (видимое имя)", "brand_name", "", hint="Появляется в шапке и футере") + """</div>
<button class="seo-btn">Создать</button>
</form></div>"""

    content = f"""<div class="seo-h1">SEO-сайты</div>
<table class="seo-table" style="margin-bottom:24px">
<thead><tr><th>Сайт</th><th>Тип</th><th>Язык</th><th>Статус</th><th>Обновлён</th><th></th></tr></thead>
<tbody>{rows}</tbody>
</table>
{create_form}"""
    return HTMLResponse(_layout(content, request))


@router.post("/seo/sites/new")
async def seo_site_new(request: Request,
                        name: str = Form(...),
                        domain: str = Form(...),
                        site_type: str = Form("client"),
                        language: str = Form("en"),
                        brand_name: str = Form("")):
    user, err = _admin_check(request)
    if err: return err
    try:
        new_id = _db.create_seo_site(
            name.strip(), domain.strip().lower(),
            site_type=site_type, language=language,
            brand_name=brand_name.strip() or name.strip(),
        )
        return _redirect_to(f"/seo/sites/{new_id}", msg="Сайт создан")
    except Exception as e:
        log.error(f"[SEO] site create error: {e}")
        return _redirect_to("/seo", err=f"Ошибка: {e}")


@router.get("/seo/sites/{site_id}", response_class=HTMLResponse)
async def seo_site_edit(request: Request, site_id: int):
    user, err = _admin_check(request)
    if err: return err
    site, e = _site_or_404(site_id)
    if e: return e

    f = """<form class="seo-form" method="post" action="/seo/sites/{id}/save">
<div class="seo-grid seo-grid-2">
""".format(id=site_id) + (
        _f_text("Название", "name", site.get("name", ""), required=True) +
        _f_text("Домен", "domain", site.get("domain", ""), required=True, hint="Без www, без https://. www обрабатывается автоматически.")
    ) + "</div>" + (
        _f_text("Алиасы (домены через запятую)", "aliases", site.get("aliases", ""), hint="Дополнительные домены, которые ведут на этот же сайт. Через запятую.")
    ) + "<div class='seo-grid seo-grid-3'>" + (
        _f_select("Тип", "site_type", site.get("site_type", "client"), [("client","Клиенты"),("staff","Сотрудники"),("other","Другое")]) +
        _f_select("Язык", "language", site.get("language", "en"), [("en","English"),("ru","Русский"),("uk","Українська"),("es","Español")]) +
        _f_select("Статус", "status", site.get("status", "draft"), [("draft","Draft (только превью)"),("live","Live (опубликован)")])
    ) + "</div>" + "<div class='seo-h2'>Брендинг</div>" + "<div class='seo-grid seo-grid-2'>" + (
        _f_text("Brand name", "brand_name", site.get("brand_name", "")) +
        _f_text("Tagline", "tagline", site.get("tagline", ""), hint="Короткий слоган под H1")
    ) + (
        _f_text("Logo URL", "logo_url", site.get("logo_url", "")) +
        _f_text("Favicon URL", "favicon_url", site.get("favicon_url", ""))
    ) + (
        _f_color("Основной цвет", "color_primary", site.get("color_primary", "#7A9B76")) +
        _f_color("Акцентный цвет", "color_secondary", site.get("color_secondary", "#E8DDD0"))
    ) + "</div>" + "<div class='seo-h2'>SEO defaults</div>" + (
        _f_text("Title suffix", "title_suffix", site.get("title_suffix", ""), hint="Добавляется к каждому title (например: ' | RelaxTouch')")
    ) + (
        _f_textarea("Default meta description", "default_meta_description", site.get("default_meta_description", ""), rows=2, hint="Используется на страницах где не задан свой description")
    ) + (
        _f_text("Default OG image URL", "default_og_image", site.get("default_og_image", ""))
    ) + "<div class='seo-h2'>Организация (для Schema.org)</div>" + "<div class='seo-grid seo-grid-2'>" + (
        _f_text("Юрлицо", "org_name", site.get("org_name", ""), hint="Например: RelaxTouch LLC") +
        _f_text("Phone", "org_phone", site.get("org_phone", ""))
    ) + (
        _f_text("Email", "org_email", site.get("org_email", "")) +
        _f_text("Address (короткая строка)", "org_address", site.get("org_address", ""))
    ) + "</div>" + "<div class='seo-h2'>Аналитика</div>" + "<div class='seo-grid seo-grid-3'>" + (
        _f_text("GA4 ID", "ga_id", site.get("ga_id", ""), hint="G-XXXXXXX") +
        _f_text("GTM ID", "gtm_id", site.get("gtm_id", ""), hint="GTM-XXXXX") +
        _f_text("FB Pixel ID", "fb_pixel_id", site.get("fb_pixel_id", ""))
    ) + "</div>" + "<div class='seo-h2'>Соцсети (JSON)</div>" + (
        _f_textarea("social_links", "social_links", site.get("social_links", ""), rows=3, hint='Например: {"instagram":"https://instagram.com/...", "facebook":"https://facebook.com/..."}')
    ) + "<div class='seo-h2'>Кастомный HTML</div>" + (
        _f_textarea("Header HTML (внутри <header>)", "header_html", site.get("header_html", ""), rows=4)
    ) + (
        _f_textarea("Footer HTML (заменяет дефолтный футер)", "footer_html", site.get("footer_html", ""), rows=6)
    ) + '<button class="seo-btn">Сохранить</button> <a href="/seo" class="seo-btn secondary">К списку сайтов</a></form>'

    content = f'<div class="seo-h1">{_esc(site.get("name") or "")}</div>{_site_subnav(site_id, "settings")}{f}'
    return HTMLResponse(_layout(content, request, breadcrumb=f'<a href="/seo">SEO</a> / {_esc(site.get("name") or "")}'))


@router.post("/seo/sites/{site_id}/save")
async def seo_site_save(request: Request, site_id: int):
    user, err = _admin_check(request)
    if err: return err
    form = await request.form()
    fields = ["name", "domain", "aliases", "site_type", "language", "status",
              "brand_name", "tagline", "logo_url", "favicon_url",
              "color_primary", "color_secondary",
              "title_suffix", "default_meta_description", "default_og_image",
              "org_name", "org_phone", "org_email", "org_address",
              "ga_id", "gtm_id", "fb_pixel_id",
              "social_links", "header_html", "footer_html"]
    payload = {k: (form.get(k) or "").strip() for k in fields if k in form}
    if "domain" in payload:
        payload["domain"] = payload["domain"].lower().lstrip("www.")
    try:
        _db.update_seo_site(site_id, **payload)
        return _redirect_to(f"/seo/sites/{site_id}", msg="Сохранено")
    except Exception as e:
        log.error(f"[SEO] site save error: {e}")
        return _redirect_to(f"/seo/sites/{site_id}", err=f"Ошибка: {e}")


@router.post("/seo/sites/{site_id}/delete")
async def seo_site_delete(request: Request, site_id: int):
    user, err = _admin_check(request)
    if err: return err
    try:
        _db.delete_seo_site(site_id)
        return _redirect_to("/seo", msg="Сайт удалён")
    except Exception as e:
        return _redirect_to("/seo", err=f"Ошибка: {e}")


# ════════════════════════════════════════════════════════════════════════════
# LOCATIONS
# ════════════════════════════════════════════════════════════════════════════

@router.get("/seo/sites/{site_id}/locations", response_class=HTMLResponse)
async def seo_locations_list(request: Request, site_id: int):
    user, err = _admin_check(request)
    if err: return err
    site, e = _site_or_404(site_id)
    if e: return e
    locs = _db.get_seo_locations(site_id)
    rows = ""
    for loc in locs:
        st = loc.get("status") or "draft"
        pill_cls = "published" if st == "published" else "draft"
        rows += f"""<tr>
<td><a href="/seo/sites/{site_id}/locations/{loc['id']}" style="color:#fde047">{_esc(loc.get('city') or '')}, {_esc(loc.get('state') or '')}</a><div style="font-size:.72rem;color:var(--text3)">/{_esc(loc.get('slug') or '')}</div></td>
<td><span class="seo-pill {pill_cls}">{st}</span></td>
<td>{_esc((loc.get('updated_at') or '')[:10])}</td>
<td><a href="/seo/sites/{site_id}/locations/{loc['id']}" class="seo-btn sm secondary">Редактировать</a>
<form method="post" action="/seo/sites/{site_id}/locations/{loc['id']}/delete" style="display:inline" onsubmit="return confirm('Удалить локацию?')"><button class="seo-btn sm danger">✕</button></form></td>
</tr>"""
    if not rows:
        rows = '<tr><td colspan="4" style="text-align:center;color:var(--text3);padding:24px">Локаций пока нет. Создайте новую ниже.</td></tr>'

    new_form = f"""<div class="seo-card">
<div class="seo-h2">Новая локация</div>
<form class="seo-form" method="post" action="/seo/sites/{site_id}/locations/new">
<div class="seo-grid seo-grid-3">
{_f_text("City", "city", "", required=True, hint="Например: Los Angeles")}
{_f_text("State (код)", "state", "", required=True, hint="Например: CA")}
{_f_text("Slug (URL)", "slug", "", hint="Если не указано — сгенерируется из city-state")}
</div>
<button class="seo-btn">Создать</button>
</form></div>"""

    content = (f'<div class="seo-h1">{_esc(site.get("name") or "")}</div>'
               f'{_site_subnav(site_id, "locations")}'
               f'<table class="seo-table" style="margin-bottom:24px"><thead>'
               f'<tr><th>Локация</th><th>Статус</th><th>Обновлено</th><th></th></tr>'
               f'</thead><tbody>{rows}</tbody></table>{new_form}')
    return HTMLResponse(_layout(content, request, breadcrumb=f'<a href="/seo">SEO</a> / <a href="/seo/sites/{site_id}">{_esc(site.get("name") or "")}</a> / Локации'))


@router.post("/seo/sites/{site_id}/locations/new")
async def seo_location_new(request: Request, site_id: int,
                            city: str = Form(...),
                            state: str = Form(...),
                            slug: str = Form("")):
    user, err = _admin_check(request)
    if err: return err
    if not slug:
        slug = f"{city.lower().replace(' ', '-')}-{state.lower()}"
    slug = "".join(ch if ch.isalnum() or ch == "-" else "" for ch in slug)
    try:
        new_id = _db.create_seo_location(
            site_id, slug=slug, city=city.strip(), state=state.strip().upper(),
            h1=f"{city.strip()}, {state.strip().upper()}",
            title=f"{city.strip()}, {state.strip().upper()}",
        )
        return _redirect_to(f"/seo/sites/{site_id}/locations/{new_id}", msg="Локация создана")
    except Exception as e:
        return _redirect_to(f"/seo/sites/{site_id}/locations", err=f"Ошибка: {e}")


@router.get("/seo/sites/{site_id}/locations/{loc_id}", response_class=HTMLResponse)
async def seo_location_edit(request: Request, site_id: int, loc_id: int):
    user, err = _admin_check(request)
    if err: return err
    site, e = _site_or_404(site_id)
    if e: return e
    loc = _db.get_seo_location(loc_id)
    if not loc or loc.get("site_id") != site_id:
        return PlainTextResponse("Location not found", status_code=404)

    contacts = _db.get_seo_location_contacts(loc_id, only_active=False)
    contact_rows = ""
    for c in contacts:
        active_pill = '<span class="seo-pill live">on</span>' if c.get("is_active") else '<span class="seo-pill draft">off</span>'
        primary = ' ★' if c.get("is_primary") else ''
        contact_rows += f"""<tr>
<td>{_esc((c.get('contact_type') or '').title())}{primary}</td>
<td>{_esc(c.get('value') or '')}</td>
<td>{_esc(c.get('label') or '')}</td>
<td>{active_pill}</td>
<td><form method="post" action="/seo/sites/{site_id}/locations/{loc_id}/contacts/{c['id']}/delete" style="display:inline" onsubmit="return confirm('Удалить?')"><button class="seo-btn sm danger">✕</button></form></td>
</tr>"""
    if not contact_rows:
        contact_rows = '<tr><td colspan="5" style="text-align:center;color:var(--text3);padding:14px">Контактов пока нет.</td></tr>'

    contact_form = f"""<form class="seo-form" method="post" action="/seo/sites/{site_id}/locations/{loc_id}/contacts/add" style="margin-top:10px">
<div class="seo-grid seo-grid-3">
{_f_select("Тип", "contact_type", "phone", [("phone","Phone"),("telegram","Telegram"),("whatsapp","WhatsApp"),("email","Email"),("sms","SMS")])}
{_f_text("Значение", "value", "", required=True, hint="Phone: +12135550100, TG: @username, WA: +12135550100, Email: a@b.com")}
{_f_text("Label (опц.)", "label", "", hint="Например: Reception, Manager")}
</div>
<div class="seo-grid seo-grid-3">
{_f_text("Display (опц.)", "display_value", "", hint="Как отображать на сайте")}
{_f_text("Position", "position", "0", type="number")}
{_f_checkbox("Primary (выделить)", "is_primary", False)}
</div>
<button class="seo-btn">Добавить контакт</button>
</form>"""

    f1 = f"""<form class="seo-form" method="post" action="/seo/sites/{site_id}/locations/{loc_id}/save">
<div class="seo-grid seo-grid-3">
{_f_text("City", "city", loc.get("city",""), required=True)}
{_f_text("State (код)", "state", loc.get("state",""), required=True)}
{_f_text("State (полностью)", "state_full", loc.get("state_full",""))}
</div>
<div class="seo-grid seo-grid-3">
{_f_text("Slug", "slug", loc.get("slug",""), required=True)}
{_f_text("Country", "country", loc.get("country","US") or "US")}
{_f_select("Статус", "status", loc.get("status","draft"), [("draft","Draft"),("published","Published")])}
</div>
<div class="seo-h2">Адрес</div>
<div class="seo-grid seo-grid-2">
{_f_text("Street", "street", loc.get("street",""))}
{_f_text("Address line 2", "address_line2", loc.get("address_line2",""))}
</div>
<div class="seo-grid seo-grid-3">
{_f_text("ZIP", "zip", loc.get("zip",""))}
{_f_text("Latitude", "latitude", str(loc.get("latitude") or ""))}
{_f_text("Longitude", "longitude", str(loc.get("longitude") or ""))}
</div>
<div class="seo-h2">SEO</div>
{_f_text("Title (вкладка браузера)", "title", loc.get("title",""))}
{_f_text("H1 (заголовок страницы)", "h1", loc.get("h1",""))}
{_f_textarea("Meta description", "meta_description", loc.get("meta_description",""), rows=2)}
{_f_text("OG image URL", "og_image", loc.get("og_image",""))}
<div class="seo-h2">Контент</div>
{_f_textarea("Intro HTML (под H1)", "intro_html", loc.get("intro_html",""), rows=5)}
{_f_textarea("Services HTML", "services_html", loc.get("services_html",""), rows=6)}
{_f_textarea("About studio HTML", "about_studio_html", loc.get("about_studio_html",""), rows=6)}
{_f_textarea("FAQ JSON", "faq_json", loc.get("faq_json","[]"), rows=4, hint='Массив объектов: [{"q":"Question?","a":"Answer."}, ...]')}
{_f_textarea("Hours JSON", "hours_json", loc.get("hours_json",""), rows=4, hint='Например: [{"day":"Mon-Fri","open":"9:00","close":"21:00"}]')}
{_f_textarea("Schema.org JSON-LD (опц., перезаписывает авто)", "schema_json", loc.get("schema_json",""), rows=4)}
{_f_text("Position в списке", "position", str(loc.get("position",0)), type="number")}
<button class="seo-btn">Сохранить</button>
<a href="/seo/sites/{site_id}/locations" class="seo-btn secondary">К списку</a>
</form>"""

    content = (f'<div class="seo-h1">{_esc(loc.get("city",""))}, {_esc(loc.get("state",""))}</div>'
               f'{_site_subnav(site_id, "locations")}{f1}'
               f'<div class="seo-h2" style="margin-top:24px">Контакты</div>'
               f'<table class="seo-table"><thead><tr><th>Тип</th><th>Значение</th><th>Label</th><th>Активен</th><th></th></tr></thead><tbody>{contact_rows}</tbody></table>'
               f'{contact_form}')
    return HTMLResponse(_layout(content, request, breadcrumb=f'<a href="/seo/sites/{site_id}/locations">Локации</a> / {_esc(loc.get("city") or "")}'))


@router.post("/seo/sites/{site_id}/locations/{loc_id}/save")
async def seo_location_save(request: Request, site_id: int, loc_id: int):
    user, err = _admin_check(request)
    if err: return err
    form = await request.form()
    fields = ["slug","city","state","state_full","country","street","address_line2","zip",
              "title","h1","meta_description","og_image",
              "intro_html","services_html","about_studio_html",
              "faq_json","schema_json","hours_json","status"]
    payload = {k: (form.get(k) or "").strip() for k in fields if k in form}
    # Numeric fields
    for k in ("latitude","longitude"):
        v = (form.get(k) or "").strip()
        if v:
            try: payload[k] = float(v)
            except: pass
        else:
            payload[k] = None
    if "position" in form:
        payload["position"] = _safe_int(form.get("position"), 0)
    if payload.get("status") == "published" and not _db.get_seo_location(loc_id).get("published_at"):
        from datetime import datetime
        payload["published_at"] = datetime.utcnow().isoformat()
    try:
        _db.update_seo_location(loc_id, **payload)
        return _redirect_to(f"/seo/sites/{site_id}/locations/{loc_id}", msg="Сохранено")
    except Exception as e:
        log.error(f"[SEO] location save error: {e}")
        return _redirect_to(f"/seo/sites/{site_id}/locations/{loc_id}", err=f"Ошибка: {e}")


@router.post("/seo/sites/{site_id}/locations/{loc_id}/delete")
async def seo_location_delete(request: Request, site_id: int, loc_id: int):
    user, err = _admin_check(request)
    if err: return err
    _db.delete_seo_location(loc_id)
    return _redirect_to(f"/seo/sites/{site_id}/locations", msg="Удалено")


@router.post("/seo/sites/{site_id}/locations/{loc_id}/contacts/add")
async def seo_contact_add(request: Request, site_id: int, loc_id: int,
                           contact_type: str = Form(...),
                           value: str = Form(...),
                           label: str = Form(""),
                           display_value: str = Form(""),
                           position: int = Form(0),
                           is_primary: str = Form("")):
    user, err = _admin_check(request)
    if err: return err
    try:
        _db.add_seo_location_contact(
            loc_id, contact_type, value,
            label=label, display_value=display_value,
            position=position, is_primary=1 if is_primary else 0
        )
        return _redirect_to(f"/seo/sites/{site_id}/locations/{loc_id}", msg="Контакт добавлен")
    except Exception as e:
        return _redirect_to(f"/seo/sites/{site_id}/locations/{loc_id}", err=f"Ошибка: {e}")


@router.post("/seo/sites/{site_id}/locations/{loc_id}/contacts/{contact_id}/delete")
async def seo_contact_delete(request: Request, site_id: int, loc_id: int, contact_id: int):
    user, err = _admin_check(request)
    if err: return err
    _db.delete_seo_location_contact(contact_id)
    return _redirect_to(f"/seo/sites/{site_id}/locations/{loc_id}", msg="Контакт удалён")


# ════════════════════════════════════════════════════════════════════════════
# PAGES (about, contact, privacy, terms, services, etc)
# ════════════════════════════════════════════════════════════════════════════

@router.get("/seo/sites/{site_id}/pages", response_class=HTMLResponse)
async def seo_pages_list(request: Request, site_id: int):
    user, err = _admin_check(request)
    if err: return err
    site, e = _site_or_404(site_id)
    if e: return e
    pages = _db.get_seo_pages(site_id)
    rows = ""
    for p in pages:
        pill = '<span class="seo-pill published">published</span>' if p.get("status") == "published" else '<span class="seo-pill draft">draft</span>'
        rows += f"""<tr>
<td><a href="/seo/sites/{site_id}/pages/{p['id']}" style="color:#fde047">{_esc(p.get('title') or p.get('slug') or '')}</a><div style="font-size:.72rem;color:var(--text3)">/{_esc(p.get('slug') or '')}</div></td>
<td>{_esc(p.get('page_type') or '')}</td>
<td>{pill}</td>
<td><form method="post" action="/seo/sites/{site_id}/pages/{p['id']}/delete" style="display:inline" onsubmit="return confirm('Удалить?')"><button class="seo-btn sm danger">✕</button></form></td>
</tr>"""
    if not rows:
        rows = '<tr><td colspan="4" style="text-align:center;color:var(--text3);padding:20px">Страниц нет.</td></tr>'

    new_form = f"""<div class="seo-card"><div class="seo-h2">Новая страница</div>
<form class="seo-form" method="post" action="/seo/sites/{site_id}/pages/new">
<div class="seo-grid seo-grid-3">
{_f_text("Slug (URL)", "slug", "", required=True, hint="about, privacy, terms, services...")}
{_f_text("Title", "title", "")}
{_f_select("Тип", "page_type", "static", [("static","Static"),("about","About"),("contact","Contact"),("privacy","Privacy"),("terms","Terms"),("service","Service"),("home","Home")])}
</div>
<button class="seo-btn">Создать</button>
</form></div>"""

    content = (f'<div class="seo-h1">{_esc(site.get("name") or "")}</div>'
               f'{_site_subnav(site_id, "pages")}'
               f'<table class="seo-table" style="margin-bottom:24px"><thead><tr>'
               f'<th>Страница</th><th>Тип</th><th>Статус</th><th></th></tr></thead>'
               f'<tbody>{rows}</tbody></table>{new_form}')
    return HTMLResponse(_layout(content, request, breadcrumb=f'<a href="/seo/sites/{site_id}">{_esc(site.get("name") or "")}</a> / Страницы'))


@router.post("/seo/sites/{site_id}/pages/new")
async def seo_page_new(request: Request, site_id: int,
                        slug: str = Form(...),
                        title: str = Form(""),
                        page_type: str = Form("static")):
    user, err = _admin_check(request)
    if err: return err
    slug_clean = "".join(ch if ch.isalnum() or ch == "-" else "" for ch in slug.strip().lower())
    try:
        new_id = _db.create_seo_page(site_id, slug=slug_clean, title=title.strip(),
                                       page_type=page_type, h1=title.strip())
        return _redirect_to(f"/seo/sites/{site_id}/pages/{new_id}", msg="Создано")
    except Exception as e:
        return _redirect_to(f"/seo/sites/{site_id}/pages", err=f"Ошибка: {e}")


@router.get("/seo/sites/{site_id}/pages/{page_id}", response_class=HTMLResponse)
async def seo_page_edit(request: Request, site_id: int, page_id: int):
    user, err = _admin_check(request)
    if err: return err
    site, e = _site_or_404(site_id)
    if e: return e
    page = _db.get_seo_page(page_id)
    if not page or page.get("site_id") != site_id:
        return PlainTextResponse("Page not found", status_code=404)
    f = f"""<form class="seo-form" method="post" action="/seo/sites/{site_id}/pages/{page_id}/save">
<div class="seo-grid seo-grid-3">
{_f_text("Slug", "slug", page.get("slug",""), required=True)}
{_f_select("Тип", "page_type", page.get("page_type","static"), [("static","Static"),("about","About"),("contact","Contact"),("privacy","Privacy"),("terms","Terms"),("service","Service"),("home","Home")])}
{_f_select("Статус", "status", page.get("status","draft"), [("draft","Draft"),("published","Published")])}
</div>
{_f_text("Title", "title", page.get("title",""))}
{_f_text("H1", "h1", page.get("h1",""))}
{_f_textarea("Meta description", "meta_description", page.get("meta_description",""), rows=2)}
{_f_text("OG image URL", "og_image", page.get("og_image",""))}
{_f_text("Canonical URL (опц.)", "canonical_url", page.get("canonical_url",""))}
{_f_textarea("Content HTML", "content_html", page.get("content_html",""), rows=14, hint="Произвольный HTML — параграфы, заголовки, списки, картинки.")}
{_f_textarea("Schema.org JSON-LD (опц.)", "schema_json", page.get("schema_json",""), rows=4)}
<div class="seo-grid seo-grid-3">
{_f_checkbox("Noindex", "noindex", page.get("noindex"))}
{_f_checkbox("Показывать в шапке", "show_in_menu", page.get("show_in_menu"))}
{_f_text("Position", "position", str(page.get("position",0)), type="number")}
</div>
{_f_text("Menu label (если в шапке)", "menu_label", page.get("menu_label",""))}
<button class="seo-btn">Сохранить</button>
<a href="/seo/sites/{site_id}/pages" class="seo-btn secondary">К списку</a>
</form>"""
    content = (f'<div class="seo-h1">{_esc(page.get("title") or page.get("slug") or "")}</div>'
               f'{_site_subnav(site_id, "pages")}{f}')
    return HTMLResponse(_layout(content, request, breadcrumb=f'<a href="/seo/sites/{site_id}/pages">Страницы</a> / {_esc(page.get("slug") or "")}'))


@router.post("/seo/sites/{site_id}/pages/{page_id}/save")
async def seo_page_save(request: Request, site_id: int, page_id: int):
    user, err = _admin_check(request)
    if err: return err
    form = await request.form()
    fields = ["slug","page_type","title","h1","meta_description","og_image",
              "canonical_url","content_html","schema_json","menu_label","status"]
    payload = {k: (form.get(k) or "").strip() for k in fields if k in form}
    payload["noindex"] = 1 if form.get("noindex") else 0
    payload["show_in_menu"] = 1 if form.get("show_in_menu") else 0
    payload["position"] = _safe_int(form.get("position"), 0)
    if payload.get("status") == "published":
        existing = _db.get_seo_page(page_id)
        if existing and not existing.get("published_at"):
            from datetime import datetime
            payload["published_at"] = datetime.utcnow().isoformat()
    try:
        _db.update_seo_page(page_id, **payload)
        return _redirect_to(f"/seo/sites/{site_id}/pages/{page_id}", msg="Сохранено")
    except Exception as e:
        return _redirect_to(f"/seo/sites/{site_id}/pages/{page_id}", err=f"Ошибка: {e}")


@router.post("/seo/sites/{site_id}/pages/{page_id}/delete")
async def seo_page_delete(request: Request, site_id: int, page_id: int):
    user, err = _admin_check(request)
    if err: return err
    _db.delete_seo_page(page_id)
    return _redirect_to(f"/seo/sites/{site_id}/pages", msg="Удалено")


# ════════════════════════════════════════════════════════════════════════════
# ARTICLES (blog)
# ════════════════════════════════════════════════════════════════════════════

@router.get("/seo/sites/{site_id}/articles", response_class=HTMLResponse)
async def seo_articles_list(request: Request, site_id: int):
    user, err = _admin_check(request)
    if err: return err
    site, e = _site_or_404(site_id)
    if e: return e
    arts = _db.get_seo_articles(site_id)
    cats = {c["id"]: c["name"] for c in _db.get_seo_categories(site_id)}
    rows = ""
    for a in arts:
        pill = '<span class="seo-pill published">published</span>' if a.get("status") == "published" else '<span class="seo-pill draft">draft</span>'
        cat_label = cats.get(a.get("category_id")) or "—"
        rows += f"""<tr>
<td><a href="/seo/sites/{site_id}/articles/{a['id']}" style="color:#fde047">{_esc(a.get('title') or a.get('slug') or '')}</a><div style="font-size:.72rem;color:var(--text3)">/blog/{_esc(a.get('slug') or '')}</div></td>
<td>{_esc(cat_label)}</td>
<td>{pill}</td>
<td>{_esc((a.get('published_at') or a.get('created_at') or '')[:10])}</td>
<td>{a.get('view_count', 0)}</td>
<td><form method="post" action="/seo/sites/{site_id}/articles/{a['id']}/delete" style="display:inline" onsubmit="return confirm('Удалить?')"><button class="seo-btn sm danger">✕</button></form></td>
</tr>"""
    if not rows:
        rows = '<tr><td colspan="6" style="text-align:center;color:var(--text3);padding:20px">Статей нет.</td></tr>'

    new_form = f"""<div class="seo-card"><div class="seo-h2">Новая статья</div>
<form class="seo-form" method="post" action="/seo/sites/{site_id}/articles/new">
<div class="seo-grid seo-grid-2">
{_f_text("Title", "title", "", required=True)}
{_f_text("Slug", "slug", "", hint="Если пусто — сгенерируется из title")}
</div>
<button class="seo-btn">Создать (как draft)</button>
</form></div>"""

    content = (f'<div class="seo-h1">{_esc(site.get("name") or "")}</div>'
               f'{_site_subnav(site_id, "articles")}'
               f'<table class="seo-table" style="margin-bottom:24px"><thead><tr>'
               f'<th>Заголовок</th><th>Рубрика</th><th>Статус</th><th>Дата</th><th>Просмотры</th><th></th></tr></thead>'
               f'<tbody>{rows}</tbody></table>{new_form}')
    return HTMLResponse(_layout(content, request, breadcrumb=f'<a href="/seo/sites/{site_id}">{_esc(site.get("name") or "")}</a> / Статьи'))


def _slugify(s: str) -> str:
    s = (s or "").lower().strip()
    out = []
    for ch in s:
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "_"):
            out.append("-")
    res = "".join(out)
    while "--" in res:
        res = res.replace("--", "-")
    return res.strip("-")[:80]


@router.post("/seo/sites/{site_id}/articles/new")
async def seo_article_new(request: Request, site_id: int,
                           title: str = Form(...),
                           slug: str = Form("")):
    user, err = _admin_check(request)
    if err: return err
    slug = _slugify(slug or title)
    try:
        new_id = _db.create_seo_article(site_id, slug=slug, title=title.strip(),
                                         h1=title.strip(), status="draft")
        return _redirect_to(f"/seo/sites/{site_id}/articles/{new_id}", msg="Создано")
    except Exception as e:
        return _redirect_to(f"/seo/sites/{site_id}/articles", err=f"Ошибка: {e}")


@router.get("/seo/sites/{site_id}/articles/{art_id}", response_class=HTMLResponse)
async def seo_article_edit(request: Request, site_id: int, art_id: int):
    user, err = _admin_check(request)
    if err: return err
    site, e = _site_or_404(site_id)
    if e: return e
    art = _db.get_seo_article(art_id)
    if not art or art.get("site_id") != site_id:
        return PlainTextResponse("Article not found", status_code=404)
    cats = _db.get_seo_categories(site_id)
    authors = _db.get_seo_authors(site_id)
    cat_opts = [("", "— Без рубрики —")] + [(str(c["id"]), c["name"]) for c in cats]
    auth_opts = [("", "— Без автора —")] + [(str(a["id"]), a["name"]) for a in authors]
    f = f"""<form class="seo-form" method="post" action="/seo/sites/{site_id}/articles/{art_id}/save">
<div class="seo-grid seo-grid-3">
{_f_text("Slug", "slug", art.get("slug",""), required=True)}
{_f_select("Рубрика", "category_id", str(art.get("category_id") or ""), cat_opts)}
{_f_select("Автор", "author_id", str(art.get("author_id") or ""), auth_opts)}
</div>
<div class="seo-grid seo-grid-2">
{_f_select("Статус", "status", art.get("status","draft"), [("draft","Draft"),("published","Published")])}
{_f_text("Published at (опц.)", "published_at", art.get("published_at","") or "", hint="ISO datetime — заполнится автоматически при публикации")}
</div>
{_f_text("Title", "title", art.get("title",""), required=True)}
{_f_text("H1", "h1", art.get("h1",""))}
{_f_textarea("Excerpt (короткое описание для карточек)", "excerpt", art.get("excerpt",""), rows=3)}
{_f_textarea("Meta description (для Google)", "meta_description", art.get("meta_description",""), rows=2)}
{_f_text("OG image URL", "og_image", art.get("og_image",""))}
{_f_text("Canonical URL (опц.)", "canonical_url", art.get("canonical_url",""))}
{_f_text("Tags (через запятую)", "tags", art.get("tags",""))}
{_f_textarea("Content HTML", "content_html", art.get("content_html",""), rows=24, hint="Произвольный HTML с заголовками H2/H3, параграфами, списками, картинками. Один H1 ставится автоматически.")}
{_f_textarea("Schema.org JSON-LD (опц.)", "schema_json", art.get("schema_json",""), rows=4)}
<div class="seo-grid seo-grid-2">
{_f_checkbox("Noindex", "noindex", art.get("noindex"))}
{_f_checkbox("Pillar (cornerstone-статья)", "is_pillar", art.get("is_pillar"))}
</div>
<button class="seo-btn">Сохранить</button>
<a href="/seo/sites/{site_id}/articles" class="seo-btn secondary">К списку</a>
</form>"""
    content = (f'<div class="seo-h1">{_esc(art.get("title") or art.get("slug") or "")}</div>'
               f'{_site_subnav(site_id, "articles")}{f}')
    return HTMLResponse(_layout(content, request, breadcrumb=f'<a href="/seo/sites/{site_id}/articles">Статьи</a> / {_esc(art.get("slug") or "")}'))


@router.post("/seo/sites/{site_id}/articles/{art_id}/save")
async def seo_article_save(request: Request, site_id: int, art_id: int):
    user, err = _admin_check(request)
    if err: return err
    form = await request.form()
    fields = ["slug","title","h1","meta_description","og_image","canonical_url",
              "excerpt","content_html","schema_json","tags","status","published_at"]
    payload = {k: (form.get(k) or "").strip() for k in fields if k in form}
    cid = (form.get("category_id") or "").strip()
    payload["category_id"] = int(cid) if cid else None
    aid = (form.get("author_id") or "").strip()
    payload["author_id"] = int(aid) if aid else None
    payload["noindex"] = 1 if form.get("noindex") else 0
    payload["is_pillar"] = 1 if form.get("is_pillar") else 0
    if payload.get("status") == "published" and not payload.get("published_at"):
        from datetime import datetime
        payload["published_at"] = datetime.utcnow().isoformat()
    try:
        _db.update_seo_article(art_id, **payload)
        return _redirect_to(f"/seo/sites/{site_id}/articles/{art_id}", msg="Сохранено")
    except Exception as e:
        return _redirect_to(f"/seo/sites/{site_id}/articles/{art_id}", err=f"Ошибка: {e}")


@router.post("/seo/sites/{site_id}/articles/{art_id}/delete")
async def seo_article_delete(request: Request, site_id: int, art_id: int):
    user, err = _admin_check(request)
    if err: return err
    _db.delete_seo_article(art_id)
    return _redirect_to(f"/seo/sites/{site_id}/articles", msg="Удалено")


# ════════════════════════════════════════════════════════════════════════════
# CATEGORIES
# ════════════════════════════════════════════════════════════════════════════

@router.get("/seo/sites/{site_id}/categories", response_class=HTMLResponse)
async def seo_cats(request: Request, site_id: int):
    user, err = _admin_check(request)
    if err: return err
    site, e = _site_or_404(site_id)
    if e: return e
    cats = _db.get_seo_categories(site_id)
    rows = ""
    for c in cats:
        rows += f"""<tr>
<td><b>{_esc(c.get('name') or '')}</b><div style="font-size:.72rem;color:var(--text3)">/blog/category/{_esc(c.get('slug') or '')}</div></td>
<td>{_esc(c.get('description') or '')[:80]}</td>
<td>
<form method="post" action="/seo/sites/{site_id}/categories/{c['id']}/save" class="seo-form" style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">
<input type="text" name="name" value="{_esc(c.get('name',''))}" style="width:160px">
<input type="text" name="slug" value="{_esc(c.get('slug',''))}" style="width:130px">
<button class="seo-btn sm">Save</button>
</form>
<form method="post" action="/seo/sites/{site_id}/categories/{c['id']}/delete" style="display:inline" onsubmit="return confirm('Удалить рубрику?')"><button class="seo-btn sm danger">✕</button></form>
</td>
</tr>"""
    if not rows:
        rows = '<tr><td colspan="3" style="text-align:center;color:var(--text3);padding:20px">Рубрик нет.</td></tr>'

    new_form = f"""<div class="seo-card"><div class="seo-h2">Новая рубрика</div>
<form class="seo-form" method="post" action="/seo/sites/{site_id}/categories/new">
<div class="seo-grid seo-grid-2">
{_f_text("Name", "name", "", required=True)}
{_f_text("Slug", "slug", "", hint="Сгенерируется автоматически если пусто")}
</div>
{_f_textarea("Description", "description", "", rows=2)}
<button class="seo-btn">Создать</button>
</form></div>"""

    content = (f'<div class="seo-h1">{_esc(site.get("name") or "")}</div>'
               f'{_site_subnav(site_id, "categories")}'
               f'<table class="seo-table" style="margin-bottom:24px"><thead><tr>'
               f'<th>Рубрика</th><th>Описание</th><th></th></tr></thead>'
               f'<tbody>{rows}</tbody></table>{new_form}')
    return HTMLResponse(_layout(content, request, breadcrumb=f'<a href="/seo/sites/{site_id}">{_esc(site.get("name") or "")}</a> / Рубрики'))


@router.post("/seo/sites/{site_id}/categories/new")
async def seo_cat_new(request: Request, site_id: int,
                       name: str = Form(...),
                       slug: str = Form(""),
                       description: str = Form("")):
    user, err = _admin_check(request)
    if err: return err
    slug = _slugify(slug or name)
    try:
        _db.create_seo_category(site_id, slug=slug, name=name.strip(),
                                  description=description.strip())
        return _redirect_to(f"/seo/sites/{site_id}/categories", msg="Создано")
    except Exception as e:
        return _redirect_to(f"/seo/sites/{site_id}/categories", err=f"Ошибка: {e}")


@router.post("/seo/sites/{site_id}/categories/{cat_id}/save")
async def seo_cat_save(request: Request, site_id: int, cat_id: int,
                        name: str = Form(...), slug: str = Form(...)):
    user, err = _admin_check(request)
    if err: return err
    try:
        _db.update_seo_category(cat_id, name=name.strip(), slug=_slugify(slug))
        return _redirect_to(f"/seo/sites/{site_id}/categories", msg="Сохранено")
    except Exception as e:
        return _redirect_to(f"/seo/sites/{site_id}/categories", err=f"Ошибка: {e}")


@router.post("/seo/sites/{site_id}/categories/{cat_id}/delete")
async def seo_cat_delete(request: Request, site_id: int, cat_id: int):
    user, err = _admin_check(request)
    if err: return err
    _db.delete_seo_category(cat_id)
    return _redirect_to(f"/seo/sites/{site_id}/categories", msg="Удалено")


# ════════════════════════════════════════════════════════════════════════════
# AUTHORS
# ════════════════════════════════════════════════════════════════════════════

@router.get("/seo/sites/{site_id}/authors", response_class=HTMLResponse)
async def seo_authors_list(request: Request, site_id: int):
    user, err = _admin_check(request)
    if err: return err
    site, e = _site_or_404(site_id)
    if e: return e
    authors = _db.get_seo_authors(site_id)
    rows = ""
    for a in authors:
        rows += f"""<tr>
<td><a href="/seo/sites/{site_id}/authors/{a['id']}" style="color:#fde047">{_esc(a.get('name') or '')}</a></td>
<td>{_esc(a.get('credentials') or '')}</td>
<td><form method="post" action="/seo/sites/{site_id}/authors/{a['id']}/delete" style="display:inline" onsubmit="return confirm('Удалить?')"><button class="seo-btn sm danger">✕</button></form></td>
</tr>"""
    if not rows:
        rows = '<tr><td colspan="3" style="text-align:center;color:var(--text3);padding:20px">Авторов нет.</td></tr>'

    new_form = f"""<div class="seo-card"><div class="seo-h2">Новый автор</div>
<form class="seo-form" method="post" action="/seo/sites/{site_id}/authors/new">
<div class="seo-grid seo-grid-2">
{_f_text("Name", "name", "", required=True)}
{_f_text("Slug", "slug", "")}
</div>
<button class="seo-btn">Создать</button>
</form></div>"""

    content = (f'<div class="seo-h1">{_esc(site.get("name") or "")}</div>'
               f'{_site_subnav(site_id, "authors")}'
               f'<table class="seo-table" style="margin-bottom:24px"><thead><tr>'
               f'<th>Имя</th><th>Credentials</th><th></th></tr></thead>'
               f'<tbody>{rows}</tbody></table>{new_form}')
    return HTMLResponse(_layout(content, request, breadcrumb=f'<a href="/seo/sites/{site_id}">{_esc(site.get("name") or "")}</a> / Авторы'))


@router.post("/seo/sites/{site_id}/authors/new")
async def seo_author_new(request: Request, site_id: int,
                          name: str = Form(...), slug: str = Form("")):
    user, err = _admin_check(request)
    if err: return err
    slug = _slugify(slug or name)
    try:
        new_id = _db.create_seo_author(site_id, slug=slug, name=name.strip())
        return _redirect_to(f"/seo/sites/{site_id}/authors/{new_id}", msg="Создано")
    except Exception as e:
        return _redirect_to(f"/seo/sites/{site_id}/authors", err=f"Ошибка: {e}")


@router.get("/seo/sites/{site_id}/authors/{auth_id}", response_class=HTMLResponse)
async def seo_author_edit(request: Request, site_id: int, auth_id: int):
    user, err = _admin_check(request)
    if err: return err
    site, e = _site_or_404(site_id)
    if e: return e
    a = _db.get_seo_author(auth_id)
    if not a or a.get("site_id") != site_id:
        return PlainTextResponse("Author not found", status_code=404)
    f = f"""<form class="seo-form" method="post" action="/seo/sites/{site_id}/authors/{auth_id}/save">
<div class="seo-grid seo-grid-2">
{_f_text("Name", "name", a.get("name",""), required=True)}
{_f_text("Slug", "slug", a.get("slug",""), required=True)}
</div>
{_f_text("Credentials (LMT, NCBTMB и т.п.)", "credentials", a.get("credentials",""))}
{_f_text("Avatar URL", "avatar_url", a.get("avatar_url",""))}
{_f_textarea("Bio (HTML)", "bio_html", a.get("bio_html",""), rows=8)}
{_f_textarea("Social links (JSON)", "social_links", a.get("social_links",""), rows=3)}
<button class="seo-btn">Сохранить</button>
<a href="/seo/sites/{site_id}/authors" class="seo-btn secondary">К списку</a>
</form>"""
    content = (f'<div class="seo-h1">{_esc(a.get("name") or "")}</div>'
               f'{_site_subnav(site_id, "authors")}{f}')
    return HTMLResponse(_layout(content, request, breadcrumb=f'<a href="/seo/sites/{site_id}/authors">Авторы</a> / {_esc(a.get("name") or "")}'))


@router.post("/seo/sites/{site_id}/authors/{auth_id}/save")
async def seo_author_save(request: Request, site_id: int, auth_id: int):
    user, err = _admin_check(request)
    if err: return err
    form = await request.form()
    fields = ["slug","name","credentials","avatar_url","bio_html","social_links"]
    payload = {k: (form.get(k) or "").strip() for k in fields if k in form}
    try:
        _db.update_seo_author(auth_id, **payload)
        return _redirect_to(f"/seo/sites/{site_id}/authors/{auth_id}", msg="Сохранено")
    except Exception as e:
        return _redirect_to(f"/seo/sites/{site_id}/authors/{auth_id}", err=f"Ошибка: {e}")


@router.post("/seo/sites/{site_id}/authors/{auth_id}/delete")
async def seo_author_delete(request: Request, site_id: int, auth_id: int):
    user, err = _admin_check(request)
    if err: return err
    _db.delete_seo_author(auth_id)
    return _redirect_to(f"/seo/sites/{site_id}/authors", msg="Удалено")


# ════════════════════════════════════════════════════════════════════════════
# REDIRECTS
# ════════════════════════════════════════════════════════════════════════════

@router.get("/seo/sites/{site_id}/redirects", response_class=HTMLResponse)
async def seo_redirects_list(request: Request, site_id: int):
    user, err = _admin_check(request)
    if err: return err
    site, e = _site_or_404(site_id)
    if e: return e
    reds = _db.get_seo_redirects(site_id)
    rows = ""
    for r in reds:
        rows += f"""<tr>
<td><code>{_esc(r.get('from_path') or '')}</code></td>
<td>→ <code>{_esc(r.get('to_path') or '')}</code></td>
<td>{r.get('status_code', 301)}</td>
<td>{r.get('hits', 0)}</td>
<td><form method="post" action="/seo/sites/{site_id}/redirects/{r['id']}/delete" style="display:inline" onsubmit="return confirm('Удалить?')"><button class="seo-btn sm danger">✕</button></form></td>
</tr>"""
    if not rows:
        rows = '<tr><td colspan="5" style="text-align:center;color:var(--text3);padding:20px">Редиректов нет.</td></tr>'

    new_form = f"""<div class="seo-card"><div class="seo-h2">Новый редирект</div>
<form class="seo-form" method="post" action="/seo/sites/{site_id}/redirects/new">
<div class="seo-grid seo-grid-3">
{_f_text("From path", "from_path", "", required=True, hint="Например: /old-url")}
{_f_text("To path", "to_path", "", required=True, hint="Например: /new-url или https://...")}
{_f_select("Код", "status_code", "301", [("301","301 Permanent"),("302","302 Temporary")])}
</div>
<button class="seo-btn">Создать</button>
</form></div>"""

    content = (f'<div class="seo-h1">{_esc(site.get("name") or "")}</div>'
               f'{_site_subnav(site_id, "redirects")}'
               f'<table class="seo-table" style="margin-bottom:24px"><thead><tr>'
               f'<th>From</th><th>To</th><th>Code</th><th>Hits</th><th></th></tr></thead>'
               f'<tbody>{rows}</tbody></table>{new_form}')
    return HTMLResponse(_layout(content, request, breadcrumb=f'<a href="/seo/sites/{site_id}">{_esc(site.get("name") or "")}</a> / Редиректы'))


@router.post("/seo/sites/{site_id}/redirects/new")
async def seo_red_new(request: Request, site_id: int,
                       from_path: str = Form(...),
                       to_path: str = Form(...),
                       status_code: int = Form(301)):
    user, err = _admin_check(request)
    if err: return err
    try:
        _db.create_seo_redirect(site_id, from_path.strip(), to_path.strip(), status_code)
        return _redirect_to(f"/seo/sites/{site_id}/redirects", msg="Создано")
    except Exception as e:
        return _redirect_to(f"/seo/sites/{site_id}/redirects", err=f"Ошибка: {e}")


@router.post("/seo/sites/{site_id}/redirects/{red_id}/delete")
async def seo_red_delete(request: Request, site_id: int, red_id: int):
    user, err = _admin_check(request)
    if err: return err
    _db.delete_seo_redirect(red_id)
    return _redirect_to(f"/seo/sites/{site_id}/redirects", msg="Удалено")


# ════════════════════════════════════════════════════════════════════════════
# PREVIEW (admin-only) — рендерит сайт в режиме preview, минуя домен
# ════════════════════════════════════════════════════════════════════════════

@router.get("/seo/preview/{site_id}/", response_class=HTMLResponse)
@router.get("/seo/preview/{site_id}", response_class=HTMLResponse)
async def seo_preview_root(request: Request, site_id: int):
    return await _seo_preview(request, site_id, "/")


@router.get("/seo/preview/{site_id}/{rest:path}")
async def seo_preview_path(request: Request, site_id: int, rest: str):
    return await _seo_preview(request, site_id, "/" + (rest or "").lstrip("/"))


async def _seo_preview(request: Request, site_id: int, path: str):
    user, err = _admin_check(request)
    if err: return err
    site, e = _site_or_404(site_id)
    if e: return e
    return await dispatch_seo_request(request, site, preview=True, preview_path=path)


# ════════════════════════════════════════════════════════════════════════════
# BULK IMPORT — заливка контента из JSON одним кликом
# ════════════════════════════════════════════════════════════════════════════

@router.get("/seo/sites/{site_id}/import", response_class=HTMLResponse)
async def seo_import_form(request: Request, site_id: int):
    user, err = _admin_check(request)
    if err: return err
    site, e = _site_or_404(site_id)
    if e: return e
    content = f'''
<div class="seo-h1">{_esc(site.get("name") or "")}</div>
{_site_subnav(site_id, "settings")}
<div class="seo-card" style="margin-top:18px">
<div class="seo-h2">Bulk-import: залить контент из JSON</div>
<p style="color:var(--text2);font-size:.88rem;margin-bottom:12px">
Вставь JSON ниже. Поддерживаемые секции: <code>site_settings</code>, <code>categories</code>,
<code>authors</code>, <code>locations</code>, <code>pages</code>, <code>articles</code>.
Каждая — массив объектов (кроме site_settings — это объект).
</p>
<p style="color:var(--text3);font-size:.78rem;margin-bottom:12px">
По умолчанию существующие записи (по slug) <b>пропускаются</b>. Включи галку чтобы перезаписывать.
</p>
<form class="seo-form" method="post" action="/seo/sites/{site_id}/import">
<div class="field"><label>JSON</label><textarea name="json_data" rows="22" placeholder='{{"site_settings":{{"brand_name":"..."}},"locations":[...]}}' required></textarea></div>
<div class="field"><label class="checkbox"><input type="checkbox" name="update_existing" value="1"> Перезаписывать существующие (по slug)</label></div>
<button class="seo-btn">Импортировать</button>
<a href="/seo/sites/{site_id}" class="seo-btn secondary">Отмена</a>
</form>
</div>
'''
    return HTMLResponse(_layout(content, request, breadcrumb=f'<a href="/seo/sites/{site_id}">{_esc(site.get("name") or "")}</a> / Import'))


@router.post("/seo/sites/{site_id}/import")
async def seo_import_run(request: Request, site_id: int,
                          json_data: str = Form(...),
                          update_existing: str = Form("")):
    user, err = _admin_check(request)
    if err: return err
    site, e = _site_or_404(site_id)
    if e: return e

    try:
        data = _json.loads(json_data)
    except Exception as ex:
        return _redirect_to(f"/seo/sites/{site_id}/import", err=f"Невалидный JSON: {ex}")

    update = bool(update_existing)
    counts = {"settings": 0, "cats": 0, "authors": 0, "locs": 0,
              "pages": 0, "arts": 0, "skipped": 0, "errors": []}

    try:
        # 1. Site settings
        if isinstance(data.get("site_settings"), dict):
            try:
                _db.update_seo_site(site_id, **data["site_settings"])
                counts["settings"] = 1
            except Exception as ex:
                counts["errors"].append(f"site_settings: {ex}")

        # 2. Categories (slug → id мапим для articles)
        cat_slug_to_id = {c["slug"]: c["id"] for c in _db.get_seo_categories(site_id)}
        for c in (data.get("categories") or []):
            slug = (c.get("slug") or "").strip()
            if not slug: continue
            try:
                if slug in cat_slug_to_id:
                    if update:
                        _db.update_seo_category(cat_slug_to_id[slug],
                            **{k: v for k, v in c.items() if k != "slug"})
                        counts["cats"] += 1
                    else:
                        counts["skipped"] += 1
                else:
                    new_id = _db.create_seo_category(
                        site_id, slug=slug, name=c.get("name", slug),
                        **{k: v for k, v in c.items() if k not in ("slug", "name")}
                    )
                    cat_slug_to_id[slug] = new_id
                    counts["cats"] += 1
            except Exception as ex:
                counts["errors"].append(f"category {slug}: {ex}")

        # 3. Authors
        author_slug_to_id = {a["slug"]: a["id"] for a in _db.get_seo_authors(site_id)}
        for a in (data.get("authors") or []):
            slug = (a.get("slug") or "").strip()
            if not slug: continue
            try:
                if slug in author_slug_to_id:
                    if update:
                        _db.update_seo_author(author_slug_to_id[slug],
                            **{k: v for k, v in a.items() if k != "slug"})
                        counts["authors"] += 1
                    else:
                        counts["skipped"] += 1
                else:
                    new_id = _db.create_seo_author(
                        site_id, slug=slug, name=a.get("name", slug),
                        **{k: v for k, v in a.items() if k not in ("slug", "name")}
                    )
                    author_slug_to_id[slug] = new_id
                    counts["authors"] += 1
            except Exception as ex:
                counts["errors"].append(f"author {slug}: {ex}")

        # 4. Locations
        existing_loc = {l["slug"]: l["id"] for l in _db.get_seo_locations(site_id)}
        for loc in (data.get("locations") or []):
            slug = (loc.get("slug") or "").strip()
            if not slug: continue
            try:
                payload = {k: v for k, v in loc.items() if k != "slug"}
                if "faq_json" in payload and not isinstance(payload["faq_json"], str):
                    payload["faq_json"] = _json.dumps(payload["faq_json"], ensure_ascii=False)
                if "hours_json" in payload and not isinstance(payload["hours_json"], str):
                    payload["hours_json"] = _json.dumps(payload["hours_json"], ensure_ascii=False)
                if slug in existing_loc:
                    if update:
                        _db.update_seo_location(existing_loc[slug], **payload)
                        counts["locs"] += 1
                    else:
                        counts["skipped"] += 1
                else:
                    _db.create_seo_location(
                        site_id, slug=slug,
                        city=loc.get("city", ""), state=loc.get("state", ""),
                        **{k: v for k, v in payload.items() if k not in ("city", "state")}
                    )
                    counts["locs"] += 1
            except Exception as ex:
                counts["errors"].append(f"location {slug}: {ex}")

        # 5. Pages
        existing_pages = {p["slug"]: p["id"] for p in _db.get_seo_pages(site_id)}
        for p in (data.get("pages") or []):
            slug = (p.get("slug") or "").strip()
            if not slug: continue
            try:
                payload = {k: v for k, v in p.items() if k != "slug"}
                if slug in existing_pages:
                    if update:
                        _db.update_seo_page(existing_pages[slug], **payload)
                        counts["pages"] += 1
                    else:
                        counts["skipped"] += 1
                else:
                    _db.create_seo_page(site_id, slug=slug, **payload)
                    counts["pages"] += 1
            except Exception as ex:
                counts["errors"].append(f"page {slug}: {ex}")

        # 6. Articles (резолвим category_slug / author_slug → id)
        existing_arts = {a["slug"]: a["id"] for a in _db.get_seo_articles(site_id)}
        for art in (data.get("articles") or []):
            slug = (art.get("slug") or "").strip()
            if not slug: continue
            try:
                payload = dict(art)
                payload.pop("slug", None)
                # Резолв slug → id
                cs = payload.pop("category_slug", None)
                if cs and cs in cat_slug_to_id:
                    payload["category_id"] = cat_slug_to_id[cs]
                au = payload.pop("author_slug", None)
                if au and au in author_slug_to_id:
                    payload["author_id"] = author_slug_to_id[au]
                if slug in existing_arts:
                    if update:
                        _db.update_seo_article(existing_arts[slug], **payload)
                        counts["arts"] += 1
                    else:
                        counts["skipped"] += 1
                else:
                    title = payload.pop("title", slug)
                    _db.create_seo_article(site_id, slug=slug, title=title, **payload)
                    counts["arts"] += 1
            except Exception as ex:
                counts["errors"].append(f"article {slug}: {ex}")

    except Exception as ex:
        log.error(f"[SEO] import fatal: {ex}", exc_info=True)
        return _redirect_to(f"/seo/sites/{site_id}/import", err=f"Fatal: {ex}")

    # Сборка отчёта
    msg_parts = []
    if counts["settings"]: msg_parts.append("настройки сайта")
    if counts["cats"]:    msg_parts.append(f"рубрики: {counts['cats']}")
    if counts["authors"]: msg_parts.append(f"авторы: {counts['authors']}")
    if counts["locs"]:    msg_parts.append(f"локации: {counts['locs']}")
    if counts["pages"]:   msg_parts.append(f"страницы: {counts['pages']}")
    if counts["arts"]:    msg_parts.append(f"статьи: {counts['arts']}")
    if counts["skipped"]: msg_parts.append(f"пропущено: {counts['skipped']}")
    summary = "Импорт: " + (", ".join(msg_parts) if msg_parts else "ничего не залилось")
    if counts["errors"]:
        first_err = counts["errors"][0][:120]
        return _redirect_to(f"/seo/sites/{site_id}/import",
                            err=f"{summary}. Ошибок: {len(counts['errors'])}. Первая: {first_err}")
    return _redirect_to(f"/seo/sites/{site_id}", msg=summary)
