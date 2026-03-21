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
                    "ALTER TABLE campaigns ALTER COLUMN channel_id DROP NOT NULL",
                    "ALTER TABLE campaigns ALTER COLUMN invite_link DROP NOT NULL",
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
    def get_setting(self, key, default=""):
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
                   user_agent=None, ip_address=None):
        click_id = secrets.token_urlsafe(12)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO click_tracking
                    (click_id,fbclid,fbp,utm_source,utm_medium,utm_campaign,utm_content,utm_term,
                     referrer,target_type,target_id,user_agent,ip_address,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
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

    # ── Staff Clicks (HR landing UTM tracking) ────────────────────────────────
    def save_staff_click(self, ref_id, target_url, target_type="wa", landing_slug="",
                         fbclid=None, fbp=None, fbc=None, utm_source=None, utm_medium=None,
                         utm_campaign=None, utm_content=None, utm_term=None):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO staff_clicks
                    (ref_id,target_url,target_type,landing_slug,fbclid,fbp,fbc,
                     utm_source,utm_medium,utm_campaign,utm_content,utm_term,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (ref_id) DO NOTHING""",
                    (ref_id, target_url, target_type, landing_slug, fbclid, fbp, fbc,
                     utm_source, utm_medium, utm_campaign, utm_content, utm_term,
                     datetime.utcnow().isoformat()))
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

    def get_staff_click_recent_any(self, minutes: int = 30):
        """Ищет любой последний неиспользованный клик за последние N минут"""
        from datetime import timedelta
        cutoff = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT * FROM staff_clicks
                    WHERE used=0 AND created_at>=%s
                    ORDER BY created_at DESC LIMIT 1""",
                    (cutoff,))
                r = cur.fetchone(); return dict(r) if r else None

    def mark_staff_click_used(self, ref_id):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE staff_clicks SET used=1 WHERE ref_id=%s", (ref_id,))
            conn.commit()

    def apply_utm_to_wa_conv(self, conv_id, fbclid=None, fbp=None, fbc=None, utm_source=None,
                              utm_medium=None, utm_campaign=None, utm_content=None, utm_term=None):
        """Применяет UTM к существующему WA диалогу (если ещё не заполнен)"""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE wa_conversations
                    SET fbclid=%s, fbp=%s, fbc=%s, utm_source=%s, utm_medium=%s,
                        utm_campaign=%s, utm_content=%s, utm_term=%s
                    WHERE id=%s AND (fbclid IS NULL OR fbclid='')""",
                    (fbclid, fbp, fbc, utm_source, utm_medium, utm_campaign,
                     utm_content, utm_term, conv_id))
            conn.commit()

    def apply_utm_to_tg_conv(self, conv_id, fbclid=None, fbp=None, fbc=None, utm_source=None,
                              utm_medium=None, utm_campaign=None, utm_content=None, utm_term=None):
        """Применяет UTM к существующему TG аккаунт диалогу"""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE tg_account_conversations
                    SET fbclid=%s, fbp=%s, fbc=%s, utm_source=%s, utm_medium=%s,
                        utm_campaign=%s, utm_content=%s, utm_term=%s
                    WHERE id=%s AND (fbclid IS NULL OR fbclid='')""",
                    (fbclid, fbp, fbc, utm_source, utm_medium, utm_campaign,
                     utm_content, utm_term, conv_id))
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

    def update_staff(self, staff_id, name, phone, email, position, status, notes, tags, manager_name=None):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE staff SET name=%s,phone=%s,email=%s,position=%s,status=%s,notes=%s,tags=%s,manager_name=%s WHERE id=%s",
                            (name,phone,email,position,status,notes,tags,manager_name or "",staff_id))
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

    def add_landing_contact(self, landing_id, ctype, label, url):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COALESCE(MAX(position),0)+1 as p FROM landing_contacts WHERE landing_id=%s", (landing_id,))
                pos = cur.fetchone()["p"]
                cur.execute("INSERT INTO landing_contacts (landing_id,type,label,url,position) VALUES (%s,%s,%s,%s,%s)",
                            (landing_id,ctype,label,url,pos))
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
                cur.execute("DELETE FROM staff WHERE wa_conv_id=%s", (conv_id,))
                cur.execute("DELETE FROM wa_conversations WHERE id=%s", (conv_id,))
            conn.commit()
        _cache.invalidate_prefix('wa_convs:')

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
                    COALESCE(ch.name, j.channel_id, 'Неизвестно') as channel_name,
                    j.channel_id,
                    COUNT(*) as joins,
                    SUM(CASE WHEN j.campaign_name!='organic' THEN 1 ELSE 0 END) as from_ads,
                    MIN(j.joined_at) as first_join,
                    MAX(j.joined_at) as last_join
                    FROM joins j
                    LEFT JOIN channels ch ON ch.channel_id = j.channel_id
                    {where} GROUP BY j.channel_id, ch.name ORDER BY joins DESC""", params)
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
                    COALESCE(ch.name, j.channel_id) as channel_name,
                    ct.utm_source, ct.utm_medium, ct.utm_campaign as utm_campaign_tag,
                    ct.fbclid, ct.fbp
                    FROM joins j
                    LEFT JOIN channels ch ON ch.channel_id = j.channel_id
                    LEFT JOIN click_tracking ct ON ct.click_id = j.click_id
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
                                      utm_medium=None, utm_campaign=None, utm_content=None, utm_term=None):
        self._init_tg_account_tables()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE tg_account_conversations
                    SET fbclid=%s, fbp=%s, utm_source=%s, utm_medium=%s,
                        utm_campaign=%s, utm_content=%s, utm_term=%s
                    WHERE id=%s AND (fbclid IS NULL OR fbclid='')""",
                    (fbclid, fbp, utm_source, utm_medium, utm_campaign, utm_content, utm_term, conv_id))
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
                cur.execute("DELETE FROM tg_account_conversations WHERE id=%s", (conv_id,))
            conn.commit()
        _cache.invalidate_prefix('tga_convs:')

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
                       utm_campaigns: str = None, test_event_code: str = None):
        fields, vals = [], []
        if name         is not None: fields.append("name=%s");          vals.append(name.strip())
        if fb_pixel_id  is not None: fields.append("fb_pixel_id=%s");   vals.append(fb_pixel_id.strip())
        if fb_token     is not None: fields.append("fb_token=%s");      vals.append(fb_token.strip())
        if tt_pixel_id  is not None: fields.append("tt_pixel_id=%s");   vals.append(tt_pixel_id.strip())
        if tt_token     is not None: fields.append("tt_token=%s");      vals.append(tt_token.strip())
        if utm_campaigns    is not None: fields.append("utm_campaigns=%s");    vals.append(utm_campaigns.strip())
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
