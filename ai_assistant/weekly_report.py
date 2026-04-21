"""Weekly report generator.

Queries this week's Calendar events, summarizes via Claude, uploads
the result to Google Drive as a Google Doc, and returns metadata for
Telegram delivery.
"""
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

logger = logging.getLogger(__name__)


REPORT_SYSTEM_PROMPT = """당신은 올에프인비(All F&B) 글로벌사업팀장의 주간 리포트 작성 비서입니다.

사용자가 제공하는 JSON 은 이번주 Google Calendar 일정입니다.
이를 바탕으로 **주간회의용 리포트**를 마크다운 형식으로 작성하세요.

포함할 내용:
1. 상단 요약 (3–5줄, 이번주 주요 활동 총괄)
2. 일정 목록 (표 형식: 날짜/시간/내용/담당 국가·매장)
3. 국가별 활동 — 해외 매장/국가가 언급된 경우 그룹화 (없으면 생략)
4. 특이사항·이슈 — 중요 미팅, 팔로우업 필요 항목
5. (가능하면) 다음주 주요 업무 — description 에서 유추 가능한 것

규칙:
- 전체 1–2페이지 분량
- 군더더기·인사말 없음
- 한국어 (매장명·국가명 등 고유명사는 원문 유지)
- 일정이 0건이면 "이번주는 등록된 일정이 없습니다" 한 줄로 끝"""


@dataclass
class ReportResult:
    week_label: str
    doc_link: str
    doc_name: str
    summary_preview: str
    event_count: int


def _week_bounds(now: datetime) -> tuple[datetime, datetime]:
    """Return (Monday 00:00, Sunday 23:59:59) of the week containing `now`."""
    monday = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    sunday_end = monday + timedelta(days=7) - timedelta(seconds=1)
    return monday, sunday_end


def generate(
    calendar: Calendar, drive: Drive, airwallex: Airwallex | None = None
) -> ReportResult:
    tz = ZoneInfo(config.DEFAULT_TIMEZONE)
    now = datetime.now(tz)
    monday, sunday_end = _week_bounds(now)
    week_label = f"{monday.strftime('%Y-%m-%d')} ~ {sunday_end.strftime('%Y-%m-%d')}"

    logger.info("Generating weekly report for %s", week_label)

    events = calendar.list_events(
        time_min=monday.isoformat(),
        time_max=sunday_end.isoformat(),
        max_results=100,
    )

    if not events:
        summary_md = "이번주는 등록된 일정이 없습니다."
    else:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        report_model = "claude-sonnet-4-6"
        response = client.messages.create(
            model=report_model,
            max_tokens=4096,
            system=REPORT_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"주간 기간: {week_label} (KST)\n"
                        f"총 {len(events)}건\n\n"
                        f"일정 데이터:\n"
                        f"{json.dumps(events, ensure_ascii=False, indent=2, default=str)}"
                    ),
                }
            ],
        )
        summary_md = "\n".join(
            b.text for b in response.content if b.type == "text"
        ).strip()

    # Optional: Airwallex finance section
    finance_md = ""
    if airwallex is not None:
        summary = finance_report.generate_markdown(airwallex, monday, sunday_end)
        finance_md = "\n\n---\n\n" + summary.markdown

    doc_title = f"주간리포트 {monday.strftime('%Y.%m.%d')}~{sunday_end.strftime('%m.%d')}"
    doc_body = (
        f"# {doc_title}\n\n"
        f"**작성 시각:** {now.strftime('%Y-%m-%d %H:%M')} KST\n"
        f"**일정 수:** {len(events)}건\n\n"
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
    )
