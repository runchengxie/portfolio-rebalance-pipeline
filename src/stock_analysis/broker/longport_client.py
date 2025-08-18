# src/stock_analysis/broker/longport_client.py
from datetime import date
from decimal import Decimal
from longport.openapi import (
    Config, QuoteContext, TradeContext, Period, AdjustType,
    OrderType, OrderSide, TimeInForceType
)


def _to_lb_symbol(ticker: str) -> str:
    """Convert ticker to LongPort symbol format.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        Formatted symbol for LongPort API
    """
    t = ticker.strip().upper()
    if t.endswith((".US", ".HK", ".SG")):
        return t
    return f"{t}.US"  # 你的项目多数是美股，默认补 .US


def get_config() -> Config:
    """Get LongPort configuration from environment variables.
    
    Returns:
        Config object for LongPort API
    """
    # 优先用环境变量；你项目已在入口处 load_dotenv
    return Config.from_env()


class LongPortClient:
    """LongPort API client for quotes and trading.
    
    Provides a thin wrapper around LongPort OpenAPI for:
    - Real-time quotes
    - Historical candlestick data
    - Order submission
    """
    
    def __init__(self, cfg: Config | None = None):
        """Initialize LongPort client.
        
        Args:
            cfg: Optional config object. If None, loads from environment.
        """
        self.cfg = cfg or get_config()
        self.q = QuoteContext(self.cfg)
        self.t = TradeContext(self.cfg)

    def quote_last(self, tickers: list[str]):
        """Get last quotes for given tickers.
        
        Args:
            tickers: List of ticker symbols
            
        Returns:
            Dict mapping symbol to (last_price, timestamp) tuple
        """
        symbols = [_to_lb_symbol(x) for x in tickers]
        resp = self.q.quote(symbols)  # 官方示例同名接口
        return {r.symbol: (r.last_done, r.timestamp) for r in resp}

    def candles(self, ticker: str, start: date, end: date, period: Period = Period.Day):
        """Get historical candlestick data.
        
        Args:
            ticker: Stock ticker symbol
            start: Start date
            end: End date
            period: Time period for candles
            
        Returns:
            Historical candlestick data
        """
        return self.q.history_candlesticks_by_date(
            _to_lb_symbol(ticker), period, AdjustType.NoAdjust, start, end
        )

    def submit_limit(self, ticker: str, price: float, qty: int, 
                    tif: TimeInForceType = TimeInForceType.Day, 
                    remark: str | None = None):
        """Submit limit order.
        
        Args:
            ticker: Stock ticker symbol
            price: Limit price
            qty: Quantity (positive for buy, negative for sell)
            tif: Time in force
            remark: Optional order remark
            
        Returns:
            Order submission response
        """
        return self.t.submit_order(
            symbol=_to_lb_symbol(ticker),
            order_type=OrderType.LO,
            side=OrderSide.Buy if qty > 0 else OrderSide.Sell,
            submitted_price=Decimal(str(abs(price))),
            submitted_quantity=Decimal(str(abs(qty))),
            time_in_force=tif,
            remark=remark,
        )