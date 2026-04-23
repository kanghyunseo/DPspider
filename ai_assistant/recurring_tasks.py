"""Recurring task templates.

Google Tasks API doesn't support recurrence natively. We store templates
in SQLite and a daily scheduled job materializes them into real Google
Tasks at the right time.

Recurrence rules supported (subset of RFC 5545 RRULE for simplicity):
- DAILY                              — every day
- WEEKLY:MO,TU,WE,TH,FR,SA,SU         — selected weekdays each week
- MONTHLY:1                          — Nth day of month (1-28 safe; 29-31 may skip)
- MONTHLY:LAST                       — last day of month
"""
from __future__ import annotations

import calendar as _cal
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config
from .gtasks import Tasks

logger = logging.getLogger(__name__)


WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


@dataclass
class RecurringTaskTemplate:
    id: int
    title: str
    notes: str | None
    rule: str           # one of DAILY / WEEKLY:... / MONTHLY:N / MONTHLY:LAST
    due_offset_days: int  # 0 = due same day, 7 = due in a week
    last_run_date: str | None  # YYYY-MM-DD; prevents double-creation
    created_at: str


def init_db() -> None:
    with sqlite3.connect(config.DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recurring_task (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                title           TEXT    NOT NULL,
                notes           TEXT,
                rule            TEXT    NOT NULL,
                due_offset_days INTEGER NOT NULL DEFAULT 0,
                last_run_date   TEXT,
                created_at      TEXT    NOT NULL
            )
            """
        )


def add_template(
    title: str, rule: str, notes: str | None = None, due_offset_days: int = 0
) -> int:
    """Insert a template. Returns new id."""
    rule = _normalize_rule(rule)
    now = datetime.now(ZoneInfo(config.DEFAULT_TIMEZONE)).isoformat()
    with sqlite3.connect(config.DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO recurring_task(title, notes, rule, due_offset_days, "
            "created_at) VALUES (?,?,?,?,?)",
            (title, notes, rule, due_offset_days, now),
        )
        return cur.lastrowid


def list_templates() -> list[RecurringTaskTemplate]:
    with sqlite3.connect(config.DB_PATH) as conn:
        rows = conn.execute(
            "SELECT id, title, notes, rule, due_offset_days, "
            "last_run_date, created_at FROM recurring_task ORDER BY id"
        ).fetchall()
    return [RecurringTaskTemplate(*row) for row in rows]


def delete_template(template_id: int) -> bool:
    with sqlite3.connect(config.DB_PATH) as conn:
        cur = conn.execute(
            "DELETE FROM recurring_task WHERE id = ?", (template_id,)
        )
        return cur.rowcount > 0


def _mark_run(template_id: int, date_str: str) -> None:
    with sqlite3.connect(config.DB_PATH) as conn:
        conn.execute(
            "UPDATE recurring_task SET last_run_date = ? WHERE id = ?",
            (date_str, template_id),
        )


def _normalize_rule(rule: str) -> str:
    rule = rule.strip().upper()
    if rule == "DAILY":
        return "DAILY"
    if rule.startswith("WEEKLY:"):
        days = [d.strip() for d in rule[len("WEEKLY:") :].split(",") if d.strip()]
        for d in days:
            if d not in WEEKDAYS:
                raise ValueError(f"Unknown weekday in rule: {d}")
        return "WEEKLY:" + ",".join(days)
    if rule.startswith("MONTHLY:"):
        spec = rule[len("MONTHLY:") :].strip()
        if spec == "LAST":
            return "MONTHLY:LAST"
        try:
            n = int(spec)
            if not 1 <= n <= 31:
                raise ValueError
            return f"MONTHLY:{n}"
        except ValueError:
            raise ValueError(f"Invalid monthly day: {spec}")
    raise ValueError(f"Unsupported rule format: {rule}")


def _matches_today(rule: str, today: datetime) -> bool:
    if rule == "DAILY":
        return True
    if rule.startswith("WEEKLY:"):
        days = rule[len("WEEKLY:") :].split(",")
        return today.weekday() in {WEEKDAYS[d] for d in days}
    if rule.startswith("MONTHLY:"):
        spec = rule[len("MONTHLY:") :]
        if spec == "LAST":
            last_day = _cal.monthrange(today.year, today.month)[1]
            return today.day == last_day
        n = int(spec)
        last_day = _cal.monthrange(today.year, today.month)[1]
        # If user asked for day 31 in a 30-day month, fire on the last day instead
        return today.day == min(n, last_day)
    return False


def materialize_due_today(tasks: Tasks) -> list[dict]:
    """Create Google Tasks for any templates that match today and haven't fired.

    Returns list of created task summaries.
    """
    tz = ZoneInfo(config.DEFAULT_TIMEZONE)
    now = datetime.now(tz)
    today_str = now.strftime("%Y-%m-%d")
    created = []
    for tpl in list_templates():
        if tpl.last_run_date == today_str:
            continue
        if not _matches_today(tpl.rule, now):
            continue
        due_date = (now + timedelta(days=tpl.due_offset_days)).strftime("%Y-%m-%d")
        # Google Tasks: send midnight UTC of the desired date
        due_iso = f"{due_date}T00:00:00Z"
        try:
            t = tasks.create_task(title=tpl.title, notes=tpl.notes, due=due_iso)
            _mark_run(tpl.id, today_str)
            created.append({"template_id": tpl.id, "task": t})
            logger.info("Recurring task fired: %s (rule=%s)", tpl.title, tpl.rule)
        except Exception:
            logger.exception(
                "Recurring task creation failed for template %s", tpl.id
            )
    return created
