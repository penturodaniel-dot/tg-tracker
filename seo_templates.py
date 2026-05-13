"""
seo_templates.py
SEO-модуль: чистые HTML-рендереры публичных страниц.

Все функции принимают dict'ы (site, location, page, article и т.п.)
и возвращают строку HTML или XML. Никакой бизнес-логики, никаких
обращений к БД — только рендер. Бизнес-логика — в routers/seo.py.

Палитра и типографика подключены через CSS-переменные на :root,
тянутся из site.color_primary / color_secondary. Шрифты — Google Fonts
с font-display: swap для скорости.
"""
import html as _html
import json as _json
import re as _re
from datetime import datetime


# ── Утилиты ──────────────────────────────────────────────────────────────────

def _esc(s) -> str:
    if s is None:
        return ""
    return _html.escape(str(s), quote=True)


def _optimize_img_url(url: str) -> str:
    """Если URL — Cloudinary CDN, инжектим transform `f_auto,q_auto`
    (auto-WebP/AVIF + автоматическая оптимизация качества).
    Не-Cloudinary URLы возвращает как есть."""
    if not url or "res.cloudinary.com" not in url or "/upload/" not in url:
        return url
    if "/upload/f_auto" in url or "/upload/q_auto" in url:
        return url
    return url.replace("/upload/", "/upload/f_auto,q_auto/", 1)


def _render_team_section(site: dict) -> str:
    """Универсальный «Our Team» блок. Берёт team_html из настроек сайта.
    Если поле пустое — ничего не рендерит. Используется на всех страницах
    перед футером — задаётся 1 раз, видно везде."""
    team_html = (site.get("team_html") or "").strip()
    if not team_html:
        return ""
    return (
        '<section style="padding:56px 0;background:var(--surface,#FDF7FB)">'
        '<div class="container">'
        f'{team_html}'
        '</div></section>'
    )


def _site_url(site: dict, path: str = "/") -> str:
    domain = (site.get("domain") or "").strip().lower()
    if domain.startswith("www."):
        domain = domain[4:]
    if not domain:
        return path
    p = "/" + (path or "/").lstrip("/")
    return f"https://{domain}{p}"


def _format_contact(contact: dict) -> dict:
    ctype = (contact.get("contact_type") or "").lower()
    value = (contact.get("value") or "").strip()
    label = (contact.get("label") or "").strip()
    display = (contact.get("display_value") or "").strip()

    if ctype == "phone":
        clean = "".join(ch for ch in value if ch.isdigit() or ch == "+")
        return {"url": f"tel:{clean}", "display": display or value,
                "label": label or "Call", "icon": "phone"}
    if ctype == "telegram":
        v = value.lstrip("@")
        if v.startswith("http"):
            url = value
        elif v.startswith("+"):
            url = f"https://t.me/{v}"
        else:
            url = f"https://t.me/{v}"
        return {"url": url,
                "display": display or ("@" + v if not v.startswith("+") else v),
                "label": label or "Telegram", "icon": "telegram"}
    if ctype == "whatsapp":
        clean = "".join(ch for ch in value if ch.isdigit())
        return {"url": f"https://wa.me/{clean}", "display": display or value,
                "label": label or "WhatsApp", "icon": "whatsapp"}
    if ctype == "email":
        return {"url": f"mailto:{value}", "display": display or value,
                "label": label or "Email", "icon": "email"}
    if ctype == "sms":
        clean = "".join(ch for ch in value if ch.isdigit() or ch == "+")
        return {"url": f"sms:{clean}", "display": display or value,
                "label": label or "SMS", "icon": "phone"}
    return {"url": value, "display": display or value,
            "label": label or ctype.title(), "icon": "link"}


def _icon_svg(icon: str) -> str:
    icons = {
        "phone": '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.37 1.9.72 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.35 1.85.59 2.81.72A2 2 0 0 1 22 16.92z"/></svg>',
        "telegram": '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M21.5 4.5l-19 7.5c-.7.3-.7 1.3 0 1.5l4.5 1.5 1.5 5c.2.7 1 .9 1.5.4l2.5-2.5 4.5 3.5c.6.5 1.5.1 1.6-.6l3-15c.2-.9-.7-1.5-1.5-1.3zm-3.5 4l-7 6.5-1 3.5-1.5-5 9.5-5z"/></svg>',
        "whatsapp": '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M17.5 14.4c-.3-.1-1.7-.8-2-.9-.3-.1-.5-.1-.7.1-.2.3-.7.9-.9 1.1-.2.2-.3.2-.6.1-.3-.1-1.2-.4-2.4-1.4-.9-.8-1.4-1.7-1.6-2-.2-.3 0-.5.1-.6.1-.1.3-.3.4-.5.1-.2.2-.3.3-.5.1-.2 0-.4 0-.5 0-.1-.7-1.7-.9-2.3-.2-.6-.5-.5-.7-.5h-.6c-.2 0-.5.1-.8.4-.3.3-1 1-1 2.5s1.1 2.9 1.2 3.1c.1.2 2.1 3.3 5.1 4.6.7.3 1.3.5 1.7.6.7.2 1.4.2 1.9.1.6-.1 1.7-.7 1.9-1.4.2-.7.2-1.3.2-1.4-.1-.1-.3-.2-.5-.3zM12 2C6.5 2 2 6.5 2 12c0 1.8.5 3.5 1.4 5L2 22l5.2-1.4c1.4.7 3 1.2 4.8 1.2 5.5 0 10-4.5 10-10S17.5 2 12 2zm0 18.2c-1.6 0-3.1-.4-4.4-1.2l-.3-.2-3.2.8.9-3.1-.2-.3c-.9-1.4-1.4-3-1.4-4.6 0-4.5 3.7-8.3 8.3-8.3s8.3 3.7 8.3 8.3-3.7 8.3-8.3 8.3z"/></svg>',
        "email": '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>',
        "link": '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>',
        "map": '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>',
        "clock": '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
    }
    return icons.get(icon, icons["link"])


# ── Schema.org JSON-LD ───────────────────────────────────────────────────────

def _schema_organization(site: dict) -> dict:
    org = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": site.get("org_name") or site.get("brand_name") or site.get("name"),
        "url": _site_url(site, "/"),
    }
    if site.get("logo_url"):
        org["logo"] = site["logo_url"]
    if site.get("org_phone"):
        org["telephone"] = site["org_phone"]
    if site.get("org_email"):
        org["email"] = site["org_email"]
    if site.get("social_links"):
        try:
            sl = _json.loads(site["social_links"])
            if isinstance(sl, dict) and sl:
                org["sameAs"] = list(sl.values())
            elif isinstance(sl, list):
                org["sameAs"] = sl
        except Exception:
            pass
    return org


def _schema_website(site: dict) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": site.get("brand_name") or site.get("name"),
        "url": _site_url(site, "/"),
    }


def _schema_local_business(site: dict, location: dict, contacts: list) -> dict:
    s = {
        "@context": "https://schema.org",
        "@type": ["LocalBusiness", "HealthAndBeautyBusiness"],
        "name": (site.get("brand_name") or site.get("name") or "") + (
            f" — {location.get('city')}" if location.get("city") else ""
        ),
        "url": _site_url(site, "/" + (location.get("slug") or "").lstrip("/")),
        "image": location.get("og_image") or site.get("default_og_image") or "",
        "priceRange": "$$",
    }
    addr = {
        "@type": "PostalAddress",
        "addressLocality": location.get("city") or "",
        "addressRegion": location.get("state") or "",
        "addressCountry": location.get("country") or "US",
    }
    if location.get("street"):
        addr["streetAddress"] = location["street"]
    if location.get("zip"):
        addr["postalCode"] = location["zip"]
    s["address"] = addr
    if location.get("latitude") and location.get("longitude"):
        s["geo"] = {
            "@type": "GeoCoordinates",
            "latitude": location["latitude"],
            "longitude": location["longitude"],
        }
    phones = [c["value"] for c in contacts if c.get("contact_type") == "phone"]
    if phones:
        s["telephone"] = phones[0]
    return s


def _schema_article(site: dict, article: dict, author: dict = None) -> dict:
    s = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": article.get("title") or article.get("h1") or "",
        "datePublished": article.get("published_at") or article.get("created_at"),
        "dateModified": article.get("updated_at") or article.get("published_at"),
        "image": article.get("og_image") or site.get("default_og_image") or "",
        "mainEntityOfPage": _site_url(site, "/blog/" + (article.get("slug") or "").lstrip("/")),
        "publisher": _schema_organization(site),
    }
    if author:
        s["author"] = {"@type": "Person", "name": author.get("name") or ""}
        if author.get("avatar_url"):
            s["author"]["image"] = author["avatar_url"]
    return s


def _schema_breadcrumb(site: dict, items: list) -> dict:
    """BreadcrumbList: items = [{name, path}, ...]. Google показывает в SERP
    под заголовком — повышает CTR. Path относительный (например '/blog')."""
    list_items = []
    for i, it in enumerate(items, 1):
        list_items.append({
            "@type": "ListItem",
            "position": i,
            "name": it.get("name", ""),
            "item": _site_url(site, it.get("path", "/")),
        })
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": list_items,
    }


def _extract_faq(content_html: str) -> list:
    """Извлекает Q&A пары из content_html. Ищем секцию FAQ
    (заголовок 'FAQ' / 'Frequently asked questions' / 'Часто задаваемые
    вопросы' и т.п.) и парсим H3-вопросы + следующий абзац как ответ.

    Возвращает [{q, a}, ...] или пустой список если FAQ не найден.
    """
    if not content_html:
        return []
    import re as _re
    # Найти FAQ-секцию: H2 с одним из ключевых слов до следующего H2 или конца
    faq_section_re = _re.compile(
        r'<h2[^>]*>\s*(?:FAQ|Frequently[\s-]asked\s+questions?|Часто[\s-]задаваемые\s+вопросы|Frequently\s+answered\s+questions)\s*[:.]?\s*</h2>(.*?)(?=<h2[^>]*>|$)',
        _re.IGNORECASE | _re.DOTALL,
    )
    m = faq_section_re.search(content_html)
    if not m:
        return []
    section = m.group(1)
    # В секции — пары: <h3>question</h3><p>answer</p>
    qa_re = _re.compile(
        r'<h3[^>]*>\s*(.*?)\s*</h3>\s*<p[^>]*>\s*(.*?)\s*</p>',
        _re.IGNORECASE | _re.DOTALL,
    )
    pairs = []
    for qm in qa_re.finditer(section):
        q = _re.sub(r'<[^>]+>', '', qm.group(1)).strip()
        a = _re.sub(r'<[^>]+>', '', qm.group(2)).strip()
        if q and a:
            pairs.append({"q": q, "a": a})
    return pairs


def _schema_faq_page(faqs: list) -> dict:
    """FAQPage Schema.org из извлечённых Q&A пар.
    Google показывает rich-результаты с FAQ в SERP."""
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": f["q"],
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": f["a"],
                },
            }
            for f in faqs
        ],
    }


def _schema_service_offers(site: dict, location: dict) -> list:
    """Список Service-объектов внутри LocalBusiness — типы массажа
    с ценами. Google использует для отображения каталога услуг."""
    base = (site.get("brand_name") or site.get("name") or "")
    city = location.get("city") or ""
    return [
        {
            "@type": "Service",
            "name": f"60-Minute Massage in {city}" if city else "60-Minute Massage",
            "provider": {"@type": "LocalBusiness", "name": base},
            "offers": {
                "@type": "Offer",
                "price": "230",
                "priceCurrency": "USD",
            },
        },
        {
            "@type": "Service",
            "name": f"30-Minute Massage in {city}" if city else "30-Minute Massage",
            "provider": {"@type": "LocalBusiness", "name": base},
            "offers": {
                "@type": "Offer",
                "price": "200",
                "priceCurrency": "USD",
            },
        },
        {
            "@type": "Service",
            "name": f"15-Minute Massage in {city}" if city else "15-Minute Massage",
            "provider": {"@type": "LocalBusiness", "name": base},
            "offers": {
                "@type": "Offer",
                "price": "140",
                "priceCurrency": "USD",
            },
        },
    ]


# ── CSS ──────────────────────────────────────────────────────────────────────

def _adjust_color(hex_color: str, amount: int = -30) -> str:
    try:
        h = hex_color.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        r = max(0, min(255, int(h[0:2], 16) + amount))
        g = max(0, min(255, int(h[2:4], 16) + amount))
        b = max(0, min(255, int(h[4:6], 16) + amount))
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return hex_color


_BASE_CSS_TEMPLATE = """
:root{--primary:__PRIMARY__;--secondary:__SECONDARY__;--bg:#FAF7F2;--text:#2C2A26;--muted:#7A7570;--border:#E5DFD5;--card:#FFFFFF;--primary-dark:__PRIMARY_DARK__;--shadow:0 6px 24px rgba(0,0,0,0.06);--radius:14px}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;color:var(--text);background:var(--bg);line-height:1.65;-webkit-font-smoothing:antialiased}
h1,h2,h3,h4{font-family:'Playfair Display',Georgia,serif;font-weight:600;line-height:1.25;color:var(--text)}
h1{font-size:clamp(2rem,4vw,3.25rem);letter-spacing:-0.02em;margin-bottom:1rem}
h2{font-size:clamp(1.6rem,3vw,2.4rem);margin:2rem 0 1rem;letter-spacing:-0.01em}
h3{font-size:1.4rem;margin:1.5rem 0 .8rem}
p{margin-bottom:1rem;color:var(--text)}
a{color:var(--primary-dark);text-decoration:none;transition:color .2s}
a:hover{color:var(--primary)}
img{max-width:100%;height:auto;display:block}
.container{max-width:1180px;margin:0 auto;padding:0 24px}
.container-narrow{max-width:780px;margin:0 auto;padding:0 24px}
header.site-header{background:#fff;border-bottom:1px solid var(--border);position:sticky;top:0;z-index:50;padding:14px 0}
.nav{display:flex;align-items:center;justify-content:space-between;gap:24px}
.brand{font-family:'Playfair Display',serif;font-size:1.45rem;font-weight:700;color:var(--primary-dark);letter-spacing:-0.01em}
.brand a{color:inherit}
.nav-links{display:flex;gap:28px;list-style:none}
.nav-links a{color:var(--text);font-weight:500;font-size:.95rem}
.nav-links a:hover{color:var(--primary-dark)}
.btn{display:inline-flex;align-items:center;gap:8px;padding:12px 24px;border-radius:999px;font-weight:600;font-size:.95rem;border:none;cursor:pointer;transition:all .2s;text-align:center;justify-content:center}
.btn-primary{background:var(--primary);color:#fff}
.btn-primary:hover{background:var(--primary-dark);color:#fff;transform:translateY(-1px);box-shadow:var(--shadow)}
.btn-outline{background:transparent;border:1.5px solid var(--primary);color:var(--primary-dark)}
.btn-outline:hover{background:var(--primary);color:#fff}
.hero{padding:80px 0 64px;background:linear-gradient(180deg,var(--secondary) 0%,var(--bg) 100%)}
.hero .lead{font-size:1.15rem;color:var(--muted);max-width:640px;margin-bottom:1.6rem}
section{padding:56px 0}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:24px;transition:box-shadow .2s}
.card:hover{box-shadow:var(--shadow)}
.grid{display:grid;gap:20px}
.grid-3{grid-template-columns:repeat(3,1fr)}
.grid-2{grid-template-columns:repeat(2,1fr)}
@media(max-width:900px){.grid-3{grid-template-columns:repeat(2,1fr)}.nav-links{display:none}}
@media(max-width:600px){.grid-3,.grid-2{grid-template-columns:1fr}.hero{padding:56px 0 40px}}
.contact-list{display:flex;flex-wrap:wrap;gap:12px;margin:1rem 0}
.contact-btn{display:inline-flex;align-items:center;gap:10px;padding:14px 20px;background:#fff;border:1px solid var(--border);border-radius:12px;font-weight:600;color:var(--text);transition:all .2s}
.contact-btn:hover{border-color:var(--primary);color:var(--primary-dark);transform:translateY(-1px);box-shadow:var(--shadow)}
.contact-btn.primary{background:var(--primary);color:#fff;border-color:var(--primary)}
.contact-btn.primary:hover{background:var(--primary-dark);color:#fff}
.breadcrumbs{font-size:.9rem;color:var(--muted);margin-bottom:1rem}
.breadcrumbs a{color:var(--muted)}
.breadcrumbs a:hover{color:var(--primary-dark)}
.meta-row{display:flex;flex-wrap:wrap;gap:16px;font-size:.9rem;color:var(--muted);margin-bottom:2rem}
.tag{display:inline-block;padding:4px 12px;background:var(--secondary);border-radius:999px;font-size:.8rem;color:var(--text);margin:2px}
.faq-item{padding:18px 0;border-bottom:1px solid var(--border)}
.faq-item summary{cursor:pointer;font-weight:600;font-size:1.05rem;list-style:none;padding-right:24px;position:relative}
.faq-item summary::after{content:'+';position:absolute;right:0;top:0;font-size:1.4rem;color:var(--primary-dark);font-weight:300}
.faq-item[open] summary::after{content:'-'}
.faq-item p{margin-top:.8rem;color:var(--muted)}
.article-card{background:#fff;border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;display:flex;flex-direction:column;transition:all .2s}
.article-card:hover{box-shadow:var(--shadow);transform:translateY(-2px)}
.article-card .img{aspect-ratio:16/9;background:var(--secondary);background-size:cover;background-position:center}
.article-card .body{padding:20px;flex:1;display:flex;flex-direction:column}
.article-card .title{font-family:'Playfair Display',serif;font-size:1.2rem;line-height:1.3;margin-bottom:8px;color:var(--text)}
.article-card .excerpt{color:var(--muted);font-size:.95rem;margin-bottom:12px;flex:1}
.article-card .meta{font-size:.82rem;color:var(--muted)}
.prose{font-size:1.05rem;line-height:1.75}
.prose h2,.prose h3{margin-top:2.4rem}
.prose p,.prose ul,.prose ol{margin-bottom:1.2rem}
.prose ul,.prose ol{padding-left:1.4rem}
.prose img{margin:1.6rem 0;border-radius:var(--radius)}
.prose blockquote{border-left:3px solid var(--primary);padding:8px 20px;color:var(--muted);font-style:italic;margin:1.4rem 0}
footer.site-footer{background:#1F1D1A;color:#D4CFC5;padding:48px 0 24px;margin-top:80px}
footer.site-footer a{color:#D4CFC5}
footer.site-footer a:hover{color:#fff}
footer.site-footer p,footer.site-footer li,footer.site-footer dd{color:#D4CFC5}
footer.site-footer h2,footer.site-footer h3,footer.site-footer h4{color:#fff}
footer.site-footer .columns{display:grid;grid-template-columns:repeat(3,1fr);gap:32px;margin-bottom:32px}
@media(max-width:700px){footer.site-footer .columns{grid-template-columns:1fr}}
footer.site-footer .copy{text-align:center;font-size:.85rem;color:#8A867E;border-top:1px solid #3A3733;padding-top:24px}
.address-card{background:#fff;border:1px solid var(--border);border-radius:var(--radius);padding:24px;display:flex;gap:16px;align-items:flex-start;color:var(--text)}
.address-card .ico{flex-shrink:0;color:var(--primary-dark);margin-top:2px}
.hours-list{list-style:none;display:grid;grid-template-columns:auto 1fr;gap:8px 24px;font-size:.95rem}
.hours-list dt{font-weight:600}
.hours-list dd{color:var(--muted)}
"""


def _build_css(site: dict) -> str:
    primary = site.get("color_primary") or "#7A9B76"
    secondary = site.get("color_secondary") or "#E8DDD0"
    primary_dark = _adjust_color(primary, -30)
    return (_BASE_CSS_TEMPLATE
            .replace("__PRIMARY__", primary)
            .replace("__SECONDARY__", secondary)
            .replace("__PRIMARY_DARK__", primary_dark))


# ── Head / Header / Footer ───────────────────────────────────────────────────

def _render_head(site: dict, *, title: str, description: str = "",
                  canonical: str = "", og_image: str = "",
                  og_type: str = "website", noindex: bool = False,
                  schema_jsons: list = None, extra_head: str = "",
                  preload_image: str = "") -> str:
    title_full = title
    if site.get("title_suffix"):
        title_full = f"{title}{site['title_suffix']}"
    desc = description or site.get("default_meta_description") or ""
    image = og_image or site.get("default_og_image") or ""
    favicon = site.get("favicon_url") or ""
    lang = site.get("language") or "en"
    brand = site.get("brand_name") or site.get("name") or ""

    schema_blocks = ""
    for s in (schema_jsons or []):
        if isinstance(s, str) and s.strip():
            schema_blocks += f'\n<script type="application/ld+json">{s}</script>'
        elif isinstance(s, (dict, list)):
            schema_blocks += f'\n<script type="application/ld+json">{_json.dumps(s, ensure_ascii=False)}</script>'

    ga_snippet = ""
    if site.get("ga_id"):
        gid = _esc(site["ga_id"])
        # Phone click tracker: fires 'phone_click' GA4 event on any <a href="tel:..."> click.
        # Mark as Key Event in GA4 Admin → Events to count as conversion.
        phone_tracker = (
            "document.addEventListener('click',function(e){"
            "var a=e.target.closest && e.target.closest('a[href^=\"tel:\"]');"
            "if(!a||typeof gtag!=='function')return;"
            "var num=a.getAttribute('href').replace('tel:','');"
            "gtag('event','phone_click',{"
            "phone_number:num,"
            "link_text:(a.innerText||'').trim().slice(0,80),"
            "page_location:location.href,"
            "page_path:location.pathname"
            "});"
            "},true);"
        )
        ga_snippet = (
            f'<script async src="https://www.googletagmanager.com/gtag/js?id={gid}"></script>'
            f'<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}'
            f"gtag('js',new Date());gtag('config','{gid}');"
            f"{phone_tracker}"
            f"</script>"
        )

    robots = '<meta name="robots" content="noindex, nofollow">' if noindex else ''

    parts = [
        '<!DOCTYPE html>',
        f'<html lang="{_esc(lang)}">',
        '<head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<title>{_esc(title_full)}</title>',
        f'<meta name="description" content="{_esc(desc)}">',
    ]
    if canonical:
        parts.append(f'<link rel="canonical" href="{_esc(canonical)}">')
    if robots:
        parts.append(robots)
    parts.append(f'<meta property="og:type" content="{_esc(og_type)}">')
    parts.append(f'<meta property="og:title" content="{_esc(title_full)}">')
    parts.append(f'<meta property="og:description" content="{_esc(desc)}">')
    if canonical:
        parts.append(f'<meta property="og:url" content="{_esc(canonical)}">')
    if image:
        parts.append(f'<meta property="og:image" content="{_esc(image)}">')
    if brand:
        parts.append(f'<meta property="og:site_name" content="{_esc(brand)}">')
    parts.append('<meta name="twitter:card" content="summary_large_image">')
    parts.append(f'<meta name="twitter:title" content="{_esc(title_full)}">')
    parts.append(f'<meta name="twitter:description" content="{_esc(desc)}">')
    if image:
        parts.append(f'<meta name="twitter:image" content="{_esc(image)}">')
    if favicon:
        parts.append(f'<link rel="icon" href="{_esc(favicon)}">')
    parts.append('<link rel="preconnect" href="https://fonts.googleapis.com">')
    parts.append('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
    parts.append('<link rel="preconnect" href="https://res.cloudinary.com" crossorigin>')
    # Non-blocking Google Fonts load: media=print trick removes CSS from critical
    # rendering path; onload swaps back to media=all. <noscript> fallback for no-JS.
    _fonts_href = "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Playfair+Display:wght@500;600;700&display=swap"
    parts.append(f'<link rel="stylesheet" href="{_fonts_href}" media="print" onload="this.media=\'all\'">')
    parts.append(f'<noscript><link rel="stylesheet" href="{_fonts_href}"></noscript>')
    # Preload above-the-fold image (LCP candidate) for faster paint.
    if preload_image:
        _pl = _optimize_img_url(preload_image)
        parts.append(f'<link rel="preload" as="image" href="{_esc(_pl)}" fetchpriority="high">')
    parts.append(f'<style>{_build_css(site)}</style>')
    if schema_blocks:
        parts.append(schema_blocks)
    if ga_snippet:
        parts.append(ga_snippet)
    if extra_head:
        parts.append(extra_head)
    parts.append('</head>')
    parts.append('<body>')
    return "\n".join(parts)


def _render_header(site: dict, menu_pages: list = None) -> str:
    brand = site.get("brand_name") or site.get("name") or "Site"
    items = [('/', "Home")]
    for p in (menu_pages or []):
        slug = (p.get("slug") or "").lstrip("/")
        label = p.get("menu_label") or p.get("title") or slug
        if not slug or not label:
            continue
        items.append((f"/{slug}", label))
    items.append(("/blog", "Blog"))

    nav_html = "".join(
        f'<li><a href="{_esc(href)}">{_esc(lbl)}</a></li>' for href, lbl in items
    )
    return (
        '<header class="site-header"><div class="container nav">'
        f'<div class="brand"><a href="/">{_esc(brand)}</a></div>'
        f'<ul class="nav-links">{nav_html}</ul>'
        '</div></header>'
    )


def _render_footer(site: dict) -> str:
    """Footer для default-шаблона. Если site["_footer_locations"] задан
    (диспатчер инжектирует список dict'ов с городами + primary phone),
    рендерится 4-я колонка «Our Locations» — до 8 городов с прямой
    ссылкой и телефоном."""
    brand = site.get("brand_name") or site.get("name") or ""
    org_name = site.get("org_name") or brand
    year = datetime.utcnow().year
    custom = site.get("footer_html") or ""
    if custom:
        return (
            f'<footer class="site-footer"><div class="container">{custom}'
            f'<div class="copy">© {year} {_esc(org_name)}. All rights reserved.</div>'
            '</div></footer></body></html>'
        )
    tagline = site.get("tagline") or ""
    phone = site.get("org_phone") or ""
    email = site.get("org_email") or ""

    # Колонка локаций (опц.) — диспатчер передаёт через site["_footer_locations"]
    locations = site.get("_footer_locations") or []
    locations_col = ""
    cols_count = 3
    if locations:
        cols_count = 4
        loc_items = ""
        for loc in locations[:8]:
            slug = (loc.get("slug") or "").lstrip("/")
            label = f"{loc.get('city','')}, {loc.get('state','')}".strip(", ")
            primary_phone = loc.get("primary_phone") or ""
            phone_html = f'<div style="font-size:.78rem;color:#A9A39A">{_esc(primary_phone)}</div>' if primary_phone else ""
            loc_items += (
                f'<li style="margin-bottom:10px"><a href="/{_esc(slug)}" style="font-size:.92rem;font-weight:600">{_esc(label)}</a>'
                f'{phone_html}</li>'
            )
        locations_col = (
            '<div><h4 style="color:#fff;font-size:1rem;margin-bottom:12px">Our Locations</h4>'
            f'<ul style="list-style:none;padding:0;margin:0">{loc_items}</ul></div>'
        )

    grid_template = "repeat(4,1fr)" if cols_count == 4 else "repeat(3,1fr)"
    grid_style = f'<style>footer.site-footer .columns{{grid-template-columns:{grid_template}}}@media(max-width:900px){{footer.site-footer .columns{{grid-template-columns:repeat(2,1fr)}}}}@media(max-width:600px){{footer.site-footer .columns{{grid-template-columns:1fr}}}}</style>' if cols_count == 4 else ""

    return (
        f'{grid_style}'
        '<footer class="site-footer"><div class="container">'
        '<div class="columns">'
        f'<div><h3 style="color:#fff;font-size:1.2rem;margin-bottom:12px">{_esc(brand)}</h3>'
        f'<p style="font-size:.9rem;line-height:1.6">{_esc(tagline)}</p></div>'
        '<div><h4 style="color:#fff;font-size:1rem;margin-bottom:12px">Contact</h4>'
        f'<p style="font-size:.9rem;line-height:1.8">{_esc(phone)}<br>{_esc(email)}</p></div>'
        '<div><h4 style="color:#fff;font-size:1rem;margin-bottom:12px">Links</h4>'
        '<p style="font-size:.9rem;line-height:1.8">'
        '<a href="/about">About</a><br><a href="/contact">Contact</a><br>'
        '<a href="/privacy">Privacy Policy</a><br><a href="/terms">Terms of Service</a></p></div>'
        f'{locations_col}'
        '</div>'
        f'<div class="copy">© {year} {_esc(org_name)}. All rights reserved.</div>'
        '</div></footer></body></html>'
    )


# ── Renderers ────────────────────────────────────────────────────────────────

def render_seo_home(site: dict, locations: list, articles: list,
                     menu_pages: list = None) -> str:
    title = site.get("brand_name") or site.get("name") or "Home"
    desc = site.get("default_meta_description") or site.get("tagline") or ""
    canonical = _site_url(site, "/")

    schemas = [_schema_organization(site), _schema_website(site)]
    head = _render_head(site, title=title, description=desc,
                         canonical=canonical, og_type="website",
                         schema_jsons=schemas)
    header = _render_header(site, menu_pages or [])

    tagline = site.get("tagline") or ""
    hero_lead = f'<p class="lead">{_esc(tagline)}</p>' if tagline else ''
    hero = (
        '<section class="hero"><div class="container">'
        f'<h1>{_esc(title)}</h1>{hero_lead}'
        '<a href="#locations" class="btn btn-primary">Find a Studio</a>'
        '</div></section>'
    )

    loc_cards = ""
    for loc in (locations or []):
        loc_url = "/" + (loc.get("slug") or "").lstrip("/")
        loc_title = loc.get("h1") or loc.get("title") or f"{loc.get('city', '')}, {loc.get('state', '')}"
        loc_desc = (loc.get("meta_description") or "")[:140]
        loc_cards += (
            f'<a href="{_esc(loc_url)}" class="card" style="text-decoration:none;color:inherit;display:block">'
            f'<h3 style="margin:0 0 8px">{_esc(loc_title)}</h3>'
            f'<p style="color:var(--muted);font-size:.95rem;margin:0">{_esc(loc_desc)}</p>'
            '</a>'
        )
    if not loc_cards:
        loc_cards = '<p style="color:var(--muted)">No locations published yet.</p>'

    locations_section = (
        '<section id="locations"><div class="container">'
        '<h2>Our Locations</h2>'
        f'<div class="grid grid-3" style="margin-top:24px">{loc_cards}</div>'
        '</div></section>'
    )

    article_cards = ""
    for art in (articles or [])[:6]:
        art_url = "/blog/" + (art.get("slug") or "").lstrip("/")
        bg = f"background-image:url('{_esc(art.get('og_image') or '')}')" if art.get("og_image") else ""
        date = (art.get("published_at") or art.get("created_at") or "")[:10]
        article_cards += (
            f'<a href="{_esc(art_url)}" class="article-card" style="text-decoration:none">'
            f'<div class="img" style="{bg}"></div>'
            '<div class="body">'
            f'<div class="title">{_esc(art.get("title", ""))}</div>'
            f'<div class="excerpt">{_esc((art.get("excerpt") or "")[:140])}</div>'
            f'<div class="meta">{_esc(date)}</div>'
            '</div></a>'
        )

    articles_section = ""
    if article_cards:
        articles_section = (
            '<section style="background:#fff"><div class="container">'
            '<h2>From the Blog</h2>'
            f'<div class="grid grid-3" style="margin-top:24px">{article_cards}</div>'
            '<div style="text-align:center;margin-top:32px">'
            '<a href="/blog" class="btn btn-outline">All Articles →</a></div>'
            '</div></section>'
        )

    return head + header + hero + locations_section + articles_section + _render_team_section(site) + _render_footer(site)


def render_seo_location(site: dict, location: dict, contacts: list,
                         menu_pages: list = None,
                         child_pages: list = None) -> str:
    """child_pages — nested service-страницы для этого города (например
    los-angeles-ca/swedish-massage). Если есть, рендерим секцию
    «Our Services in [City]» со ссылками. Это создаёт hub-структуру
    для PageRank-flow между city-page и service-pages."""
    title = location.get("title") or location.get("h1") or f"{location.get('city')}, {location.get('state')}"
    h1 = location.get("h1") or title
    desc = location.get("meta_description") or site.get("default_meta_description") or ""
    canonical = _site_url(site, "/" + (location.get("slug") or "").lstrip("/"))

    # Schemas: LocalBusiness (с прайсами как hasOfferCatalog) + BreadcrumbList
    local_schema = _schema_local_business(site, location, contacts)
    # Добавляем service offers (60min/30min/15min) в LocalBusiness
    local_schema["hasOfferCatalog"] = {
        "@type": "OfferCatalog",
        "name": "Massage Sessions",
        "itemListElement": _schema_service_offers(site, location),
    }
    schemas = [local_schema]
    schemas.append(_schema_breadcrumb(site, [
        {"name": "Home", "path": "/"},
        {"name": location.get("city", ""), "path": "/" + (location.get("slug") or "").lstrip("/")},
    ]))
    # FAQPage из faq_json локации
    try:
        loc_faqs = _json.loads(location.get("faq_json") or "[]")
        if isinstance(loc_faqs, list) and loc_faqs:
            schemas.append(_schema_faq_page([
                {"q": f.get("q", ""), "a": f.get("a", "")}
                for f in loc_faqs if isinstance(f, dict) and f.get("q") and f.get("a")
            ]))
    except Exception:
        pass

    head = _render_head(site, title=title, description=desc,
                         canonical=canonical, og_type="website",
                         og_image=location.get("og_image", ""),
                         schema_jsons=schemas)
    header = _render_header(site, menu_pages or [])

    breadcrumbs = (
        '<div class="breadcrumbs">'
        f'<a href="/">Home</a> / {_esc(location.get("city", ""))}</div>'
    )

    contacts_html = ""
    for c in (contacts or []):
        f = _format_contact(c)
        cls = "contact-btn primary" if c.get("is_primary") else "contact-btn"
        contacts_html += (
            f'<a href="{_esc(f["url"])}" class="{cls}">'
            f'{_icon_svg(f["icon"])}<span>{_esc(f["display"])}</span></a>'
        )

    address_html = ""
    if location.get("street") or location.get("zip"):
        addr_parts = [
            location.get("street", ""),
            location.get("address_line2", ""),
            ", ".join(filter(None, [location.get("city"), location.get("state"), location.get("zip")])),
        ]
        addr_str = "<br>".join(_esc(p) for p in addr_parts if p)

        # Кнопка "Open in Google Maps": приоритет — пользовательский URL,
        # иначе строим из lat/long, иначе из адреса
        gmap_url = (location.get("google_maps_url") or "").strip()
        if not gmap_url:
            if location.get("latitude") and location.get("longitude"):
                gmap_url = f"https://www.google.com/maps/search/?api=1&query={location['latitude']},{location['longitude']}"
            elif location.get("street"):
                from urllib.parse import quote_plus as _qp
                _q = _qp(", ".join(filter(None, [
                    location.get("street"), location.get("city"),
                    location.get("state"), location.get("zip")
                ])))
                gmap_url = f"https://www.google.com/maps/search/?api=1&query={_q}"

        gmap_btn = ""
        if gmap_url:
            gmap_btn = (
                f'<div style="margin-top:12px"><a href="{_esc(gmap_url)}" target="_blank" rel="noopener" class="btn btn-outline" style="font-size:.85rem;padding:8px 16px">'
                f'{_icon_svg("map")}<span>Open in Google Maps</span></a></div>'
            )

        address_html = (
            '<div class="address-card" style="margin:1.5rem 0">'
            f'<div class="ico">{_icon_svg("map")}</div>'
            f'<div><strong>Studio Address</strong><br>{addr_str}{gmap_btn}</div>'
            '</div>'
        )

        # Встроенная карта Google Maps (iframe). Берём из lat/lng если есть,
        # иначе строим q=address. Без API key — используем publichный embed.
        if location.get("latitude") and location.get("longitude"):
            _embed_q = f"{location['latitude']},{location['longitude']}"
        elif location.get("street"):
            from urllib.parse import quote_plus as _qp
            _embed_q = _qp(", ".join(filter(None, [
                location.get("street"), location.get("city"),
                location.get("state"), location.get("zip")
            ])))
        else:
            _embed_q = None

        if _embed_q:
            address_html += (
                '<div style="margin:1rem 0;border-radius:var(--radius);overflow:hidden;border:1px solid var(--border)">'
                f'<iframe src="https://maps.google.com/maps?q={_esc(str(_embed_q))}&z=15&output=embed" '
                'width="100%" height="320" style="border:0;display:block" '
                'loading="lazy" referrerpolicy="no-referrer-when-downgrade" '
                f'title="Map of {_esc(location.get("city",""))}"></iframe>'
                '</div>'
            )

    hours_html = ""
    try:
        hrs = _json.loads(location.get("hours_json") or "[]")
        if isinstance(hrs, list) and hrs:
            rows = "".join(
                f'<dt>{_esc(h.get("day", ""))}</dt>'
                f'<dd>{_esc(h.get("open", ""))} - {_esc(h.get("close", ""))}</dd>'
                for h in hrs if isinstance(h, dict)
            )
            hours_html = (
                '<div class="card" style="margin:1.5rem 0">'
                f'<h3 style="margin-top:0">{_icon_svg("clock")} Hours</h3>'
                f'<dl class="hours-list">{rows}</dl>'
                '</div>'
            )
    except Exception:
        pass

    faqs_html = ""
    try:
        faqs = _json.loads(location.get("faq_json") or "[]")
        if isinstance(faqs, list) and faqs:
            items = "".join(
                f'<details class="faq-item"><summary>{_esc(fq.get("q", ""))}</summary>'
                f'<p>{_esc(fq.get("a", ""))}</p></details>'
                for fq in faqs if isinstance(fq, dict)
            )
            faqs_html = (
                '<section><div class="container-narrow">'
                f'<h2>Frequently Asked Questions</h2>{items}'
                '</div></section>'
            )
    except Exception:
        pass

    services_html = ""
    if location.get("services_html"):
        services_html = (
            '<section style="background:#fff"><div class="container-narrow">'
            f'<h2>Services</h2><div class="prose">{location["services_html"]}</div>'
            '</div></section>'
        )

    about_studio = ""
    if location.get("about_studio_html"):
        about_studio = (
            '<section><div class="container-narrow">'
            f'<h2>About Our Studio</h2><div class="prose">{location["about_studio_html"]}</div>'
            '</div></section>'
        )

    intro = location.get("intro_html") or ""
    hero = (
        '<section class="hero"><div class="container">'
        f'{breadcrumbs}<h1>{_esc(h1)}</h1>'
        f'<div class="prose" style="margin-top:1rem">{intro}</div>'
        f'<div class="contact-list">{contacts_html}</div>'
        f'{address_html}{hours_html}'
        '</div></section>'
    )

    # Секция «Our Services in [City]» — карточки nested service-страниц.
    # Создаёт city-page → service-page внутреннюю перелинковку (hub pattern,
    # хорошо для SEO PageRank-flow).
    children_section = ""
    if child_pages:
        cards = ""
        for cp in child_pages:
            href = "/" + (cp.get("slug") or "").lstrip("/")
            t = cp.get("h1") or cp.get("title") or cp.get("slug") or ""
            d = (cp.get("meta_description") or "")[:140]
            cards += (
                f'<a href="{_esc(href)}" class="card" style="text-decoration:none;color:inherit;display:block">'
                f'<h3 style="margin:0 0 8px">{_esc(t)}</h3>'
                f'<p style="color:var(--muted);font-size:.95rem;margin:0">{_esc(d)}</p>'
                '</a>'
            )
        children_section = (
            '<section style="background:var(--surface,#FAF7F2)"><div class="container">'
            f'<h2>Our Services in {_esc(location.get("city",""))}</h2>'
            '<p style="color:var(--muted);max-width:680px;margin-bottom:24px">Choose the modality that fits what your body needs today.</p>'
            f'<div class="grid grid-3" style="margin-top:24px">{cards}</div>'
            '</div></section>'
        )

    return head + header + hero + services_html + about_studio + children_section + faqs_html + _render_team_section(site) + _render_footer(site)


def render_seo_page(site: dict, page: dict, menu_pages: list = None,
                     parent_location: dict = None) -> str:
    title = page.get("title") or page.get("h1") or page.get("slug") or "Page"
    h1 = page.get("h1") or title
    desc = page.get("meta_description") or site.get("default_meta_description") or ""
    canonical = page.get("canonical_url") or _site_url(site, "/" + (page.get("slug") or "").lstrip("/"))

    schemas = []
    if page.get("schema_json"):
        schemas.append(page["schema_json"])
    # BreadcrumbList — если есть parent_location, добавляем её в иерархию
    bc_items = [{"name": "Home", "path": "/"}]
    if parent_location:
        bc_items.append({
            "name": parent_location.get("city", "") + ", " + parent_location.get("state", ""),
            "path": "/" + (parent_location.get("slug") or "").lstrip("/"),
        })
    bc_items.append({"name": title, "path": "/" + (page.get("slug") or "").lstrip("/")})
    schemas.append(_schema_breadcrumb(site, bc_items))

    head = _render_head(site, title=title, description=desc,
                         canonical=canonical, og_type="website",
                         og_image=page.get("og_image", ""),
                         noindex=bool(page.get("noindex")),
                         schema_jsons=schemas)
    header = _render_header(site, menu_pages or [])

    # Visible breadcrumb HTML
    if parent_location:
        parent_city = _esc(parent_location.get("city", "") + ", " + parent_location.get("state", ""))
        parent_slug = _esc((parent_location.get("slug") or "").lstrip("/"))
        breadcrumb_html = f'<a href="/">Home</a> / <a href="/{parent_slug}">{parent_city}</a> / {_esc(title)}'
    else:
        breadcrumb_html = f'<a href="/">Home</a> / {_esc(title)}'

    body = (
        '<section><div class="container-narrow">'
        f'<div class="breadcrumbs">{breadcrumb_html}</div>'
        f'<h1>{_esc(h1)}</h1>'
        f'<div class="prose">{page.get("content_html") or ""}</div>'
        '</div></section>'
    )
    return head + header + body + _render_team_section(site) + _render_footer(site)


def render_seo_blog_index(site: dict, articles: list, categories: list = None,
                           menu_pages: list = None, category: dict = None) -> str:
    base_title = "Blog" if not category else (category.get("name") or "Blog")
    desc = (category and category.get("meta_description")) or site.get("default_meta_description") or ""
    canonical = _site_url(site, "/blog" + (f"/category/{category['slug']}" if category else ""))

    # BreadcrumbList на блог-индексе
    bc_items = [{"name": "Home", "path": "/"}, {"name": "Blog", "path": "/blog"}]
    if category:
        bc_items.append({"name": category.get("name", ""), "path": f"/blog/category/{category.get('slug','')}"})
    schemas = [_schema_breadcrumb(site, bc_items)]

    head = _render_head(site, title=base_title, description=desc,
                         canonical=canonical, og_type="website",
                         schema_jsons=schemas)
    header = _render_header(site, menu_pages or [])

    cards = ""
    for art in articles or []:
        art_url = "/blog/" + (art.get("slug") or "").lstrip("/")
        bg = f"background-image:url('{_esc(art.get('og_image') or '')}')" if art.get("og_image") else ""
        date = (art.get("published_at") or art.get("created_at") or "")[:10]
        cards += (
            f'<a href="{_esc(art_url)}" class="article-card" style="text-decoration:none">'
            f'<div class="img" style="{bg}"></div>'
            '<div class="body">'
            f'<div class="title">{_esc(art.get("title", ""))}</div>'
            f'<div class="excerpt">{_esc((art.get("excerpt") or "")[:160])}</div>'
            f'<div class="meta">{_esc(date)}</div>'
            '</div></a>'
        )
    if not cards:
        cards = '<p style="color:var(--muted)">No articles yet.</p>'

    cat_links = ""
    if categories:
        chips = '<a href="/blog" class="tag">All</a>'
        for cat in categories:
            chips += f'<a href="/blog/category/{_esc(cat["slug"])}" class="tag">{_esc(cat["name"])}</a>'
        cat_links = f'<div style="margin:1rem 0;display:flex;flex-wrap:wrap;gap:8px">{chips}</div>'

    breadcrumbs = (
        '<div class="breadcrumbs"><a href="/">Home</a> / Blog'
        + (f' / {_esc(category["name"])}' if category else '')
        + '</div>'
    )

    body = (
        '<section class="hero"><div class="container">'
        f'{breadcrumbs}<h1>{_esc(base_title)}</h1>{cat_links}'
        '</div></section>'
        '<section><div class="container">'
        f'<div class="grid grid-3">{cards}</div>'
        '</div></section>'
    )
    return head + header + body + _render_team_section(site) + _render_footer(site)


# ── Авто-перелинковка между статьями ────────────────────────────────────────
# Карта (slug → ключевые фразы для линкования). Длинные фразы первыми чтобы
# при поиске они совпали раньше своих коротких вариантов. Дополняй по мере
# написания новых статей.
_INTERNAL_LINK_MAP = [
    ("what-is-tantric-massage-really",  [
        "what is tantric massage",
        "tantric massage",
    ]),
    ("your-first-tantric-session-what-to-expect", [
        "your first tantric session",
        "first tantric session",
        "what to expect",
    ]),
    ("tantric-vs-sensual-massage-difference", [
        "tantric vs sensual massage",
        "tantric and sensual",
        "sensual massage",
    ]),
    ("why-slow-touch-matters", [
        "why slow touch matters",
        "science of slow touch",
        "slow touch",
        "CT-fibre pathway",
        "C-tactile fibres",
    ]),
    ("tantric-massage-for-stress-and-burnout", [
        "tantric massage for stress",
        "burnout",
        "anxiety",
        "stress",
    ]),
    ("how-to-prepare-for-a-tantric-session", [
        "how to prepare for a tantric session",
        "prepare for a tantric session",
    ]),
    ("tantric-massage-etiquette", [
        "tantric massage etiquette",
        "tipping",
        "etiquette",
    ]),
    ("tantric-massage-for-couples", [
        "tantric massage for couples",
        "couples session",
        "couples",
    ]),
    ("how-to-choose-a-tantric-practitioner", [
        "how to choose a tantric practitioner",
        "choose a tantric practitioner",
        "choose a practitioner",
    ]),
    ("history-of-tantric-bodywork-in-the-west", [
        "history of tantric bodywork",
        "Esalen",
        "Mantak Chia",
        "Margot Anand",
    ]),
]


def _auto_link_internal_articles(html: str, current_slug: str = "") -> str:
    """Вставляет ссылки на другие статьи в content_html.

    Стратегия:
    - Никогда не линкуем на саму статью (current_slug)
    - Не трогаем текст внутри <a>, <h1-6>, <code>, <pre> (там уже что-то есть)
    - Только ПЕРВОЕ вхождение фразы → одна ссылка на target
    - Word-boundary матчинг (Swedish-massage в одно слово не матчится)
    - Регистронезависимо, но сохраняет оригинальный регистр в линке
    """
    if not html:
        return html

    # Защищённые регионы (внутри них не линкуем)
    protect_pattern = _re.compile(
        r'(<a\s[^>]*?>.*?</a>|<h[1-6][^>]*>.*?</h[1-6]>|<code[^>]*>.*?</code>|<pre[^>]*>.*?</pre>)',
        _re.IGNORECASE | _re.DOTALL,
    )
    parts = protect_pattern.split(html)
    # parts[0] / parts[2] / parts[4] ... — обычный текст (можно линковать)
    # parts[1] / parts[3] / parts[5] ... — защищённые регионы (не трогаем)

    linked_slugs = set()
    for target_slug, keywords in _INTERNAL_LINK_MAP:
        if target_slug == current_slug or target_slug in linked_slugs:
            continue
        for i in range(0, len(parts), 2):
            if target_slug in linked_slugs:
                break
            text = parts[i]
            for kw in keywords:
                regex = _re.compile(
                    r'(?<![\w-])(' + _re.escape(kw) + r')(?![\w-])',
                    _re.IGNORECASE,
                )
                m = regex.search(text)
                if m:
                    matched = m.group(1)
                    replacement = f'<a href="/blog/{target_slug}">{matched}</a>'
                    parts[i] = text[:m.start()] + replacement + text[m.end():]
                    linked_slugs.add(target_slug)
                    break

    return "".join(parts)


def render_seo_article(site: dict, article: dict, author: dict = None,
                        category: dict = None, related: list = None,
                        menu_pages: list = None) -> str:
    title = article.get("title") or article.get("h1") or "Article"
    h1 = article.get("h1") or title
    desc = article.get("meta_description") or article.get("excerpt") or ""
    canonical = article.get("canonical_url") or _site_url(site, "/blog/" + (article.get("slug") or "").lstrip("/"))

    # Schemas: Article + BreadcrumbList + опц. FAQPage если найдены FAQ
    schemas = [_schema_article(site, article, author)]
    breadcrumb_items = [{"name": "Home", "path": "/"}, {"name": "Blog", "path": "/blog"}]
    if category:
        breadcrumb_items.append({"name": category.get("name", ""), "path": f"/blog/category/{category.get('slug','')}"})
    breadcrumb_items.append({"name": title, "path": f"/blog/{(article.get('slug') or '').lstrip('/')}"})
    schemas.append(_schema_breadcrumb(site, breadcrumb_items))
    faqs = _extract_faq(article.get("content_html") or "")
    if faqs:
        schemas.append(_schema_faq_page(faqs))

    head = _render_head(site, title=title, description=desc,
                         canonical=canonical, og_type="article",
                         og_image=article.get("og_image", ""),
                         noindex=bool(article.get("noindex")),
                         schema_jsons=schemas,
                         preload_image=article.get("og_image", ""))
    header = _render_header(site, menu_pages or [])

    pub = (article.get("published_at") or article.get("created_at") or "")[:10]
    upd = (article.get("updated_at") or "")[:10]
    show_updated = upd and upd != pub
    author_name = author.get("name") if author else ""
    cat_label = category.get("name") if category else ""

    cat_link = ""
    if category:
        cat_link = f' / <a href="/blog/category/{_esc(category["slug"])}">{_esc(cat_label)}</a>'
    breadcrumbs = (
        '<div class="breadcrumbs">'
        f'<a href="/">Home</a> / <a href="/blog">Blog</a>{cat_link} / {_esc(title[:40])}'
        '</div>'
    )

    # Meta-row с time-тегами + опциональная "Updated:" дата
    by = f"By {_esc(author_name)}" if author_name else ""
    sep = " · " if author_name and pub else ""
    pub_html = f'<time datetime="{_esc(pub)}" itemprop="datePublished">{_esc(pub)}</time>' if pub else ""
    upd_html = ""
    if show_updated:
        upd_html = f' · <span style="color:var(--muted)">Updated: <time datetime="{_esc(upd)}" itemprop="dateModified">{_esc(upd)}</time></span>'
    meta = f'<div class="meta-row">{by}{sep}{pub_html}{upd_html}</div>'

    cover = ""
    if article.get("og_image"):
        _cov = _optimize_img_url(article["og_image"])
        # Above-the-fold cover = LCP element. Eager + high priority, not lazy.
        cover = (
            f'<img loading="eager" fetchpriority="high" decoding="async" '
            f'src="{_esc(_cov)}" alt="{_esc(title)}" '
            'style="width:100%;border-radius:var(--radius);margin:1rem 0 2rem">'
        )

    tags_html = ""
    if article.get("tags"):
        tags = [t.strip() for t in article["tags"].split(",") if t.strip()]
        chips = "".join(f'<span class="tag">{_esc(t)}</span>' for t in tags)
        tags_html = f'<div style="margin:2rem 0">{chips}</div>'

    author_block = ""
    if author and (author.get("bio_html") or author.get("name")):
        avatar = ""
        if author.get("avatar_url"):
            avatar = (
                f'<img loading="lazy" src="{_esc(author["avatar_url"])}" '
                f'alt="{_esc(author.get("name") or "")}" '
                'style="width:64px;height:64px;border-radius:50%;flex-shrink:0">'
            )
        creds = ""
        if author.get("credentials"):
            creds = (
                f'<div style="color:var(--muted);font-size:.9rem;margin-bottom:8px">'
                f'{_esc(author["credentials"])}</div>'
            )
        author_block = (
            '<div class="card" style="margin-top:3rem;display:flex;gap:16px;align-items:flex-start">'
            f'{avatar}<div>'
            f'<div style="font-weight:600;font-size:1.1rem">{_esc(author.get("name", ""))}</div>'
            f'{creds}'
            f'<div style="color:var(--muted);font-size:.95rem">{author.get("bio_html") or ""}</div>'
            '</div></div>'
        )

    related_html = ""
    if related:
        cards = ""
        for art in related[:3]:
            art_url = "/blog/" + (art.get("slug") or "").lstrip("/")
            bg = f"background-image:url('{_esc(art.get('og_image') or '')}')" if art.get("og_image") else ""
            cards += (
                f'<a href="{_esc(art_url)}" class="article-card" style="text-decoration:none">'
                f'<div class="img" style="{bg}"></div>'
                f'<div class="body"><div class="title">{_esc(art.get("title", ""))}</div></div>'
                '</a>'
            )
        related_html = (
            '<section style="background:#fff"><div class="container">'
            '<h2>Related Articles</h2>'
            f'<div class="grid grid-3" style="margin-top:24px">{cards}</div>'
            '</div></section>'
        )

    # Авто-перелинковка между статьями: вставляем ссылки на родственные
    # материалы прямо в тело статьи (первое вхождение каждой фразы).
    linked_content = _auto_link_internal_articles(
        article.get("content_html") or "",
        current_slug=article.get("slug", ""),
    )

    body = (
        '<section><div class="container-narrow">'
        f'{breadcrumbs}<h1>{_esc(h1)}</h1>{meta}{cover}'
        f'<div class="prose">{linked_content}</div>'
        f'{tags_html}{author_block}'
        '</div></section>'
        f'{related_html}'
    )
    return head + header + body + _render_team_section(site) + _render_footer(site)


# ── sitemap.xml / robots.txt ─────────────────────────────────────────────────

def render_sitemap_xml(site: dict, urls: list) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    home = _site_url(site, "/")
    lines.append(f'<url><loc>{_esc(home)}</loc><changefreq>weekly</changefreq><priority>1.0</priority></url>')

    blog = _site_url(site, "/blog")
    lines.append(f'<url><loc>{_esc(blog)}</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>')

    for u in urls or []:
        loc = _site_url(site, u.get("loc") or "/")
        lastmod = (u.get("lastmod") or "")[:10]
        ptype = u.get("type") or ""
        priority = "0.9" if ptype == "location" else ("0.7" if ptype == "article" else "0.6")
        changefreq = "weekly" if ptype in ("location", "article") else "monthly"
        lastmod_tag = f'<lastmod>{_esc(lastmod)}</lastmod>' if lastmod else ''
        lines.append(
            f'<url><loc>{_esc(loc)}</loc>{lastmod_tag}'
            f'<changefreq>{changefreq}</changefreq><priority>{priority}</priority></url>'
        )
    lines.append('</urlset>')
    return "\n".join(lines)


def render_robots_txt(site: dict) -> str:
    domain = (site.get("domain") or "").strip().lower()
    sitemap_url = f"https://{domain}/sitemap.xml" if domain else "/sitemap.xml"
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /__seo_preview/\n"
        "Disallow: /admin/\n"
        "\n"
        f"Sitemap: {sitemap_url}\n"
    )


def render_404(site: dict, menu_pages: list = None) -> str:
    head = _render_head(site, title="Page Not Found",
                         description="The page you're looking for could not be found.",
                         noindex=True)
    header = _render_header(site, menu_pages or [])
    body = (
        '<section style="padding:120px 0;text-align:center"><div class="container">'
        '<h1>404</h1>'
        '<p style="font-size:1.15rem;color:var(--muted);margin-bottom:2rem">'
        "The page you're looking for could not be found.</p>"
        '<a href="/" class="btn btn-primary">Back to Home</a>'
        '</div></section>'
    )
    return head + header + body + _render_team_section(site) + _render_footer(site)


def render_seo_search(site: dict, query: str, results: list,
                       menu_pages: list = None) -> str:
    """Страница результатов поиска по сайту. Простой LIKE-поиск
    результатов в админке диспатчера, рендер здесь.
    Search-страницы должны быть noindex (Google не индексирует
    результаты поиска по сайту)."""
    title = (f"Search: {query}" if query else "Search") + " · " + (site.get("brand_name") or site.get("name") or "")
    head = _render_head(site, title=title,
                         description="Search results",
                         noindex=True)
    header = _render_header(site, menu_pages or [])

    form_html = (
        '<form method="get" action="/search" style="margin:0 0 2rem;display:flex;gap:8px">'
        f'<input type="text" name="q" value="{_esc(query)}" placeholder="Search articles..." '
        'style="flex:1;padding:14px 18px;border:1px solid var(--border);border-radius:999px;font-size:1rem">'
        '<button type="submit" class="btn btn-primary">Search</button>'
        '</form>'
    )

    cards_html = ""
    for art in results:
        art_url = "/blog/" + (art.get("slug") or "").lstrip("/")
        excerpt = (art.get("excerpt") or art.get("meta_description") or "")[:200]
        cards_html += (
            '<article style="padding:20px 0;border-bottom:1px solid var(--border)">'
            f'<h3 style="margin:0 0 6px"><a href="{_esc(art_url)}">{_esc(art.get("title", ""))}</a></h3>'
            f'<p style="color:var(--muted);font-size:.95rem;margin:0">{_esc(excerpt)}</p>'
            '</article>'
        )
    if not cards_html:
        if query:
            cards_html = f'<p style="color:var(--muted);text-align:center;padding:32px">No results for "<strong>{_esc(query)}</strong>".</p>'
        else:
            cards_html = '<p style="color:var(--muted);text-align:center;padding:32px">Type a query above to search.</p>'

    summary = ""
    if query:
        summary = f'<div style="color:var(--muted);font-size:.92rem;margin-bottom:12px">Found {len(results)} result(s) for "<strong>{_esc(query)}</strong>"</div>'

    body = (
        '<section><div class="container-narrow">'
        '<div class="breadcrumbs"><a href="/">Home</a> / Search</div>'
        '<h1>Search</h1>'
        f'{form_html}{summary}{cards_html}'
        '</div></section>'
    )
    return head + header + body + _render_team_section(site) + _render_footer(site)
