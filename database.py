import sqlite3
import os
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
                    joined_at     TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS landing_links (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    title      TEXT NOT NULL,
                    tg_link    TEXT NOT NULL,
                    emoji      TEXT DEFAULT '📢',
                    position   INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS message_flows (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT NOT NULL,
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

                CREATE TABLE IF NOT EXISTS conversations (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    tg_chat_id      TEXT NOT NULL UNIQUE,
                    visitor_name    TEXT NOT NULL DEFAULT 'Неизвестный',
                    username        TEXT,
                    source          TEXT DEFAULT 'telegram',
                    status          TEXT DEFAULT 'open',
                    unread_count    INTEGER DEFAULT 0,
                    last_message    TEXT,
                    last_message_at TEXT,
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

                CREATE TABLE IF NOT EXISTS clients (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER,
                    tg_chat_id      TEXT UNIQUE,
                    name            TEXT,
                    username        TEXT,
                    phone           TEXT,
                    email           TEXT,
                    notes           TEXT,
                    tags            TEXT DEFAULT '[]',
                    created_at      TEXT NOT NULL
                );
            """)

    # ── Settings ──────────────────────────────────────────────────────────────

    def get_setting(self, key: str, default: str = "") -> str:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        with self._conn() as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (key, value))

    # ── Channels ──────────────────────────────────────────────────────────────

    def add_channel(self, name: str, channel_id: str):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO channels (name, channel_id, created_at) VALUES (?,?,?)",
                (name, channel_id, datetime.utcnow().isoformat())
            )

    def get_channels(self):
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT c.*, COUNT(j.id) as total_joins
                FROM channels c
                LEFT JOIN joins j ON j.channel_id = c.channel_id
                GROUP BY c.id ORDER BY c.created_at DESC
            """).fetchall()
            return [dict(r) for r in rows]

    def delete_channel(self, channel_id: str):
        with self._conn() as conn:
            conn.execute("DELETE FROM channels WHERE channel_id=?", (channel_id,))

    def get_channel_ids(self):
        with self._conn() as conn:
            rows = conn.execute("SELECT channel_id FROM channels").fetchall()
            return [r["channel_id"] for r in rows]

    # ── Campaigns ─────────────────────────────────────────────────────────────

    def save_campaign(self, name: str, channel_id: str, invite_link: str):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO campaigns (name, channel_id, invite_link, created_at) VALUES (?,?,?,?)",
                (name, channel_id, invite_link, datetime.utcnow().isoformat())
            )

    def get_campaign_by_link(self, invite_link: str | None):
        if not invite_link:
            return None
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM campaigns WHERE invite_link=?", (invite_link,)).fetchone()
            return dict(row) if row else None

    def get_campaigns(self, channel_id: str | None = None):
        with self._conn() as conn:
            if channel_id:
                rows = conn.execute("""
                    SELECT c.*, COUNT(j.id) AS joins
                    FROM campaigns c
                    LEFT JOIN joins j ON j.campaign_name = c.name AND j.channel_id = c.channel_id
                    WHERE c.channel_id=?
                    GROUP BY c.id ORDER BY c.created_at DESC
                """, (channel_id,)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT c.*, COUNT(j.id) AS joins
                    FROM campaigns c
                    LEFT JOIN joins j ON j.campaign_name = c.name AND j.channel_id = c.channel_id
                    GROUP BY c.id ORDER BY c.created_at DESC
                """).fetchall()
            return [dict(r) for r in rows]

    # ── Joins ──────────────────────────────────────────────────────────────────

    def log_join(self, user_id: int, channel_id: str, invite_link: str | None, campaign_name: str):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO joins (user_id, channel_id, invite_link, campaign_name, joined_at) VALUES (?,?,?,?,?)",
                (user_id, channel_id, invite_link, campaign_name, datetime.utcnow().isoformat())
            )

    def get_recent_joins(self, limit: int = 50):
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM joins ORDER BY joined_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_organic_joins(self):
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM joins WHERE campaign_name='organic'").fetchone()
            return row["cnt"] if row else 0

    def get_stats(self):
        with self._conn() as conn:
            total    = conn.execute("SELECT COUNT(*) AS c FROM joins").fetchone()["c"]
            from_ads = conn.execute("SELECT COUNT(*) AS c FROM joins WHERE campaign_name!='organic'").fetchone()["c"]
            organic  = conn.execute("SELECT COUNT(*) AS c FROM joins WHERE campaign_name='organic'").fetchone()["c"]
            channels = conn.execute("SELECT COUNT(*) AS c FROM channels").fetchone()["c"]
            campaigns= conn.execute("SELECT COUNT(*) AS c FROM campaigns").fetchone()["c"]
            convs    = conn.execute("SELECT COUNT(*) AS c FROM conversations").fetchone()["c"]
            unread   = conn.execute("SELECT COALESCE(SUM(unread_count),0) AS c FROM conversations").fetchone()["c"]
            return {"total": total, "from_ads": from_ads, "organic": organic,
                    "channels": channels, "campaigns": campaigns, "conversations": convs, "unread": unread}

    # ── Conversations ─────────────────────────────────────────────────────────

    def get_or_create_conversation(self, tg_chat_id: str, visitor_name: str, username: str | None) -> dict:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM conversations WHERE tg_chat_id=?", (tg_chat_id,)).fetchone()
            if row:
                return dict(row)
            conn.execute(
                "INSERT INTO conversations (tg_chat_id, visitor_name, username, created_at) VALUES (?,?,?,?)",
                (tg_chat_id, visitor_name, username, datetime.utcnow().isoformat())
            )
            row = conn.execute("SELECT * FROM conversations WHERE tg_chat_id=?", (tg_chat_id,)).fetchone()
            return dict(row)

    def get_conversations(self):
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM conversations
                ORDER BY COALESCE(last_message_at, created_at) DESC
            """).fetchall()
            return [dict(r) for r in rows]

    def get_conversation(self, conv_id: int):
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM conversations WHERE id=?", (conv_id,)).fetchone()
            return dict(row) if row else None

    def get_conversation_by_chat(self, tg_chat_id: str):
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM conversations WHERE tg_chat_id=?", (tg_chat_id,)).fetchone()
            return dict(row) if row else None

    def update_conversation_last_message(self, tg_chat_id: str, text: str, increment_unread: bool = True):
        with self._conn() as conn:
            if increment_unread:
                conn.execute("""
                    UPDATE conversations
                    SET last_message=?, last_message_at=?, unread_count=unread_count+1
                    WHERE tg_chat_id=?
                """, (text[:100], datetime.utcnow().isoformat(), tg_chat_id))
            else:
                conn.execute("""
                    UPDATE conversations
                    SET last_message=?, last_message_at=?
                    WHERE tg_chat_id=?
                """, (text[:100], datetime.utcnow().isoformat(), tg_chat_id))

    def mark_conversation_read(self, conv_id: int):
        with self._conn() as conn:
            conn.execute("UPDATE conversations SET unread_count=0 WHERE id=?", (conv_id,))
            conn.execute("""
                UPDATE messages SET read_by_manager=1
                WHERE conversation_id=? AND sender_type='visitor'
            """, (conv_id,))

    def close_conversation(self, conv_id: int):
        with self._conn() as conn:
            conn.execute("UPDATE conversations SET status='closed' WHERE id=?", (conv_id,))

    def reopen_conversation(self, conv_id: int):
        with self._conn() as conn:
            conn.execute("UPDATE conversations SET status='open' WHERE id=?", (conv_id,))

    # ── Messages ──────────────────────────────────────────────────────────────

    def save_message(self, conversation_id: int, tg_chat_id: str, sender_type: str,
                     content: str, tg_message_id: int | None = None) -> int:
        with self._conn() as conn:
            cur = conn.execute("""
                INSERT INTO messages (conversation_id, tg_chat_id, sender_type, content, tg_message_id, created_at)
                VALUES (?,?,?,?,?,?)
            """, (conversation_id, tg_chat_id, sender_type, content,
                  tg_message_id, datetime.utcnow().isoformat()))
            return cur.lastrowid

    def get_messages(self, conversation_id: int, limit: int = 100):
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM messages WHERE conversation_id=?
                ORDER BY created_at ASC LIMIT ?
            """, (conversation_id, limit)).fetchall()
            return [dict(r) for r in rows]

    def get_new_messages(self, conversation_id: int, after_id: int):
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM messages WHERE conversation_id=? AND id>?
                ORDER BY created_at ASC
            """, (conversation_id, after_id)).fetchall()
            return [dict(r) for r in rows]

    # ── Clients ───────────────────────────────────────────────────────────────

    def get_or_create_client(self, tg_chat_id: str, name: str, username: str | None, conv_id: int):
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM clients WHERE tg_chat_id=?", (tg_chat_id,)).fetchone()
            if row:
                return dict(row)
            conn.execute("""
                INSERT INTO clients (conversation_id, tg_chat_id, name, username, created_at)
                VALUES (?,?,?,?,?)
            """, (conv_id, tg_chat_id, name, username, datetime.utcnow().isoformat()))
            row = conn.execute("SELECT * FROM clients WHERE tg_chat_id=?", (tg_chat_id,)).fetchone()
            return dict(row)

    def get_clients(self):
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM clients ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]

    def update_client(self, client_id: int, name: str, phone: str, email: str, notes: str, tags: str):
        with self._conn() as conn:
            conn.execute("""
                UPDATE clients SET name=?, phone=?, email=?, notes=?, tags=?
                WHERE id=?
            """, (name, phone, email, notes, tags, client_id))

    def get_client_by_conv(self, conv_id: int):
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM clients WHERE conversation_id=?", (conv_id,)).fetchone()
            return dict(row) if row else None

    # ── Landing ────────────────────────────────────────────────────────────────

    def get_landing_links(self):
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM landing_links ORDER BY position ASC").fetchall()
            return [dict(r) for r in rows]

    def add_landing_link(self, title: str, tg_link: str, emoji: str = "📢"):
        with self._conn() as conn:
            pos = conn.execute("SELECT COALESCE(MAX(position),0)+1 FROM landing_links").fetchone()[0]
            conn.execute("INSERT INTO landing_links (title, tg_link, emoji, position) VALUES (?,?,?,?)",
                         (title, tg_link, emoji, pos))

    def delete_landing_link(self, link_id: int):
        with self._conn() as conn:
            conn.execute("DELETE FROM landing_links WHERE id=?", (link_id,))

    # ── Message Flow ───────────────────────────────────────────────────────────

    def get_flows(self, channel_id: str | None = None):
        with self._conn() as conn:
            if channel_id:
                rows = conn.execute("SELECT * FROM message_flows WHERE channel_id=? ORDER BY step ASC", (channel_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM message_flows ORDER BY channel_id, step ASC").fetchall()
            return [dict(r) for r in rows]

    def add_flow_step(self, channel_id: str, step: int, delay_min: int, message: str):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO message_flows (channel_id, step, delay_min, message) VALUES (?,?,?,?)",
                (channel_id, step, delay_min, message)
            )

    def delete_flow_step(self, flow_id: int):
        with self._conn() as conn:
            conn.execute("DELETE FROM message_flows WHERE id=?", (flow_id,))

    def log_flow_sent(self, user_id: int, channel_id: str, step: int):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO flow_log (user_id, channel_id, step, sent_at) VALUES (?,?,?,?)",
                (user_id, channel_id, step, datetime.utcnow().isoformat())
            )

    def was_flow_sent(self, user_id: int, channel_id: str, step: int) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM flow_log WHERE user_id=? AND channel_id=? AND step=?",
                (user_id, channel_id, step)
            ).fetchone()
            return row is not None
