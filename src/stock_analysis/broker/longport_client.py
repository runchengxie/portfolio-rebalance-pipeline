import os
import time
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from dotenv import load_dotenv

# 兼容性导入：优先使用 longport，回退到 longbridge
try:
    from longport.openapi import Config, Market, QuoteContext, TradeContext
except ImportError:
    from longbridge.openapi import Config, Market, QuoteContext, TradeContext

# 时区支持（Python 3.9+），不可用时回退为本地时间判定
try:
    from zoneinfo import ZoneInfo  # type: ignore
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from datetime import date, datetime

load_dotenv()


def getenv_both(name_new: str, name_old: str, default: str = None) -> str:
    """兼容性环境变量读取函数，优先读取新前缀，回退到旧前缀。
    
    Args:
        name_new: 新的环境变量名（LONGPORT_*）
        name_old: 旧的环境变量名（LONGBRIDGE_*）
        default: 默认值
        
    Returns:
        环境变量值或默认值
    """
    return os.getenv(name_new) or os.getenv(name_old) or default


class Env(str, Enum):
    TEST = "test"
    REAL = "real"


@dataclass
class BrokerLimits:
    max_notional_per_order: float = 20000.0   # 单笔最大金额
    max_qty_per_order: int = 500             # 单笔最大股数（按美股演示）
    trading_window_start: str = "09:30"      # 本地时间（仅作为降级回退）
    trading_window_end: str = "16:00"


def _to_lb_symbol(ticker: str) -> str:
    """Convert ticker to LongPort symbol format.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        Formatted symbol for LongPort API
    """
    t = ticker.strip().upper()
    if t.endswith((".US", ".HK", ".SG", ".CN")):
        return t
    return f"{t}.US"  # 你的项目多数是美股，默认补 .US


def _market_of(symbol: str) -> str:
    s = symbol.upper()
    if s.endswith(".US"):
        return "US"
    if s.endswith(".HK"):
        return "HK"
    if s.endswith(".CN"):
        return "CN"
    if s.endswith(".SG"):
        return "SG"
    # 默认为美股
    return "US"


def _market_enum(m: str) -> Market:
    return {
        "US": Market.US,
        "HK": Market.HK,
        "CN": Market.CN,
        "SG": Market.SG,
    }[m]


def _market_tz(m: str) -> str:
    # 交易所本地时区
    return {
        "US": "America/New_York",
        "HK": "Asia/Hong_Kong",
        "CN": "Asia/Shanghai",
        "SG": "Asia/Singapore",
    }[m]


class LongPortClient:
    """LongPort API client for quotes and trading.
    
    Provides a thin wrapper around LongPort OpenAPI for:
    - Real-time quotes
    - Historical candlestick data
    - Order submission with risk controls
    """
    
    def __init__(self, env: str = None, limits: BrokerLimits | None = None) -> None:
        """Initialize LongPort client.
        
        Args:
            env: Environment (test/real). If None, uses LONGPORT_DEFAULT_ENV or defaults to test.
            limits: Risk control limits. If None, uses default limits.
        """
        default_env = getenv_both("LONGPORT_DEFAULT_ENV", "LONGBRIDGE_DEFAULT_ENV", "test")
        self.env = Env((env or default_env).lower())
        self.region = getenv_both("LONGPORT_REGION", "LONGBRIDGE_REGION", "hk")
        self.app_key = getenv_both("LONGPORT_APP_KEY", "LONGBRIDGE_APP_KEY")
        self.app_secret = getenv_both("LONGPORT_APP_SECRET", "LONGBRIDGE_APP_SECRET")
        self.token_test = getenv_both("LONGPORT_ACCESS_TOKEN_TEST", "LONGBRIDGE_ACCESS_TOKEN_TEST")
        self.token_real = getenv_both("LONGPORT_ACCESS_TOKEN_REAL", "LONGBRIDGE_ACCESS_TOKEN_REAL")
        self.token_fallback = getenv_both("LONGPORT_ACCESS_TOKEN", "LONGBRIDGE_ACCESS_TOKEN")

        if self.env == Env.TEST:
            access_token = self.token_test or self.token_fallback
        else:
            access_token = self.token_real or self.token_fallback

        if not all([self.app_key, self.app_secret, access_token]):
            raise RuntimeError("LongPort 凭据不完整，请检查 .env")

        # Config 会根据 token 自动识别纸交易或实盘
        self.config = Config(
            app_key=self.app_key,
            app_secret=self.app_secret,
            access_token=access_token,
        )

        self.quote = QuoteContext(self.config)
        self.trade = TradeContext(self.config)
        self.limits = limits or BrokerLimits()

        # 是否允许扩展时段（盘前/盘后/隔夜）
        enable_overnight = getenv_both("LONGPORT_ENABLE_OVERNIGHT", "LONGBRIDGE_ENABLE_OVERNIGHT", "false")
        self.allow_extended = str(enable_overnight).strip().lower() in {"1", "true", "yes", "y"}

        # 缓存：交易日与当日交易时段（TTL: 10分钟）
        self._session_cache: dict[str, list[tuple[int, int, str]]] = {}
        self._session_cache_expire_at: float = 0.0
        self._is_trading_day_cache: dict[str, bool] = {}
        self._day_cache_expire_at: float = 0.0
        self._cache_ttl_seconds: int = 600

    # ---------- 读行情 ----------
    def quote_last(self, symbols: Iterable[str]) -> dict[str, tuple[float, str]]:
        """Get last quotes for given symbols.
        
        Args:
            symbols: List of ticker symbols
            
        Returns:
            Dict mapping symbol to (last_price, timestamp) tuple
        """
        bars: dict[str, tuple[float, str]] = {}
        symbol_list = [_to_lb_symbol(x) for x in symbols]
        ret = self.quote.quote(symbol_list)
        for i in ret:
            bars[i.symbol] = (i.last_done or 0.0, i.timestamp or "")
        return bars

    def portfolio_snapshot(self) -> tuple[float, dict[str, int]]:
        """返回现金余额与持仓数量映射。
        Returns:
            cash_usd: 可用或总现金（USD 为主，必要时合并）
            positions: { "AAPL.US": 100, ... }
        """
        cash = 0.0
        pos_map: dict[str, int] = {}

        # 1) 现金：尽量宽松兼容不同返回结构
        try:
            # 常见：asset() 或 account_balance()
            asset_fn = getattr(self.trade, "asset", None) or getattr(self.trade, "account_balance", None)
            if asset_fn:
                asset = asset_fn()
                # 优先 USD，可回退到总币种合计
                if hasattr(asset, "cash_infos") and asset.cash_infos:
                    for ci in asset.cash_infos:
                        ccy = getattr(ci, "currency", "") or getattr(ci, "ccy", "")
                        amt = float(getattr(ci, "cash", 0) or getattr(ci, "available_cash", 0) or 0)
                        if str(ccy).upper() == "USD":
                            cash += amt
                    if cash == 0.0:
                        # 合计所有币种，粗暴但好用
                        for ci in asset.cash_infos:
                            cash += float(getattr(ci, "cash", 0) or getattr(ci, "available_cash", 0) or 0)
                else:
                    # 其他字段名兜底
                    for name in ("cash", "available_cash", "total_cash"):
                        v = getattr(asset, name, None)
                        if v is not None:
                            cash = float(v)
                            break
        except Exception:
            # 实在拿不到，就当 0，后面也还能按市值算目标
            cash = 0.0

        # 2) 持仓
        try:
            pos_fn = getattr(self.trade, "position_list", None) or getattr(self.trade, "stock_positions", None)
            if pos_fn:
                ret = pos_fn()
                items = getattr(ret, "positions", None) or getattr(ret, "items", None) or ret
                for it in items or []:
                    sym = getattr(it, "symbol", "") or getattr(it, "stock", "")
                    qty = getattr(it, "quantity", None) or getattr(it, "qty", None) or getattr(it, "position", None)
                    if sym and qty:
                        pos_map[_to_lb_symbol(str(sym))] = int(qty)
        except Exception:
            pass

        return float(cash), pos_map

    def lot_size(self, symbol: str) -> int:
        """查询最小交易单位，查不到就返回 1。"""
        try:
            info = self.quote.static_info([_to_lb_symbol(symbol)])
            if info and info[0].lot_size:
                return max(1, int(info[0].lot_size))
        except Exception:
            pass
        return 1

    # ---------- 内部：权威开市信息缓存 ----------
    def _refresh_caches_if_needed(self) -> None:
        now_ts = time.time()
        # 刷新交易时段缓存
        if now_ts >= self._session_cache_expire_at:
            try:
                resp = self.quote.trading_session()
                session_map: dict[str, list[tuple[int, int, str]]] = {}
                for item in getattr(resp, "market_trade_session", []) or []:
                    market = getattr(item, "market", "").upper()
                    sessions = []
                    for seg in getattr(item, "trade_session", []) or []:
                        beg = int(getattr(seg, "beg_time", 0))  # hhmm
                        end = int(getattr(seg, "end_time", 0))  # hhmm
                        code = getattr(seg, "trade_session", None)
                        # 约定：None/0 => Regular, 1 => Pre, 2 => Post, 3 => Overnight（若支持）
                        if code in (None, 0):
                            kind = "Regular"
                        elif code == 1:
                            kind = "Pre"
                        elif code == 2:
                            kind = "Post"
                        elif code == 3:
                            kind = "Overnight"
                        else:
                            kind = "Other"
                        sessions.append((beg, end, kind))
                    if market:
                        session_map[market] = sessions
                self._session_cache = session_map
                self._session_cache_expire_at = now_ts + self._cache_ttl_seconds
            except Exception:
                # 不可用时清空并立即过期，留给降级逻辑处理
                self._session_cache = {}
                self._session_cache_expire_at = 0.0
        
        # 刷新“今天是否交易日”缓存（按市场）
        if now_ts >= self._day_cache_expire_at:
            try:
                today = date.today()
                # 我们只在用到某个市场时再填充，先清空
                self._is_trading_day_cache = {}
                self._day_cache_expire_at = now_ts + self._cache_ttl_seconds
            except Exception:
                self._is_trading_day_cache = {}
                self._day_cache_expire_at = 0.0

    def _is_trading_day(self, market_str: str) -> bool:
        # 先看缓存
        if market_str in self._is_trading_day_cache:
            return self._is_trading_day_cache[market_str]
        try:
            today = date.today()
            resp = self.quote.trading_days(_market_enum(market_str), today, today)
            days = set(getattr(resp, "trade_day", []) or [])
            # API 返回 YYMMDD 字符串，简单比较今日是否在其中
            yymmdd = today.strftime("%Y%m%d")[2:]  # 转为YYMMDD
            ok = yymmdd in days
            self._is_trading_day_cache[market_str] = ok
            return ok
        except Exception:
            # API 失败：保守返回 False（fail closed）
            self._is_trading_day_cache[market_str] = False
            return False

    # ---------- 下单前检查 ----------
    def _check_window(self, symbol: str) -> None:
        """Check if current time is within trading window.
        
        使用 LongPort 权威交易时段与交易日接口。若接口不可用则回退为本地时间粗判。
        """
        self._refresh_caches_if_needed()

        symbol_fmt = _to_lb_symbol(symbol)
        market_str = _market_of(symbol_fmt)

        # 1) 非交易日则拒绝
        if not self._is_trading_day(market_str):
            raise RuntimeError("非交易日，禁止交易")

        # 2) 权威分段判定
        sessions = self._session_cache.get(market_str, [])
        if sessions and ZoneInfo is not None:
            tz = ZoneInfo(_market_tz(market_str))
            now_ex = datetime.now(tz)
            hhmm = now_ex.hour * 100 + now_ex.minute
            # 允许的分段
            def allowed(kind: str) -> bool:
                if kind == "Regular":
                    return True
                # 盘前/盘后/隔夜：仅当允许扩展时段时放行
                return self.allow_extended and (kind in {"Pre", "Post", "Overnight", "Other"})

            in_any = any(beg <= hhmm <= end and allowed(kind) for beg, end, kind in sessions)
            if not in_any:
                allowed_kinds = {k for _, _, k in sessions if allowed(k)}
                win = ", ".join([f"{beg:04d}-{end:04d}({k})" for beg, end, k in sessions if k in allowed_kinds]) or "无"
                raise RuntimeError(f"不在允许的交易时段：{win}")
            return

        # 3) 降级：本地时间字符串粗判（原有逻辑）
        now_local = datetime.now().strftime("%H:%M")
        if not (self.limits.trading_window_start <= now_local <= self.limits.trading_window_end):
            raise RuntimeError(
                f"不在交易时段 {self.limits.trading_window_start}-{self.limits.trading_window_end}（降级判定）"
            )

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

        # 干跑或 TEST：跳过时间窗检查，但保留 lot 与金额估算
        if dry_run or self.env == Env.TEST:
            lot = self.lot_size(symbol_formatted)
            if qty % lot != 0:
                raise RuntimeError(f"{symbol_formatted} 数量需为最小交易单位 {lot} 的整数倍")
            px, _ = self.quote_last([symbol]).get(symbol_formatted, (0.0, ""))
            notional = px * qty
            if notional > self.limits.max_notional_per_order:
                raise RuntimeError(f"超过单笔金额上限 ${self.limits.max_notional_per_order:,.0f}")
            return {
                "env": self.env.value,
                "dry_run": True,
                "symbol": symbol_formatted,
                "qty": qty,
                "side": side,
                "est_px": px,
                "est_notional": notional,
                "ts": time.time(),
            }

        # 真下单：严格检查
        self._check_window(symbol_formatted)  # 原逻辑在这里再调用
        self._check_lot(symbol_formatted, qty)
        if qty > self.limits.max_qty_per_order:
            raise RuntimeError(f"超过单笔数量上限 {self.limits.max_qty_per_order}")
        px, _ = self.quote_last([symbol]).get(symbol_formatted, (0.0, ""))
        notional = px * qty
        if notional > self.limits.max_notional_per_order:
            raise RuntimeError(f"超过单笔金额上限 ${self.limits.max_notional_per_order:,.0f}")

        # TODO: 调 LongPort 真下单接口（此处留白以免误触）
        return {
            "env": self.env.value,
            "dry_run": False,
            "symbol": symbol_formatted,
            "qty": qty,
            "side": side,
            "est_px": px,
            "est_notional": notional,
            "ts": time.time(),
            "order_id": "SIMULATED_ID",
        }

    def close(self):
        """Close quote and trade contexts (容错，不依赖 SDK 是否提供 close)。"""
        for ctx in (self.quote, self.trade):
            try:
                fn = getattr(ctx, "close", None)
                if callable(fn):
                    fn()
            except Exception:
                # 忽略关闭异常，避免影响主流程
                pass


# 兼容性别名，保持向后兼容
LongBridgeClient = LongPortClient