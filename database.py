import os
import secrets
import hashlib
from datetime import datetime
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

DATABASE_URL = os.getenv("DATABASE_URL", "")

# Railway иногда даёт URL с postgres:// вместо postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_pool: ThreadedConnectionPool | None = None


def _get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None or _pool.closed:
        _pool = ThreadedConnectionPool(1, 10, DATABASE_URL)
    return _pool


@contextmanager
def _get_conn():
    pool = _get_pool()
    conn = pool.getconn()
    try:
        conn.autocommit = False
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def _row(cursor, row) -> dict:
    """Конвертирует строку psycopg2 в dict."""
    if row is None:
        return None
    cols = [desc[0] for desc in cursor.description]
    return dict(zip(cols, row))


def _rows(cursor) -> list[dict]:
    cols = [desc[0] for desc in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


# ══════════════════════════════════════════════════════════════════════════════

class Database:
    def __init__(self):
        self._init_db()

    def _init_db(self):
        with _get_conn() as conn:
            cur = conn.cursor()

            cur.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id         SERIAL PRIMARY KEY,
                    username   TEXT NOT NULL UNIQUE,
                    password   TEXT NOT NULL,
                    role       TEXT NOT NULL DEFAULT 'manager',
                    created_at TEXT NOT NULL
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS channels (
                    id         SERIAL PRIMARY KEY,
                    name       TEXT NOT NULL,
                    channel_id TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS campaigns (
                    id          SERIAL PRIMARY KEY,
                    name        TEXT NOT NULL,
                    channel_id  TEXT NOT NULL,
                    invite_link TEXT NOT NULL UNIQUE,
                    created_at  TEXT NOT NULL
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS joins (
                    id            SERIAL PRIMARY KEY,
                    user_id       BIGINT NOT NULL,
                    channel_id    TEXT,
                    invite_link   TEXT,
                    campaign_name TEXT NOT NULL DEFAULT 'organic',
                    click_id      TEXT,
                    joined_at     TEXT NOT NULL
                )
            """)

            cur.execute("""
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
                )
            """)

            cur.execute("""
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
                )
            """)

            cur.execute("""
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
                    created_at      TEXT NOT NULL
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id              SERIAL PRIMARY KEY,
                    conversation_id INTEGER NOT NULL,
                    tg_chat_id      TEXT NOT NULL,
                    sender_type     TEXT NOT NULL,
                    content         TEXT,
                    media_url       TEXT,
                    media_type      TEXT,
                    tg_message_id   BIGINT,
                    read_by_manager INTEGER DEFAULT 0,
                    created_at      TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                )
            """)

            cur.execute("""
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
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS landing_links (
                    id       SERIAL PRIMARY KEY,
                    title    TEXT NOT NULL,
                    tg_link  TEXT NOT NULL,
                    emoji    TEXT DEFAULT '📢',
                    position INTEGER DEFAULT 0
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS message_flows (
                    id         SERIAL PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    bot_type   TEXT NOT NULL DEFAULT 'tracker',
                    step       INTEGER NOT NULL DEFAULT 0,
                    delay_min  INTEGER NOT NULL DEFAULT 0,
                    message    TEXT NOT NULL,
                    active     INTEGER NOT NULL DEFAULT 1
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS flow_log (
                    id         SERIAL PRIMARY KEY,
                    user_id    BIGINT NOT NULL,
                    channel_id TEXT NOT NULL,
                    step       INTEGER NOT NULL,
                    sent_at    TEXT NOT NULL
                )
            """)

            cur.execute("""
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
                    created_at      TEXT NOT NULL
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS wa_messages (
                    id              SERIAL PRIMARY KEY,
                    conversation_id INTEGER NOT NULL,
                    wa_chat_id      TEXT NOT NULL,
                    sender_type     TEXT NOT NULL,
                    content         TEXT,
                    media_url       TEXT,
                    media_type      TEXT,
                    read_by_manager INTEGER DEFAULT 0,
                    created_at      TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES wa_conversations(id)
                )
            """)

            # Таблица для лендингов сотрудников (TG + WA кнопки)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS staff_landing_links (
                    id         SERIAL PRIMARY KEY,
                    title      TEXT NOT NULL,
                    link_type  TEXT NOT NULL DEFAULT 'tg',
                    url        TEXT NOT NULL,
                    emoji      TEXT DEFAULT '📢',
                    position   INTEGER DEFAULT 0
                )
            """)

            # Дефолтный admin
            cur.execute("SELECT COUNT(*) FROM users")
            count = cur.fetchone()[0]
            if count == 0:
                pwd = hashlib.sha256("admin123".encode()).hexdigest()
                cur.execute(
                    "INSERT INTO users (username,password,role,created_at) VALUES (%s,%s,%s,%s)",
                    ("admin", pwd, "admin", datetime.utcnow().isoformat())
                )

    # ── Settings ──────────────────────────────────────────────────────────────

    def get_setting(self, key: str, default: str = "") -> str:
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM settings WHERE key=%s", (key,))
            row = cur.fetchone()
            return row[0] if row else default

    def set_setting(self, key: str, value: str):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO settings (key,value) VALUES (%s,%s)
                ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value
            """, (key, value))

    # ── Users ─────────────────────────────────────────────────────────────────

    def get_user(self, username: str) -> dict | None:
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE username=%s", (username,))
            return _row(cur, cur.fetchone())

    def get_users(self):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id,username,role,created_at FROM users ORDER BY created_at")
            return _rows(cur)

    def create_user(self, username: str, password: str, role: str = "manager"):
        pwd = hashlib.sha256(password.encode()).hexdigest()
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users (username,password,role,created_at) VALUES (%s,%s,%s,%s)",
                (username, pwd, role, datetime.utcnow().isoformat())
            )

    def delete_user(self, user_id: int):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM users WHERE id=%s", (user_id,))

    def verify_user(self, username: str, password: str) -> dict | None:
        pwd = hashlib.sha256(password.encode()).hexdigest()
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE username=%s AND password=%s", (username, pwd))
            return _row(cur, cur.fetchone())

    # ── Channels ──────────────────────────────────────────────────────────────

    def add_channel(self, name: str, channel_id: str):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO channels (name,channel_id,created_at) VALUES (%s,%s,%s)
                ON CONFLICT (channel_id) DO NOTHING
            """, (name, channel_id, datetime.utcnow().isoformat()))

    def get_channels(self):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT c.*, COUNT(j.id) as total_joins
                FROM channels c LEFT JOIN joins j ON j.channel_id=c.channel_id
                GROUP BY c.id ORDER BY c.created_at DESC
            """)
            return _rows(cur)

    def delete_channel(self, channel_id: str):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM channels WHERE channel_id=%s", (channel_id,))

    def get_channel_ids(self):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT channel_id FROM channels")
            return [r[0] for r in cur.fetchall()]

    # ── Campaigns ─────────────────────────────────────────────────────────────

    def save_campaign(self, name: str, channel_id: str, invite_link: str):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO campaigns (name,channel_id,invite_link,created_at) VALUES (%s,%s,%s,%s)
                ON CONFLICT (invite_link) DO NOTHING
            """, (name, channel_id, invite_link, datetime.utcnow().isoformat()))

    def get_campaign_by_link(self, invite_link: str | None):
        if not invite_link: return None
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM campaigns WHERE invite_link=%s", (invite_link,))
            return _row(cur, cur.fetchone())

    def get_campaigns(self, channel_id: str | None = None):
        with _get_conn() as conn:
            cur = conn.cursor()
            if channel_id:
                cur.execute("""
                    SELECT c.*, COUNT(j.id) AS joins FROM campaigns c
                    LEFT JOIN joins j ON j.campaign_name=c.name AND j.channel_id=c.channel_id
                    WHERE c.channel_id=%s GROUP BY c.id ORDER BY c.created_at DESC
                """, (channel_id,))
            else:
                cur.execute("""
                    SELECT c.*, COUNT(j.id) AS joins FROM campaigns c
                    LEFT JOIN joins j ON j.campaign_name=c.name AND j.channel_id=c.channel_id
                    GROUP BY c.id ORDER BY c.created_at DESC
                """)
            return _rows(cur)

    # ── Joins ─────────────────────────────────────────────────────────────────

    def log_join(self, user_id: int, channel_id: str, invite_link: str | None,
                 campaign_name: str, click_id: str | None = None) -> int:
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO joins (user_id,channel_id,invite_link,campaign_name,click_id,joined_at)
                VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
            """, (user_id, channel_id, invite_link, campaign_name, click_id,
                  datetime.utcnow().isoformat()))
            return cur.fetchone()[0]

    def get_recent_joins(self, limit: int = 50):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT j.*, c.name as channel_name
                FROM joins j LEFT JOIN channels c ON c.channel_id=j.channel_id
                ORDER BY j.joined_at DESC LIMIT %s
            """, (limit,))
            return _rows(cur)

    # ── Click Tracking ────────────────────────────────────────────────────────

    def save_click(self, fbclid=None, fbp=None, utm_source=None,
                   utm_medium=None, utm_campaign=None, utm_content=None,
                   utm_term=None, referrer=None, target_type="channel",
                   target_id=None, user_agent=None, ip_address=None) -> str:
        click_id = secrets.token_urlsafe(12)
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO click_tracking
                (click_id,fbclid,fbp,utm_source,utm_medium,utm_campaign,utm_content,utm_term,
                 referrer,target_type,target_id,user_agent,ip_address,created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (click_id, fbclid, fbp, utm_source, utm_medium, utm_campaign, utm_content,
                  utm_term, referrer, target_type, target_id, user_agent, ip_address,
                  datetime.utcnow().isoformat()))
        return click_id

    def get_click(self, click_id: str) -> dict | None:
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM click_tracking WHERE click_id=%s", (click_id,))
            return _row(cur, cur.fetchone())

    def save_utm(self, click_data: dict, conversation_id: int = None, join_id: int = None):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO utm_tracking
                (conversation_id,join_id,click_id,fbclid,fbp,utm_source,utm_medium,
                 utm_campaign,utm_content,utm_term,referrer,created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (conversation_id, join_id, click_data.get("click_id"), click_data.get("fbclid"),
                  click_data.get("fbp"), click_data.get("utm_source"), click_data.get("utm_medium"),
                  click_data.get("utm_campaign"), click_data.get("utm_content"),
                  click_data.get("utm_term"), click_data.get("referrer"),
                  datetime.utcnow().isoformat()))

    def get_utm_by_conv(self, conversation_id: int) -> dict | None:
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM utm_tracking WHERE conversation_id=%s
                ORDER BY id DESC LIMIT 1
            """, (conversation_id,))
            return _row(cur, cur.fetchone())

    def get_click_stats(self, days: int = 30):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT DATE(created_at::timestamp) as day,
                       COUNT(*) as clicks,
                       SUM(CASE WHEN fbclid IS NOT NULL THEN 1 ELSE 0 END) as with_fbclid
                FROM click_tracking
                WHERE created_at >= (NOW() - INTERVAL '%s days')::TEXT
                GROUP BY day ORDER BY day
            """, (days,))
            return _rows(cur)

    # ── Conversations ─────────────────────────────────────────────────────────

    def get_or_create_conversation(self, tg_chat_id: str, visitor_name: str,
                                   username: str | None) -> dict:
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM conversations WHERE tg_chat_id=%s", (tg_chat_id,))
            row = _row(cur, cur.fetchone())
            if row: return row
            cur.execute("""
                INSERT INTO conversations (tg_chat_id,visitor_name,username,created_at)
                VALUES (%s,%s,%s,%s) RETURNING *
            """, (tg_chat_id, visitor_name, username, datetime.utcnow().isoformat()))
            return _row(cur, cur.fetchone())

    def get_conversations(self):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT c.*,
                       u.utm_source, u.utm_campaign, u.utm_medium,
                       u.fbclid, u.utm_content
                FROM conversations c
                LEFT JOIN LATERAL (
                    SELECT utm_source, utm_campaign, utm_medium, fbclid, utm_content
                    FROM utm_tracking
                    WHERE conversation_id = c.id
                    ORDER BY id DESC LIMIT 1
                ) u ON true
                ORDER BY COALESCE(c.last_message_at, c.created_at) DESC
            """)
            return _rows(cur)

    def get_conversation(self, conv_id: int):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM conversations WHERE id=%s", (conv_id,))
            return _row(cur, cur.fetchone())

    def update_conversation_last_message(self, tg_chat_id: str, text: str,
                                          increment_unread: bool = True):
        with _get_conn() as conn:
            cur = conn.cursor()
            if increment_unread:
                cur.execute("""
                    UPDATE conversations
                    SET last_message=%s, last_message_at=%s, unread_count=unread_count+1
                    WHERE tg_chat_id=%s
                """, (text[:100], datetime.utcnow().isoformat(), tg_chat_id))
            else:
                cur.execute("""
                    UPDATE conversations SET last_message=%s, last_message_at=%s
                    WHERE tg_chat_id=%s
                """, (text[:100], datetime.utcnow().isoformat(), tg_chat_id))

    def mark_conversation_read(self, conv_id: int):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE conversations SET unread_count=0 WHERE id=%s", (conv_id,))
            cur.execute("""
                UPDATE messages SET read_by_manager=1
                WHERE conversation_id=%s AND sender_type='visitor'
            """, (conv_id,))

    def close_conversation(self, conv_id: int):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE conversations SET status='closed' WHERE id=%s", (conv_id,))

    def reopen_conversation(self, conv_id: int):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE conversations SET status='open' WHERE id=%s", (conv_id,))

    def set_conv_fb_event(self, conv_id: int, event: str):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE conversations SET fb_event_sent=%s WHERE id=%s", (event, conv_id))

    # ── Messages ──────────────────────────────────────────────────────────────

    def save_message(self, conversation_id: int, tg_chat_id: str, sender_type: str,
                     content: str, tg_message_id: int | None = None,
                     media_url: str | None = None, media_type: str | None = None):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO messages
                (conversation_id,tg_chat_id,sender_type,content,tg_message_id,
                 media_url,media_type,created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """, (conversation_id, tg_chat_id, sender_type, content, tg_message_id,
                  media_url, media_type, datetime.utcnow().isoformat()))

    def get_messages(self, conversation_id: int, limit: int = 100):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM messages WHERE conversation_id=%s
                ORDER BY created_at ASC LIMIT %s
            """, (conversation_id, limit))
            return _rows(cur)

    def get_new_messages(self, conversation_id: int, after_id: int):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM messages WHERE conversation_id=%s AND id>%s
                ORDER BY created_at ASC
            """, (conversation_id, after_id))
            return _rows(cur)

    # ── Staff ─────────────────────────────────────────────────────────────────

    def get_or_create_staff(self, tg_chat_id: str, name: str,
                             username: str | None, conv_id: int) -> dict:
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM staff WHERE tg_chat_id=%s", (tg_chat_id,))
            row = _row(cur, cur.fetchone())
            if row: return row
            cur.execute("""
                INSERT INTO staff (conversation_id,tg_chat_id,name,username,created_at)
                VALUES (%s,%s,%s,%s,%s) RETURNING *
            """, (conv_id, tg_chat_id, name, username, datetime.utcnow().isoformat()))
            return _row(cur, cur.fetchone())

    def get_staff(self, status: str | None = None):
        with _get_conn() as conn:
            cur = conn.cursor()
            if status:
                cur.execute("SELECT * FROM staff WHERE status=%s ORDER BY created_at DESC", (status,))
            else:
                cur.execute("SELECT * FROM staff ORDER BY created_at DESC")
            return _rows(cur)

    def update_staff(self, staff_id: int, name: str, phone: str, email: str,
                     position: str, status: str, notes: str, tags: str):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE staff SET name=%s,phone=%s,email=%s,position=%s,
                status=%s,notes=%s,tags=%s WHERE id=%s
            """, (name, phone, email, position, status, notes, tags, staff_id))

    def update_staff_status(self, staff_id: int, status: str):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE staff SET status=%s WHERE id=%s", (status, staff_id))

    def get_staff_by_conv(self, conv_id: int):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM staff WHERE conversation_id=%s", (conv_id,))
            return _row(cur, cur.fetchone())

    def set_staff_fb_event(self, staff_id: int, event: str):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE staff SET fb_event_sent=%s WHERE id=%s", (event, staff_id))

    def get_staff_funnel(self):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT status, COUNT(*) as cnt FROM staff GROUP BY status")
            return {r[0]: r[1] for r in cur.fetchall()}

    # ── Stats ─────────────────────────────────────────────────────────────────

    def get_stats(self):
        with _get_conn() as conn:
            cur = conn.cursor()
            def one(q, p=()):
                cur.execute(q, p)
                return cur.fetchone()[0]
            return {
                "total":         one("SELECT COUNT(*) FROM joins"),
                "from_ads":      one("SELECT COUNT(*) FROM joins WHERE campaign_name!='organic'"),
                "organic":       one("SELECT COUNT(*) FROM joins WHERE campaign_name='organic'"),
                "channels":      one("SELECT COUNT(*) FROM channels"),
                "campaigns":     one("SELECT COUNT(*) FROM campaigns"),
                "conversations": one("SELECT COUNT(*) FROM conversations"),
                "unread":        one("SELECT COALESCE(SUM(unread_count),0) FROM conversations"),
                "staff":         one("SELECT COUNT(*) FROM staff"),
                "clicks":        one("SELECT COUNT(*) FROM click_tracking"),
            }

    def get_joins_by_day(self, days: int = 30):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT DATE(joined_at::timestamp) as day,
                       COUNT(*) as cnt,
                       SUM(CASE WHEN campaign_name!='organic' THEN 1 ELSE 0 END) as from_ads
                FROM joins
                WHERE joined_at >= (NOW() - INTERVAL '%s days')::TEXT
                GROUP BY day ORDER BY day
            """, (days,))
            return _rows(cur)

    def get_campaign_stats(self):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT campaign_name, COUNT(*) as joins,
                       MIN(joined_at) as first_join, MAX(joined_at) as last_join
                FROM joins WHERE campaign_name!='organic'
                GROUP BY campaign_name ORDER BY joins DESC LIMIT 20
            """)
            return _rows(cur)

    def get_staff_by_day(self, days: int = 30):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT DATE(created_at::timestamp) as day, COUNT(*) as cnt
                FROM staff
                WHERE created_at >= (NOW() - INTERVAL '%s days')::TEXT
                GROUP BY day ORDER BY day
            """, (days,))
            return _rows(cur)

    # ── Landing (Клиенты) ─────────────────────────────────────────────────────

    def get_landing_links(self):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM landing_links ORDER BY position ASC")
            return _rows(cur)

    def add_landing_link(self, title: str, tg_link: str, emoji: str = "📢"):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COALESCE(MAX(position),0)+1 FROM landing_links")
            pos = cur.fetchone()[0]
            cur.execute("""
                INSERT INTO landing_links (title,tg_link,emoji,position) VALUES (%s,%s,%s,%s)
            """, (title, tg_link, emoji, pos))

    def delete_landing_link(self, link_id: int):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM landing_links WHERE id=%s", (link_id,))

    # ── Landing (Сотрудники) ──────────────────────────────────────────────────

    def get_staff_landing_links(self):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM staff_landing_links ORDER BY position ASC")
            return _rows(cur)

    def add_staff_landing_link(self, title: str, url: str,
                                link_type: str = "tg", emoji: str = "📢"):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COALESCE(MAX(position),0)+1 FROM staff_landing_links")
            pos = cur.fetchone()[0]
            cur.execute("""
                INSERT INTO staff_landing_links (title,link_type,url,emoji,position)
                VALUES (%s,%s,%s,%s,%s)
            """, (title, link_type, url, emoji, pos))

    def delete_staff_landing_link(self, link_id: int):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM staff_landing_links WHERE id=%s", (link_id,))

    # ── Message Flow ───────────────────────────────────────────────────────────

    def get_flows(self, channel_id: str | None = None, bot_type: str | None = None):
        with _get_conn() as conn:
            cur = conn.cursor()
            q = "SELECT * FROM message_flows WHERE 1=1"
            params = []
            if channel_id:
                q += " AND channel_id=%s"; params.append(channel_id)
            if bot_type:
                q += " AND bot_type=%s";   params.append(bot_type)
            cur.execute(q + " ORDER BY step ASC", params)
            return _rows(cur)

    def add_flow_step(self, channel_id: str, bot_type: str, step: int,
                      delay_min: int, message: str):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO message_flows (channel_id,bot_type,step,delay_min,message)
                VALUES (%s,%s,%s,%s,%s)
            """, (channel_id, bot_type, step, delay_min, message))

    def delete_flow_step(self, flow_id: int):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM message_flows WHERE id=%s", (flow_id,))

    def log_flow_sent(self, user_id: int, channel_id: str, step: int):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO flow_log (user_id,channel_id,step,sent_at) VALUES (%s,%s,%s,%s)
            """, (user_id, channel_id, step, datetime.utcnow().isoformat()))

    def was_flow_sent(self, user_id: int, channel_id: str, step: int) -> bool:
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id FROM flow_log WHERE user_id=%s AND channel_id=%s AND step=%s
            """, (user_id, channel_id, step))
            return bool(cur.fetchone())

    # ── WhatsApp Conversations ─────────────────────────────────────────────────

    def get_or_create_wa_conversation(self, wa_chat_id: str, wa_number: str,
                                       visitor_name: str) -> dict:
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM wa_conversations WHERE wa_chat_id=%s", (wa_chat_id,))
            row = _row(cur, cur.fetchone())
            if row: return row
            cur.execute("""
                INSERT INTO wa_conversations (wa_chat_id,wa_number,visitor_name,created_at)
                VALUES (%s,%s,%s,%s) RETURNING *
            """, (wa_chat_id, wa_number, visitor_name, datetime.utcnow().isoformat()))
            return _row(cur, cur.fetchone())

    def get_wa_conversations(self):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM wa_conversations
                ORDER BY COALESCE(last_message_at, created_at) DESC
            """)
            return _rows(cur)

    def get_wa_conversation(self, conv_id: int):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM wa_conversations WHERE id=%s", (conv_id,))
            return _row(cur, cur.fetchone())

    def save_wa_message(self, conv_id: int, wa_chat_id: str, sender_type: str,
                        content: str, media_url: str | None = None,
                        media_type: str | None = None):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO wa_messages
                (conversation_id,wa_chat_id,sender_type,content,media_url,media_type,created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (conv_id, wa_chat_id, sender_type, content, media_url, media_type,
                  datetime.utcnow().isoformat()))

    def get_wa_messages(self, conv_id: int, limit: int = 100):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM wa_messages WHERE conversation_id=%s
                ORDER BY created_at ASC LIMIT %s
            """, (conv_id, limit))
            return _rows(cur)

    def get_new_wa_messages(self, conv_id: int, after_id: int):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM wa_messages WHERE conversation_id=%s AND id>%s
                ORDER BY created_at ASC
            """, (conv_id, after_id))
            return _rows(cur)

    def update_wa_last_message(self, wa_chat_id: str, text: str,
                                increment_unread: bool = True):
        with _get_conn() as conn:
            cur = conn.cursor()
            if increment_unread:
                cur.execute("""
                    UPDATE wa_conversations
                    SET last_message=%s, last_message_at=%s, unread_count=unread_count+1
                    WHERE wa_chat_id=%s
                """, (text[:100], datetime.utcnow().isoformat(), wa_chat_id))
            else:
                cur.execute("""
                    UPDATE wa_conversations SET last_message=%s, last_message_at=%s
                    WHERE wa_chat_id=%s
                """, (text[:100], datetime.utcnow().isoformat(), wa_chat_id))

    def mark_wa_read(self, conv_id: int):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE wa_conversations SET unread_count=0 WHERE id=%s", (conv_id,))
            cur.execute("""
                UPDATE wa_messages SET read_by_manager=1
                WHERE conversation_id=%s AND sender_type='visitor'
            """, (conv_id,))

    def close_wa_conversation(self, conv_id: int):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE wa_conversations SET status='closed' WHERE id=%s", (conv_id,))

    def reopen_wa_conversation(self, conv_id: int):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE wa_conversations SET status='open' WHERE id=%s", (conv_id,))

    def set_wa_fb_event(self, conv_id: int, event: str):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE wa_conversations SET fb_event_sent=%s WHERE id=%s",
                        (event, conv_id))

    def get_wa_stats(self):
        with _get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM wa_conversations")
            total = cur.fetchone()[0]
            cur.execute("SELECT COALESCE(SUM(unread_count),0) FROM wa_conversations")
            unread = cur.fetchone()[0]
            return {"total": total, "unread": unread}
