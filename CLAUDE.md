# TGTracker CRM — CLAUDE.md

## Что это за проект

CRM-система для отслеживания лидов и общения с клиентами через Telegram и WhatsApp.
Основные задачи: трекинг вступлений в TG-каналы → Meta/TikTok Conversions API, управление перепиской в TG-аккаунте и WA, аналитика по лидам и сотрудникам.

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
main.py                  # FastAPI app, lifespan, auth, лендинги, роутинг
database.py              # Класс Database — все SQL-запросы, in-memory TTL кэш
bot_manager.py           # BOT1 (Трекер) + BOT2 (Уведомления) — aiogram
meta_capi.py             # Meta Conversions API — send_subscribe_event()
tiktok_capi.py           # TikTok CAPI
cloudinary_upload.py     # Загрузка медиа на Cloudinary
client_templates.py      # HTML-шаблоны клиентских страниц
landing_templates.py     # HTML-шаблоны лендингов (несколько вариантов)

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

frontend/
  src/
    components/NavSidebar.jsx   # Боковое меню
    ...                         # Остальные React-компоненты
  dist/                  # Скомпилированный бандл — КОММИТИТСЯ В GIT
  package.json
  vite.config.js
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
- Несколько шаблонов в `landing_templates.py`
- Поддержка кастомных доменов через `CustomDomainMiddleware`
- URL: `/l/{slug}` или кастомный домен → корень

### Meta CAPI matching
Для атрибуции нужны (в порядке важности):
1. `fbclid` → `fbc` (из URL лендинга)
2. `_fbp` cookie (устанавливается Meta Pixel)
3. `external_id` = sha256(telegram_user_id)

---

## Права доступа (tab IDs)

```
channels, campaigns, landings           # Клиенты
tg_account_chat, wa_chat                # Чаты
staff, staff_bonuses, scripts           # Сотрудники
landings_staff, analytics_staff         # HR
analytics_clients                       # Аналитика клиентов
```

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
