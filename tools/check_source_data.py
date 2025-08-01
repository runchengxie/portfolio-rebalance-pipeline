# 文件名: check_database_data.py
# 存放路径: your_project_root/tools/check_database_data.py

import pandas as pd
import sqlite3
from pathlib import Path

# --- 配置 ---
# 脚本位于 tools/ 文件夹下，向上回溯两层到达项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
DB_PATH = DATA_DIR / 'financial_data.db'

# 这些是在你的 backtest 日志 (rebalancing_diagnostics_log.csv) 中被识别为缺失的股票
MISSING_TICKERS_FROM_LOG = {
    "IOTS", "FNJN", "PGNX", "WBC", "CUO", "AGN", "LOGM", "MJCO", 
    "VSLR", "NBL", "MEET", "TERP", "CPN", "BREW", "WPX", "MYL", "CXO"
}

# 数据库中需要检查的表
TABLES_TO_CHECK = [
    'share_prices',
    'balance_sheet',
    'cash_flow',
    'income'
]

# --- 辅助函数 ---
def tidy_ticker(col: pd.Series) -> pd.Series:
    """统一清洗和格式化股票代码列。"""
    return col.astype('string').str.upper().str.strip().str.replace(r'_DELISTED$', '', regex=True).replace({'': pd.NA})

# --- 主逻辑 ---
def main():
    """主函数，用于执行数据库检查。"""
    print("--- 开始直接检查 SQLite 数据库中是否存在缺失的股票代码 ---\n")
    print(f"项目根目录被识别为: {PROJECT_ROOT}")
    print(f"正在检查数据库文件: {DB_PATH}\n")

    if not DB_PATH.exists():
        print(f"[错误] 数据库文件未找到: {DB_PATH}")
        print("请先运行 'tools/load_data_to_db.py' 来创建数据库。")
        return

    all_tables_ok = True
    try:
        con = sqlite3.connect(DB_PATH)

        for table_name in TABLES_TO_CHECK:
            print(f"--- 正在查询表: '{table_name}' ---")
            
            try:
                # 查询该表中所有唯一的 Ticker
                query = f"SELECT DISTINCT Ticker FROM {table_name}"
                df = pd.read_sql_query(query, con)
                
                if df.empty:
                    print(f"[警告] 表 '{table_name}' 中没有找到任何数据。\n")
                    all_tables_ok = False
                    continue

                # 清理并获取数据库表中的所有唯一股票代码
                db_tickers = set(tidy_ticker(df['Ticker']).dropna())
                print(f"在表中找到 {len(db_tickers)} 个唯一的股票代码。")

                # 找出在回测中缺失的股票，哪些也确实不在这个数据库表中
                not_found_in_this_table = MISSING_TICKERS_FROM_LOG - db_tickers

                if not not_found_in_this_table:
                    print(f"✅ 确认：所有在回测日志中缺失的股票，在此表中都存在。")
                else:
                    all_tables_ok = False
                    print(f"❌ 证实缺失：以下 {len(not_found_in_this_table)} 个股票代码在此表中确实不存在:")
                    print(sorted(list(not_found_in_this_table)))
                
                print("-" * 50 + "\n")

            except pd.io.sql.DatabaseError:
                print(f"[错误] 表 '{table_name}' 在数据库中不存在或查询失败。\n")
                all_tables_ok = False
                continue

    except Exception as e:
        all_tables_ok = False
        print(f"[严重错误] 连接或查询数据库时出错: {e}\n")
    finally:
        if 'con' in locals():
            con.close()

    print("--- 检查完毕 ---")
    if not all_tables_ok:
        print("检查证实，你的 'financial_data.db' 数据库中确实缺少策略所需的某些股票数据。")
        print("这表明，你用于生成数据库的原始 'us-....csv' 文件可能本身就不包含这些股票。")
        print("这完全解释了为什么回测时会出现数据缺失的问题。")
    else:
        print("所有在回测日志中缺失的股票似乎都存在于数据库的各个表中。")
        print("如果问题依旧，可能是在数据加载或合并逻辑中（例如日期范围过滤）导致它们被排除了。")

# --- 运行脚本 ---
if __name__ == "__main__":
    main()