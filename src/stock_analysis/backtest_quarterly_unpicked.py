import datetime
import sys
import time
from pathlib import Path

import pandas as pd
from dateutil.relativedelta import relativedelta

# 导入新的模块
from .backtest.engine import run_quarterly_backtest, generate_report
from .backtest.prep import load_portfolios, load_price_feeds
from .utils.paths import (
    QUANT_PORTFOLIO_FILE as PORTFOLIO_FILE,
    DB_PATH,
    DEFAULT_INITIAL_CASH as INITIAL_CASH,
    OUTPUTS_DIR
)


# 策略类和辅助函数已移至 backtest.engine 和 backtest.prep 模块


def main():
    """主函数 - 运行未精选季度回测"""
    print("--- Running Quarterly Point-in-Time Backtest (Database Mode) ---")

    try:
        # 加载投资组合数据（未精选版本）
        portfolios = load_portfolios(PORTFOLIO_FILE, is_ai_selection=False)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    if not portfolios:
        print("[INFO] No portfolios found. Exiting.")
        return

    print(f"✓ Loaded {len(portfolios)} portfolio snapshots.")

    # 收集所有需要的股票代码
    all_needed_tickers = set()
    for df in portfolios.values():
        all_needed_tickers.update(df["Ticker"].dropna())

    # 动态确定回测时间范围
    first_rebalance_date = min(portfolios.keys())
    last_rebalance_date = max(portfolios.keys())
    
    BACKTEST_START_DATE = first_rebalance_date
    BACKTEST_END_DATE = last_rebalance_date + relativedelta(months=3, days=10)

    print("Dynamically set backtest period based on portfolio dates:")
    print(f"  - First signal date: {first_rebalance_date}")
    print(f"  - Data loading will start from: {BACKTEST_START_DATE}")
    print(f"  - Data loading will end around: {BACKTEST_END_DATE}")
    print(f"Calculating for a total of {len(all_needed_tickers)} unique tickers...")

    # 加载价格数据
    start_time = time.time()
    try:
        price_data_dict = load_price_feeds(
            DB_PATH,
            all_needed_tickers,
            start_date=BACKTEST_START_DATE,
            end_date=BACKTEST_END_DATE,
        )
        load_time = time.time() - start_time
        print(f"\n[PERFORMANCE] 数据加载耗时: {load_time:.2f}秒")
    except Exception as e:
        print(f"[ERROR] Price data could not be loaded: {e}", file=sys.stderr)
        sys.exit(1)

    if not price_data_dict:
        print("[ERROR] No price data available. Exiting.", file=sys.stderr)
        sys.exit(1)

    # 运行回测
    portfolio_value, metrics = run_quarterly_backtest(
        portfolios=portfolios,
        data_feeds=price_data_dict,
        initial_cash=INITIAL_CASH,
        start_date=BACKTEST_START_DATE,
        end_date=BACKTEST_END_DATE,
        use_logging=False,  # 未精选版本使用print
        add_observers=False,  # 未精选版本不添加观察器
        add_annual_return=False  # 未精选版本不添加年化收益分析器
    )

    # 生成报告
    output_png = OUTPUTS_DIR / "quarterly_strategy_returns.png"
    generate_report(
        metrics=metrics,
        title="Quarterly Point-in-Time Strategy Backtest Results",
        portfolio_value=portfolio_value,
        output_png=output_png
    )


if __name__ == "__main__":
    main()
