import sys
import time
import datetime

from .backtest.engine import (
    generate_report,
    run_quarterly_backtest,
    run_benchmark_backtest,
)
from .backtest.prep import (
    load_portfolios,
    load_price_feeds,
    load_spy_data,
)
from .utils.config import get_backtest_period, get_initial_cash
from .utils.paths import (
    DB_PATH,
    OUTPUTS_DIR,
    QUANT_PORTFOLIO_FILE,
    QUANT_PORTFOLIO_JSON_DIR,
)

# Strategy classes and helper functions have been moved to backtest.engine and backtest.prep modules


def main(*, log_level: int | None = None):
    """Main function - Run unselected quarterly backtest

    Args:
        log_level: Optional logging level for strategy logs
    """
    print("--- Running Quarterly Point-in-Time Backtest (Database Mode) ---")

    try:
        # Prefer JSON directory if present, otherwise fall back to Excel workbook
        portfolio_path = (
            QUANT_PORTFOLIO_JSON_DIR
            if QUANT_PORTFOLIO_JSON_DIR.exists()
            else QUANT_PORTFOLIO_FILE
        )

        # Load portfolio data (unselected version)
        portfolios = load_portfolios(portfolio_path, is_ai_selection=False)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    if not portfolios:
        print("[INFO] No portfolios found. Exiting.")
        return

    print(f"✓ Loaded {len(portfolios)} portfolio snapshots.")

    # Collect all needed ticker symbols
    all_needed_tickers = set()
    for df in portfolios.values():
        all_needed_tickers.update(df["Ticker"].dropna())

    # Get unified backtest time range from config file
    BACKTEST_START_DATE, BACKTEST_END_DATE = get_backtest_period(portfolios)

    # Get initial cash from config file
    initial_cash = get_initial_cash("quant")

    print(f"Backtest period: {BACKTEST_START_DATE} to {BACKTEST_END_DATE}")
    print(f"Initial cash: ${initial_cash:,.2f}")
    print(f"Calculating for a total of {len(all_needed_tickers)} unique tickers...")

    # Load price data
    start_time = time.time()
    try:
        price_data_dict = load_price_feeds(
            DB_PATH,
            all_needed_tickers,
            start_date=BACKTEST_START_DATE,
            end_date=BACKTEST_END_DATE,
        )
        load_time = time.time() - start_time
        print(f"\n[PERFORMANCE] Data loading time: {load_time:.2f} seconds")
    except Exception as e:
        print(f"[ERROR] Price data could not be loaded: {e}", file=sys.stderr)
        sys.exit(1)

    if not price_data_dict:
        print("[ERROR] No price data available. Exiting.", file=sys.stderr)
        sys.exit(1)

    # Run backtest
    portfolio_value, metrics = run_quarterly_backtest(
        portfolios=portfolios,
        data_feeds=price_data_dict,
        initial_cash=initial_cash,
        start_date=BACKTEST_START_DATE,
        end_date=BACKTEST_END_DATE,
        use_logging=False,  # Unselected version uses print
        add_observers=False,  # Unselected version does not add observers
        add_annual_return=False,  # Unselected version does not add annual return analyzer
        log_level=log_level,
    )

    # Prepare SPY benchmark
    spy_value = None
    try:
        start_dt = datetime.datetime.combine(BACKTEST_START_DATE, datetime.time())
        end_dt = datetime.datetime.combine(BACKTEST_END_DATE, datetime.time())
        spy_data = load_spy_data(DB_PATH, start_dt, end_dt)
        spy_value, _ = run_benchmark_backtest(
            data=spy_data,
            initial_cash=initial_cash,
            ticker="SPY",
            log_level=log_level,
        )
    except Exception as e:
        print(f"[WARN] SPY benchmark skipped: {e}")

    # Generate report
    output_png = OUTPUTS_DIR / "quarterly_strategy_returns.png"
    generate_report(
        metrics=metrics,
        title="Quarterly Point-in-Time Strategy Backtest Results",
        portfolio_value=portfolio_value,
        output_png=output_png,
        benchmark_value=spy_value,
        benchmark_label="SPY",
    )


if __name__ == "__main__":
    main()
