"""Morning briefing — today's events + today's task deadlines + overdue."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config
from .gcal import Calendar
from .gtasks import Tasks, is_overdue

logger = logging.getLogger(__name__)


def _today_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1) - timedelta(seconds=1)
    return start, end


def _format_event(ev: dict, tz: ZoneInfo) -> str:
    start = ev.get("start", "")
    summary = ev.get("summary", "(제목 없음)")
    try:
        # All-day events have date only (no time component / no offset)
        if "T" in start:
            dt = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(tz)
            time_str = dt.strftime("%H:%M")
        else:
            time_str = "종일"
    except ValueError:
        time_str = start[:16]
    loc = ev.get("location")
    loc_str = f" @ {loc}" if loc else ""
    return f"  • {time_str}  {summary}{loc_str}"


def _format_task(t: dict, now: datetime) -> str:
    title = t.get("title", "(제목 없음)")
    due = t.get("due")
    if due:
        try:
            d = datetime.fromisoformat(due.replace("Z", "+00:00"))
            days = (d.date() - now.date()).days
            if days < 0:
                tag = f"🚧 {-days}일 지연"
            elif days == 0:
                tag = "🔥 오늘"
            elif days <= 3:
                tag = f"⏰ D-{days}"
            else:
                tag = f"D-{days}"
            return f"  • {title}  [{tag}]"
        except ValueError:
            pass
    return f"  • {title}"


def build_briefing(calendar: Calendar, tasks: Tasks) -> str:
    """Compose a morning briefing message string."""
    tz = ZoneInfo(config.DEFAULT_TIMEZONE)
    now = datetime.now(tz)
    start, end = _today_bounds(now)

    # Events today
    try:
        events = calendar.list_events(
            time_min=start.isoformat(),
            time_max=end.isoformat(),
            max_results=20,
        )
    except Exception as e:
        logger.exception("Daily briefing: calendar fetch failed")
        events = []
        events_err = str(e)
    else:
        events_err = None

    # Tasks: open + categorize
    try:
        open_tasks = tasks.list_tasks(show_completed=False, max_results=100)
    except Exception as e:
        logger.exception("Daily briefing: tasks fetch failed")
        open_tasks = []
        tasks_err = str(e)
    else:
        tasks_err = None

    today_str = now.strftime("%Y-%m-%d")
    overdue: list[dict] = []
    due_today: list[dict] = []
    due_soon: list[dict] = []  # within 3 days
    for t in open_tasks:
        if is_overdue(t, now):
            overdue.append(t)
            continue
        due = t.get("due")
        if not due:
            continue
        try:
            d = datetime.fromisoformat(due.replace("Z", "+00:00"))
        except ValueError:
            continue
        if d.date() == now.date():
            due_today.append(t)
        elif 0 < (d.date() - now.date()).days <= 3:
            due_soon.append(t)

    weekday_kr = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]
    lines: list[str] = [
        f"☀️ 오늘 브리핑 — {today_str} ({weekday_kr})",
        "",
        f"📅 일정 ({len(events)}건)",
    ]
    if events_err:
        lines.append(f"  ⚠️ 캘린더 조회 실패: {events_err}")
    elif not events:
        lines.append("  (일정 없음)")
    else:
        for ev in events:
            lines.append(_format_event(ev, tz))

    lines.append("")
    lines.append(f"🔥 오늘 마감 업무 ({len(due_today)}건)")
    if not due_today:
        lines.append("  (없음)")
    else:
        for t in due_today:
            lines.append(_format_task(t, now))

    if overdue:
        lines.append("")
        lines.append(f"🚧 지연 업무 ({len(overdue)}건)")
        for t in overdue[:10]:
            lines.append(_format_task(t, now))
        if len(overdue) > 10:
            lines.append(f"  …외 {len(overdue) - 10}건")

    if due_soon:
        lines.append("")
        lines.append(f"⏰ 마감 임박 (3일 이내, {len(due_soon)}건)")
        for t in due_soon[:5]:
            lines.append(_format_task(t, now))

    if tasks_err:
        lines.append("")
        lines.append(f"⚠️ 업무 조회 실패: {tasks_err}")

    return "\n".join(lines)
