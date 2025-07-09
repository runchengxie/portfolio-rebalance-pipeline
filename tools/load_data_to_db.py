# tools/load_data_to_db.py
import pandas as pd
import sqlite3
from pathlib import Path

# --- 路径配置 ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
DB_PATH = DATA_DIR / 'financial_data.db'

def tidy_ticker(col: pd.Series) -> pd.Series:
    """您的数据清洗函数"""
    return col.astype('string').str.upper().str.strip().str.replace(r'_DELISTED$', '', regex=True).replace({'': pd.NA})

def main():
    print(f"Creating SQLite database at: {DB_PATH}")
    # 连接数据库 (如果不存在则会创建)
    con = sqlite3.connect(DB_PATH)

    # --- 处理财务报表 ---
    print("Processing financial statements...")
    # 这里可以复用您 run_selection.py 中的 load_and_merge_financial_data 逻辑
    # 为了简化，我们这里分开加载
    financial_files = {
        'balance_sheet': 'us-balance-ttm.csv',
        'cash_flow': 'us-cashflow-ttm.csv',
        'income': 'us-income-ttm.csv'
    }

    for table_name, file_name in financial_files.items():
        print(f"  Loading {file_name} into table '{table_name}'...")
        try:
            df = pd.read_csv(DATA_DIR / file_name, sep=';', on_bad_lines='skip')
            df['Ticker'] = tidy_ticker(df['Ticker'])
            df.rename(columns={'Publish Date': 'date_known', 'Fiscal Year': 'year'}, inplace=True)
            df['date_known'] = pd.to_datetime(df['date_known'], errors='coerce')
            
            # 使用 to_sql 写入数据库
            df.to_sql(table_name, con, if_exists='replace', index=False)
            print(f"    - Creating indexes for '{table_name}'...")
            # 为关键列创建索引，这是性能提升的关键！
            con.execute(f'CREATE INDEX idx_{table_name}_ticker_date ON {table_name} (Ticker, date_known);')
        except Exception as e:
            print(f"    [ERROR] Failed to process {file_name}: {e}")

    # --- 处理股价数据 ---
    print("Processing price data...")
    price_file = 'us-shareprices-daily.csv'
    try:
        df_prices = pd.read_csv(DATA_DIR / price_file, sep=';', on_bad_lines='skip')
        df_prices['Ticker'] = tidy_ticker(df_prices['Ticker'])
        df_prices['Date'] = pd.to_datetime(df_prices['Date'], errors='coerce')
        df_prices.to_sql('share_prices', con, if_exists='replace', index=False)
        print("    - Creating index for 'share_prices'...")
        con.execute('CREATE INDEX idx_prices_ticker_date ON share_prices (Ticker, Date);')
    except Exception as e:
        print(f"    [ERROR] Failed to process {price_file}: {e}")

    con.commit()
    con.close()
    print("\nDatabase creation complete!")

if __name__ == '__main__':
    main()