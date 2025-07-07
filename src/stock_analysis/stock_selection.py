import pandas as pd
import numpy as np
from scipy.stats import zscore
from pathlib import Path

# --- Configuration ---
# 设置数据目录
DATA_DIR = Path(__file__).resolve().parent.parent / 'data'

# --- 修改点 ---
# 不再需要硬编码的 START_YEAR 和 END_YEAR。
# 代码将自动检测数据中的所有年份。

# 定义因子构建所需的特征 (保持不变)
FACTOR_WEIGHTS = {'cfo': 1, 'ceq': 1, 'txt': 1, 'd_txt': 1, 'd_at': -1, 'd_rect': -1}

# 定义输出的Excel文件名和要选择的股票数量
OUTPUT_FILE = 'dynamic_multi_year_ranked_stocks.xlsx'
NUM_STOCKS_TO_SELECT = 50

# --- Helper Functions ---
def load_and_merge_financial_data(data_dir: Path) -> pd.DataFrame:
    """
    从本地CSV文件加载、清洗和合并财务数据。
    (此函数保持不变)
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

    def clean_dataframe(df):
        df['Report Date'] = pd.to_datetime(df['Report Date'], errors='coerce')
        df.rename(columns={'Fiscal Year': 'year'}, inplace=True)
        numeric_cols = [col for col in df.columns if df[col].dtype == 'object' and col not in ['Ticker', 'Currency', 'Fiscal Period']]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        # --- 关键修改：将年份转换为整数，避免浮点数问题 ---
        return df.dropna(subset=['Report Date', 'year']).astype({'year': 'int'})

    df_bs = clean_dataframe(df_bs)
    df_cf = clean_dataframe(df_cf)
    df_is = clean_dataframe(df_is)

    merge_keys = ['Ticker', 'year', 'Report Date']
    df_cf_subset = df_cf[['Ticker', 'year', 'Report Date', 'Net Cash from Operating Activities']]
    df_is_subset = df_is[['Ticker', 'year', 'Report Date', 'Income Tax (Expense) Benefit, Net']]
    df_bs_subset = df_bs[['Ticker', 'year', 'Report Date', 'Total Equity', 'Total Assets', 'Accounts & Notes Receivable']]
    
    df_bs_subset = df_bs_subset.rename(columns={'Total Equity': 'ceq', 'Total Assets': 'at', 'Accounts & Notes Receivable': 'rect'})
    df_cf_subset = df_cf_subset.rename(columns={'Net Cash from Operating Activities': 'cfo'})
    df_is_subset = df_is_subset.rename(columns={'Income Tax (Expense) Benefit, Net': 'txt'})

    df_merged = pd.merge(df_bs_subset, df_is_subset, on=merge_keys, how='inner')
    df_final = pd.merge(df_merged, df_cf_subset, on=merge_keys, how='inner')
    
    df_final = df_final.sort_values('Report Date', ascending=False).drop_duplicates(subset=['Ticker', 'year'])

    df_final.loc[df_final['at'] <= 0, 'at'] = np.nan
    df_final.loc[df_final['ceq'] <= 0, 'ceq'] = np.nan

    print(f"Merged data has {len(df_final)} rows.")
    return df_final


# --- Main Logic ---

def main():
    # 1. 加载数据
    df_financials = load_and_merge_financial_data(DATA_DIR)
    if df_financials.empty:
        print("Could not load financial data. Exiting.")
        return
    
    # 2. 计算变化量 (Deltas)
    df_financials = df_financials.sort_values(by=['Ticker', 'year'])
    factor_components = list(FACTOR_WEIGHTS.keys())
    delta_features = [feat for feat in factor_components if feat.startswith('d_')]
    original_features = [feat.replace('d_', '') for feat in delta_features]
    
    for feat in original_features:
        df_financials[f'd_{feat}'] = df_financials.groupby('Ticker')[feat].diff()

    # --- 核心修改点：动态获取年份 ---
    # 3. 从数据中动态获取所有可用的年份，并进行排序
    available_years = sorted(df_financials['year'].unique())
    print(f"\nDynamically detected years in the data: {available_years}")
    print("Note: The first year of data for any stock will be used for delta calculation and not scored.")

    # 4. 按年份循环，计算每年的因子分
    all_year_scores = []
    print("\n--- Calculating factor scores for each available year ---")

    for year in available_years:
        print(f"Processing Year {year}...")
        df_year_data = df_financials[df_financials['year'] == year].copy()
        
        # 删除因子计算中任何一个指标有缺失值的行
        # 注意：这一步会自动处理掉每个股票的第一个数据年份，因为它们的delta值是NaN
        df_year_data.dropna(subset=factor_components, inplace=True)

        if len(df_year_data) < 10: # 至少需要一些公司才能进行有意义的Z-score标准化
            print(f"  Skipping year {year}: Not enough valid data points after cleaning.")
            continue

        # Z-score标准化并计算当年的因子分
        df_zscores = pd.DataFrame(index=df_year_data.index)
        for component in factor_components:
            df_zscores[f'z_{component}'] = zscore(df_year_data[component])

        df_year_data['factor_score'] = 0.0
        for component, weight in FACTOR_WEIGHTS.items():
            df_year_data['factor_score'] += df_zscores[f'z_{component}'] * weight
        
        all_year_scores.append(df_year_data[['Ticker', 'year', 'factor_score']])

    if not all_year_scores:
        print("\nCould not generate scores for any year. Please check your data. Exiting.")
        return

    # 5. 合并所有年份的得分，并计算平均分
    df_all_scores = pd.concat(all_year_scores, ignore_index=True)
    
    print("\n--- Aggregating scores across all available years ---")
    df_agg_scores = df_all_scores.groupby('Ticker')['factor_score'].agg(['mean', 'count'])
    df_agg_scores.rename(columns={'mean': 'average_factor_score', 'count': 'num_valid_years'}, inplace=True)

    # 6. 按最终的平均分进行排序
    df_final_ranking = df_agg_scores.sort_values(by='average_factor_score', ascending=False)
    
    # 7. 选出得分最高的N只股票
    df_top_stocks = df_final_ranking.head(NUM_STOCKS_TO_SELECT)
    
    # 8. 打印结果到控制台
    print(f"\n--- Top {NUM_STOCKS_TO_SELECT} Selected Stocks (based on average score from all available data) ---")
    print(df_top_stocks)
    
    # 9. 将完整的排名列表保存到Excel文件
    try:
        df_final_ranking.to_excel(OUTPUT_FILE, index=True)
        print(f"\nSuccessfully saved the full dynamically-ranked list of stocks to '{OUTPUT_FILE}'")
    except Exception as e:
        print(f"\nError saving to Excel file: {e}")
        print("Please ensure you have 'openpyxl' installed (`pip install openpyxl`).")

if __name__ == "__main__":
    main()