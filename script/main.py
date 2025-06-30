import pandas as pd
import numpy as np
from scipy.stats import zscore
from pathlib import Path

# --- Configuration ---
# 设置数据目录
DATA_DIR = Path(__file__).resolve().parent.parent / 'data'

# 定义回测的起止年份
START_YEAR = 2015
END_YEAR = 2021 # 将结束年份调整为2021，因为TTM数据可能到2022年，但我们需要之后一年的回报

# 定义因子构建所需的特征及其在CSV文件中的原始列名
# 我们将把这些原始列名映射为更简洁的名称
COLUMN_MAP = {
    'Net Cash from Operating Activities': 'cfo',
    'Income Tax Expense': 'txt',
    'Total Equity': 'ceq',
    'Total Assets': 'at',
    'Accounts Receivable': 'rect'
}

# 脚本内部使用的简洁特征名
FEATURES = list(COLUMN_MAP.values())

# 定义因子权重：Z(cfo) + Z(ceq) + Z(txt) + Z(Δtxt) - Z(Δat) - Z(Δrect)
# 注意：这需要先计算变化量 (delta)
FACTOR_WEIGHTS = {'cfo': 1, 'ceq': 1, 'txt': 1, 'd_txt': 1, 'd_at': -1, 'd_rect': -1}

# 用于分组分析的分位数数量
N_QUANTILES = 5


# --- Helper Functions ---

def load_and_merge_financial_data(data_dir: Path) -> pd.DataFrame:
    """
    从本地CSV文件加载、清洗和合并财务数据。
    参考 notebook/notebook.ipynb 的加载逻辑。
    """
    print("Loading financial data from local CSV files...")
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
        return pd.DataFrame()

    # 数据清洗
    def clean_dataframe(df):
        df['Report Date'] = pd.to_datetime(df['Report Date'], errors='coerce')
        df.rename(columns={'Fiscal Year': 'year'}, inplace=True)
        numeric_cols = [col for col in df.columns if df[col].dtype == 'object' and col not in ['Ticker', 'Currency', 'Fiscal Period']]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        return df.dropna(subset=['Report Date', 'year'])

    df_bs = clean_dataframe(df_bs)
    df_cf = clean_dataframe(df_cf)
    df_is = clean_dataframe(df_is)

    # 如果需要，可以取消注释此行来查看所有列名
    print("DEBUG: Columns in Income Statement file are:", df_is.columns.tolist())

    # 合并数据
    merge_keys = ['Ticker', 'year', 'Report Date']
    df_cf_subset = df_cf[['Ticker', 'year', 'Report Date', 'Net Cash from Operating Activities']]
    
    # +++ THE FIX IS HERE +++
    # Let's try 'Income Tax', which matches the pattern of other columns like 'Net Income'
    df_is_subset = df_is[['Ticker', 'year', 'Report Date', 'Income Tax']]
    
    df_bs_subset = df_bs[['Ticker', 'year', 'Report Date', 'Total Equity', 'Total Assets', 'Accounts Receivable']]
    
    # 核心字段重命名
    df_bs_subset = df_bs_subset.rename(columns={'Total Equity': 'ceq', 'Total Assets': 'at', 'Accounts Receivable': 'rect'})
    df_cf_subset = df_cf_subset.rename(columns={'Net Cash from Operating Activities': 'cfo'})

    # +++ AND THE FIX IS HERE +++
    df_is_subset = df_is_subset.rename(columns={'Income Tax': 'txt'})

    df_merged = pd.merge(df_bs_subset, df_is_subset, on=merge_keys, how='inner')
    df_final = pd.merge(df_merged, df_cf_subset, on=merge_keys, how='inner')
    
    df_final = df_final.sort_values('Report Date', ascending=False).drop_duplicates(subset=['Ticker', 'year'])

    df_final.loc[df_final['at'] <= 0, 'at'] = np.nan
    df_final.loc[df_final['ceq'] <= 0, 'ceq'] = np.nan

    print(f"Merged data has {len(df_final)} rows.")
    return df_final


def get_forward_returns_mock(tickers: pd.Series, factor_year: int) -> pd.DataFrame:
    """
    *** MOCK FUNCTION - 重要提示 ***
    生成模拟的未来一年回报。
    在实际应用中，你需要用一个从你的股价数据文件中读取数据的真实函数来替换它。

    Args:
        tickers (pd.Series): 包含股票代码的Series。
        factor_year (int): 因子计算的年份。

    Returns:
        pd.DataFrame: 包含 'Ticker' 和 'fwd_return' 列的DataFrame。
    """
    print(f"--- WARNING: Generating MOCK forward returns for year {factor_year+1}. ---")
    print("--- This should be replaced with a real price data implementation. ---")
    
    # 模拟平均10%的年回报率和30%的波动率
    np.random.seed(factor_year) # 使用年份作为种子以保证结果可复现
    mock_returns = np.random.normal(0.10, 0.30, size=len(tickers))
    
    df_returns = pd.DataFrame({
        'Ticker': tickers,
        'fwd_return': mock_returns
    })
    return df_returns

# --- Main Logic ---

def main():
    # 1. 一次性加载所有财务数据
    df_financials = load_and_merge_financial_data(DATA_DIR)

    if df_financials.empty:
        print("Could not load financial data. Exiting.")
        return

    print("\nRaw Financial Data Sample:")
    print(df_financials.head())
    
    # 2. 计算所需的变化量 (Deltas)
    df_financials = df_financials.sort_values(by=['Ticker', 'year'])
    for feat in ['txt', 'at', 'rect']: # 需要计算变化量的特征
        df_financials[f'd_{feat}'] = df_financials.groupby('Ticker')[feat].diff()

    print("\nFinancial Data with Deltas Sample:")
    print(df_financials[['Ticker', 'year', 'at', 'd_at']].head())

    # 3. 按年份循环，计算因子并进行分组回测
    quantile_returns = []

    for year in range(START_YEAR, END_YEAR + 1):
        print(f"\n--- Processing Year {year} Factor ---")

        # 筛选当年的财务数据
        # 注意：计算变化量需要前一年的数据，所以d_...列在START_YEAR会是NaN
        df_year_data = df_financials[df_financials['year'] == year].copy()

        # 确定因子所有组成部分
        factor_components = list(FACTOR_WEIGHTS.keys())
        
        # 删除在因子计算中任何一个指标有缺失值的行
        initial_count = len(df_year_data)
        df_year_data.dropna(subset=factor_components, inplace=True)
        print(f"Dropped {initial_count - len(df_year_data)} stocks due to missing factor components for year {year}.")

        if len(df_year_data) < N_QUANTILES * 10: # 确保有足够的数据进行分组
            print(f"Skipping year {year}: Not enough valid data points ({len(df_year_data)}).")
            continue

        # 对每个因子组成部分进行Z-score标准化
        df_zscores = pd.DataFrame(index=df_year_data.index)
        for component in factor_components:
            df_zscores[f'z_{component}'] = zscore(df_year_data[component])

        # 根据权重计算最终的因子分
        df_year_data['factor_score'] = 0.0
        for component, weight in FACTOR_WEIGHTS.items():
            df_year_data['factor_score'] += df_zscores[f'z_{component}'] * weight

        print("Factor Score Calculation Sample:")
        print(df_year_data[['Ticker', 'factor_score']].head())

        # 4. 获取未来一年的回报 (使用模拟函数)
        df_fwd_returns = get_forward_returns_mock(df_year_data['Ticker'], year)

        # 5. 合并因子分和未来回报
        df_eval = pd.merge(df_year_data[['Ticker', 'year', 'factor_score']], df_fwd_returns, on='Ticker', how='inner')

        if df_eval.empty or 'fwd_return' not in df_eval.columns or df_eval['fwd_return'].isnull().all():
             print(f"Skipping year {year}: Merge failed or no valid forward returns.")
             continue
        
        # 6. 分组分析
        try:
            df_eval['quantile'] = pd.qcut(df_eval['factor_score'], N_QUANTILES, labels=False, duplicates='drop') + 1
            # 计算每个分位的平均回报
            avg_quantile_return = df_eval.groupby('quantile')['fwd_return'].mean()
            print(f"\nAverage Forward Return by Factor Quantile for year {year+1}:")
            print(avg_quantile_return)
            quantile_returns.append(avg_quantile_return)
        except Exception as e:
            print(f"Error during quantile analysis for year {year}: {e}")
            print("Factor score distribution:")
            print(df_eval['factor_score'].describe())

    # 7. 汇总并展示最终结果
    if quantile_returns:
        # 计算所有年份的平均分组收益
        df_quantile_summary = pd.concat(quantile_returns, axis=1).mean(axis=1)
        df_quantile_summary.index.name = 'Quantile (1=Bottom, 5=Top)'
        print("\n\n--- Overall Quantile Performance (Average Annual Forward Return) ---")
        print(df_quantile_summary)

        # 计算多空组合的年化收益
        if len(df_quantile_summary) == N_QUANTILES:
            top_bottom_spread = df_quantile_summary.iloc[-1] - df_quantile_summary.iloc[0]
            print(f"\nAverage Top Quantile (Q5) Return: {df_quantile_summary.iloc[-1]:.4f}")
            print(f"Average Bottom Quantile (Q1) Return: {df_quantile_summary.iloc[0]:.4f}")
            print(f"Average Top-Bottom Spread (Long Q5, Short Q1): {top_bottom_spread:.4f}")
    else:
        print("\nNo valid quantile results generated across the specified years.")

if __name__ == "__main__":
    main()