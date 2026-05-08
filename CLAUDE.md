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

docs/
  seo-content/
    relaxtouchtoday-bootstrap.json  # Стартовый контент для SEO-сайтов
                                     # (для импорта через /seo/sites/{id}/import)
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

**Публичный рендер (`seo_templates.py`):**
- Полная SEO-обвязка: `<title>`, meta description, canonical, Open Graph, Twitter Card, Schema.org JSON-LD (`Organization`, `WebSite`, `LocalBusiness` + `HealthAndBeautyBusiness`, `Article`)
- `sitemap.xml` и `robots.txt` генерируются автоматически на каждый сайт
- Inline CSS с подстановкой палитры через `__PRIMARY__` / `__SECONDARY__` (через `.replace()`, НЕ `%`-formatting — в CSS есть `100%` который ломает % syntax)
- Google Fonts (Inter + Playfair Display) с `font-display: swap`
- Mobile-responsive
- Контакт-кнопки: `tel:`, `mailto:`, `t.me/`, `wa.me/`, `sms:` + inline SVG-иконки

**Маршруты публичные** (на SEO-домене):
- `/` — главная (locations grid + recent articles)
- `/blog` — индекс статей
- `/blog/category/<slug>` — статьи рубрики
- `/blog/<slug>` — статья
- `/<slug>` — локация (приоритет) или статическая страница
- `/sitemap.xml` / `/robots.txt`

**Админка** (на CRM-домене, под `/seo/*`):
- `/seo` — список сайтов
- `/seo/sites/{id}` — настройки (брендинг, домен, палитра, GA, status)
- `/seo/sites/{id}/locations` — города (CRUD), на каждой — адрес, координаты, FAQ JSON, hours JSON, контакты
- `/seo/sites/{id}/pages` — статические (about, contact, privacy, terms, services)
- `/seo/sites/{id}/articles` — блог (категория, автор, content_html, pillar-флаг, view counter)
- `/seo/sites/{id}/categories` / `/authors` / `/redirects`
- `/seo/sites/{id}/import` — **bulk-import JSON** (целая `site_settings` + категории + локации + страницы + статьи одним кликом). По умолчанию пропускает существующие slug; галка перезаписывает.
- `/seo/preview/{id}/{path:path}` — admin-preview, **обходит фильтр `status='live'/published'`** чтобы можно было смотреть черновики. Внутри переписывает root-relative ссылки в preview-prefix чтобы навигация осталась внутри `/seo/preview/{id}/...`. **Важно:** при rewrite не переносить старые headers — `Content-Length` стухнет → пустая страница. Использовать `HTMLResponse(content=html, status_code=...)` без `headers=...`.

**Доступ к админке:** только role=`admin`. Manager → 403.

**Sidebar:** пункт «SEO → Сайты» добавлен в обе версии (React `NavSidebar.jsx` для TG-чатов и HTML `nav_html()` для всех остальных страниц).

**Стартовый контент:** `docs/seo-content/relaxtouch-bootstrap.json` — 1 site_settings + 4 categories + 1 author + 4 static pages + 15 location pages для `relaxtouchtoday.com`. Импортируется через `/seo/sites/{id}/import`.

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
- `seo_sites` — сайты (домен, язык, брендинг, status)
- `seo_locations` — города на сайте (адрес, координаты, FAQ, hours)
- `seo_location_contacts` — телефоны / TG / WA / email на локацию (тип, value, is_primary)
- `seo_pages` — статические страницы (about, contact, privacy, terms, services)
- `seo_articles` — блог (slug → category, author, content_html, view_count)
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
