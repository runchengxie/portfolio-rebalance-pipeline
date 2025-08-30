"""Diff-style renderer for rebalance previews.

Produces a human-readable diff similar to git control:
- Top summary card: totals before/after, cash/stocks/funds split
- Diffstat: added/removed/increase/decrease counts
- Per-position diffs
- Order list (SELL first, then BUY)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Tuple

from ..models import AccountSnapshot, Order, Position, RebalanceResult


def _fmt_money(v: float) -> str:
    return f"${v:,.2f}"


def _fmt_pct(v: float) -> str:
    return f"{v*100:,.2f}%"


def _is_fund_symbol(symbol: str) -> bool:
    # Heuristic: funds in our snapshot builder come from fund_positions and
    # usually do not include a ".US/.HK" suffix. This is a best-effort tag.
    return "." not in symbol


def _positions_value(positions: Iterable[Position]) -> float:
    return sum(float(p.estimated_value) for p in positions)


@dataclass
class Buckets:
    cash: float
    stocks: float
    funds: float

    @property
    def total(self) -> float:
        return self.cash + self.stocks + self.funds


def _bucketize(snapshot: AccountSnapshot) -> Buckets:
    stocks_val = 0.0
    funds_val = 0.0
    for p in snapshot.positions:
        if _is_fund_symbol(p.symbol):
            funds_val += float(p.estimated_value)
        else:
            stocks_val += float(p.estimated_value)
    return Buckets(cash=float(snapshot.cash_usd), stocks=stocks_val, funds=funds_val)


def _bucketize_after(
    before_cash: float, targets: Iterable[Position], orders: Iterable[Order]
) -> Buckets:
    # Estimate after-cash via orders, using provided order.price
    notional_sell = 0.0
    notional_buy = 0.0
    for od in orders:
        px = float(od.price or 0.0)
        amt = px * float(od.quantity)
        if od.side.upper() == "SELL":
            notional_sell += amt
        else:
            notional_buy += amt
    cash_after = float(before_cash) + notional_sell - notional_buy
    # Sum targets by bucket
    stocks_val = 0.0
    funds_val = 0.0
    for p in targets:
        if _is_fund_symbol(p.symbol):
            funds_val += float(p.estimated_value)
        else:
            stocks_val += float(p.estimated_value)
    return Buckets(cash=cash_after, stocks=stocks_val, funds=funds_val)


def _diffstat(
    current: Dict[str, Position], target: Dict[str, Position]
) -> Tuple[int, int, int, int]:
    added = 0
    removed = 0
    increased = 0
    decreased = 0
    all_syms = set(current) | set(target)
    for s in sorted(all_syms):
        cur_q = int(current.get(s).quantity) if s in current else 0
        tgt_q = int(target.get(s).quantity) if s in target else 0
        if cur_q == 0 and tgt_q > 0:
            added += 1
        elif cur_q > 0 and tgt_q == 0:
            removed += 1
        elif tgt_q > cur_q:
            increased += 1
        elif tgt_q < cur_q:
            decreased += 1
    return added, removed, increased, decreased


def render_rebalance_diff(
    result: RebalanceResult, before: AccountSnapshot
) -> str:
    lines: list[str] = []

    # Top summary card
    b = _bucketize(before)
    after_b = _bucketize_after(before.cash_usd, result.target_positions, result.orders)
    total_before = b.total
    total_after = after_b.total if after_b.total > 0 else result.total_portfolio_value

    lines.append("=== Rebalance Preview (Diff) ===")
    lines.append(
        f"As of: {before.env.upper()}  Currency: USD  Mode: {'DRY-RUN' if result.dry_run else 'LIVE'}"
    )
    lines.append("--- Totals (Before → After) ---")
    lines.append(
        f"Cash:   {_fmt_money(b.cash)} → {_fmt_money(after_b.cash)}  (Δ {_fmt_money(after_b.cash - b.cash)})"
    )
    lines.append(
        f"Stocks: {_fmt_money(b.stocks)} → {_fmt_money(after_b.stocks)}  (Δ {_fmt_money(after_b.stocks - b.stocks)})"
    )
    lines.append(
        f"Funds:  {_fmt_money(b.funds)} → {_fmt_money(after_b.funds)}  (Δ {_fmt_money(after_b.funds - b.funds)})"
    )
    lines.append(
        f"Total:  {_fmt_money(total_before)} → {_fmt_money(total_after)}"
    )
    lines.append("")

    # Diffstat
    cur_map = {p.symbol: p for p in before.positions}
    tgt_map = {p.symbol: p for p in result.target_positions}
    added, removed, inc, dec = _diffstat(cur_map, tgt_map)
    lines.append("--- Diffstat ---")
    lines.append(
        f"Added: {added}  Removed: {removed}  Increased: {inc}  Decreased: {dec}"
    )
    lines.append("")

    # Per-position diffs
    lines.append("Symbol    Before(%)  Before($,sh)      →   After(%)   After($,sh)       Δsh   Action")
    lines.append("-" * 90)
    # Use total_after or result.total_portfolio_value for weights
    denom_before = total_before if total_before > 0 else max(1.0, result.total_portfolio_value)
    denom_after = total_after if total_after > 0 else max(1.0, result.total_portfolio_value)
    all_syms = sorted(set(cur_map) | set(tgt_map))
    for s in all_syms:
        cur = cur_map.get(s)
        tgt = tgt_map.get(s)
        cur_val = float(cur.estimated_value) if cur else 0.0
        cur_qty = int(cur.quantity) if cur else 0
        tgt_val = float(tgt.estimated_value) if tgt else 0.0
        tgt_qty = int(tgt.quantity) if tgt else 0
        cur_w = cur_val / denom_before if denom_before > 0 else 0.0
        tgt_w = tgt_val / denom_after if denom_after > 0 else 0.0
        delta_qty = tgt_qty - cur_qty
        # action text if any order exists
        action = ""
        if delta_qty > 0:
            action = f"BUY {delta_qty}"
        elif delta_qty < 0:
            action = f"SELL {abs(delta_qty)}"
        else:
            action = "HOLD"
        lines.append(
            f"{s[:8]:8s}  {_fmt_pct(cur_w):>8}  {_fmt_money(cur_val):>12},{cur_qty:>4}  →  "
            f"{_fmt_pct(tgt_w):>8}  {_fmt_money(tgt_val):>12},{tgt_qty:>4}  {delta_qty:>5}  {action}"
        )

    lines.append("")

    # Orders list (SELL first)
    lines.append("--- Orders ---")
    if not result.orders:
        lines.append("No orders (already aligned or below lot thresholds)")
    else:
        sell_first = sorted(
            result.orders,
            key=lambda o: (0 if o.side.upper() == "SELL" else 1, -(o.price or 0) * o.quantity),
        )
        for od in sell_first:
            est_amt = (od.price or 0.0) * float(od.quantity)
            lines.append(
                f"{od.side:4s} {od.symbol[:8]:8s} {od.quantity:>6} @ {('MKT' if not od.price else _fmt_money(od.price)):<8} est { _fmt_money(est_amt)}"
            )

    return "\n".join(lines)

