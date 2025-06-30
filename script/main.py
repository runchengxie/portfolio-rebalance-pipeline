import pandas as pd
import numpy as np
from scipy.stats import zscore
from pathlib import Path

# --- Configuration ---
# 设置数据目录
DATA_DIR = Path(__file__).resolve().parent.parent / 'data'

# --- 修改点 ---
# 我们不再需要回测区间，而是设定一个选股的目标年份
# 使用2021年的财报数据来为2022年选股
TARGET_YEAR = 2021

# 定义因子构建所需的特征及其在CSV文件中的原始列名
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
FACTOR_WEIGHTS = {'cfo': 1, 'ceq': 1, 'txt': 1, 'd_txt': 1, 'd_at': -1, 'd_rect': -1}

# --- 修改点 ---
# 定义输出的Excel文件名和要选择的股票数量
OUTPUT_FILE = 'selected_stocks_for_2022.xlsx'
NUM_STOCKS_TO_SELECT = 50 # 您可以根据需要调整这个数字


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
        return df.dropna(subset=['Report Date', 'year'])

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
    # 1. 一次性加载所有财务数据
    df_financials = load_and_merge_financial_data(DATA_DIR)
    if df_financials.empty:
        print("Could not load financial data. Exiting.")
        return
    
    # 2. 计算所需的变化量 (Deltas)
    df_financials = df_financials.sort_values(by=['Ticker', 'year'])
    for feat in ['txt', 'at', 'rect']:
        df_financials[f'd_{feat}'] = df_financials.groupby('Ticker')[feat].diff()

    # --- 修改点：不再进行循环回测，而是直接进行选股 ---
    print(f"\n--- Selecting stocks based on {TARGET_YEAR} financial data ---")

    # 3. 筛选目标年份的财务数据
    df_year_data = df_financials[df_financials['year'] == TARGET_YEAR].copy()

    # 4. 数据清洗：删除因子计算中任何一个指标有缺失值的行
    factor_components = list(FACTOR_WEIGHTS.keys())
    initial_count = len(df_year_data)
    df_year_data.dropna(subset=factor_components, inplace=True)
    print(f"Found {len(df_year_data)} stocks with complete financial data for {TARGET_YEAR}.")
    print(f"(Dropped {initial_count - len(df_year_data)} stocks due to missing factor components).")

    if len(df_year_data) < 10:
        print(f"Not enough valid data points to proceed. Exiting.")
        return

    # 5. 计算因子分
    # 对每个因子组成部分进行Z-score标准化
    df_zscores = pd.DataFrame(index=df_year_data.index)
    for component in factor_components:
        df_zscores[f'z_{component}'] = zscore(df_year_data[component])

    # 根据权重计算最终的因子分
    df_year_data['factor_score'] = 0.0
    for component, weight in FACTOR_WEIGHTS.items():
        df_year_data['factor_score'] += df_zscores[f'z_{component}'] * weight

    # 6. 按因子分对股票进行排序
    df_ranked_stocks = df_year_data.sort_values(by='factor_score', ascending=False)

    # 7. 选出得分最高的N只股票
    df_selected_stocks = df_ranked_stocks.head(NUM_STOCKS_TO_SELECT)

    # 8. 打印结果到控制台
    print(f"\n--- Top {NUM_STOCKS_TO_SELECT} Selected Stocks for year {TARGET_YEAR+1} ---")
    print(" (Based on factor score from TTM data of year", TARGET_YEAR,")")
    print(df_selected_stocks[['Ticker', 'factor_score']].to_string(index=False))

    # 9. 将完整的排名列表保存到Excel文件，以便进一步分析
    # 我们保存完整列表，而不仅仅是前N个，这样您可以自己查看更多信息
    columns_to_save = ['Ticker', 'year', 'factor_score'] + factor_components
    try:
        df_ranked_stocks[columns_to_save].to_excel(OUTPUT_FILE, index=False)
        print(f"\nSuccessfully saved the full ranked list of stocks to '{OUTPUT_FILE}'")
        print("You can open this file in Excel to see all stocks sorted by their factor score.")
    except Exception as e:
        print(f"\nError saving to Excel file: {e}")
        print("Please ensure you have 'openpyxl' installed (`pip install openpyxl`).")


if __name__ == "__main__":
    main()