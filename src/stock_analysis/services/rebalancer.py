"""调仓服务

提供调仓相关的业务逻辑，包括计划生成和执行。
"""

import json
from datetime import datetime
from pathlib import Path

from ..broker.longport_client import LongPortClient, _to_lb_symbol
from ..models import AccountSnapshot, Order, Position, RebalanceResult
from ..utils.logging import get_logger
from .account_snapshot import get_quotes
from ..utils.config import load_cfg
from ..fees import FeeSchedule, estimate_fees
from decimal import Decimal, ROUND_HALF_UP

logger = get_logger(__name__)


class RebalanceService:
    """调仓服务类"""

    def __init__(self, env: str = "real", client: LongPortClient | None = None):
        self.env = env
        self.client = client

    def _get_client(self) -> LongPortClient:
        """获取客户端实例"""
        if not self.client:
            self.client = LongPortClient(env=self.env)
        return self.client

    def close(self):
        """关闭客户端连接"""
        if self.client:
            self.client.close()
            self.client = None

    def plan_rebalance(
        self,
        target_tickers: list[str],
        account_snapshot: AccountSnapshot,
        quotes: dict[str, float] | None = None,
        allow_fractional: bool = False,
    ) -> RebalanceResult:
        """制定调仓计划

        Args:
            target_tickers: 目标股票列表
            account_snapshot: 当前账户快照

        Returns:
            RebalanceResult: 调仓计划结果
        """
        if not target_tickers:
            raise ValueError("目标股票列表不能为空")

        # 获取实时报价（未提供则内部拉取一次）
        if quotes is None:
            lb_symbols = [
                _to_lb_symbol(ticker.upper().strip()) for ticker in target_tickers
            ]
            try:
                quote_objs = get_quotes(lb_symbols, client=self._get_client())
                # 转为简单价格映射
                quotes = {sym: q.price for sym, q in quote_objs.items()}
            except Exception as e:
                logger.error(f"获取报价失败: {e}")
                raise

        # 计算等权重目标仓位（带兜底：若总资产为 0 或缺失，则以 USD 现金 + 报价估值重算）
        n_stocks = len(target_tickers)
        if account_snapshot.total_portfolio_value and account_snapshot.total_portfolio_value > 0:
            effective_total = float(account_snapshot.total_portfolio_value)
        else:
            total_pos_value = 0.0
            if quotes is None:
                lb_symbols = [
                    _to_lb_symbol(ticker.upper().strip()) for ticker in target_tickers
                ]
                quote_objs = get_quotes(lb_symbols, client=self._get_client())
                quotes = {sym: q.price for sym, q in quote_objs.items()}
            # 用 quotes 给当前持仓估值
            current_positions_map = {pos.symbol: pos for pos in account_snapshot.positions}
            for sym, pos in current_positions_map.items():
                px = float((quotes or {}).get(sym, pos.last_price or 0.0))
                total_pos_value += px * float(pos.quantity)
            effective_total = float(account_snapshot.cash_usd) + float(total_pos_value)
            if effective_total <= 0:
                # 进一步提示：如果券商返回了非 USD 的净资产，但无法估值现有持仓，则需要 FX 或切换到 real 环境
                try:
                    from ..utils.logging import get_logger as _get_logger

                    _lg = _get_logger(__name__)
                    if account_snapshot.base_currency and account_snapshot.base_currency != "USD":
                        _lg.warning(
                            "总资产为 0：当前环境持仓/现金按 USD 计为 0，券商净资产为非USD(%s)。"
                            " 可使用 real 环境干跑，或提供 FX 汇率进行折算。",
                            account_snapshot.base_currency,
                        )
                    else:
                        _lg.warning(
                            "总资产为 0：未获取到 USD 现金与可估值持仓，建议切换 real 环境或检查账户余额。"
                        )
                except Exception:
                    pass
        target_value_per_stock = effective_total / n_stocks

        # 构建当前持仓映射
        current_positions_map = {pos.symbol: pos for pos in account_snapshot.positions}

        # 生成调仓订单
        orders = []
        target_positions = []

        client = self._get_client()
        cfg = load_cfg() or {}
        fees_cfg = (cfg.get("fees") or {}) if isinstance(cfg, dict) else {}
        fs = FeeSchedule(
            commission=float(fees_cfg.get("commission", 0.0) or 0.0),
            platform_per_share=float(fees_cfg.get("platform_per_share", 0.005) or 0.0),
            fractional_pct_lt1=float(fees_cfg.get("fractional_pct_lt1", 0.012) or 0.0),
            fractional_cap_lt1=float(fees_cfg.get("fractional_cap_lt1", 0.99) or 0.0),
            sell_reg_fees_bps=float(fees_cfg.get("sell_reg_fees_bps", 0.0) or 0.0),
        )
        frac_cfg = (cfg.get("fractional_preview") or {}) if isinstance(cfg, dict) else {}
        frac_enable = bool(frac_cfg.get("enable", True))
        frac_step = Decimal(str(frac_cfg.get("default_step", 0.001)))

        for ticker in target_tickers:
            symbol = ticker.upper().strip()
            lb_symbol = _to_lb_symbol(symbol)

            # 获取价格
            px = (quotes or {}).get(lb_symbol)
            if not px or px <= 0:
                logger.warning(f"跳过 {symbol}：无有效价格")
                continue

            price = float(px)

            # 当前持仓
            current_position = current_positions_map.get(lb_symbol)
            current_qty = current_position.quantity if current_position else 0

            # 计算目标持仓
            target_qty_raw = target_value_per_stock / price
            if allow_fractional:
                # 计划层允许小数，但下单层仍以最小交易单位执行
                # 由于 Order/Position 目前的 quantity 为 int，这里保持向下取整到 lot
                lot_size = client.lot_size(lb_symbol)
                target_qty = (int(target_qty_raw) // lot_size) * lot_size
            else:
                lot_size = client.lot_size(lb_symbol)
                target_qty = (int(target_qty_raw) // lot_size) * lot_size

            # 创建目标持仓（保守执行：整数股/lot），但计算展示用的目标小数股
            target_qty_frac = Decimal(0)
            if price > 0 and frac_enable:
                target_qty_frac = (Decimal(target_value_per_stock) / Decimal(price)).quantize(
                    frac_step, rounding=ROUND_HALF_UP
                )
            target_position = Position(
                symbol=lb_symbol,
                quantity=target_qty,
                last_price=price,
                estimated_value=target_qty * price,
                env=self.env,
            )
            target_positions.append(target_position)

            # 计算差额
            delta_qty = target_qty - current_qty

            if abs(delta_qty) < lot_size:
                logger.info(
                    f"跳过 {symbol}：差额 {delta_qty} 小于最小交易单位 {lot_size}"
                )
                continue

            # 生成订单
            if delta_qty > 0:
                side = "BUY"
                qty_to_trade = delta_qty
            else:
                side = "SELL"
                qty_to_trade = abs(delta_qty)

            order = Order(
                symbol=symbol,
                quantity=qty_to_trade,
                side=side,
                price=price,
                order_type="MARKET",
            )
            # 费用估算（以整数执行量计费）；若目标小数股<1，提供碎股提示
            est_fee, frac_hint = estimate_fees(
                side=side,
                qty_int=qty_to_trade,
                price=price,
                any_fractional_lt1=(target_qty_frac > 0 and target_qty_frac < 1),
                fs=fs,
            )
            order.est_fees = est_fee
            order.est_frac_hint = frac_hint
            if frac_enable:
                order.target_qty_frac = float(target_qty_frac)
                order.rounded_target_qty = int(target_qty)
                order.rounding_loss = float(target_qty_frac - Decimal(int(target_qty)))
            orders.append(order)

        # 处理非目标列表中的现有持仓：清仓（target 视为 0）
        target_set = { _to_lb_symbol(t.upper().strip()) for t in target_tickers }
        for sym, cur in current_positions_map.items():
            if sym in target_set:
                continue
            current_qty = int(cur.quantity)
            if current_qty <= 0:
                continue
            lot_size = client.lot_size(sym)
            # 取整至 lot
            qty_to_sell = (current_qty // lot_size) * lot_size
            if qty_to_sell <= 0:
                continue
            # 使用已有报价
            px = float((quotes or {}).get(sym, cur.last_price or 0.0))
            # 目标持仓加入 0 行，便于 diff 视图
            target_positions.append(
                Position(symbol=sym, quantity=0, last_price=px, estimated_value=0.0, env=self.env)
            )
            o = Order(
                symbol=sym,
                quantity=qty_to_sell,
                side="SELL",
                price=px if px > 0 else None,
                order_type="MARKET",
            )
            est_fee, frac_hint = estimate_fees(
                side="SELL",
                qty_int=qty_to_sell,
                price=px or 0.0,
                any_fractional_lt1=False,
                fs=fs,
            )
            o.est_fees = est_fee
            o.est_frac_hint = frac_hint
            orders.append(o)

        return RebalanceResult(
            target_positions=target_positions,
            current_positions=account_snapshot.positions,
            orders=orders,
            total_portfolio_value=effective_total,
            target_value_per_stock=target_value_per_stock,
            env=self.env,
        )

    def execute_orders(self, orders: list[Order], dry_run: bool = True) -> list[Order]:
        """执行订单列表

        Args:
            orders: 订单列表
            dry_run: 是否为干跑模式

        Returns:
            List[Order]: 执行结果更新后的订单列表
        """
        if not orders:
            return []

        client = self._get_client()
        executed_orders = []

        for order in orders:
            try:
                result = client.place_order(
                    order.symbol,
                    order.quantity,
                    order.side,
                    dry_run=dry_run,
                    est_px=order.price if order.price else None,
                )

                # 更新订单状态
                if dry_run:
                    order.status = "DRY_RUN"
                    order.order_id = (
                        f"dry_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    )
                else:
                    order.status = (
                        "SUCCESS" if result.get("success", False) else "FAILED"
                    )
                    order.order_id = result.get("order_id")
                    if not result.get("success", False):
                        order.error_message = result.get("error", "未知错误")

                executed_orders.append(order)

            except Exception as e:
                logger.error(
                    f"执行订单失败 {order.symbol} {order.side} {order.quantity}: {e}"
                )
                order.status = "FAILED"
                order.error_message = str(e)
                executed_orders.append(order)

        return executed_orders

    def save_audit_log(
        self, rebalance_result: RebalanceResult, dry_run: bool = True
    ) -> Path:
        """保存审计日志

        Args:
            rebalance_result: 调仓结果
            dry_run: 是否为干跑模式

        Returns:
            Path: 日志文件路径
        """
        log_dir = Path("outputs/orders")
        log_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        mode = "dry" if dry_run else "live"
        log_file = log_dir / f"{timestamp}_{self.env}_{mode}.jsonl"

        with open(log_file, "w", encoding="utf-8") as f:
            for order in rebalance_result.orders:
                order_dict = {
                    "symbol": order.symbol,
                    "quantity": order.quantity,
                    "side": order.side,
                    "price": order.price,
                    "status": order.status,
                    "order_id": order.order_id,
                    "timestamp": order.timestamp.isoformat()
                    if order.timestamp
                    else None,
                    "error_message": order.error_message,
                    "env": self.env,
                    "dry_run": dry_run,
                }
                f.write(json.dumps(order_dict, ensure_ascii=False) + "\n")

        logger.info(f"审计日志已保存到: {log_file}")
        return log_file
