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
BACKTEST_START_DATE = '2018-01-01'
BACKTEST_END_DATE = '2023-12-31'
BACKTEST_FREQUENCY = 'Q'  # 'Q' for quarterly, 'M' for monthly
ROLLING_WINDOW_YEARS = 5  # 使用过去5年的数据进行滚动平均
NUM_STOCKS_TO_SELECT = 50
OUTPUT_FILE = f'point_in_time_backtest_top_{NUM_STOCKS_TO_SELECT}_stocks.xlsx'

# --- 因子配置  ---
FACTOR_WEIGHTS = {'cfo': 1, 'ceq': 1, 'txt': 1, 'd_txt': 1, 'd_at': -1, 'd_rect': -1}

# --- Helper Functions ---
def load_and_merge_financial_data(data_dir: Path) -> pd.DataFrame:
    """
    从本地CSV文件加载、清洗和合并财务数据。
    (此函数保持不变)
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
        # 使用 'Publish Date' 如果存在, 否则用 'Report Date'
        # 这里我们统一使用 'Report Date' 作为已知时间的依据
        date_col = 'Publish Date' if 'Publish Date' in df.columns else 'Report Date'
        df.rename(columns={date_col: 'date_known'}, inplace=True)
        df['date_known'] = pd.to_datetime(df['date_known'], errors='coerce')
        
        df.rename(columns={'Fiscal Year': 'year'}, inplace=True)
        numeric_cols = [col for col in df.columns if df[col].dtype == 'object' and col not in ['Ticker', 'Currency', 'Fiscal Period']]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        return df.dropna(subset=['date_known', 'year']).astype({'year': 'int'})

    df_bs = clean_dataframe(df_bs)
    df_cf = clean_dataframe(df_cf)
    df_is = clean_dataframe(df_is)
    
    # 注意: 为了保证数据一致性, 合并键应包含 'year' 和 'date_known'
    merge_keys = ['Ticker', 'year', 'date_known']
    df_cf_subset = df_cf[['Ticker', 'year', 'date_known', 'Net Cash from Operating Activities']]
    df_is_subset = df_is[['Ticker', 'year', 'date_known', 'Income Tax (Expense) Benefit, Net']]
    df_bs_subset = df_bs[['Ticker', 'year', 'date_known', 'Total Equity', 'Total Assets', 'Accounts & Notes Receivable']]
    
    df_bs_subset = df_bs_subset.rename(columns={'Total Equity': 'ceq', 'Total Assets': 'at', 'Accounts & Notes Receivable': 'rect'})
    df_cf_subset = df_cf_subset.rename(columns={'Net Cash from Operating Activities': 'cfo'})
    df_is_subset = df_is_subset.rename(columns={'Income Tax (Expense) Benefit, Net': 'txt'})

    df_merged = pd.merge(df_bs_subset, df_is_subset, on=merge_keys, how='inner')
    df_final = pd.merge(df_merged, df_cf_subset, on=merge_keys, how='inner')
    
    # 按报告日期排序, 确保 diff() 计算是时序正确的
    df_final = df_final.sort_values(['Ticker', 'date_known'], ascending=True)
    df_final = df_final.drop_duplicates(subset=['Ticker', 'year'], keep='last') # 保留同一年份最新的报告

    df_final.loc[df_final['at'] <= 0, 'at'] = np.nan
    df_final.loc[df_final['ceq'] <= 0, 'ceq'] = np.nan

    print(f"Merged data has {len(df_final)} rows.")
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

def run_backtest(df_financials: pd.DataFrame):
    """
    执行基于滑动窗口和Point-in-Time数据的回测。
    """
    # 1. 生成回测日期序列
    backtest_dates = pd.date_range(start=BACKTEST_START_DATE, end=BACKTEST_END_DATE, freq=BACKTEST_FREQUENCY)
    
    all_period_portfolios = {}
    
    print("\n--- Starting Point-in-Time Backtest ---")
    print(f"Configuration: {BACKTEST_START_DATE} to {BACKTEST_END_DATE}, Freq: {BACKTEST_FREQUENCY}, Window: {ROLLING_WINDOW_YEARS} years")

    # 2. 遍历每个回测日期
    for i, current_date in enumerate(backtest_dates):
        print(f"\nProcessing backtest for date: {current_date.date()} ({i+1}/{len(backtest_dates)})")
        
        # 3. 定义此时间点的滑动窗口
        window_start_date = current_date - relativedelta(years=ROLLING_WINDOW_YEARS)
        
        # 4. 筛选在当前回测日期 "已知" 的所有数据
        #    'date_known' <= current_date
        known_data = df_financials[df_financials['date_known'] <= current_date].copy()
        
        # 5. 对于每只股票，只保留其最新的 "已知" 报告 (Point-in-Time关键步骤)
        latest_known_data = known_data.sort_values('date_known').groupby('Ticker').tail(1)
        
        # 6. 计算这些最新报告的因子得分
        #    注意：这里的因子计算本身不涉及滑动窗口，而是基于单期财报
        df_scores_latest = calculate_factors_point_in_time(latest_known_data)
        if df_scores_latest.empty:
            print("  -> No valid data to calculate scores for this period. Skipping.")
            continue
            
        # 7. 使用滑动窗口聚合历史得分，以获得更稳健的排名
        #    - 获取窗口内的所有历史数据点
        historical_window_data = known_data[known_data['date_known'] >= window_start_date]
        #    - 计算这些历史数据点的因子分
        df_scores_historical = calculate_factors_point_in_time(historical_window_data)
        if df_scores_historical.empty:
            print("  -> Not enough historical data in the window. Skipping.")
            continue
        #    - 按股票聚合，计算滑动窗口内的平均分
        df_agg_scores = df_scores_historical.groupby('Ticker')['factor_score'].agg(['mean', 'count'])
        df_agg_scores.rename(columns={'mean': 'avg_factor_score_5y', 'count': 'num_reports_5y'}, inplace=True)
        
        # 8. 排序和选股
        df_ranked = df_agg_scores.sort_values(by='avg_factor_score_5y', ascending=False)
        
        # 9. 选出排名前N的股票
        top_stocks = df_ranked.head(NUM_STOCKS_TO_SELECT)
        
        print(f"  -> Selected {len(top_stocks)} stocks for the period starting {current_date.date()}.")
        # 10. 存储当期选股结果
        all_period_portfolios[current_date.date()] = top_stocks.reset_index()

    return all_period_portfolios


def main():
    # 1. 加载和预处理数据
    df_financials = load_and_merge_financial_data(DATA_DIR)
    if df_financials.empty:
        print("Could not load financial data. Exiting.")
        return
        
    # 2. 运行严谨的回测
    portfolios = run_backtest(df_financials)
    
    if not portfolios:
        print("\nBacktest finished but no portfolios were generated. Please check data and date ranges.")
        return

    # 3. 将回测结果保存到Excel，每个时期的选股结果放在一个单独的Sheet中
    output_path = OUTPUTS_DIR / OUTPUT_FILE
    try:
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            for date, df_portfolio in portfolios.items():
                sheet_name = str(date)
                df_portfolio.to_excel(writer, sheet_name=sheet_name, index=False)
        print(f"\nSuccessfully saved backtest results to '{output_path}'")
        print("Each sheet in the Excel file represents the selected portfolio for that quarter-end.")
    except Exception as e:
        print(f"\nError saving to Excel file: {e}")
        print("Please ensure you have 'openpyxl' installed (`pip install openpyxl`).")


if __name__ == "__main__":
    main()