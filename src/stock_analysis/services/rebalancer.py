"""调仓服务

提供调仓相关的业务逻辑，包括计划生成和执行。
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from ..broker.longport_client import LongPortClient, _to_lb_symbol
from ..models import AccountSnapshot, Order, Position, RebalanceResult
from ..utils.logging import get_logger
from .account_snapshot import get_account_snapshot, get_quotes

logger = get_logger(__name__)


class RebalanceService:
    """调仓服务类"""
    
    def __init__(self, env: str = "test"):
        self.env = env
        self.client = None
    
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
    
    def plan_rebalance(self, target_tickers: List[str], account_snapshot: AccountSnapshot) -> RebalanceResult:
        """制定调仓计划
        
        Args:
            target_tickers: 目标股票列表
            account_snapshot: 当前账户快照
            
        Returns:
            RebalanceResult: 调仓计划结果
        """
        if not target_tickers:
            raise ValueError("目标股票列表不能为空")
        
        # 获取实时报价
        lb_symbols = [_to_lb_symbol(ticker.upper().strip()) for ticker in target_tickers]
        try:
            quotes = get_quotes(lb_symbols, self.env)
        except Exception as e:
            logger.error(f"获取报价失败: {e}")
            raise
        
        # 计算等权重目标仓位
        n_stocks = len(target_tickers)
        target_value_per_stock = account_snapshot.total_portfolio_value / n_stocks
        
        # 构建当前持仓映射
        current_positions_map = {pos.symbol: pos for pos in account_snapshot.positions}
        
        # 生成调仓订单
        orders = []
        target_positions = []
        
        client = self._get_client()
        
        for ticker in target_tickers:
            symbol = ticker.upper().strip()
            lb_symbol = _to_lb_symbol(symbol)
            
            # 获取价格
            quote = quotes.get(lb_symbol)
            if not quote or quote.price <= 0:
                logger.warning(f"跳过 {symbol}：无有效价格")
                continue
            
            price = quote.price
            
            # 当前持仓
            current_position = current_positions_map.get(lb_symbol)
            current_qty = current_position.quantity if current_position else 0
            
            # 计算目标持仓（按最小交易单位取整）
            target_qty_raw = target_value_per_stock / price
            lot_size = client.lot_size(lb_symbol)
            target_qty = (int(target_qty_raw) // lot_size) * lot_size
            
            # 创建目标持仓
            target_position = Position(
                symbol=lb_symbol,
                quantity=target_qty,
                last_price=price,
                estimated_value=target_qty * price,
                env=self.env
            )
            target_positions.append(target_position)
            
            # 计算差额
            delta_qty = target_qty - current_qty
            
            if abs(delta_qty) < lot_size:
                logger.info(f"跳过 {symbol}：差额 {delta_qty} 小于最小交易单位 {lot_size}")
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
                order_type="MARKET"
            )
            orders.append(order)
        
        return RebalanceResult(
            target_positions=target_positions,
            current_positions=account_snapshot.positions,
            orders=orders,
            total_portfolio_value=account_snapshot.total_portfolio_value,
            target_value_per_stock=target_value_per_stock,
            env=self.env
        )
    
    def execute_orders(self, orders: List[Order], dry_run: bool = True) -> List[Order]:
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
                    dry_run=dry_run
                )
                
                # 更新订单状态
                if dry_run:
                    order.status = "DRY_RUN"
                    order.order_id = f"dry_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                else:
                    order.status = "SUCCESS" if result.get("success", False) else "FAILED"
                    order.order_id = result.get("order_id")
                    if not result.get("success", False):
                        order.error_message = result.get("error", "未知错误")
                
                executed_orders.append(order)
                
            except Exception as e:
                logger.error(f"执行订单失败 {order.symbol} {order.side} {order.quantity}: {e}")
                order.status = "FAILED"
                order.error_message = str(e)
                executed_orders.append(order)
        
        return executed_orders
    
    def save_audit_log(self, rebalance_result: RebalanceResult, dry_run: bool = True) -> Path:
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
                    "timestamp": order.timestamp.isoformat() if order.timestamp else None,
                    "error_message": order.error_message,
                    "env": self.env,
                    "dry_run": dry_run
                }
                f.write(json.dumps(order_dict, ensure_ascii=False) + "\n")
        
        logger.info(f"审计日志已保存到: {log_file}")
        return log_file