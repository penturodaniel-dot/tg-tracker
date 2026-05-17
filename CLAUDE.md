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
3. `uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1`

#### ⚠️ КРИТИЧНО: uvicorn `--workers 1`

**НЕ увеличивать без выноса ботов в отдельный сервис.** Подводный камень:

- В `main.py` `lifespan` стартуют 2 Telegram бота (`bot_manager.py`): BOT1 Трекер + BOT2 Уведомления. Они работают через **long-polling** (`getUpdates`).
- Telegram разрешает **только одну активную polling-сессию на bot token**.
- С `--workers 2+` каждый воркер запускает свою копию `lifespan` → 2 копии бота → `TelegramConflictError: terminated by other getUpdates request` в бесконечном retry-loop. Боты ломаются, уведомления и Subscribe-events в Meta CAPI не доходят.

**Как корректно скейлить FastAPI workers** (когда понадобится):

1. Создать **отдельный Railway service** с тем же репо
2. В этом service'е `Start Command`: `python -c "from bot_manager import run_bots; run_bots()"` (или аналог — функцию надо выделить из `lifespan`)
3. В основном FastAPI service'е убрать стартап ботов из `lifespan` (флаг env `DISABLE_BOT_POLLING=true` или просто отключить `bot_manager.start()` в lifespan)
4. Оба сервиса шарят `DATABASE_URL` (один Postgres)
5. Теперь FastAPI service можно скейлить `--workers 2/3/4` без конфликтов

Пока этого не сделано — **держать `--workers 1`** на основном service'е.

#### Cloudflare как frontline (важно для производительности)

DNS обоих SEO-доменов (`relaxtouchtoday.com`, `choiseforyoutoday.com`) на Cloudflare **в режиме Proxied** (🟠 оранжевое облако, НЕ серое). SSL/TLS mode = **Full (strict)** — нужно для совместимости с Railway (Railway сам выписывает SSL для custom domains).

**Page Rules для кэширования** (создать на каждом домене):
- URL pattern: `*relaxtouchtoday.com/*` (и аналогично `*choiseforyoutoday.com/*`)
- Cache Level: **Cache Everything**
- Edge Cache TTL: **1 hour**
- Browser Cache TTL: **30 minutes**

При создании Cloudflare предупреждает "may not apply to your traffic" — игнорировать (Cloudflare ищет wildcard DNS-запись `*.domain.com`, которой нет; реальные записи `@` и `www` в proxied режиме работают).

**Эффект:** при активных FB-кампаниях на лендинги (`/l/<slug>`) и Yelp/Google трафике на SEO-страницы p50 response time на Railway упал с 5-20 сек → 200-500мс. Сервер обрабатывает только cache misses (раз в час на каждую страницу).

**Что НЕ кэшировать** (если CRM админка на этом же домене): добавь второе Page Rule выше первого с `Cache Level: Bypass` для `/seo/*`, `/login`, `/api/*`. Cloudflare по умолчанию НЕ кэширует POST, так что формы безопасны и без этого.

**Проверка работы кэша:** DevTools → Network → header `cf-cache-status: HIT`. `MISS` нормально на первом запросе; повторный должен быть `HIT`.

#### Monitoring response time

Railway → service → **Metrics** / **Observability**. Здоровые значения для этого приложения:
- p50: 100-500 мс (с Cloudflare кэшем); 1-3 сек (без кэша, но при нормальной нагрузке)
- p99: 1-3 сек

Если **p50 > 3 сек** длительно — что-то не так: либо upstream traffic surge без кэша, либо медленный SQL-запрос блокирует worker, либо БД connection pool исчерпан.

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

**Кастомный домен на лендинг (1 домен = 1 кампания):**
- Поле `landings.custom_domain` (idempotent ALTER). Привязка через UI: `/landings/edit?id=X` → секция **«🌐 Кастомный домен»** → поле «Домен (без https:// и www.)» → POST `/landings/set_domain` → `db.set_landing_custom_domain`.
- ⚠️ UI-блок `domain_block` строится в `landings_edit` и **должен быть вставлен** в `content` f-string (после `{project_block}`). Если кто-то уберёт `{domain_block}` из сборки — форма пропадёт, бэкенд при этом продолжит работать (роут жив). Фикс восстановления — коммит `7c552be`.
- `CustomDomainMiddleware` на apex `/` делает `db.get_landing_by_domain(host)` (динамический lookup, без деплоя) → рендерит привязанный лендинг.
- Один домен нельзя привязать к 2 лендингам (БД-проверка по `custom_domain`).
- Порядок подключения: **Cloudflare zone+DNS+Bypass-кэш → Railway Custom Domain → CRM custom_domain → Meta domain verify**. Cloudflare для landing-доменов = **Cache Level: Bypass** (Cache Everything убьёт клик-трекинг — каждый заход должен дойти до сервера).

### Кнопки на лендингах и клик-трекинг
- На каждом лендинге настраиваются кнопки контактов (Telegram / WhatsApp)
- Клик на кнопку идёт через **относительный** `/go-staff?ref={ref_id}` (HR) или `/go?to=...` (client). **Relative, НЕ `{app_url}/go...`** — критично для мульти-домена: юзер остаётся на домене кампании, `_fbp` cookie не теряется (cookies domain-scoped), event_source_url совпадает с доменом браузерного Pixel. Фикс — коммит `a32d22d`.
- Endpoint:
  1. Создаёт запись в таблице `staff_clicks` (HR) / `click_tracking` (client) — `target_url`, `target_type`, `utm_*`, `fbclid`, `fbp`, `fbc`, `ttclid`, `ttp`. Для client `/go` также пишет **`click_tracking.source_domain`** = Host запроса (нужно для CAPI в bot-флоу, см. ниже).
  2. Шлёт server-side событие в Meta CAPI (Lead/Contact/Subscribe — `landings.fb_event`)
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

**`event_source_url` (мульти-домен):**
- `/go-staff` (HR/staff Subscribe/Contact) — берётся из **Host заголовка запроса** (домен кампании), фолбэк на `app_url` setting если Host пуст. FB + TikTok CAPI.
- bot-флоу (client Subscribe при вступлении в канал, `bot_manager.py`) — HTTP-запроса нет, поэтому берётся **`click_tracking.source_domain`** сохранённый в момент клика на `/go`; фолбэк на `app_url`. Фикс — коммиты `a32d22d` + `4354aec`.
- Итог: при 2+ доменах CAPI рапортует реальный домен кампании = совпадает с браузерным Pixel → корректная дедупликация Meta + проходит domain verification.

> ⚠️ **Операционный gotcha — `{{fbclid}}` в Meta Ads.** У Facebook **НЕТ макроса `{{fbclid}}`**. Если в Website URL рекламы вручную прописать `&fbclid={{fbclid}}` — FB его не раскрывает, и этот мусорный первый параметр **затирает** реальный `fbclid`, который FB сам автодобавляет в конец URL (FastAPI берёт первый дубль). Симптом: `[BOT1] matching=⚠️ слабый | fbclid=—` хотя fbp ловится. Код корректно нормализует `{{fbclid}}`→None (`database.py save_click`). **Фикс — в Meta Ads Manager:** убрать `fbclid={{fbclid}}` из URL (FB добавит реальный сам), валидные макросы (`{{ad.name}}` и т.п.) — в поле **URL Parameters**, не в самом URL. С реальным fbclid → `matching=✅✅ отличный` (fbclid+fbp+fbc+ip+ua).

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
- Google Fonts (Inter + Playfair Display) загружаются **асинхронно** через `media="print" onload="this.media='all'"` паттерн (CSS не блокирует render-path). `<noscript>` fallback для no-JS. Экономит ~780мс на mobile LCP.
- **Performance / Core Web Vitals оптимизации:**
  - `<link rel="preconnect">` для `fonts.googleapis.com`, `fonts.gstatic.com`, `res.cloudinary.com` — сокращает TLS handshake до CDN с картинками
  - `_render_head(..., preload_image=...)` — если передан URL, инжектит `<link rel="preload" as="image" fetchpriority="high">` для above-the-fold картинки (LCP candidate). `render_seo_article` передаёт `article.og_image` как preload_image.
  - Article cover image (`<img>` в начале статьи) рендерится с `loading="eager" fetchpriority="high" decoding="async"` — это LCP element выше fold, lazy здесь бьёт по Core Web Vitals.
  - URL картинки cover'а гонится через `_optimize_img_url()` (Cloudinary `f_auto,q_auto` → WebP/AVIF)
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
- **GA4 `phone_click` event** (default template) — если у сайта задан `ga_id`, в `<head>` после gtag-инициализации инжектится глобальный `document.addEventListener('click', ...)` который ловит клики по `<a href="tel:...">` и шлёт `gtag('event', 'phone_click', {phone_number, link_text, page_location, page_path})`. Это main conversion для local services (звонок = запись). Помечается как Key Event в GA4 Admin → Events. Jobs landing **НЕ** трогаем — там CTA = Telegram-кнопки + FB Pixel `Lead` event.

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
- **Авто-301 для удалённых страниц (SEO hygiene, коммит `5d25af8`):**
  - nested URL не найден (или draft в prod), но parent city существует и published → **301 на `/<city>`** (раньше silently рендерил city-страницу с 200 OK → duplicate content).
  - `/blog/<slug>` не найден (или draft в prod) → **301 на `/blog`**.
  - В preview-режиме оба остаются 404 (чтобы админ видел реальное draft-состояние).
  - Зачем: после tantric-пивота 30+ старых nested URL (swedish-massage и т.п.) висели в Google index. 301 даёт быстрый деиндекс (~7 дней vs ~30) + перенос link equity. Универсально для любых будущих bulk-delete без ручных entries в `seo_redirects`.
- `/search?q=...` — site search (LIKE по article title/h1/excerpt/meta_description/content_html). Honors language filter. Page отдаётся с `noindex`.
- `/sitemap.xml` / `/robots.txt`

**Админка** (на CRM-домене, под `/seo/*`):
- `/seo` — список сайтов
- `/seo/sites/{id}` — настройки (брендинг, домен, палитра, GA, status)
- `/seo/sites/{id}/locations` — города (CRUD), на каждой — адрес, координаты, **`google_maps_url`** (share-ссылка), FAQ JSON, hours JSON, контакты
- `/seo/sites/{id}/pages` — статические (about, contact, privacy, terms, services)
- `/seo/sites/{id}/articles` — блог (категория, автор, content_html, pillar-флаг, view counter)
- **Bulk-publish + per-row toggle status** — на листингах `locations`, `pages`, `articles`:
  - Сверху списка кнопка **«Опубликовать все драфты (N)»** (видна только если есть драфты, с confirm-popup). POST `/seo/sites/{id}/{type}/bulk-publish` — переключает все draft в published одной транзакцией.
  - Per-row кнопка **«Опубликовать» / «Снять»** рядом с delete. POST `/seo/sites/{id}/{type}/{item_id}/toggle-status` — toggle статуса конкретной сущности.
  - При первом переходе в published — автозаполняется `published_at` (через хелпер `_set_status_with_published_at`).
  - Экономит десятки кликов при активации больших импортов (30+ nested pages, 10 articles за раз).
- **Bulk-delete кнопки** (добавлены для tantric-пивота, остаются полезны для будущих rebranding-операций):
  - На `/articles`: красная **«Удалить все статьи (N)»** — POST `/seo/sites/{id}/articles/bulk-delete-all`. Strong confirm. Удаляет ВСЕ статьи сайта.
  - На `/pages`: красная **«Удалить все nested-страницы (N)»** — POST `/seo/sites/{id}/pages/bulk-delete-nested`. Удаляет только страницы где `slug` содержит `/` (= city × service nested). Static pages (about/contact/privacy/terms) **не трогает**.
- `/seo/sites/{id}/categories` / `/authors` / `/redirects`
- `/seo/sites/{id}/import` — **bulk-import JSON** (целая `site_settings` + категории + локации + страницы + статьи одним кликом). По умолчанию пропускает существующие slug; галка перезаписывает.
- `/seo/preview/{id}/{path:path}` — admin-preview, **обходит фильтр `status='live'/published'`** чтобы можно было смотреть черновики. Внутри переписывает root-relative ссылки в preview-prefix чтобы навигация осталась внутри `/seo/preview/{id}/...`. **Важно:** при rewrite не переносить старые headers — `Content-Length` стухнет → пустая страница. Использовать `HTMLResponse(content=html, status_code=...)` без `headers=...`.
- `/seo/upload` (POST, multipart) — **загрузчик картинок** через Cloudinary. Принимает `file`, проверяет content-type=`image/*`, max 10 MB, заливает в папку `seo/`, возвращает `{url}`. Используется кнопкой «Загрузить» в админ-формах через JS (`seoUploadImage`). Альтернатива ручному копированию URL — особенно полезно потому что часть внешних CDN (Unsplash и т.д.) хотлинк-блочат.

**Image fields в формах:** все поля картинок (`logo_url`, `favicon_url`, `default_og_image`, `og_image` на location/page/article, `avatar_url` на author) рендерятся через хелпер `_f_image_url()` — URL-инпут + кнопка «📤 Загрузить» + live-превью thumbnail. JS-handlers (`seoUpdImgPreview`, `seoUploadImage`) встроены в `_ADMIN_CSS` (constant в routers/seo.py — содержит `<style>` + `<script>`).

**Доступ к админке:** только role=`admin`. Manager → 403.

**Sidebar:** пункт «SEO → Сайты» добавлен в обе версии (React `NavSidebar.jsx` для TG-чатов и HTML `nav_html()` для всех остальных страниц).

**Стартовый контент в репозитории:**

*RelaxTouch (relaxtouchtoday.com — Tantric Wellness, default template). Перепрофилировано 2026-05 со wellness/spa на mindful tantric massage. 6 активных локаций.*
- `docs/seo-content/relaxtouch-bootstrap.json` — 1 site_settings + 4 categories (tantric-practices, mindful-body, newcomers-guide, city-guides) + 1 author + 4 static pages + **6 locations only** (LA, Costa Mesa, Newark, Arlington, Chicago, Brooklyn).
  - Каждая локация **расширена** до ~700-900 слов (с 250 было). Используются 3 слота: `intro_html` (короткий hero-параграф) + `services_html` (услуги+цены) + **`about_studio_html`** (новый — рендерится как секция "About Our Studio" под Services). about_studio_html содержит 3 H3-подзаголовка: **Getting here** (район, transit lines, freeways, парковка), **Who we tend to see** (профиль клиента города), **Why [City], specifically** (философское обоснование). Контент **уникален per city** — раньше Google трактовал 6 локаций как near-duplicates и индексировал только одну.
  - `faq_json` расширен до **7-9 вопросов** на локацию (с 3-4 было). Включает 2-3 city-specific (Metro lines, parking, проблема winter weather для Chicago, suburb service area, и т.д.) + обязательные generic (first session, what to wear, medical disclaimer, **How do I book** = phone only, **How do I pay** = cash only).
- `docs/seo-content/relaxtouch-articles-batch-1.json` — 5 pillar-статей: What Is Tantric Massage (Really), Your First Tantric Session, Tantric vs Sensual, Why Slow Touch Matters, Tantric Massage for Stress/Anxiety/Burnout
- `docs/seo-content/relaxtouch-articles-batch-2.json` — 5 supporting articles: How to Prepare, Etiquette/Tipping, Tantric for Couples (honest take — не offering "couples session"), How to Choose a Specialist, History of Tantric Bodywork in the West
- `docs/seo-content/relaxtouch-city-service-pages-LA.json` — 4 nested City × Service страниц для Los Angeles (`los-angeles-ca/tantric-full-body-massage`, `/sensory-massage`, `/slow-touch-massage`, `/deep-body-connection-massage`)
- `docs/seo-content/relaxtouch-city-service-pages-batch-2.json` — 20 nested страниц (Costa Mesa, Newark, Arlington, Chicago, Brooklyn × 4 услуги). Сгенерировано через `build_city_service_pages_tantric.py` в `C:\Users\user\AppData\Local\Temp\`.
- Цены: **60 min — $230**, **30 min — $200** (2-tier).
- 4 услуги: **Tantric Full Body Massage** (signature) / **Sensory Massage** / **Slow Touch Massage** / **Deep Body Connection Massage**. Без "Couples" как отдельной услуги — есть статья про couples с альтернативой (две сессии back-to-back в соседних комнатах).
- **Изображения**: 7 реальных Cloudinary URL клиента **зашиты в JSON** (default_og_image, 6 location og_image, 10 article og_image, 24 nested page og_image — ротация). Не сбрасываются на placeholder при re-import.
- **Бизнес-политики (закреплены везде):**
  - **Booking: phone only** — каждая FAQ "How do I book?" говорит "Bookings are taken by phone only... We do not accept bookings through email, online forms, or third-party platforms." Contact page тоже переписан.
  - **Payment: cash only** — каждая локация имеет FAQ "How do I pay?" с "Cash only, paid at the studio... We do not currently accept card or online payments." Schema.org `paymentAccepted` = `["Cash"]` only.
- **Tone of voice / правила контента (закреплены везде после нескольких чисток):**
  - НЕ используем "practitioner" / "bodyworker" / "therapist" / "licensed therapist" — используем **"specialist"** (singular) / **"our specialists"** (plural) / "our team". Применено по всему контенту через word-boundary regex (`\bpractitioner\b` → `specialist` etc.).
  - НЕ используем **никаких** trigger-words: `sexual`, `genital`, `happy ending`, `extras`, `awakening`, `intimate`. По всему публичному контенту 0 occurrences.
  - НЕ используем медицинские заявки ("heal/cure/treat") — используем "support/ease/relieve". Медицинский disclaimer ("we don't diagnose, treat or claim to cure... please consult a licensed healthcare provider") **сохранён** дословно — юридически важен.
  - НЕ используем gov/federal/military framing (Arlington изначально позиционировался через "federal employees / government contractors / military / Pentagon City corridor" — всё убрано, заменено на "central Arlington" / "professionals, lawyers, tech and finance / DC-area commuters"). По всему репо 0 occurrences `federal`/`government`/`military`/`Pentagon`/`contractor`/`lobbyist`.
  - **Исключение по trigger-words: `legal-update-relaxtouch.json` (Terms of Service)** — в Conduct clause намеренно сохранена фраза "sexual harassment" как стандартная legal protection language. Это даёт студии контрактное основание прерывать сессию и взимать полную плату при недопустимом поведении. Юридически обязательно, не трогать.
- `docs/seo-content/legal-update-relaxtouch.json` — юр-инфа Digital Chaos Inc. (NY) + Privacy + Terms (US-формат, Richmond County jurisdiction, CCPA + GDPR rights)
- **Скрипты-помощники** (в `C:\Users\user\AppData\Local\Temp\`, не в репо):
  - `build_city_service_pages_tantric.py` — генератор 24 nested pages
  - `expand_locations.py` — расширение 6 locations до 700-900 слов
  - `apply_real_images.py` — простановка Cloudinary URLs во все og_image поля
  - `apply_naming_payment_fixes.py` — practitioner→specialist + phone-only + cash-only
  - `remove_gov_references.py` — чистка federal/government из Arlington
  - `remove_prenatal.py` — историческая чистка prenatal-упоминаний (до пивота)
  Все скрипты idempotent; можно перезапускать без последствий.

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
