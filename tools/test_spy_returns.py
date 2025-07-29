import backtrader as bt
import pandas as pd
from pathlib import Path
import datetime
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import sqlite3

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

# 数据库路径
DB_PATH = DATA_DIR / 'financial_data.db'

# --- 回测配置 ---
SPY_TICKER = 'SPY'
PRICE_DATA_FILE = DATA_DIR / 'us-shareprices-daily.csv'
if not PRICE_DATA_FILE.exists():
    PRICE_DATA_FILE = DATA_DIR / 'us-shareprices-daily.txt'

INITIAL_CASH = 100_000.0
START_DATE = datetime.datetime(2020, 12, 31)
END_DATE = datetime.datetime(2025, 3, 31)

# --- 辅助函数 ---
def tidy_ticker(col: pd.Series) -> pd.Series:
    """统一清洗和格式化股票代码列。"""
    return col.astype('string').str.upper().str.strip().str.replace(r'_DELISTED$', '', regex=True).replace({'': pd.NA})

def load_spy_data_from_db(db_path: Path, start_date: datetime.datetime, end_date: datetime.datetime) -> pd.DataFrame:
    """从SQLite数据库加载并准备SPY的日频价格数据。"""
    print(f"Loading SPY data from database: {db_path.name}...")
    
    if not db_path.exists():
        raise FileNotFoundError(f"Database file not found: {db_path}")
    
    # 连接数据库
    con = sqlite3.connect(db_path)
    
    try:
        # 查询SPY数据
        query = """
        SELECT Date, Open, High, Low, Close, Volume, Dividend
        FROM share_prices 
        WHERE Ticker = ? AND Date >= ? AND Date <= ?
        ORDER BY Date
        """
        
        spy_data = pd.read_sql_query(
            query, 
            con, 
            params=[SPY_TICKER, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')],
            parse_dates=['Date']
        )
        
        if spy_data.empty:
            raise ValueError(f"No SPY data found in database for the specified date range: {start_date} to {end_date}")
        
        # 设置日期为索引
        spy_data.set_index('Date', inplace=True)
        
        # 重命名列以符合backtrader的要求
        column_mapping = {
            'Open': 'open',
            'High': 'high', 
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume',
            'Dividend': 'dividend'
        }
        
        spy_data = spy_data.rename(columns=column_mapping)
        
        # 确保所有必需的列都存在
        required_columns = ['open', 'high', 'low', 'close', 'volume', 'dividend']
        for col in required_columns:
            if col not in spy_data.columns:
                if col == 'dividend':
                    spy_data[col] = 0.0  # 如果没有分红列，设为0
                else:
                    raise ValueError(f"Required column '{col}' not found in data")
        
        spy_data['openinterest'] = 0
        
        # 填充缺失值
        spy_data['dividend'] = spy_data['dividend'].fillna(0.0)
        price_volume_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in price_volume_cols:
            spy_data[col] = spy_data[col].ffill().bfill()
        
        # Final check for any NaNs
        if spy_data[['open', 'high', 'low', 'close', 'volume']].isnull().values.any():
            raise ValueError("NaN values still present in the final data feed. Halting.")
        
        print(f"Loaded {len(spy_data)} rows for SPY from {spy_data.index.min().date()} to {spy_data.index.max().date()}.")
        
        # 调试：检查分红数据
        dividend_data = spy_data[spy_data['dividend'] > 0]
        print(f"Found {len(dividend_data)} dividend payments:")
        if len(dividend_data) > 0:
            print(dividend_data[['close', 'dividend']].head())
        
        return spy_data[['open', 'high', 'low', 'close', 'volume', 'dividend', 'openinterest']]
        
    finally:
        con.close()

def load_spy_data(price_path: Path, start_date: datetime.datetime, end_date: datetime.datetime) -> pd.DataFrame:
    """加载并准备SPY的日频价格数据。优先从数据库读取，如果失败则从CSV文件读取。"""
    
    # 优先尝试从数据库读取
    try:
        return load_spy_data_from_db(DB_PATH, start_date, end_date)
    except Exception as e:
        print(f"Failed to load from database: {e}")
        print(f"Falling back to CSV file: {price_path.name}...")
    
    # 备用：从CSV文件读取
    if not price_path.exists():
        raise FileNotFoundError(f"Price data file not found: {price_path}")

    px_full = pd.read_csv(price_path, sep=';', parse_dates=['Date'])
    px_full.columns = px_full.columns.str.strip()
    
    print(">>> Actual CSV Columns:", px_full.columns.tolist())

    numeric_cols = ['Open', 'High', 'Low', 'Close', 'Adj. Close', 'Volume', 'Dividend']
    for col in numeric_cols:
        if col in px_full.columns:
            px_full[col] = pd.to_numeric(px_full[col], errors='coerce')
        else:
            px_full[col] = 0

    # --- ROBUST NaN FILLING ---
    # Fix the FutureWarning and ensure Dividend is filled first
    px_full['Dividend'] = px_full['Dividend'].fillna(0.0)

    # Use a two-pass fill for price/volume to handle NaNs at the start or end
    price_volume_cols = ['Open', 'High', 'Low', 'Close', 'Adj. Close', 'Volume']
    for col in price_volume_cols:
        if col in px_full.columns:
            # First, forward-fill, then backward-fill any remaining NaNs (like at the start)
            px_full[col] = px_full.groupby('Ticker')[col].ffill().bfill()
    # --- END OF ROBUST FILLING ---

    px_full['Ticker'] = tidy_ticker(px_full['Ticker'])
    px_full.dropna(subset=['Ticker', 'Date', 'Adj. Close'], inplace=True)
    
    spy_df = px_full[
        (px_full['Ticker'] == SPY_TICKER) &
        (px_full['Date'] >= start_date) &
        (px_full['Date'] <= end_date)
    ].copy()

    if spy_df.empty:
        raise ValueError(f"No data found for SPY ticker '{SPY_TICKER}' in the specified date range.")

    spy_df.set_index('Date', inplace=True)
    
    spy_df.rename(columns={
        'Open': 'open', 'High': 'high', 'Low': 'low',
        'Close': 'close', 'Volume': 'volume', 'Dividend': 'dividend'
    }, inplace=True)
    
    for col in ['open', 'high', 'low', 'close', 'volume', 'dividend']:
        if col not in spy_df.columns:
            spy_df[col] = 0.0

    spy_df['openinterest'] = 0
    
    # Final check for any NaNs
    if spy_df[['open', 'high', 'low', 'close', 'volume']].isnull().values.any():
        raise ValueError("NaN values still present in the final data feed. Halting.")

    print(f"Loaded {len(spy_df)} rows for SPY from {spy_df.index.min().date()} to {spy_df.index.max().date()}.")
    
    # 检查分红数据
    dividend_data = spy_df[spy_df['dividend'] > 0]
    print(f"Found {len(dividend_data)} dividend payments:")
    if len(dividend_data) > 0:
        print(dividend_data[['close', 'dividend']].head())
    return spy_df[['open', 'high', 'low', 'close', 'volume', 'dividend', 'openinterest']]

# --- Backtrader 策略 ---
class BuyAndHold(bt.Strategy):
    """一个简单的买入并持有策略。"""
    params = (
        ('include_dividends', False),
    )
    
    def __init__(self):
        self.bought = False
    
    def next(self):
        # 只在第一次有数据时买入
        if not self.bought:
            # 将几乎所有的现金用于买入资产
            self.order_target_percent(target=0.99)
            self.bought = True
        
        # 处理分红
        if self.params.include_dividends:
            # 尝试访问分红数据
            try:
                # 检查当前数据行是否有分红
                current_date = self.data.datetime.date(0)
                # 从原始数据中查找分红
                if hasattr(self, 'dividend_data'):
                    dividend_today = self.dividend_data.get(current_date, 0)
                    if dividend_today > 0:
                        position_size = self.getposition().size
                        if position_size > 0:
                            dividend_amount = dividend_today * position_size
                            self.broker.add_cash(dividend_amount)
                            print(f"Dividend received: ${dividend_amount:.2f} on {current_date}")
            except Exception as e:
                pass  # 忽略错误，继续执行

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
    
    # 准备用于backtrader的数据
    data_for_feed = data[['open', 'high', 'low', 'close', 'volume']].copy()
    
    # 添加分红列
    if include_dividends:
        data_for_feed['dividend'] = data['dividend']
    else:
        data_for_feed['dividend'] = 0.0
    
    # 添加openinterest列（backtrader需要）
    data_for_feed['openinterest'] = 0
    
    # 确保没有缺失值
    data_for_feed = data_for_feed.fillna(0)

    # 创建数据feed
    feed = bt.feeds.PandasData(dataname=data_for_feed)
    cerebro.adddata(feed)
    
    # 准备分红数据字典
    dividend_data = {}
    if include_dividends:
        dividend_rows = data[data['dividend'] > 0]
        for date, row in dividend_rows.iterrows():
            dividend_data[date.date()] = row['dividend']
    
    # 添加策略，传递分红参数和分红数据
    strategy = cerebro.addstrategy(BuyAndHold, include_dividends=include_dividends)
    # 将分红数据附加到策略类
    BuyAndHold.dividend_data = dividend_data
    
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
    
    # 计算收益率
    price_return_pct = (price_returns_portfolio.iloc[-1] / INITIAL_CASH - 1) * 100
    total_return_pct = (total_returns_portfolio.iloc[-1] / INITIAL_CASH - 1) * 100
    dividend_benefit = total_return_pct - price_return_pct
    
    print(f"\nPrice Return: {price_return_pct:.2f}%")
    print(f"Total Return: {total_return_pct:.2f}%")
    print(f"Dividend Benefit: {dividend_benefit:.2f}%")

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