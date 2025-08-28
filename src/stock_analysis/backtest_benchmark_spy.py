import datetime

from .backtest.engine import generate_report, run_benchmark_backtest
from .backtest.prep import load_spy_data
from .utils.config import get_backtest_period, get_initial_cash
from .utils.paths import DB_PATH, OUTPUTS_DIR

# --- 回测配置 ---
SPY_TICKER = "SPY"


# 数据加载函数和策略类已移至相应模块


def main():
    """主执行函数 - 运行SPY基准回测"""
    print("--- SPY Benchmark Backtest ---")

    # 从配置文件获取统一的时间区间
    start_date, end_date = get_backtest_period()
    start_datetime = datetime.datetime.combine(start_date, datetime.time())
    end_datetime = datetime.datetime.combine(end_date, datetime.time())

    # 从配置文件获取初始资金
    initial_cash = get_initial_cash("spy")

    print(f"Backtest period: {start_date} to {end_date}")
    print(f"Initial cash: ${initial_cash:,.2f}")

    try:
        # 加载SPY数据
        spy_data = load_spy_data(DB_PATH, start_datetime, end_datetime, SPY_TICKER)
    except (FileNotFoundError, ValueError) as e:
        print(f"[ERROR] Failed to load data: {e}")
        return

    # 运行基准回测
    portfolio_value, metrics = run_benchmark_backtest(
        data=spy_data, initial_cash=initial_cash, ticker=SPY_TICKER
    )

    # 生成报告
    output_png = OUTPUTS_DIR / "spy_benchmark_returns.png"
    generate_report(
        metrics=metrics,
        title="SPY Benchmark Results (Total Return)",
        portfolio_value=portfolio_value,
        output_png=output_png,
    )


if __name__ == "__main__":
    main()
