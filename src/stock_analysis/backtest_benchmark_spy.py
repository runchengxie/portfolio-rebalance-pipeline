import datetime

from .backtest.engine import generate_report, run_benchmark_backtest
from .backtest.prep import load_spy_data
from .utils.config import get_backtest_period, get_initial_cash
from .utils.paths import DB_PATH, OUTPUTS_DIR

# --- Backtest Configuration ---
SPY_TICKER = "SPY"


# Data loading functions and strategy classes have been moved to respective modules


def main():
    """Main execution function - Run SPY benchmark backtest"""
    print("--- SPY Benchmark Backtest ---")

    # Get unified time period from configuration file
    start_date, end_date = get_backtest_period()
    start_datetime = datetime.datetime.combine(start_date, datetime.time())
    end_datetime = datetime.datetime.combine(end_date, datetime.time())

    # Get initial cash from configuration file
    initial_cash = get_initial_cash("spy")

    print(f"Backtest period: {start_date} to {end_date}")
    print(f"Initial cash: ${initial_cash:,.2f}")

    try:
        # Load SPY data
        spy_data = load_spy_data(DB_PATH, start_datetime, end_datetime, SPY_TICKER)
    except (FileNotFoundError, ValueError) as e:
        print(f"[ERROR] Failed to load data: {e}")
        return

    # Run benchmark backtest
    portfolio_value, metrics = run_benchmark_backtest(
        data=spy_data, initial_cash=initial_cash, ticker=SPY_TICKER
    )

    # Generate report
    output_png = OUTPUTS_DIR / "spy_benchmark_returns.png"
    generate_report(
        metrics=metrics,
        title="SPY Benchmark Results (Total Return)",
        portfolio_value=portfolio_value,
        output_png=output_png,
    )


if __name__ == "__main__":
    main()
