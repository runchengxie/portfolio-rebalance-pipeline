import datetime
import sqlite3
from pathlib import Path

import backtrader as bt
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd

# --- 路径配置 ---
try:
    # 假设脚本位于根目录的 'tests' 文件夹下
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
except NameError:
    # 如果在交互式环境（如Jupyter）中运行，则使用当前工作目录
    PROJECT_ROOT = Path.cwd()

DATA_DIR = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# 数据库路径
DB_PATH = DATA_DIR / "financial_data.db"

# --- 回测配置 ---
SPY_TICKER = "SPY"
INITIAL_CASH = 100_000.0
START_DATE = datetime.datetime(2021, 4, 2)
END_DATE = datetime.datetime(2025, 7, 2)


# --- 辅助函数 ---
def load_spy_data_from_db(
    db_path: Path, start_date: datetime.datetime, end_date: datetime.datetime
) -> pd.DataFrame:
    """从SQLite数据库加载并准备SPY的日频价格数据。"""
    print(f"Loading SPY data from database: {db_path.name}...")

    if not db_path.exists():
        raise FileNotFoundError(f"Database file not found: {db_path}")

    con = sqlite3.connect(db_path)

    try:
        query = """
        SELECT Date, Open, High, Low, Close, Volume, Dividend
        FROM share_prices 
        WHERE Ticker = ? AND Date >= ? AND Date <= ?
        ORDER BY Date
        """

        spy_data = pd.read_sql_query(
            query,
            con,
            params=[
                SPY_TICKER,
                start_date.strftime("%Y-%m-%d"),
                end_date.strftime("%Y-%m-%d"),
            ],
            parse_dates=["Date"],
        )

        if spy_data.empty:
            raise ValueError(
                f"No SPY data found in database for the specified date range: {start_date} to {end_date}"
            )

        spy_data.set_index("Date", inplace=True)
        spy_data["Dividend"] = spy_data["Dividend"].fillna(0.0)

        print(
            f"Loaded {len(spy_data)} rows for SPY from {spy_data.index.min().date()} to {spy_data.index.max().date()}."
        )
        return spy_data

    finally:
        con.close()


# --- Backtrader 策略 ---
class BuyAndHold(bt.Strategy):
    """一个简单的买入并持有策略。"""

    def __init__(self):
        self.bought = False

    def next(self):
        if not self.bought:
            self.order_target_percent(target=0.99)
            self.bought = True


# --- 回测执行与报告函数 ---
def run_spy_backtest(data: pd.DataFrame, initial_cash: float) -> tuple[pd.Series, dict]:
    """
    运行一个买入并持有SPY的总回报回测。
    """
    print("\n--- Running SPY Buy-and-Hold Backtest (Total Return) ---")

    cerebro = bt.Cerebro()
    cerebro.broker.set_cash(initial_cash)

    # 准备数据 feed，backtrader会自动处理'Dividend'列
    bt_feed = bt.feeds.PandasData(dataname=data, openinterest=None)
    cerebro.adddata(bt_feed)

    cerebro.addstrategy(BuyAndHold)

    # 添加分析器
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="time_return")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")

    results = cerebro.run()
    strat = results[0]

    # --- 提取指标 ---
    final_value = cerebro.broker.getvalue()
    total_return = strat.analyzers.returns.get_analysis().get("rtot", 0.0)
    max_drawdown = strat.analyzers.drawdown.get_analysis().max.drawdown

    start_date = data.index.min().date()
    end_date = data.index.max().date()

    # 计算年化收益率 (逻辑与 run_backtest.py 完全相同)
    duration_in_days = (end_date - start_date).days
    annualized_return = 0.0
    if duration_in_days > 0:
        duration_in_years = duration_in_days / 365.25
        if duration_in_years > 0:
            annualized_return = ((1 + total_return) ** (1 / duration_in_years)) - 1

    # 生成每日投资组合价值序列
    tr_analyzer = strat.analyzers.getbyname("time_return")
    returns = pd.Series(tr_analyzer.get_analysis())
    cumulative_returns = (1 + returns).cumprod()
    portfolio_value = initial_cash * cumulative_returns
    start_date_ts = data.index.min() - pd.Timedelta(days=1)
    portfolio_value = pd.concat(
        [pd.Series({start_date_ts: initial_cash}), portfolio_value]
    )

    # 将指标打包成字典，以便打印报告
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


def print_summary_report(metrics: dict):
    """格式化并打印回测结果报告。"""
    print("\n" + "=" * 50)
    print(f"{'SPY Benchmark Results (Total Return)':^50}")
    print("=" * 50)
    print(
        f"Time Period Covered:     {metrics['start_date'].strftime('%Y-%m-%d')} to {metrics['end_date'].strftime('%Y-%m-%d')}"
    )
    print(f"Initial Portfolio Value: ${metrics['initial_value']:,.2f}")
    print(f"Final Portfolio Value:   ${metrics['final_value']:,.2f}")
    print("-" * 50)
    print(f"Total Return:            {metrics['total_return'] * 100:.2f}%")
    print(f"Annualized Return:       {metrics['annualized_return'] * 100:.2f}%")
    print(f"Max Drawdown:            {metrics['max_drawdown']:.2f}%")
    print("=" * 50)


# --- 主逻辑 ---
def main():
    """主执行函数"""
    print("--- SPY Benchmark Backtest ---")

    try:
        spy_data = load_spy_data_from_db(DB_PATH, START_DATE, END_DATE)
    except (FileNotFoundError, ValueError) as e:
        print(f"[ERROR] Failed to load data: {e}")
        return

    # 运行总回报回测
    portfolio_value, metrics = run_spy_backtest(spy_data, INITIAL_CASH)

    # 打印总结报告
    print_summary_report(metrics)

    # 绘图
    print("\nGenerating plot...")
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(14, 8))

    portfolio_value.plot(
        ax=ax, label="SPY Buy & Hold (Total Return)", color="darkorange", lw=2
    )

    ax.set_title(
        f"SPY Benchmark: Buy-and-Hold Total Return ({START_DATE.year} - {END_DATE.year})",
        fontsize=16,
    )
    ax.set_xlabel("Date", fontsize=12)
    ax.set_ylabel("Portfolio Value ($)", fontsize=12)
    ax.legend(fontsize=12)

    formatter = mticker.FormatStrFormatter("$%.0f")
    ax.yaxis.set_major_formatter(formatter)

    plt.tight_layout()

    output_path = OUTPUTS_DIR / "spy_total_return_benchmark.png"
    plt.savefig(output_path, dpi=300)

    print(f"Plot saved successfully to: {output_path}")


if __name__ == "__main__":
    main()
