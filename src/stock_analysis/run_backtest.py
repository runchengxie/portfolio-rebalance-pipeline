# src/stock_analysis/run_backtest.py
# 
# 改进版回测脚本，支持SQLite数据库加载以获得更好的性能
# 
# 主要改进：
# 1. 添加了从SQLite数据库加载数据的功能
# 2. 使用批量查询优化数据库访问性能
# 3. 自动回退到CSV文件加载（向后兼容）
# 4. 添加了性能监控和数据源信息显示
# 
# 使用方法：
# - 设置 USE_DATABASE = True 使用数据库模式（推荐）
# - 设置 USE_DATABASE = False 使用传统CSV模式
# - 确保 financial_data.db 存在（通过 tools/load_data_to_db.py 创建）

import backtrader as bt
import pandas as pd
from pathlib import Path
import datetime
import sqlite3
# --- 新增的导入 ---
import logging
import sys
# --- 新增结束 ---

# --- 路径配置 ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
OUTPUTS_DIR = PROJECT_ROOT / 'outputs'
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# --- 回测配置 ---
NUM_STOCKS_TO_SELECT = 50
PORTFOLIO_FILE = OUTPUTS_DIR / f'point_in_time_backtest_top_{NUM_STOCKS_TO_SELECT}_stocks.xlsx'
PRICE_DATA_FILE = DATA_DIR / 'us-shareprices-daily.csv'
if not PRICE_DATA_FILE.exists():
    PRICE_DATA_FILE = DATA_DIR / 'us-shareprices-daily.txt'

# --- 数据库配置 ---
DB_PATH = DATA_DIR / 'financial_data.db'
USE_DATABASE = True  # 设置为True使用数据库，False使用CSV文件

def configure_data_source(use_database: bool = True):
    """
    配置数据源。
    
    Args:
        use_database (bool): True使用数据库，False使用CSV文件
    """
    global USE_DATABASE
    USE_DATABASE = use_database
    
    if use_database:
        if not DB_PATH.exists():
            print(f"[WARNING] 数据库文件不存在: {DB_PATH}")
            print("[WARNING] 请先运行 tools/load_data_to_db.py 创建数据库")
            print("[WARNING] 将自动切换到CSV模式")
            USE_DATABASE = False
        else:
            print(f"[INFO] 数据库模式已启用: {DB_PATH}")
    else:
        print(f"[INFO] CSV模式已启用: {PRICE_DATA_FILE}")
    
    return USE_DATABASE

INITIAL_CASH = 1_000_000.0
SPY_TICKER = 'SPY' # 确保这个 Ticker 与您的数据文件中的完全一致

# --- Backtrader 策略 ---
class PointInTimeStrategy(bt.Strategy):
    params = (('portfolios', None),)

    def __init__(self):
        self.rebalance_dates = sorted(self.p.portfolios.keys())
        self.next_rebalance_idx = 0
        self.get_next_rebalance_date()
        # 将SPY数据单独保存，用于获取当前日期
        self.spy_data = self.getdatabyname(SPY_TICKER)

    def log(self, txt, dt=None):
        dt = dt or self.spy_data.datetime.date(0)
        # 现在 log 方法会通过 print 被日志系统捕获
        print(f'{dt.isoformat()} - {txt}')

    def get_next_rebalance_date(self):
        if self.next_rebalance_idx < len(self.rebalance_dates):
            self.next_rebalance_date = self.rebalance_dates[self.next_rebalance_idx]
        else:
            self.next_rebalance_date = None

    def next(self):
        current_date = self.spy_data.datetime.date(0)

        if self.next_rebalance_date and current_date >= self.next_rebalance_date:
            self.log(f'--- Rebalancing on {current_date} for signal date {self.next_rebalance_date} ---')
            target_tickers_df = self.p.portfolios[self.next_rebalance_date]
            target_tickers = set(target_tickers_df['Ticker'])
            available_data_tickers = {d._name for d in self.datas if d._name != SPY_TICKER}
            final_target_tickers = target_tickers.intersection(available_data_tickers)

            if not final_target_tickers:
                self.log("Warning: No target tickers are available in the price data for this period.")
                self.next_rebalance_idx += 1
                self.get_next_rebalance_date()
                return

            current_positions = {data._name for data in self.datas if self.getposition(data).size > 0}
            
            # Sell stocks no longer in the target portfolio
            for ticker in current_positions:
                if ticker not in final_target_tickers and ticker != SPY_TICKER:
                    data = self.getdatabyname(ticker)
                    self.log(f'Closing position in {ticker}')
                    self.order_target_percent(data=data, target=0.0)

            # Buy stocks in the target portfolio
            target_percent = 1.0 / len(final_target_tickers)
            for ticker in final_target_tickers:
                data = self.getdatabyname(ticker)
                self.log(f'Setting target position for {ticker} to {target_percent:.2%}')
                self.order_target_percent(data=data, target=target_percent)
            
            self.next_rebalance_idx += 1
            self.get_next_rebalance_date()
            self.log('--- Rebalancing Complete ---')

class BuyAndHoldSpy(bt.Strategy):
    def start(self):
        self.spy = self.datas[0]
        self.log(f"Strategy started. Initial portfolio value: {self.broker.getvalue():.2f}")
        self.order_target_percent(data=self.spy, target=0.99)

    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        print(f'{dt.isoformat()} - SPY Strategy - {txt}')

# --- 辅助函数 ---
def tidy_ticker(col: pd.Series) -> pd.Series:
    return col.astype('string').str.upper().str.strip().str.replace(r'_DELISTED$', '', regex=True).replace({'': pd.NA})

def load_portfolios(portfolio_path: Path) -> dict:
    if not portfolio_path.exists():
        raise FileNotFoundError(f"Portfolio file not found: {portfolio_path}")
    xls = pd.read_excel(portfolio_path, sheet_name=None, engine='openpyxl')
    portfolios = {pd.to_datetime(date_str).date(): df for date_str, df in xls.items()}
    return {k: v for k, v in portfolios.items() if not v.empty and 'Ticker' in v.columns}

def load_all_price_data_from_db(db_path: Path, all_needed_tickers: set, start_date: datetime.date, end_date: datetime.date) -> dict:
    """
    从SQLite数据库加载并准备所有价格数据，将所有股票对齐到主时间线。
    """
    print("Loading and preparing all price data from database...")
    
    if not db_path.exists():
        raise FileNotFoundError(f"Database file not found: {db_path}")
    
    con = sqlite3.connect(db_path)
    
    try:
        # 首先获取SPY数据以建立主时间线
        spy_query = """
        SELECT Date, Open, High, Low, Close, Volume, Dividend
        FROM share_prices 
        WHERE Ticker = ? AND Date >= ? AND Date <= ?
        ORDER BY Date
        """
        
        spy_df = pd.read_sql_query(
            spy_query,
            con,
            params=[SPY_TICKER, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')],
            parse_dates=['Date']
        )
        
        if spy_df.empty:
            raise ValueError(f"SPY ticker '{SPY_TICKER}' not found in database for the specified date range.")
        
        spy_df.set_index('Date', inplace=True)
        master_index = spy_df.index.unique().sort_values()
        print(f"Master timeline created from SPY data with {len(master_index)} trading days.")
        
        # 批量查询所有需要的股票数据
        tickers_list = list(all_needed_tickers)
        placeholders = ','.join(['?' for _ in tickers_list])
        
        bulk_query = f"""
        SELECT Date, Ticker, Open, High, Low, Close, Volume, Dividend
        FROM share_prices 
        WHERE Ticker IN ({placeholders}) AND Date >= ? AND Date <= ?
        ORDER BY Ticker, Date
        """
        
        params = tickers_list + [start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')]
        
        all_data = pd.read_sql_query(
            bulk_query,
            con,
            params=params,
            parse_dates=['Date']
        )
        
        if all_data.empty:
            raise ValueError("No price data found in database for the specified tickers and date range.")
        
        # 数据预处理
        all_data.set_index('Date', inplace=True)
        
        # 重命名列以符合backtrader要求
        column_mapping = {
            'Open': 'open',
            'High': 'high', 
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume',
            'Dividend': 'dividend'
        }
        all_data = all_data.rename(columns=column_mapping)
        
        # 添加openinterest列
        all_data['openinterest'] = 0
        
        # 按股票分组处理数据
        data_feeds = {}
        for ticker in sorted(list(all_needed_tickers)):
            df_ticker_raw = all_data[all_data['Ticker'] == ticker][['open', 'high', 'low', 'close', 'volume', 'dividend', 'openinterest']].sort_index()
            
            if df_ticker_raw.empty:
                print(f"  [WARNING] No price data for ticker '{ticker}' in the specified date range.")
                continue
            
            # 对齐到主时间线
            df_aligned = df_ticker_raw.reindex(master_index)
            
            # 填充缺失值
            df_aligned[['open', 'high', 'low', 'close']] = df_aligned[['open', 'high', 'low', 'close']].ffill()
            df_aligned[['volume', 'dividend', 'openinterest']] = df_aligned[['volume', 'dividend', 'openinterest']].fillna(0)
            df_aligned.dropna(inplace=True)

            if not df_aligned.empty:
                data_feeds[ticker] = df_aligned
            else:
                print(f"  [WARNING] Ticker '{ticker}' has no overlapping data with the master timeline after alignment.")
                
        print(f"Loaded and aligned price data for {len(data_feeds)} tickers from database.")
        return data_feeds
        
    finally:
        con.close()

def load_all_price_data(price_path: Path, all_needed_tickers: set, start_date: datetime.date, end_date: datetime.date) -> dict:
    """
    Loads and prepares all price data, aligning all tickers to a master timeline.
    优先从数据库加载，如果失败则从CSV文件加载。
    """
    # 如果启用数据库且数据库文件存在，优先使用数据库
    if USE_DATABASE and DB_PATH.exists():
        try:
            return load_all_price_data_from_db(DB_PATH, all_needed_tickers, start_date, end_date)
        except Exception as e:
            print(f"Failed to load from database: {e}")
            print(f"Falling back to CSV file: {price_path.name}...")
    
    # 备用：从CSV文件加载（原有逻辑）
    print("Loading and preparing all price data from CSV...")
    px_full = pd.read_csv(price_path, sep=';', parse_dates=['Date'])
    px_full['Ticker'] = tidy_ticker(px_full['Ticker'])
    px_full.dropna(subset=['Ticker', 'Date', 'Adj. Close'], inplace=True)
    
    px = px_full[(px_full['Date'] >= pd.to_datetime(start_date)) & (px_full['Date'] <= pd.to_datetime(end_date))].copy()
    px.set_index('Date', inplace=True)

    for col in ['Open', 'High', 'Low', 'Close', 'Volume', 'Dividend']:
        if col not in px.columns:
            px[col] = px['Adj. Close'] if col in ['Open', 'High', 'Low', 'Close'] else 0
    
    px.rename(columns={
        'Open': 'open', 'High': 'high', 'Low': 'low',
        'Adj. Close': 'close', 'Volume': 'volume', 'Dividend': 'dividend'
    }, inplace=True)
    
    px['openinterest'] = 0

    if SPY_TICKER not in px['Ticker'].unique():
        raise ValueError(f"SPY ticker '{SPY_TICKER}' not found in price data.")
    
    spy_df = px[px['Ticker'] == SPY_TICKER]
    master_index = spy_df.index.unique().sort_values()
    print(f"Master timeline created from SPY data with {len(master_index)} trading days.")

    data_feeds = {}
    for ticker in sorted(list(all_needed_tickers)):
        df_ticker_raw = px[px['Ticker'] == ticker][['open', 'high', 'low', 'close', 'volume', 'dividend', 'openinterest']].sort_index()
        
        if df_ticker_raw.empty:
            print(f"  [WARNING] No price data for ticker '{ticker}' in the specified date range.")
            continue
        
        df_aligned = df_ticker_raw.reindex(master_index)
        df_aligned[['open', 'high', 'low', 'close']] = df_aligned[['open', 'high', 'low', 'close']].ffill()
        df_aligned[['volume', 'dividend', 'openinterest']] = df_aligned[['volume', 'dividend', 'openinterest']].fillna(0)
        df_aligned.dropna(inplace=True)

        if not df_aligned.empty:
            data_feeds[ticker] = df_aligned
        else:
            print(f"  [WARNING] Ticker '{ticker}' has no overlapping data with the master timeline after alignment.")
            
    print(f"Loaded and aligned price data for {len(data_feeds)} tickers from CSV.")
    return data_feeds


def print_analysis(analyzers, initial_cash):
    """打印分析器的结果"""
    pyfolio_analyzer = analyzers.pyfolio.get_analysis()
    returns_series = pd.Series(pyfolio_analyzer.get('returns', {}))
    total_open = initial_cash

    if not returns_series.empty:
        cumulative_returns = (1 + returns_series).cumprod()
        total_close = total_open * cumulative_returns.iloc[-1]
        total_return = (total_close - total_open) / total_open
        num_years = len(returns_series) / 252.0
        annual_return = (1 + total_return) ** (1.0/num_years) - 1 if num_years > 0 else 0.0
    else:
        total_close, total_return, num_years, annual_return = total_open, 0.0, 0.0, 0.0

    print(f'期初价值: {total_open:,.2f}')
    print(f'期末价值: {total_close:,.2f}')
    print(f'总回报率: {total_return:.2%}')
    if num_years > 0:
        print(f'年化回报率: {annual_return:.2%}')
    
    sharpe_analyzer = analyzers.sharpe
    if sharpe_analyzer:
        sharpe_ratio = sharpe_analyzer.get_analysis().get('sharperatio')
        if sharpe_ratio is not None:
             print(f'夏普比率 (年化): {sharpe_ratio:.2f}')

    drawdown_analyzer = analyzers.drawdown
    if drawdown_analyzer:
        dd_analysis = drawdown_analyzer.get_analysis()
        if dd_analysis and hasattr(dd_analysis, 'max') and dd_analysis.max.drawdown is not None:
            print(f'最大回撤: {dd_analysis.max.drawdown:.2%}')
            print(f'最大回撤周期 (天): {dd_analysis.max.len}')

# ==============================================================================
# --- 新增：日志配置 ---
# ==============================================================================

class StreamToLogger:
    """
    一个辅助类，用于将流（如 sys.stdout, sys.stderr）的输出重定向到 logging 模块。
    """
    def __init__(self, logger, level):
        self.logger = logger
        self.level = level

    def write(self, message):
        # 移除消息末尾的空白符，避免打印空行
        if message.rstrip():
            self.logger.log(self.level, message.rstrip())

    def flush(self):
        # 这个方法是必须的，以满足文件对象的接口
        pass

def setup_logging(log_dir: Path):
    """配置日志，使其同时输出到控制台和文件"""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file_path = log_dir / f"backtest_run_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    # 1. 配置根 logger
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        handlers=[
                            logging.FileHandler(log_file_path, mode='w', encoding='utf-8'),
                            logging.StreamHandler(sys.__stdout__) # 使用原始 stdout
                        ])

    # 2. 重定向 stdout 和 stderr
    logger = logging.getLogger()
    sys.stdout = StreamToLogger(logger, logging.INFO)
    sys.stderr = StreamToLogger(logger, logging.ERROR)
    
    print(f"日志系统已启动。所有输出将被记录到: {log_file_path}")
    print("-" * 60)


# ==============================================================================
# --- 新增结束 ---
# ==============================================================================

def main():
    print("--- Running Backtest with Backtrader (Enhanced with Database Support) ---")
    print()
    
    # 配置数据源
    actual_use_db = configure_data_source(USE_DATABASE)
    
    if actual_use_db:
        print(f"✓ 将使用高性能数据库模式从 {DB_PATH.name} 加载数据")
    else:
        print(f"→ 使用传统CSV模式从 {PRICE_DATA_FILE.name} 加载数据")
    print()

    try:
        portfolios = load_portfolios(PORTFOLIO_FILE)
        rebalance_dates = sorted(portfolios.keys())
        if not rebalance_dates:
            print("[ERROR] No valid portfolio dates found in the excel file.")
            return

        start_date = rebalance_dates[0]
        end_date = rebalance_dates[-1] + datetime.timedelta(days=90)
        print(f"\n[INFO] Setting unified backtest period from {start_date} to {end_date}")

        all_portfolio_tickers = set().union(*(set(df['Ticker']) for df in portfolios.values()))
        all_needed_tickers = all_portfolio_tickers.union({SPY_TICKER})
        
        # 添加性能监控
        import time
        start_time = time.time()
        price_data_dict = load_all_price_data(PRICE_DATA_FILE, all_needed_tickers, start_date, end_date)
        load_time = time.time() - start_time
        print(f"\n[PERFORMANCE] 数据加载耗时: {load_time:.2f}秒")
        print(f"[PERFORMANCE] 加载了 {len(price_data_dict)} 只股票的数据")

    except (FileNotFoundError, ValueError) as e:
        # 使用 logging 记录错误
        logging.error(f"[ERROR] {e}. Please run the selection script first or check your data files.", exc_info=False)
        return
    except Exception as e:
        logging.error(f"[FATAL] An unhandled exception occurred during data loading: {e}", exc_info=True)
        return

    if SPY_TICKER not in price_data_dict:
        print(f"[ERROR] SPY Ticker '{SPY_TICKER}' not found in loaded price data. Cannot run benchmark.")
        return

    # --- 回测 1: 运行主策略 ---
    print("\n--- Running Main Strategy Backtest ---")
    cerebro_main = bt.Cerebro(stdstats=False)
    cerebro_main.addstrategy(PointInTimeStrategy, portfolios=portfolios)

    for ticker, df in price_data_dict.items():
        if ticker in all_needed_tickers:
            data_feed = bt.feeds.PandasData(dataname=df, name=ticker)
            cerebro_main.adddata(data_feed)
            
    cerebro_main.broker.setcash(INITIAL_CASH)
    cerebro_main.broker.setcommission(commission=0.001)
    
    cerebro_main.addobserver(bt.observers.Value)
    cerebro_main.addanalyzer(bt.analyzers.PyFolio, _name='pyfolio')
    cerebro_main.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', timeframe=bt.TimeFrame.Years)
    cerebro_main.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    
    main_results = cerebro_main.run()
    print("Main strategy backtest finished.")

    # --- 回测 2: 运行SPY基准策略 ---
    print("\n--- Running SPY Benchmark Backtest ---")
    cerebro_spy = bt.Cerebro(stdstats=False)
    cerebro_spy.addstrategy(BuyAndHoldSpy)
    
    spy_data_feed = bt.feeds.PandasData(dataname=price_data_dict[SPY_TICKER], name=SPY_TICKER)
    cerebro_spy.adddata(spy_data_feed)
    
    cerebro_spy.broker.setcash(INITIAL_CASH)
    cerebro_spy.broker.setcommission(commission=0.001)

    cerebro_spy.addanalyzer(bt.analyzers.PyFolio, _name='pyfolio')
    cerebro_spy.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', timeframe=bt.TimeFrame.Years)
    cerebro_spy.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    
    spy_results = cerebro_spy.run()
    print("SPY benchmark backtest finished.")

    # --- 打印结果 ---
    print("\n" + "="*50)
    print("      多因子选股策略 (Point-in-Time Strategy) 表现")
    print("="*50)
    if main_results: print_analysis(main_results[0].analyzers, INITIAL_CASH)

    print("\n" + "="*50)
    print("      买入并持有SPY (Buy & Hold SPY) 表现")
    print("="*50)
    if spy_results: print_analysis(spy_results[0].analyzers, INITIAL_CASH)
    print("="*50 + "\n")

    # --- 绘图 ---
    try:
        plot_path = OUTPUTS_DIR / 'backtrader_plot.png'
        print(f"Generating plot for the main strategy... saving to {plot_path}")
        fig = cerebro_main.plot(iplot=False, style='line', volume=False, plotind=False)[0][0]
        fig.savefig(plot_path, dpi=300)
        print("Plot saved successfully.")
    except Exception as e:
        logging.warning(f"Could not generate plot. Error: {e}")
        print("This might happen if you are running in an environment without a display backend.")

if __name__ == '__main__':
    # 在所有操作开始前，先设置好日志
    # 注意，日志文件的路径将基于 OUTPUTS_DIR
    setup_logging(log_dir=OUTPUTS_DIR / 'logs') 
    main()