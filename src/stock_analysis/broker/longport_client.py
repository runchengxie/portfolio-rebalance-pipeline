import os
import time
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

# Compatibility import: prefer longport, fallback to longbridge
try:
    from longport.openapi import Config, Market, QuoteContext, TradeContext
except ImportError:
    from longbridge.openapi import Config, Market, QuoteContext, TradeContext

# Timezone support (Python 3.9+), fallback to local time determination when unavailable
try:
    from zoneinfo import ZoneInfo  # type: ignore
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from datetime import date, datetime


def get_config():
    """Return LongPort configuration based on environment variables.

    Compatible with direct calls in tests, equivalent to Config.from_env().
    """
    return Config.from_env()


def getenv_both(name_new: str, name_old: str, default: str = None) -> str:
    """Compatibility environment variable reading function, prioritize new prefix, fallback to old prefix.

    Args:
        name_new: New environment variable name (LONGPORT_*)
        name_old: Old environment variable name (LONGBRIDGE_*)
        default: Default value

    Returns:
        Environment variable value or default value
    """
    return os.getenv(name_new) or os.getenv(name_old) or default


class Env(str, Enum):
    REAL = "real"


@dataclass
class BrokerLimits:
    max_notional_per_order: float = 20000.0  # Maximum amount per order
    max_qty_per_order: int = 500  # Maximum shares per order (US stock example)
    trading_window_start: str = "09:30"  # Local time (fallback only)
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
    return f"{t}.US"  # Most stocks in your project are US stocks, default to .US


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
    # Exchange local timezone
    return {
        "US": "America/New_York",
        "HK": "Asia/Hong_Kong",
        "CN": "Asia/Shanghai",
        "SG": "Asia/Singapore",
    }[m]


class LongPortClient:
    """LongPort client for stock trading and querying.

    Provides a unified interface to access LongPort's trading and quote functionality.
    """

    def __init__(self, env: str | None = None, limits: BrokerLimits | None = None, config=None):
        """Initialize LongPort client.

        Args:
            config: LongPort configuration object, if None then read from environment variables
        """
        # Force use of REAL environment
        self.env = Env.REAL
        self.region = getenv_both("LONGPORT_REGION", "LONGBRIDGE_REGION", "hk")

        self.app_key = getenv_both("LONGPORT_APP_KEY", "LONGBRIDGE_APP_KEY")
        self.app_secret = getenv_both("LONGPORT_APP_SECRET", "LONGBRIDGE_APP_SECRET")
        self.token_test = getenv_both(
            "LONGPORT_ACCESS_TOKEN_TEST", "LONGBRIDGE_ACCESS_TOKEN_TEST"
        )
        # Live trading prioritizes LONGPORT_ACCESS_TOKEN, compatible with legacy LONGPORT_ACCESS_TOKEN_REAL
        self.token_real = os.getenv("LONGPORT_ACCESS_TOKEN") or os.getenv(
            "LONGPORT_ACCESS_TOKEN_REAL"
        )

        # Validate required items first
        if not self.app_key or not self.app_secret:
            raise RuntimeError("缺少 LONGPORT_APP_KEY/SECRET。请通过系统环境变量注入。")

        # Only support REAL environment
        if not self.token_real:
            raise RuntimeError(
                "缺少 LONGPORT_ACCESS_TOKEN（或兼容 LONGPORT_ACCESS_TOKEN_REAL）。请通过系统环境变量注入。"
            )
        access_token = self.token_real

        # Inject token/region via environment variables, then use SDK's from_env to select correct endpoint and default config
        self._prev_env = {
            "LONGPORT_APP_KEY": os.getenv("LONGPORT_APP_KEY"),
            "LONGPORT_APP_SECRET": os.getenv("LONGPORT_APP_SECRET"),
            "LONGPORT_ACCESS_TOKEN": os.getenv("LONGPORT_ACCESS_TOKEN"),
            "LONGPORT_REGION": os.getenv("LONGPORT_REGION"),
        }
        os.environ["LONGPORT_APP_KEY"] = self.app_key
        os.environ["LONGPORT_APP_SECRET"] = self.app_secret
        os.environ["LONGPORT_ACCESS_TOKEN"] = access_token
        if self.region:
            os.environ["LONGPORT_REGION"] = self.region
        # Uniformly use SDK recommended from_env to ensure correct region and routing
        self.config = Config.from_env()

        self.quote = QuoteContext(self.config)
        self.trade = TradeContext(self.config)
        self.limits = limits or BrokerLimits()

        enable_overnight = getenv_both(
            "LONGPORT_ENABLE_OVERNIGHT", "LONGBRIDGE_ENABLE_OVERNIGHT", "false"
        )
        self.allow_extended = str(enable_overnight).strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
        }

        # Cache related
        self._session_cache: dict[str, list[tuple[int, int, str]]] = {}
        self._session_cache_expire_at: float = 0.0
        self._is_trading_day_cache: dict[str, bool] = {}
        self._day_cache_expire_at: float = 0.0
        self._cache_ttl_seconds: int = 600

    # ---------- Quote Data ----------
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
            # Prefer last_done, fallback to prev_close if missing/zero
            px = float((getattr(i, "last_done", 0) or 0) or 0)
            if px <= 0:
                prev = getattr(i, "prev_close", None)
                if prev not in (None, 0):
                    try:
                        px = float(prev)
                    except Exception:
                        px = 0.0
            bars[i.symbol] = (px, getattr(i, "timestamp", "") or "")
        return bars

    def portfolio_snapshot(self) -> tuple[float, dict[str, int], float | None, str | None]:
        """
        Get account snapshot including cash and position information.
        
        Returns:
            Tuple of (cash_usd, stock_position_map, net_assets, base_currency)
            - cash_usd: USD available cash only (no FX conversion)
            - stock_position_map: {'AAPL.US': 100, ...}
            - net_assets: Total assets from broker (multi-currency/positions), if available
            - base_currency: Currency of net_assets (e.g. 'HKD')

        Compatible with different SDK versions of asset/balance and stock_positions/position_list return formats.
        """
        cash_usd = 0.0
        pos_map: dict[str, int] = {}
        net_assets: float | None = None
        base_ccy: str | None = None

        # ---------- Cash ----------
        try:
            asset_fn = getattr(self.trade, "asset", None) or getattr(
                self.trade, "account_balance", None
            )
            if asset_fn:
                asset = asset_fn()
                # 1) Prioritize aggregation from cash_infos
                ci_list = (
                    getattr(asset, "cash_infos", None)
                    or getattr(asset, "cash_info", None)
                    or []
                )
                totals: dict[str, float] = {}
                for ci in ci_list:
                    ccy = str(
                        getattr(ci, "currency", "") or getattr(ci, "ccy", "")
                    ).upper()
                    amt = float(
                        getattr(ci, "cash", 0) or getattr(ci, "available_cash", 0) or 0
                    )
                    if not ccy:
                        continue
                    totals[ccy] = totals.get(ccy, 0.0) + amt
                # Only use USD cash as cash_usd, avoid incorrect multi-currency addition
                cash_usd = totals.get("USD", 0.0)
                # Broker's total assets and currency
                na = getattr(asset, "net_assets", None)
                if na is not None:
                    try:
                        net_assets = float(na)
                    except Exception:
                        net_assets = None
                base_ccy = str(getattr(asset, "currency", "") or "").upper() or None
                # 3) Fallback to common fields if still zero
                if cash_usd == 0.0:
                    for name in ("cash", "available_cash", "total_cash"):
                        v = getattr(asset, name, None)
                        if v is not None:
                            cash_usd = float(v)
                            break
        except Exception:
            pass  # For display only, ignore if unavailable

        # ---------- Positions ----------
        try:
            pos_fn = getattr(self.trade, "stock_positions", None) or getattr(
                self.trade, "position_list", None
            )
            if not pos_fn:
                return cash_usd, pos_map, net_assets, base_ccy

            ret = pos_fn()

            # Compatible with multiple formats:
            # 1) Object has .list; 2) Object has .channels (new version return);
            # 3) dict has same-named keys; 4) Direct list
            groups = getattr(ret, "list", None) or getattr(ret, "channels", None)
            if groups is None and isinstance(ret, dict):
                groups = ret.get("list", None) or ret.get("channels", None)
            if groups is None:
                groups = ret  # Some SDKs directly return flattened list

            def push(sym, qty, market=None):
                if sym is None or qty is None:
                    return
                try:
                    q = int(float(qty))
                except Exception:
                    return
                s = str(sym).upper()
                if "." not in s and market:
                    s = f"{s}.{str(market).upper()}"
                pos_map[s] = pos_map.get(s, 0) + q

            if isinstance(groups, list):
                for g in groups:
                    # Format A (old): Group object contains stock_info list
                    stock_info = getattr(g, "stock_info", None)
                    if stock_info is None and isinstance(g, dict):
                        stock_info = g.get("stock_info")

                    if stock_info is not None:
                        for it in stock_info:
                            sym = (
                                getattr(it, "symbol", None)
                                if not isinstance(it, dict)
                                else it.get("symbol")
                            )
                            qty = (
                                getattr(it, "quantity", None)
                                if not isinstance(it, dict)
                                else it.get("quantity")
                            )
                            mkt = (
                                getattr(it, "market", None)
                                if not isinstance(it, dict)
                                else it.get("market")
                            )
                            push(sym, qty, mkt)
                    else:
                        # Format B (new): Group contains positions list (e.g. ret.channels[].positions)
                        positions = getattr(g, "positions", None)
                        if positions is None and isinstance(g, dict):
                            positions = g.get("positions")
                        if positions is not None:
                            for it in positions:
                                sym = (
                                    getattr(it, "symbol", None)
                                    if not isinstance(it, dict)
                                    else it.get("symbol")
                                )
                                qty = (
                                    getattr(it, "quantity", None)
                                    if not isinstance(it, dict)
                                    else it.get("quantity")
                                )
                                mkt = (
                                    getattr(it, "market", None)
                                    if not isinstance(it, dict)
                                    else it.get("market")
                                )
                                push(sym, qty, mkt)
                        else:
                            # Format C: Already flattened Position object
                            it = g
                            sym = (
                                getattr(it, "symbol", None)
                                if not isinstance(it, dict)
                                else it.get("symbol")
                            )
                            qty = (
                                getattr(it, "quantity", None)
                                if not isinstance(it, dict)
                                else it.get("quantity")
                            )
                            mkt = (
                                getattr(it, "market", None)
                                if not isinstance(it, dict)
                                else it.get("market")
                            )
                            push(sym, qty, mkt)
        except Exception:
            # Return empty if unavailable, caller will gracefully degrade
            pass

        return cash_usd, pos_map, net_assets, base_ccy

    def fund_positions(self) -> dict[str, tuple[float, float, str]]:
        """
        Get fund position information.
        
        Returns:
            Fund position mapping: { symbol => (holding_units, current_nav, currency) }
            - symbol: Fund code/ISIN returned by LongPort
            - holding_units: Holding units (float)
            - current_nav: Current net asset value (float)
            - currency: Currency code
        """
        result: dict[str, tuple[float, float, str]] = {}
        try:
            fn = getattr(self.trade, "fund_positions", None)
            if not fn:
                return result
            resp = fn()
            # Format: resp.list[account].fund_info[*]
            accounts = getattr(resp, "list", None) or []
            for acc in accounts:
                fund_info = getattr(acc, "fund_info", None) or []
                for it in fund_info:
                    sym = (
                        getattr(it, "symbol", None)
                        if not isinstance(it, dict)
                        else it.get("symbol")
                    )
                    units = (
                        getattr(it, "holding_units", None)
                        if not isinstance(it, dict)
                        else it.get("holding_units")
                    )
                    nav = (
                        getattr(it, "current_net_asset_value", None)
                        if not isinstance(it, dict)
                        else it.get("current_net_asset_value")
                    )
                    ccy = (
                        getattr(it, "currency", None)
                        if not isinstance(it, dict)
                        else it.get("currency")
                    )
                    if sym is None or units is None or nav is None:
                        continue
                    try:
                        u = float(units)
                        p = float(nav)
                    except Exception:
                        continue
                    result[str(sym)] = (u, p, str(ccy or ""))
        except Exception:
            # Failure to get fund positions doesn't affect main flow
            pass
        return result

    def lot_size(self, symbol: str) -> int:
        """Get the lot size (shares per lot) for a stock.

        Args:
            symbol: Stock symbol

        Returns:
            Shares per lot
        """
        # Fast path: US stocks default to 1, avoid unnecessary permission output from static info queries
        if _market_of(symbol) == "US":
            return 1
        try:
            info = self.quote.static_info([_to_lb_symbol(symbol)])
            if info and info[0].lot_size:
                return max(1, int(info[0].lot_size))
        except Exception:
            pass
        return 1

    # ---------- Internal: Authoritative market info caching ----------
    def _refresh_caches_if_needed(self) -> None:
        """Refresh trading session and trading day cache if expired."""
        now_ts = time.time()
        # Refresh trading session cache
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
                        # Convention: None/0 => Regular, 1 => Pre, 2 => Post, 3 => Overnight (if supported)
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
                # Clear and expire immediately when unavailable, leave to fallback logic
                self._session_cache = {}
                self._session_cache_expire_at = 0.0

        # Refresh "is today a trading day" cache (by market)
        if now_ts >= self._day_cache_expire_at:
            try:
                date.today()
                # We only populate when a market is used, clear first
                self._is_trading_day_cache = {}
                self._day_cache_expire_at = now_ts + self._cache_ttl_seconds
            except Exception:
                self._is_trading_day_cache = {}
                self._day_cache_expire_at = 0.0

    def _is_trading_day(self, market_str: str) -> bool:
        # Check cache first
        if market_str in self._is_trading_day_cache:
            return self._is_trading_day_cache[market_str]
        try:
            today = date.today()
            resp = self.quote.trading_days(_market_enum(market_str), today, today)
            days = set(getattr(resp, "trade_day", []) or [])
            # API returns YYMMDD string, simply check if today is in it
            yymmdd = today.strftime("%Y%m%d")[2:]  # Convert to YYMMDD
            ok = yymmdd in days
            self._is_trading_day_cache[market_str] = ok
            return ok
        except Exception:
            # API failure: conservatively return False (fail closed)
            self._is_trading_day_cache[market_str] = False
            return False

    # ---------- Pre-order checks ----------
    def _check_window(self, symbol: str) -> None:
        """Check if current time is within trading window.

        Uses LongPort authoritative trading session and trading day interface. Falls back to local time estimation if interface unavailable.
        """
        self._refresh_caches_if_needed()

        symbol_fmt = _to_lb_symbol(symbol)
        market_str = _market_of(symbol_fmt)

        # 1) Reject if not a trading day
        if not self._is_trading_day(market_str):
            raise RuntimeError("非交易日，禁止交易")

        # 2) Authoritative segment determination
        sessions = self._session_cache.get(market_str, [])
        if sessions and ZoneInfo is not None:
            tz = ZoneInfo(_market_tz(market_str))
            now_ex = datetime.now(tz)
            hhmm = now_ex.hour * 100 + now_ex.minute

            # Allowed segments
            def allowed(kind: str) -> bool:
                if kind == "Regular":
                    return True
                # Pre/Post/Overnight: only allow when extended hours are enabled
                return self.allow_extended and (
                    kind in {"Pre", "Post", "Overnight", "Other"}
                )

            in_any = any(
                beg <= hhmm <= end and allowed(kind) for beg, end, kind in sessions
            )
            if not in_any:
                allowed_kinds = {k for _, _, k in sessions if allowed(k)}
                win = (
                    ", ".join(
                        [
                            f"{beg:04d}-{end:04d}({k})"
                            for beg, end, k in sessions
                            if k in allowed_kinds
                        ]
                    )
                    or "无"
                )
                raise RuntimeError(f"不在允许的交易时段：{win}")
            return

        # 3) Fallback: rough local time string check (original logic)
        now_local = datetime.now().strftime("%H:%M")
        if not (
            self.limits.trading_window_start
            <= now_local
            <= self.limits.trading_window_end
        ):
            raise RuntimeError(
                f"不在交易时段 {self.limits.trading_window_start}-{self.limits.trading_window_end}（降级判定）"
            )

    def _check_lot(self, symbol: str, qty: int) -> None:
        """Check if quantity is valid lot size."""
        sec = self.quote.static_info([symbol])[0]
        lot = max(1, sec.lot_size or 1)
        if qty % lot != 0:
            raise RuntimeError(f"{symbol} 数量需为最小交易单位 {lot} 的整数倍")

    # ---------- Order placement (market order equal weight example) ----------
    def place_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        dry_run: bool = True,
        est_px: float | None = None,
    ) -> dict:
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

        # Dry run or TEST: skip time window check, but keep lot and amount estimation
        if dry_run:
            lot = self.lot_size(symbol_formatted)
            if qty % lot != 0:
                raise RuntimeError(
                    f"{symbol_formatted} 数量需为最小交易单位 {lot} 的整数倍"
                )
            px = float(est_px) if est_px is not None else self.quote_last([symbol]).get(symbol_formatted, (0.0, ""))[0]
            notional = px * qty
            if notional > self.limits.max_notional_per_order:
                raise RuntimeError(
                    f"超过单笔金额上限 ${self.limits.max_notional_per_order:,.0f}"
                )
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

        # Real order: strict checks
        self._check_window(symbol_formatted)  # Original logic called here again
        self._check_lot(symbol_formatted, qty)
        if qty > self.limits.max_qty_per_order:
            raise RuntimeError(f"超过单笔数量上限 {self.limits.max_qty_per_order}")
        px = float(est_px) if est_px is not None else self.quote_last([symbol]).get(symbol_formatted, (0.0, ""))[0]
        notional = px * qty
        if notional > self.limits.max_notional_per_order:
            raise RuntimeError(
                f"超过单笔金额上限 ${self.limits.max_notional_per_order:,.0f}"
            )

        # TODO: Call LongPort real order interface (left blank to avoid accidental triggering)
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
        """Close quote and trade contexts (fault-tolerant, does not depend on whether SDK provides close)."""
        for ctx in (self.quote, self.trade):
            try:
                fn = getattr(ctx, "close", None)
                if callable(fn):
                    fn()
            except Exception:
                # Ignore close exceptions to avoid affecting main flow
                pass
        # Restore environment variables to avoid affecting subsequent instances or other usage in processes
        try:
            for k, v in (getattr(self, "_prev_env", {}) or {}).items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        except Exception:
            # Any restoration failure should not affect the caller
            pass
