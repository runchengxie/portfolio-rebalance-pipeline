"""Data model definitions.

Defines core data structures used in the system.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Quote:
    """Stock quote data."""

    symbol: str
    price: float
    timestamp: str

    def __post_init__(self):
        """Data validation."""
        if self.price < 0:
            raise ValueError(f"价格不能为负数: {self.price}")


@dataclass
class Position:
    """Position data."""

    symbol: str
    quantity: int
    last_price: float
    estimated_value: float
    env: str = "test"

    def __post_init__(self):
        """Data validation and calculation."""
        if self.quantity < 0:
            raise ValueError(f"持仓数量不能为负数: {self.quantity}")
        if self.last_price < 0:
            raise ValueError(f"价格不能为负数: {self.last_price}")
        # Auto-calculate if no estimated value is provided
        if self.estimated_value == 0:
            self.estimated_value = self.quantity * self.last_price


@dataclass
class Order:
    """订单数据"""

    symbol: str
    quantity: int
    side: str  # "BUY" or "SELL"
    price: float | None = None
    order_type: str = "MARKET"
    status: str = "PENDING"
    order_id: str | None = None
    timestamp: datetime | None = None
    error_message: str | None = None
    # Phase 1 preview fields (optional)
    target_qty_frac: float | None = None
    rounded_target_qty: int | None = None
    rounding_loss: float | None = None
    est_fees: float | None = None
    est_frac_hint: float | None = None

    def __post_init__(self):
        """数据验证"""
        if self.quantity <= 0:
            raise ValueError(f"订单数量必须大于0: {self.quantity}")
        if self.side not in ["BUY", "SELL"]:
            raise ValueError(f"订单方向必须是 BUY 或 SELL: {self.side}")
        if self.price is not None and self.price <= 0:
            raise ValueError(f"价格必须大于0: {self.price}")
        if not self.timestamp:
            self.timestamp = datetime.now()


@dataclass
class AccountSnapshot:
    """账户快照数据"""

    env: str
    cash_usd: float
    positions: list[Position]
    total_market_value: float = 0.0
    total_portfolio_value: float = 0.0
    base_currency: str | None = None

    def __post_init__(self):
        """计算总值：若调用方提供了总资产，则优先使用。"""
        self.total_market_value = sum(pos.estimated_value for pos in self.positions)
        if not self.total_portfolio_value:
            self.total_portfolio_value = self.cash_usd + self.total_market_value


@dataclass
class RebalanceResult:
    """调仓结果数据"""

    target_positions: list[Position]
    current_positions: list[Position]
    orders: list[Order]
    total_portfolio_value: float
    target_value_per_stock: float
    dry_run: bool = True
    env: str = "test"
    sheet_name: str = ""

    @property
    def order_count(self) -> int:
        """订单数量"""
        return len(self.orders)

    @property
    def successful_orders(self) -> list[Order]:
        """成功的订单"""
        return [order for order in self.orders if order.status == "SUCCESS"]

    @property
    def failed_orders(self) -> list[Order]:
        """失败的订单"""
        return [order for order in self.orders if order.status == "FAILED"]
