"""SQLite-backed conversation history (final text only, one row per turn)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def init_db(db_path: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                role       TEXT    NOT NULL CHECK(role IN ('user','assistant')),
                content    TEXT    NOT NULL,
                created_at TEXT    NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_created ON messages(user_id, id)"
        )


def load_history(db_path: str, user_id: int, limit: int) -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages "
            "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    rows.reverse()
    return [{"role": role, "content": content} for role, content in rows]


def append_message(db_path: str, user_id: int, role: str, content: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO messages(user_id, role, content, created_at) "
            "VALUES(?,?,?,?)",
            (user_id, role, content, datetime.now(timezone.utc).isoformat()),
        )


def clear_history(db_path: str, user_id: int) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
