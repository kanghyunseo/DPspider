"""Airwallex weekly finance summary (returns Markdown)."""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from .airwallex_client import Airwallex, AirwallexError

logger = logging.getLogger(__name__)


@dataclass
class FinanceSummary:
    markdown: str
    total_income: dict[str, float]   # {currency: total}
    total_expense: dict[str, float]  # {currency: absolute total (positive)}
    transaction_count: int
    has_error: bool = False
    error: str | None = None


def _fmt_amount(amount: float, currency: str) -> str:
    # Show integer if no cents, else 2 decimals. Thousands separator.
    if abs(amount - round(amount)) < 0.005:
        return f"{int(round(amount)):,} {currency}"
    return f"{amount:,.2f} {currency}"


def generate_markdown(
    client: Airwallex, start: datetime, end: datetime
) -> FinanceSummary:
    """Summarize transactions in [start, end) into a markdown section."""
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
            total_income={},
            total_expense={},
            transaction_count=0,
            has_error=True,
            error=str(e),
        )

    income_by_ccy: dict[str, float] = defaultdict(float)
    expense_by_ccy: dict[str, float] = defaultdict(float)
    top_income: list[tuple] = []   # (amount, currency, description, date)
    top_expense: list[tuple] = []

    for t in transactions:
        # Airwallex transactions use signed "amount" in source currency
        # Handle variations: "amount"/"net_amount", "currency"/"source_currency"
        amount = t.get("net_amount") or t.get("amount") or 0
        currency = (
            t.get("currency")
            or t.get("source_currency")
            or t.get("settle_currency")
            or "???"
        )
        desc = (
            t.get("description")
            or t.get("reference")
            or t.get("type")
            or "(설명 없음)"
        )
        created = t.get("created_at") or t.get("settled_at") or ""

        try:
            amount = float(amount)
        except (TypeError, ValueError):
            continue

        if amount >= 0:
            income_by_ccy[currency] += amount
            top_income.append((amount, currency, desc, created))
        else:
            expense_by_ccy[currency] += -amount
            top_expense.append((-amount, currency, desc, created))

    top_income.sort(key=lambda x: -x[0])
    top_expense.sort(key=lambda x: -x[0])

    # ---- Markdown ----
    lines: list[str] = ["## 💰 자금 현황 (Airwallex)", ""]

    # Current balances
    if balances:
        lines.append("### 현재 잔액")
        lines.append("")
        lines.append("| 통화 | 잔액 |")
        lines.append("|---|---|")
        for b in balances:
            ccy = b.get("currency", "???")
            # Different fields across Airwallex surfaces; try a few
            total = (
                b.get("total_amount")
                or b.get("available_amount")
                or b.get("amount")
                or 0
            )
            try:
                total = float(total)
            except (TypeError, ValueError):
                total = 0
            lines.append(f"| {ccy} | {_fmt_amount(total, ccy)} |")
        lines.append("")

    # Week income/expense
    lines.append(f"### 이번주 수익·지출 ({len(transactions)}건)")
    lines.append("")
    if not transactions:
        lines.append("해당 기간에 거래 내역이 없습니다.")
        lines.append("")
    else:
        currencies = sorted(set(income_by_ccy) | set(expense_by_ccy))
        lines.append("| 통화 | 수익(입금) | 지출(출금) | 순액 |")
        lines.append("|---|---|---|---|")
        for ccy in currencies:
            inc = income_by_ccy.get(ccy, 0.0)
            exp = expense_by_ccy.get(ccy, 0.0)
            net = inc - exp
            lines.append(
                f"| {ccy} "
                f"| {_fmt_amount(inc, ccy)} "
                f"| {_fmt_amount(exp, ccy)} "
                f"| {_fmt_amount(net, ccy)} |"
            )
        lines.append("")

    # Top 5 each way
    if top_income:
        lines.append("#### 주요 입금 (Top 5)")
        lines.append("")
        for amt, ccy, desc, date in top_income[:5]:
            date_short = (date or "")[:10]
            lines.append(f"- `{date_short}` {_fmt_amount(amt, ccy)} — {desc}")
        lines.append("")

    if top_expense:
        lines.append("#### 주요 출금 (Top 5)")
        lines.append("")
        for amt, ccy, desc, date in top_expense[:5]:
            date_short = (date or "")[:10]
            lines.append(f"- `{date_short}` {_fmt_amount(amt, ccy)} — {desc}")
        lines.append("")

    return FinanceSummary(
        markdown="\n".join(lines),
        total_income=dict(income_by_ccy),
        total_expense=dict(expense_by_ccy),
        transaction_count=len(transactions),
    )
