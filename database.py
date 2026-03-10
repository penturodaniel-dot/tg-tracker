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
            total = conn.execute("SELECT COUNT(*) AS c FROM joins").fetchone()["c"]
            from_ads = conn.execute("SELECT COUNT(*) AS c FROM joins WHERE campaign_name!='organic'").fetchone()["c"]
            organic = conn.execute("SELECT COUNT(*) AS c FROM joins WHERE campaign_name='organic'").fetchone()["c"]
            channels = conn.execute("SELECT COUNT(*) AS c FROM channels").fetchone()["c"]
            campaigns = conn.execute("SELECT COUNT(*) AS c FROM campaigns").fetchone()["c"]
            return {"total": total, "from_ads": from_ads, "organic": organic, "channels": channels, "campaigns": campaigns}

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
