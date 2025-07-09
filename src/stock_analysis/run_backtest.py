# src/stock_analysis/run_backtest.py

import pandas as pd
from pathlib import Path

# --- 路径配置 ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
OUTPUTS_DIR = PROJECT_ROOT / 'outputs'
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# --- 回测配置 ---
NUM_STOCKS_TO_SELECT = 50 # 确保这与选股脚本的配置一致
PORTFOLIO_FILE = OUTPUTS_DIR / f'point_in_time_backtest_top_{NUM_STOCKS_TO_SELECT}_stocks.xlsx'
TRANSACTION_LAG_DAYS = 2 # 交易延迟天数

def tidy_ticker(col: pd.Series) -> pd.Series:
    """统一清洗和格式化股票代码列。"""
    return col.astype('string').str.upper().str.strip().str.replace(r'_DELISTED$', '', regex=True).replace({'': pd.NA})

def load_portfolios(portfolio_path: Path) -> dict:
    """从Excel文件加载选股结果。"""
    print(f"Loading portfolios from: {portfolio_path}")
    if not portfolio_path.exists():
        print(f"[ERROR] Portfolio file not found. Please run the selection script first.")
        return {}
    
    # pd.read_excel(None) 读取所有sheet到一个字典
    xls = pd.read_excel(portfolio_path, sheet_name=None)
    
    # 将sheet name (字符串) 转换回日期对象
    portfolios = {pd.to_datetime(date_str).date(): df for date_str, df in xls.items()}
    print(f"Successfully loaded {len(portfolios)} portfolios.")
    return portfolios

def load_price_data(data_dir: Path) -> pd.DataFrame:
    """加载并处理日频价格数据。"""
    print("Loading and processing daily price data...")
    try:
        price_path = data_dir / 'us-shareprices-daily.csv'
        if not price_path.exists():
            price_path = data_dir / 'us-shareprices-daily.txt'
        
        px = pd.read_csv(price_path, sep=';')
        px['Date'] = pd.to_datetime(px['Date'])
        px['Ticker'] = tidy_ticker(px['Ticker'])
        px.dropna(subset=['Ticker'], inplace=True)
        px.drop_duplicates(subset=['Date', 'Ticker'], keep='last', inplace=True)
        
        price_wide = px.pivot(index='Date', columns='Ticker', values='Adj. Close')
        print(f"Price data loaded. Shape: {price_wide.shape}")
        return price_wide
    except Exception as e:
        print(f"[ERROR] Failed to load or process price data: {e}")
        return pd.DataFrame()

def run_price_backtest(portfolios: dict, price_df: pd.DataFrame, lag_days: int) -> pd.DataFrame:
    """根据选股结果和价格计算投资组合收益率。"""
    print("Calculating portfolio returns...")
    all_returns = []
    portfolio_dates = sorted(portfolios.keys())

    for i in range(len(portfolio_dates) - 1):
        start_date = portfolio_dates[i]
        end_date = portfolio_dates[i+1]
        
        current_portfolio = portfolios[start_date]
        candidate_tickers = current_portfolio['Ticker'].tolist()
        
        available_tickers = [t for t in candidate_tickers if t in price_df.columns]
        if not available_tickers: continue
        
        trade_start_date = pd.to_datetime(start_date) + pd.Timedelta(days=lag_days)
        trade_end_date = pd.to_datetime(end_date) - pd.Timedelta(days=1)

        try:
            entry_price_date = price_df.index[price_df.index >= trade_start_date][0]
            exit_price_date = price_df.index[price_df.index <= trade_end_date][-1]
        except IndexError:
            continue

        entry_prices = price_df.loc[entry_price_date, available_tickers]
        exit_prices = price_df.loc[exit_price_date, available_tickers]
        
        combined_prices = pd.DataFrame({'entry': entry_prices, 'exit': exit_prices}).dropna()
        if combined_prices.empty: continue
        
        period_returns = (combined_prices['exit'] / combined_prices['entry']) - 1
        portfolio_return = period_returns.mean()
        
        all_returns.append({'date': end_date, 'return': portfolio_return})

    if not all_returns:
        print("[WARNING] Could not calculate any returns.")
        return pd.DataFrame()

    df_returns = pd.DataFrame(all_returns).set_index('date')
    df_returns['cumulative_return'] = (1 + df_returns['return']).cumprod()
    return df_returns

# --- Main Logic for Backtest Script ---
def main():
    """
    独立运行价格回测的脚本。
    """
    print("--- Running Price Backtest Script ---")
    
    # 1. 加载选股结果
    portfolios = load_portfolios(PORTFOLIO_FILE)
    if not portfolios:
        return

    # 2. 加载价格数据
    price_wide = load_price_data(DATA_DIR)
    if price_wide.empty:
        return

    # 3. 运行价格回测
    df_returns = run_price_backtest(portfolios, price_wide, TRANSACTION_LAG_DAYS)

    # 4. 保存收益率结果
    if not df_returns.empty:
        returns_csv_path = OUTPUTS_DIR / 'portfolio_returns.csv'
        df_returns.to_csv(returns_csv_path)
        print(f"\nBacktest complete. Returns data saved to:\n{returns_csv_path}")
        
        # 可选的绘图逻辑
        # try: ... except: ...
    else:
        print("\nBacktest finished, but no returns were calculated.")

if __name__ == "__main__":
    main()