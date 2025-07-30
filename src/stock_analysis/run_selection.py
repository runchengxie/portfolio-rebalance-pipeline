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

# --- 策略配置 ---
BACKTEST_FREQUENCY = 'QE'
ROLLING_WINDOW_YEARS = 5
NUM_STOCKS_TO_SELECT = 20
MIN_REPORTS_IN_WINDOW = 5
OUTPUT_FILE = OUTPUTS_DIR / f'point_in_time_backtest_top_{NUM_STOCKS_TO_SELECT}_stocks.xlsx'

# --- 因子配置 ---
FACTOR_WEIGHTS = {'cfo': 1, 'ceq': 1, 'txt': 1, 'd_txt': 1, 'd_at': -1, 'd_rect': -1}

# --- Helper Functions ---
def tidy_ticker(col: pd.Series) -> pd.Series:
    return col.astype('string').str.upper().str.strip().str.replace(r'_DELISTED$', '', regex=True).replace({'': pd.NA})

def clean_dataframe(df_raw: pd.DataFrame) -> pd.DataFrame:
    df = df_raw.copy()
    df['Ticker'] = tidy_ticker(df['Ticker'])
    df.rename(columns={'Publish Date': 'date_known', 'Fiscal Year': 'year'}, inplace=True)
    df['date_known'] = pd.to_datetime(df['date_known'], errors='coerce')
    numeric_cols = [c for c in df.columns if c not in ['Ticker', 'Currency', 'Fiscal Period', 'date_known']]
    df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors='coerce')
    df = df.dropna(subset=['Ticker', 'date_known', 'year'])
    df = df.astype({'year': 'int'})
    return df

def load_and_merge_financial_data(data_dir: Path) -> pd.DataFrame:
    print("Loading and merging financial data...")
    bs_path = data_dir / 'us-balance-ttm.csv'
    cf_path = data_dir / 'us-cashflow-ttm.csv'
    is_path = data_dir / 'us-income-ttm.csv'
    
    try:
        df_bs = clean_dataframe(pd.read_csv(bs_path, sep=';'))
        df_cf = clean_dataframe(pd.read_csv(cf_path, sep=';'))
        df_is = clean_dataframe(pd.read_csv(is_path, sep=';'))
    except FileNotFoundError as e:
        print(f"[ERROR] Could not find financial data files in '{data_dir}'. {e}")
        return pd.DataFrame()

    merge_keys = ['Ticker', 'year', 'date_known']
    df_cf_subset = df_cf[['Ticker', 'year', 'date_known', 'Net Cash from Operating Activities']].rename(columns={'Net Cash from Operating Activities': 'cfo'})
    df_is_subset = df_is[['Ticker', 'year', 'date_known', 'Income Tax (Expense) Benefit, Net']].rename(columns={'Income Tax (Expense) Benefit, Net': 'txt'})
    df_bs_subset = df_bs[['Ticker', 'year', 'date_known', 'Total Equity', 'Total Assets', 'Accounts & Notes Receivable']].rename(columns={'Total Equity': 'ceq', 'Total Assets': 'at', 'Accounts & Notes Receivable': 'rect'})

    df_merged = pd.merge(df_bs_subset, df_is_subset, on=merge_keys, how='inner')
    df_final = pd.merge(df_merged, df_cf_subset, on=merge_keys, how='inner')
    df_final = df_final.sort_values(['Ticker', 'year', 'date_known']).drop_duplicates(subset=['Ticker', 'year'], keep='last')
    
    df_final.loc[df_final['at'] <= 0, 'at'] = np.nan
    df_final.loc[df_final['ceq'] <= 0, 'ceq'] = np.nan
    
    print(f"Merged data has {len(df_final)} rows.")
    return df_final

def calculate_factors_point_in_time(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(by=['Ticker', 'date_known'])
    factor_components = list(FACTOR_WEIGHTS.keys())
    delta_features = [feat for feat in factor_components if feat.startswith('d_')]
    original_features = [feat.replace('d_', '') for feat in delta_features]
    
    for feat in original_features:
        df[f'd_{feat}'] = df.groupby('Ticker')[feat].diff()
        
    df_cleaned = df.dropna(subset=factor_components).copy()
    if df_cleaned.empty: return pd.DataFrame()

    df_zscores = pd.DataFrame(index=df_cleaned.index)
    for component in factor_components:
        df_zscores[f'z_{component}'] = zscore(df_cleaned[component])

    df_cleaned['factor_score'] = 0.0
    for component, weight in FACTOR_WEIGHTS.items():
        df_cleaned['factor_score'] += df_zscores[f'z_{component}'] * weight
        
    return df_cleaned[['Ticker', 'date_known', 'year', 'factor_score']]

def calc_factor_scores(df_financials: pd.DataFrame, as_of_date: pd.Timestamp, window_years: int, min_reports_required: int) -> pd.DataFrame:
    known_data = df_financials[df_financials['date_known'] <= as_of_date].copy()
    if known_data.empty: return pd.DataFrame()

    known_data_with_factors = calculate_factors_point_in_time(known_data)
    if known_data_with_factors.empty: return pd.DataFrame()

    window_start_date = as_of_date - relativedelta(years=window_years)
    historical_window_scores = known_data_with_factors[known_data_with_factors['date_known'] >= window_start_date]
    if historical_window_scores.empty: return pd.DataFrame()

    df_agg_scores = historical_window_scores.groupby('Ticker')['factor_score'].agg(['mean', 'count'])
    df_agg_scores.rename(columns={'mean': 'avg_factor_score', 'count': 'num_reports'}, inplace=True)

    # 只保留在窗口期内报告数量大于等于我们要求的最小数量的公司
    df_agg_scores = df_agg_scores[df_agg_scores['num_reports'] >= min_reports_required]

    return df_agg_scores

# --- Main Logic for Selection Script ---
def main():
    print("--- Running Stock Selection Script ---")
    df_financials = load_and_merge_financial_data(DATA_DIR)
    if df_financials.empty:
        print("Could not load financial data. Exiting.")
        return

    print("Finding a viable backtest start date...")
    
    # 获取所有唯一的、已知的财务报告发布日期
    possible_publish_dates = sorted(df_financials['date_known'].unique())

    backtest_start_date = None
    viable_rebalance_dates = []

    # 确定所有可行的调仓日期
    for publish_date in possible_publish_dates:
        # 调仓日 = 发布日 + 3个交易日
        rebalance_day = publish_date + pd.offsets.BDay(3)
        scores = calc_factor_scores(df_financials, publish_date, ROLLING_WINDOW_YEARS, MIN_REPORTS_IN_WINDOW)
        if len(scores) >= NUM_STOCKS_TO_SELECT:
            if backtest_start_date is None:
                backtest_start_date = rebalance_day
                print(f"Found a viable start date: {backtest_start_date.date()}.")
            viable_rebalance_dates.append(rebalance_day)

    if backtest_start_date is None:
        print("Could not find any period with enough stocks to start. Exiting.")
        return

    all_period_portfolios = {}
    latest_known = df_financials['date_known'].max().normalize()

    print(f"Starting selection from {backtest_start_date.date()} to {latest_known.date()}...")
    for i, rebalance_day in enumerate(viable_rebalance_dates):
        # 我们基于发布日的数据来决定在调仓日的持仓
        # 因此，计算因子得分时，我们使用发布日（调仓日-3BD）
        # 注意：这是一个简化的假设，实际中可能需要更复杂的逻辑来匹配准确的发布日
        publish_date_for_calc = rebalance_day - pd.offsets.BDay(3)

        print(f"  - Processing rebalance on {rebalance_day.date()} (based on data before {publish_date_for_calc.date()}) ({i+1}/{len(viable_rebalance_dates)})")
        df_agg_scores = calc_factor_scores(df_financials, publish_date_for_calc, ROLLING_WINDOW_YEARS, MIN_REPORTS_IN_WINDOW)
        if df_agg_scores.empty: continue
        
        df_ranked = df_agg_scores.sort_values(by='avg_factor_score', ascending=False)
        top_stocks = df_ranked.head(NUM_STOCKS_TO_SELECT)
        all_period_portfolios[rebalance_day.date()] = top_stocks.reset_index()

    if all_period_portfolios:
        with pd.ExcelWriter(OUTPUT_FILE) as writer:
            for date, df_portfolio in all_period_portfolios.items():
                df_portfolio.to_excel(writer, sheet_name=str(date), index=False)
        print(f"\nStock selection complete. Results saved to:\n{OUTPUT_FILE}")
    else:
        print("\nNo portfolios were generated.")

if __name__ == "__main__":
    main()