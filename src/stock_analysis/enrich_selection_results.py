import pandas as pd
from pathlib import Path

# --- 路径配置 ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
OUTPUTS_DIR = PROJECT_ROOT / 'outputs'

# --- 文件配置 ---
# 确保这个数字与你的选股脚本一致
NUM_STOCKS_TO_SELECT = 50 
# 这是输入文件
INPUT_FILE = OUTPUTS_DIR / f'point_in_time_backtest_top_{NUM_STOCKS_TO_SELECT}_stocks.xlsx'
# 这是输出文件
ENRICHED_OUTPUT_FILE = OUTPUTS_DIR / f'point_in_time_backtest_top_{NUM_STOCKS_TO_SELECT}_stocks_enriched.xlsx'


def tidy_ticker(col: pd.Series) -> pd.Series:
    """统一清洗和格式化股票代码列。"""
    return col.astype('string').str.upper().str.strip().str.replace(r'_DELISTED$', '', regex=True).replace({'': pd.NA})


def load_company_info(data_dir: Path) -> pd.DataFrame:
    """加载并准备公司信息数据。"""
    print("Loading company information...")
    company_path = data_dir / 'us-companies.csv'
    if not company_path.exists():
        company_path = data_dir / 'us-companies.txt'

    if not company_path.exists():
        print(f"[WARNING] Company info file not found in '{data_dir}'. Cannot enrich results.")
        return pd.DataFrame()

    try:
        df_co = pd.read_csv(company_path, sep=';', on_bad_lines='skip')
        df_co['Ticker'] = tidy_ticker(df_co['Ticker'])
        
        cols_to_keep = ['Ticker', 'Company Name', 'IndustryId', 'Business Summary']
        existing_cols = [c for c in cols_to_keep if c in df_co.columns]
        
        df_co_info = df_co[existing_cols].drop_duplicates(subset=['Ticker'], keep='last')
        print(f"Loaded info for {len(df_co_info)} unique companies.")
        return df_co_info
    except Exception as e:
        print(f"[ERROR] Failed to load or process company info: {e}")
        return pd.DataFrame()


def enrich_portfolio_file(input_path: Path, output_path: Path, company_info: pd.DataFrame):
    """读取选股结果，丰富信息，并保存到新文件。"""
    if not input_path.exists():
        print(f"[ERROR] Input portfolio file not found: {input_path}")
        print("Please run the selection script first.")
        return

    print(f"Reading portfolio data from: {input_path}")
    # 读取所有sheets
    xls = pd.read_excel(input_path, sheet_name=None)
    
    print(f"Enriching {len(xls)} portfolio sheets...")
    with pd.ExcelWriter(output_path) as writer:
        for sheet_name, df_portfolio in xls.items():
            if 'Ticker' not in df_portfolio.columns:
                print(f"  - Skipping sheet '{sheet_name}' as it has no 'Ticker' column.")
                df_portfolio.to_excel(writer, sheet_name=sheet_name, index=False)
                continue
                
            # 使用左连接（left merge）来丰富数据
            enriched_df = pd.merge(df_portfolio, company_info, on='Ticker', how='left')
            enriched_df.to_excel(writer, sheet_name=sheet_name, index=False)
    
    print(f"\nEnrichment complete. Enriched data saved to:\n{output_path}")

# --- Main Logic for Enrichment Script ---
def main():
    print("--- Running Results Enrichment Script ---")
    
    # 1. 加载公司信息
    df_companies = load_company_info(DATA_DIR)
    if df_companies.empty:
        return

    # 2. 丰富选股文件
    enrich_portfolio_file(INPUT_FILE, ENRICHED_OUTPUT_FILE, df_companies)

if __name__ == "__main__":
    main()