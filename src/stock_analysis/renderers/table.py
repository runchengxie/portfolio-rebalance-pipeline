"""Table renderer

Provides table format data rendering functionality.
"""

from ..models import AccountSnapshot, Order, Quote, RebalanceResult


def render_quotes(quotes: list[Quote]) -> str:
    """Render stock quotes table

    Args:
        quotes: List of quotes

    Returns:
        str: Formatted table string
    """
    if not quotes:
        return "无报价数据"

    lines = []
    lines.append("实时报价:")
    lines.append("-" * 50)

    for quote in quotes:
        lines.append(
            f"{quote.symbol:12} | 价格: {quote.price:>10.2f} | 时间: {quote.timestamp}"
        )

    return "\n".join(lines)


def render_account_snapshot(
    snapshot: AccountSnapshot, only_funds: bool = False, only_positions: bool = False
) -> str:
    """Render account snapshot table

    Args:
        snapshot: Account snapshot
        only_funds: Only show fund information
        only_positions: Only show position information

    Returns:
        str: Formatted table string
    """
    lines = []

    # Environment identifier
    if snapshot.env == "real":
        lines.append("!!! REAL ACCOUNT DATA (READ-ONLY) !!!")

    # Fund information
    if not only_positions:
        lines.append(f"\n[{snapshot.env.upper()}] 现金(USD): ${snapshot.cash_usd:,.2f}")
        if not only_funds:
            lines.append(f"持仓市值: ${snapshot.total_market_value:,.2f}")
            lines.append(f"总资产: ${snapshot.total_portfolio_value:,.2f}")

    # Position information
    if not only_funds:
        if snapshot.positions:
            if not only_positions:
                lines.append("\n持仓详情:")
            lines.append("Symbol        Qty        Last       Est.Value")
            lines.append("-" * 50)

            for position in snapshot.positions:
                lines.append(
                    f"{position.symbol:12} {position.quantity:10} "
                    f"{position.last_price:10.2f} ${position.estimated_value:>10,.2f}"
                )
        else:
            if not only_positions:
                lines.append("\n无持仓")

    return "\n".join(lines)


def render_multiple_account_snapshots(
    snapshots: list[AccountSnapshot],
    only_funds: bool = False,
    only_positions: bool = False,
) -> str:
    """Render multiple account snapshots

    Args:
        snapshots: List of account snapshots
        only_funds: Only show fund information
        only_positions: Only show position information

    Returns:
        str: Formatted table string
    """
    if not snapshots:
        return "无账户数据"

    lines = []
    for snapshot in snapshots:
        lines.append(render_account_snapshot(snapshot, only_funds, only_positions))

    return "\n".join(lines)


def render_rebalance_plan(result: RebalanceResult) -> str:
    """Render rebalance plan table

    Args:
        result: Rebalance result

    Returns:
        str: Formatted table string
    """
    lines = []

    # Title
    mode = "干跑模式" if result.dry_run else "实际执行模式"
    lines.append(f"\n=== {mode} - {result.sheet_name} 差额调仓 ===")
    lines.append("-" * 80)

    # Account overview
    lines.append(f"总资产: ${result.total_portfolio_value:,.2f}")
    lines.append(f"等权重分配: 每只股票目标市值 ${result.target_value_per_stock:,.2f}")
    lines.append("-" * 80)

    # Rebalance details header
    lines.append("Symbol   | 当前价格 | 当前持仓 | 目标持仓 | 差额    | 操作")
    lines.append("-" * 80)

    # Build current positions mapping
    current_positions_map = {pos.symbol: pos for pos in result.current_positions}

    # Show rebalance situation for each target stock
    for target_pos in result.target_positions:
        current_pos = current_positions_map.get(target_pos.symbol)
        current_qty = current_pos.quantity if current_pos else 0

        delta_qty = target_pos.quantity - current_qty

        # Find corresponding order
        order = None
        for o in result.orders:
            if o.symbol == target_pos.symbol or o.symbol.replace(
                ".US", ""
            ) == target_pos.symbol.replace(".US", ""):
                order = o
                break

        if order:
            action = f"{order.side} {order.quantity}"
        elif abs(delta_qty) > 0:
            action = "跳过（差额太小）"
        else:
            action = "无变化"

        lines.append(
            f"{target_pos.symbol[:8]:8s} | {target_pos.last_price:8.2f} | "
            f"{current_qty:8d} | {target_pos.quantity:8d} | {delta_qty:7d} | {action}"
        )

    # Order summary
    lines.append(f"\n总计处理 {len(result.orders)} 个订单")

    if result.dry_run:
        lines.append("\n注意：这是干跑模式，未实际下单")
        lines.append("使用 --execute 参数可实际执行交易")
    else:
        lines.append("\n警告：已实际下单，请检查券商账户确认执行情况")

    return "\n".join(lines)


def render_orders(orders: list[Order]) -> str:
    """Render order list

    Args:
        orders: List of orders

    Returns:
        str: Formatted table string
    """
    if not orders:
        return "无订单数据"

    lines = []
    lines.append("订单详情:")
    lines.append("Symbol   | Side | Qty    | Price    | Status   | Order ID")
    lines.append("-" * 65)

    for order in orders:
        price_str = f"{order.price:.2f}" if order.price else "MARKET"
        order_id_str = order.order_id[:8] if order.order_id else "N/A"

        lines.append(
            f"{order.symbol[:8]:8s} | {order.side:4s} | {order.quantity:6d} | "
            f"{price_str:8s} | {order.status:8s} | {order_id_str}"
        )

        if order.error_message:
            lines.append(f"  -> 错误: {order.error_message}")

    return "\n".join(lines)
