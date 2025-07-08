import pandas as pd
import numpy as np
from scipy.stats import zscore
from pathlib import Path
from dateutil.relativedelta import relativedelta

# --- 路径配置 ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
OUTPUTS_DIR = PROJECT_ROOT / 'outputs'
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# --- 回测配置 ---
BACKTEST_FREQUENCY = 'QE'  # 'QE' for quarterly, 'M' for monthly
ROLLING_WINDOW_YEARS = 5  # 使用过去5年的数据进行滚动平均
NUM_STOCKS_TO_SELECT = 50
OUTPUT_FILE = f'point_in_time_backtest_top_{NUM_STOCKS_TO_SELECT}_stocks.xlsx'

# --- 因子配置  ---
FACTOR_WEIGHTS = {'cfo': 1, 'ceq': 1, 'txt': 1, 'd_txt': 1, 'd_at': -1, 'd_rect': -1}

# --- Helper Functions ---
def load_and_merge_financial_data(data_dir: Path) -> pd.DataFrame:
    """
    从本地CSV文件加载、清洗和合并财务数据。
    明确使用 'Publish Date' 作为Point-in-Time的依据。
    """
    print(f"Loading financial data from local CSV files in: {data_dir}")
    bs_path = data_dir / 'us-balance-ttm.csv'
    cf_path = data_dir / 'us-cashflow-ttm.csv'
    is_path = data_dir / 'us-income-ttm.csv'

    try:
        df_bs = pd.read_csv(bs_path, sep=';')
        df_cf = pd.read_csv(cf_path, sep=';')
        df_is = pd.read_csv(is_path, sep=';')
        print("Successfully loaded balance sheet, cash flow, and income statement files.")
    except FileNotFoundError as e:
        print(f"Error: Could not find financial data files in '{data_dir}'. {e}")
        print("Please check if the PROJECT_ROOT definition at the top of the script correctly points to your project's root directory.")
        return pd.DataFrame()

    def clean_dataframe(df):
        # 明确使用 'Publish Date' 作为我们判断信息是否"已知"的唯一时间戳
        df.rename(columns={'Publish Date': 'date_known'}, inplace=True)
        df['date_known'] = pd.to_datetime(df['date_known'], errors='coerce')
        
        df.rename(columns={'Fiscal Year': 'year'}, inplace=True)
        numeric_cols = [col for col in df.columns if df[col].dtype == 'object' and col not in ['Ticker', 'Currency', 'Fiscal Period']]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 删除没有有效 'date_known' 的行
        return df.dropna(subset=['date_known', 'year']).astype({'year': 'int'})

    df_bs = clean_dataframe(df_bs)
    df_cf = clean_dataframe(df_cf)
    df_is = clean_dataframe(df_is)
    
    # 为了保证合并的是完全相同的报告（对应相同的发布日期），将 'date_known' 加入合并键
    merge_keys = ['Ticker', 'year', 'date_known'] 
    
    # 选择需要的列，确保 'date_known' 包含在内
    df_cf_subset = df_cf[['Ticker', 'year', 'date_known', 'Net Cash from Operating Activities']]
    df_is_subset = df_is[['Ticker', 'year', 'date_known', 'Income Tax (Expense) Benefit, Net']]
    df_bs_subset = df_bs[['Ticker', 'year', 'date_known', 'Total Equity', 'Total Assets', 'Accounts & Notes Receivable']]
    
    # 重命名其他列
    df_bs_subset = df_bs_subset.rename(columns={'Total Equity': 'ceq', 'Total Assets': 'at', 'Accounts & Notes Receivable': 'rect'})
    df_cf_subset = df_cf_subset.rename(columns={'Net Cash from Operating Activities': 'cfo'})
    df_is_subset = df_is_subset.rename(columns={'Income Tax (Expense) Benefit, Net': 'txt'})

    # 使用新的 merge_keys 进行合并
    df_merged = pd.merge(df_bs_subset, df_is_subset, on=merge_keys, how='inner')
    df_final = pd.merge(df_merged, df_cf_subset, on=merge_keys, how='inner')
    
    # 按发布日期排序，如果同一财年有多次发布（如重述），保留最新的那次发布
    df_final = df_final.sort_values(['Ticker', 'year', 'date_known'], ascending=True)
    df_final = df_final.drop_duplicates(subset=['Ticker', 'year'], keep='last')

    # 数据清洗
    df_final.loc[df_final['at'] <= 0, 'at'] = np.nan
    df_final.loc[df_final['ceq'] <= 0, 'ceq'] = np.nan

    print(f"Merged data has {len(df_final)} rows, using 'Publish Date' as the point-in-time reference.")
    return df_final


# --- Main Logic ---
def calculate_factors_point_in_time(df: pd.DataFrame) -> pd.DataFrame:
    """
    为给定时间点的数据计算因子。
    """
    # 1. 计算变化量 (Deltas) - groupby().diff() 保证在每个股票内部计算
    df = df.sort_values(by=['Ticker', 'date_known']) # 必须排序以保证diff正确
    factor_components = list(FACTOR_WEIGHTS.keys())
    delta_features = [feat for feat in factor_components if feat.startswith('d_')]
    original_features = [feat.replace('d_', '') for feat in delta_features]
    
    for feat in original_features:
        df[f'd_{feat}'] = df.groupby('Ticker')[feat].diff()
        
    # 2. 清洗数据，删除无法计算因子的行
    df_cleaned = df.dropna(subset=factor_components).copy()
    if df_cleaned.empty:
        return pd.DataFrame()

    # 3. 标准化 (Z-score)
    df_zscores = pd.DataFrame(index=df_cleaned.index)
    for component in factor_components:
        df_zscores[f'z_{component}'] = zscore(df_cleaned[component])

    # 4. 计算最终因子分
    df_cleaned['factor_score'] = 0.0
    for component, weight in FACTOR_WEIGHTS.items():
        df_cleaned['factor_score'] += df_zscores[f'z_{component}'] * weight
        
    return df_cleaned[['Ticker', 'date_known', 'year', 'factor_score']]

def run_backtest(df_financials: pd.DataFrame, 
                 backtest_start: pd.Timestamp, 
                 backtest_end: pd.Timestamp, 
                 freq: str = BACKTEST_FREQUENCY):
    """
    执行基于滑动窗口和Point-in-Time数据的回测。
    """
    # 1. 生成回测日期序列
    backtest_dates = pd.date_range(start=backtest_start, end=backtest_end, freq=freq)
    
    all_period_portfolios = {}
    
    print("\n--- Starting Point-in-Time Backtest ---")
    print(f"Configuration: {backtest_start.date()} to {backtest_end.date()}, Freq: {freq}, Window: {ROLLING_WINDOW_YEARS} years")

    # 2. 遍历每个回测日期
    for i, current_date in enumerate(backtest_dates):
        print(f"\nProcessing backtest for date: {current_date.date()} ({i+1}/{len(backtest_dates)})")
        
        # 3. 筛选在当前回测日期 "已知" 的所有数据
        known_data = df_financials[df_financials['date_known'] <= current_date].copy()
        if known_data.empty:
            print("  -> No data available for this period. Skipping.")
            continue

        # 4. 先计算所有已知数据的因子，包括差分
        #    这样可以确保即使一只股票只有两期数据，也能算出有效的差分值
        known_data_with_factors = calculate_factors_point_in_time(known_data)
        if known_data_with_factors.empty:
            print("  -> No valid data to calculate scores for this period after initial calculation. Skipping.")
            continue

        # 5. 对于每只股票，只保留其最新的 "已知" 报告 (Point-in-Time关键步骤)
        #    此时差分特征已经计算完毕，不会因为 tail(1) 而丢失
        latest_scores = (
            known_data_with_factors
            .sort_values('date_known')
            .groupby('Ticker', as_index=False)
            .tail(1)
        )

        if latest_scores.empty:
            print("  -> No stocks with valid scores after selecting latest. Skipping.")
            continue

        # 6. 使用滑动窗口聚合历史得分，以获得更稳健的排名
        window_start_date = current_date - relativedelta(years=ROLLING_WINDOW_YEARS)
        historical_window_scores = known_data_with_factors[
            known_data_with_factors['date_known'] >= window_start_date
        ]

        if historical_window_scores.empty:
            print("  -> Not enough historical data in the window. Skipping.")
            continue

        # 按股票聚合，计算滑动窗口内的平均分
        df_agg_scores = historical_window_scores.groupby('Ticker')['factor_score'].agg(['mean', 'count'])
        df_agg_scores.rename(columns={'mean': 'avg_factor_score_5y', 'count': 'num_reports_5y'}, inplace=True)

        # 7. 排序和选股
        df_ranked = df_agg_scores.sort_values(by='avg_factor_score_5y', ascending=False)
        
        # 8. 选出排名前N的股票
        top_stocks = df_ranked.head(NUM_STOCKS_TO_SELECT)
        
        print(f"  -> Selected {len(top_stocks)} stocks for the period starting {current_date.date()}.")
        # 9. 存储当期选股结果
        all_period_portfolios[current_date.date()] = top_stocks.reset_index()

    return all_period_portfolios


def run_price_backtest(portfolios: dict, price_df: pd.DataFrame, lag_days: int = 2):
    """
    根据选股结果和日频价格数据，计算投资组合的收益率。
    """
    print("\n--- Running Price-Based Backtest ---")
    all_returns = []
    
    # 获取所有调仓日期
    portfolio_dates = sorted(portfolios.keys())

    for i in range(len(portfolio_dates) - 1):
        start_date = portfolio_dates[i]
        end_date = portfolio_dates[i+1]
        
        # 1. 获取当期持仓
        current_portfolio = portfolios[start_date]
        tickers = current_portfolio['Ticker'].tolist()
        
        # 2. 确定实际的建仓日和平仓日
        # 建仓日：调仓日之后 lag_days 个交易日
        # 平仓日：下一个调仓日的前一个交易日
        trade_start_date = pd.to_datetime(start_date) + pd.Timedelta(days=lag_days)
        trade_end_date = pd.to_datetime(end_date) - pd.Timedelta(days=1)

        # 找到价格数据中实际对应的日期
        try:
            entry_price_date = price_df.index[price_df.index >= trade_start_date][0]
            exit_price_date = price_df.index[price_df.index <= trade_end_date][-1]
        except IndexError:
            print(f"  -> Could not find valid trading dates between {trade_start_date.date()} and {trade_end_date.date()}. Skipping period.")
            continue

        # 3. 获取建仓价和平仓价
        entry_prices = price_df.loc[entry_price_date, tickers].dropna()
        exit_prices = price_df.loc[exit_price_date, tickers].dropna()
        
        # 对齐股票池，以防有股票在期间退市或数据缺失
        common_tickers = entry_prices.index.intersection(exit_prices.index)
        if len(common_tickers) == 0:
            print(f"  -> No common stocks with valid prices for period {start_date}. Skipping.")
            continue
            
        entry_prices = entry_prices[common_tickers]
        exit_prices = exit_prices[common_tickers]

        # 4. 计算等权回报率
        period_returns = (exit_prices / entry_prices) - 1
        portfolio_return = period_returns.mean()
        
        all_returns.append({'date': end_date, 'return': portfolio_return})
        print(f"  -> Period {start_date} to {end_date}: Portfolio Return = {portfolio_return:.4f}")

    if not all_returns:
        print("Could not calculate any returns.")
        return pd.DataFrame()

    # 5. 计算累计收益曲线
    df_returns = pd.DataFrame(all_returns).set_index('date')
    df_returns['cumulative_return'] = (1 + df_returns['return']).cumprod()
    return df_returns


def main():
    # 1. 加载并合并财报
    df_financials = load_and_merge_financial_data(DATA_DIR)
    if df_financials.empty:
        print("Could not load financial data. Exiting.")
        return

    # 2. 动态确定回测区间
    earliest_known = df_financials['date_known'].min().normalize()
    latest_known = df_financials['date_known'].max().normalize()
    
    backtest_start_date = earliest_known + pd.DateOffset(years=ROLLING_WINDOW_YEARS)
    backtest_end_date = latest_known

    # 3. 运行基于基本面的滚动选股
    portfolios = run_backtest(df_financials, 
                              backtest_start=backtest_start_date, 
                              backtest_end=backtest_end_date)

    # 4. 保存详细选股结果到Excel
    if portfolios:
        with pd.ExcelWriter(OUTPUTS_DIR / OUTPUT_FILE) as writer:
            for date, df_portfolio in portfolios.items():
                sheet_name = str(date)
                df_portfolio.to_excel(writer, sheet_name=sheet_name, index=False)
        print(f"\nPoint-in-time backtest results saved to {OUTPUTS_DIR / OUTPUT_FILE}")
    else:
        print("\nNo portfolios were generated during the fundamental backtest.")
        return

    # 5. 加载日频股价数据
    try:
        price_path = DATA_DIR / 'us-shareprices-daily.csv'
        if not price_path.exists():
             price_path = DATA_DIR / 'us-shareprices-daily.txt' # 兼容示例文件
        px = pd.read_csv(price_path, sep=';')
        px['Date'] = pd.to_datetime(px['Date'])
        price_wide = px.pivot(index='Date', columns='Ticker', values='Adj. Close')
        print(f"Successfully loaded and pivoted price data. Shape: {price_wide.shape}")
    except FileNotFoundError:
        print(f"Price data not found in {DATA_DIR}. Skipping price backtest.")
        return

    # 6. 运行价格回测
    df_returns = run_price_backtest(portfolios, price_wide)

    # 7. 保存收益率结果
    if not df_returns.empty:
        returns_csv_path = OUTPUTS_DIR / 'portfolio_returns.csv'
        df_returns.to_csv(returns_csv_path)
        print(f"Portfolio returns saved to {returns_csv_path}")

        # 可选：绘制收益曲线图 (依赖 simplifed_backtesting.py)
        try:
            from simplifed_backtesting import plot_backtest_results
            plot_backtest_results(df_returns, None, f'Factor Strategy Cumulative Returns', OUTPUTS_DIR / 'cumulative_returns.png')
            print(f"Cumulative return plot saved to {OUTPUTS_DIR / 'cumulative_returns.png'}")
        except ImportError:
            print("Skipping plot generation: `simplifed_backtesting.py` not found or has issues.")


if __name__ == "__main__":
    main()