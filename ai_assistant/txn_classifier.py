"""Classify Airwallex transactions into business categories using Claude.

Cached in SQLite (txn_category table) so we only call the API for
transactions we haven't seen before.
"""
from __future__ import annotations

import json
import logging
from typing import Iterable

import anthropic

from . import config, storage

logger = logging.getLogger(__name__)


# Business categories (Korean labels). The classifier picks one per txn.
BUSINESS_CATEGORIES = [
    "급여",        # salary / wage payments to staff
    "원자재/식자재",  # ingredients, raw materials, supplier purchases
    "임대료",       # rent
    "공과금",       # utilities (electric/water/gas/internet)
    "마케팅/광고",  # marketing, ads, promotions
    "인쇄/디자인",  # printing, signage, design
    "운송/물류",    # logistics, shipping, courier
    "컨설팅/용역",  # consulting fees, service fees
    "장비/비품",    # equipment, fixtures, furniture
    "수수료",       # bank/payment fees
    "환불",         # refunds (in or out)
    "매출정산",     # sales settlement (incoming from card processors)
    "내부이체",     # internal transfers between own accounts
    "기타",         # uncategorized
]

CLASSIFY_SYSTEM_PROMPT = (
    "당신은 F&B 회사의 거래내역을 비즈니스 카테고리로 분류하는 회계 보조입니다. "
    "거래 1건당 description, amount, currency, source_type 정보가 주어집니다. "
    "각 거래에 대해 가장 적합한 카테고리 1개를 다음 목록에서 골라주세요:\n"
    + ", ".join(BUSINESS_CATEGORIES)
    + "\n\n"
    "분류 기준:\n"
    "- description 에 'Salary', '급여', '월급', 'Pay XXX (Salary...)' → 급여\n"
    "- 'Pay to [업체명]' + 식자재/원료/메뉴 관련 키워드 → 원자재/식자재\n"
    "- '임대', 'rent', 'Lease' → 임대료\n"
    "- '인쇄', 'Print', '디자인', '메뉴판' → 인쇄/디자인\n"
    "- 'Marketing', '광고', 'Ad', 'Promotion' → 마케팅/광고\n"
    "- 'Consulting', '컨설팅', 'consulting fee' → 컨설팅/용역\n"
    "- DEPOSIT 류의 입금 (Keeta, NOTPROVIDED 등 카드사·결제대행) → 매출정산\n"
    "- 'Refund' / 'Reversal' / 환불 키워드 → 환불\n"
    "- FEE source_type → 수수료\n"
    "- 자기 계좌 간 이체로 보이면 → 내부이체\n"
    "- 명확하지 않으면 → 기타\n\n"
    "vendor 필드: description 에서 거래 상대방(직원명·업체명) 추출. 없으면 빈 문자열.\n\n"
    "도구 classify_transactions 를 1번만 호출. 입력으로 받은 모든 거래를 결과에 포함."
)


CLASSIFY_TOOL = {
    "name": "classify_transactions",
    "description": "거래 분류 결과를 일괄 반환합니다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "txn_id": {"type": "string"},
                        "category": {
                            "type": "string",
                            "enum": BUSINESS_CATEGORIES,
                        },
                        "vendor": {"type": "string"},
                    },
                    "required": ["txn_id", "category"],
                },
            }
        },
        "required": ["results"],
    },
}


def _txn_to_classifier_input(t: dict) -> dict:
    return {
        "txn_id": t.get("id"),
        "description": (t.get("description") or "")[:200],
        "amount": t.get("amount"),
        "currency": t.get("currency"),
        "source_type": t.get("source_type"),
        "transaction_type": t.get("transaction_type"),
    }


def _classify_batch(transactions: list[dict]) -> list[tuple[str, str, str | None]]:
    """Send a batch (up to ~50 txns) to Claude. Returns list of (id, cat, vendor)."""
    if not transactions:
        return []
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    payload = [_txn_to_classifier_input(t) for t in transactions]
    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=4096,
        system=CLASSIFY_SYSTEM_PROMPT,
        tools=[CLASSIFY_TOOL],
        tool_choice={"type": "tool", "name": "classify_transactions"},
        messages=[
            {
                "role": "user",
                "content": (
                    f"분류할 거래 {len(transactions)}건:\n\n"
                    f"{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}"
                ),
            }
        ],
    )
    out: list[tuple[str, str, str | None]] = []
    for block in response.content:
        if block.type != "tool_use" or block.name != "classify_transactions":
            continue
        for r in block.input.get("results", []):
            tid = r.get("txn_id")
            cat = r.get("category")
            vendor = r.get("vendor") or None
            if tid and cat:
                out.append((tid, cat, vendor))
    return out


def classify(
    transactions: Iterable[dict], batch_size: int = 50
) -> dict[str, dict]:
    """Classify transactions, using cache. Returns {txn_id: {category, vendor}}."""
    txns = list(transactions)
    ids = [t["id"] for t in txns if t.get("id")]
    cached = storage.get_txn_categories(config.DB_PATH, ids)

    uncategorized = [t for t in txns if t.get("id") and t["id"] not in cached]
    if not uncategorized:
        return cached

    logger.info(
        "Classifying %d uncategorized transactions (batch=%d)",
        len(uncategorized),
        batch_size,
    )
    new_results: list[tuple[str, str, str | None]] = []
    for i in range(0, len(uncategorized), batch_size):
        batch = uncategorized[i : i + batch_size]
        try:
            new_results.extend(_classify_batch(batch))
        except Exception:
            logger.exception(
                "Classifier batch %d-%d failed; will retry next time",
                i,
                i + len(batch),
            )

    storage.save_txn_categories(config.DB_PATH, new_results)
    for tid, cat, vendor in new_results:
        cached[tid] = {"category": cat, "vendor": vendor}
    return cached
