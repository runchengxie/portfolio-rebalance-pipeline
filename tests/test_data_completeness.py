import pandas as pd
import sqlite3
from pathlib import Path
import pytest

# --- 路径配置 ---
# 测试脚本通常放在 tests/ 文件夹下
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
OUTPUTS_DIR = PROJECT_ROOT / 'outputs'
DB_PATH = DATA_DIR / 'financial_data.db'

# "事实的来源": 我们的回测需要用到哪些股票，是由这个文件决定的
PORTFOLIO_FILE = OUTPUTS_DIR / 'point_in_time_backtest_quarterly.xlsx'

# --- 辅助函数 ---
def tidy_ticker(col: pd.Series) -> pd.Series:
    """统一清洗和格式化股票代码列。"""
    return col.astype('string').str.upper().str.strip().str.replace(r'_DELISTED$', '', regex=True).replace({'': pd.NA})

# --- 测试设置 (Pytest Fixture) ---
@pytest.fixture(scope="module")
def required_tickers() -> set:
    """
    一个 Pytest "fixture"，用于加载并返回所有回测必需的股票代码。
    它只会在整个测试会话中运行一次。
    """
    if not PORTFOLIO_FILE.exists():
        pytest.fail(f"选股文件未找到: {PORTFOLIO_FILE}. 请先运行选股脚本。")

    xls = pd.read_excel(PORTFOLIO_FILE, sheet_name=None, engine='openpyxl')
    
    all_tickers = set()
    for sheet_name, df in xls.items():
        if 'Ticker' in df.columns:
            all_tickers.update(tidy_ticker(df['Ticker']).dropna())
            
    if not all_tickers:
        pytest.fail("从选股文件中未能提取任何股票代码。")
        
    print(f"\n从 '{PORTFOLIO_FILE.name}' 中加载了 {len(all_tickers)} 个必需的股票代码用于测试。")
    return all_tickers

# --- 测试函数 ---
def test_all_selected_tickers_exist_in_database(required_tickers: set):
    """
    这是一个测试用例。它会检查所有从选股文件中加载的股票，
    确保它们在数据库的每一个核心表中都存在。
    """
    if not DB_PATH.exists():
        pytest.fail(f"数据库文件未找到: {DB_PATH}. 请先运行 load_data_to_db.py。")

    con = sqlite3.connect(DB_PATH)
    
    tables_to_check = ['share_prices', 'balance_sheet', 'cash_flow', 'income']
    all_missing_info = []

    for table in tables_to_check:
        try:
            query = f"SELECT DISTINCT Ticker FROM {table}"
            df_db = pd.read_sql_query(query, con)
            db_tickers = set(tidy_ticker(df_db['Ticker']).dropna())
            
            missing_in_this_table = required_tickers - db_tickers
            
            if missing_in_this_table:
                # 不要立即失败，先收集所有错误信息
                all_missing_info.append(
                    f"在表 '{table}' 中缺失 {len(missing_in_this_table)} 个股票: {sorted(list(missing_in_this_table))}"
                )
        except Exception as e:
            pytest.fail(f"查询数据库表 '{table}' 时出错: {e}")
    
    con.close()

    # --- 断言 ---
    # 在所有检查完成后，进行最终断言。如果 all_missing_info 列表不为空，测试失败。
    assert not all_missing_info, f"数据完整性检查失败:\n" + "\n".join(all_missing_info)