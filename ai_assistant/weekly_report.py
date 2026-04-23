"""Weekly report generator.

Pulls last week's Calendar events + Google Tasks state + Airwallex
finance, summarizes via Claude, uploads the result to Google Drive
as a Google Doc, and returns metadata for Telegram delivery.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import anthropic

from . import config, finance_report
from .airwallex_client import Airwallex
from .gcal import Calendar
from .gdrive import Drive
from .gtasks import Tasks, is_overdue

logger = logging.getLogger(__name__)


REPORT_SYSTEM_PROMPT = """당신은 올에프인비(All F&B) 글로벌사업팀장의 \
주간 리포트 작성 비서입니다.

사용자가 JSON 으로 **지난주** 데이터를 제공합니다 — Calendar 일정, \
Google Tasks 의 진행상황(완료/진행중/지연/신규).
이를 바탕으로 **지난주 회고 + 이번주 전망 리포트**를 마크다운으로 작성하세요.

리포트 구조 (반드시 이 순서):

# 1. 한 줄 요약
지난주를 한 문장으로. 핵심 성과 1개 + 핵심 이슈 1개.

# 2. ✅ 완료된 업무
지난주에 완료처리된 task 목록. 각 항목 한 줄: "- [완료일] 제목 (notes 핵심)"

# 3. 🔄 진행중 업무
status=needsAction 이고 due가 지난주 종료 시점 이후인 task. \
마감일 임박순 정렬. 각 항목: "- [~마감일] 제목 — notes 한 줄 요약"

# 4. 🚧 지연/블로커
status=needsAction 이고 due가 이미 지난 task. 가장 위험한 것부터.

# 5. 🆕 이번주 신규/예정 업무
이번주 마감인 task + 캘린더 일정의 description 에서 유추 가능한 신규 업무.

# 6. 📅 지난주 일정 회고
캘린더 이벤트 표 (날짜/시간/내용/담당). 5건 이하면 표, 많으면 국가별 그룹화.

# 7. 🌏 국가별 활동
해외 매장/국가가 언급된 항목 그룹화. (없으면 생략)

# 8. 📌 다음주 우선순위
top 3 — 사용자가 가장 신경 써야 할 일.

규칙:
- 군더더기·인사말 없음
- 한국어, 고유명사 원문 유지
- 데이터가 없는 섹션은 "(해당 없음)" 한 줄로 짧게 처리
- 전체 1~2페이지 분량
- 일정/task 모두 0건이면 "지난주는 기록된 활동이 없습니다" 한 줄로 끝"""


@dataclass
class ReportResult:
    week_label: str
    doc_link: str
    doc_name: str
    summary_preview: str
    event_count: int
    completed_task_count: int
    open_task_count: int


def _previous_week_bounds(now: datetime) -> tuple[datetime, datetime]:
    """Return (Monday 00:00, Sunday 23:59:59) of the week BEFORE `now`."""
    this_monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    last_monday = this_monday - timedelta(days=7)
    last_sunday_end = this_monday - timedelta(seconds=1)
    return last_monday, last_sunday_end


def _gather_tasks(
    tasks: Tasks, week_start: datetime, week_end: datetime, now: datetime
) -> dict:
    """Categorize tasks: completed_last_week, open, overdue, new_this_week."""
    # Completed in [week_start, week_end] — needs RFC 3339 with UTC offset
    completed = tasks.list_tasks(
        completed_min=week_start.isoformat(),
        completed_max=week_end.isoformat(),
        max_results=100,
    )
    open_tasks = tasks.list_tasks(show_completed=False, max_results=100)

    overdue = [t for t in open_tasks if is_overdue(t, now)]
    overdue_ids = {t["id"] for t in overdue}
    in_progress = [t for t in open_tasks if t["id"] not in overdue_ids]

    # "Created during the report week" — Google Tasks doesn't expose
    # createdAt directly via list, so we approximate "new this week"
    # by the `updated` timestamp falling inside the week.
    new_this_week = []
    for t in open_tasks:
        u = t.get("updated")
        if not u:
            continue
        try:
            ut = datetime.fromisoformat(u.replace("Z", "+00:00"))
        except ValueError:
            continue
        if week_start <= ut <= week_end:
            new_this_week.append(t)

    return {
        "completed_last_week": completed,
        "in_progress": in_progress,
        "overdue": overdue,
        "new_last_week": new_this_week,
    }


def generate(
    calendar: Calendar,
    drive: Drive,
    tasks: Tasks,
    airwallex: Airwallex | None = None,
) -> ReportResult:
    tz = ZoneInfo(config.DEFAULT_TIMEZONE)
    now = datetime.now(tz)
    monday, sunday_end = _previous_week_bounds(now)
    week_label = (
        f"{monday.strftime('%Y-%m-%d')} ~ "
        f"{sunday_end.strftime('%Y-%m-%d')} (지난주)"
    )

    logger.info("Generating previous-week report for %s", week_label)

    events = calendar.list_events(
        time_min=monday.isoformat(),
        time_max=sunday_end.isoformat(),
        max_results=100,
    )

    try:
        task_data = _gather_tasks(tasks, monday, sunday_end, now)
    except Exception:
        logger.exception("Failed to gather tasks for weekly report")
        task_data = {
            "completed_last_week": [],
            "in_progress": [],
            "overdue": [],
            "new_last_week": [],
            "_error": "Google Tasks 조회 실패",
        }

    completed_count = len(task_data["completed_last_week"])
    open_count = len(task_data["in_progress"]) + len(task_data["overdue"])
    has_any = bool(events) or completed_count or open_count

    if not has_any:
        summary_md = "지난주는 기록된 활동이 없습니다 (일정·업무 모두 0건)."
    else:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        report_model = "claude-sonnet-4-6"
        payload = {
            "week_label": week_label,
            "events_count": len(events),
            "events": events,
            "tasks": task_data,
        }
        response = client.messages.create(
            model=report_model,
            max_tokens=4096,
            system=REPORT_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"주간 기간: {week_label} (KST)\n"
                        f"일정 {len(events)}건 / 완료 task {completed_count}건 "
                        f"/ 진행중 task {open_count}건 "
                        f"(지연 {len(task_data['overdue'])}건)\n\n"
                        f"데이터:\n"
                        f"{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}"
                    ),
                }
            ],
        )
        summary_md = "\n".join(
            b.text for b in response.content if b.type == "text"
        ).strip()

    finance_md = ""
    if airwallex is not None:
        finance = finance_report.generate_markdown(airwallex, monday, sunday_end)
        finance_md = "\n\n---\n\n" + finance.markdown

    doc_title = (
        f"주간리포트(지난주) {monday.strftime('%Y.%m.%d')}~"
        f"{sunday_end.strftime('%m.%d')}"
    )
    doc_body = (
        f"# {doc_title}\n\n"
        f"**작성 시각:** {now.strftime('%Y-%m-%d %H:%M')} KST\n"
        f"**일정:** {len(events)}건  |  "
        f"**완료 업무:** {completed_count}건  |  "
        f"**진행중 업무:** {open_count}건 "
        f"(지연 {len(task_data['overdue'])}건)\n\n"
        f"---\n\n"
        f"{summary_md}"
        f"{finance_md}\n"
    )

    uploaded = drive.upload_markdown_as_doc(doc_title, doc_body)
    logger.info("Uploaded weekly report: %s", uploaded["link"])

    preview = summary_md if len(summary_md) <= 600 else summary_md[:600] + "..."
    return ReportResult(
        week_label=week_label,
        doc_link=uploaded["link"],
        doc_name=uploaded["name"],
        summary_preview=preview,
        event_count=len(events),
        completed_task_count=completed_count,
        open_task_count=open_count,
    )
