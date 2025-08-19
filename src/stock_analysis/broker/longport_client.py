import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, Tuple

from dotenv import load_dotenv
from longbridge import Config
from longbridge.openapi import QuoteContext, TradeContext

load_dotenv()

class Env(str, Enum):
    TEST = "test"
    REAL = "real"

@dataclass
class BrokerLimits:
    max_notional_per_order: float = 20000.0   # 单笔最大金额
    max_qty_per_order: int = 500             # 单笔最大股数（按美股演示）
    trading_window_start: str = "09:30"      # 本地时间
    trading_window_end: str = "16:00"

def _to_lb_symbol(ticker: str) -> str:
    """Convert ticker to LongBridge symbol format.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        Formatted symbol for LongBridge API
    """
    t = ticker.strip().upper()
    if t.endswith((".US", ".HK", ".SG")):
        return t
    return f"{t}.US"  # 你的项目多数是美股，默认补 .US

class LongPortClient:
    """LongBridge API client for quotes and trading.
    
    Provides a thin wrapper around LongBridge OpenAPI for:
    - Real-time quotes
    - Historical candlestick data
    - Order submission with risk controls
    """
    
    def __init__(self, env: str = None, limits: BrokerLimits | None = None) -> None:
        """Initialize LongBridge client.
        
        Args:
            env: Environment (test/real). If None, uses LONGBRIDGE_DEFAULT_ENV or defaults to test.
            limits: Risk control limits. If None, uses default limits.
        """
        self.env = Env((env or os.getenv("LONGBRIDGE_DEFAULT_ENV", "test")).lower())
        self.region = os.getenv("LONGBRIDGE_REGION", "hk")
        self.app_key = os.getenv("LONGBRIDGE_APP_KEY")
        self.app_secret = os.getenv("LONGBRIDGE_APP_SECRET")
        self.token_test = os.getenv("LONGBRIDGE_ACCESS_TOKEN_TEST")
        self.token_real = os.getenv("LONGBRIDGE_ACCESS_TOKEN_REAL")
        self.token_fallback = os.getenv("LONGBRIDGE_ACCESS_TOKEN")

        if self.env == Env.TEST:
            access_token = self.token_test or self.token_fallback
        else:
            access_token = self.token_real or self.token_fallback

        if not all([self.app_key, self.app_secret, access_token]):
            raise RuntimeError("LongBridge 凭据不完整，请检查 .env")

        # longbridge.Config 会根据 token 自动识别纸交易或实盘
        self.config = Config(
            app_key=self.app_key,
            app_secret=self.app_secret,
            access_token=access_token,
            http_url=None,  # 用默认
            quote_endpoint=None,
            trade_endpoint=None,
        )

        self.quote = QuoteContext(self.config)
        self.trade = TradeContext(self.config)
        self.limits = limits or BrokerLimits()

    # ---------- 读行情 ----------
    def quote_last(self, symbols: Iterable[str]) -> Dict[str, Tuple[float, str]]:
        """Get last quotes for given symbols.
        
        Args:
            symbols: List of ticker symbols
            
        Returns:
            Dict mapping symbol to (last_price, timestamp) tuple
        """
        bars: Dict[str, Tuple[float, str]] = {}
        symbol_list = [_to_lb_symbol(x) for x in symbols]
        ret = self.quote.quote(symbol_list)
        for i in ret:
            bars[i.symbol] = (i.last_done or 0.0, i.timestamp or "")
        return bars

    # ---------- 下单前检查 ----------
    def _check_window(self) -> None:
        """Check if current time is within trading window."""
        # 简化版：只按本地时间字符串判断
        from datetime import datetime
        now = datetime.now().strftime("%H:%M")
        if not (self.limits.trading_window_start <= now <= self.limits.trading_window_end):
            raise RuntimeError(f"不在交易时段 {self.limits.trading_window_start}-{self.limits.trading_window_end}")

    def _check_lot(self, symbol: str, qty: int) -> None:
        """Check if quantity is valid lot size."""
        sec = self.quote.static_info([symbol])[0]
        lot = max(1, sec.lot_size or 1)
        if qty % lot != 0:
            raise RuntimeError(f"{symbol} 数量需为最小交易单位 {lot} 的整数倍")

    # ---------- 下单（市价等权示例） ----------
    def place_order(self, symbol: str, qty: int, side: str, dry_run: bool = True) -> dict:
        """Place order with risk controls.
        
        Args:
            symbol: Stock symbol
            qty: Quantity to trade
            side: Order side (BUY/SELL)
            dry_run: If True, only simulate the order
            
        Returns:
            Order result dictionary
        """
        if qty <= 0:
            raise ValueError("下单数量必须为正")

        symbol_formatted = _to_lb_symbol(symbol)
        
        self._check_window()
        self._check_lot(symbol_formatted, qty)
        if qty > self.limits.max_qty_per_order:
            raise RuntimeError(f"超过单笔数量上限 {self.limits.max_qty_per_order}")

        # 拉一口价估个名义金额做风控
        px, _ = self.quote_last([symbol]).get(symbol_formatted, (0.0, ""))
        notional = px * qty
        if notional > self.limits.max_notional_per_order:
            raise RuntimeError(f"超过单笔金额上限 ${self.limits.max_notional_per_order:,.0f}")

        if dry_run or self.env == Env.TEST:
            return {
                "env": self.env.value,
                "dry_run": True,
                "symbol": symbol_formatted,
                "qty": qty,
                "side": side,
                "est_px": px,
                "est_notional": notional,
                "ts": int(time.time()),
            }

        # 真下单
        # 这里以美股市价单演示；不同市场下单参数请按 longbridge 文档设置
        resp = self.trade.submit_order(
            symbol=symbol_formatted,
            order_type="MO",  # 市价
            side=side.upper(),  # BUY / SELL
            submitted_quantity=qty,
            # time_in_force="DAY",
        )
        return {
            "env": self.env.value,
            "dry_run": False,
            "order_id": getattr(resp, "order_id", None),
            "symbol": symbol_formatted,
            "qty": qty,
            "side": side,
            "ts": int(time.time()),
        }

    def close(self):
        """Close quote and trade contexts."""
        self.quote.close()
        self.trade.close()