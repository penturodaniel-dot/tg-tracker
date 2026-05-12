# TGTracker CRM — CLAUDE.md

## Что это за проект

CRM-система для отслеживания лидов и общения с клиентами через Telegram и WhatsApp,
плюс мульти-сайтовая SEO-CMS для продвижения контентных проектов в Google.

Основные задачи:
- Трекинг вступлений в TG-каналы → Meta / TikTok Conversions API
- Управление перепиской в подключённом TG-аккаунте (Telethon) и WhatsApp
- Аналитика по лидам и сотрудникам
- **SEO-модуль:** мульти-сайт CMS под кастомные домены — лендинги по городам, статьи, статические страницы, sitemap, Schema.org, контакты на локацию (TG / phone / WA / email)

---

## Стек

| Слой | Технологии |
|---|---|
| Backend | Python 3.11, FastAPI, uvicorn |
| Frontend | React + Vite (сборка в `frontend/dist/`, коммитится в git) |
| БД | PostgreSQL (psycopg2, `DATABASE_URL`) |
| TG боты | aiogram 3.7 (2 бота: трекер + уведомления) |
| TG аккаунт | Отдельный сервис на Railway (Telethon) — `TG_SERVICE_URL` |
| WA | Отдельный WA-сервис — `WA_SERVICE_URL` |
| Медиафайлы | Cloudinary |
| Реклама | Meta Conversions API v19, TikTok CAPI |
| Деплой | Railway (nixpacks) |

---

## Переменные окружения (Railway)

```
DATABASE_URL          # PostgreSQL строка подключения
DASHBOARD_PASSWORD    # Пароль входа в CRM (сохраняется в settings таблице)
BOT_TOKEN             # Бот 1 — Трекер (вступления в каналы)
BOT2_TOKEN            # Бот 2 — Уведомления (авторизация, новые сообщения)
PIXEL_ID              # Meta Pixel ID (глобальный)
META_TOKEN            # Meta Conversions API токен
APP_URL               # Публичный URL приложения (https://...)
TG_SERVICE_URL        # URL Telethon-сервиса (TG аккаунт)
TG_API_SECRET         # Секрет для вызовов TG сервиса из CRM
TG_WEBHOOK_SECRET     # Секрет для вебхуков от TG сервиса
WA_SERVICE_URL        # URL WA-сервиса
WA_API_SECRET         # Секрет для вызовов WA сервиса
WA_WEBHOOK_SECRET     # Секрет для вебхуков от WA сервиса
CLOUDINARY_CLOUD_NAME # Cloudinary
CLOUDINARY_API_KEY
CLOUDINARY_API_SECRET
```

---

## Структура файлов

```
main.py                  # FastAPI app, lifespan, auth, лендинги, роутинг,
                          #   CustomDomainMiddleware (SEO + landings)
database.py              # Класс Database — все SQL-запросы, in-memory TTL кэш
bot_manager.py           # BOT1 (Трекер) + BOT2 (Уведомления) — aiogram
meta_capi.py             # Meta Conversions API — send_subscribe_event()
tiktok_capi.py           # TikTok CAPI
cloudinary_upload.py     # Загрузка медиа на Cloudinary
client_templates.py      # HTML-шаблоны клиентских страниц
landing_templates.py     # HTML-шаблоны лендингов (несколько вариантов)
seo_templates.py         # HTML/XML-рендереры публичных страниц SEO-сайтов
                          #   (главная, локация, статья, sitemap, robots, 404)

routers/
  chat_tga.py            # TG Аккаунт чат (переписка через Telethon-сервис)
  chat_wa.py             # WhatsApp чат
  chat_bot.py            # Telegram бот чат
  analytics.py           # Аналитика клиентов и сотрудников
  staff.py               # База сотрудников, бонусы
  channels.py            # Telegram каналы
  projects.py            # Проекты (пиксели, utm)
  scripts.py             # Скрипты продаж
  users_tags.py          # Пользователи CRM, теги, права доступа
  settings.py            # Настройки CRM (боты, пиксели, безопасность)
  seo.py                 # SEO-модуль: dispatch_seo_request (для middleware)
                          #   + админка под /seo/* (CRUD сайтов / локаций /
                          #   страниц / статей / контактов / редиректов)
                          #   + bulk JSON import + admin preview

frontend/
  src/
    components/NavSidebar.jsx   # Боковое меню (включая пункт SEO)
    ...                         # Остальные React-компоненты
  dist/                  # Скомпилированный бандл — КОММИТИТСЯ В GIT
  package.json
  vite.config.js

seo_templates_jobs.py    # Альтернативный шаблон 'jobs_landing' для HR-сайтов
                          # (pink/magenta gradient, Montserrat+Open Sans,
                          # FB Pixel Lead-event на Telegram-кнопках,
                          # i18n ru/ua/en, JobPosting Schema.org)

docs/
  seo-content/
    relaxtouch-bootstrap.json              # RelaxTouch (relaxtouchtoday.com):
                                             # site_settings + categories + authors
                                             # + 4 static pages + 15 locations
    relaxtouch-articles-batch-1.json       # 5 статей RelaxTouch, ~6,400 слов
    relaxtouch-articles-batch-2.json       # 5 статей RelaxTouch, ~5,800 слов
    choiseforyoutoday-bootstrap.json       # ChoiseForYouToday (choiseforyoutoday.com):
                                             # JobsLanding-сайт, мигрирован с Lovable.dev,
                                             # 19 статей ru/ua/en + JobPosting schema
    legal-update-relaxtouch.json           # Юр. данные Digital Chaos Inc. + privacy/terms
    legal-update-choiseforyoutoday.json    # Юр. данные + privacy/terms/about на русском
    favicons/
      relaxtouch.svg                       # SVG фавикон RelaxTouch (R monogram)
      relaxtouch-leaf.svg                  # SVG фавикон RelaxTouch (стилизованный лист)
      choiseforyoutoday.svg                # SVG фавикон Choise (M monogram)
      choiseforyoutoday-chat.svg           # SVG фавикон Choise (chat bubble)
    # (импорт через /seo/sites/{id}/import; slug-based upsert)
```

---

## Команды разработки

### Первый запуск / установка

```bash
pip install -r requirements.txt
cd frontend && npm install
cd frontend && npm run build  # собрать React
uvicorn main:app --reload     # запустить dev-сервер
```

### После изменения JSX/React-файлов

```bash
cd frontend && npm run build  # ОБЯЗАТЕЛЬНО после каждого изменения .jsx
git add frontend/dist/        # коммитить dist — он отдаётся как статика
```

> **Важно:** `frontend/dist/` коммитится в репозиторий и служится FastAPI как статика.
> Изменения в `.jsx` файлах не видны в браузере без пересборки бандла.

### Деплой (Railway)

Railway автоматически запускает nixpacks:
1. `pip install -r requirements.txt`
2. `cd frontend && npm install && npm run build`
3. `uvicorn main:app --host 0.0.0.0 --port $PORT`

---

## Архитектурные особенности

### Аутентификация
- Cookie `session_id` (SHA256-хэш), TTL 12ч (настраивается в settings)
- Rate limiting /login: 5 попыток за 10 мин с одного IP
- Права доступа по вкладкам через `require_auth(tab="tab_id")`
- Роли: `admin` (все права) и `manager` (только разрешённые вкладки)

### База данных
- Класс `Database` в `database.py`, все методы там
- In-memory TTL кэш (4 сек) для частых запросов — `_TTLCache`
- Настройки хранятся в таблице `settings` (key/value)
- Env-переменные → `settings` таблица при первом старте (если ещё нет значения)

### Боты (bot_manager.py)
- **BOT1 — Трекер**: отслеживает вступления в каналы, привязывает к кликам, отправляет Subscribe в Meta CAPI
- **BOT2 — Уведомления**: отправляет уведомления менеджеру о новых сообщениях
- Боты стартуют в `lifespan` FastAPI, токены берутся из `settings` таблицы

### TG Аккаунт (Telethon-сервис)
- Отдельный Railway-сервис (`tg-service` репозиторий)
- CRM общается с ним через HTTP API (`TG_SERVICE_URL`)
- Входящие/исходящие сообщения → вебхук на `/tga/webhook`
- Исходящие сообщения (написанные прямо в Telegram) синхронизируются через `is_outgoing: True`
- Дедупликация по `tg_msg_id` в таблице `tg_account_messages`

### Лендинги
- Несколько шаблонов в `landing_templates.py` (для клиентов и для HR/staff)
- Клиентский лендинг рендерится через `client_templates.py` если `landing.type == "client"`
- Поддержка кастомных доменов через `CustomDomainMiddleware`
- URL: `/l/{slug}` или кастомный домен → корень

### Кнопки на лендингах и клик-трекинг
- На каждом лендинге настраиваются кнопки контактов (Telegram / WhatsApp)
- Клик на кнопку идёт через `/go-staff?ref={ref_id}` (для HR-лендингов) или эквивалентный endpoint
- Endpoint:
  1. Создаёт запись в таблице `staff_clicks` (сохраняет `target_url`, `target_type`, `utm_*`, `fbclid`, `fbp`, `fbc`, `ttclid`, `ttp`)
  2. Шлёт server-side событие в Meta CAPI (Lead/Contact/Subscribe — что настроено на лендинге, поле `landings.fb_event`)
  3. Редиректит юзера на t.me / wa.me ссылку
- Поле `staff_clicks.target_url` — ссылка t.me или wa.me на конкретный аккаунт
- При телеграмном клике в URL добавляется `?start=ref_{ref_id}` чтобы можно было точно сматчить когда юзер напишет

### Атрибуция входящих TG-сообщений (chat_tga.py)
Когда подключённый TG-аккаунт получает первое сообщение от нового юзера, CRM пытается найти соответствующий клик в `staff_clicks`. Логика в 3 шага:

1. **По `ref_XXX` в тексте сообщения** — если юзер пришёл по `/start ref_AAA` и Telegram прислал это в первом сообщении (через `db.get_staff_click(ref_id)`).
2. **Time-window 3 минуты** — берёт последний клик `target_type='telegram'` за 3 минуты, **отфильтрованный по target_url, ведущему именно на ПОДКЛЮЧЁННЫЙ TG-аккаунт** (через `db.get_staff_click_recent_for_account(minutes, tg_username, tg_phone)`). Подключённый аккаунт берётся из настроек `tg_account_username` и `tg_account_phone`.
3. **По `tg_user_id`** за 30 дней (через `db.get_staff_click_by_tg_user`) — если юзер уже когда-то был привязан.

После успешного матча CRM записывает `utm_*`, `fbclid`, `fbp`, `fbc` в `tg_account_conversations`, привязывает клик к `tg_user_id` (`bind_staff_click_to_tg_user`) и помечает `used=1`.

> **Важно:** в шаге 2 фильтрация по target_url критична. Если её не делать (как было в старой версии), параллельные клики на лендинги других кампаний (operators_dnepr и т.п.) будут попадать в сообщения, идущие в наш аккаунт, и присваивать им чужой тег. См. фикс в коммите `03d60ee`.

### Meta CAPI matching
Для атрибуции нужны (в порядке важности):
1. `fbclid` → `fbc` (из URL лендинга)
2. `_fbp` cookie (устанавливается Meta Pixel)
3. `external_id` = sha256(telegram_user_id)
4. IP-адрес и User-Agent (помогают делать matching, сохраняются при клике)

### SEO-модуль (мульти-сайт CMS)

Полностью изолированный модуль. **НЕ зависит** и **не модифицирует** существующую логику чатов, лидов, лендингов, ботов или CAPI.

**Архитектура:**
- 8 таблиц с префиксом `seo_`: `seo_sites`, `seo_locations`, `seo_location_contacts`, `seo_pages`, `seo_categories`, `seo_authors`, `seo_articles`, `seo_redirects`. Lazy init через `_init_seo_tables()`.
- Каждый сайт — независимая конфигурация: домен, язык, бренд, палитра, GA, FB Pixel, Schema.org Organization, кастомный header/footer HTML.
- Status сайта: `draft` (виден только в админ-preview) или `live` (отдаётся публично на своём домене).

**Маршрутизация (CustomDomainMiddleware в `main.py`):**
1. Системный домен (`*.railway.app`, `localhost`) → передача дальше по обычной логике CRM.
2. Кастомный домен есть в `seo_sites` И `status='live'` → `dispatch_seo_request(request, site)` из `routers/seo.py`. Все ошибки внутри ловятся → middleware никогда не падает из-за SEO-багов.
3. Иначе → фолбэк на существующую логику лендингов (без изменений).

**Мульти-шаблон система:** каждый сайт может выбрать `template` (поле в `seo_sites`):
- `default` — wellness/spa style (RelaxTouch). Inter + Playfair Display, sage-палитра. Hero + locations grid + recent articles на главной. См. `seo_templates.py`.
- `jobs_landing` — HR/recruitment landing (ChoiseForYouToday). Pink/magenta gradient, Montserrat + Open Sans. Полный landing с hero/about/benefits/requirements/how/offers/CTA. Strings i18n (ru/ua/en) выбираются по `site.language`. См. `seo_templates_jobs.py`.

Диспатчер в `routers/seo.py` ветвится по `site.template` для homepage / blog index / article / page / 404. Локации только в default (jobs_landing их не использует — это лендинги без множественных адресов).

**Публичный рендер (`seo_templates.py` — default + общие хелперы):**
- Полная SEO-обвязка: `<title>`, meta description, canonical, Open Graph, Twitter Card, Schema.org JSON-LD (`Organization`, `WebSite`, `LocalBusiness` + `HealthAndBeautyBusiness`, `Article`, `BreadcrumbList`, `FAQPage`, `Service`/`OfferCatalog`)
- `sitemap.xml` и `robots.txt` генерируются автоматически на каждый сайт
- Inline CSS с подстановкой палитры через `__PRIMARY__` / `__SECONDARY__` (через `.replace()`, НЕ `%`-formatting — в CSS есть `100%` который ломает % syntax)
- Google Fonts (Inter + Playfair Display) с `font-display: swap`
- Mobile-responsive
- Контакт-кнопки: `tel:`, `mailto:`, `t.me/`, `wa.me/`, `sms:` + inline SVG-иконки
- **Локации**: встроенный Google Maps iframe (без API-ключа, через `maps.google.com/maps?q=lat,lng&output=embed`) + кнопка «Open in Google Maps» (приоритет — пользовательский `google_maps_url`, иначе строится из координат). На странице города **автоматически** появляется секция «Our Services in [City]» если в `seo_pages` есть child-страницы со slug'ами `<city-slug>/<service-slug>` — карточки со ссылками на каждый nested page. Это hub-перелинковка для PageRank-flow.
- **Статьи**: автоматическая внутренняя перелинковка через `_auto_link_internal_articles()` — карта `_INTERNAL_LINK_MAP` (slug → варианты ключевых фраз) ищется в `content_html`, первое вхождение каждой фразы заменяется ссылкой на `/blog/{slug}`. Защищены `<a>`, `<h1-6>`, `<code>`, `<pre>`. Один линк на target slug на статью. Не линкует сам в себя.
- **«Updated:» дата** — если `article.updated_at` отличается от `published_at`, рендерится «Updated: YYYY-MM-DD» с `<time itemprop="dateModified">`. Freshness signal для Google.
- **FAQPage Schema** — авто-парсится из тела статьи (находит H2 «Frequently asked questions» / «Часто задаваемые вопросы» и парсит H3+P пары). Локации тоже получают FAQPage из `faq_json`.
- **BreadcrumbList Schema** — на каждой статье / странице / локации / nested-page (с правильной иерархией Home › City › Service для nested).
- **Image optimization**: `_optimize_img_url()` для Cloudinary URL'ов инжектит `f_auto,q_auto` → авто-WebP/AVIF + auto-quality. Все `<img>` теги имеют `loading="lazy"` (кроме FB Pixel noscript).
- **Our Team block**: `_render_team_section(site)` рендерит `site.team_html` (если задано) перед футером на ВСЕХ страницах — задаётся в админке 1 раз, отображается везде.
- **Footer «Our Locations»** (default) — диспатчер инжектирует `site["_footer_locations"]` (до 8 городов с primary-телефоном); footer рендерит 4-ю колонку.
- **Site search** — `/search?q=...` — простой LIKE-поиск по статьям с language-фильтром. Search-страницы `noindex` (best practice).

**Jobs Landing рендер (`seo_templates_jobs.py`):**
- Те же SEO-хелперы (`_schema_organization`, `_schema_article`, `_auto_link_internal_articles`) что в default — реюзаются
- Свой `_render_jobs_head` — Montserrat + Open Sans + Pixel + GA + JobPosting schema
- Свой `_render_jobs_header` — навигация с anchor-ссылками на секции главной
- Свой `_render_jobs_footer` — 3 колонки + legal-row с ссылками на /privacy, /terms (E-E-A-T) + copyright
- `_tg_btn(site, ...)` хелпер — все Telegram-кнопки шлют **`fbq('track','Lead')`** при клике (если `site.fb_pixel_id` задан, иначе guard `typeof fbq==='function'` пропускает)
- Полная homepage из секций: hero / about+banner / benefits-grid (6 cards) / requirements / how-it-works (3 steps) / offers / CTA
- Локализация ru/ua/en через embedded `T` dict
- Использует `site.color_primary` / `color_secondary` для всех градиентов через CSS `.replace()` подстановку
- `site.hero_image_url` — фото человека на главной (опц.)
- `site.secondary_image_url` — фон баннера в about (опц.)
- `site.telegram_url` / `site.whatsapp_url` — точки контакта
- ⚠️ Python 3.11 не поддерживает PEP 701 (вложенные f-string с одинаковыми кавычками). На production используется 3.11 — **избегай нестинга f-string**, только plain string concat. Иначе `import` упадёт → middleware вернёт «Internal error». Локально 3.13 не отловит этот баг — проверяй через `ast.parse(feature_version=(3,11))`.

**Language-фильтр для листингов:** на мульти-язычных сайтах (типа choise: ru/ua/en статьи в одной БД) каждая статья импортирована с `tags='ru'/'ua'/'en'`. Диспатчер в `/blog`, на главной (recent), и в related статьи передаёт `tag_filter=site.language` → показывает только нужный язык. Прямой `/blog/<slug>` URL **НЕ** фильтрует — все статьи доступны → Google продолжает индексировать ua/en URL'ы которые уже были в индексе.

⚠️ **«Толерантный» фильтр** в `get_seo_articles` (Python-side post-filter):
- Статья с `tags` совпадающим с `tag_filter` → показать
- Статья **без** language-тегов вообще (только топические типа «swedish, beginner») → показать как language-agnostic
- Статья с другим language-тегом (en на ru-сайте) → скрыть

Это нужно потому что на одно-язычных сайтах (типа RelaxTouch — все статьи на en, теги топические) строгий SQL-фильтр всё бы скрыл. Recognized lang tags: `ru, ua, uk, en, es, de, fr, pl, it, pt`.

**Маршруты публичные** (на SEO-домене):
- `/` — главная (locations grid + recent articles в default; полный landing в jobs_landing)
- `/blog` — индекс статей
- `/blog/category/<slug>` — статьи рубрики
- `/blog/<slug>` — статья
- `/<slug>` — локация (приоритет) или статическая страница
- `/<city-slug>/<service-slug>` — **nested service-page** (например `/los-angeles-ca/swedish-massage`). Диспатчер ищет `seo_pages.slug == 'los-angeles-ca/swedish-massage'`. Если есть — рендер с breadcrumb `Home › City › Service` через `parent_location` параметр в `render_seo_page`.
- `/search?q=...` — site search (LIKE по article title/h1/excerpt/meta_description/content_html). Honors language filter. Page отдаётся с `noindex`.
- `/sitemap.xml` / `/robots.txt`

**Админка** (на CRM-домене, под `/seo/*`):
- `/seo` — список сайтов
- `/seo/sites/{id}` — настройки (брендинг, домен, палитра, GA, status)
- `/seo/sites/{id}/locations` — города (CRUD), на каждой — адрес, координаты, **`google_maps_url`** (share-ссылка), FAQ JSON, hours JSON, контакты
- `/seo/sites/{id}/pages` — статические (about, contact, privacy, terms, services)
- `/seo/sites/{id}/articles` — блог (категория, автор, content_html, pillar-флаг, view counter)
- `/seo/sites/{id}/categories` / `/authors` / `/redirects`
- `/seo/sites/{id}/import` — **bulk-import JSON** (целая `site_settings` + категории + локации + страницы + статьи одним кликом). По умолчанию пропускает существующие slug; галка перезаписывает.
- `/seo/preview/{id}/{path:path}` — admin-preview, **обходит фильтр `status='live'/published'`** чтобы можно было смотреть черновики. Внутри переписывает root-relative ссылки в preview-prefix чтобы навигация осталась внутри `/seo/preview/{id}/...`. **Важно:** при rewrite не переносить старые headers — `Content-Length` стухнет → пустая страница. Использовать `HTMLResponse(content=html, status_code=...)` без `headers=...`.
- `/seo/upload` (POST, multipart) — **загрузчик картинок** через Cloudinary. Принимает `file`, проверяет content-type=`image/*`, max 10 MB, заливает в папку `seo/`, возвращает `{url}`. Используется кнопкой «Загрузить» в админ-формах через JS (`seoUploadImage`). Альтернатива ручному копированию URL — особенно полезно потому что часть внешних CDN (Unsplash и т.д.) хотлинк-блочат.

**Image fields в формах:** все поля картинок (`logo_url`, `favicon_url`, `default_og_image`, `og_image` на location/page/article, `avatar_url` на author) рендерятся через хелпер `_f_image_url()` — URL-инпут + кнопка «📤 Загрузить» + live-превью thumbnail. JS-handlers (`seoUpdImgPreview`, `seoUploadImage`) встроены в `_ADMIN_CSS` (constant в routers/seo.py — содержит `<style>` + `<script>`).

**Доступ к админке:** только role=`admin`. Manager → 403.

**Sidebar:** пункт «SEO → Сайты» добавлен в обе версии (React `NavSidebar.jsx` для TG-чатов и HTML `nav_html()` для всех остальных страниц).

**Стартовый контент в репозитории:**

*RelaxTouch (relaxtouchtoday.com — wellness/spa, default template):*
- `docs/seo-content/relaxtouch-bootstrap.json` — 1 site_settings + 4 categories + 1 author + 4 static pages + 15 location pages
- `docs/seo-content/relaxtouch-articles-batch-1.json` — 5 pillar-статей (~6,400 слов): Swedish vs Deep Tissue, How Often, First Massage, Science-Backed Benefits, Hot Stone
- `docs/seo-content/relaxtouch-articles-batch-2.json` — 4 статьи (~4,600 слов): Lower Back Pain, Tipping Etiquette, Sports Massage Runners, How to Choose a Therapist
- `docs/seo-content/relaxtouch-city-service-pages-LA.json` — 5 nested City × Service страниц для Los Angeles (`los-angeles-ca/swedish-massage`, `/deep-tissue-massage`, `/hot-stone-massage`, `/sports-massage`, `/couples-massage`) — long-tail keywords, ~400-700 слов каждая, FAQ + pricing + CTA на /los-angeles-ca
- `docs/seo-content/relaxtouch-city-service-pages-batch-2.json` — 25 nested City × Service страниц (Costa Mesa CA, Newark CA, Arlington VA, Chicago IL, Brooklyn NY × 5 услуг). Сгенерировано через `build_city_service_pages.py` (~9,400 слов, 90 KB)
- `docs/seo-content/legal-update-relaxtouch.json` — обновление с реальной юридической инфой (`Digital Chaos Inc.`, NY, 252 Seaview Ave, Staten Island, NY 10305) + Privacy + Terms (US-формат, Richmond County jurisdiction, CCPA + GDPR rights)

*ChoiseForYouToday (choiseforyoutoday.com — HR/jobs, jobs_landing template):*
- `docs/seo-content/choiseforyoutoday-bootstrap.json` — 1 site_settings (template=jobs_landing, ru, FB Pixel `1321696403049126`, Google Site Verification `XvBJpr-...`) + 3 categories (work/success/life) + 1 author + 1 homepage page (с JobPosting Schema.org) + 19 articles (ru/ua/en mix). Контент сграблен с публичного Supabase REST API при миграции с Lovable.dev.
- `docs/seo-content/legal-update-choiseforyoutoday.json` — юр. данные + Privacy + Terms + About страницы на русском (anti-scam уведомление в About: «услуги бесплатны для кандидаток»)

*Favicons:*
- `docs/seo-content/favicons/*.svg` — SVG фавиконки для обоих сайтов (по 2 варианта каждому)

Все импортируются через `/seo/sites/{id}/import`. Slug-based upsert (skip-existing по умолчанию, галка для перезаписи).

**Юридическое лицо:** оба сайта (RelaxTouch и ChoiseForYouToday) операторируются одной компанией — `Digital Chaos Inc.`, Domestic Business Corp., County of Richmond, NY State, 252 Seaview Ave, Staten Island, NY 10305. EIN — приватный, **никогда не публиковать на сайте/в Schema.org**.

### Ключевые таблицы

**Существующие (CRM core):**
- `clicks` — клики на клиентских лендингах (для трекинга вступлений в каналы)
- `staff_clicks` — клики на HR/staff лендингах (для трекинга первого сообщения в TG/WA)
- `tg_account_conversations` / `tg_account_messages` — переписка через Telethon
- `wa_conversations` / `wa_messages` — переписка через WhatsApp
- `conversations` — переписка через бот-аккаунт
- `projects` — рекламные проекты (свой пиксель, токен, traffic_source, fb_event)
- `landings` — лендинги (привязка к проекту, `fb_event`, `traffic_source`)
- `channels`, `campaigns` — TG-каналы и рекламные кампании на них
- `staff` — база сотрудников
- `settings` — key/value настройки CRM

**SEO-модуль:**
- `seo_sites` — сайты:
  - Базовые: домен, язык, брендинг, GA/Pixel, header/footer HTML, status, color_primary/secondary
  - **`template`** — `'default'` или `'jobs_landing'` — определяет рендер главной + внутренних страниц (ALTER через `_init_seo_tables()`)
  - **`hero_image_url`** / **`secondary_image_url`** — для jobs_landing (hero фото + banner)
  - **`telegram_url`** / **`whatsapp_url`** — точки контакта (jobs_landing рисует кнопки CTA)
  - **`team_html`** — HTML-блок «Our Team» (имена + фото), рендерится перед футером на ВСЕХ страницах сайта (homepage, locations, articles, blog index, static pages, search). Single source of truth — заполняется один раз в `/seo/sites/{id}` и распространяется автоматически. Шаблон с placeholder-разметкой подставляется из админки.
- `seo_locations` — города на сайте (адрес, lat/lng, **`google_maps_url`**, FAQ JSON, hours JSON). Колонка `google_maps_url` добавлена через `ALTER TABLE IF NOT EXISTS`.
- `seo_location_contacts` — телефоны / TG / WA / email на локацию (contact_type, value, is_primary, is_active)
- `seo_pages` — статические страницы (about, contact, privacy, terms, services) **+ nested City × Service страницы** (slug содержит `/`, напр. `los-angeles-ca/swedish-massage`). Диспетчер в `routers/seo.py` сначала проверяет full path как slug → если найдено и parent-slug совпадает с локацией, рендерит как nested service page с breadcrumbs `Home → City → Service` + хаб-перелинковкой (city ↔ service bidirectional для PageRank flow). Поле `slug=''` зарезервировано под homepage-page для jobs_landing (туда кладётся title/meta_description/og_image/JobPosting schema_json для главной).
- `seo_articles` — блог (slug → category_id, author_id, content_html, is_pillar, view_count, **`tags`** хранит CSV-теги, в т.ч. язык `ru`/`ua`/`en` для language-фильтра в листингах)
- `seo_categories` / `seo_authors`
- `seo_redirects` — 301/302 редиректы с трекингом hits

---

## Права доступа (tab IDs)

```
channels, campaigns, landings           # Клиенты
tg_account_chat, wa_chat                # Чаты
staff, staff_bonuses, scripts           # Сотрудники
landings_staff, analytics_staff         # HR
analytics_clients                       # Аналитика клиентов
seo                                     # SEO-модуль (admin-only)
tags, users, projects, settings         # Настройки (admin-only)
```

> Боковая навигация описана в **двух местах**:
> - `frontend/src/components/NavSidebar.jsx` — React-сайдбар (виден только в TG-чатах, кэшируется в `frontend/dist/`)
> - `main.py` функция `nav_html()` — HTML-сайдбар (виден на всех остальных страницах)
>
> При добавлении нового пункта меню **нужно править оба файла** + ребилдить React: `cd frontend && npm run build && git add frontend/dist/`.

---

## Внешние сервисы

| Сервис | Назначение | Конфиг |
|---|---|---|
| Meta CAPI | Subscribe events при вступлении в канал | `PIXEL_ID`, `META_TOKEN` |
| TikTok CAPI | Аналог Meta для TikTok | в settings таблице |
| Cloudinary | Хранение медиафайлов | `CLOUDINARY_*` |
| Telethon TG Service | Прямая переписка через TG аккаунт | `TG_SERVICE_URL` |
| WA Service | WhatsApp Business API | `WA_SERVICE_URL` |
| Railway | Хостинг | nixpacks, `PORT` env |
