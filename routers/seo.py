"""
routers/seo.py
SEO-модуль: публичный диспетчер запросов и админка.

Этот модуль НЕ модифицирует поведение существующих роутеров (chat_*,
analytics, staff, channels, projects и т.д.). Он только добавляет
новые маршруты и предоставляет функцию dispatch_seo_request, которую
вызовет CustomDomainMiddleware (Коммит 4) при заходе на SEO-домен.

В этом коммите экспортируются:
- dispatch_seo_request(request, site)  — основная точка входа из middleware
- router (APIRouter)                    — пока без зарегистрированных маршрутов
- setup(db, *, app_url=None)            — инициализатор зависимостей
"""
import logging
from urllib.parse import unquote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response

import seo_templates as tpl

log = logging.getLogger(__name__)

router = APIRouter()

_db = None
_app_url: str = ""


def setup(db, *, app_url: str = ""):
    global _db, _app_url
    _db = db
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

async def dispatch_seo_request(request: Request, site: dict) -> Response:
    """Главная точка входа из CustomDomainMiddleware.

    Принимает уже сматченный сайт (по домену) и текущий request,
    возвращает Response (HTML / XML / redirect / 404).

    Внутри ловим все исключения и при ошибках возвращаем 500 без падения
    middleware — чтобы баги в SEO-модуле не задели остальной траффик.
    """
    if not _db:
        return PlainTextResponse("SEO module not initialized", status_code=500)

    try:
        path = _normalize_path(request.url.path)

        # Только опубликованные сайты обслуживаем (если не draft с явным разрешением)
        if site.get("status") != "live":
            # Drafts отдают 404 для публики — превью только через админку (Коммит 3)
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

        menu_pages = _menu_pages_for(site)

        # Корень — главная сайта
        if path == "/" or path == "":
            locations = _db.get_seo_locations(site["id"], status="published")
            articles = _db.get_seo_articles(site["id"], status="published", limit=6)
            html = tpl.render_seo_home(site, locations, articles, menu_pages)
            return HTMLResponse(html)

        # Блог-индекс
        if path == "/blog":
            articles = _db.get_seo_articles(site["id"], status="published", limit=50)
            categories = _db.get_seo_categories(site["id"])
            html = tpl.render_seo_blog_index(site, articles, categories, menu_pages)
            return HTMLResponse(html)

        # Блог по категории: /blog/category/<slug>
        if path.startswith("/blog/category/"):
            cat_slug = path[len("/blog/category/"):].split("/", 1)[0]
            category = _db.get_seo_category_by_slug(site["id"], cat_slug)
            if not category:
                return _render_404(site, menu_pages)
            articles = _db.get_seo_articles(site["id"], status="published",
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
            if not article or article.get("status") != "published":
                return _render_404(site, menu_pages)
            author = None
            if article.get("author_id"):
                author = _db.get_seo_author(article["author_id"])
            category = None
            if article.get("category_id"):
                category = _db.get_seo_category(article["category_id"])
            related = _db.get_seo_articles(
                site["id"], status="published",
                category_id=article.get("category_id"), limit=4
            )
            related = [r for r in related if r["id"] != article["id"]][:3]
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
        if location and location.get("status") == "published":
            contacts = _db.get_seo_location_contacts(location["id"], only_active=True)
            html = tpl.render_seo_location(site, location, contacts, menu_pages)
            return HTMLResponse(html)

        # Затем — статические страницы
        page = _db.get_seo_page_by_slug(site["id"], slug)
        if page and page.get("status") == "published":
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
