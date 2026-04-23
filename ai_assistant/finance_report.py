"""Airwallex finance summary, categorized by transaction type.

Categorization scheme (based on source_type + transaction_type):
- DEPOSIT          → 매출 정산 입금
- PAYOUT           → 송금 지급
- PAYOUT_REVERSAL  → 송금 반환 (실패한 송금 환원)
- CARD_PURCHASE/ISSUING_CAPTURE → 법인카드 결제 (확정 차감)
- CARD_PURCHASE/ISSUING_AUTHORISATION_HOLD/RELEASE → 카드 임시 승인 (상쇄, 보고서에서 제외)
- CARD_REFUND      → 카드 환불 입금
- FEE              → Airwallex 수수료
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from .airwallex_client import Airwallex, AirwallexError
from . import txn_classifier

logger = logging.getLogger(__name__)


# Category keys → (display label, emoji). Order = display order.
_CATEGORY_LABELS: dict[str, tuple[str, str]] = {
    "deposit": ("매출 정산 입금", "💰"),
    "card_refund": ("카드 환불 입금", "💳"),
    "payout_reversal": ("송금 반환", "🔁"),
    "payout": ("송금 지급", "🏦"),
    "card_capture": ("법인카드 결제", "💳"),
    "fee": ("Airwallex 수수료", "💸"),
    "card_hold": ("카드 임시 승인 (상쇄)", "⏸"),  # informational, excluded from net
    "other": ("기타", "❓"),
}


def _categorize(t: dict) -> str:
    src = (t.get("source_type") or "").upper()
    typ = (t.get("transaction_type") or "").upper()

    if src == "DEPOSIT":
        return "deposit"
    if src == "FEE":
        return "fee"
    if src == "CARD_REFUND":
        return "card_refund"
    if src == "PAYOUT":
        if typ == "PAYOUT_REVERSAL":
            return "payout_reversal"
        return "payout"
    if src == "CARD_PURCHASE":
        if typ == "ISSUING_CAPTURE":
            return "card_capture"
        return "card_hold"  # HOLD or RELEASE
    return "other"


@dataclass
class CategoryStats:
    label: str
    emoji: str
    count: int = 0
    by_currency: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    samples: list[tuple] = field(default_factory=list)  # (amount, ccy, desc, date)

    def add(self, amount: float, currency: str, desc: str, date: str) -> None:
        self.count += 1
        self.by_currency[currency] += amount
        self.samples.append((amount, currency, desc, date))


@dataclass
class FinanceSummary:
    markdown: str
    by_category: dict[str, CategoryStats]
    transaction_count: int
    has_error: bool = False
    error: str | None = None


def _fmt_amount(amount: float, currency: str) -> str:
    if abs(amount - round(amount)) < 0.005:
        return f"{int(round(amount)):,} {currency}"
    return f"{amount:,.2f} {currency}"


def _fmt_signed(amount: float, currency: str) -> str:
    sign = "+" if amount > 0 else ""
    return f"{sign}{_fmt_amount(amount, currency)}"


def generate_markdown(
    client: Airwallex, start: datetime, end: datetime
) -> FinanceSummary:
    """Summarize transactions in [start, end) into a categorized markdown section."""
    try:
        transactions = client.list_transactions(start, end)
        balances = client.get_balances()
    except (AirwallexError, Exception) as e:
        logger.exception("Airwallex finance summary failed")
        return FinanceSummary(
            markdown=(
                "## 💰 자금 현황 (Airwallex)\n\n"
                f"⚠️ Airwallex 데이터 조회 실패: `{e}`\n"
            ),
            by_category={},
            transaction_count=0,
            has_error=True,
            error=str(e),
        )

    # Bucket transactions
    buckets: dict[str, CategoryStats] = {
        key: CategoryStats(label=label, emoji=emoji)
        for key, (label, emoji) in _CATEGORY_LABELS.items()
    }
    for t in transactions:
        cat = _categorize(t)
        try:
            amount = float(t.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        currency = t.get("currency") or "?"
        desc = (
            t.get("description")
            or t.get("transaction_type")
            or "(설명 없음)"
        )
        date = (t.get("settled_at") or t.get("created_at") or "")[:10]
        buckets[cat].add(amount, currency, desc, date)

    # ---- Markdown ----
    lines: list[str] = ["## 💰 자금 현황 (Airwallex)", ""]

    # Current balances (non-zero only)
    nonzero_balances = []
    for b in balances:
        try:
            total = float(b.get("total_amount") or b.get("available_amount") or 0)
        except (TypeError, ValueError):
            continue
        if abs(total) >= 0.005:
            nonzero_balances.append((b.get("currency", "?"), total))
    nonzero_balances.sort(key=lambda x: -abs(x[1]))

    if nonzero_balances:
        lines.append("### 현재 잔액")
        lines.append("")
        lines.append("| 통화 | 잔액 |")
        lines.append("|---|---|")
        for ccy, amt in nonzero_balances:
            lines.append(f"| {ccy} | {_fmt_amount(amt, ccy)} |")
        lines.append("")

    # Category summary
    lines.append(f"### 카테고리별 집계 ({len(transactions)}건)")
    lines.append("")
    if not transactions:
        lines.append("해당 기간에 거래 내역이 없습니다.")
        lines.append("")
    else:
        lines.append("| 카테고리 | 건수 | 금액 |")
        lines.append("|---|---|---|")
        for key in _CATEGORY_LABELS:
            stats = buckets[key]
            if stats.count == 0:
                continue
            amt_str = " / ".join(
                _fmt_signed(v, ccy) for ccy, v in stats.by_currency.items()
            )
            lines.append(f"| {stats.emoji} {stats.label} | {stats.count} | {amt_str} |")
        lines.append("")

        # Net cash flow (excluding card_hold which nets to zero by design)
        net_by_ccy: dict[str, float] = defaultdict(float)
        for key, stats in buckets.items():
            if key == "card_hold":
                continue
            for ccy, v in stats.by_currency.items():
                net_by_ccy[ccy] += v
        if net_by_ccy:
            lines.append("**순현금흐름**: " + ", ".join(
                _fmt_signed(v, ccy) for ccy, v in sorted(net_by_ccy.items())
            ))
            lines.append("")

    # Top items per important category
    def _top_section(title: str, samples: list[tuple], reverse: bool, n: int = 5) -> None:
        if not samples:
            return
        lines.append(f"#### {title}")
        lines.append("")
        sorted_s = sorted(samples, key=lambda x: x[0], reverse=reverse)[:n]
        for amt, ccy, desc, date in sorted_s:
            short = (desc[:50] + "…") if len(desc) > 51 else desc
            lines.append(f"- `{date}` {_fmt_signed(amt, ccy)} — {short}")
        lines.append("")

    _top_section("주요 송금 지급 Top 5", buckets["payout"].samples, reverse=False)
    _top_section("주요 매출 정산 입금 Top 5", buckets["deposit"].samples, reverse=True)
    _top_section("주요 카드 결제 Top 5", buckets["card_capture"].samples, reverse=False)

    # ---- Business-category breakdown (Claude classifier) ----
    try:
        classified = txn_classifier.classify(transactions)
    except Exception as e:
        logger.exception("Business-category classification failed")
        classified = {}
        lines.append(f"### 비즈니스 카테고리 분류")
        lines.append(f"⚠️ 자동 분류 실패: {e}")
        lines.append("")

    if classified:
        cat_totals: dict[str, dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )  # {category: {currency: signed total}}
        cat_counts: dict[str, int] = defaultdict(int)
        cat_vendors: dict[str, dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )  # {category: {vendor: |amount|}}
        for t in transactions:
            tid = t.get("id")
            info = classified.get(tid)
            if not info:
                continue
            cat = info["category"]
            try:
                amt = float(t.get("amount") or 0)
            except (TypeError, ValueError):
                continue
            ccy = t.get("currency") or "?"
            cat_totals[cat][ccy] += amt
            cat_counts[cat] += 1
            vendor = info.get("vendor")
            if vendor:
                cat_vendors[cat][vendor] += abs(amt)

        lines.append("### 비즈니스 카테고리별 분류 (자동)")
        lines.append("")
        lines.append("| 카테고리 | 건수 | 금액 | 주요 거래처 |")
        lines.append("|---|---|---|---|")
        # Sort by absolute total (largest first)
        cat_keys = sorted(
            cat_totals.keys(),
            key=lambda k: -sum(abs(v) for v in cat_totals[k].values()),
        )
        for cat in cat_keys:
            amt_str = " / ".join(
                _fmt_signed(v, ccy) for ccy, v in cat_totals[cat].items()
            )
            top_vendors = sorted(
                cat_vendors[cat].items(), key=lambda x: -x[1]
            )[:3]
            vendor_str = ", ".join(name for name, _ in top_vendors) or "-"
            if len(vendor_str) > 60:
                vendor_str = vendor_str[:60] + "…"
            lines.append(
                f"| {cat} | {cat_counts[cat]} | {amt_str} | {vendor_str} |"
            )
        lines.append("")

    return FinanceSummary(
        markdown="\n".join(lines),
        by_category=buckets,
        transaction_count=len(transactions),
    )
