import backtrader as bt
import pandas as pd
from pathlib import Path
import datetime
import sqlite3
import logging
import sys

# --- 路径配置 ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
OUTPUTS_DIR = PROJECT_ROOT / 'outputs'
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# --- 回测配置 ---
NUM_STOCKS_TO_SELECT = 50
PORTFOLIO_FILE = OUTPUTS_DIR / f'point_in_time_backtest_top_{NUM_STOCKS_TO_SELECT}_stocks.xlsx'

# --- 数据库配置 ---
DB_PATH = DATA_DIR / 'financial_data.db'

INITIAL_CASH = 1_000_000.0
SPY_TICKER = 'SPY'

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
        print(f"[ERROR] 数据库文件不存在: {db_path}", file=sys.stderr)
        print("[ERROR] 请先运行 'tools/load_data_to_db.py' 创建数据库", file=sys.stderr)
        sys.exit(1)
    
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
        
        data_feeds = {}
        # 将SPY数据添加到feeds中
        data_feeds[SPY_TICKER] = bt.feeds.PandasData(dataname=spy_df, name=SPY_TICKER)

        # 处理其他股票
        for ticker, group in all_data.groupby('Ticker'):
            if ticker == SPY_TICKER:
                continue
            
            group = group.set_index('Date')
            # 对齐到主时间线
            aligned_df = group.reindex(master_index).fillna(method='ffill')
            aligned_df.loc[:, ['Open', 'High', 'Low', 'Close', 'Volume', 'Dividend']] = aligned_df.loc[:, ['Open', 'High', 'Low', 'Close', 'Volume', 'Dividend']].ffill()
            aligned_df.loc[:, 'Volume'] = aligned_df['Volume'].fillna(0)
            aligned_df.loc[:, 'Dividend'] = aligned_df['Dividend'].fillna(0)

            if not aligned_df.empty and not aligned_df['Close'].isnull().all():
                data_feeds[ticker] = bt.feeds.PandasData(dataname=aligned_df, name=ticker)

        print(f"Loaded data for {len(data_feeds)} tickers.")
        return data_feeds

    finally:
        con.close()

def setup_logging():
    """
    配置日志记录，将标准输出重定向到文件和控制台。
    """
    log_file = OUTPUTS_DIR / 'backtest_log.txt'
    
    # 清空旧的日志文件
    if log_file.exists():
        log_file.unlink()
        
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    print(f"日志将记录到: {log_file}")

def run_backtest(data_feeds: dict, portfolios: dict, initial_cash: float):
    """
    运行主要的回测策略。
    """
    print("\n--- Running Point-in-Time Strategy ---")
    cerebro = bt.Cerebro()
    cerebro.broker.set_cash(initial_cash)

    for name, data in data_feeds.items():
        cerebro.adddata(data, name=name)

    cerebro.addstrategy(PointInTimeStrategy, portfolios=portfolios)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')

    results = cerebro.run()
    final_value = cerebro.broker.getvalue()
    print(f'\n--- Backtest Results ---')
    print(f'Final Portfolio Value: {final_value:,.2f}')
    
    # 提取分析结果
    strat = results[0]
    sharpe_ratio = strat.analyzers.sharpe.get_analysis().get('sharperatio', float('nan'))
    max_drawdown = strat.analyzers.drawdown.get_analysis().max.drawdown
    total_return = strat.analyzers.returns.get_analysis().get('rtot', float('nan'))
    
    print(f'Sharpe Ratio: {sharpe_ratio:.2f}')
    print(f'Max Drawdown: {max_drawdown:.2f}%')
    print(f'Total Return: {total_return*100:.2f}%')
    print('--- End of Backtest ---')

def run_spy_benchmark_strategy(spy_data_feed, start_date, end_date):
    """
    运行买入并持有SPY的基准策略。
    """
    print("\n--- Running Buy and Hold SPY Benchmark ---")
    cerebro = bt.Cerebro()
    cerebro.broker.set_cash(INITIAL_CASH)
    cerebro.adddata(spy_data_feed, name=SPY_TICKER)
    cerebro.addstrategy(BuyAndHoldSpy)
    cerebro.run()
    final_value = cerebro.broker.getvalue()
    print(f'Final SPY Portfolio Value: {final_value:,.2f}')
    print('--- End of SPY Benchmark ---')

def main(run_spy_benchmark=True):
    """
    主函数，用于运行回测。
    """
    print("--- Running Backtest with Backtrader (Database Mode) ---")
    
    try:
        portfolios = load_portfolios(PORTFOLIO_FILE)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    if not portfolios:
        print("[INFO] No portfolios found. Exiting.")
        return

    print(f"✓ Loaded {len(portfolios)} portfolio snapshots.")

    all_needed_tickers = set([SPY_TICKER])
    for df in portfolios.values():
        all_needed_tickers.update(tidy_ticker(df['Ticker']).dropna())

    start_date = min(portfolios.keys())
    end_date = max(portfolios.keys()) + datetime.timedelta(days=365)

    print(f"Date range for backtest: {start_date} to {end_date}")
    print(f"Total unique tickers required: {len(all_needed_tickers)}")

    import time
    start_time = time.time()
    price_data_dict = load_all_price_data_from_db(DB_PATH, all_needed_tickers, start_date, end_date)
    load_time = time.time() - start_time
    print(f"\n[PERFORMANCE] 数据加载耗时: {load_time:.2f}秒")

    if not price_data_dict or SPY_TICKER not in price_data_dict:
        print("[ERROR] Price data could not be loaded or SPY data is missing. Exiting.", file=sys.stderr)
        sys.exit(1)

    run_backtest(price_data_dict, portfolios, initial_cash=INITIAL_CASH)

    if run_spy_benchmark:
        spy_data_feed = price_data_dict.get(SPY_TICKER)
        if spy_data_feed:
            run_spy_benchmark_strategy(spy_data_feed, start_date, end_date)
        else:
            print("[WARNING] SPY data not found, cannot run benchmark.")

if __name__ == '__main__':
    # 配置日志
    setup_logging()
    main()