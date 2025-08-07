# filename: src/stock_analysis/run_backtest_quarterly_ai_pick.py

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
from dateutil.relativedelta import relativedelta

# --- 路径配置 ---
# 【关键】: 这部分代码根据脚本的当前位置动态计算项目根目录。
# 只要您的目录结构是 'your_project_folder/src/stock_analysis'，这段代码就能正确工作。
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# 指向季度的选股结果文件
PORTFOLIO_FILE = OUTPUTS_DIR / "point_in_time_ai_stock_picks_all_sheets.xlsx"

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
        self.timeline = self.datas[0]
        self.rebalance_log = []

    def log(self, txt, dt=None):
        dt = dt or self.timeline.datetime.date(0)
        logging.info(f"{dt.isoformat()} - {txt}")

    def get_next_rebalance_date(self):
        if self.next_rebalance_idx < len(self.rebalance_dates):
            self.next_rebalance_date = self.rebalance_dates[self.next_rebalance_idx]
        else:
            self.next_rebalance_date = None

    def next(self):
        current_date = self.timeline.datetime.date(0)

        if self.next_rebalance_date and current_date >= self.next_rebalance_date:
            self.log(
                f"--- Rebalancing on {current_date} for signal date {self.next_rebalance_date} ---"
            )
            target_tickers_df = self.p.portfolios[self.next_rebalance_date]
            target_tickers = set(target_tickers_df["Ticker"])

            self.log(
                f"Diagnosis: Model selected {len(target_tickers)} tickers: {target_tickers}"
            )

            available_data_tickers = {d._name for d in self.datas}

            final_target_tickers = target_tickers.intersection(available_data_tickers)
            missing_tickers = target_tickers - available_data_tickers

            self.log(
                f"Diagnosis: {len(available_data_tickers)} tickers have price data available in the database."
            )
            self.log(
                f"Diagnosis: Intersection has {len(final_target_tickers)} tickers: {final_target_tickers if final_target_tickers else 'EMPTY'}"
            )

            log_entry = {
                "rebalance_date": self.next_rebalance_date,
                "model_tickers": len(target_tickers),
                "available_tickers": len(final_target_tickers),
                "missing_tickers_list": ", ".join(missing_tickers),
            }
            self.rebalance_log.append(log_entry)

            if not final_target_tickers:
                self.log(
                    "CRITICAL WARNING: All-cash period. No selected tickers were found in the price database."
                )
                if missing_tickers:
                    self.log(
                        f"CRITICAL WARNING: The following {len(missing_tickers)} tickers were missing price data: {missing_tickers}"
                    )

                self.next_rebalance_idx += 1
                self.get_next_rebalance_date()
                return

            current_positions = {
                data._name for data in self.datas if self.getposition(data).size > 0
            }

            for ticker in current_positions:
                if ticker not in final_target_tickers:
                    data = self.getdatabyname(ticker)
                    self.log(f"Closing position in {ticker}")
                    self.order_target_percent(data=data, target=0.0)

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
        self.log("--- Backtest Finished ---")
        log_df = pd.DataFrame(self.rebalance_log)
        if not log_df.empty:
            log_path = OUTPUTS_DIR / "rebalancing_diagnostics_log.csv"
            log_df.to_csv(log_path, index=False)
            self.log(f"Rebalancing diagnostics saved to: {log_path}")


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
    portfolios = {}

    for date_str, df in xls.items():
        # 自动处理列名大小写，兼容 'ticker' 和 'Ticker'
        if 'ticker' in df.columns and 'Ticker' not in df.columns:
            df.rename(columns={'ticker': 'Ticker'}, inplace=True)
        
        if not df.empty and "Ticker" in df.columns:
            portfolios[pd.to_datetime(date_str).date()] = df

    return portfolios


def load_all_price_data_from_db(
    db_path: Path,
    all_needed_tickers: set,
    start_date: datetime.date,
    end_date: datetime.date,
) -> dict:
    print(f"Loading and preparing all price data from {start_date} to {end_date}...")
    if not db_path.exists():
        print(f"[ERROR] 数据库文件不存在: {db_path}", file=sys.stderr)
        sys.exit(1)

    con = sqlite3.connect(db_path)
    try:
        date_query = "SELECT DISTINCT Date FROM share_prices WHERE Date >= ? AND Date <= ? ORDER BY Date"
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

        all_data.drop_duplicates(subset=["Ticker", "Date"], keep="last", inplace=True)

        data_feeds = {}
        for ticker, group in all_data.groupby("Ticker"):
            group = group.set_index("Date")
            aligned_df = group.reindex(master_index)
            
            aligned_df.ffill(inplace=True)
            aligned_df.bfill(inplace=True)

            aligned_df["Volume"].fillna(0, inplace=True)
            aligned_df["Dividend"].fillna(0, inplace=True)

            if not aligned_df.empty and not aligned_df["Close"].isnull().all():
                data_feeds[ticker] = bt.feeds.PandasData(
                    dataname=aligned_df, name=ticker
                )

        print(f"Loaded data for {len(data_feeds)} tickers.")
        return data_feeds
    finally:
        con.close()


def setup_logging():
    log_file = OUTPUTS_DIR / "backtest_log_quarterly_ai_pick.txt"
    if log_file.exists():
        log_file.unlink()
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
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
    print("\n--- Running Quarterly AI Pick Strategy (Total Return) ---")
    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.set_cash(initial_cash)

    for name in sorted(data_feeds.keys()):
        cerebro.adddata(data_feeds[name], name=name)
        
    cerebro.addobserver(bt.observers.Broker)
    cerebro.addobserver(bt.observers.Trades)
    cerebro.addobserver(bt.observers.TimeReturn)

    cerebro.addstrategy(PointInTimeStrategy, portfolios=portfolios)

    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="time_return")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.AnnualReturn, _name="annual_return")

    results = cerebro.run()
    strat = results[0]

    print("\nCalculating performance metrics...")
    tr_analyzer = strat.analyzers.getbyname("time_return")
    returns = pd.Series(tr_analyzer.get_analysis(), name='return').sort_index()
    cumulative_returns = (1 + returns).cumprod()

    total_return = (
        cumulative_returns.iloc[-1] - 1 if not cumulative_returns.empty else 0.0
    )
    final_value = cerebro.broker.getvalue()
    max_drawdown = strat.analyzers.drawdown.get_analysis().max.drawdown
    
    annual_returns = strat.analyzers.annual_return.get_analysis()
    avg_annual_return = sum(annual_returns.values()) / len(annual_returns) if annual_returns else 0.0

    print("\n" + "=" * 50)
    print(f"{'Quarterly AI Pick Backtest Results':^50}")
    print("=" * 50)
    print(
        f"Time Period Covered:     {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
    )
    print(f"Initial Portfolio Value: ${initial_cash:,.2f}")
    print(f"Final Portfolio Value:   ${final_value:,.2f}")
    print("-" * 50)
    print(f"Total Return:            {total_return * 100:.2f}%")
    print(f"Annualized Return:       {avg_annual_return * 100:.2f}%")
    print(f"Max Drawdown:            {max_drawdown:.2f}%")
    print("=" * 50)

    print("\nGenerating performance chart...")
    portfolio_value = (
        initial_cash * cumulative_returns
        if not cumulative_returns.empty
        else pd.Series(
            {
                pd.Timestamp(start_date): initial_cash,
                pd.Timestamp(end_date): initial_cash,
            }
        )
    )
    start_date_ts = pd.Timestamp(start_date) - pd.Timedelta(days=1)
    portfolio_value = pd.concat(
        [pd.Series({start_date_ts: initial_cash}), portfolio_value]
    )

    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(14, 8))

    portfolio_value.plot(
        ax=ax, label="AI Quarterly Strategy", color="royalblue", lw=2
    )

    ax.set_title(
        f"AI Quarterly Strategy Backtest ({start_date.year} - {end_date.year})",
        fontsize=16,
    )
    ax.set_xlabel("Date", fontsize=12)
    ax.set_ylabel("Portfolio Value ($)", fontsize=12)
    ax.legend(fontsize=12)

    formatter = mticker.FuncFormatter(lambda x, p: f"${x:,.0f}")
    ax.yaxis.set_major_formatter(formatter)

    plt.tight_layout()

    output_path = OUTPUTS_DIR / "ai_quarterly_strategy_returns.png"
    plt.savefig(output_path, dpi=300)

    print(f"Chart saved successfully to: {output_path}")


def main():
    print("--- Running Quarterly Backtest with Backtrader (Database Mode) ---")

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

    first_rebalance_date = min(portfolios.keys())
    last_rebalance_date = max(portfolios.keys())

    BACKTEST_START_DATE = first_rebalance_date
    BACKTEST_END_DATE = last_rebalance_date + relativedelta(months=3, days=10)

    print("Dynamically set backtest period based on portfolio dates:")
    print(f"  - First signal date: {first_rebalance_date}")
    print(f"  - Data loading will start from: {BACKTEST_START_DATE}")
    print(f"  - Data loading will end around: {BACKTEST_END_DATE}")

    print(f"Calculating for a total of {len(all_needed_tickers)} unique tickers...")

    start_time = time.time()
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

    all_dates = set()
    for feed in price_data_dict.values():
        all_dates.update(feed.p.dataname.index.to_pydatetime())

    actual_end_date = max(all_dates).date() if all_dates else BACKTEST_END_DATE

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
    