"""Backtesting engine module

Provides unified backtest runner, strategy classes and report generation functionality.
"""

import datetime
from pathlib import Path
from typing import Any

import backtrader as bt
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd
from backtrader.metabase import findowner

# ``backtrader`` strategies require a ``Cerebro`` instance during
# instantiation.  For unit tests where strategies are created in isolation this
# instance is absent, leading to attribute errors.  A lightweight metaclass is
# provided to safely handle this scenario by giving the strategy a dummy id when
# no ``Cerebro`` owner is found.
from backtrader.strategy import MetaStrategy

from ..utils.logging import StrategyLogger
from ..utils.paths import OUTPUTS_DIR
from .prep import DividendPandasData


class _SafeMetaStrategy(MetaStrategy):
    """Metaclass that tolerates missing ``Cerebro`` when instantiating.

    When strategies are instantiated outside of a Backtrader ``Cerebro``
    environment (as the tests in this repository do), the original
    :class:`MetaStrategy` attempts to access ``cerebro._next_stid()`` and raises
    an ``AttributeError``.  This subclass assigns a dummy identifier instead of
    failing, allowing the strategy object to be constructed and its logic to be
    tested in isolation.
    """

    def donew(cls, *args, **kwargs):
        # Call ``MetaBase.donew`` directly to avoid the default ``MetaStrategy``
        # implementation which assumes the presence of a ``Cerebro`` instance.
        _obj, args, kwargs = super(MetaStrategy, cls).donew(*args, **kwargs)
        cerebro = findowner(_obj, bt.Cerebro)
        _obj.env = _obj.cerebro = cerebro
        _obj._id = cerebro._next_stid() if cerebro else 0
        return _obj, args, kwargs

    def dopreinit(cls, _obj, *args, **kwargs):
        # Skip heavy initialisation when running outside of Cerebro.  This
        # avoids dependencies on data feeds during unit tests.
        if getattr(_obj, "cerebro", None) is None:
            return _obj, args, kwargs
        return super().dopreinit(_obj, *args, **kwargs)

    def dopostinit(cls, _obj, *args, **kwargs):
        if getattr(_obj, "cerebro", None) is None:
            return _obj, args, kwargs
        return super().dopostinit(_obj, *args, **kwargs)


class PointInTimeStrategy(bt.Strategy, metaclass=_SafeMetaStrategy):
    """Unified point-in-time strategy class

    Integrates AI version and unfiltered version strategy logic,
    controlling differences through parameters.
    """

    params = (
        ("portfolios", None),
        ("use_logging", True),  # Control whether to use logging or print
        ("logger_name", "strategy"),
        ("log_level", None),
    )

    def __init__(self):
        """Initialise strategy state.

        ``PointInTimeStrategy`` is often instantiated in tests without passing
        the ``portfolios`` parameter and later re-initialised after the
        attribute has been populated.  The original implementation assumed that
        ``self.p.portfolios`` was always a dictionary, which caused an
        ``AttributeError`` when it was ``None``.  To make the strategy more
        robust and idempotent we gracefully handle a missing portfolio
        configuration by defaulting to an empty dictionary.
        """

        self.portfolios = self.p.portfolios or {}
        self.rebalance_dates = sorted(self.portfolios.keys())
        self.next_rebalance_idx = 0
        self.get_next_rebalance_date()
        # ``datas`` may be empty when instantiated outside of Cerebro
        self.timeline = self.datas[0] if getattr(self, "datas", []) else None
        self.rebalance_log = []

        # Initialize logger
        self.strategy_logger = StrategyLogger(
            use_logging=self.p.use_logging,
            logger_name=self.p.logger_name,
            level=self.p.log_level,
        )

    def log(self, txt, dt=None):
        """Log message"""
        if (
            dt is None
            and self.timeline is not None
            and hasattr(self.timeline, "datetime")
        ):
            try:
                dt = self.timeline.datetime.date(0)
            except Exception:
                dt = None
        self.strategy_logger.log(txt, dt)

    def get_next_rebalance_date(self):
        """Get next rebalancing date"""
        if self.next_rebalance_idx < len(self.rebalance_dates):
            self.next_rebalance_date = self.rebalance_dates[self.next_rebalance_idx]
        else:
            self.next_rebalance_date = None

    def next(self):
        """Main strategy logic"""
        current_date = self.timeline.datetime.date(0)

        # Process dividends for all held positions
        for data in self.datas:
            if hasattr(self, "broker") and hasattr(self, "getposition"):
                position = self.getposition(data)
            else:
                position = None
            if position is None or getattr(position, "size", 0) <= 0:
                continue
            dividend = getattr(data, "dividend", None)
            if dividend is None:
                continue
            dividend_value = dividend[0]
            if dividend_value > 0 and hasattr(self, "broker"):
                cash = position.size * dividend_value
                self.log(f"Dividend received for {data._name}: {cash:.2f}")
                self.broker.add_cash(cash)
                # Recommended default: accrue dividends as cash.
                # Reinvestment happens naturally on scheduled rebalancing.
                if hasattr(self, "order_target_percent"):
                    self.order_target_percent(target=self.p.target_percent)

        if self.next_rebalance_date and current_date >= self.next_rebalance_date:
            self.log(
                f"--- Rebalancing on {current_date} for signal date "
                f"{self.next_rebalance_date} ---"
            )

            target_tickers_df = self.p.portfolios[self.next_rebalance_date]
            target_tickers = set(target_tickers_df["Ticker"])

            self.log(
                "Diagnosis: Model selected "
                f"{len(target_tickers)} tickers: {target_tickers}"
            )

            available_data_tickers = {d._name for d in self.datas}

            final_target_tickers = target_tickers.intersection(available_data_tickers)
            missing_tickers = target_tickers - available_data_tickers

            self.log(
                "Diagnosis: "
                f"{len(available_data_tickers)} tickers have price data "
                "available in the database."
            )
            self.log(
                f"Diagnosis: Intersection has {len(final_target_tickers)} tickers: "
                f"{final_target_tickers if final_target_tickers else 'EMPTY'}"
            )

            # Record diagnostic information
            log_entry = {
                "rebalance_date": self.next_rebalance_date,
                "model_tickers": len(target_tickers),
                "available_tickers": len(final_target_tickers),
                "missing_tickers_list": ", ".join(missing_tickers),
            }
            self.rebalance_log.append(log_entry)

            if not final_target_tickers:
                self.log(
                    "CRITICAL WARNING: All-cash period. "
                    "No selected tickers were found in the price database."
                )
                if missing_tickers:
                    self.log(
                        "CRITICAL WARNING: The following "
                        f"{len(missing_tickers)} tickers were missing price data: "
                        f"{missing_tickers}"
                    )

                self.next_rebalance_idx += 1
                self.get_next_rebalance_date()
                return

            # Close positions not in target portfolio
            current_positions = {
                data._name for data in self.datas if self.getposition(data).size > 0
            }

            for ticker in current_positions:
                if ticker not in final_target_tickers:
                    data = self.getdatabyname(ticker)
                    self.log(f"Closing position in {ticker}")
                    self.order_target_percent(data=data, target=0.0)

            # Equal weight position building
            target_percent = 1.0 / len(final_target_tickers)
            for ticker in final_target_tickers:
                data = self.getdatabyname(ticker)
                self.log(
                    f"Setting target position for {ticker} to {target_percent:.2%}"
                )
                self.order_target_percent(data=data, target=target_percent)

            self.next_rebalance_idx += 1
            self.get_next_rebalance_date()
            self.log("--- Rebalancing Complete ---")

    def stop(self):
        """Processing when strategy ends"""
        self.log("--- Backtest Finished ---")
        log_df = pd.DataFrame(self.rebalance_log)
        if not log_df.empty:
            log_path = OUTPUTS_DIR / "rebalancing_diagnostics_log.csv"
            log_df.to_csv(log_path, index=False)
            self.log(f"Rebalancing diagnostics saved to: {log_path}")


class BuyAndHoldStrategy(bt.Strategy, metaclass=_SafeMetaStrategy):
    """Buy and hold strategy with dividend reinvestment into the same asset.

    - On the first bar, invest a target percentage of equity (default 99%).
    - On dividend days, book cash from dividends and maintain the target percent,
      which effectively reinvests dividends into the same asset.
    """

    params = (
        ("target_percent", 0.99),
        ("use_logging", True),
        ("logger_name", "benchmark"),
        ("log_level", None),
    )

    def __init__(self):
        self.bought = False
        # ``datas`` may be empty when instantiated outside of Cerebro (tests).
        self.timeline = self.datas[0] if getattr(self, "datas", []) else None
        self.strategy_logger = StrategyLogger(
            use_logging=self.p.use_logging,
            logger_name=self.p.logger_name,
            level=self.p.log_level,
        )

    def log(self, txt: str) -> None:
        dt = None
        if self.timeline is not None and hasattr(self.timeline, "datetime"):
            try:
                dt = self.timeline.datetime.date(0)
            except Exception:
                dt = None
        self.strategy_logger.log(txt, dt)

    def next(self):
        data = self.datas[0] if getattr(self, "datas", []) else None

        # Initial purchase
        if not self.bought:
            name = getattr(data, "_name", "asset") if data else "asset"
            self.log(f"Initial buy to target {self.p.target_percent:.2%} for {name}")
            self.order_target_percent(target=self.p.target_percent)
            self.bought = True
            return

        if data is None:
            return

        # Dividend handling: add cash, then keep target allocation to reinvest
        position = self.getposition(data) if hasattr(self, "getposition") else None
        if position is not None and getattr(position, "size", 0) > 0:
            dividend = getattr(data, "dividend", None)
            if dividend is not None:
                dividend_value = dividend[0]
                if dividend_value > 0 and hasattr(self, "broker"):
                    cash = position.size * dividend_value
                    self.log(f"Dividend received for {data._name}: {cash:.2f}")
                    self.broker.add_cash(cash)
                    # Maintain target percent to reinvest available cash
                    self.log(
                        "Reinvesting dividends to maintain target "
                        f"{self.p.target_percent:.2%}"
                    )
                    self.order_target_percent(target=self.p.target_percent)


def run_quarterly_backtest(
    portfolios: dict[datetime.date, pd.DataFrame],
    data_feeds: dict[str, bt.feeds.PandasData],
    initial_cash: float,
    start_date: datetime.date,
    end_date: datetime.date,
    use_logging: bool = True,
    add_observers: bool = False,
    add_annual_return: bool = False,
    log_level: int | None = None,
) -> tuple[pd.Series, dict[str, Any]]:
    """Run quarterly rebalancing backtest

    Args:
        portfolios: Portfolio dictionary
        data_feeds: Data feed dictionary
        initial_cash: Initial capital
        start_date: Start date
        end_date: End date
        use_logging: Whether to use logging (True) or print (False)
        add_observers: Whether to add observers
        add_annual_return: Whether to add annual return analyzer

    Returns:
        Tuple[pd.Series, Dict]: Portfolio value series and metrics dictionary
    """
    print(
        "\n--- Running Quarterly "
        f"{'AI Pick' if use_logging else 'Point-in-Time'} Strategy (Total Return) ---"
    )

    # Create Cerebro instance
    cerebro = bt.Cerebro(stdstats=not add_observers if add_observers else True)
    cerebro.broker.set_cash(initial_cash)

    # Add data feeds
    for name in sorted(data_feeds.keys()):
        cerebro.adddata(data_feeds[name], name=name)

    # Add strategy
    cerebro.addstrategy(
        PointInTimeStrategy,
        portfolios=portfolios,
        use_logging=use_logging,
        logger_name="strategy",
        log_level=log_level,
    )

    # Add analyzers
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="time_return")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")

    if add_annual_return:
        cerebro.addanalyzer(bt.analyzers.AnnualReturn, _name="annual_return")

    # Add observers (if needed)
    if add_observers:
        cerebro.addobserver(bt.observers.Broker)
        cerebro.addobserver(bt.observers.Trades)
        cerebro.addobserver(bt.observers.BuySell)

    # Run backtest
    results = cerebro.run()
    strat = results[0]

    # Extract metrics
    final_value = cerebro.broker.getvalue()
    total_return = strat.analyzers.returns.get_analysis().get("rtot", 0.0)
    max_drawdown = strat.analyzers.drawdown.get_analysis().max.drawdown

    # Calculate annualized return
    duration_in_days = (end_date - start_date).days
    annualized_return = 0.0
    if duration_in_days > 0:
        duration_in_years = duration_in_days / 365.25
        if duration_in_years > 0:
            annualized_return = ((1 + total_return) ** (1 / duration_in_years)) - 1

    # Generate portfolio value series
    tr_analyzer = strat.analyzers.getbyname("time_return")
    returns = pd.Series(tr_analyzer.get_analysis())
    cumulative_returns = (1 + returns).cumprod()
    portfolio_value = initial_cash * cumulative_returns

    # Add initial value
    first_date = returns.index.min() if not returns.empty else start_date
    start_date_ts = pd.to_datetime(first_date) - pd.Timedelta(days=1)
    portfolio_value = pd.concat(
        [pd.Series({start_date_ts: initial_cash}), portfolio_value]
    )

    # Assemble metrics dictionary
    metrics = {
        "start_date": start_date,
        "end_date": end_date,
        "initial_value": initial_cash,
        "final_value": final_value,
        "total_return": total_return,
        "annualized_return": annualized_return,
        "max_drawdown": max_drawdown,
    }

    # Add annual return analysis (if available)
    if add_annual_return:
        annual_returns = strat.analyzers.getbyname("annual_return").get_analysis()
        metrics["annual_returns"] = annual_returns

    return portfolio_value, metrics


def run_benchmark_backtest(
    data: pd.DataFrame,
    initial_cash: float,
    ticker: str = "SPY",
    *,
    target_percent: float = 0.99,
    log_level: int | None = None,
) -> tuple[pd.Series, dict[str, Any]]:
    """Run benchmark backtest (buy and hold)

    Args:
        data: Price data
        initial_cash: Initial capital
        ticker: Stock ticker

    Returns:
        Tuple[pd.Series, Dict]: Portfolio value series and metrics dictionary
    """
    print(f"\n--- Running {ticker} Buy-and-Hold Backtest (Total Return) ---")

    cerebro = bt.Cerebro()
    cerebro.broker.set_cash(initial_cash)

    # Prepare data feed with dividend line support
    bt_feed = DividendPandasData(dataname=data, openinterest=None, name=ticker)
    cerebro.adddata(bt_feed)

    cerebro.addstrategy(
        BuyAndHoldStrategy,
        target_percent=target_percent,
        use_logging=True,
        logger_name="benchmark",
        log_level=log_level,
    )

    # Add analyzers
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="time_return")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")

    results = cerebro.run()
    strat = results[0]

    # Extract metrics
    final_value = cerebro.broker.getvalue()
    total_return = strat.analyzers.returns.get_analysis().get("rtot", 0.0)
    max_drawdown = strat.analyzers.drawdown.get_analysis().max.drawdown

    start_date = data.index.min().date()
    end_date = data.index.max().date()

    # Calculate annualized return
    duration_in_days = (end_date - start_date).days
    annualized_return = 0.0
    if duration_in_days > 0:
        duration_in_years = duration_in_days / 365.25
        if duration_in_years > 0:
            annualized_return = ((1 + total_return) ** (1 / duration_in_years)) - 1

    # Generate portfolio value series
    tr_analyzer = strat.analyzers.getbyname("time_return")
    returns = pd.Series(tr_analyzer.get_analysis())
    cumulative_returns = (1 + returns).cumprod()
    portfolio_value = initial_cash * cumulative_returns
    start_date_ts = data.index.min() - pd.Timedelta(days=1)
    portfolio_value = pd.concat(
        [pd.Series({start_date_ts: initial_cash}), portfolio_value]
    )

    # Assemble metrics dictionary
    metrics = {
        "start_date": start_date,
        "end_date": end_date,
        "initial_value": initial_cash,
        "final_value": final_value,
        "total_return": total_return,
        "annualized_return": annualized_return,
        "max_drawdown": max_drawdown,
    }

    return portfolio_value, metrics


def generate_report(
    metrics: dict[str, Any],
    title: str,
    portfolio_value: pd.Series,
    output_png: Path | None = None,
    benchmark_value: pd.Series | None = None,
    benchmark_label: str = "Benchmark",
) -> None:
    """Generate unified backtest report

    Args:
        metrics: Metrics dictionary
        title: Report title
        portfolio_value: Portfolio value series
        output_png: Output image path (optional)
        benchmark_value: Benchmark value series (optional)
        benchmark_label: Benchmark label
    """
    # Print text report
    print("\n" + "=" * 50)
    print(f"{title:^50}")
    print("=" * 50)
    print(
        "Time Period Covered:     "
        f"{metrics['start_date'].strftime('%Y-%m-%d')} "
        f"to {metrics['end_date'].strftime('%Y-%m-%d')}"
    )
    print(f"Initial Portfolio Value: ${metrics['initial_value']:,.2f}")
    print(f"Final Portfolio Value:   ${metrics['final_value']:,.2f}")
    print("-" * 50)
    print(f"Total Return:            {metrics['total_return'] * 100:.2f}%")
    print(f"Annualized Return:       {metrics['annualized_return'] * 100:.2f}%")
    print(f"Max Drawdown:            {metrics['max_drawdown']:.2f}%")
    print("=" * 50)

    # Generate chart
    print("\nGenerating plot...")
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(14, 8))

    # Plot main strategy
    portfolio_value.plot(
        ax=ax, label=title.split("(")[0].strip(), color="steelblue", lw=2
    )

    # Plot benchmark (if provided)
    if benchmark_value is not None:
        benchmark_value.plot(ax=ax, label=benchmark_label, color="darkorange", lw=2)

    # Format chart
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f"${x:,.0f}"))
    ax.set_title(title, fontsize=16)
    ax.set_xlabel("Date", fontsize=12)
    ax.set_ylabel("Portfolio Value ($)", fontsize=12)
    ax.legend(fontsize=12)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()

    # Save image
    if output_png:
        plt.savefig(output_png, dpi=300, bbox_inches="tight")
        print(f"Plot saved to: {output_png}")

    plt.show()
