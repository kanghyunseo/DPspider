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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS txn_category (
                txn_id           TEXT PRIMARY KEY,
                business_category TEXT NOT NULL,
                vendor           TEXT,
                classified_at    TEXT NOT NULL
            )
            """
        )


def get_txn_categories(db_path: str, txn_ids: list[str]) -> dict[str, dict]:
    """Return {txn_id: {category, vendor}} for cached txns."""
    if not txn_ids:
        return {}
    placeholders = ",".join("?" * len(txn_ids))
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT txn_id, business_category, vendor "
            f"FROM txn_category WHERE txn_id IN ({placeholders})",
            txn_ids,
        ).fetchall()
    return {tid: {"category": cat, "vendor": vendor} for tid, cat, vendor in rows}


def save_txn_categories(
    db_path: str, classifications: list[tuple[str, str, str | None]]
) -> None:
    """Save (txn_id, category, vendor) tuples. INSERT OR REPLACE."""
    if not classifications:
        return
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO txn_category"
            "(txn_id, business_category, vendor, classified_at) "
            "VALUES (?,?,?,?)",
            [(tid, cat, vendor, now) for tid, cat, vendor in classifications],
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
