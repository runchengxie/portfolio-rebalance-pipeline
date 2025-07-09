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
SPY_TICKER = 'SPY' # 假设您的价格数据中有SPY作为基准

# --- Backtrader 策略 ---
class PointInTimeStrategy(bt.Strategy):
    """
    根据预先计算好的调仓信号进行等权重调仓的策略。
    """
    params = (
        ('portfolios', None), # 接收选股结果的字典
    )

    def __init__(self):
        self.rebalance_dates = sorted(self.p.portfolios.keys())
        self.next_rebalance_idx = 0
        self.get_next_rebalance_date()

    def log(self, txt, dt=None):
        """策略的日志记录功能"""
        dt = dt or self.datas[0].datetime.date(0)
        print(f'{dt.isoformat()} - {txt}')

    def get_next_rebalance_date(self):
        """获取下一个调仓日期"""
        if self.next_rebalance_idx < len(self.rebalance_dates):
            self.next_rebalance_date = self.rebalance_dates[self.next_rebalance_idx]
        else:
            self.next_rebalance_date = None # 没有更多调仓日了

    def next(self):
        """每个bar（通常是每天）都会调用此方法"""
        current_date = self.datas[0].datetime.date(0)

        # 检查是否到达或超过了调仓日
        if self.next_rebalance_date and current_date >= self.next_rebalance_date:
            self.log(f'--- Rebalancing on {current_date} for signal date {self.next_rebalance_date} ---')
            
            # 1. 获取新的目标股票列表
            target_tickers_df = self.p.portfolios[self.next_rebalance_date]
            target_tickers = set(target_tickers_df['Ticker'])
            
            # 获取所有可用的数据feed及其对应的ticker
            available_data_tickers = {d._name for d in self.datas if d._name != SPY_TICKER}
            
            # 过滤出在数据源中存在的股票
            final_target_tickers = target_tickers.intersection(available_data_tickers)
            if not final_target_tickers:
                self.log("Warning: No target tickers are available in the price data for this period.")
                # 更新到下一个调仓日
                self.next_rebalance_idx += 1
                self.get_next_rebalance_date()
                return

            # 2. 卖出不再持有的股票
            for data in self.datas:
                ticker = data._name
                if ticker != SPY_TICKER and self.getposition(data).size > 0:
                    if ticker not in final_target_tickers:
                        self.log(f'Closing position in {ticker}')
                        self.order_target_percent(data=data, target=0.0)

            # 3. 为新的目标股票组合分配资金（等权重）
            target_percent = 1.0 / len(final_target_tickers)
            for data in self.datas:
                ticker = data._name
                if ticker in final_target_tickers:
                    self.log(f'Setting target position for {ticker} to {target_percent:.2%}')
                    self.order_target_percent(data=data, target=target_percent)
            
            # 4. 更新到下一个调仓日期
            self.next_rebalance_idx += 1
            self.get_next_rebalance_date()
            self.log('--- Rebalancing Complete ---')

class BuyAndHoldSpy(bt.Strategy):
    """一个简单的买入并持有SPY的基准策略"""
    def start(self):
        self.spy = self.datas[0] # 假设SPY是第一个传入的数据
        self.order_target_percent(data=self.spy, target=0.99) # 几乎全部买入

    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        # print(f'{dt.isoformat()} - SPY - {txt}') # 可以取消注释来查看SPY策略的日志

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
    """加载所有需要的股票价格数据，并按ticker分组"""
    print("Loading and preparing all price data...")
    px = pd.read_csv(price_path, sep=';', parse_dates=['Date'])
    px['Ticker'] = tidy_ticker(px['Ticker'])
    px.dropna(subset=['Ticker', 'Date', 'Adj. Close'], inplace=True)
    px.set_index('Date', inplace=True)
    
    # Backtrader需要'open', 'high', 'low', 'close', 'volume'列
    # 如果没有，用'Adj. Close'填充
    for col in ['Open', 'High', 'Low', 'Close', 'Volume', 'Dividend']:
        if col not in px.columns:
            if col in ['Open', 'High', 'Low', 'Close']:
                px[col] = px['Adj. Close']
            elif col == 'Volume':
                px[col] = 0
            elif col == 'Dividend':
                px[col] = 0.0

    # 重命名列以符合backtrader标准
    px.rename(columns={
        'Open': 'open', 'High': 'high', 'Low': 'low',
        'Adj. Close': 'close', # 使用调整后收盘价作为'close'
        'Volume': 'volume', 'Dividend': 'dividend'
    }, inplace=True)
    
    px['openinterest'] = 0 # backtrader需要这一列

    data_feeds = {}
    for ticker in all_needed_tickers:
        df_ticker = px[px['Ticker'] == ticker][['open', 'high', 'low', 'close', 'volume', 'dividend', 'openinterest']].sort_index()
        if not df_ticker.empty:
            data_feeds[ticker] = df_ticker
            
    print(f"Loaded price data for {len(data_feeds)} tickers.")
    return data_feeds

def print_analysis(analyzers):
    """打印分析器的结果 (修正版)"""
    # 首先从分析器集合中获取名为 'returns' 的具体分析器
    returns_analyzer = analyzers.returns
    
    # 现在从这个具体的分析器中获取投资组合价值
    total_open = returns_analyzer.portfolio.startingvalue
    total_close = returns_analyzer.portfolio.endingvalue
    total_return = (total_close - total_open) / total_open if total_open != 0 else 0
    
    # 同样，从正确的分析器获取日期
    try:
        num_years = (returns_analyzer.portfolio.last_dt - returns_analyzer.portfolio.first_dt).days / 365.25
        annual_return = (1 + total_return) ** (1/num_years) - 1 if num_years > 0 else 0
    except Exception:
        num_years = 0
        annual_return = 0

    print(f'期初价值: {total_open:,.2f}')
    print(f'期末价值: {total_close:,.2f}')
    print(f'总回报率: {total_return:.2%}')
    if num_years > 0:
        print(f'年化回报率: {annual_return:.2%}')
    
    # 其他分析器的访问方式是正确的，因为它们是通过名字从集合中访问的
    if analyzers.sharpe and hasattr(analyzers.sharpe, 'sharperatio') and analyzers.sharpe.sharperatio is not None:
        print(f'夏普比率 (年化): {analyzers.sharpe.sharperatio:.2f}')
    if analyzers.drawdown and hasattr(analyzers.drawdown, 'max') and analyzers.drawdown.max.drawdown is not None:
        print(f'最大回撤: {analyzers.drawdown.max.drawdown:.2%}')
        print(f'最大回撤周期 (天): {analyzers.drawdown.max.len}')

# --- 主逻辑 ---
def main():
    print("--- Running Backtest with Backtrader ---")

    # 1. 加载选股信号
    try:
        portfolios = load_portfolios(PORTFOLIO_FILE)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}. Please run the selection script first.")
        return
        
    all_portfolio_tickers = set().union(*(set(df['Ticker']) for df in portfolios.values()))
    all_needed_tickers = all_portfolio_tickers.union({SPY_TICKER})

    # 2. 加载所有需要的价格数据
    price_data_dict = load_all_price_data(PRICE_DATA_FILE, all_needed_tickers)
    
    if SPY_TICKER not in price_data_dict:
        print(f"[ERROR] SPY Ticker '{SPY_TICKER}' not found in the price data. Cannot run benchmark.")
        return

    # 3. 创建Cerebro引擎
    cerebro = bt.Cerebro(stdstats=False) # 我们将用自己的分析器

    # 4. 添加策略
    cerebro.addstrategy(PointInTimeStrategy, portfolios=portfolios)
    cerebro.addstrategy(BuyAndHoldSpy)

    # 5. 添加数据到Cerebro
    # 确保SPY是第一个，这样BuyAndHoldSpy策略才能正确引用
    spy_df = price_data_dict.pop(SPY_TICKER)
    spy_data_feed = bt.feeds.PandasData(dataname=spy_df, name=SPY_TICKER)
    cerebro.adddata(spy_data_feed)

    for ticker, df in price_data_dict.items():
        if ticker in all_portfolio_tickers:
            data_feed = bt.feeds.PandasData(dataname=df, name=ticker)
            cerebro.adddata(data_feed)
            
    # 6. 配置引擎
    cerebro.broker.setcash(INITIAL_CASH)
    cerebro.broker.setcommission(commission=0.001) # 设置0.1%的佣金

    # 7. 添加分析器和观察器
    cerebro.addobserver(bt.observers.Broker)
    cerebro.addobserver(bt.observers.Trades)
    cerebro.addobserver(bt.observers.Value)
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', timeframe=bt.TimeFrame.Years)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.PyFolio, _name='pyfolio')

    # 8. 运行回测
    print("\nRunning backtest...")
    results = cerebro.run()
    print("Backtest finished.")

    # 9. 打印结果
    print("\n" + "="*40)
    print("      多因子选股策略 (Point-in-Time Strategy) 表现")
    print("="*40)
    print_analysis(results[0].analyzers)

    print("\n" + "="*40)
    print("      买入并持有SPY (Buy & Hold SPY) 表现")
    print("="*40)
    print_analysis(results[1].analyzers)
    print("="*40 + "\n")

    # 10. 绘图
    try:
        plot_path = OUTPUTS_DIR / 'backtrader_plot.png'
        print(f"Generating plot... saving to {plot_path}")
        # cerebro.plot(style='candlestick', barup='green', bardown='red')
        fig = cerebro.plot(iplot=False, style='line', volume=False)[0][0]
        fig.savefig(plot_path, dpi=300)
        print("Plot saved successfully.")
    except Exception as e:
        print(f"[WARNING] Could not generate plot. Error: {e}")
        print("This might happen if you are running in an environment without a display backend.")

if __name__ == '__main__':
    main()