# tests/performance_comparison.py
import time
import pandas as pd
import sqlite3
from pathlib import Path
import datetime

# --- 路径配置 ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
DB_PATH = DATA_DIR / 'financial_data.db'
CSV_PATH = DATA_DIR / 'us-shareprices-daily.csv'

# --- 测试配置 ---
SPY_TICKER = 'SPY'
START_DATE = datetime.datetime(2015, 12, 31)
END_DATE = datetime.datetime(2024, 12, 31)

def load_spy_from_csv():
    """从CSV文件加载SPY数据"""
    df = pd.read_csv(CSV_PATH, sep=';', parse_dates=['Date'])
    df.columns = df.columns.str.strip()
    spy_data = df[df['Ticker'] == SPY_TICKER].copy()
    spy_data.set_index('Date', inplace=True)
    spy_data = spy_data[(spy_data.index >= START_DATE) & (spy_data.index <= END_DATE)]
    return spy_data

def load_spy_from_db():
    """从SQLite数据库加载SPY数据"""
    con = sqlite3.connect(DB_PATH)
    try:
        query = """
        SELECT Date, Open, High, Low, Close, Volume, Dividend
        FROM share_prices 
        WHERE Ticker = ? AND Date >= ? AND Date <= ?
        ORDER BY Date
        """
        
        spy_data = pd.read_sql_query(
            query, 
            con, 
            params=[SPY_TICKER, START_DATE.strftime('%Y-%m-%d'), END_DATE.strftime('%Y-%m-%d')],
            parse_dates=['Date']
        )
        spy_data.set_index('Date', inplace=True)
        return spy_data
    finally:
        con.close()

def benchmark_loading():
    """性能对比测试"""
    print("=== SPY数据加载性能对比测试 ===")
    print(f"测试期间: {START_DATE.date()} 到 {END_DATE.date()}")
    print(f"目标股票: {SPY_TICKER}")
    print()
    
    # 测试CSV加载
    print("测试CSV文件加载...")
    start_time = time.time()
    csv_data = load_spy_from_csv()
    csv_time = time.time() - start_time
    print(f"CSV加载时间: {csv_time:.4f}秒")
    print(f"CSV数据行数: {len(csv_data)}")
    print()
    
    # 测试数据库加载
    print("测试数据库加载...")
    start_time = time.time()
    db_data = load_spy_from_db()
    db_time = time.time() - start_time
    print(f"数据库加载时间: {db_time:.4f}秒")
    print(f"数据库数据行数: {len(db_data)}")
    print()
    
    # 性能对比
    speedup = csv_time / db_time if db_time > 0 else float('inf')
    print("=== 性能对比结果 ===")
    print(f"CSV加载时间:    {csv_time:.4f}秒")
    print(f"数据库加载时间:  {db_time:.4f}秒")
    print(f"性能提升倍数:    {speedup:.2f}x")
    print(f"时间节省:       {((csv_time - db_time) / csv_time * 100):.1f}%")
    
    # 数据一致性检查
    print()
    print("=== 数据一致性检查 ===")
    if len(csv_data) == len(db_data):
        print("✓ 数据行数一致")
    else:
        print(f"✗ 数据行数不一致: CSV={len(csv_data)}, DB={len(db_data)}")
    
    # 检查日期范围
    csv_start, csv_end = csv_data.index.min(), csv_data.index.max()
    db_start, db_end = db_data.index.min(), db_data.index.max()
    
    if csv_start == db_start and csv_end == db_end:
        print("✓ 日期范围一致")
    else:
        print(f"✗ 日期范围不一致")
        print(f"  CSV: {csv_start.date()} 到 {csv_end.date()}")
        print(f"  DB:  {db_start.date()} 到 {db_end.date()}")

if __name__ == '__main__':
    benchmark_loading()