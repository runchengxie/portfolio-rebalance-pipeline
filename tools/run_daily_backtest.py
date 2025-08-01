import datetime
import logging
import sqlite3
import sys
import time
from pathlib import Path

import backtrader as bt
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd

# --- 路径配置 ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

PORTFOLIO_FILE = OUTPUTS_DIR / "point_in_time_backtest_dynamic.xlsx"

# --- 数据库配置 ---
DB_PATH = DATA_DIR / "financial_data.db"

INITIAL_CASH = 1_000_000.0


# --- Backtrader 策略 ---
class PointInTimeStrategy(bt.Strategy):
    params = (("portfolios", None),)

    def __init__(self):
        self.rebalance_dates = sorted(self.p.portfolios.keys())
        self.next_rebalance_idx = 0
        self.get_next_rebalance_date()
        # 使用第一个数据源作为统一的时间线基准
        self.timeline = self.datas[0]

    def log(self, txt, dt=None):
        dt = dt or self.timeline.datetime.date(0)
        # 现在 log 方法会通过 print 被日志系统捕获
        print(f"{dt.isoformat()} - {txt}")

    def get_next_rebalance_date(self):
        if self.next_rebalance_idx < len(self.rebalance_dates):
            self.next_rebalance_date = self.rebalance_dates[self.next_rebalance_idx]
        else:
            self.next_rebalance_date = None

    def next(self):
        current_date = self.timeline.datetime.date(0)

        # 只有当模拟的当前日期达到或超过下一个调仓日期时，才执行调仓
        if self.next_rebalance_date and current_date >= self.next_rebalance_date:
            self.log(
                f"--- Rebalancing on {current_date} for signal date {self.next_rebalance_date} ---"
            )
            target_tickers_df = self.p.portfolios[self.next_rebalance_date]
            target_tickers = set(target_tickers_df["Ticker"])
            available_data_tickers = {d._name for d in self.datas}
            final_target_tickers = target_tickers.intersection(available_data_tickers)

            if not final_target_tickers:
                self.log(
                    "Warning: No target tickers are available in the price data for this period."
                )
                self.next_rebalance_idx += 1
                self.get_next_rebalance_date()
                return

            current_positions = {
                data._name for data in self.datas if self.getposition(data).size > 0
            }

            # Sell stocks no longer in the target portfolio
            for ticker in current_positions:
                if ticker not in final_target_tickers:
                    data = self.getdatabyname(ticker)
                    self.log(f"Closing position in {ticker}")
                    self.order_target_percent(data=data, target=0.0)

            # Buy stocks in the target portfolio
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


# --- 辅助函数 ---
def tidy_ticker(col: pd.Series) -> pd.Series:
    return (
        col.astype("string")
        .str.upper()
        .str.strip()
        .str.replace(r"_DELISTED$", "", regex=True)
        .replace({"": pd.NA})
    )


def load_portfolios(portfolio_path: Path) -> dict:
    if not portfolio_path.exists():
        raise FileNotFoundError(f"Portfolio file not found: {portfolio_path}")
    xls = pd.read_excel(portfolio_path, sheet_name=None, engine="openpyxl")
    portfolios = {pd.to_datetime(date_str).date(): df for date_str, df in xls.items()}
    return {
        k: v for k, v in portfolios.items() if not v.empty and "Ticker" in v.columns
    }


def load_all_price_data_from_db(
    db_path: Path,
    all_needed_tickers: set,
    start_date: datetime.date,
    end_date: datetime.date,
) -> dict:
    """
    从SQLite数据库加载并准备所有价格数据，将所有股票对齐到统一的主时间线。
    """
    print(f"Loading and preparing all price data from {start_date} to {end_date}...")

    if not db_path.exists():
        print(f"[ERROR] 数据库文件不存在: {db_path}", file=sys.stderr)
        print("[ERROR] 请先运行 'tools/load_data_to_db.py' 创建数据库", file=sys.stderr)
        sys.exit(1)

    con = sqlite3.connect(db_path)

    try:
        date_query = """
        SELECT DISTINCT Date 
        FROM share_prices 
        WHERE Date >= ? AND Date <= ?
        ORDER BY Date
        """
        master_dates_df = pd.read_sql_query(
            date_query,
            con,
            params=[start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")],
            parse_dates=["Date"],
        )
        if master_dates_df.empty:
            raise ValueError(
                "No trading days found in the database for the specified date range."
            )

        master_index = pd.to_datetime(master_dates_df["Date"])
        print(f"Master timeline created with {len(master_index)} trading days.")

        tickers_list = list(all_needed_tickers)
        placeholders = ",".join(["?" for _ in tickers_list])

        bulk_query = f"""
        SELECT Date, Ticker, Open, High, Low, Close, Volume, Dividend
        FROM share_prices 
        WHERE Ticker IN ({placeholders}) AND Date >= ? AND Date <= ?
        ORDER BY Ticker, Date
        """

        params = tickers_list + [
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d"),
        ]

        all_data = pd.read_sql_query(
            bulk_query, con, params=params, parse_dates=["Date"]
        )

        data_feeds = {}
        for ticker, group in all_data.groupby("Ticker"):
            group = group.set_index("Date")
            aligned_df = group.reindex(master_index).ffill()
            aligned_df.loc[
                :, ["Open", "High", "Low", "Close", "Volume", "Dividend"]
            ] = aligned_df.loc[
                :, ["Open", "High", "Low", "Close", "Volume", "Dividend"]
            ].ffill()
            aligned_df.loc[:, "Volume"] = aligned_df["Volume"].fillna(0)
            aligned_df.loc[:, "Dividend"] = aligned_df["Dividend"].fillna(0)

            if not aligned_df.empty and not aligned_df["Close"].isnull().all():
                data_feeds[ticker] = bt.feeds.PandasData(
                    dataname=aligned_df, name=ticker
                )

        print(f"Loaded data for {len(data_feeds)} tickers.")
        return data_feeds

    finally:
        con.close()


def setup_logging():
    log_file = OUTPUTS_DIR / "backtest_log.txt"
    if log_file.exists():
        log_file.unlink()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(message)s",
        handlers=[logging.FileHandler(log_file), logging.StreamHandler(sys.stdout)],
    )
    print(f"日志将记录到: {log_file}")


def run_backtest(
    data_feeds: dict,
    portfolios: dict,
    initial_cash: float,
    start_date: datetime.date,
    end_date: datetime.date,
):
    """
    运行主要的回测策略，并在最后打印包含时间段的总结报告，并生成业绩图表。
    """
    print("\n--- Running Point-in-Time Strategy (Total Return) ---")
    cerebro = bt.Cerebro()
    cerebro.broker.set_cash(initial_cash)

    for name in sorted(data_feeds.keys()):
        cerebro.adddata(data_feeds[name], name=name)

    cerebro.addstrategy(PointInTimeStrategy, portfolios=portfolios)

    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="time_return")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")

    results = cerebro.run()
    strat = results[0]

    print("\nCalculating performance metrics from TimeReturn analyzer...")
    tr_analyzer = strat.analyzers.getbyname("time_return")
    returns = pd.Series(tr_analyzer.get_analysis()).sort_index()

    cumulative_returns = (1 + returns).cumprod()

    if not cumulative_returns.empty:
        total_return = cumulative_returns.iloc[-1] - 1
        final_value = initial_cash * cumulative_returns.iloc[-1]
    else:
        total_return = 0.0
        final_value = initial_cash

    max_drawdown = strat.analyzers.drawdown.get_analysis().max.drawdown

    duration_in_days = (end_date - start_date).days
    annualized_return = 0.0
    if duration_in_days > 0:
        duration_in_years = duration_in_days / 365.25
        if duration_in_years > 0 and (1 + total_return) > 0:
            annualized_return = ((1 + total_return) ** (1 / duration_in_years)) - 1

    print("\n" + "=" * 50)
    print(f"{'Backtest Results (Total Return)':^50}")
    print("=" * 50)
    # 报告的起始日期现在是真正的回测开始日期
    print(
        f"Time Period Covered:     {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
    )
    print(f"Initial Portfolio Value: ${initial_cash:,.2f}")
    print(f"Final Portfolio Value:   ${final_value:,.2f}")
    print("-" * 50)
    print(f"Total Return:            {total_return * 100:.2f}%")
    print(f"Annualized Return:       {annualized_return * 100:.2f}%")
    print(f"Max Drawdown:            {max_drawdown:.2f}%")
    print("=" * 50)

    print("\nGenerating performance chart...")
    if not cumulative_returns.empty:
        portfolio_value = initial_cash * cumulative_returns
        # 这里的 start_date 现在是更早的 BACKTEST_START，图表起点正确
        start_date_ts = pd.Timestamp(start_date) - pd.Timedelta(days=1)
        portfolio_value = pd.concat(
            [pd.Series({start_date_ts: initial_cash}), portfolio_value]
        )
    else:
        portfolio_value = pd.Series(
            {
                pd.Timestamp(start_date): initial_cash,
                pd.Timestamp(end_date): initial_cash,
            }
        )

    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(14, 8))

    portfolio_value.plot(
        ax=ax, label="Multi-Factor Strategy (Total Return)", color="royalblue", lw=2
    )

    ax.set_title(
        f"Strategy Backtest Performance ({start_date.year} - {end_date.year})",
        fontsize=16,
    )
    ax.set_xlabel("Date", fontsize=12)
    ax.set_ylabel("Portfolio Value ($)", fontsize=12)
    ax.legend(fontsize=12)

    formatter = mticker.FuncFormatter(lambda x, p: f"${x:,.0f}")
    ax.yaxis.set_major_formatter(formatter)

    plt.tight_layout()

    output_path = OUTPUTS_DIR / "strategy_cumulative_returns.png"
    plt.savefig(output_path, dpi=300)

    print(f"Chart saved successfully to: {output_path}")


def main():
    """
    主函数，用于运行回测。
    """
    print("--- Running Backtest with Backtrader (Database Mode, Portfolio-Only) ---")

    try:
        portfolios = load_portfolios(PORTFOLIO_FILE)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    if not portfolios:
        print("[INFO] No portfolios found. Exiting.")
        return

    print(f"✓ Loaded {len(portfolios)} portfolio snapshots.")

    all_needed_tickers = set()
    for df in portfolios.values():
        all_needed_tickers.update(tidy_ticker(df["Ticker"]).dropna())

    # --- MODIFICATION START: 显式分离回测期与信号期 ---
    # 1. 定义一个固定的、更早的回测开始日期
    BACKTEST_START_DATE = datetime.date(2020, 12, 31)

    # 2. 信号的日期范围保持不变，用于确定需要哪些股票代码
    first_signal_date = min(portfolios.keys())

    # 3. 回测结束日期固定为 2025-06-30
    BACKTEST_END_DATE = datetime.date(2025, 6, 30)

    print(f"Backtest observation period: {BACKTEST_START_DATE} to {BACKTEST_END_DATE}")
    print(f"First trading signal expected around: {first_signal_date}")
    # --- MODIFICATION END ---

    print(f"Calculating for a total of {len(all_needed_tickers)} unique tickers...")

    start_time = time.time()
    # 使用定义好的回测起止日期来加载数据
    price_data_dict = load_all_price_data_from_db(
        DB_PATH,
        all_needed_tickers,
        start_date=BACKTEST_START_DATE,
        end_date=BACKTEST_END_DATE,
    )
    load_time = time.time() - start_time
    print(f"\n[PERFORMANCE] 数据加载耗时: {load_time:.2f}秒")

    if not price_data_dict:
        print("[ERROR] Price data could not be loaded. Exiting.", file=sys.stderr)
        sys.exit(1)

    # --- 【代码修改点】 ---
    # 删除了原来动态获取 actual_end_date 的逻辑。
    # 直接使用我们预设的固定回测结束日期。
    #
    # BEFORE:
    # all_dates = []
    # for data_feed in price_data_dict.values():
    #     if not data_feed.p.dataname.empty:
    #         all_dates.append(data_feed.p.dataname.index[-1])
    # actual_end_date = max(all_dates).date() if all_dates else BACKTEST_END_DATE
    #
    # AFTER:
    actual_end_date = BACKTEST_END_DATE
    # --- 【修改结束】 ---

    # 运行回测，传入完整的观察期
    run_backtest(
        data_feeds=price_data_dict,
        portfolios=portfolios,
        initial_cash=INITIAL_CASH,
        start_date=BACKTEST_START_DATE,
        end_date=actual_end_date,
    )


if __name__ == "__main__":
    setup_logging()
    main()
