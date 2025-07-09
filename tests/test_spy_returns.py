import backtrader as bt
import pandas as pd
from pathlib import Path
import datetime
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# --- 路径配置 ---
try:
    # 假设脚本位于根目录的 'tests' 文件夹下
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
except NameError:
    # 如果在交互式环境（如Jupyter）中运行，则使用当前工作目录
    PROJECT_ROOT = Path.cwd()

DATA_DIR = PROJECT_ROOT / 'data'
OUTPUTS_DIR = PROJECT_ROOT / 'outputs'
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# --- 回测配置 ---
SPY_TICKER = 'SPY'
PRICE_DATA_FILE = DATA_DIR / 'us-shareprices-daily.csv'
if not PRICE_DATA_FILE.exists():
    PRICE_DATA_FILE = DATA_DIR / 'us-shareprices-daily.txt'

INITIAL_CASH = 100_000.0
START_DATE = datetime.datetime(2015, 8, 31)
END_DATE = datetime.datetime(2023, 12, 31)

# --- 辅助函数 ---
def tidy_ticker(col: pd.Series) -> pd.Series:
    """统一清洗和格式化股票代码列。"""
    return col.astype('string').str.upper().str.strip().str.replace(r'_DELISTED$', '', regex=True).replace({'': pd.NA})

def load_spy_data(price_path: Path, start_date: datetime.datetime, end_date: datetime.datetime) -> pd.DataFrame:
    """加载并准备SPY的日频价格数据。"""
    print(f"Loading SPY data from {price_path.name}...")
    if not price_path.exists():
        raise FileNotFoundError(f"Price data file not found: {price_path}")

    px_full = pd.read_csv(price_path, sep=';', parse_dates=['Date'])
    
    # --- 关键修复：清理列名中的所有潜在空格 ---
    px_full.columns = px_full.columns.str.strip()
    # -------------------------------------------

    px_full['Ticker'] = tidy_ticker(px_full['Ticker'])
    px_full.dropna(subset=['Ticker', 'Date', 'Adj. Close'], inplace=True)
    
    spy_df = px_full[
        (px_full['Ticker'] == SPY_TICKER) &
        (px_full['Date'] >= start_date) &
        (px_full['Date'] <= end_date)
    ].copy()

    if spy_df.empty:
        # 提供了更详细的错误信息
        full_date_range = px_full[px_full['Ticker'] == SPY_TICKER]['Date']
        if not full_date_range.empty:
             raise ValueError(f"No data found for SPY ticker '{SPY_TICKER}' in the specified date range "
                           f"({start_date.date()} to {end_date.date()}). "
                           f"However, data exists in the file from {full_date_range.min().date()} to {full_date_range.max().date()}.")
        else:
            raise ValueError(f"No data found for SPY ticker '{SPY_TICKER}' in the entire file.")

    spy_df.set_index('Date', inplace=True)
    
    # 重命名列以匹配 backtrader 的要求
    spy_df.rename(columns={
        'Open': 'open', 'High': 'high', 'Low': 'low',
        'Adj. Close': 'close', 'Volume': 'volume', 'Dividend': 'dividend'
    }, inplace=True)
    
    # 确保所有必需的列都存在
    # 检查 'close' 列是否存在，这是最重要的
    if 'close' not in spy_df.columns:
        raise KeyError("Failed to create 'close' column. Check if 'Adj. Close' exists in the CSV and is spelled correctly.")

    for col in ['open', 'high', 'low', 'volume', 'dividend']:
        if col not in spy_df.columns:
            # 如果 'open', 'high', 'low' 不存在, 用 'close' 填充
            if col in ['open', 'high', 'low']:
                spy_df[col] = spy_df['close']
            else: # 其他缺失列（如volume, dividend）用0填充
                spy_df[col] = 0

    spy_df['openinterest'] = 0
    
    print(f"Loaded {len(spy_df)} rows for SPY from {spy_df.index.min().date()} to {spy_df.index.max().date()}.")
    return spy_df[['open', 'high', 'low', 'close', 'volume', 'dividend', 'openinterest']]

# --- Backtrader 策略 ---
class BuyAndHold(bt.Strategy):
    """一个简单的买入并持有策略。"""
    def start(self):
        # 将几乎所有的现金用于买入资产
        self.order_target_percent(target=0.99)

    def next(self):
        # 策略逻辑在start中已完成，next中无需操作
        pass

# --- 回测执行函数 ---
def run_spy_backtest(data: pd.DataFrame, initial_cash: float, include_dividends: bool) -> pd.Series:
    """
    运行一个买入并持有SPY的回测。

    Args:
        data (pd.DataFrame): 包含价格和（可选）分红的数据。
        initial_cash (float): 初始资金。
        include_dividends (bool): 是否在回测中考虑分红。

    Returns:
        pd.Series: 包含每日投资组合价值的时间序列。
    """
    cerebro = bt.Cerebro()
    cerebro.broker.set_cash(initial_cash)
    
    # 如果不考虑分红，则从数据中移除分红列
    data_for_feed = data.copy()
    if not include_dividends:
        data_for_feed['dividend'] = 0.0

    # 创建数据feed
    feed = bt.feeds.PandasData(dataname=data_for_feed)
    cerebro.adddata(feed)
    
    # 添加策略
    cerebro.addstrategy(BuyAndHold)
    
    # 添加分析器以跟踪投资组合价值
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name='time_return')

    print(f"Running backtest {'WITH' if include_dividends else 'WITHOUT'} dividends...")
    results = cerebro.run()
    
    # 提取每日回报率
    tr_analyzer = results[0].analyzers.getbyname('time_return')
    returns = pd.Series(tr_analyzer.get_analysis())
    
    # 计算累计回报并转换为投资组合价值
    cumulative_returns = (1 + returns).cumprod()
    portfolio_value = initial_cash * cumulative_returns
    
    # 将初始值添加到序列的开头
    start_date = data.index.min() - pd.Timedelta(days=1)
    portfolio_value = pd.concat([pd.Series({start_date: initial_cash}), portfolio_value])
    
    return portfolio_value

# --- 主逻辑 ---
def main():
    """主执行函数"""
    print("--- SPY Price Return vs. Total Return Backtest ---")
    
    try:
        spy_data = load_spy_data(PRICE_DATA_FILE, START_DATE, END_DATE)
    except (FileNotFoundError, ValueError) as e:
        print(f"[ERROR] Failed to load data: {e}")
        return

    # 1. 运行价格收益回测 (不考虑分红)
    price_returns_portfolio = run_spy_backtest(spy_data, INITIAL_CASH, include_dividends=False)
    
    # 2. 运行总收益回测 (考虑分红)
    total_returns_portfolio = run_spy_backtest(spy_data, INITIAL_CASH, include_dividends=True)
    
    print("\n--- Backtest Results ---")
    print(f"Final Value (Price Return): ${price_returns_portfolio.iloc[-1]:,.2f}")
    print(f"Final Value (Total Return): ${total_returns_portfolio.iloc[-1]:,.2f}")

    # 3. 绘图比较
    print("\nGenerating comparison plot...")
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(14, 8))
    
    price_returns_portfolio.plot(ax=ax, label='SPY Price Return (No Dividends)', color='royalblue', lw=2)
    total_returns_portfolio.plot(ax=ax, label='SPY Total Return (Dividends Reinvested)', color='darkorange', lw=2)
    
    ax.set_title(f'SPY: Price Return vs. Total Return ({START_DATE.year} - {END_DATE.year})', fontsize=16)
    ax.set_xlabel('Date', fontsize=12)
    ax.set_ylabel('Portfolio Value ($)', fontsize=12)
    ax.legend(fontsize=12)
    
    # 格式化Y轴为美元
    formatter = mticker.FormatStrFormatter('$%.0f')
    ax.yaxis.set_major_formatter(formatter)
    
    plt.tight_layout()
    
    # 保存图表
    output_path = OUTPUTS_DIR / 'spy_price_vs_total_return.png'
    plt.savefig(output_path, dpi=300)
    
    print(f"Plot saved successfully to: {output_path}")
    # plt.show() # 如果在本地运行，可以取消注释以显示图表

if __name__ == "__main__":
    main()