"""국가별 F&B 트렌드 브리프 — Claude web_search 로 주간 동향 조사."""
import logging
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import anthropic

from . import config
from .gdrive import Drive

logger = logging.getLogger(__name__)


TRENDS_SYSTEM_PROMPT = """당신은 올에프인비(All F&B) 글로벌사업팀장의 \
시장조사 리서치 애널리스트입니다.

주어진 국가들의 지난 1~2주간 외식·F&B 업계 주요 동향을 웹에서 조사하여 \
**주간 트렌드 브리프**를 마크다운으로 작성하세요.

각 국가별 섹션에 다음을 포함:
- 🔥 신규 트렌드 / 떠오르는 메뉴·컨셉 (1~3개)
- 🏢 주요 경쟁사·대형 프랜차이즈 소식 (런칭/철수/증자/M&A 등)
- 👥 소비자 트렌드 변화 (가격 민감도, 배달 vs 매장, 건강지향 등)
- 💡 올에프인비 시사점 (한 줄로 간결하게)

규칙:
- 각 국가 섹션은 `## 🇸🇬 싱가포르` 처럼 국기 이모지 + 국가명으로 시작
- 각 항목에 근거 출처 링크를 `[기사제목](URL)` 형식으로 포함
- 추측 대신 **웹 검색 결과에 근거**해서만 작성. 검색해도 특별한 소식 없으면 "특이사항 없음" 명시
- 전체 2~3페이지 분량. 간결하게
- 맨 앞에 `# 국가별 F&B 주간 트렌드 브리프` 제목 + 작성일
- 마지막에 `## 📌 이번주 포인트` 로 전 국가 걸친 인사이트 3~5개 요약"""


@dataclass
class TrendsResult:
    period_label: str
    doc_link: str
    doc_name: str
    summary_preview: str
    countries: list[str]


def generate(drive: Drive, countries: list[str]) -> TrendsResult:
    if not countries:
        raise RuntimeError("TREND_COUNTRIES 가 비어있습니다.")

    tz = ZoneInfo(config.DEFAULT_TIMEZONE)
    now = datetime.now(tz)
    period_label = now.strftime("%Y-%m-%d")
    logger.info("Generating F&B trends report for: %s", ", ".join(countries))

    user_prompt = (
        f"조사 대상 국가: {', '.join(countries)}\n\n"
        f"위 국가들의 지난 1~2주간 외식·F&B 업계 주요 동향을 웹에서 조사해서 "
        f"주간 트렌드 브리프를 작성해주세요. "
        f"각 국가별로 web_search 툴을 여러 번 사용해도 좋습니다."
    )

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    tools = [
        {"type": "web_search_20260209", "name": "web_search"},
        {"type": "web_fetch_20260209", "name": "web_fetch"},
    ]

    messages: list[dict] = [{"role": "user", "content": user_prompt}]
    final_response = None

    # Server-side web_search loop may hit its internal limit (10 iterations)
    # and return pause_turn. Handle by re-sending and letting the server resume.
    for attempt in range(5):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            system=TRENDS_SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )
        final_response = response

        if response.stop_reason == "pause_turn":
            logger.info("Trends report: pause_turn, resuming (attempt %d)", attempt + 1)
            messages = [
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": response.content},
            ]
            continue

        break

    text = "\n".join(
        b.text for b in final_response.content if b.type == "text"
    ).strip()

    if not text:
        text = "⚠️ 트렌드 조사 결과를 수집하지 못했습니다."

    doc_title = f"F&B 트렌드 브리프 {period_label}"
    uploaded = drive.upload_markdown_as_doc(doc_title, text)
    logger.info("Uploaded trends report: %s", uploaded["link"])

    preview = text if len(text) <= 600 else text[:600] + "..."
    return TrendsResult(
        period_label=period_label,
        doc_link=uploaded["link"],
        doc_name=uploaded["name"],
        summary_preview=preview,
        countries=countries,
    )
