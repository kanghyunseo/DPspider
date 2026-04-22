"""Claude-powered scheduling agent (manual tool-use loop)."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import anthropic

from . import config, storage
from .gcal import Calendar

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """당신은 올에프인비(All F&B) 글로벌사업팀장을 돕는 업무 비서입니다.

주요 역할:
- 팀장의 지시를 받아 Google Calendar에 일정을 등록/수정/삭제/조회
- 해외 직영/가맹 매장 관리 업무(리뷰 분석, 마케팅, 회계) 관련 스케줄링
- 한국어로 자연스럽게 대화. 필요시 영문 용어(매장명, 국가명 등) 섞어 사용

일정 처리 규칙:
- 날짜/시간은 한국 시간대(Asia/Seoul) 기준. "내일", "다음주 월요일" 등 상대 표현은 각 메시지 상단에 제공되는 [현재 시각] 기준으로 계산
- 종료 시간이 명시되지 않으면 기본 1시간으로 설정
- 일정을 만들 때 description에 맥락(담당 매장/국가/업무 종류)을 반드시 기록
- 일정 조회 결과가 많으면 한국 시간으로 보기 좋게 포맷하여 요약 (예: "4/22(화) 14:00-15:00 싱가포르 매장 리뷰")

응답 스타일:
- 간결하게, 실행 결과 위주로 보고
- 불필요한 인사말·사족 생략
- 사용자가 명확히 지시한 경우 확인 없이 바로 실행하고 결과만 보고
- 애매한 경우에만 되물음"""


def build_tools() -> list[dict]:
    return [
        {
            "name": "create_event",
            "description": (
                "Google Calendar에 새 일정을 생성합니다. "
                "시작/종료 시각은 타임존 포함 ISO 8601 형식 "
                "(예: 2026-04-22T14:00:00+09:00)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "일정 제목"},
                    "start_datetime": {
                        "type": "string",
                        "description": "시작 시각 (ISO 8601 with timezone offset)",
                    },
                    "end_datetime": {
                        "type": "string",
                        "description": "종료 시각 (ISO 8601 with timezone offset)",
                    },
                    "description": {
                        "type": "string",
                        "description": "상세 설명 (담당 국가, 매장, 업무 분류 등)",
                    },
                    "location": {
                        "type": "string",
                        "description": "장소 또는 화상회의 링크",
                    },
                    "attendees": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "참석자 이메일 주소 목록",
                    },
                },
                "required": ["summary", "start_datetime", "end_datetime"],
            },
        },
        {
            "name": "list_events",
            "description": "특정 기간의 일정을 조회합니다. 조회 후 사용자에게 한국어로 요약해서 전달하세요.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "time_min": {
                        "type": "string",
                        "description": "조회 시작 시각 (ISO 8601 with timezone)",
                    },
                    "time_max": {
                        "type": "string",
                        "description": "조회 종료 시각 (ISO 8601 with timezone)",
                    },
                    "max_results": {"type": "integer", "default": 20},
                    "query": {
                        "type": "string",
                        "description": "제목·설명 검색 키워드 (선택)",
                    },
                },
                "required": ["time_min", "time_max"],
            },
        },
        {
            "name": "update_event",
            "description": (
                "기존 일정을 수정합니다. event_id는 list_events로 먼저 조회해서 찾으세요."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string"},
                    "summary": {"type": "string"},
                    "start_datetime": {"type": "string"},
                    "end_datetime": {"type": "string"},
                    "description": {"type": "string"},
                    "location": {"type": "string"},
                },
                "required": ["event_id"],
            },
        },
        {
            "name": "delete_event",
            "description": (
                "일정을 삭제합니다. event_id는 list_events로 먼저 조회해서 찾으세요."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"event_id": {"type": "string"}},
                "required": ["event_id"],
            },
        },
    ]


class Assistant:
    def __init__(self, calendar: Calendar):
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.calendar = calendar
        self.tools = build_tools()

    def _execute_tool(self, name: str, tool_input: dict) -> dict | list[dict]:
        try:
            if name == "create_event":
                return self.calendar.create_event(**tool_input)
            if name == "list_events":
                return self.calendar.list_events(**tool_input)
            if name == "update_event":
                return self.calendar.update_event(**tool_input)
            if name == "delete_event":
                return self.calendar.delete_event(**tool_input)
            return {"error": f"Unknown tool: {name}"}
        except Exception as e:
            logger.exception("Tool execution failed: %s", name)
            return {"error": f"{type(e).__name__}: {e}"}

    def process_message(
        self, user_id: int, user_text: str, max_iterations: int = 10
    ) -> str:
        history = storage.load_history(config.DB_PATH, user_id, config.HISTORY_LIMIT)

        now = datetime.now(ZoneInfo(config.DEFAULT_TIMEZONE))
        weekday_kr = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]
        contextualized = (
            f"[현재 시각: {now.strftime('%Y-%m-%d %H:%M')} KST ({weekday_kr})]\n\n"
            f"{user_text}"
        )
        messages: list[dict] = history + [
            {"role": "user", "content": contextualized}
        ]

        final_text = ""
        for _ in range(max_iterations):
            response = self.client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=self.tools,
                messages=messages,
            )

            messages.append(
                {
                    "role": "assistant",
                    "content": [b.model_dump() for b in response.content],
                }
            )

            if response.stop_reason == "end_turn":
                final_text = "\n".join(
                    b.text for b in response.content if b.type == "text"
                ).strip()
                break

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = self._execute_tool(block.name, block.input)
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": json.dumps(
                                    result, ensure_ascii=False, default=str
                                ),
                            }
                        )
                messages.append({"role": "user", "content": tool_results})
                continue

            logger.warning("Unexpected stop_reason: %s", response.stop_reason)
            final_text = "⚠️ 응답을 처리할 수 없습니다."
            break
        else:
            final_text = "⚠️ 최대 처리 반복 횟수를 초과했습니다."

        storage.append_message(config.DB_PATH, user_id, "user", user_text)
        storage.append_message(
            config.DB_PATH, user_id, "assistant", final_text or "(응답 없음)"
        )
        return final_text or "(응답이 비어있습니다)"
