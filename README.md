# TG Tracker — инструкция по запуску

## Структура файлов
```
main.py          — основное приложение (бот + веб-сервер)
database.py      — база данных SQLite
meta_capi.py     — отправка событий в Meta
requirements.txt — зависимости
Procfile         — команда запуска для Railway
```

## Деплой на Railway

### 1. Создай репозиторий на GitHub
- Зайди на github.com → New repository → назови `tg-tracker` → Create
- Загрузи все файлы проекта

### 2. Создай проект на Railway
- railway.app → New Project → Deploy from GitHub repo → выбери `tg-tracker`

### 3. Добавь переменные окружения
В Railway: твой проект → Variables → добавь каждую:

| Переменная          | Значение                        |
|---------------------|---------------------------------|
| BOT_TOKEN           | твой токен от @BotFather        |
| CHANNEL_ID          | -1003835844880                  |
| PIXEL_ID            | 876260075247607                 |
| META_TOKEN          | твой CAPI токен из Meta         |
| DASHBOARD_PASSWORD  | любой пароль для входа          |

### 4. Деплой запустится автоматически

### 5. Открой дашборд
- В Railway: Settings → Networking → Generate Domain
- Зайди на: https://твой-адрес.railway.app/?key=твой_пароль

## Как использовать

1. Открой дашборд → введи название кампании (например `FB_Broad_March`)
2. Нажми "Создать ссылку" — получишь Telegram invite link
3. Вставь этот invite link в рекламу в Meta Ads как ссылку назначения
4. Люди кликают рекламу → переходят в канал по этой ссылке → подписываются
5. Бот фиксирует подписку → событие улетает в Meta CAPI
6. В Ads Manager видишь реальную стоимость подписчика!

## Тестирование Meta CAPI
В файле meta_capi.py раскомментируй строку:
`# "test_event_code": "TEST12345",`
Замени TEST12345 на код из Meta Events Manager → Test Events
