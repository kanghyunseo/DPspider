"""Extract proposed calendar events from an image/PDF attachment.

Uses Claude with a single non-side-effecting `propose_event` tool, so
the LLM only describes what it would create — actual Calendar writes
happen later, after the user confirms via inline keyboard buttons.
"""
from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import anthropic

from . import config

logger = logging.getLogger(__name__)


EXTRACT_SYSTEM_PROMPT = """첨부된 이미지/PDF에서 일정 정보(항공권/호텔 \
바우처/회의 문서 등)를 추출하는 비서입니다.

각 일정마다 propose_event 도구를 호출하세요. **실제 캘린더 등록은 \
사용자 확인 후 별도로 진행**되므로 이 단계에서는 propose_event 만 부르면 됩니다.

규칙:
- **항공권**: 편명/출발지/도착지/시간 추출. 표시된 시간은 **각 공항의 \
현지 시간**임에 유의 — start/end_datetime의 timezone offset은 공항 \
IATA 코드 기준으로 정확히 지정 (ICN=+09:00, SIN=+08:00, NRT=+09:00, \
HKG=+08:00, JFK=-04:00, LAX=-07:00 등). 제목 형식: \
"✈️ [편명] [출발]→[도착]". description에 편명/좌석/예약번호/터미널 보존. \
왕복이면 출발편/귀국편 각각 propose_event 1번씩.
- **호텔 바우처**: 호텔명, 체크인/체크아웃 날짜 추출. \
체크인일 15:00 → 체크아웃일 11:00 (현지시간 기준). \
제목 "🏨 [호텔명] ([도시])". description에 주소/예약번호/객실타입 보존.
- **회의 문서/초대장**: 회의명/일시/장소/참석자 추출 → propose_event.

상대 표현은 [현재 시각] 기준으로 계산.
정보가 명확하지 않으면 추측하지 말고 텍스트로 무엇이 모호한지 보고."""


PROPOSE_EVENT_TOOL = {
    "name": "propose_event",
    "description": (
        "추출한 일정 1건을 등록 후보로 제안합니다. "
        "이 도구는 실제 캘린더에 쓰지 않고 사용자 확인용 미리보기만 만듭니다."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "일정 제목"},
            "start_datetime": {
                "type": "string",
                "description": "시작 시각 ISO 8601 with timezone offset",
            },
            "end_datetime": {
                "type": "string",
                "description": "종료 시각 ISO 8601 with timezone offset",
            },
            "description": {
                "type": "string",
                "description": "상세 정보 (편명/예약번호/주소 등)",
            },
            "location": {"type": "string", "description": "장소 (옵션)"},
        },
        "required": ["summary", "start_datetime", "end_datetime"],
    },
}


@dataclass
class ProposedEvent:
    summary: str
    start_datetime: str
    end_datetime: str
    description: str | None = None
    location: str | None = None

    def to_calendar_kwargs(self) -> dict:
        kw: dict = {
            "summary": self.summary,
            "start_datetime": self.start_datetime,
            "end_datetime": self.end_datetime,
        }
        if self.description:
            kw["description"] = self.description
        if self.location:
            kw["location"] = self.location
        return kw


@dataclass
class ExtractionResult:
    events: list[ProposedEvent]
    notes: str  # any free-form remarks Claude added (e.g., what was ambiguous)


def _build_attachment_block(data: bytes, mime: str) -> dict:
    encoded = base64.standard_b64encode(data).decode()
    block_type = "document" if mime == "application/pdf" else "image"
    return {
        "type": block_type,
        "source": {"type": "base64", "media_type": mime, "data": encoded},
    }


def extract_events(
    attachment_bytes: bytes,
    mime: str,
    caption: str | None = None,
    max_iterations: int = 5,
) -> ExtractionResult:
    """Send the attachment to Claude and collect proposed events."""
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    now = datetime.now(ZoneInfo(config.DEFAULT_TIMEZONE))
    weekday_kr = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]
    user_text = caption or "첨부에서 일정 정보를 추출해주세요."
    contextualized = (
        f"[현재 시각: {now.strftime('%Y-%m-%d %H:%M')} KST ({weekday_kr})]\n\n"
        f"{user_text}"
    )

    block = _build_attachment_block(attachment_bytes, mime)
    messages: list[dict] = [
        {
            "role": "user",
            "content": [block, {"type": "text", "text": contextualized}],
        }
    ]

    proposed: list[ProposedEvent] = []
    notes_parts: list[str] = []

    for _ in range(max_iterations):
        response = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=4096,
            system=EXTRACT_SYSTEM_PROMPT,
            tools=[PROPOSE_EVENT_TOOL],
            messages=messages,
        )
        messages.append(
            {
                "role": "assistant",
                "content": [b.model_dump() for b in response.content],
            }
        )

        # Collect any text blocks (notes / clarifications)
        for b in response.content:
            if b.type == "text" and b.text.strip():
                notes_parts.append(b.text.strip())

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "tool_use":
            tool_results = []
            for b in response.content:
                if b.type != "tool_use":
                    continue
                if b.name == "propose_event":
                    try:
                        proposed.append(
                            ProposedEvent(
                                summary=b.input["summary"],
                                start_datetime=b.input["start_datetime"],
                                end_datetime=b.input["end_datetime"],
                                description=b.input.get("description"),
                                location=b.input.get("location"),
                            )
                        )
                        result_text = "제안 기록됨"
                    except KeyError as e:
                        result_text = f"필수 필드 누락: {e}"
                else:
                    result_text = f"알 수 없는 도구: {b.name}"
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": b.id,
                        "content": result_text,
                    }
                )
            messages.append({"role": "user", "content": tool_results})
            continue

        logger.warning(
            "Unexpected stop_reason during extraction: %s", response.stop_reason
        )
        break
    else:
        logger.warning("Hit max_iterations during attachment extraction")

    return ExtractionResult(events=proposed, notes="\n".join(notes_parts).strip())


def format_events_preview(events: list[ProposedEvent]) -> str:
    """Build a Telegram-friendly preview of proposed events."""
    if not events:
        return "(추출된 일정 없음)"
    lines = []
    for i, ev in enumerate(events, 1):
        lines.append(f"{i}. {ev.summary}")
        lines.append(f"   ⏰ {ev.start_datetime}  →  {ev.end_datetime}")
        if ev.location:
            lines.append(f"   📍 {ev.location}")
        if ev.description:
            d = ev.description
            short = d if len(d) <= 200 else d[:200] + "…"
            lines.append(f"   📝 {short}")
        lines.append("")
    return "\n".join(lines).rstrip()
