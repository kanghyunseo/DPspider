"""Claude-powered scheduling agent (manual tool-use loop)."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import anthropic

from . import config, knowledge, recurring_tasks, storage, txn_classifier
from .airwallex_client import Airwallex
from .gcal import Calendar
from .gtasks import Tasks

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """당신은 올에프인비(All F&B) 글로벌사업팀장을 돕는 업무 비서입니다.

주요 역할:
- 팀장의 지시를 받아 Google Calendar에 일정을 등록/수정/삭제/조회
- **Google Tasks로 진행중 업무·할 일 관리** (생성/조회/완료/수정)
- 해외 직영/가맹 매장 관리 업무(리뷰 분석, 마케팅, 회계) 관련 스케줄링
- **첨부된 이미지·PDF (항공권, 호텔 바우처, 회의 문서 등)에서 일정 정보를 추출해 자동 등록**
- 한국어로 자연스럽게 대화. 필요시 영문 용어(매장명, 국가명 등) 섞어 사용

도구 선택 가이드:
- **고정된 시각**(미팅, 출장, 약속) → create_event (캘린더)
- **마감일이 있는 업무**(보고서 작성, 계약 체결, 자료 준비) → create_task
- 일정과 업무를 헷갈리면 사용자에게 어느 쪽인지 확인

일정 처리 규칙:
- 날짜/시간은 한국 시간대(Asia/Seoul) 기준. "내일", "다음주 월요일" 등 상대 표현은 각 메시지 상단에 제공되는 [현재 시각] 기준으로 계산
- 종료 시간이 명시되지 않으면 기본 1시간으로 설정
- 일정을 만들 때 description에 맥락(담당 매장/국가/업무 종류, 예약번호 등)을 반드시 기록
- 일정 조회 결과가 많으면 한국 시간으로 보기 좋게 포맷하여 요약 (예: "4/22(화) 14:00-15:00 싱가포르 매장 리뷰")

지식베이스(RAG) 활용:
- 사용자 질문이 "지난번 베트남 가맹 계약 조건이 뭐였지?", "ABC 인테리어 업체랑 마지막에 합의한 단가가?", "싱가포르 노무 규정" 처럼 **과거 정보 회상**이면 → 답변 전에 knowledge_search 우선 호출
- 검색 결과가 있으면 그걸 근거로 답하고 [#id] 형태로 출처 표시
- 검색 결과가 없거나 약한 매칭만 있으면 솔직히 "지식베이스에 관련 정보가 없습니다" 답변
- 사용자가 "이거 기억해둬", "지식베이스에 저장", "정리해서 저장" 식이면 → knowledge_add. 제목은 짧고 명확하게, content는 충분히 상세하게, tags는 검색에 도움될 키워드(국가/매장/주제) 콤마 구분

자금/회계 조회 (Airwallex):
- "이번달 잔액", "USD 잔고 얼마야?" → airwallex_balances
- "이번달 거래내역 카테고리별로", "지난주 입출금 합계" → airwallex_summary (from_date~to_date, KST 기준 YYYY-MM-DD)
- "지난달 급여 총액", "이번달 식자재 비용 얼마?" → airwallex_summary 에 category 지정 (급여/원자재/식자재/임대료/공과금/마케팅/광고/인쇄/디자인/운송/물류/컨설팅/용역/장비/비품/수수료/환불/매출정산/내부이체/기타)
- "이번달 가장 큰 출금 5개", "최근 큰 입금 내역" → airwallex_top_transactions (direction=out/in/all, top_n)
- 결과 보고시 통화별로 정리하고, 큰 금액은 천 단위 콤마 표시. 필요시 KRW 환산은 추정치임을 명시
- 날짜는 항상 KST 기준으로 해석. "이번달" = 1일~오늘, "지난달" = 전월 1일~말일, "이번주" = 월요일~오늘

반복 일정/업무 처리:
- "매주 월요일 9시 직영점 매출 체크 미팅" 같은 반복 일정 → create_event 에 recurrence=['RRULE:FREQ=WEEKLY;BYDAY=MO']
- "매일 오후 6시 일일 마감 정산", "매월 1일 임대료 송금 확인" 등 자주 쓰는 RRULE:
  - 매일: ['RRULE:FREQ=DAILY']
  - 매주 평일: ['RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR']
  - 매월 N일: ['RRULE:FREQ=MONTHLY;BYMONTHDAY=N']
- "매주 금요일 주간 매출 정리하는 업무 등록" → add_recurring_task(rule='WEEKLY:FR', due_offset_days=0)
  - rule 형식: 'DAILY' / 'WEEKLY:MO,WE,FR' / 'MONTHLY:1' / 'MONTHLY:LAST'

업무(Task) 처리 규칙:
- 업무 제목 앞에는 담당 국가/매장 이모지(🇸🇬🇻🇳🇯🇵🇺🇸🇮🇩 등) 또는 키워드를 붙여 한눈에 식별 가능하게 (예: "🇸🇬 싱가포르 2호점 인테리어 견적 검토")
- **마감일(due)은 항상 `YYYY-MM-DDT00:00:00Z` (UTC 자정) 형식으로 보낼 것**. Google Tasks는 due를 UTC 날짜로만 저장하므로 KST 자정(`+09:00`)으로 보내면 하루 밀려서 저장됨. 예: 4월 30일 마감 → `2026-04-30T00:00:00Z`
- notes(설명)에 진행 상황·관련 매장·블로커·다음 액션을 기록. 진행률 업데이트 시 notes 끝에 "[YYYY-MM-DD] 진행 60% — XX 완료, YY 대기" 형식으로 누적
- "X 완료" / "X 끝났어" → list_tasks로 매칭되는 task 찾아 complete_task
- "X 진행 50%로 업데이트" → list_tasks로 찾아서 update_task로 notes에 추가
- 막연한 "할 일 보여줘" → list_tasks(show_completed=False) 후 마감 임박순 정렬해서 보고

첨부 파일 처리 규칙:
- **항공권**: 편명/출발지/도착지/시간을 추출. 표시된 시간은 **각 공항의 현지 시간**임에 유의 — start/end_datetime의 timezone offset은 공항 IATA 코드 기준으로 정확히 지정 (예: ICN=+09:00, SIN=+08:00, NRT=+09:00, JFK=-04:00 등). 일정 제목은 "✈️ [편명] [출발]→[도착]" 형식. description에 편명, 좌석, 예약번호, 터미널 등 보존. 왕복이면 출발편/귀국편 각각 등록.
- **호텔 바우처**: 호텔명, 체크인/체크아웃 날짜를 추출. 체크인일 15:00부터 체크아웃일 11:00까지의 일정으로 등록 (현지 시간 기준). 제목 "🏨 [호텔명] ([도시])". description에 주소, 예약번호, 객실 타입 보존.
- **회의 초대장/문서**: 회의명, 일시, 장소, 참석자를 추출해 일정 등록.
- 파일에서 정보를 명확히 읽을 수 없거나 모호한 부분은 추측하지 말고 어떤 정보가 누락됐는지 보고 후 사용자에게 확인.
- 등록 후 어떤 일정을 어떻게 만들었는지 한 줄 요약으로 보고.

응답 스타일:
- 간결하게, 실행 결과 위주로 보고
- 불필요한 인사말·사족 생략
- 사용자가 명확히 지시한 경우 확인 없이 바로 실행하고 결과만 보고
- 애매한 경우에만 되물음

⚠️ 절대 규칙 (환각 금지):
- "등록/생성/변경/수정/삭제/완료처리" 같은 **변경 액션을 보고할 때는 반드시 해당 툴을 먼저 호출**해야 합니다. 툴 호출 없이 "✓ 완료" / "등록했습니다" / "변경했습니다" 같은 표현을 사용하는 것은 사실상 거짓말이며 절대 금지.
- 툴 호출 결과로 받은 실제 데이터(event id, 실제 등록된 시각)만 보고. 추측 금지.
- 툴이 에러를 반환하면 그 에러를 그대로 사용자에게 보여주고, 성공한 척 하지 말 것.
- 등록·변경 작업이 여러 건이면 각각 개별 툴 호출. 한 번의 텍스트 응답으로 여러 건 등록한 척 하면 안 됨."""


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
                    "recurrence": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "RFC 5545 RRULE 문자열 배열로 반복 규칙 지정. 예: "
                            "['RRULE:FREQ=WEEKLY;BYDAY=MO'] = 매주 월요일, "
                            "['RRULE:FREQ=DAILY;COUNT=5'] = 매일 5회, "
                            "['RRULE:FREQ=MONTHLY;BYMONTHDAY=1'] = 매월 1일"
                        ),
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
        # ---------- Google Tasks ----------
        {
            "name": "create_task",
            "description": (
                "Google Tasks에 새 업무(할 일)를 추가합니다. "
                "마감일이 있으면 due 에 RFC 3339 형식으로 (시간은 무시되고 날짜만 저장됨)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "업무 제목 (담당 국가 이모지 권장)",
                    },
                    "notes": {
                        "type": "string",
                        "description": "설명/맥락/진행 상황",
                    },
                    "due": {
                        "type": "string",
                        "description": "마감일 RFC 3339 (예: 2026-04-30T00:00:00+09:00)",
                    },
                },
                "required": ["title"],
            },
        },
        {
            "name": "list_tasks",
            "description": (
                "할 일 목록을 조회합니다. "
                "show_completed=False(기본): 미완료만. "
                "completed_min/completed_max(RFC 3339)로 완료된 task 필터 가능."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "show_completed": {
                        "type": "boolean",
                        "description": "완료된 task도 포함할지",
                        "default": False,
                    },
                    "completed_min": {
                        "type": "string",
                        "description": "이 시각 이후 완료된 task만 (RFC 3339)",
                    },
                    "completed_max": {
                        "type": "string",
                        "description": "이 시각 이전 완료된 task만 (RFC 3339)",
                    },
                    "due_min": {"type": "string"},
                    "due_max": {"type": "string"},
                },
            },
        },
        {
            "name": "complete_task",
            "description": (
                "task를 완료 처리합니다. task_id는 list_tasks 로 먼저 찾아두세요."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"task_id": {"type": "string"}},
                "required": ["task_id"],
            },
        },
        {
            "name": "update_task",
            "description": (
                "task의 제목/메모/마감일/상태 수정. "
                "task_id는 list_tasks 로 먼저 조회. "
                "status 는 'needsAction' 또는 'completed'."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "title": {"type": "string"},
                    "notes": {"type": "string"},
                    "due": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["needsAction", "completed"],
                    },
                },
                "required": ["task_id"],
            },
        },
        {
            "name": "delete_task",
            "description": (
                "task를 영구 삭제합니다. 잘못 만든 task가 아니면 보통 "
                "complete_task 를 사용하세요."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"task_id": {"type": "string"}},
                "required": ["task_id"],
            },
        },
        # ---------- Recurring Task templates ----------
        {
            "name": "add_recurring_task",
            "description": (
                "주기적으로 자동 생성되는 업무 템플릿을 추가합니다. "
                "매일 새벽 1시에 룰 매칭되는 템플릿이 새 Google Task로 생성됨. "
                "rule 형식: 'DAILY' / 'WEEKLY:MO,TU,...' / 'MONTHLY:1' / 'MONTHLY:LAST'. "
                "due_offset_days=0이면 생성일 마감, 7이면 일주일 후 마감."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "rule": {"type": "string"},
                    "notes": {"type": "string"},
                    "due_offset_days": {"type": "integer", "default": 0},
                },
                "required": ["title", "rule"],
            },
        },
        {
            "name": "list_recurring_tasks",
            "description": "등록된 반복 업무 템플릿 전체 조회.",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "delete_recurring_task",
            "description": (
                "반복 업무 템플릿을 삭제합니다. 이미 생성된 Task는 영향 없음. "
                "template_id는 list_recurring_tasks 로 먼저 조회."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"template_id": {"type": "integer"}},
                "required": ["template_id"],
            },
        },
        # ---------- Knowledge base (RAG) ----------
        {
            "name": "knowledge_add",
            "description": (
                "지식베이스에 문서를 추가합니다. 계약 조건/매뉴얼/회의록/벤더 정보 등 "
                "나중에 검색해서 활용할 정보. 의미 기반 검색이 가능하도록 임베딩이 자동 저장됨."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "짧고 명확한 제목 (예: '베트남 1호점 임대 계약')",
                    },
                    "content": {
                        "type": "string",
                        "description": "본문 내용. 충분히 상세하게.",
                    },
                    "tags": {
                        "type": "string",
                        "description": (
                            "콤마 구분 태그 (예: '베트남,임대,계약'). "
                            "검색 시 필터로 사용 가능. 옵션."
                        ),
                    },
                },
                "required": ["title", "content"],
            },
        },
        {
            "name": "knowledge_search",
            "description": (
                "지식베이스를 의미 기반으로 검색합니다. "
                "질문이나 키워드를 query에 넣으면 가장 관련 있는 문서 top_k개 반환. "
                "사용자 질문에 답하기 전에 관련 정보가 있을 만하면 우선 호출하세요."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "검색 질의"},
                    "top_k": {"type": "integer", "default": 5},
                    "tag": {
                        "type": "string",
                        "description": "특정 태그로 결과 필터 (옵션)",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "knowledge_list",
            "description": "최근 등록된 지식베이스 항목 목록 (제목·태그만).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 20},
                },
            },
        },
        {
            "name": "knowledge_delete",
            "description": "지식베이스 항목 삭제. id는 knowledge_list 로 먼저 조회.",
            "input_schema": {
                "type": "object",
                "properties": {"entry_id": {"type": "integer"}},
                "required": ["entry_id"],
            },
        },
        # ---------- Airwallex (finance) ----------
        {
            "name": "airwallex_balances",
            "description": (
                "Airwallex 모든 통화별 현재 잔액을 조회합니다. "
                "0인 통화는 자동 제외. Airwallex 미설정 시 에러."
            ),
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "airwallex_summary",
            "description": (
                "특정 기간의 거래내역을 카테고리·통화별로 집계합니다. "
                "from_date / to_date 는 KST 기준 'YYYY-MM-DD' (포함). "
                "category 가 주어지면 해당 비즈니스 카테고리만 합산. "
                "결과: 총 입/출금, 순액, 카테고리별 breakdown, 통화별 breakdown."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "from_date": {
                        "type": "string",
                        "description": "조회 시작일 (KST, YYYY-MM-DD, 포함)",
                    },
                    "to_date": {
                        "type": "string",
                        "description": "조회 종료일 (KST, YYYY-MM-DD, 포함)",
                    },
                    "category": {
                        "type": "string",
                        "description": (
                            "비즈니스 카테고리 필터 (옵션). "
                            "급여, 원자재/식자재, 임대료, 공과금, 마케팅/광고, "
                            "인쇄/디자인, 운송/물류, 컨설팅/용역, 장비/비품, "
                            "수수료, 환불, 매출정산, 내부이체, 기타"
                        ),
                    },
                },
                "required": ["from_date", "to_date"],
            },
        },
        {
            "name": "airwallex_top_transactions",
            "description": (
                "특정 기간 가장 큰 거래 N건을 반환합니다. "
                "direction='out' = 출금만, 'in' = 입금만, 'all' = 절대값 기준."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "from_date": {
                        "type": "string",
                        "description": "조회 시작일 (KST, YYYY-MM-DD, 포함)",
                    },
                    "to_date": {
                        "type": "string",
                        "description": "조회 종료일 (KST, YYYY-MM-DD, 포함)",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["in", "out", "all"],
                        "default": "all",
                    },
                    "top_n": {"type": "integer", "default": 10},
                },
                "required": ["from_date", "to_date"],
            },
        },
        {
            "name": "airwallex_list_by_category",
            "description": (
                "특정 카테고리의 거래 내역 raw 목록을 반환합니다 "
                "(vendor·금액·날짜). 'X 업체에 얼마 보냈었지?' 같은 상세 질의용."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "from_date": {"type": "string"},
                    "to_date": {"type": "string"},
                    "category": {
                        "type": "string",
                        "description": "필수. 비즈니스 카테고리명",
                    },
                    "limit": {"type": "integer", "default": 30},
                },
                "required": ["from_date", "to_date", "category"],
            },
        },
    ]


class Assistant:
    def __init__(
        self,
        calendar: Calendar,
        tasks: Tasks,
        airwallex: Airwallex | None = None,
    ):
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.calendar = calendar
        self.tasks = tasks
        self.airwallex = airwallex
        self.tools = build_tools()

    # ---------- Airwallex helpers ----------

    def _kst_range_to_utc(
        self, from_date: str, to_date: str
    ) -> tuple[datetime, datetime]:
        """Inclusive KST date range → UTC datetime [start, end_exclusive)."""
        tz = ZoneInfo(config.DEFAULT_TIMEZONE)
        start_kst = datetime.fromisoformat(from_date).replace(tzinfo=tz)
        end_kst = (
            datetime.fromisoformat(to_date).replace(tzinfo=tz)
            + timedelta(days=1)
        )
        return (
            start_kst.astimezone(ZoneInfo("UTC")),
            end_kst.astimezone(ZoneInfo("UTC")),
        )

    def _signed_amount(self, t: dict) -> float:
        """Positive = inflow, negative = outflow."""
        amt = float(t.get("amount") or 0)
        ttype = (t.get("transaction_type") or "").upper()
        # Heuristic: DEPOSIT-like → positive, others (PAYOUT, FEE, CARD_CAPTURE, REFUND_OUT) → negative
        if ttype in ("DEPOSIT", "INCOMING_FUND", "REFUND_IN", "RELEASE"):
            return abs(amt)
        if ttype in ("PAYOUT", "FEE", "CARD_CAPTURE", "REFUND_OUT", "HOLD"):
            return -abs(amt)
        # Fallback to sign of source amount
        return amt

    def _execute_tool(self, name: str, tool_input: dict) -> dict | list[dict]:
        # Always log the call so we can audit "did the bot actually do X?".
        # Truncate input preview to avoid leaking huge payloads to logs.
        try:
            input_preview = json.dumps(
                tool_input, ensure_ascii=False, default=str
            )[:500]
        except Exception:
            input_preview = repr(tool_input)[:500]
        logger.info("Tool call → %s | input=%s", name, input_preview)
        result = self._execute_tool_inner(name, tool_input)
        try:
            result_preview = json.dumps(
                result, ensure_ascii=False, default=str
            )[:500]
        except Exception:
            result_preview = repr(result)[:500]
        logger.info("Tool result ← %s | %s", name, result_preview)
        return result

    def _execute_tool_inner(
        self, name: str, tool_input: dict
    ) -> dict | list[dict]:
        try:
            if name == "create_event":
                return self.calendar.create_event(**tool_input)
            if name == "list_events":
                return self.calendar.list_events(**tool_input)
            if name == "update_event":
                return self.calendar.update_event(**tool_input)
            if name == "delete_event":
                return self.calendar.delete_event(**tool_input)
            if name == "create_task":
                return self.tasks.create_task(**tool_input)
            if name == "list_tasks":
                return self.tasks.list_tasks(**tool_input)
            if name == "complete_task":
                return self.tasks.complete_task(**tool_input)
            if name == "update_task":
                return self.tasks.update_task(**tool_input)
            if name == "delete_task":
                return self.tasks.delete_task(**tool_input)
            if name == "add_recurring_task":
                tpl_id = recurring_tasks.add_template(**tool_input)
                return {"template_id": tpl_id, "message": "반복 템플릿 추가됨"}
            if name == "list_recurring_tasks":
                return [
                    {
                        "id": t.id,
                        "title": t.title,
                        "rule": t.rule,
                        "due_offset_days": t.due_offset_days,
                        "last_run_date": t.last_run_date,
                        "notes": t.notes,
                    }
                    for t in recurring_tasks.list_templates()
                ]
            if name == "delete_recurring_task":
                ok = recurring_tasks.delete_template(tool_input["template_id"])
                return {"deleted": ok}
            if name == "knowledge_add":
                kid = knowledge.add_entry(**tool_input)
                return {"id": kid, "message": "지식베이스에 추가됨"}
            if name == "knowledge_search":
                results = knowledge.search(**tool_input)
                return [
                    {
                        "id": r.id,
                        "title": r.title,
                        "content": r.content,
                        "tags": r.tags,
                        "similarity": r.similarity,
                    }
                    for r in results
                ]
            if name == "knowledge_list":
                limit = tool_input.get("limit", 20)
                return [
                    {
                        "id": e.id,
                        "title": e.title,
                        "tags": e.tags,
                        "created_at": e.created_at,
                    }
                    for e in knowledge.list_entries(limit=limit)
                ]
            if name == "knowledge_delete":
                ok = knowledge.delete_entry(tool_input["entry_id"])
                return {"deleted": ok}
            if name == "airwallex_balances":
                if not self.airwallex:
                    return {"error": "Airwallex 미설정"}
                balances = self.airwallex.get_balances()
                # Filter zero balances, return only relevant fields
                out = []
                for b in balances:
                    avail = float(b.get("available_amount") or 0)
                    pending = float(b.get("pending_amount") or 0)
                    total = float(b.get("total_amount") or (avail + pending))
                    if avail == 0 and pending == 0 and total == 0:
                        continue
                    out.append(
                        {
                            "currency": b.get("currency"),
                            "available": avail,
                            "pending": pending,
                            "total": total,
                        }
                    )
                return out
            if name in (
                "airwallex_summary",
                "airwallex_top_transactions",
                "airwallex_list_by_category",
            ):
                if not self.airwallex:
                    return {"error": "Airwallex 미설정"}
                from_dt, to_dt = self._kst_range_to_utc(
                    tool_input["from_date"], tool_input["to_date"]
                )
                txns = self.airwallex.list_transactions(from_dt, to_dt)

                if name == "airwallex_summary":
                    cat_filter = tool_input.get("category")
                    cats = txn_classifier.classify(txns) if txns else {}
                    by_cat: dict[str, dict] = {}
                    by_ccy_in: dict[str, float] = {}
                    by_ccy_out: dict[str, float] = {}
                    count = 0
                    for t in txns:
                        signed = self._signed_amount(t)
                        ccy = t.get("currency") or "?"
                        info = cats.get(t.get("id"), {})
                        cat = info.get("category", "기타")
                        if cat_filter and cat != cat_filter:
                            continue
                        count += 1
                        if signed >= 0:
                            by_ccy_in[ccy] = by_ccy_in.get(ccy, 0) + signed
                        else:
                            by_ccy_out[ccy] = by_ccy_out.get(ccy, 0) + abs(signed)
                        slot = by_cat.setdefault(
                            cat, {"in": {}, "out": {}, "count": 0}
                        )
                        slot["count"] += 1
                        target = slot["in"] if signed >= 0 else slot["out"]
                        target[ccy] = target.get(ccy, 0) + abs(signed)
                    return {
                        "period_kst": f"{tool_input['from_date']} ~ {tool_input['to_date']}",
                        "transaction_count": count,
                        "category_filter": cat_filter,
                        "inflow_by_currency": by_ccy_in,
                        "outflow_by_currency": by_ccy_out,
                        "by_category": by_cat,
                    }

                if name == "airwallex_top_transactions":
                    direction = tool_input.get("direction", "all")
                    top_n = tool_input.get("top_n", 10)
                    cats = txn_classifier.classify(txns) if txns else {}
                    enriched = []
                    for t in txns:
                        signed = self._signed_amount(t)
                        if direction == "in" and signed <= 0:
                            continue
                        if direction == "out" and signed >= 0:
                            continue
                        info = cats.get(t.get("id"), {})
                        enriched.append(
                            {
                                "date": (t.get("created_at") or "")[:10],
                                "amount": signed,
                                "currency": t.get("currency"),
                                "description": (t.get("description") or "")[:120],
                                "category": info.get("category"),
                                "vendor": info.get("vendor"),
                                "transaction_type": t.get("transaction_type"),
                            }
                        )
                    enriched.sort(key=lambda x: abs(x["amount"]), reverse=True)
                    return enriched[:top_n]

                # airwallex_list_by_category
                cat_target = tool_input["category"]
                limit = tool_input.get("limit", 30)
                cats = txn_classifier.classify(txns) if txns else {}
                items = []
                for t in txns:
                    info = cats.get(t.get("id"), {})
                    if info.get("category") != cat_target:
                        continue
                    signed = self._signed_amount(t)
                    items.append(
                        {
                            "date": (t.get("created_at") or "")[:10],
                            "amount": signed,
                            "currency": t.get("currency"),
                            "vendor": info.get("vendor"),
                            "description": (t.get("description") or "")[:120],
                        }
                    )
                items.sort(key=lambda x: x["date"], reverse=True)
                return items[:limit]
            return {"error": f"Unknown tool: {name}"}
        except Exception as e:
            logger.exception("Tool execution failed: %s", name)
            return {"error": f"{type(e).__name__}: {e}"}

    def process_message(
        self,
        user_id: int,
        user_text: str,
        attachments: list[dict] | None = None,
        max_iterations: int = 10,
    ) -> str:
        """Process a user message, optionally with image/PDF attachments.

        attachments: list of pre-built Anthropic content blocks
            (type='image' or type='document').
        """
        history = storage.load_history(config.DB_PATH, user_id, config.HISTORY_LIMIT)

        now = datetime.now(ZoneInfo(config.DEFAULT_TIMEZONE))
        weekday_kr = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]
        contextualized = (
            f"[현재 시각: {now.strftime('%Y-%m-%d %H:%M')} KST ({weekday_kr})]\n\n"
            f"{user_text}"
        )

        if attachments:
            user_content: str | list[dict] = [
                *attachments,
                {"type": "text", "text": contextualized},
            ]
        else:
            user_content = contextualized

        messages: list[dict] = history + [
            {"role": "user", "content": user_content}
        ]

        final_text = ""
        tool_calls_made = 0  # Track over the whole turn for hallucination check
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
                # Hallucination guard: if the model claims to have made a
                # change ("등록했습니다", "변경했습니다" 등) but never
                # invoked any tool this turn, flag it loudly so the user
                # doesn't trust a fabricated success.
                action_markers = (
                    "등록했", "등록 완료", "등록완료", "추가했",
                    "변경했", "수정했", "삭제했", "완료처리",
                    "✓ 완료", "완료했습니다", "생성했", "만들었",
                )
                if (
                    tool_calls_made == 0
                    and final_text
                    and any(m in final_text for m in action_markers)
                ):
                    logger.error(
                        "HALLUCINATION SUSPECTED: assistant claims an "
                        "action without any tool call. user_id=%s, "
                        "user_text=%r, reply=%r",
                        user_id,
                        user_text[:200],
                        final_text[:300],
                    )
                    final_text = (
                        "⚠️ 시스템 오류 — 작업을 실제로 수행하지 못했는데 "
                        "성공 메시지를 생성하려 했습니다. 다시 시도해 "
                        "주세요. (이 오류는 자동으로 기록됩니다.)\n\n"
                        f"원래 응답:\n{final_text}"
                    )
                break

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        tool_calls_made += 1
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
