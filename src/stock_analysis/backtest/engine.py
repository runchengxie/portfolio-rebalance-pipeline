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

from ..logging import StrategyLogger
from ..services.marketdata import RiskFreeRateService
from ..utils.paths import OUTPUTS_DIR
from .prep import DividendPandasData


_RISK_FREE_SERVICE: RiskFreeRateService | None = None


def _get_risk_free_service() -> RiskFreeRateService:
    """Return a lazily-initialised risk-free rate service."""

    global _RISK_FREE_SERVICE
    if _RISK_FREE_SERVICE is None:
        _RISK_FREE_SERVICE = RiskFreeRateService.from_app_config()
    return _RISK_FREE_SERVICE


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
                # Recommended default: accrue dividends as cash. Reinvestment
                # happens naturally during the next scheduled rebalancing for
                # this strategy (equal-weight allocation). Do not attempt to
                # maintain a global target percent here, because this strategy
                # has no such parameter and calling ``order_target_percent``
                # without a specific data target can raise errors.

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
    if not returns.empty:
        returns.index = pd.to_datetime(returns.index)
        returns = returns.sort_index()
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

    sharpe_ratio = None
    if not returns.empty:
        try:
            rf_service = _get_risk_free_service()
            sharpe_ratio = rf_service.compute_sharpe(returns)
            metrics["risk_free_series"] = rf_service.default_series
        except Exception as exc:  # pragma: no cover - defensive guard
            print(f"[WARN] Unable to compute Sharpe ratio: {exc}")
    if sharpe_ratio is not None:
        metrics["sharpe"] = sharpe_ratio

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
    if not returns.empty:
        returns.index = pd.to_datetime(returns.index)
        returns = returns.sort_index()
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

    sharpe_ratio = None
    if not returns.empty:
        try:
            rf_service = _get_risk_free_service()
            sharpe_ratio = rf_service.compute_sharpe(returns)
            metrics["risk_free_series"] = rf_service.default_series
        except Exception as exc:  # pragma: no cover - defensive guard
            print(f"[WARN] Unable to compute Sharpe ratio: {exc}")
    if sharpe_ratio is not None:
        metrics["sharpe"] = sharpe_ratio

    return portfolio_value, metrics


def _index_to_100(series: pd.Series) -> pd.Series:
    """Rebase a time series to start at 100 while dropping missing values."""

    cleaned = series.dropna()
    if cleaned.empty:
        return cleaned
    return 100.0 * cleaned / cleaned.iloc[0]


def _underwater(series: pd.Series) -> pd.Series:
    """Compute drawdown series expressed as negative percentages."""

    cleaned = series.dropna()
    if cleaned.empty:
        return cleaned
    rolling_max = cleaned.cummax()
    return cleaned / rolling_max - 1.0


def generate_report(
    metrics: dict[str, Any],
    title: str,
    portfolio_value: pd.Series,
    output_png: Path | None = None,
    benchmark_value: pd.Series | None = None,
    benchmark_label: str = "Benchmark",
    benchmark_metrics: dict[str, Any] | None = None,
    *,
    report_mode: str = "comparison_only",
    with_underwater: bool = True,
    index_to_100: bool = True,
    use_log_scale: bool = False,
) -> None:
    """Generate unified backtest report

    Args:
        metrics: Metrics dictionary
        title: Report title
        portfolio_value: Portfolio value series
        output_png: Output image path (optional)
        benchmark_value: Benchmark value series (optional)
        benchmark_label: Benchmark label
        benchmark_metrics: Optional metrics dictionary for benchmark comparison
        report_mode: Controls textual output. Options are "comparison_only",
            "strategy_only", or "both".
        with_underwater: Include an underwater (drawdown) subplot when True.
        index_to_100: Rebase values to 100 before plotting when True.
        use_log_scale: Display the equity curve on a log scale when True.
    """

    valid_modes = {"comparison_only", "strategy_only", "both"}
    if report_mode not in valid_modes:  # pragma: no cover - defensive guard
        raise ValueError(
            "report_mode must be one of 'comparison_only', 'strategy_only', 'both'"
        )

    def _render_metrics_block(block_title: str, block_metrics: dict[str, Any]) -> None:
        print("\n" + "=" * 50)
        print(f"{block_title:^50}")
        print("=" * 50)
        print(
            "Time Period Covered:     "
            f"{block_metrics['start_date'].strftime('%Y-%m-%d')} "
            f"to {block_metrics['end_date'].strftime('%Y-%m-%d')}"
        )
        print(f"Initial Portfolio Value: ${block_metrics['initial_value']:,.2f}")
        print(f"Final Portfolio Value:   ${block_metrics['final_value']:,.2f}")
        print("-" * 50)
        print(f"Total Return:            {block_metrics['total_return'] * 100:.2f}%")
        print(
            "Annualized Return:       "
            f"{block_metrics['annualized_return'] * 100:.2f}%"
        )
        print(f"Max Drawdown:            {block_metrics['max_drawdown']:.2f}%")
        if block_metrics.get("sharpe") is not None:
            print(f"Sharpe Ratio:           {block_metrics['sharpe']:.3f}")
            rf_series = block_metrics.get("risk_free_series")
            if rf_series:
                print(f"Risk-free Series:       {rf_series}")
        print("=" * 50)

    def _format_percent(value: float | None) -> str:
        if value is None:
            return "N/A"
        return f"{value * 100:.2f}%"

    def _format_drawdown(value: float | None) -> str:
        if value is None:
            return "N/A"
        return f"{value:.2f}%"

    def _format_sharpe(value: float | None) -> str:
        if value is None:
            return "N/A"
        return f"{value:.3f}"

    if report_mode in {"strategy_only", "both"}:
        _render_metrics_block(title, metrics)

    benchmark_section_title = f"{benchmark_label} Benchmark Results"
    if benchmark_metrics is not None and report_mode == "both":
        _render_metrics_block(benchmark_section_title, benchmark_metrics)

    if benchmark_metrics is not None:
        strategy_label = title.replace("Results", "").strip() or "Strategy"
        benchmark_column_label = benchmark_label or "Benchmark"
        column_width = max(len(strategy_label), len(benchmark_column_label), 20)

        print("\nBenchmark Comparison (Unified Methodology):")
        header = (
            f"{'Metric':<20}{strategy_label:<{column_width}}"
            f"{benchmark_column_label:<{column_width}}"
        )
        print(header)
        print("-" * len(header))

        comparison_rows = [
            (
                "Total Return",
                _format_percent(metrics.get("total_return")),
                _format_percent(benchmark_metrics.get("total_return")),
            ),
            (
                "Annualized Return",
                _format_percent(metrics.get("annualized_return")),
                _format_percent(benchmark_metrics.get("annualized_return")),
            ),
            (
                "Max Drawdown",
                _format_drawdown(metrics.get("max_drawdown")),
                _format_drawdown(benchmark_metrics.get("max_drawdown")),
            ),
            (
                "Sharpe Ratio",
                _format_sharpe(metrics.get("sharpe")),
                _format_sharpe(benchmark_metrics.get("sharpe")),
            ),
        ]

        for metric_name, strategy_value, benchmark_value_str in comparison_rows:
            print(
                f"{metric_name:<20}{strategy_value:<{column_width}}"
                f"{benchmark_value_str:<{column_width}}"
            )

        print("-" * len(header))
        strategy_period = (
            f"{metrics['start_date'].strftime('%Y-%m-%d')}"
            f" to {metrics['end_date'].strftime('%Y-%m-%d')}"
        )
        benchmark_period = (
            f"{benchmark_metrics['start_date'].strftime('%Y-%m-%d')}"
            f" to {benchmark_metrics['end_date'].strftime('%Y-%m-%d')}"
        )
        print(f"Period Covered:{strategy_period:>18} | {benchmark_period}")
        print(
            "Initial / Final:"  # Align initial and final values for both series
            f" ${metrics['initial_value']:,.2f} → ${metrics['final_value']:,.2f}"
            f" | ${benchmark_metrics['initial_value']:,.2f}"
            f" → ${benchmark_metrics['final_value']:,.2f}"
        )
        rf_series = metrics.get("risk_free_series") or benchmark_metrics.get(
            "risk_free_series"
        )
        if rf_series:
            print(f"Risk-free Series: {rf_series}")

    # Harmonise data prior to plotting
    portfolio_series = portfolio_value.sort_index()
    benchmark_series = (
        benchmark_value.sort_index() if benchmark_value is not None else None
    )

    if benchmark_series is not None:
        aligned = pd.concat(
            [
                portfolio_series.rename("Strategy"),
                benchmark_series.rename(benchmark_label or "Benchmark"),
            ],
            axis=1,
        ).sort_index()
        aligned = aligned.ffill().dropna()
        if aligned.empty:
            benchmark_series = None
        else:
            portfolio_series = aligned.iloc[:, 0]
            benchmark_series = aligned.iloc[:, 1]

    if index_to_100:
        portfolio_plot = _index_to_100(portfolio_series)
        benchmark_plot = (
            _index_to_100(benchmark_series) if benchmark_series is not None else None
        )
        y_label = "Index (Base = 100)"
    else:
        portfolio_plot = portfolio_series
        benchmark_plot = benchmark_series
        y_label = "Portfolio Value ($)"

    # Generate chart
    print("\nGenerating plot...")
    plt.style.use("seaborn-v0_8-whitegrid")
    nrows = 2 if with_underwater else 1
    fig, axes = plt.subplots(nrows=nrows, ncols=1, figsize=(14, 8), sharex=True)
    if with_underwater:
        ax_equity, ax_drawdown = axes  # type: ignore[misc]
    else:
        ax_equity = axes  # type: ignore[assignment]

    portfolio_label = title.split("(")[0].strip() or "Strategy"
    portfolio_plot.plot(ax=ax_equity, label=portfolio_label, lw=2, color="steelblue")

    if benchmark_plot is not None:
        benchmark_plot.plot(
            ax=ax_equity, label=benchmark_label or "Benchmark", lw=2, color="darkorange"
        )

    ax_equity.set_title(title, fontsize=16)
    ax_equity.set_ylabel(y_label, fontsize=12)
    ax_equity.legend(fontsize=12)
    if not index_to_100:
        ax_equity.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda value, _: f"${value:,.0f}")
        )
    if use_log_scale:
        ax_equity.set_yscale("log")

    if with_underwater:
        drawdown_series = _underwater(portfolio_series)
        if not drawdown_series.empty:
            ax_drawdown.plot(drawdown_series.index, drawdown_series, lw=1.2, color="steelblue")
            ax_drawdown.fill_between(
                drawdown_series.index,
                drawdown_series,
                0,
                color="steelblue",
                alpha=0.25,
                step="pre",
            )
        ax_drawdown.set_ylabel("Drawdown", fontsize=12)
        ax_drawdown.set_xlabel("Date", fontsize=12)
        ax_drawdown.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1.0))
        ax_drawdown.grid(True, alpha=0.3)
    else:
        ax_equity.set_xlabel("Date", fontsize=12)

    ax_equity.grid(True, alpha=0.3)
    plt.tight_layout()

    if output_png:
        plt.savefig(output_png, dpi=300, bbox_inches="tight")
        print(f"Plot saved to: {output_png}")

    plt.show()
