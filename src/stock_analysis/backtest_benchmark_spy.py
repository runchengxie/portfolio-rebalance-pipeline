import datetime
from pathlib import Path

# 导入新的模块
from .backtest.engine import run_benchmark_backtest, generate_report
from .backtest.prep import load_spy_data
from .utils.paths import DB_PATH, SPY_INITIAL_CASH as INITIAL_CASH, OUTPUTS_DIR

# --- 回测配置 ---
SPY_TICKER = "SPY"
START_DATE = datetime.datetime(2021, 4, 2)
END_DATE = datetime.datetime(2025, 7, 2)


# 数据加载函数和策略类已移至相应模块


def main():
    """主执行函数 - 运行SPY基准回测"""
    print("--- SPY Benchmark Backtest ---")

    try:
        # 加载SPY数据
        spy_data = load_spy_data(DB_PATH, START_DATE, END_DATE, SPY_TICKER)
    except (FileNotFoundError, ValueError) as e:
        print(f"[ERROR] Failed to load data: {e}")
        return

    # 运行基准回测
    portfolio_value, metrics = run_benchmark_backtest(
        data=spy_data,
        initial_cash=INITIAL_CASH,
        ticker=SPY_TICKER
    )

    # 生成报告
    output_png = OUTPUTS_DIR / "spy_benchmark_returns.png"
    generate_report(
        metrics=metrics,
        title="SPY Benchmark Results (Total Return)",
        portfolio_value=portfolio_value,
        output_png=output_png
    )


if __name__ == "__main__":
    main()
