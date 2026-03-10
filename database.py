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
                CREATE TABLE IF NOT EXISTS campaigns (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT NOT NULL,
                    invite_link TEXT NOT NULL UNIQUE,
                    created_at  TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS joins (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id       INTEGER NOT NULL,
                    invite_link   TEXT,
                    campaign_name TEXT NOT NULL DEFAULT 'organic',
                    joined_at     TEXT NOT NULL
                );
            """)

    # ── Campaigns ─────────────────────────────────────────────────────────────

    def save_campaign(self, name: str, invite_link: str):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO campaigns (name, invite_link, created_at) VALUES (?, ?, ?)",
                (name, invite_link, datetime.utcnow().isoformat()),
            )

    def get_campaign_by_link(self, invite_link: str | None):
        if not invite_link:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM campaigns WHERE invite_link = ?", (invite_link,)
            ).fetchone()
            return dict(row) if row else None

    def get_campaigns(self):
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT c.id, c.name, c.invite_link, c.created_at,
                       COUNT(j.id) AS joins
                FROM campaigns c
                LEFT JOIN joins j ON j.campaign_name = c.name
                GROUP BY c.id
                ORDER BY c.created_at DESC
            """).fetchall()
            return [dict(r) for r in rows]

    # ── Joins ──────────────────────────────────────────────────────────────────

    def log_join(self, user_id: int, invite_link: str | None, campaign_name: str):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO joins (user_id, invite_link, campaign_name, joined_at) VALUES (?, ?, ?, ?)",
                (user_id, invite_link, campaign_name, datetime.utcnow().isoformat()),
            )

    def get_recent_joins(self, limit: int = 50):
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM joins ORDER BY joined_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_organic_joins(self):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM joins WHERE campaign_name = 'organic'"
            ).fetchone()
            return row["cnt"] if row else 0
