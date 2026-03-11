import sqlite3
import os
import secrets
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "tracker.db")


class Database:
    def __init__(self):
        self._init_db()

    def _conn(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                -- РОЛИ
                CREATE TABLE IF NOT EXISTS users (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    username     TEXT NOT NULL UNIQUE,
                    password     TEXT NOT NULL,
                    role         TEXT NOT NULL DEFAULT 'manager',
                    created_at   TEXT NOT NULL
                );

                -- КАНАЛЫ / КАМПАНИИ / ПОДПИСКИ
                CREATE TABLE IF NOT EXISTS channels (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT NOT NULL,
                    channel_id  TEXT NOT NULL UNIQUE,
                    created_at  TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS campaigns (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT NOT NULL,
                    channel_id  TEXT NOT NULL,
                    invite_link TEXT NOT NULL UNIQUE,
                    created_at  TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS joins (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id       INTEGER NOT NULL,
                    channel_id    TEXT,
                    invite_link   TEXT,
                    campaign_name TEXT NOT NULL DEFAULT 'organic',
                    click_id      TEXT,
                    joined_at     TEXT NOT NULL
                );

                -- ТРЕКИНГ КЛИКОВ
                CREATE TABLE IF NOT EXISTS click_tracking (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
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

                -- UTM ПРИВЯЗКА К ДИАЛОГУ
                CREATE TABLE IF NOT EXISTS utm_tracking (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
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

                -- ЧАТЫ СОТРУДНИКОВ
                CREATE TABLE IF NOT EXISTS conversations (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    tg_chat_id      TEXT NOT NULL UNIQUE,
                    visitor_name    TEXT NOT NULL DEFAULT 'Неизвестный',
                    username        TEXT,
                    status          TEXT DEFAULT 'open',
                    unread_count    INTEGER DEFAULT 0,
                    last_message    TEXT,
                    last_message_at TEXT,
                    fb_event_sent   TEXT,
                    created_at      TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER NOT NULL,
                    tg_chat_id      TEXT NOT NULL,
                    sender_type     TEXT NOT NULL,
                    content         TEXT,
                    tg_message_id   INTEGER,
                    read_by_manager INTEGER DEFAULT 0,
                    created_at      TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                );

                -- СОТРУДНИКИ
                CREATE TABLE IF NOT EXISTS staff (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
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

                -- ЛЕНДИНГ
                CREATE TABLE IF NOT EXISTS landing_links (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    title    TEXT NOT NULL,
                    tg_link  TEXT NOT NULL,
                    emoji    TEXT DEFAULT '📢',
                    position INTEGER DEFAULT 0
                );

                -- MESSAGE FLOW
                CREATE TABLE IF NOT EXISTS message_flows (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT NOT NULL,
                    bot_type   TEXT NOT NULL DEFAULT 'tracker',
                    step       INTEGER NOT NULL DEFAULT 0,
                    delay_min  INTEGER NOT NULL DEFAULT 0,
                    message    TEXT NOT NULL,
                    active     INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS flow_log (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    INTEGER NOT NULL,
                    channel_id TEXT NOT NULL,
                    step       INTEGER NOT NULL,
                    sent_at    TEXT NOT NULL
                );
            """)
            # Создаём дефолтного admin если нет пользователей
            count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            if count == 0:
                import hashlib
                pwd = hashlib.sha256("admin123".encode()).hexdigest()
                conn.execute("INSERT INTO users (username,password,role,created_at) VALUES (?,?,?,?)",
                             ("admin", pwd, "admin", datetime.utcnow().isoformat()))

    # ── Settings ──────────────────────────────────────────────────────────────

    def get_setting(self, key: str, default: str = "") -> str:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        with self._conn() as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (key, value))

    # ── Users / Roles ─────────────────────────────────────────────────────────

    def get_user(self, username: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            return dict(row) if row else None

    def get_users(self):
        with self._conn() as conn:
            return [dict(r) for r in conn.execute("SELECT id,username,role,created_at FROM users ORDER BY created_at").fetchall()]

    def create_user(self, username: str, password: str, role: str = "manager"):
        import hashlib
        pwd = hashlib.sha256(password.encode()).hexdigest()
        with self._conn() as conn:
            conn.execute("INSERT INTO users (username,password,role,created_at) VALUES (?,?,?,?)",
                         (username, pwd, role, datetime.utcnow().isoformat()))

    def delete_user(self, user_id: int):
        with self._conn() as conn:
            conn.execute("DELETE FROM users WHERE id=?", (user_id,))

    def verify_user(self, username: str, password: str) -> dict | None:
        import hashlib
        pwd = hashlib.sha256(password.encode()).hexdigest()
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE username=? AND password=?", (username, pwd)).fetchone()
            return dict(row) if row else None

    # ── Channels ──────────────────────────────────────────────────────────────

    def add_channel(self, name: str, channel_id: str):
        with self._conn() as conn:
            conn.execute("INSERT OR IGNORE INTO channels (name,channel_id,created_at) VALUES (?,?,?)",
                         (name, channel_id, datetime.utcnow().isoformat()))

    def get_channels(self):
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT c.*, COUNT(j.id) as total_joins
                FROM channels c LEFT JOIN joins j ON j.channel_id=c.channel_id
                GROUP BY c.id ORDER BY c.created_at DESC""").fetchall()
            return [dict(r) for r in rows]

    def delete_channel(self, channel_id: str):
        with self._conn() as conn:
            conn.execute("DELETE FROM channels WHERE channel_id=?", (channel_id,))

    def get_channel_ids(self):
        with self._conn() as conn:
            return [r["channel_id"] for r in conn.execute("SELECT channel_id FROM channels").fetchall()]

    # ── Campaigns ─────────────────────────────────────────────────────────────

    def save_campaign(self, name: str, channel_id: str, invite_link: str):
        with self._conn() as conn:
            conn.execute("INSERT OR IGNORE INTO campaigns (name,channel_id,invite_link,created_at) VALUES (?,?,?,?)",
                         (name, channel_id, invite_link, datetime.utcnow().isoformat()))

    def get_campaign_by_link(self, invite_link: str | None):
        if not invite_link: return None
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM campaigns WHERE invite_link=?", (invite_link,)).fetchone()
            return dict(row) if row else None

    def get_campaigns(self, channel_id: str | None = None):
        with self._conn() as conn:
            if channel_id:
                rows = conn.execute("""
                    SELECT c.*, COUNT(j.id) AS joins FROM campaigns c
                    LEFT JOIN joins j ON j.campaign_name=c.name AND j.channel_id=c.channel_id
                    WHERE c.channel_id=? GROUP BY c.id ORDER BY c.created_at DESC""", (channel_id,)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT c.*, COUNT(j.id) AS joins FROM campaigns c
                    LEFT JOIN joins j ON j.campaign_name=c.name AND j.channel_id=c.channel_id
                    GROUP BY c.id ORDER BY c.created_at DESC""").fetchall()
            return [dict(r) for r in rows]

    # ── Joins ─────────────────────────────────────────────────────────────────

    def log_join(self, user_id: int, channel_id: str, invite_link: str | None,
                 campaign_name: str, click_id: str | None = None) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO joins (user_id,channel_id,invite_link,campaign_name,click_id,joined_at) VALUES (?,?,?,?,?,?)",
                (user_id, channel_id, invite_link, campaign_name, click_id, datetime.utcnow().isoformat()))
            return cur.lastrowid

    def get_recent_joins(self, limit: int = 50):
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT j.*, c.name as channel_name FROM joins j LEFT JOIN channels c ON c.channel_id=j.channel_id ORDER BY j.joined_at DESC LIMIT ?", (limit,)).fetchall()]

    # ── Click Tracking ────────────────────────────────────────────────────────

    def save_click(self, fbclid: str = None, fbp: str = None, utm_source: str = None,
                   utm_medium: str = None, utm_campaign: str = None, utm_content: str = None,
                   utm_term: str = None, referrer: str = None, target_type: str = "channel",
                   target_id: str = None, user_agent: str = None, ip_address: str = None) -> str:
        click_id = secrets.token_urlsafe(12)
        with self._conn() as conn:
            conn.execute("""INSERT INTO click_tracking
                (click_id,fbclid,fbp,utm_source,utm_medium,utm_campaign,utm_content,utm_term,
                 referrer,target_type,target_id,user_agent,ip_address,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (click_id, fbclid, fbp, utm_source, utm_medium, utm_campaign, utm_content,
                 utm_term, referrer, target_type, target_id, user_agent, ip_address,
                 datetime.utcnow().isoformat()))
        return click_id

    def get_click(self, click_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM click_tracking WHERE click_id=?", (click_id,)).fetchone()
            return dict(row) if row else None

    def save_utm(self, click_data: dict, conversation_id: int = None, join_id: int = None):
        with self._conn() as conn:
            conn.execute("""INSERT INTO utm_tracking
                (conversation_id,join_id,click_id,fbclid,fbp,utm_source,utm_medium,
                 utm_campaign,utm_content,utm_term,referrer,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (conversation_id, join_id, click_data.get("click_id"), click_data.get("fbclid"),
                 click_data.get("fbp"), click_data.get("utm_source"), click_data.get("utm_medium"),
                 click_data.get("utm_campaign"), click_data.get("utm_content"),
                 click_data.get("utm_term"), click_data.get("referrer"),
                 datetime.utcnow().isoformat()))

    def get_utm_by_conv(self, conversation_id: int) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM utm_tracking WHERE conversation_id=? ORDER BY id DESC LIMIT 1",
                               (conversation_id,)).fetchone()
            return dict(row) if row else None

    def get_click_stats(self, days: int = 30):
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT DATE(created_at) as day, COUNT(*) as clicks,
                       SUM(CASE WHEN fbclid IS NOT NULL THEN 1 ELSE 0 END) as with_fbclid
                FROM click_tracking WHERE created_at >= DATE('now', ?)
                GROUP BY day ORDER BY day""", (f"-{days} days",)).fetchall()
            return [dict(r) for r in rows]

    # ── Conversations ─────────────────────────────────────────────────────────

    def get_or_create_conversation(self, tg_chat_id: str, visitor_name: str, username: str | None) -> dict:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM conversations WHERE tg_chat_id=?", (tg_chat_id,)).fetchone()
            if row: return dict(row)
            conn.execute("INSERT INTO conversations (tg_chat_id,visitor_name,username,created_at) VALUES (?,?,?,?)",
                         (tg_chat_id, visitor_name, username, datetime.utcnow().isoformat()))
            return dict(conn.execute("SELECT * FROM conversations WHERE tg_chat_id=?", (tg_chat_id,)).fetchone())

    def get_conversations(self):
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM conversations ORDER BY COALESCE(last_message_at,created_at) DESC").fetchall()]

    def get_conversation(self, conv_id: int):
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM conversations WHERE id=?", (conv_id,)).fetchone()
            return dict(row) if row else None

    def update_conversation_last_message(self, tg_chat_id: str, text: str, increment_unread: bool = True):
        with self._conn() as conn:
            if increment_unread:
                conn.execute("UPDATE conversations SET last_message=?,last_message_at=?,unread_count=unread_count+1 WHERE tg_chat_id=?",
                             (text[:100], datetime.utcnow().isoformat(), tg_chat_id))
            else:
                conn.execute("UPDATE conversations SET last_message=?,last_message_at=? WHERE tg_chat_id=?",
                             (text[:100], datetime.utcnow().isoformat(), tg_chat_id))

    def mark_conversation_read(self, conv_id: int):
        with self._conn() as conn:
            conn.execute("UPDATE conversations SET unread_count=0 WHERE id=?", (conv_id,))
            conn.execute("UPDATE messages SET read_by_manager=1 WHERE conversation_id=? AND sender_type='visitor'", (conv_id,))

    def close_conversation(self, conv_id: int):
        with self._conn() as conn:
            conn.execute("UPDATE conversations SET status='closed' WHERE id=?", (conv_id,))

    def reopen_conversation(self, conv_id: int):
        with self._conn() as conn:
            conn.execute("UPDATE conversations SET status='open' WHERE id=?", (conv_id,))

    def set_conv_fb_event(self, conv_id: int, event: str):
        with self._conn() as conn:
            conn.execute("UPDATE conversations SET fb_event_sent=? WHERE id=?", (event, conv_id))

    # ── Messages ──────────────────────────────────────────────────────────────

    def save_message(self, conversation_id: int, tg_chat_id: str, sender_type: str,
                     content: str, tg_message_id: int | None = None):
        with self._conn() as conn:
            conn.execute("INSERT INTO messages (conversation_id,tg_chat_id,sender_type,content,tg_message_id,created_at) VALUES (?,?,?,?,?,?)",
                         (conversation_id, tg_chat_id, sender_type, content, tg_message_id, datetime.utcnow().isoformat()))

    def get_messages(self, conversation_id: int, limit: int = 100):
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at ASC LIMIT ?",
                (conversation_id, limit)).fetchall()]

    def get_new_messages(self, conversation_id: int, after_id: int):
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM messages WHERE conversation_id=? AND id>? ORDER BY created_at ASC",
                (conversation_id, after_id)).fetchall()]

    # ── Staff ─────────────────────────────────────────────────────────────────

    def get_or_create_staff(self, tg_chat_id: str, name: str, username: str | None, conv_id: int):
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM staff WHERE tg_chat_id=?", (tg_chat_id,)).fetchone()
            if row: return dict(row)
            conn.execute("INSERT INTO staff (conversation_id,tg_chat_id,name,username,created_at) VALUES (?,?,?,?,?)",
                         (conv_id, tg_chat_id, name, username, datetime.utcnow().isoformat()))
            return dict(conn.execute("SELECT * FROM staff WHERE tg_chat_id=?", (tg_chat_id,)).fetchone())

    def get_staff(self, status: str | None = None):
        with self._conn() as conn:
            if status:
                rows = conn.execute("SELECT * FROM staff WHERE status=? ORDER BY created_at DESC", (status,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM staff ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]

    def update_staff(self, staff_id: int, name: str, phone: str, email: str,
                     position: str, status: str, notes: str, tags: str):
        with self._conn() as conn:
            conn.execute("UPDATE staff SET name=?,phone=?,email=?,position=?,status=?,notes=?,tags=? WHERE id=?",
                         (name, phone, email, position, status, notes, tags, staff_id))

    def update_staff_status(self, staff_id: int, status: str):
        with self._conn() as conn:
            conn.execute("UPDATE staff SET status=? WHERE id=?", (status, staff_id))

    def get_staff_by_conv(self, conv_id: int):
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM staff WHERE conversation_id=?", (conv_id,)).fetchone()
            return dict(row) if row else None

    def set_staff_fb_event(self, staff_id: int, event: str):
        with self._conn() as conn:
            conn.execute("UPDATE staff SET fb_event_sent=? WHERE id=?", (event, staff_id))

    def get_staff_funnel(self):
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT status, COUNT(*) as cnt FROM staff GROUP BY status""").fetchall()
            return {r["status"]: r["cnt"] for r in rows}

    # ── Stats ─────────────────────────────────────────────────────────────────

    def get_stats(self):
        with self._conn() as conn:
            total     = conn.execute("SELECT COUNT(*) AS c FROM joins").fetchone()["c"]
            from_ads  = conn.execute("SELECT COUNT(*) AS c FROM joins WHERE campaign_name!='organic'").fetchone()["c"]
            organic   = conn.execute("SELECT COUNT(*) AS c FROM joins WHERE campaign_name='organic'").fetchone()["c"]
            channels  = conn.execute("SELECT COUNT(*) AS c FROM channels").fetchone()["c"]
            campaigns = conn.execute("SELECT COUNT(*) AS c FROM campaigns").fetchone()["c"]
            convs     = conn.execute("SELECT COUNT(*) AS c FROM conversations").fetchone()["c"]
            unread    = conn.execute("SELECT COALESCE(SUM(unread_count),0) AS c FROM conversations").fetchone()["c"]
            staff_cnt = conn.execute("SELECT COUNT(*) AS c FROM staff").fetchone()["c"]
            clicks    = conn.execute("SELECT COUNT(*) AS c FROM click_tracking").fetchone()["c"]
            return {"total": total, "from_ads": from_ads, "organic": organic,
                    "channels": channels, "campaigns": campaigns,
                    "conversations": convs, "unread": unread,
                    "staff": staff_cnt, "clicks": clicks}

    def get_joins_by_day(self, days: int = 30):
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT DATE(joined_at) as day, COUNT(*) as cnt,
                       SUM(CASE WHEN campaign_name!='organic' THEN 1 ELSE 0 END) as from_ads
                FROM joins WHERE joined_at >= DATE('now', ?)
                GROUP BY day ORDER BY day""", (f"-{days} days",)).fetchall()
            return [dict(r) for r in rows]

    def get_campaign_stats(self):
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT campaign_name, COUNT(*) as joins,
                       MIN(joined_at) as first_join, MAX(joined_at) as last_join
                FROM joins WHERE campaign_name!='organic'
                GROUP BY campaign_name ORDER BY joins DESC LIMIT 20""").fetchall()
            return [dict(r) for r in rows]

    def get_staff_by_day(self, days: int = 30):
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT DATE(created_at) as day, COUNT(*) as cnt
                FROM staff WHERE created_at >= DATE('now', ?)
                GROUP BY day ORDER BY day""", (f"-{days} days",)).fetchall()
            return [dict(r) for r in rows]

    # ── Landing ────────────────────────────────────────────────────────────────

    def get_landing_links(self):
        with self._conn() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM landing_links ORDER BY position ASC").fetchall()]

    def add_landing_link(self, title: str, tg_link: str, emoji: str = "📢"):
        with self._conn() as conn:
            pos = conn.execute("SELECT COALESCE(MAX(position),0)+1 FROM landing_links").fetchone()[0]
            conn.execute("INSERT INTO landing_links (title,tg_link,emoji,position) VALUES (?,?,?,?)",
                         (title, tg_link, emoji, pos))

    def delete_landing_link(self, link_id: int):
        with self._conn() as conn:
            conn.execute("DELETE FROM landing_links WHERE id=?", (link_id,))

    # ── Message Flow ───────────────────────────────────────────────────────────

    def get_flows(self, channel_id: str | None = None, bot_type: str | None = None):
        with self._conn() as conn:
            q = "SELECT * FROM message_flows WHERE 1=1"
            params = []
            if channel_id: q += " AND channel_id=?"; params.append(channel_id)
            if bot_type:   q += " AND bot_type=?";   params.append(bot_type)
            return [dict(r) for r in conn.execute(q + " ORDER BY step ASC", params).fetchall()]

    def add_flow_step(self, channel_id: str, bot_type: str, step: int, delay_min: int, message: str):
        with self._conn() as conn:
            conn.execute("INSERT INTO message_flows (channel_id,bot_type,step,delay_min,message) VALUES (?,?,?,?,?)",
                         (channel_id, bot_type, step, delay_min, message))

    def delete_flow_step(self, flow_id: int):
        with self._conn() as conn:
            conn.execute("DELETE FROM message_flows WHERE id=?", (flow_id,))

    def log_flow_sent(self, user_id: int, channel_id: str, step: int):
        with self._conn() as conn:
            conn.execute("INSERT INTO flow_log (user_id,channel_id,step,sent_at) VALUES (?,?,?,?)",
                         (user_id, channel_id, step, datetime.utcnow().isoformat()))

    def was_flow_sent(self, user_id: int, channel_id: str, step: int) -> bool:
        with self._conn() as conn:
            return bool(conn.execute(
                "SELECT id FROM flow_log WHERE user_id=? AND channel_id=? AND step=?",
                (user_id, channel_id, step)).fetchone())
