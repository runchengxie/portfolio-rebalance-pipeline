import backtrader as bt
import pandas as pd
from pathlib import Path
import datetime

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
            
            for ticker in current_positions:
                if ticker not in final_target_tickers and ticker != SPY_TICKER:
                    data = self.getdatabyname(ticker)
                    self.log(f'Closing position in {ticker}')
                    self.order_target_percent(data=data, target=0.0)

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

def load_all_price_data(price_path: Path, all_needed_tickers: set) -> dict:
    print("Loading and preparing all price data...")
    px = pd.read_csv(price_path, sep=';', parse_dates=['Date'])
    px['Ticker'] = tidy_ticker(px['Ticker'])
    px.dropna(subset=['Ticker', 'Date', 'Adj. Close'], inplace=True)
    px.set_index('Date', inplace=True)
    
    for col in ['Open', 'High', 'Low', 'Close', 'Volume', 'Dividend']:
        if col not in px.columns:
            px[col] = px['Adj. Close'] if col in ['Open', 'High', 'Low', 'Close'] else 0
    if 'Dividend' not in px.columns: px['Dividend'] = 0.0

    px.rename(columns={
        'Open': 'open', 'High': 'high', 'Low': 'low',
        'Adj. Close': 'close', 'Volume': 'volume', 'Dividend': 'dividend'
    }, inplace=True)
    
    px['openinterest'] = 0

    data_feeds = {}
    for ticker in sorted(list(all_needed_tickers)):
        df_ticker = px[px['Ticker'] == ticker][['open', 'high', 'low', 'close', 'volume', 'dividend', 'openinterest']].sort_index()
        if not df_ticker.empty:
            data_feeds[ticker] = df_ticker
            if ticker == SPY_TICKER:
                print(f"  [INFO] SPY data loaded. Date range: {df_ticker.index.min().date()} to {df_ticker.index.max().date()}")
            
    print(f"Loaded price data for {len(data_feeds)} tickers.")
    return data_feeds

def print_analysis(analyzers, initial_cash):
    """打印分析器的结果"""
    pyfolio_analyzer = analyzers.pyfolio.get_analysis()
    returns_series = pd.Series(pyfolio_analyzer.get('returns', {}))
    total_open = initial_cash

    if not returns_series.empty:
        total_close = initial_cash * (1 + returns_series.cumsum().iloc[-1])
        total_return = (total_close - total_open) / total_open if total_open != 0 else 0.0
        num_years = len(returns_series) / 252
        annual_return = (1 + total_return) ** (1/num_years) - 1 if num_years > 0 else 0.0
    else:
        total_close, total_return, num_years, annual_return = total_open, 0.0, 0.0, 0.0

    print(f'期初价值: {total_open:,.2f}')
    print(f'期末价值: {total_close:,.2f}')
    print(f'总回报率: {total_return:.2%}')
    if num_years > 0:
        print(f'年化回报率: {annual_return:.2%}')
    
    # 修复: 使用属性访问分析器
    sharpe_analyzer = analyzers.sharpe
    if sharpe_analyzer:
        sharpe_ratio = sharpe_analyzer.get_analysis().get('sharperatio')
        if sharpe_ratio is not None:
             print(f'夏普比率 (年化): {sharpe_ratio:.2f}')

    drawdown_analyzer = analyzers.drawdown
    if drawdown_analyzer:
        dd_analysis = drawdown_analyzer.get_analysis()
        if dd_analysis.max.drawdown is not None:
            print(f'最大回撤: {dd_analysis.max.drawdown:.2%}')
            print(f'最大回撤周期 (天): {dd_analysis.max.len}')

# --- 主逻辑 ---
def main():
    print("--- Running Backtest with Backtrader ---")

    try:
        portfolios = load_portfolios(PORTFOLIO_FILE)
        all_portfolio_tickers = set().union(*(set(df['Ticker']) for df in portfolios.values()))
        all_needed_tickers = all_portfolio_tickers.union({SPY_TICKER})
        price_data_dict = load_all_price_data(PRICE_DATA_FILE, all_needed_tickers)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}. Please run the selection script first.")
        return

    if SPY_TICKER not in price_data_dict:
        print(f"[ERROR] SPY Ticker '{SPY_TICKER}' not found. Cannot run benchmark.")
        return

    # 修复: 确定统一的回测周期
    rebalance_dates = sorted(portfolios.keys())
    start_date = rebalance_dates[0]
    end_date = rebalance_dates[-1] + datetime.timedelta(days=90) # 假设一个季度后结束
    print(f"\n[INFO] Setting unified backtest period from {start_date} to {end_date}")

    # --- 回测 1: 运行主策略 ---
    print("\n--- Running Main Strategy Backtest ---")
    cerebro_main = bt.Cerebro(stdstats=False)
    cerebro_main.addstrategy(PointInTimeStrategy, portfolios=portfolios)

    # 添加所有需要的股票数据，并强制使用统一日期
    for ticker, df in price_data_dict.items():
        if ticker in all_needed_tickers:
            data_feed = bt.feeds.PandasData(dataname=df, fromdate=start_date, todate=end_date, name=ticker)
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
    
    # 只添加SPY的数据，并强制使用统一日期
    spy_data_feed = bt.feeds.PandasData(dataname=price_data_dict[SPY_TICKER], fromdate=start_date, todate=end_date, name=SPY_TICKER)
    cerebro_spy.adddata(spy_data_feed)
    
    cerebro_spy.broker.setcash(INITIAL_CASH)
    cerebro_spy.broker.setcommission(commission=0.001)

    cerebro_spy.addanalyzer(bt.analyzers.PyFolio, _name='pyfolio')
    cerebro_spy.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', timeframe=bt.TimeFrame.Years)
    cerebro_spy.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    
    spy_results = cerebro_spy.run()
    print("SPY benchmark backtest finished.")

    # --- 打印结果 ---
    print("\n" + "="*40)
    print("      多因子选股策略 (Point-in-Time Strategy) 表现")
    print("="*40)
    print_analysis(main_results[0].analyzers, INITIAL_CASH)

    print("\n" + "="*40)
    print("      买入并持有SPY (Buy & Hold SPY) 表现")
    print("="*40)
    print_analysis(spy_results[0].analyzers, INITIAL_CASH)
    print("="*40 + "\n")

    # --- 绘图 (只画主策略的图) ---
    try:
        plot_path = OUTPUTS_DIR / 'backtrader_plot.png'
        print(f"Generating plot for the main strategy... saving to {plot_path}")
        fig = cerebro_main.plot(iplot=False, style='line', volume=False, plotind=False)[0][0]
        fig.savefig(plot_path, dpi=300)
        print("Plot saved successfully.")
    except Exception as e:
        print(f"[WARNING] Could not generate plot. Error: {e}")
        print("This might happen if you are running in an environment without a display backend.")

if __name__ == '__main__':
    main()