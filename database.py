import os
import logging
import hashlib
import secrets
import time
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

log = logging.getLogger(__name__)
DATABASE_URL = os.getenv("DATABASE_URL", "")


# ── Простой in-memory TTL кэш ─────────────────────────────────────────────────
class _TTLCache:
    """Потокобезопасный TTL кэш. key → (value, expires_at)"""
    def __init__(self):
        self._store: dict = {}

    def get(self, key: str):
        entry = self._store.get(key)
        if entry and time.monotonic() < entry[1]:
            return entry[0]
        self._store.pop(key, None)
        return None

    def set(self, key: str, value, ttl: float = 4.0):
        self._store[key] = (value, time.monotonic() + ttl)

    def invalidate(self, *keys: str):
        for k in keys:
            self._store.pop(k, None)

    def invalidate_prefix(self, prefix: str):
        to_del = [k for k in self._store if k.startswith(prefix)]
        for k in to_del:
            self._store.pop(k, None)

_cache = _TTLCache()


class Database:
    def __init__(self):
        self._init_db()

    def _conn(self):
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

    def _init_db(self):
        with self._conn() as conn:
            with conn.cursor() as cur:
                # ── Базовые таблицы ───────────────────────────────────────────
                cur.execute("""
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                    password TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'manager', created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS channels (
                    id SERIAL PRIMARY KEY, name TEXT NOT NULL,
                    channel_id TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);

                -- Кампания = группа каналов + лендинг
                CREATE TABLE IF NOT EXISTS campaigns (
                    id SERIAL PRIMARY KEY,
                    name        TEXT NOT NULL UNIQUE,
                    slug        TEXT NOT NULL UNIQUE,
                    description TEXT DEFAULT '',
                    created_at  TEXT NOT NULL
                );

                -- Каналы внутри кампании (каждый со своей invite-ссылкой)
                CREATE TABLE IF NOT EXISTS campaign_channels (
                    id          SERIAL PRIMARY KEY,
                    campaign_id INTEGER NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
                    channel_id  TEXT NOT NULL,
                    channel_name TEXT,
                    invite_link TEXT NOT NULL,
                    position    INTEGER DEFAULT 0,
                    created_at  TEXT NOT NULL
                );

                -- Подписки (join_id → click_id → fbclid/fbp)
                CREATE TABLE IF NOT EXISTS joins (
                    id            SERIAL PRIMARY KEY,
                    user_id       BIGINT NOT NULL,
                    channel_id    TEXT,
                    invite_link   TEXT,
                    campaign_name TEXT NOT NULL DEFAULT 'organic',
                    click_id      TEXT,
                    joined_at     TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS click_tracking (
                    id           SERIAL PRIMARY KEY,
                    click_id     TEXT NOT NULL UNIQUE,
                    fbclid       TEXT,
                    fbp          TEXT,
                    utm_source   TEXT,
                    utm_medium   TEXT,
                    utm_campaign TEXT,
                    utm_content  TEXT,
                    utm_term     TEXT,
                    referrer     TEXT,
                    target_type  TEXT DEFAULT 'channel',
                    target_id    TEXT,
                    user_agent   TEXT,
                    ip_address   TEXT,
                    created_at   TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS utm_tracking (
                    id              SERIAL PRIMARY KEY,
                    conversation_id INTEGER,
                    join_id         INTEGER,
                    click_id        TEXT,
                    fbclid          TEXT,
                    fbp             TEXT,
                    utm_source      TEXT,
                    utm_medium      TEXT,
                    utm_campaign    TEXT,
                    utm_content     TEXT,
                    utm_term        TEXT,
                    referrer        TEXT,
                    created_at      TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversations (
                    id              SERIAL PRIMARY KEY,
                    tg_chat_id      TEXT NOT NULL UNIQUE,
                    visitor_name    TEXT NOT NULL DEFAULT 'Неизвестный',
                    username        TEXT,
                    status          TEXT DEFAULT 'open',
                    unread_count    INTEGER DEFAULT 0,
                    last_message    TEXT,
                    last_message_at TEXT,
                    fb_event_sent   TEXT,
                    utm_source      TEXT,
                    utm_campaign    TEXT,
                    fbclid          TEXT,
                    created_at      TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id              SERIAL PRIMARY KEY,
                    conversation_id INTEGER NOT NULL,
                    tg_chat_id      TEXT NOT NULL,
                    sender_type     TEXT NOT NULL,
                    content         TEXT,
                    media_url       TEXT,
                    media_type      TEXT,
                    tg_message_id   INTEGER,
                    read_by_manager INTEGER DEFAULT 0,
                    created_at      TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS staff (
                    id              SERIAL PRIMARY KEY,
                    conversation_id INTEGER,
                    tg_chat_id      TEXT UNIQUE,
                    name            TEXT,
                    username        TEXT,
                    phone           TEXT,
                    email           TEXT,
                    position        TEXT,
                    status          TEXT DEFAULT 'new',
                    notes           TEXT,
                    tags            TEXT DEFAULT '',
                    fb_event_sent   TEXT,
                    created_at      TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS landings (
                    id         SERIAL PRIMARY KEY,
                    name       TEXT NOT NULL,
                    type       TEXT NOT NULL DEFAULT 'client',
                    slug       TEXT NOT NULL UNIQUE,
                    content    TEXT NOT NULL DEFAULT '{}',
                    active     INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS landing_contacts (
                    id         SERIAL PRIMARY KEY,
                    landing_id INTEGER NOT NULL,
                    type       TEXT NOT NULL,
                    label      TEXT NOT NULL,
                    url        TEXT NOT NULL,
                    position   INTEGER DEFAULT 0
                );
                -- Добавляем city если ещё нет (миграция)
                DO $$ BEGIN
                    ALTER TABLE landing_contacts ADD COLUMN IF NOT EXISTS city TEXT DEFAULT '';
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$;
                CREATE TABLE IF NOT EXISTS wa_conversations (
                    id              SERIAL PRIMARY KEY,
                    wa_chat_id      TEXT NOT NULL UNIQUE,
                    wa_number       TEXT NOT NULL,
                    visitor_name    TEXT NOT NULL DEFAULT 'Неизвестный',
                    status          TEXT DEFAULT 'open',
                    unread_count    INTEGER DEFAULT 0,
                    last_message    TEXT,
                    last_message_at TEXT,
                    fb_event_sent   TEXT,
                    utm_source      TEXT,
                    utm_campaign    TEXT,
                    fbclid          TEXT,
                    created_at      TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS wa_messages (
                    id              SERIAL PRIMARY KEY,
                    conversation_id INTEGER NOT NULL,
                    wa_chat_id      TEXT NOT NULL,
                    sender_type     TEXT NOT NULL,
                    content         TEXT,
                    media_url       TEXT,
                    media_type      TEXT,
                    read_by_manager INTEGER DEFAULT 0,
                    created_at      TEXT NOT NULL
                );
                """)

                # ── Миграции для уже существующих БД ─────────────────────────
                # Меняем структуру старой таблицы campaigns (убираем NOT NULL с channel_id)
                migrations = [
                    "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS slug TEXT",
                    "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS description TEXT DEFAULT ''",
                    "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS landing_id INTEGER DEFAULT NULL",
                    "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS project_id INTEGER DEFAULT NULL",
                    "ALTER TABLE campaigns ALTER COLUMN channel_id DROP NOT NULL",
                    "ALTER TABLE campaigns ALTER COLUMN invite_link DROP NOT NULL",
                    "ALTER TABLE campaign_channels ADD COLUMN IF NOT EXISTS city TEXT DEFAULT ''",
                    "ALTER TABLE campaign_channels ADD COLUMN IF NOT EXISTS phone TEXT DEFAULT ''",
                    "ALTER TABLE campaign_channels ADD COLUMN IF NOT EXISTS address TEXT DEFAULT ''",
                    "ALTER TABLE campaign_channels ADD COLUMN IF NOT EXISTS tg_label TEXT DEFAULT ''",
                    "ALTER TABLE campaign_channels ADD COLUMN IF NOT EXISTS phone_label TEXT DEFAULT ''",
                    "CREATE TABLE IF NOT EXISTS campaign_phones (id SERIAL PRIMARY KEY, campaign_id INTEGER NOT NULL, city TEXT DEFAULT '', phone TEXT DEFAULT '', position INTEGER DEFAULT 0)",
                    "ALTER TABLE wa_conversations ADD COLUMN IF NOT EXISTS utm_source TEXT",
                    "ALTER TABLE wa_conversations ADD COLUMN IF NOT EXISTS utm_campaign TEXT",
                    "ALTER TABLE wa_conversations ADD COLUMN IF NOT EXISTS fbclid TEXT",
                    "ALTER TABLE wa_conversations ADD COLUMN IF NOT EXISTS fb_event_sent TEXT",
                    "ALTER TABLE wa_conversations ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'open'",
                    "ALTER TABLE wa_conversations ADD COLUMN IF NOT EXISTS unread_count INTEGER DEFAULT 0",
                    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS utm_source TEXT",
                    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS utm_campaign TEXT",
                    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS fbclid TEXT",
                    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS fb_event_sent TEXT",
                    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'open'",
                    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS unread_count INTEGER DEFAULT 0",
                    "ALTER TABLE wa_messages ADD COLUMN IF NOT EXISTS media_url TEXT",
                    "ALTER TABLE wa_messages ADD COLUMN IF NOT EXISTS media_type TEXT",
                    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS media_url TEXT",
                    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS media_type TEXT",
                    "ALTER TABLE staff ADD COLUMN IF NOT EXISTS wa_conv_id INTEGER DEFAULT NULL",
                    "ALTER TABLE staff ADD COLUMN IF NOT EXISTS tga_conv_id INTEGER DEFAULT NULL",
                    "ALTER TABLE staff ALTER COLUMN tg_chat_id DROP NOT NULL",
                    # Профиль пользователей TG/WA
                    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS photo_url TEXT",
                    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS phone TEXT",
                    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS bio TEXT",
                    "ALTER TABLE wa_conversations ADD COLUMN IF NOT EXISTS photo_url TEXT",
                    "ALTER TABLE wa_conversations ADD COLUMN IF NOT EXISTS wa_bio TEXT",
                    # Права доступа менеджеров
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS permissions TEXT DEFAULT ''",
                    # Раздельные пиксели клиенты/сотрудники
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name TEXT DEFAULT ''",
                    # Staff clicks — UTM трекинг для HR лендингов
                    """CREATE TABLE IF NOT EXISTS staff_clicks (
                        id          SERIAL PRIMARY KEY,
                        ref_id      TEXT NOT NULL UNIQUE,
                        fbclid      TEXT,
                        fbp         TEXT,
                        utm_source  TEXT,
                        utm_medium  TEXT,
                        utm_campaign TEXT,
                        utm_content TEXT,
                        utm_term    TEXT,
                        target_url  TEXT,
                        target_type TEXT DEFAULT 'wa',
                        landing_slug TEXT,
                        used        INTEGER DEFAULT 0,
                        created_at  TEXT NOT NULL
                    )""",
                    # fbp/fbc в conversations/wa_conversations для CAPI matching
                    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS fbp TEXT",
                    "ALTER TABLE wa_conversations ADD COLUMN IF NOT EXISTS fbp TEXT",
                    "ALTER TABLE staff_clicks ADD COLUMN IF NOT EXISTS fbc TEXT",
                    "ALTER TABLE staff_clicks ADD COLUMN IF NOT EXISTS ttclid TEXT",
                    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS tt_test_event_code TEXT DEFAULT ''",
                    "ALTER TABLE tg_account_conversations ADD COLUMN IF NOT EXISTS ttclid TEXT DEFAULT ''",
                    "ALTER TABLE tg_account_conversations ADD COLUMN IF NOT EXISTS ttp TEXT DEFAULT ''",
                    "ALTER TABLE wa_conversations ADD COLUMN IF NOT EXISTS ttclid TEXT DEFAULT ''",
                    "ALTER TABLE wa_conversations ADD COLUMN IF NOT EXISTS ttp TEXT DEFAULT ''",
                    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS tt_token TEXT DEFAULT ''",
                    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS traffic_source TEXT DEFAULT ''",
                    "ALTER TABLE landings ADD COLUMN IF NOT EXISTS traffic_source TEXT DEFAULT ''",
                    "ALTER TABLE staff_clicks ADD COLUMN IF NOT EXISTS ttp TEXT",
                "ALTER TABLE landings ADD COLUMN IF NOT EXISTS fb_event TEXT DEFAULT ''",
                    "ALTER TABLE staff_clicks ADD COLUMN IF NOT EXISTS tg_user_id TEXT",
                    "ALTER TABLE wa_conversations ADD COLUMN IF NOT EXISTS fbc TEXT",
                    "ALTER TABLE tg_account_conversations ADD COLUMN IF NOT EXISTS fbc TEXT",
                    "ALTER TABLE wa_conversations ADD COLUMN IF NOT EXISTS utm_medium TEXT",
                    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS utm_medium TEXT",
                    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS utm_content TEXT",
                    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS utm_term TEXT",
                    "ALTER TABLE wa_conversations ADD COLUMN IF NOT EXISTS utm_content TEXT",
                    "ALTER TABLE wa_conversations ADD COLUMN IF NOT EXISTS utm_term TEXT",
                    "ALTER TABLE staff ADD COLUMN IF NOT EXISTS photo_url TEXT",
                    "ALTER TABLE staff ADD COLUMN IF NOT EXISTS manager_name TEXT DEFAULT ''",
                    "ALTER TABLE staff ADD COLUMN IF NOT EXISTS city TEXT DEFAULT ''",
                    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS sender_name TEXT DEFAULT ''",
                    "ALTER TABLE wa_messages ADD COLUMN IF NOT EXISTS sender_name TEXT DEFAULT ''",
                    "ALTER TABLE landings ADD COLUMN IF NOT EXISTS custom_domain TEXT DEFAULT ''",
                    "ALTER TABLE landings ADD COLUMN IF NOT EXISTS project_id INTEGER DEFAULT NULL",
                    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS project_id INTEGER DEFAULT NULL",
                    "ALTER TABLE wa_conversations ADD COLUMN IF NOT EXISTS project_id INTEGER DEFAULT NULL",
                    "ALTER TABLE tg_account_conversations ADD COLUMN IF NOT EXISTS project_id INTEGER DEFAULT NULL",
                    "ALTER TABLE projects ADD COLUMN IF NOT EXISTS test_event_code TEXT DEFAULT ''",
                ]
                # ── Индексы для быстрой выборки ─────────────────────────────
                _indexes = [
                    "CREATE INDEX IF NOT EXISTS idx_tga_conv_status ON tg_account_conversations (status, last_message_at DESC NULLS LAST)",
                    "CREATE INDEX IF NOT EXISTS idx_tga_conv_user ON tg_account_conversations (tg_user_id)",
                    "CREATE INDEX IF NOT EXISTS idx_tga_conv_utm ON tg_account_conversations (utm_campaign)",
                    "CREATE INDEX IF NOT EXISTS idx_tga_msg_conv ON tg_account_messages (conversation_id, created_at ASC)",
                    "ALTER TABLE tg_account_messages ADD COLUMN IF NOT EXISTS is_read BOOLEAN DEFAULT FALSE",
                    "ALTER TABLE tg_account_messages ADD COLUMN IF NOT EXISTS tg_msg_id BIGINT DEFAULT NULL",
                    "CREATE INDEX IF NOT EXISTS idx_wa_conv_status ON wa_conversations (status, last_message_at DESC NULLS LAST)",
                    "CREATE INDEX IF NOT EXISTS idx_wa_conv_chat ON wa_conversations (wa_chat_id)",
                    "CREATE INDEX IF NOT EXISTS idx_wa_conv_utm ON wa_conversations (utm_campaign)",
                    "CREATE INDEX IF NOT EXISTS idx_wa_msg_conv ON wa_messages (conversation_id, created_at ASC)",
                    "CREATE INDEX IF NOT EXISTS idx_staff_status ON staff (status, created_at DESC)",
                    "CREATE INDEX IF NOT EXISTS idx_staff_clicks_used ON staff_clicks (used, created_at DESC)",
                    "CREATE INDEX IF NOT EXISTS idx_staff_clicks_ref ON staff_clicks (ref_id)",
                    "CREATE INDEX IF NOT EXISTS idx_landings_slug ON landings (slug)",
                    "CREATE INDEX IF NOT EXISTS idx_conv_status ON conversations (status, last_message_at DESC NULLS LAST)",
                    "CREATE INDEX IF NOT EXISTS idx_utm_conv ON utm_tracking (conversation_id)",
                    "CREATE INDEX IF NOT EXISTS idx_conv_tags ON conv_tags (conv_type, conv_id)",
                    "CREATE INDEX IF NOT EXISTS idx_campaigns_slug ON campaigns (slug)",
                ]
                for _idx in _indexes:
                    try: cur.execute(_idx)
                    except Exception: pass
                # Таблица галереи фото сотрудников
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS staff_gallery (
                        id         SERIAL PRIMARY KEY,
                        staff_id   INTEGER NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
                        photo_url  TEXT NOT NULL,
                        caption    TEXT DEFAULT '',
                        created_at TEXT NOT NULL
                    )
                """)
                # Теги для чатов
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS tags (
                        id         SERIAL PRIMARY KEY,
                        name       TEXT NOT NULL UNIQUE,
                        color      TEXT NOT NULL DEFAULT '#6366f1',
                        created_at TEXT NOT NULL
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS conv_tags (
                        id        SERIAL PRIMARY KEY,
                        tag_id    INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
                        conv_type TEXT NOT NULL,
                        conv_id   INTEGER NOT NULL,
                        UNIQUE(tag_id, conv_type, conv_id)
                    )
                """)

                for m in migrations:
                    try:
                        cur.execute(m)
                    except Exception as ex:
                        log.warning(f"Migration skipped: {ex}")
                # Проекты — группируют пиксели и utm кампании
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS projects (
                        id                SERIAL PRIMARY KEY,
                        name              TEXT NOT NULL UNIQUE,
                        fb_pixel_id       TEXT DEFAULT '',
                        fb_token          TEXT DEFAULT '',
                        tt_pixel_id       TEXT DEFAULT '',
                        tt_token          TEXT DEFAULT '',
                        utm_campaigns     TEXT DEFAULT '',
                        test_event_code   TEXT DEFAULT '',
                        created_at        TEXT NOT NULL
                    )
                """)
                # Привязка лендинга к проекту

                # Заполняем slug для старых кампаний где он NULL
                cur.execute("UPDATE campaigns SET slug = LOWER(REPLACE(name, ' ', '-')) || '-' || id WHERE slug IS NULL OR slug = ''")

                # Скрипты общения — шаблонные сообщения по категориям для каждого проекта
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS scripts (
                        id         SERIAL PRIMARY KEY,
                        project_id INTEGER NOT NULL,
                        category   TEXT NOT NULL DEFAULT 'Общее',
                        title      TEXT NOT NULL,
                        body       TEXT NOT NULL DEFAULT '',
                        sort_order INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS staff_notes (
                        id           SERIAL PRIMARY KEY,
                        staff_id     INTEGER NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
                        manager_name TEXT NOT NULL DEFAULT '',
                        type         TEXT NOT NULL DEFAULT 'note',
                        text         TEXT NOT NULL DEFAULT '',
                        remind_at    TEXT DEFAULT NULL,
                        created_at   TEXT NOT NULL
                    )
                """)
                try:
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_staff_notes_staff_id ON staff_notes(staff_id)")
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_staff_notes_remind_at ON staff_notes(remind_at) WHERE remind_at IS NOT NULL")
                except Exception:
                    pass

            conn.commit()

        # Default admin
        try:
            with self._conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) as c FROM users")
                    if cur.fetchone()["c"] == 0:
                        pwd = hashlib.sha256("admin123".encode()).hexdigest()
                        cur.execute("INSERT INTO users (username,password,role,created_at) VALUES (%s,%s,%s,%s)",
                                    ("admin", pwd, "admin", datetime.utcnow().isoformat()))
                conn.commit()
        except Exception as e:
            log.error(f"Admin init error: {e}")

    # ── Settings ──────────────────────────────────────────────────────────────
    def get_settings_bulk(self, keys: list) -> dict:
        """Получить несколько настроек одним запросом с кэшированием 60 сек."""
        import time as _time
        now = _time.time()
        # Инициализируем кэш если нет
        if not hasattr(self, '_settings_cache'):
            self._settings_cache = {}
            self._settings_cache_ts = 0
        # Обновляем кэш раз в 60 секунд
        if now - self._settings_cache_ts > 60:
            with self._conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT key, value FROM settings")
                    self._settings_cache = {r["key"]: r["value"] for r in cur.fetchall()}
                    self._settings_cache_ts = now
        # Возвращаем нужные ключи из кэша
        return {k: self._settings_cache.get(k, "") for k in keys}

    def get_setting(self, key, default=""):
        """Получить настройку с кэшированием."""
        result = self.get_settings_bulk([key])
        val = result.get(key, "")
        return val if val != "" else default
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM settings WHERE key=%s", (key,))
                r = cur.fetchone(); return r["value"] if r else default

    def set_setting(self, key, value):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO settings (key,value) VALUES (%s,%s) ON CONFLICT (key) DO UPDATE SET value=%s", (key,value,value))
            conn.commit()

    # ── Users ─────────────────────────────────────────────────────────────────
    def get_users(self):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id,username,role,created_at,permissions,display_name FROM users ORDER BY created_at")
                return [dict(r) for r in cur.fetchall()]

    def get_user_by_id(self, user_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id,username,role,created_at,permissions,display_name FROM users WHERE id=%s", (user_id,))
                r = cur.fetchone(); return dict(r) if r else None

    def create_user(self, username, password, role="manager", permissions="", display_name=""):
        pwd = hashlib.sha256(password.encode()).hexdigest()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO users (username,password,role,created_at,permissions,display_name) VALUES (%s,%s,%s,%s,%s,%s)",
                            (username, pwd, role, datetime.utcnow().isoformat(), permissions, display_name))
            conn.commit()

    def update_user(self, user_id, username, role, permissions, new_password=None, display_name=None):
        with self._conn() as conn:
            with conn.cursor() as cur:
                if new_password:
                    pwd = hashlib.sha256(new_password.encode()).hexdigest()
                    cur.execute("UPDATE users SET username=%s,role=%s,permissions=%s,password=%s,display_name=%s WHERE id=%s",
                                (username, role, permissions, pwd, display_name or "", user_id))
                else:
                    cur.execute("UPDATE users SET username=%s,role=%s,permissions=%s,display_name=%s WHERE id=%s",
                                (username, role, permissions, display_name or "", user_id))
            conn.commit()

    def delete_user(self, user_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
            conn.commit()

    def verify_user(self, username, password):
        pwd = hashlib.sha256(password.encode()).hexdigest()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users WHERE username=%s AND password=%s", (username, pwd))
                r = cur.fetchone(); return dict(r) if r else None

    def update_conv_profile(self, conv_id, photo_url=None, phone=None, bio=None):
        with self._conn() as conn:
            with conn.cursor() as cur:
                if photo_url is not None:
                    cur.execute("UPDATE conversations SET photo_url=%s WHERE id=%s", (photo_url, conv_id))
                if phone is not None:
                    cur.execute("UPDATE conversations SET phone=%s WHERE id=%s", (phone, conv_id))
                if bio is not None:
                    cur.execute("UPDATE conversations SET bio=%s WHERE id=%s", (bio, conv_id))
            conn.commit()

    def update_wa_conv_profile(self, conv_id, photo_url=None, bio=None):
        with self._conn() as conn:
            with conn.cursor() as cur:
                if photo_url is not None:
                    cur.execute("UPDATE wa_conversations SET photo_url=%s WHERE id=%s", (photo_url, conv_id))
                if bio is not None:
                    cur.execute("UPDATE wa_conversations SET wa_bio=%s WHERE id=%s", (bio, conv_id))
            conn.commit()

    # ── Channels ──────────────────────────────────────────────────────────────
    def add_channel(self, name, channel_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO channels (name,channel_id,created_at) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                            (name, channel_id, datetime.utcnow().isoformat()))
            conn.commit()

    def get_channels(self):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT c.*, COUNT(j.id) as total_joins FROM channels c
                    LEFT JOIN joins j ON j.channel_id=c.channel_id
                    GROUP BY c.id ORDER BY c.created_at DESC""")
                return [dict(r) for r in cur.fetchall()]

    def delete_channel(self, channel_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM channels WHERE channel_id=%s", (channel_id,))
            conn.commit()

    def get_channel_ids(self):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT channel_id FROM channels")
                return [r["channel_id"] for r in cur.fetchall()]

    # ── Campaigns (новая модель: 1 кампания = много каналов) ──────────────────
    def create_campaign(self, name: str, slug: str, description: str = "", landing_id: int = None) -> int:
        import re
        clean_slug = re.sub(r'[^a-z0-9-]', '-', slug.lower().strip())
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO campaigns (name,slug,description,landing_id,created_at) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                            (name.strip(), clean_slug, description, landing_id, datetime.utcnow().isoformat()))
                r = cur.fetchone()
            conn.commit()
            return r["id"]

    def update_campaign_landing(self, campaign_id: int, landing_id: int):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE campaigns SET landing_id=%s WHERE id=%s", (landing_id, campaign_id))
            conn.commit()

    def set_campaign_project(self, campaign_id: int, project_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE campaigns SET project_id=%s WHERE id=%s",
                            (project_id, campaign_id))
            conn.commit()

    def get_campaign_project(self, campaign_id: int):
        """Возвращает проект привязанный к кампании или None."""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT p.* FROM projects p "
                    "JOIN campaigns c ON c.project_id = p.id "
                    "WHERE c.id=%s", (campaign_id,)
                )
                r = cur.fetchone()
                return dict(r) if r else None

    def get_campaigns(self, channel_id=None):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT c.*,
                        COUNT(DISTINCT cc.id) AS channel_count,
                        COUNT(DISTINCT j.id)  AS total_joins
                    FROM campaigns c
                    LEFT JOIN campaign_channels cc ON cc.campaign_id = c.id
                    LEFT JOIN joins j ON j.campaign_name = c.name
                    GROUP BY c.id ORDER BY c.created_at DESC
                """)
                return [dict(r) for r in cur.fetchall()]

    def get_campaign(self, campaign_id: int):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM campaigns WHERE id=%s", (campaign_id,))
                r = cur.fetchone()
                return dict(r) if r else None

    def get_campaign_by_slug(self, slug: str):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM campaigns WHERE slug=%s", (slug,))
                r = cur.fetchone()
                return dict(r) if r else None

    def delete_campaign(self, campaign_id: int):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM campaign_channels WHERE campaign_id=%s", (campaign_id,))
                cur.execute("DELETE FROM campaigns WHERE id=%s", (campaign_id,))
            conn.commit()

    # ── Campaign Channels ──────────────────────────────────────────────────────
    def add_campaign_channel(self, campaign_id: int, channel_id: str, channel_name: str, invite_link: str):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COALESCE(MAX(position),0)+1 as p FROM campaign_channels WHERE campaign_id=%s", (campaign_id,))
                pos = cur.fetchone()["p"]
                cur.execute("""INSERT INTO campaign_channels (campaign_id,channel_id,channel_name,invite_link,position,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s)""",
                    (campaign_id, channel_id, channel_name, invite_link, pos, datetime.utcnow().isoformat()))
            conn.commit()

    def get_campaign_channels(self, campaign_id: int):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT cc.*, 
                    COUNT(j.id) AS joins
                    FROM campaign_channels cc
                    LEFT JOIN joins j ON j.invite_link = cc.invite_link
                    WHERE cc.campaign_id=%s
                    GROUP BY cc.id ORDER BY cc.position""", (campaign_id,))
                return [dict(r) for r in cur.fetchall()]

    def get_campaign_phones(self, campaign_id: int) -> list:
        """Для обратной совместимости — теперь телефоны хранятся в campaign_channels.phone"""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, city, phone FROM campaign_channels WHERE campaign_id=%s AND phone!='' ORDER BY position",
                    (campaign_id,)
                )
                return [dict(r) for r in cur.fetchall()]

    def set_campaign_channel_city(self, cc_id: int, city: str):
        self.set_campaign_channel_location(cc_id, city, "")

    def set_campaign_channel_location(self, cc_id: int, city: str, phone: str,
                                       address: str = "", tg_label: str = "",
                                       phone_label: str = ""):
        """Сохранить город, телефон, адрес и заголовки для канала кампании."""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE campaign_channels SET city=%s, phone=%s, address=%s, "
                    "tg_label=%s, phone_label=%s WHERE id=%s",
                    (city.strip(), phone.strip(), address.strip(),
                     tg_label.strip(), phone_label.strip(), cc_id)
                )
            conn.commit()

    def remove_campaign_channel(self, cc_id: int):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM campaign_channels WHERE id=%s", (cc_id,))
            conn.commit()

    def get_campaign_by_invite_link(self, invite_link: str):
        """Найти кампанию по invite-ссылке одного из её каналов"""
        if not invite_link: return None
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT c.* FROM campaigns c
                    JOIN campaign_channels cc ON cc.campaign_id = c.id
                    WHERE cc.invite_link = %s LIMIT 1""", (invite_link,))
                r = cur.fetchone()
                return dict(r) if r else None

    # ── Старый метод для обратной совместимости ─────────────────────────────
    def save_campaign(self, name, channel_id, invite_link, landing_id=None):
        """Устаревший метод — создаёт кампанию + добавляет один канал"""
        import re
        slug = re.sub(r'[^a-z0-9-]', '-', name.lower()) + "-" + secrets.token_hex(3)
        try:
            camp_id = self.create_campaign(name, slug)
        except Exception:
            # Уже существует — находим
            with self._conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id FROM campaigns WHERE name=%s", (name,))
                    r = cur.fetchone()
                    camp_id = r["id"] if r else None
            if not camp_id: return
        self.add_campaign_channel(camp_id, channel_id, channel_id, invite_link)

    def get_campaign_by_link(self, invite_link):
        return self.get_campaign_by_invite_link(invite_link)

    # ── Joins ─────────────────────────────────────────────────────────────────
    def log_join(self, user_id, channel_id, invite_link, campaign_name, click_id=None):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO joins (user_id,channel_id,invite_link,campaign_name,click_id,joined_at) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                            (user_id,channel_id,invite_link,campaign_name,click_id,datetime.utcnow().isoformat()))
                r = cur.fetchone()
            conn.commit(); return r["id"]

    def get_recent_joins(self, limit=30):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT j.*, c.name as channel_name FROM joins j
                    LEFT JOIN channels c ON c.channel_id=j.channel_id
                    ORDER BY j.joined_at DESC LIMIT %s""", (limit,))
                return [dict(r) for r in cur.fetchall()]

    # ── Click Tracking ─────────────────────────────────────────────────────────
    def save_click(self, fbclid=None, fbp=None, utm_source=None, utm_medium=None,
                   utm_campaign=None, utm_content=None, utm_term=None,
                   referrer=None, target_type="channel", target_id=None,
                   user_agent=None, ip_address=None, click_id=None):
        if not click_id:
            click_id = secrets.token_urlsafe(12)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO click_tracking
                    (click_id,fbclid,fbp,utm_source,utm_medium,utm_campaign,utm_content,utm_term,
                     referrer,target_type,target_id,user_agent,ip_address,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (click_id) DO NOTHING""",
                    (click_id,fbclid,fbp,utm_source,utm_medium,utm_campaign,utm_content,
                     utm_term,referrer,target_type,target_id,user_agent,ip_address,
                     datetime.utcnow().isoformat()))
            conn.commit()
        return click_id

    def get_click(self, click_id):
        if not click_id: return None
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM click_tracking WHERE click_id=%s", (click_id,))
                r = cur.fetchone(); return dict(r) if r else None

    def get_latest_click_by_link(self, invite_link: str, minutes: int = 120):
        """Найти последний клик по invite_link канала — самый точный matching."""
        from datetime import timedelta
        cutoff = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT * FROM click_tracking
                    WHERE target_id = %s AND created_at > %s
                    ORDER BY created_at DESC LIMIT 1""",
                    (invite_link, cutoff))
                r = cur.fetchone()
                return dict(r) if r else None

    def get_latest_click_by_utm(self, utm_campaign: str, minutes: int = 60):
        """Найти последний клик по utm_campaign за последние N минут."""
        from datetime import timedelta
        cutoff = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT * FROM click_tracking
                    WHERE utm_campaign=%s AND created_at > %s
                    ORDER BY created_at DESC LIMIT 1""",
                    (utm_campaign, cutoff))
                r = cur.fetchone()
                return dict(r) if r else None

    # ── Staff Clicks (HR landing UTM tracking) ────────────────────────────────
    def save_staff_click(self, ref_id, target_url, target_type="wa", landing_slug="",
                         fbclid=None, fbp=None, fbc=None, utm_source=None, utm_medium=None,
                         utm_campaign=None, utm_content=None, utm_term=None,
                         ttclid=None, ttp=None):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO staff_clicks
                    (ref_id,target_url,target_type,landing_slug,fbclid,fbp,fbc,
                     utm_source,utm_medium,utm_campaign,utm_content,utm_term,
                     ttclid,ttp,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (ref_id) DO NOTHING""",
                    (ref_id, target_url, target_type, landing_slug, fbclid, fbp, fbc,
                     utm_source, utm_medium, utm_campaign, utm_content, utm_term,
                     ttclid, ttp, datetime.utcnow().isoformat()))
            conn.commit()

    def get_staff_click(self, ref_id):
        if not ref_id: return None
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM staff_clicks WHERE ref_id=%s", (ref_id,))
                r = cur.fetchone(); return dict(r) if r else None

    def get_staff_click_recent(self, landing_slug: str, minutes: int = 30):
        """Ищет последний неиспользованный клик по лендингу за последние N минут"""
        from datetime import timedelta
        cutoff = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT * FROM staff_clicks
                    WHERE landing_slug=%s AND used=0 AND created_at>=%s
                    ORDER BY created_at DESC LIMIT 1""",
                    (landing_slug, cutoff))
                r = cur.fetchone(); return dict(r) if r else None

    def get_staff_click_recent_any(self, minutes: int = 30, target_type: str = None):
        """Ищет последний неиспользованный клик за последние N минут, опционально по типу"""
        from datetime import timedelta
        cutoff = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()
        with self._conn() as conn:
            with conn.cursor() as cur:
                if target_type:
                    cur.execute("""SELECT * FROM staff_clicks
                        WHERE used=0 AND created_at>=%s AND target_type=%s
                        ORDER BY created_at DESC LIMIT 1""",
                        (cutoff, target_type))
                else:
                    cur.execute("""SELECT * FROM staff_clicks
                        WHERE used=0 AND created_at>=%s
                        ORDER BY created_at DESC LIMIT 1""",
                        (cutoff,))
                r = cur.fetchone(); return dict(r) if r else None

    def get_staff_click_by_tg_user(self, tg_user_id: str, minutes: int = 1440):
        """Ищет клик привязанный к конкретному tg_user_id (за последние N минут)"""
        from datetime import timedelta
        cutoff = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT * FROM staff_clicks
                    WHERE tg_user_id=%s AND target_type='telegram' AND created_at>=%s
                    ORDER BY created_at DESC LIMIT 1""",
                    (str(tg_user_id), cutoff))
                r = cur.fetchone(); return dict(r) if r else None

    def bind_staff_click_to_tg_user(self, ref_id: str, tg_user_id: str):
        """Привязываем клик к tg_user_id после первого сообщения"""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE staff_clicks SET tg_user_id=%s WHERE ref_id=%s",
                            (str(tg_user_id), ref_id))
            conn.commit()

    def mark_staff_click_used(self, ref_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE staff_clicks SET used=1 WHERE ref_id=%s", (ref_id,))
            conn.commit()

    def apply_utm_to_wa_conv(self, conv_id, fbclid=None, fbp=None, fbc=None, utm_source=None,
                              utm_medium=None, utm_campaign=None, utm_content=None, utm_term=None,
                              ttclid=None, ttp=None):
        """Применяет UTM к существующему WA диалогу (если ещё не заполнен)"""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE wa_conversations
                    SET fbclid=%s, fbp=%s, fbc=%s, utm_source=%s, utm_medium=%s,
                        utm_campaign=%s, utm_content=%s, utm_term=%s
                    WHERE id=%s AND (utm_source IS NULL OR utm_source='')""",
                    (fbclid, fbp, fbc, utm_source, utm_medium, utm_campaign,
                     utm_content, utm_term, conv_id))
                if ttclid or ttp:
                    cur.execute("UPDATE wa_conversations SET ttclid=%s, ttp=%s WHERE id=%s",
                                (ttclid or '', ttp or '', conv_id))
            conn.commit()

    def apply_utm_to_tg_conv(self, conv_id, fbclid=None, fbp=None, fbc=None, utm_source=None,
                              utm_medium=None, utm_campaign=None, utm_content=None, utm_term=None,
                              ttclid=None, ttp=None):
        """Применяет UTM к существующему TG аккаунт диалогу"""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE tg_account_conversations
                    SET fbclid=%s, fbp=%s, fbc=%s, utm_source=%s, utm_medium=%s,
                        utm_campaign=%s, utm_content=%s, utm_term=%s
                    WHERE id=%s AND (utm_source IS NULL OR utm_source='')""",
                    (fbclid, fbp, fbc, utm_source, utm_medium, utm_campaign,
                     utm_content, utm_term, conv_id))
                if ttclid or ttp:
                    cur.execute("UPDATE tg_account_conversations SET ttclid=%s, ttp=%s WHERE id=%s",
                                (ttclid or '', ttp or '', conv_id))
            conn.commit()

    def save_utm(self, click_data, conversation_id=None, join_id=None):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO utm_tracking
                    (conversation_id,join_id,click_id,fbclid,fbp,utm_source,utm_medium,
                     utm_campaign,utm_content,utm_term,referrer,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (conversation_id,join_id,click_data.get("click_id"),click_data.get("fbclid"),
                     click_data.get("fbp"),click_data.get("utm_source"),click_data.get("utm_medium"),
                     click_data.get("utm_campaign"),click_data.get("utm_content"),
                     click_data.get("utm_term"),click_data.get("referrer"),
                     datetime.utcnow().isoformat()))
            conn.commit()

    def get_utm_by_conv(self, conversation_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM utm_tracking WHERE conversation_id=%s ORDER BY id DESC LIMIT 1", (conversation_id,))
                r = cur.fetchone(); return dict(r) if r else None

    # ── Conversations (TG) ────────────────────────────────────────────────────
    def get_or_create_conversation(self, tg_chat_id, visitor_name, username,
                                   utm_source=None, utm_campaign=None, fbclid=None):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM conversations WHERE tg_chat_id=%s", (tg_chat_id,))
                r = cur.fetchone()
                if r:
                    # Обновляем имя и username при каждом заходе (могли измениться)
                    if visitor_name and visitor_name != str(tg_chat_id):
                        cur.execute("""UPDATE conversations
                            SET visitor_name=%s, username=%s WHERE tg_chat_id=%s""",
                            (visitor_name, username, tg_chat_id))
                        conn.commit()
                        cur.execute("SELECT * FROM conversations WHERE tg_chat_id=%s", (tg_chat_id,))
                        r = cur.fetchone()
                    return dict(r)
                cur.execute("""INSERT INTO conversations
                    (tg_chat_id,visitor_name,username,utm_source,utm_campaign,fbclid,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                    (tg_chat_id,visitor_name,username,utm_source,utm_campaign,fbclid,
                     datetime.utcnow().isoformat()))
                r = cur.fetchone()
            conn.commit(); return dict(r)

    def get_conversations(self, status=None):
        with self._conn() as conn:
            with conn.cursor() as cur:
                if status:
                    cur.execute("SELECT * FROM conversations WHERE status=%s ORDER BY COALESCE(last_message_at,created_at) DESC", (status,))
                else:
                    cur.execute("SELECT * FROM conversations ORDER BY COALESCE(last_message_at,created_at) DESC")
                return [dict(r) for r in cur.fetchall()]

    def delete_conversation(self, conv_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM messages WHERE conversation_id=%s", (conv_id,))
                cur.execute("DELETE FROM utm_tracking WHERE conversation_id=%s", (conv_id,))
                cur.execute("DELETE FROM staff WHERE conversation_id=%s", (conv_id,))
                cur.execute("DELETE FROM conversations WHERE id=%s", (conv_id,))
            conn.commit()

    def get_conversation(self, conv_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM conversations WHERE id=%s", (conv_id,))
                r = cur.fetchone(); return dict(r) if r else None

    def update_conversation_last_message(self, tg_chat_id, text, increment_unread=True):
        with self._conn() as conn:
            with conn.cursor() as cur:
                if increment_unread:
                    cur.execute("UPDATE conversations SET last_message=%s,last_message_at=%s,unread_count=unread_count+1 WHERE tg_chat_id=%s",
                                (text[:100],datetime.utcnow().isoformat(),tg_chat_id))
                else:
                    cur.execute("UPDATE conversations SET last_message=%s,last_message_at=%s WHERE tg_chat_id=%s",
                                (text[:100],datetime.utcnow().isoformat(),tg_chat_id))
            conn.commit()

    def mark_conversation_read(self, conv_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE conversations SET unread_count=0 WHERE id=%s", (conv_id,))
                cur.execute("UPDATE messages SET read_by_manager=1 WHERE conversation_id=%s AND sender_type='visitor'", (conv_id,))
            conn.commit()

    def close_conversation(self, conv_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE conversations SET status='closed' WHERE id=%s", (conv_id,))
            conn.commit()

    def reopen_conversation(self, conv_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE conversations SET status='open' WHERE id=%s", (conv_id,))
            conn.commit()

    def set_conv_fb_event(self, conv_id, event):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE conversations SET fb_event_sent=%s WHERE id=%s", (event, conv_id))
            conn.commit()

    # ── Messages (TG) ─────────────────────────────────────────────────────────
    def save_message(self, conversation_id, tg_chat_id, sender_type, content,
                     tg_message_id=None, media_url=None, media_type=None, sender_name=None):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO messages
                    (conversation_id,tg_chat_id,sender_type,content,tg_message_id,media_url,media_type,created_at,sender_name)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (conversation_id,tg_chat_id,sender_type,content,tg_message_id,
                     media_url,media_type,datetime.utcnow().isoformat(),sender_name))
            conn.commit()

    def get_messages(self, conversation_id, limit=100):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM messages WHERE conversation_id=%s ORDER BY created_at ASC LIMIT %s",
                            (conversation_id, limit))
                return [dict(r) for r in cur.fetchall()]

    def get_new_messages(self, conversation_id, after_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM messages WHERE conversation_id=%s AND id>%s ORDER BY created_at ASC",
                            (conversation_id, after_id))
                return [dict(r) for r in cur.fetchall()]

    # ── Staff ─────────────────────────────────────────────────────────────────
    def get_or_create_staff(self, tg_chat_id, name, username, conv_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM staff WHERE tg_chat_id=%s", (tg_chat_id,))
                r = cur.fetchone()
                if r: return dict(r)
                cur.execute("INSERT INTO staff (conversation_id,tg_chat_id,name,username,created_at) VALUES (%s,%s,%s,%s,%s) RETURNING *",
                            (conv_id,tg_chat_id,name,username,datetime.utcnow().isoformat()))
                r = cur.fetchone()
            conn.commit(); return dict(r)

    def get_staff(self, status=None, sort="newest", search=""):
        with self._conn() as conn:
            with conn.cursor() as cur:
                conditions = []
                params = []
                if status:
                    conditions.append("status=%s")
                    params.append(status)
                if search:
                    conditions.append("(LOWER(name) LIKE %s OR LOWER(username) LIKE %s OR LOWER(phone) LIKE %s OR LOWER(email) LIKE %s)")
                    q = f"%{search.lower()}%"
                    params.extend([q, q, q, q])
                where = "WHERE " + " AND ".join(conditions) if conditions else ""
                order = {
                    "newest": "ORDER BY created_at DESC",
                    "oldest": "ORDER BY created_at ASC",
                    "name":   "ORDER BY name ASC",
                    "status": "ORDER BY status ASC, created_at DESC",
                }.get(sort, "ORDER BY created_at DESC")
                cur.execute(f"SELECT * FROM staff {where} {order}", params)
                return [dict(r) for r in cur.fetchall()]

    def get_staff_tags(self) -> list:
        """Все уникальные теги из поля tags сотрудников, отсортированные по частоте"""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT tags FROM staff WHERE tags IS NOT NULL AND tags != ''")
                rows = cur.fetchall()
        counts = {}
        for r in rows:
            for t in r["tags"].split(","):
                t = t.strip()
                if t:
                    counts[t] = counts.get(t, 0) + 1
        return sorted(counts.keys(), key=lambda x: -counts[x])

    def update_staff_status_only(self, staff_id: int, status: str):
        """Быстрое обновление только статуса"""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE staff SET status=%s WHERE id=%s", (status, staff_id))
            conn.commit()
        _cache.invalidate('tga_in_staff', 'wa_in_staff')

    def update_staff(self, staff_id, name, phone, email, position, status, notes, tags, manager_name=None, city=""):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE staff SET name=%s,phone=%s,email=%s,position=%s,status=%s,notes=%s,tags=%s,manager_name=%s,city=%s WHERE id=%s",
                            (name,phone,email,position,status,notes,tags,manager_name or "",city or "",staff_id))
            conn.commit()
        _cache.invalidate('tga_in_staff', 'wa_in_staff')

    def delete_staff_full(self, staff_id):
        """Полное удаление сотрудника со всей связанной информацией"""
        with self._conn() as conn:
            with conn.cursor() as cur:
                # Получаем связанные conv_id
                cur.execute("SELECT conversation_id, wa_conv_id FROM staff WHERE id=%s", (staff_id,))
                r = cur.fetchone()
                if r:
                    if r["conversation_id"]:
                        cur.execute("DELETE FROM messages WHERE conversation_id=%s", (r["conversation_id"],))
                        cur.execute("DELETE FROM utm_tracking WHERE conversation_id=%s", (r["conversation_id"],))
                        cur.execute("DELETE FROM conversations WHERE id=%s", (r["conversation_id"],))
                    if r["wa_conv_id"]:
                        cur.execute("DELETE FROM wa_messages WHERE conversation_id=%s", (r["wa_conv_id"],))
                        cur.execute("DELETE FROM wa_conversations WHERE id=%s", (r["wa_conv_id"],))
                cur.execute("DELETE FROM staff WHERE id=%s", (staff_id,))
            conn.commit()
        _cache.invalidate('tga_in_staff', 'wa_in_staff')

    def get_staff_by_conv(self, conv_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM staff WHERE conversation_id=%s", (conv_id,))
                r = cur.fetchone(); return dict(r) if r else None

    def update_staff_photo(self, staff_id, photo_url):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE staff SET photo_url=%s WHERE id=%s", (photo_url, staff_id))
            conn.commit()

    # ── Галерея фото сотрудника ───────────────────────────────────────────────
    def add_staff_gallery_photo(self, staff_id: int, photo_url: str, caption: str = "") -> dict:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO staff_gallery (staff_id, photo_url, caption, created_at) VALUES (%s,%s,%s,%s) RETURNING *",
                    (staff_id, photo_url, caption, datetime.utcnow().isoformat())
                )
                r = cur.fetchone()
            conn.commit()
            return dict(r)

    def get_staff_gallery(self, staff_id: int) -> list:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM staff_gallery WHERE staff_id=%s ORDER BY created_at ASC", (staff_id,))
                return [dict(r) for r in cur.fetchall()]

    def delete_staff_gallery_photo(self, photo_id: int, staff_id: int) -> bool:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM staff_gallery WHERE id=%s AND staff_id=%s", (photo_id, staff_id))
                deleted = cur.rowcount > 0
            conn.commit()
            return deleted

    # ── Теги для чатов ────────────────────────────────────────────────────────

    def get_all_tags(self) -> list:
        """Все теги справочника"""
        cached = _cache.get('all_tags')
        if cached is not None:
            return cached
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM tags ORDER BY name")
                result = [dict(r) for r in cur.fetchall()]
        _cache.set('all_tags', result, ttl=10.0)
        return result

    def create_tag(self, name: str, color: str = "#6366f1") -> dict:
        """Создать новый тег"""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO tags (name, color, created_at) VALUES (%s,%s,%s) RETURNING *",
                    (name.strip(), color, datetime.utcnow().isoformat())
                )
                r = cur.fetchone()
            conn.commit()
        _cache.invalidate('all_tags')
        _cache.invalidate_prefix('conv_tags_map:')
        return dict(r)

    def update_tag(self, tag_id: int, name: str, color: str) -> bool:
        with self._conn() as conn:
            with conn.cursor() as cur:
                if name.strip():
                    cur.execute("UPDATE tags SET name=%s, color=%s WHERE id=%s", (name.strip(), color, tag_id))
                else:
                    cur.execute("UPDATE tags SET color=%s WHERE id=%s", (color, tag_id))
                ok = cur.rowcount > 0
            conn.commit()
        _cache.invalidate('all_tags')
        _cache.invalidate_prefix('conv_tags_map:')
        return ok

    def delete_tag(self, tag_id: int) -> bool:
        """Удалить тег (conv_tags удалятся каскадно)"""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM tags WHERE id=%s", (tag_id,))
                ok = cur.rowcount > 0
            conn.commit()
        _cache.invalidate('all_tags')
        _cache.invalidate_prefix('conv_tags_map:')
        return ok

    def get_conv_tags(self, conv_type: str, conv_id: int) -> list:
        """Теги конкретного чата"""
        cache_key = f"conv_tags:{conv_type}:{conv_id}"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT t.* FROM tags t
                    JOIN conv_tags ct ON ct.tag_id = t.id
                    WHERE ct.conv_type=%s AND ct.conv_id=%s
                    ORDER BY t.name
                """, (conv_type, conv_id))
                result = [dict(r) for r in cur.fetchall()]
        _cache.set(cache_key, result, ttl=5.0)
        return result

    def add_conv_tag(self, conv_type: str, conv_id: int, tag_id: int) -> bool:
        """Привязать тег к чату"""
        with self._conn() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        "INSERT INTO conv_tags (tag_id, conv_type, conv_id) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                        (tag_id, conv_type, conv_id)
                    )
                    ok = cur.rowcount > 0
                except Exception:
                    ok = False
            conn.commit()
        _cache.invalidate(f"conv_tags:{conv_type}:{conv_id}")
        _cache.invalidate_prefix(f"conv_tags_map:{conv_type}")
        return ok

    def remove_conv_tag(self, conv_type: str, conv_id: int, tag_id: int) -> bool:
        """Отвязать тег от чата"""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM conv_tags WHERE tag_id=%s AND conv_type=%s AND conv_id=%s",
                    (tag_id, conv_type, conv_id)
                )
                ok = cur.rowcount > 0
            conn.commit()
        _cache.invalidate(f"conv_tags:{conv_type}:{conv_id}")
        _cache.invalidate_prefix(f"conv_tags_map:{conv_type}")
        return ok

    def get_all_conv_tags_map(self, conv_type: str) -> dict:
        """Возвращает {conv_id: [tag, ...]} для всех чатов заданного типа — одним запросом"""
        cache_key = f"conv_tags_map:{conv_type}"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT ct.conv_id, t.id, t.name, t.color
                    FROM conv_tags ct JOIN tags t ON t.id = ct.tag_id
                    WHERE ct.conv_type=%s
                """, (conv_type,))
                result: dict = {}
                for r in cur.fetchall():
                    result.setdefault(r["conv_id"], []).append({"id": r["id"], "name": r["name"], "color": r["color"]})
        _cache.set(cache_key, result, ttl=5.0)
        return result

    def get_convs_by_tag(self, conv_type: str, tag_id: int) -> list:
        """Все conv_id чатов с данным тегом"""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT conv_id FROM conv_tags WHERE conv_type=%s AND tag_id=%s",
                    (conv_type, tag_id)
                )
                return [r["conv_id"] for r in cur.fetchall()]

    def get_staff_by_id(self, staff_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM staff WHERE id=%s", (staff_id,))
                r = cur.fetchone(); return dict(r) if r else None

    def get_staff_by_tg_account_conv(self, tga_conv_id):
        """Находит сотрудника по ID TG аккаунт диалога"""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM staff WHERE tga_conv_id=%s LIMIT 1", (tga_conv_id,))
                r = cur.fetchone(); return dict(r) if r else None

    def get_tga_conv_ids_in_staff(self):
        """Возвращает set всех tga_conv_id которые уже добавлены в базу сотрудников"""
        cached = _cache.get('tga_in_staff')
        if cached is not None:
            return cached
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT tga_conv_id, id as staff_id, name FROM staff WHERE tga_conv_id IS NOT NULL")
                result = {r["tga_conv_id"]: {"staff_id": r["staff_id"], "name": r["name"]} for r in cur.fetchall()}
        _cache.set('tga_in_staff', result, ttl=8.0)
        return result

    def get_wa_conv_ids_in_staff(self):
        """Возвращает dict всех wa_conv_id которые уже добавлены в базу сотрудников"""
        cached = _cache.get('wa_in_staff')
        if cached is not None:
            return cached
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT wa_conv_id, id as staff_id, name FROM staff WHERE wa_conv_id IS NOT NULL")
                result = {r["wa_conv_id"]: {"staff_id": r["staff_id"], "name": r["name"]} for r in cur.fetchall()}
        _cache.set('wa_in_staff', result, ttl=8.0)
        return result

    def get_staff_by_wa_conv(self, wa_conv_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM staff WHERE wa_conv_id=%s", (wa_conv_id,))
                r = cur.fetchone(); return dict(r) if r else None

    def get_or_create_wa_staff(self, wa_conv_id, name, wa_number):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM staff WHERE wa_conv_id=%s", (wa_conv_id,))
                r = cur.fetchone()
                if r: return dict(r)
                cur.execute("""INSERT INTO staff (wa_conv_id, name, username, created_at)
                    VALUES (%s,%s,%s,%s) RETURNING *""",
                    (wa_conv_id, name, wa_number, datetime.utcnow().isoformat()))
                r = cur.fetchone()
            conn.commit(); return dict(r)

    def get_or_create_tga_staff(self, tga_conv_id, name, username=""):
        """Создать/найти сотрудника по TG аккаунт диалогу"""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM staff WHERE tga_conv_id=%s", (tga_conv_id,))
                r = cur.fetchone()
                if r: return dict(r)
                tg_handle = ("@" + username) if username else ""
                cur.execute("""INSERT INTO staff (tga_conv_id, name, username, created_at)
                    VALUES (%s,%s,%s,%s) RETURNING *""",
                    (tga_conv_id, name, tg_handle, datetime.utcnow().isoformat()))
                r = cur.fetchone()
            conn.commit()
        _cache.invalidate('tga_in_staff')
        return dict(r)

    def set_staff_fb_event(self, staff_id, event):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE staff SET fb_event_sent=%s WHERE id=%s", (event, staff_id))
            conn.commit()

    def get_staff_funnel(self):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status, COUNT(*) as cnt FROM staff GROUP BY status")
                return {r["status"]: r["cnt"] for r in cur.fetchall()}

    # ── Landings ──────────────────────────────────────────────────────────────
    def get_landings(self, ltype=None):
        with self._conn() as conn:
            with conn.cursor() as cur:
                if ltype:
                    cur.execute("SELECT * FROM landings WHERE type=%s ORDER BY created_at DESC", (ltype,))
                else:
                    cur.execute("SELECT * FROM landings ORDER BY created_at DESC")
                return [dict(r) for r in cur.fetchall()]

    def get_landing(self, landing_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM landings WHERE id=%s", (landing_id,))
                r = cur.fetchone(); return dict(r) if r else None

    def copy_landing(self, landing_id: int, new_name: str, new_slug: str) -> int:
        """Копирует лендинг с новым именем и slug"""
        landing = self.get_landing(landing_id)
        if not landing:
            raise ValueError(f"Landing {landing_id} not found")
        contacts = self.get_landing_contacts(landing_id)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO landings (name, type, slug, content, active, project_id, traffic_source, created_at)
                       VALUES (%s, %s, %s, %s, 1, %s, %s, %s) RETURNING id""",
                    (new_name.strip(), landing.get("type", "staff"), new_slug.strip(),
                     landing.get("content", "{}"), landing.get("project_id"),
                     landing.get("traffic_source", ""),
                     __import__("datetime").datetime.utcnow().isoformat())
                )
                new_id = cur.fetchone()["id"]
                for c in contacts:
                    cur.execute(
                        "INSERT INTO landing_contacts (landing_id, type, label, url, position) VALUES (%s,%s,%s,%s,%s)",
                        (new_id, c["type"], c["label"], c["url"], c.get("position", 0))
                    )
            conn.commit()
        return new_id

    def update_landing_traffic_source(self, landing_id: int, traffic_source: str):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE landings SET traffic_source=%s WHERE id=%s", (traffic_source, landing_id))
            conn.commit()

    def get_landing_by_slug(self, slug):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM landings WHERE slug=%s", (slug,))
                r = cur.fetchone(); return dict(r) if r else None

    def get_landing_by_domain(self, domain: str):
        """Найти лендинг по кастомному домену (без www, без порта)"""
        domain = domain.lower().strip()
        # Убираем www.
        if domain.startswith("www."):
            domain = domain[4:]
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM landings WHERE LOWER(custom_domain)=%s AND custom_domain!=''", (domain,))
                r = cur.fetchone(); return dict(r) if r else None

    def set_landing_custom_domain(self, landing_id: int, domain: str) -> bool:
        """Установить или очистить кастомный домен лендинга"""
        domain = domain.strip().lower()
        if domain.startswith("www."):
            domain = domain[4:]
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE landings SET custom_domain=%s WHERE id=%s", (domain, landing_id))
                ok = cur.rowcount > 0
            conn.commit()
        return ok

    def create_landing(self, name, ltype, slug, content):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO landings (name,type,slug,content,created_at) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                            (name, ltype, slug, content, datetime.utcnow().isoformat()))
                r = cur.fetchone()
            conn.commit(); return r["id"]

    def update_landing_content(self, landing_id, content):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE landings SET content=%s WHERE id=%s", (content, landing_id))
            conn.commit()

    def delete_landing(self, landing_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM landing_contacts WHERE landing_id=%s", (landing_id,))
                cur.execute("DELETE FROM landings WHERE id=%s", (landing_id,))
            conn.commit()

    def get_landing_contacts(self, landing_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM landing_contacts WHERE landing_id=%s ORDER BY position", (landing_id,))
                return [dict(r) for r in cur.fetchall()]

    def add_landing_contact(self, landing_id, ctype, label, url, city=""):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COALESCE(MAX(position),0)+1 as p FROM landing_contacts WHERE landing_id=%s", (landing_id,))
                pos = cur.fetchone()["p"]
                cur.execute("INSERT INTO landing_contacts (landing_id,type,label,url,position,city) VALUES (%s,%s,%s,%s,%s,%s)",
                            (landing_id,ctype,label,url,pos,city.strip()))
            conn.commit()

    def delete_landing_contact(self, contact_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM landing_contacts WHERE id=%s", (contact_id,))
            conn.commit()

    # ── WA Conversations ──────────────────────────────────────────────────────
    def get_or_create_wa_conversation(self, wa_chat_id, wa_number, visitor_name,
                                       utm_source=None, utm_campaign=None, fbclid=None):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM wa_conversations WHERE wa_chat_id=%s", (wa_chat_id,))
                r = cur.fetchone()
                if r: return dict(r)
                cur.execute("""INSERT INTO wa_conversations
                    (wa_chat_id,wa_number,visitor_name,utm_source,utm_campaign,fbclid,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                    (wa_chat_id,wa_number,visitor_name,utm_source,utm_campaign,fbclid,
                     datetime.utcnow().isoformat()))
                r = cur.fetchone()
            conn.commit(); return dict(r)

    def get_wa_conversations(self, status=None, limit=30, offset=0):
        cache_key = f"wa_convs:{status or 'all'}:{offset}"
        if offset == 0:
            cached = _cache.get(cache_key)
            if cached is not None:
                return cached
        with self._conn() as conn:
            with conn.cursor() as cur:
                if status:
                    cur.execute("SELECT * FROM wa_conversations WHERE status=%s ORDER BY COALESCE(last_message_at,created_at) DESC LIMIT %s OFFSET %s", (status, limit, offset))
                else:
                    cur.execute("SELECT * FROM wa_conversations ORDER BY COALESCE(last_message_at,created_at) DESC LIMIT %s OFFSET %s", (limit, offset))
                result = [dict(r) for r in cur.fetchall()]
        if offset == 0:
            _cache.set(cache_key, result, ttl=4.0)
        return result

    def count_wa_conversations(self, status=None):
        with self._conn() as conn:
            with conn.cursor() as cur:
                if status:
                    cur.execute("SELECT COUNT(*) as c FROM wa_conversations WHERE status=%s", (status,))
                else:
                    cur.execute("SELECT COUNT(*) as c FROM wa_conversations")
                return cur.fetchone()["c"]

    def delete_wa_conversation(self, conv_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM wa_messages WHERE conversation_id=%s", (conv_id,))
                cur.execute("DELETE FROM conv_tags WHERE conv_type='wa' AND conv_id=%s", (conv_id,))
                # Отвязываем сотрудника (не удаляем карточку, только связь)
                cur.execute("UPDATE staff SET wa_conv_id=NULL WHERE wa_conv_id=%s", (conv_id,))
                cur.execute("DELETE FROM wa_conversations WHERE id=%s", (conv_id,))
            conn.commit()
        _cache.invalidate_prefix('wa_convs:')
        _cache.invalidate(f"conv_tags:wa:{conv_id}")
        _cache.invalidate_prefix("conv_tags_map:wa")

    def get_wa_conversation(self, conv_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM wa_conversations WHERE id=%s", (conv_id,))
                r = cur.fetchone(); return dict(r) if r else None

    def save_wa_message(self, conv_id, wa_chat_id, sender_type, content,
                        media_url=None, media_type=None, sender_name=None):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO wa_messages
                    (conversation_id,wa_chat_id,sender_type,content,media_url,media_type,created_at,sender_name)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (conv_id,wa_chat_id,sender_type,content,media_url,media_type,
                     datetime.utcnow().isoformat(),sender_name))
            conn.commit()

    def get_wa_messages(self, conv_id, limit=100):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM wa_messages WHERE conversation_id=%s ORDER BY created_at ASC LIMIT %s",
                            (conv_id, limit))
                return [dict(r) for r in cur.fetchall()]

    def get_new_wa_messages(self, conv_id, after_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM wa_messages WHERE conversation_id=%s AND id>%s ORDER BY created_at ASC",
                            (conv_id, after_id))
                return [dict(r) for r in cur.fetchall()]

    def update_wa_last_message(self, wa_chat_id, text, increment_unread=True):
        safe_text = (text or "")[:100]
        with self._conn() as conn:
            with conn.cursor() as cur:
                if increment_unread:
                    cur.execute("UPDATE wa_conversations SET last_message=%s,last_message_at=%s,unread_count=unread_count+1 WHERE wa_chat_id=%s",
                                (safe_text, datetime.utcnow().isoformat(), wa_chat_id))
                else:
                    cur.execute("UPDATE wa_conversations SET last_message=%s,last_message_at=%s WHERE wa_chat_id=%s",
                                (safe_text, datetime.utcnow().isoformat(), wa_chat_id))
            conn.commit()
        _cache.invalidate_prefix('wa_convs:')

    def mark_wa_read(self, conv_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE wa_conversations SET unread_count=0 WHERE id=%s", (conv_id,))
                cur.execute("UPDATE wa_messages SET read_by_manager=1 WHERE conversation_id=%s AND sender_type='visitor'", (conv_id,))
            conn.commit()
        _cache.invalidate_prefix('wa_convs:')
        _cache.invalidate('stats')

    def close_wa_conversation(self, conv_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE wa_conversations SET status='closed' WHERE id=%s", (conv_id,))
            conn.commit()
        _cache.invalidate_prefix('wa_convs:')

    def reopen_wa_conversation(self, conv_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE wa_conversations SET status='open' WHERE id=%s", (conv_id,))
            conn.commit()
        _cache.invalidate_prefix('wa_convs:')

    def set_wa_fb_event(self, conv_id, event):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE wa_conversations SET fb_event_sent=%s WHERE id=%s", (event, conv_id))
            conn.commit()

    def get_wa_stats(self):
        with self._conn() as conn:
            with conn.cursor() as cur:
                def cnt(q): cur.execute(q); return cur.fetchone()["c"]
                return {
                    "total_convs": cnt("SELECT COUNT(*) as c FROM wa_conversations"),
                    "open_convs":  cnt("SELECT COUNT(*) as c FROM wa_conversations WHERE status='open'"),
                    "unread":      cnt("SELECT COALESCE(SUM(unread_count),0) as c FROM wa_conversations"),
                    "total_msgs":  cnt("SELECT COUNT(*) as c FROM wa_messages"),
                    "incoming":    cnt("SELECT COUNT(*) as c FROM wa_messages WHERE sender_type='visitor'"),
                    "outgoing":    cnt("SELECT COUNT(*) as c FROM wa_messages WHERE sender_type='manager'"),
                }

    # ── Stats ─────────────────────────────────────────────────────────────────
    def get_stats(self):
        cached = _cache.get('stats')
        if cached is not None:
            return cached
        with self._conn() as conn:
            with conn.cursor() as cur:
                def cnt(q, p=None):
                    cur.execute(q, p); return cur.fetchone()["c"]
                result = {
                    "total":       cnt("SELECT COUNT(*) as c FROM joins"),
                    "from_ads":    cnt("SELECT COUNT(*) as c FROM joins WHERE campaign_name!='organic'"),
                    "organic":     cnt("SELECT COUNT(*) as c FROM joins WHERE campaign_name='organic'"),
                    "channels":    cnt("SELECT COUNT(*) as c FROM channels"),
                    "campaigns":   cnt("SELECT COUNT(*) as c FROM campaigns"),
                    "conversations": cnt("SELECT COUNT(*) as c FROM conversations"),
                    "unread":      cnt("SELECT COALESCE(SUM(unread_count),0) as c FROM conversations"),
                    "staff":       cnt("SELECT COUNT(*) as c FROM staff"),
                    "clicks":      cnt("SELECT COUNT(*) as c FROM click_tracking"),
                    "wa_unread":   cnt("SELECT COALESCE(SUM(unread_count),0) as c FROM wa_conversations"),
                    "tga_unread":  cnt("SELECT COALESCE(SUM(unread_count),0) as c FROM tg_account_conversations"),
                }
        _cache.set('stats', result, ttl=3.0)
        return result

    # ══════════════════════════════════════════════════════════════════════════
    # КЛИЕНТЫ — аналитика подписок
    # ══════════════════════════════════════════════════════════════════════════

    def get_joins_by_day(self, days=30, date_from=None, date_to=None):
        where, params = self._date_filter("joined_at", days, date_from, date_to)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""SELECT DATE(joined_at::timestamp) as day,
                    COUNT(*) as cnt,
                    SUM(CASE WHEN campaign_name!='organic' THEN 1 ELSE 0 END) as from_ads,
                    SUM(CASE WHEN campaign_name='organic' THEN 1 ELSE 0 END) as organic
                    FROM joins {where} GROUP BY day ORDER BY day""", params)
                return [dict(r) for r in cur.fetchall()]

    def get_joins_summary(self, date_from=None, date_to=None, days=30):
        where, params = self._date_filter("joined_at", days, date_from, date_to)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN campaign_name!='organic' THEN 1 ELSE 0 END) as from_ads,
                    SUM(CASE WHEN campaign_name='organic' THEN 1 ELSE 0 END) as organic,
                    SUM(CASE WHEN click_id IS NOT NULL THEN 1 ELSE 0 END) as tracked,
                    COUNT(DISTINCT channel_id) as channels_active,
                    COUNT(DISTINCT campaign_name) as campaigns_active
                    FROM joins {where}""", params)
                return dict(cur.fetchone())

    def get_joins_by_channel(self, date_from=None, date_to=None, days=30):
        where, params = self._date_filter("j.joined_at", days, date_from, date_to)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""SELECT
                    COALESCE(
                        NULLIF(cc.channel_name, ''),
                        NULLIF(cc.channel_name, j.channel_id),
                        ch.name,
                        j.channel_id,
                        'Неизвестно'
                    ) as channel_name,
                    j.channel_id,
                    COUNT(*) as joins,
                    SUM(CASE WHEN j.campaign_name!='organic' THEN 1 ELSE 0 END) as from_ads,
                    MIN(j.joined_at) as first_join,
                    MAX(j.joined_at) as last_join
                    FROM joins j
                    LEFT JOIN channels ch ON ch.channel_id = j.channel_id
                    LEFT JOIN campaign_channels cc ON cc.invite_link = j.invite_link
                        AND cc.channel_name IS NOT NULL
                        AND cc.channel_name != ''
                        AND cc.channel_name != j.channel_id
                    {where} GROUP BY j.channel_id, ch.name, cc.channel_name ORDER BY joins DESC""", params)
                return [dict(r) for r in cur.fetchall()]

    def get_joins_by_campaign(self, date_from=None, date_to=None, days=30):
        where, params = self._date_filter("joined_at", days, date_from, date_to)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""SELECT
                    campaign_name,
                    COUNT(*) as joins,
                    SUM(CASE WHEN click_id IS NOT NULL THEN 1 ELSE 0 END) as tracked,
                    MIN(joined_at) as first_join,
                    MAX(joined_at) as last_join
                    FROM joins {where}
                    GROUP BY campaign_name ORDER BY joins DESC LIMIT 30""", params)
                return [dict(r) for r in cur.fetchall()]

    def get_campaign_funnel(self, date_from=None, date_to=None, days=30):
        """Воронка по кампаниям: клики → подписки → конверсия + разбивка по городам"""
        where_j, params_j = self._date_filter("j.joined_at", days, date_from, date_to)
        where_c, params_c = self._date_filter("ct.created_at", days, date_from, date_to)
        with self._conn() as conn:
            with conn.cursor() as cur:
                # Клики по utm_campaign
                cur.execute(f"""SELECT COALESCE(utm_campaign,'(direct)') as campaign,
                    COUNT(*) as clicks,
                    SUM(CASE WHEN fbclid IS NOT NULL THEN 1 ELSE 0 END) as fb_clicks
                    FROM click_tracking ct {where_c}
                    GROUP BY utm_campaign""", params_c)
                clicks_map = {r['campaign']: dict(r) for r in cur.fetchall()}

                # Подписки по campaign_name + город из cc
                cur.execute(f"""SELECT j.campaign_name,
                    COUNT(*) as joins,
                    SUM(CASE WHEN j.click_id IS NOT NULL THEN 1 ELSE 0 END) as tracked,
                    SUM(CASE WHEN ct.fbclid IS NOT NULL THEN 1 ELSE 0 END) as fb_joins,
                    MAX(j.joined_at) as last_join,
                    COUNT(DISTINCT j.channel_id) as channels
                    FROM joins j
                    LEFT JOIN click_tracking ct ON ct.click_id = j.click_id
                    {where_j}
                    GROUP BY j.campaign_name ORDER BY joins DESC""", params_j)
                rows = [dict(r) for r in cur.fetchall()]

                # Подписки по городам (из campaign_channels.city)
                cur.execute(f"""SELECT j.campaign_name,
                    COALESCE(cc.city, '—') as city,
                    COUNT(*) as joins
                    FROM joins j
                    LEFT JOIN campaign_channels cc ON cc.invite_link = j.invite_link
                    {where_j}
                    GROUP BY j.campaign_name, cc.city ORDER BY joins DESC""", params_j)
                city_rows = cur.fetchall()
                city_map = {}
                for r in city_rows:
                    city_map.setdefault(r['campaign_name'], []).append(
                        {'city': r['city'], 'joins': r['joins']}
                    )

                # Объединяем
                for row in rows:
                    cname = row['campaign_name']
                    cl = clicks_map.get(cname, {})
                    row['clicks']    = cl.get('clicks', 0)
                    row['fb_clicks'] = cl.get('fb_clicks', 0)
                    row['cr'] = round(row['joins'] / row['clicks'] * 100, 1) if row.get('clicks') else 0
                    row['cities'] = city_map.get(cname, [])
                return rows

    def get_clicks_by_day(self, date_from=None, date_to=None, days=30):
        where, params = self._date_filter("created_at", days, date_from, date_to)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""SELECT DATE(created_at::timestamp) as day,
                    COUNT(*) as clicks,
                    SUM(CASE WHEN fbclid IS NOT NULL THEN 1 ELSE 0 END) as from_fb
                    FROM click_tracking {where} GROUP BY day ORDER BY day""", params)
                return [dict(r) for r in cur.fetchall()]

    def get_clicks_summary(self, date_from=None, date_to=None, days=30):
        where, params = self._date_filter("created_at", days, date_from, date_to)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""SELECT COUNT(*) as total,
                    SUM(CASE WHEN fbclid IS NOT NULL THEN 1 ELSE 0 END) as from_fb,
                    SUM(CASE WHEN fbp IS NOT NULL THEN 1 ELSE 0 END) as has_fbp,
                    COUNT(DISTINCT utm_campaign) as campaigns
                    FROM click_tracking {where}""", params)
                return dict(cur.fetchone())

    def get_utm_sources(self, date_from=None, date_to=None, days=30):
        where, params = self._date_filter("created_at", days, date_from, date_to)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""SELECT
                    COALESCE(utm_source,'(direct)') as source,
                    COALESCE(utm_medium,'(none)') as medium,
                    COUNT(*) as clicks
                    FROM click_tracking {where}
                    GROUP BY utm_source, utm_medium ORDER BY clicks DESC LIMIT 20""", params)
                return [dict(r) for r in cur.fetchall()]

    def get_recent_joins_detailed(self, limit=30, date_from=None, date_to=None, days=30):
        where, params = self._date_filter("j.joined_at", days, date_from, date_to)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""SELECT j.*,
                    COALESCE(
                        NULLIF(cc.channel_name, ''),
                        NULLIF(cc.channel_name, j.channel_id),
                        ch.name,
                        j.channel_id
                    ) as channel_name,
                    ct.utm_source, ct.utm_medium, ct.utm_campaign as utm_campaign_tag,
                    ct.fbclid, ct.fbp
                    FROM joins j
                    LEFT JOIN channels ch ON ch.channel_id = j.channel_id
                    LEFT JOIN click_tracking ct ON ct.click_id = j.click_id
                    LEFT JOIN campaign_channels cc ON cc.invite_link = j.invite_link
                        AND cc.channel_name IS NOT NULL
                        AND cc.channel_name != ''
                        AND cc.channel_name != j.channel_id
                    {where} ORDER BY j.joined_at DESC LIMIT %s""", params + [limit])
                return [dict(r) for r in cur.fetchall()]

    # ══════════════════════════════════════════════════════════════════════════
    # СОТРУДНИКИ — аналитика
    # ══════════════════════════════════════════════════════════════════════════

    def get_staff_summary(self, date_from=None, date_to=None, days=30):
        where, params = self._date_filter("created_at", days, date_from, date_to)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""SELECT COUNT(*) as total,
                    SUM(CASE WHEN status='new' THEN 1 ELSE 0 END) as s_new,
                    SUM(CASE WHEN status='review' THEN 1 ELSE 0 END) as s_review,
                    SUM(CASE WHEN status='interview' THEN 1 ELSE 0 END) as s_interview,
                    SUM(CASE WHEN status='hired' THEN 1 ELSE 0 END) as s_hired,
                    SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END) as s_rejected
                    FROM staff {where}""", params)
                return dict(cur.fetchone())

    def get_staff_by_day(self, date_from=None, date_to=None, days=30):
        where, params = self._date_filter("created_at", days, date_from, date_to)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""SELECT DATE(created_at::timestamp) as day,
                    COUNT(*) as cnt,
                    SUM(CASE WHEN status='hired' THEN 1 ELSE 0 END) as hired
                    FROM staff {where} GROUP BY day ORDER BY day""", params)
                return [dict(r) for r in cur.fetchall()]

    def get_messages_by_day(self, date_from=None, date_to=None, days=30):
        """Сообщения TG чата по дням"""
        where, params = self._date_filter("created_at", days, date_from, date_to)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""SELECT DATE(created_at::timestamp) as day,
                    COUNT(*) as total,
                    SUM(CASE WHEN sender_type='visitor' THEN 1 ELSE 0 END) as incoming,
                    SUM(CASE WHEN sender_type='manager' THEN 1 ELSE 0 END) as outgoing
                    FROM messages {where} GROUP BY day ORDER BY day""", params)
                return [dict(r) for r in cur.fetchall()]

    def get_messages_summary(self, date_from=None, date_to=None, days=30):
        where, params = self._date_filter("created_at", days, date_from, date_to)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""SELECT COUNT(*) as total,
                    SUM(CASE WHEN sender_type='visitor' THEN 1 ELSE 0 END) as incoming,
                    SUM(CASE WHEN sender_type='manager' THEN 1 ELSE 0 END) as outgoing,
                    COUNT(DISTINCT conversation_id) as active_convos
                    FROM messages {where}""", params)
                return dict(cur.fetchone())

    def get_wa_messages_by_day(self, date_from=None, date_to=None, days=30):
        where, params = self._date_filter("created_at", days, date_from, date_to)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""SELECT DATE(created_at::timestamp) as day,
                    COUNT(*) as total,
                    SUM(CASE WHEN sender_type='visitor' THEN 1 ELSE 0 END) as incoming,
                    SUM(CASE WHEN sender_type='manager' THEN 1 ELSE 0 END) as outgoing
                    FROM wa_messages {where} GROUP BY day ORDER BY day""", params)
                return [dict(r) for r in cur.fetchall()]

    def get_tga_messages_by_day(self, date_from=None, date_to=None, days=30):
        """Сообщения TG аккаунт чатов по дням"""
        where, params = self._date_filter("created_at", days, date_from, date_to)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""SELECT DATE(created_at::timestamp) as day,
                    COUNT(*) as total,
                    SUM(CASE WHEN sender_type='visitor' THEN 1 ELSE 0 END) as incoming,
                    SUM(CASE WHEN sender_type='manager' THEN 1 ELSE 0 END) as outgoing
                    FROM tg_account_messages {where} GROUP BY day ORDER BY day""", params)
                return [dict(r) for r in cur.fetchall()]

    def get_tga_messages_summary(self, date_from=None, date_to=None, days=30):
        """Сводка по сообщениям TG аккаунт чатов"""
        where, params = self._date_filter("created_at", days, date_from, date_to)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""SELECT COUNT(*) as total,
                    SUM(CASE WHEN sender_type='visitor' THEN 1 ELSE 0 END) as incoming,
                    SUM(CASE WHEN sender_type='manager' THEN 1 ELSE 0 END) as outgoing,
                    COUNT(DISTINCT conversation_id) as active_convos
                    FROM tg_account_messages {where}""", params)
                return dict(cur.fetchone())

    def get_tga_stats(self):
        """Общая статистика TG аккаунт чатов"""
        with self._conn() as conn:
            with conn.cursor() as cur:
                def cnt(q): cur.execute(q); return cur.fetchone()["c"]
                return {
                    "total_convs": cnt("SELECT COUNT(*) as c FROM tg_account_conversations"),
                    "open_convs":  cnt("SELECT COUNT(*) as c FROM tg_account_conversations WHERE status='open'"),
                    "unread":      cnt("SELECT COALESCE(SUM(unread_count),0) as c FROM tg_account_conversations"),
                    "total_msgs":  cnt("SELECT COUNT(*) as c FROM tg_account_messages"),
                    "incoming":    cnt("SELECT COUNT(*) as c FROM tg_account_messages WHERE sender_type='visitor'"),
                    "outgoing":    cnt("SELECT COUNT(*) as c FROM tg_account_messages WHERE sender_type='manager'"),
                    "fb_convs":    cnt("SELECT COUNT(*) as c FROM tg_account_conversations WHERE fbclid IS NOT NULL AND fbclid != ''"),
                }

    def get_staff_funnel(self, date_from=None, date_to=None):
        """Воронка + конверсия"""
        if date_from and date_to:
            where = "WHERE created_at::timestamp BETWEEN %s AND %s"
            params = [date_from, date_to + " 23:59:59"]
        else:
            where, params = "", []
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT status, COUNT(*) as cnt FROM staff {where} GROUP BY status", params)
                d = {r["status"]: r["cnt"] for r in cur.fetchall()}
        total = sum(d.values()) or 1
        d["conversion_hired"] = round(d.get("hired", 0) / total * 100, 1)
        d["conversion_rejected"] = round(d.get("rejected", 0) / total * 100, 1)
        return d

    def get_staff_response_stats(self, date_from=None, date_to=None, days=30):
        """Активность по каждому разговору — сколько сообщений, последнее"""
        where, params = self._date_filter("s.created_at", days, date_from, date_to)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""SELECT s.name, s.status, s.created_at,
                    COALESCE(s.tg_chat_id, 'WA') as channel,
                    COUNT(m.id) as msg_count,
                    MAX(m.created_at) as last_message_at
                    FROM staff s
                    LEFT JOIN messages m ON m.tg_chat_id = s.tg_chat_id
                    {where}
                    GROUP BY s.id, s.name, s.status, s.created_at, s.tg_chat_id
                    ORDER BY s.created_at DESC LIMIT 50""", params)
                return [dict(r) for r in cur.fetchall()]

    # ── Вспомогательный метод фильтра дат ─────────────────────────────────────
    def _date_filter(self, field: str, days: int = 30, date_from=None, date_to=None):
        if date_from and date_to:
            return f"WHERE {field}::timestamp BETWEEN %s AND %s", [date_from, date_to + " 23:59:59"]
        elif date_from:
            return f"WHERE {field}::timestamp >= %s", [date_from]
        else:
            return f"WHERE {field}::timestamp >= NOW() - INTERVAL '{days} days'", []

    def get_campaign_stats(self):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT campaign_name, COUNT(*) as joins,
                    MIN(joined_at) as first_join, MAX(joined_at) as last_join
                    FROM joins WHERE campaign_name!='organic'
                    GROUP BY campaign_name ORDER BY joins DESC LIMIT 20""")
                return [dict(r) for r in cur.fetchall()]

    def get_click_stats(self, days=30):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT DATE(created_at::timestamp) as day, COUNT(*) as clicks
                    FROM click_tracking WHERE created_at::timestamp >= NOW() - INTERVAL '30 days'
                    GROUP BY day ORDER BY day""")
                return [dict(r) for r in cur.fetchall()]

    # ══════════════════════════════════════════════════════════════════════════
    # TG АККАУНТ — методы работы с диалогами
    # ══════════════════════════════════════════════════════════════════════════

    def _init_tg_account_tables(self):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("ALTER TABLE tg_account_conversations ADD COLUMN IF NOT EXISTS photo_url TEXT DEFAULT ''")
                cur.execute("ALTER TABLE tg_account_conversations ADD COLUMN IF NOT EXISTS tg_about TEXT DEFAULT ''")
                cur.execute("""
                CREATE TABLE IF NOT EXISTS tg_account_conversations (
                    id              SERIAL PRIMARY KEY,
                    tg_user_id      TEXT NOT NULL UNIQUE,
                    visitor_name    TEXT NOT NULL DEFAULT 'Неизвестный',
                    username        TEXT DEFAULT '',
                    phone           TEXT DEFAULT '',
                    status          TEXT DEFAULT 'open',
                    unread_count    INTEGER DEFAULT 0,
                    last_message    TEXT,
                    last_message_at TEXT,
                    fb_event_sent   TEXT,
                    fbclid          TEXT,
                    fbp             TEXT,
                    utm_source      TEXT,
                    utm_medium      TEXT,
                    utm_campaign    TEXT,
                    utm_content     TEXT,
                    utm_term        TEXT,
                    created_at      TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tg_account_messages (
                    id              SERIAL PRIMARY KEY,
                    conversation_id INTEGER NOT NULL REFERENCES tg_account_conversations(id) ON DELETE CASCADE,
                    tg_user_id      TEXT NOT NULL,
                    sender_type     TEXT NOT NULL,
                    sender_name     TEXT DEFAULT '',
                    content         TEXT,
                    media_url       TEXT,
                    media_type      TEXT,
                    created_at      TEXT NOT NULL
                );
                """)
            conn.commit()

    def get_or_create_tg_account_conversation(self, tg_user_id, visitor_name, username="", phone=""):
        self._init_tg_account_tables()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM tg_account_conversations WHERE tg_user_id=%s", (tg_user_id,))
                r = cur.fetchone()
                if r:
                    if visitor_name and not visitor_name.isdigit():
                        cur.execute("UPDATE tg_account_conversations SET visitor_name=%s, username=%s WHERE tg_user_id=%s",
                                    (visitor_name, username, tg_user_id))
                        conn.commit()
                        cur.execute("SELECT * FROM tg_account_conversations WHERE tg_user_id=%s", (tg_user_id,))
                        r = cur.fetchone()
                    return dict(r)
                cur.execute("""INSERT INTO tg_account_conversations
                    (tg_user_id,visitor_name,username,phone,created_at)
                    VALUES (%s,%s,%s,%s,%s) RETURNING *""",
                    (tg_user_id, visitor_name, username, phone, datetime.utcnow().isoformat()))
                r = cur.fetchone()
            conn.commit()
            return dict(r)

    def get_tg_account_conversation(self, conv_id):
        self._init_tg_account_tables()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM tg_account_conversations WHERE id=%s", (conv_id,))
                r = cur.fetchone(); return dict(r) if r else None

    def get_tg_account_conversations(self, status=None, limit=30, offset=0):
        self._init_tg_account_tables()
        cache_key = f"tga_convs:{status or 'all'}:{offset}"
        if offset == 0:
            cached = _cache.get(cache_key)
            if cached is not None:
                return cached
        with self._conn() as conn:
            with conn.cursor() as cur:
                if status:
                    cur.execute("SELECT * FROM tg_account_conversations WHERE status=%s ORDER BY COALESCE(last_message_at,created_at) DESC LIMIT %s OFFSET %s", (status, limit, offset))
                else:
                    cur.execute("SELECT * FROM tg_account_conversations ORDER BY COALESCE(last_message_at,created_at) DESC LIMIT %s OFFSET %s", (limit, offset))
                result = [dict(r) for r in cur.fetchall()]
        if offset == 0:
            _cache.set(cache_key, result, ttl=4.0)
        return result

    def count_tg_account_conversations(self, status=None):
        self._init_tg_account_tables()
        with self._conn() as conn:
            with conn.cursor() as cur:
                if status:
                    cur.execute("SELECT COUNT(*) as c FROM tg_account_conversations WHERE status=%s", (status,))
                else:
                    cur.execute("SELECT COUNT(*) as c FROM tg_account_conversations")
                return cur.fetchone()["c"]

    def get_tg_account_conv_by_user(self, tg_user_id: str):
        """Найти диалог по tg_user_id."""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM tg_account_conversations WHERE tg_user_id=%s", (tg_user_id,))
                r = cur.fetchone()
                return dict(r) if r else None

    def mark_tga_messages_read(self, conv_id: int, max_id: int):
        """Пометить исходящие сообщения как прочитанные до max_id включительно."""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE tg_account_messages
                    SET is_read = TRUE
                    WHERE conversation_id = %s
                    AND sender_type = 'manager'
                    AND is_read = FALSE
                    AND (tg_msg_id IS NULL OR tg_msg_id <= %s)""",
                    (conv_id, max_id))
            conn.commit()

    def get_tga_read_max_id(self, conv_id: int) -> int:
        """Получить max tg_msg_id прочитанных исходящих сообщений."""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT COALESCE(MAX(tg_msg_id), 0) as max_id
                    FROM tg_account_messages
                    WHERE conversation_id=%s AND sender_type='manager' AND is_read=TRUE""",
                    (conv_id,))
                r = cur.fetchone()
                return r["max_id"] if r else 0

    def save_tg_account_message(self, conv_id, tg_user_id, sender_type, content,
                                 media_url=None, media_type=None, sender_name=None):
        self._init_tg_account_tables()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO tg_account_messages
                    (conversation_id,tg_user_id,sender_type,sender_name,content,media_url,media_type,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (conv_id,tg_user_id,sender_type,sender_name or "",content,media_url,media_type,datetime.utcnow().isoformat()))
            conn.commit()

    def get_tg_account_messages(self, conv_id, limit=100):
        self._init_tg_account_tables()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM tg_account_messages WHERE conversation_id=%s ORDER BY created_at ASC LIMIT %s", (conv_id, limit))
                return [dict(r) for r in cur.fetchall()]

    def get_new_tg_account_messages(self, conv_id, after_id=0):
        self._init_tg_account_tables()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM tg_account_messages WHERE conversation_id=%s AND id>%s ORDER BY created_at ASC", (conv_id, after_id))
                return [dict(r) for r in cur.fetchall()]

    def update_tg_account_last_message(self, tg_user_id, text, increment_unread=True):
        self._init_tg_account_tables()
        with self._conn() as conn:
            with conn.cursor() as cur:
                if increment_unread:
                    cur.execute("UPDATE tg_account_conversations SET last_message=%s,last_message_at=%s,unread_count=unread_count+1 WHERE tg_user_id=%s",
                                (text[:100],datetime.utcnow().isoformat(),tg_user_id))
                else:
                    cur.execute("UPDATE tg_account_conversations SET last_message=%s,last_message_at=%s WHERE tg_user_id=%s",
                                (text[:100],datetime.utcnow().isoformat(),tg_user_id))
            conn.commit()
        _cache.invalidate_prefix('tga_convs:')
        _cache.invalidate('stats')

    def mark_tg_account_conv_read(self, conv_id):
        self._init_tg_account_tables()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE tg_account_conversations SET unread_count=0 WHERE id=%s", (conv_id,))
            conn.commit()
        _cache.invalidate_prefix('tga_convs:')

    def apply_utm_to_tg_account_conv(self, conv_id, fbclid=None, fbp=None, utm_source=None,
                                      utm_medium=None, utm_campaign=None, utm_content=None, utm_term=None,
                                      ttclid=None, ttp=None):
        self._init_tg_account_tables()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE tg_account_conversations
                    SET fbclid=%s, fbp=%s, utm_source=%s, utm_medium=%s,
                        utm_campaign=%s, utm_content=%s, utm_term=%s
                    WHERE id=%s AND (utm_source IS NULL OR utm_source='')""",
                    (fbclid, fbp, utm_source, utm_medium, utm_campaign, utm_content, utm_term, conv_id))
                # ttclid/ttp сохраняем всегда если есть
                if ttclid or ttp:
                    cur.execute("""UPDATE tg_account_conversations
                        SET ttclid=%s, ttp=%s WHERE id=%s""",
                        (ttclid or '', ttp or '', conv_id))
            conn.commit()
        _cache.invalidate_prefix('tga_convs:')

    def set_tg_account_fb_event(self, conv_id, event):
        self._init_tg_account_tables()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE tg_account_conversations SET fb_event_sent=%s WHERE id=%s", (event, conv_id))
            conn.commit()

    def close_tg_account_conv(self, conv_id):
        self._init_tg_account_tables()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE tg_account_conversations SET status='closed' WHERE id=%s", (conv_id,))
            conn.commit()
        _cache.invalidate_prefix('tga_convs:')

    def reopen_tg_account_conv(self, conv_id):
        self._init_tg_account_tables()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE tg_account_conversations SET status='open' WHERE id=%s", (conv_id,))
            conn.commit()
        _cache.invalidate_prefix('tga_convs:')

    def update_tg_account_contact_info(self, conv_id, photo_url=None, about=None):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE tg_account_conversations SET photo_url=%s, tg_about=%s WHERE id=%s",
                            (photo_url or "", about or "", conv_id))
            conn.commit()

    def delete_tg_account_conversation(self, conv_id):
        self._init_tg_account_tables()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM tg_account_messages WHERE conversation_id=%s", (conv_id,))
                cur.execute("DELETE FROM conv_tags WHERE conv_type='tga' AND conv_id=%s", (conv_id,))
                # Отвязываем сотрудника (не удаляем карточку, только связь)
                cur.execute("UPDATE staff SET tga_conv_id=NULL WHERE tga_conv_id=%s", (conv_id,))
                cur.execute("DELETE FROM tg_account_conversations WHERE id=%s", (conv_id,))
            conn.commit()
        _cache.invalidate_prefix('tga_convs:')
        _cache.invalidate(f"conv_tags:tga:{conv_id}")
        _cache.invalidate_prefix("conv_tags_map:tga")

    # ══════════════════════════════════════════════════════════════════════════
    # PROJECTS — мультипиксельные проекты
    # ══════════════════════════════════════════════════════════════════════════

    def get_projects(self) -> list:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM projects ORDER BY created_at")
                return [dict(r) for r in cur.fetchall()]

    def get_project(self, project_id: int) -> dict | None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM projects WHERE id=%s", (project_id,))
                r = cur.fetchone()
                return dict(r) if r else None

    def create_project(self, name: str) -> int:
        from datetime import datetime
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO projects (name, created_at) VALUES (%s, %s) RETURNING id",
                    (name.strip(), datetime.utcnow().isoformat())
                )
                return cur.fetchone()["id"]
            conn.commit()

    def update_project(self, project_id: int, name: str = None,
                       fb_pixel_id: str = None, fb_token: str = None,
                       tt_pixel_id: str = None, tt_token: str = None,
                       utm_campaigns: str = None, test_event_code: str = None,
                       tt_test_event_code: str = None, traffic_source: str = None, **kwargs):
        fields, vals = [], []
        if name         is not None: fields.append("name=%s");          vals.append(name.strip())
        if fb_pixel_id  is not None: fields.append("fb_pixel_id=%s");   vals.append(fb_pixel_id.strip())
        if fb_token     is not None: fields.append("fb_token=%s");      vals.append(fb_token.strip())
        if tt_pixel_id  is not None: fields.append("tt_pixel_id=%s");   vals.append(tt_pixel_id.strip())
        if tt_token     is not None: fields.append("tt_token=%s");      vals.append(tt_token.strip())
        if utm_campaigns         is not None: fields.append("utm_campaigns=%s");         vals.append(utm_campaigns.strip())
        if tt_test_event_code is not None: fields.append("tt_test_event_code=%s"); vals.append(tt_test_event_code or "")
        if traffic_source is not None:
            fields.append("traffic_source=%s"); vals.append(traffic_source or "")
        if test_event_code  is not None: fields.append("test_event_code=%s"); vals.append(test_event_code.strip())
        if not fields: return
        vals.append(project_id)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE projects SET {', '.join(fields)} WHERE id=%s", vals)
            conn.commit()

    def delete_project(self, project_id: int):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM projects WHERE id=%s", (project_id,))
            conn.commit()

    def get_project_by_utm(self, utm_campaign: str) -> dict | None:
        """Найти проект по utm_campaign — ищем совпадение в comma-separated utm_campaigns."""
        if not utm_campaign:
            return None
        projects = self.get_projects()
        utm_lower = utm_campaign.strip().lower()
        for p in projects:
            campaigns = [c.strip().lower() for c in (p.get("utm_campaigns") or "").split(",") if c.strip()]
            if utm_lower in campaigns:
                return p
        return None

    def set_landing_project(self, landing_id: int, project_id: int | None):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE landings SET project_id=%s WHERE id=%s", (project_id, landing_id))
            conn.commit()

    # ── Поиск по диалогам ─────────────────────────────────────────────────────

    def search_wa_conversations(self, query: str, status: str = None) -> list:
        """Поиск по WA диалогам: имя, номер телефона, UTM кампания"""
        # Убираем + если пользователь ввёл +номер
        clean_query = query.lstrip("+").strip()
        q = f"%{clean_query.lower()}%"
        with self._conn() as conn:
            with conn.cursor() as cur:
                status_clause = "AND status=%s" if status else ""
                params = [q, q, q, q]
                if status:
                    params.append(status)
                cur.execute(f"""
                    SELECT * FROM wa_conversations
                    WHERE (
                        LOWER(visitor_name) LIKE %s OR
                        LOWER(wa_number)    LIKE %s OR
                        LOWER(utm_campaign) LIKE %s OR
                        LOWER(last_message) LIKE %s
                    ) {status_clause}
                    ORDER BY COALESCE(last_message_at, created_at) DESC
                    LIMIT 50
                """, params)
                return [dict(r) for r in cur.fetchall()]

    def search_tg_account_conversations(self, query: str, status: str = None) -> list:
        """Поиск по TG Account диалогам: имя, username, UTM кампания"""
        # Убираем @ если пользователь ввёл @username
        clean_query = query.lstrip("@").strip()
        q = f"%{clean_query.lower()}%"
        with self._conn() as conn:
            with conn.cursor() as cur:
                status_clause = "AND status=%s" if status else ""
                params = [q, q, q, q]
                if status:
                    params.append(status)
                cur.execute(f"""
                    SELECT * FROM tg_account_conversations
                    WHERE (
                        LOWER(visitor_name)  LIKE %s OR
                        LOWER(username)      LIKE %s OR
                        LOWER(utm_campaign)  LIKE %s OR
                        LOWER(last_message)  LIKE %s
                    ) {status_clause}
                    ORDER BY COALESCE(last_message_at, created_at) DESC
                    LIMIT 50
                """, params)
                return [dict(r) for r in cur.fetchall()]

    # ── Scripts ───────────────────────────────────────────────────────────────
    def get_scripts(self, project_id: int) -> list:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM scripts WHERE project_id=%s ORDER BY category, sort_order, id",
                    (project_id,)
                )
                return [dict(r) for r in cur.fetchall()]

    def get_script(self, script_id: int) -> dict | None:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM scripts WHERE id=%s", (script_id,))
                r = cur.fetchone(); return dict(r) if r else None

    def create_script(self, project_id: int, category: str, title: str, body: str, sort_order: int = 0) -> int:
        from datetime import datetime
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO scripts (project_id, category, title, body, sort_order, created_at) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                    (project_id, category.strip(), title.strip(), body, sort_order, datetime.utcnow().isoformat())
                )
                new_id = cur.fetchone()["id"]
            conn.commit()
            return new_id

    def update_script(self, script_id: int, category: str, title: str, body: str, sort_order: int = 0):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE scripts SET category=%s, title=%s, body=%s, sort_order=%s WHERE id=%s",
                    (category.strip(), title.strip(), body, sort_order, script_id)
                )
            conn.commit()

    def delete_script(self, script_id: int):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM scripts WHERE id=%s", (script_id,))
            conn.commit()

    def get_script_categories(self, project_id: int) -> list:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT category FROM scripts WHERE project_id=%s ORDER BY category",
                    (project_id,)
                )
                return [r["category"] for r in cur.fetchall()]

    # ══════════════════════════════════════════════════════════════════════════
    # АВТОПОСТИНГ
    # ══════════════════════════════════════════════════════════════════════════

    def _ensure_autopost_tables(self):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS autopost_campaigns (
                        id              SERIAL PRIMARY KEY,
                        name            TEXT NOT NULL,
                        status          TEXT DEFAULT 'paused',
                        bot_token       TEXT DEFAULT '',
                        channel_id      TEXT DEFAULT '',
                        timezone        TEXT DEFAULT 'US/Eastern',
                        windows         TEXT DEFAULT '[[8,10],[18,21]]',
                        windows_label   TEXT DEFAULT '8-10, 18-21',
                        max_posts       INTEGER DEFAULT 2,
                        delay_min       INTEGER DEFAULT 5,
                        delay_max       INTEGER DEFAULT 15,
                        post_mode       TEXT DEFAULT 'loop',
                        current_index   INTEGER DEFAULT 1,
                        created_at      TEXT NOT NULL
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS autopost_posts (
                        id              SERIAL PRIMARY KEY,
                        campaign_id     INTEGER NOT NULL,
                        position        INTEGER DEFAULT 1,
                        caption         TEXT DEFAULT '',
                        media_url       TEXT DEFAULT '',
                        media_type      TEXT DEFAULT '',
                        sent_count      INTEGER DEFAULT 0,
                        last_sent_at    TEXT,
                        created_at      TEXT NOT NULL
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS autopost_log (
                        id              SERIAL PRIMARY KEY,
                        campaign_id     INTEGER NOT NULL,
                        post_id         INTEGER,
                        window_start    INTEGER,
                        window_end      INTEGER,
                        sent_at         TEXT NOT NULL,
                        status          TEXT DEFAULT 'ok',
                        error           TEXT DEFAULT ''
                    )
                """)
            conn.commit()

    def get_autopost_campaigns(self, status=None):
        self._ensure_autopost_tables()
        with self._conn() as conn:
            with conn.cursor() as cur:
                if status:
                    cur.execute("SELECT * FROM autopost_campaigns WHERE status=%s ORDER BY id", (status,))
                else:
                    cur.execute("SELECT * FROM autopost_campaigns ORDER BY id")
                return [dict(r) for r in cur.fetchall()]

    def get_autopost_campaign(self, campaign_id: int):
        self._ensure_autopost_tables()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM autopost_campaigns WHERE id=%s", (campaign_id,))
                r = cur.fetchone()
                return dict(r) if r else None

    def create_autopost_campaign(self, name: str, timezone: str = "US/Eastern") -> int:
        self._ensure_autopost_tables()
        from datetime import datetime
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO autopost_campaigns (name, timezone, created_at) VALUES (%s,%s,%s) RETURNING id",
                    (name, timezone, datetime.utcnow().isoformat())
                )
                return cur.fetchone()["id"]
            conn.commit()

    def update_autopost_campaign(self, campaign_id: int, **kwargs):
        allowed = ["bot_token","channel_id","timezone","windows","windows_label",
                   "max_posts","delay_min","delay_max","post_mode","status"]
        fields, vals = [], []
        for k, v in kwargs.items():
            if k in allowed:
                fields.append(f"{k}=%s"); vals.append(v)
        if not fields: return
        vals.append(campaign_id)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE autopost_campaigns SET {', '.join(fields)} WHERE id=%s", vals)
            conn.commit()

    def set_autopost_status(self, campaign_id: int, status: str):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE autopost_campaigns SET status=%s WHERE id=%s", (status, campaign_id))
            conn.commit()

    def delete_autopost_campaign(self, campaign_id: int):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM autopost_posts WHERE campaign_id=%s", (campaign_id,))
                cur.execute("DELETE FROM autopost_log WHERE campaign_id=%s", (campaign_id,))
                cur.execute("DELETE FROM autopost_campaigns WHERE id=%s", (campaign_id,))
            conn.commit()

    def get_autopost_posts(self, campaign_id: int):
        self._ensure_autopost_tables()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM autopost_posts WHERE campaign_id=%s ORDER BY position", (campaign_id,))
                return [dict(r) for r in cur.fetchall()]

    def get_autopost_post(self, post_id: int):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM autopost_posts WHERE id=%s", (post_id,))
                r = cur.fetchone(); return dict(r) if r else None

    def get_autopost_posts_count(self, campaign_id: int) -> int:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) as c FROM autopost_posts WHERE campaign_id=%s", (campaign_id,))
                return cur.fetchone()["c"]

    def get_autopost_sent_count(self, campaign_id: int) -> int:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COALESCE(SUM(sent_count),0) as c FROM autopost_posts WHERE campaign_id=%s", (campaign_id,))
                return cur.fetchone()["c"]

    def add_autopost_post(self, campaign_id: int, caption: str, position: int,
                          media_url: str = None, media_type: str = None):
        from datetime import datetime
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO autopost_posts (campaign_id, position, caption, media_url, media_type, created_at) VALUES (%s,%s,%s,%s,%s,%s)",
                    (campaign_id, position, caption, media_url or "", media_type or "", datetime.utcnow().isoformat())
                )
            conn.commit()

    def delete_autopost_post(self, post_id: int):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM autopost_posts WHERE id=%s", (post_id,))
            conn.commit()

    def get_autopost_next_index(self, campaign_id: int) -> int:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_index FROM autopost_campaigns WHERE id=%s", (campaign_id,))
                r = cur.fetchone()
                return r["current_index"] if r else 1

    def get_autopost_next_post(self, campaign_id: int):
        idx = self.get_autopost_next_index(campaign_id)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM autopost_posts WHERE campaign_id=%s AND position>=%s ORDER BY position LIMIT 1",
                    (campaign_id, idx)
                )
                r = cur.fetchone()
                return dict(r) if r else None

    def advance_autopost_index(self, campaign_id: int):
        post = self.get_autopost_next_post(campaign_id)
        if post:
            next_pos = post["position"] + 1
            with self._conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE autopost_campaigns SET current_index=%s WHERE id=%s", (next_pos, campaign_id))
                conn.commit()

    def reset_autopost_index(self, campaign_id: int):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE autopost_campaigns SET current_index=1 WHERE id=%s", (campaign_id,))
            conn.commit()

    def mark_autopost_sent(self, post_id: int):
        from datetime import datetime
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE autopost_posts SET sent_count=sent_count+1, last_sent_at=%s WHERE id=%s",
                    (datetime.utcnow().isoformat(), post_id)
                )
            conn.commit()

    def get_autopost_window_count(self, campaign_id: int, window: tuple) -> int:
        """Сколько постов отправлено в текущем окне сегодня"""
        from datetime import datetime
        today = datetime.utcnow().date().isoformat()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT COUNT(*) as c FROM autopost_log
                       WHERE campaign_id=%s AND window_start=%s AND window_end=%s
                       AND sent_at>=%s AND status='ok'""",
                    (campaign_id, window[0], window[1], today)
                )
                return cur.fetchone()["c"]

    def log_autopost_window(self, campaign_id: int, window: tuple):
        from datetime import datetime
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO autopost_log (campaign_id, window_start, window_end, sent_at) VALUES (%s,%s,%s,%s)",
                    (campaign_id, window[0], window[1], datetime.utcnow().isoformat())
                )
            conn.commit()

    def reset_autopost_window(self, campaign_id: int):
        """Сброс счётчика окна — вызывается когда окно неактивно"""
        pass  # счётчик берётся из лога по дате — ничего сбрасывать не нужно

    # ── Медиатека автопостинга ─────────────────────────────────────────────────
    def _ensure_media_library(self):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS autopost_media (
                        id          SERIAL PRIMARY KEY,
                        name        TEXT DEFAULT '',
                        url         TEXT NOT NULL,
                        media_type  TEXT DEFAULT 'image',
                        size_bytes  INTEGER DEFAULT 0,
                        created_at  TEXT NOT NULL
                    )
                """)
            conn.commit()

    def get_autopost_media(self) -> list:
        self._ensure_media_library()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM autopost_media ORDER BY created_at DESC")
                return [dict(r) for r in cur.fetchall()]

    def add_autopost_media(self, name: str, url: str, media_type: str = "image", size_bytes: int = 0) -> int:
        self._ensure_media_library()
        from datetime import datetime
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO autopost_media (name, url, media_type, size_bytes, created_at) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                    (name, url, media_type, size_bytes, datetime.utcnow().isoformat())
                )
                return cur.fetchone()["id"]
            conn.commit()

    def delete_autopost_media(self, media_id: int):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM autopost_media WHERE id=%s", (media_id,))
            conn.commit()

    def update_autopost_post(self, post_id: int, caption: str = None,
                              media_url: str = None, media_type: str = None):
        fields, vals = [], []
        if caption is not None:   fields.append("caption=%s");    vals.append(caption)
        if media_url is not None: fields.append("media_url=%s");  vals.append(media_url)
        if media_type is not None: fields.append("media_type=%s"); vals.append(media_type)
        if not fields: return
        vals.append(post_id)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE autopost_posts SET {', '.join(fields)} WHERE id=%s", vals)
            conn.commit()

    def reorder_autopost_posts(self, campaign_id: int, post_ids: list):
        """Обновляем position по новому порядку"""
        with self._conn() as conn:
            with conn.cursor() as cur:
                for i, pid in enumerate(post_ids, 1):
                    cur.execute("UPDATE autopost_posts SET position=%s WHERE id=%s AND campaign_id=%s",
                                (i, pid, campaign_id))
            conn.commit()

    def get_autopost_log(self, campaign_id: int, limit: int = 10) -> list:
        self._ensure_autopost_tables()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM autopost_log WHERE campaign_id=%s ORDER BY sent_at DESC LIMIT %s",
                    (campaign_id, limit)
                )
                return [dict(r) for r in cur.fetchall()]

    # ── Шаблоны постов ────────────────────────────────────────────────────────
    def _ensure_post_templates(self):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS autopost_templates (
                        id          SERIAL PRIMARY KEY,
                        name        TEXT NOT NULL,
                        caption     TEXT DEFAULT '',
                        media_url   TEXT DEFAULT '',
                        media_type  TEXT DEFAULT '',
                        tags        TEXT DEFAULT '',
                        created_at  TEXT NOT NULL
                    )
                """)
            conn.commit()

    def get_autopost_templates(self, tag: str = None) -> list:
        self._ensure_post_templates()
        with self._conn() as conn:
            with conn.cursor() as cur:
                if tag:
                    cur.execute("SELECT * FROM autopost_templates WHERE tags LIKE %s ORDER BY created_at DESC", (f"%{tag}%",))
                else:
                    cur.execute("SELECT * FROM autopost_templates ORDER BY created_at DESC")
                return [dict(r) for r in cur.fetchall()]

    def get_autopost_template(self, tpl_id: int):
        self._ensure_post_templates()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM autopost_templates WHERE id=%s", (tpl_id,))
                r = cur.fetchone(); return dict(r) if r else None

    def save_autopost_template(self, name: str, caption: str, media_url: str = "",
                                media_type: str = "", tags: str = "") -> int:
        self._ensure_post_templates()
        from datetime import datetime
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO autopost_templates (name, caption, media_url, media_type, tags, created_at) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                    (name.strip(), caption.strip(), media_url, media_type, tags.strip(), datetime.utcnow().isoformat())
                )
                return cur.fetchone()["id"]
            conn.commit()

    def update_autopost_template(self, tpl_id: int, name: str = None, caption: str = None,
                                  media_url: str = None, media_type: str = None, tags: str = None):
        fields, vals = [], []
        if name is not None:       fields.append("name=%s");       vals.append(name.strip())
        if caption is not None:    fields.append("caption=%s");    vals.append(caption.strip())
        if media_url is not None:  fields.append("media_url=%s");  vals.append(media_url)
        if media_type is not None: fields.append("media_type=%s"); vals.append(media_type)
        if tags is not None:       fields.append("tags=%s");       vals.append(tags.strip())
        if not fields: return
        vals.append(tpl_id)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE autopost_templates SET {', '.join(fields)} WHERE id=%s", vals)
            conn.commit()

    def delete_autopost_template(self, tpl_id: int):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM autopost_templates WHERE id=%s", (tpl_id,))
            conn.commit()

    # ── Ручное создание сотрудника ────────────────────────────────────────────
    def create_staff_manual(self, name: str, phone: str = "", email: str = "",
                             position: str = "", status: str = "new",
                             notes: str = "", tags: str = "",
                             username: str = "", manager_name: str = "",
                             city: str = "", created_at_override: str = None) -> int:
        from datetime import datetime
        # Если передана дата вручную — используем её (формат YYYY-MM-DD)
        if created_at_override:
            try:
                _dt = datetime.strptime(created_at_override[:10], "%Y-%m-%d")
                created_at = _dt.isoformat()
            except: created_at = datetime.utcnow().isoformat()
        else:
            created_at = datetime.utcnow().isoformat()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO staff (name, phone, email, position, status, notes, tags,
                       username, manager_name, city, created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (name.strip(), phone.strip(), email.strip(), position.strip(),
                     status, notes.strip(), tags.strip(),
                     username.strip(), manager_name.strip(), city.strip(), created_at)
                )
                return cur.fetchone()["id"]
            conn.commit()

    def update_staff_created_at(self, staff_id: int, date_str: str):
        """Обновляет дату добавления карточки"""
        from datetime import datetime
        try:
            _dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
            created_at = _dt.isoformat()
        except: return
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE staff SET created_at=%s WHERE id=%s", (created_at, staff_id))
            conn.commit()

    def get_staff_by_month(self, year: int, month: int) -> list:
        """Сотрудники добавленные в указанный месяц"""
        prefix = f"{year:04d}-{month:02d}"
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM staff WHERE created_at LIKE %s ORDER BY created_at",
                    (f"{prefix}%",)
                )
                return [dict(r) for r in cur.fetchall()]

    # ── Бонусные ставки ───────────────────────────────────────────────────────
    def _ensure_bonus_rates(self):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS bonus_rates (
                        id           SERIAL PRIMARY KEY,
                        status       TEXT NOT NULL UNIQUE,
                        rate         NUMERIC(10,2) DEFAULT 0,
                        manager_rate NUMERIC(10,2) DEFAULT 0,
                        label        TEXT DEFAULT '',
                        updated_at   TEXT NOT NULL
                    )
                """)
                # migration для старых БД
                try:
                    cur.execute("ALTER TABLE bonus_rates ADD COLUMN IF NOT EXISTS manager_rate NUMERIC(10,2) DEFAULT 0")
                except Exception:
                    pass
            conn.commit()

    def get_bonus_rates(self) -> dict:
        """Возвращает {status: {rate, label}}"""
        self._ensure_bonus_rates()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status, rate, label FROM bonus_rates")
                return {r["status"]: {"rate": float(r["rate"]), "label": r["label"]} for r in cur.fetchall()}

    def set_bonus_rate(self, status: str, rate: float, label: str = ""):
        self._ensure_bonus_rates()
        from datetime import datetime
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO bonus_rates (status, rate, label, updated_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (status) DO UPDATE
                    SET rate=%s, label=%s, updated_at=%s
                """, (status, rate, label, now, rate, label, now))
            conn.commit()

    def get_staff_filtered(self, date_from: str = None, date_to: str = None,
                            status: str = None, manager: str = None) -> list:
        """Фильтрация сотрудников по диапазону дат и статусу"""
        conditions = []
        params = []
        if date_from:
            conditions.append("created_at >= %s")
            params.append(date_from)
        if date_to:
            # До конца дня
            conditions.append("created_at <= %s")
            params.append(date_to + "T23:59:59")
        if status:
            conditions.append("status = %s")
            params.append(status)
        if manager:
            conditions.append("manager_name = %s")
            params.append(manager)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM staff {where} ORDER BY created_at DESC", params)
                return [dict(r) for r in cur.fetchall()]

    def get_status_at_date(self, staff_id: int, date_to: str) -> str | None:
        """Возвращает статус сотрудника на конец указанной даты по истории staff_notes.
        Ищет последнюю запись type='status' до date_to включительно.
        Если истории нет — возвращает None (caller использует текущий статус)."""
        deadline = (date_to + "T23:59:59") if date_to and "T" not in date_to else (date_to or "")
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT text FROM staff_notes "
                    "WHERE staff_id=%s AND type='status' AND created_at <= %s "
                    "ORDER BY created_at DESC LIMIT 1",
                    (staff_id, deadline)
                )
                row = cur.fetchone()
                if not row:
                    return None
                # Формат текста: "Статус: old → new"
                text = row["text"] or ""
                if "→" in text:
                    return text.split("→")[-1].strip()
                return None

    def get_staff_bonus_summary(self, date_from: str = None, date_to: str = None,
                                 manager: str = None) -> dict:
        """Итоговая статистика бонусов за период.
        Статус берётся из истории staff_notes на конец периода (date_to).
        Если истории нет — используется текущий статус сотрудника."""
        staff = self.get_staff_filtered(date_from=date_from, date_to=date_to, manager=manager)
        rates = self.get_bonus_rates()
        summary = {}
        total_amount = 0.0
        total_count = len(staff)
        for s in staff:
            # Пробуем взять статус из истории на конец периода
            hist_status = self.get_status_at_date(s["id"], date_to) if date_to else None
            st = hist_status or s.get("status") or "new"
            _rate = rates.get(st, {}).get("rate", 0)
            if st not in summary:
                summary[st] = {"count": 0, "rate": _rate, "amount": 0}
            summary[st]["count"] += 1
            summary[st]["amount"] += _rate
            total_amount += _rate
        return {"by_status": summary, "total_count": total_count, "total_amount": total_amount}

    # ── Staff Notes (история касаний) ─────────────────────────────────────────

    def add_staff_note(self, staff_id: int, manager_name: str, note_type: str,
                       text: str, remind_at: str = None) -> dict:
        from datetime import datetime
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO staff_notes (staff_id, manager_name, type, text, remind_at, created_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s) RETURNING *",
                    (staff_id, manager_name, note_type, text, remind_at or None, now)
                )
                row = dict(cur.fetchone())
            conn.commit()
        return row

    def get_staff_notes(self, staff_id: int) -> list:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM staff_notes WHERE staff_id=%s ORDER BY created_at DESC",
                    (staff_id,)
                )
                return [dict(r) for r in cur.fetchall()]

    def delete_staff_note(self, note_id: int, staff_id: int) -> bool:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM staff_notes WHERE id=%s AND staff_id=%s",
                    (note_id, staff_id)
                )
                deleted = cur.rowcount > 0
            conn.commit()
        return deleted

    def get_staff_last_contact(self, staff_id: int):
        """Дата последнего касания"""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT created_at FROM staff_notes WHERE staff_id=%s ORDER BY created_at DESC LIMIT 1",
                    (staff_id,)
                )
                row = cur.fetchone()
                return row["created_at"] if row else None

    def get_staff_reminders_due(self) -> list:
        """Сотрудники у кого remind_at <= сегодня"""
        from datetime import date
        today = date.today().isoformat()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT sn.*, s.name as staff_name, s.id as staff_id "
                    "FROM staff_notes sn JOIN staff s ON s.id = sn.staff_id "
                    "WHERE sn.remind_at IS NOT NULL AND sn.remind_at <= %s "
                    "ORDER BY sn.remind_at ASC",
                    (today,)
                )
                return [dict(r) for r in cur.fetchall()]

    def get_staff_no_contact_days(self, staff_id: int) -> int:
        """Сколько дней прошло с последнего касания"""
        from datetime import datetime
        last = self.get_staff_last_contact(staff_id)
        if not last:
            return -1
        try:
            last_dt = datetime.fromisoformat(last[:19])
            return (datetime.utcnow() - last_dt).days
        except Exception:
            return -1
