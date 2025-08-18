import sqlite3
from pathlib import Path
import pandas as pd

# 统一用项目内的路径配置
from .utils.paths import DATA_DIR, DB_PATH  # ← 用已有模块，别重复造轮子


def tidy_ticker(col: pd.Series) -> pd.Series:
    """数据清洗函数：标准化股票代码"""
    return (
        col.astype("string").str.upper().str.strip()
           .str.replace(r"_DELISTED$", "", regex=True).replace({"": pd.NA})
    )


def _fast_pragmas(con: sqlite3.Connection, fast: bool = True) -> None:
    """设置SQLite性能优化参数"""
    if fast:
        con.execute("PRAGMA journal_mode=OFF;")
        con.execute("PRAGMA synchronous=OFF;")
    else:
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA temp_store=MEMORY;")
    con.execute("PRAGMA cache_size=-200000;")  # 约200MB


def _load_csv_in_chunks(csv_path: Path, table: str, con: sqlite3.Connection,
                        parse_dates=None, sep=";", dtype=None, chunk=200_000) -> int:
    """分块加载CSV文件到数据库"""
    rows = 0
    first = True
    for df in pd.read_csv(csv_path, sep=sep, on_bad_lines="skip",
                          parse_dates=parse_dates, dtype=dtype, chunksize=chunk):
        if "Ticker" in df.columns:
            df["Ticker"] = tidy_ticker(df["Ticker"])
            df = df.dropna(subset=["Ticker"])
        
        # 财报字段改名逻辑
        if table in {"balance_sheet", "cash_flow", "income"}:
            if "Publish Date" in df.columns:
                df.rename(columns={"Publish Date": "date_known"}, inplace=True)
            if "Fiscal Year" in df.columns:
                df.rename(columns={"Fiscal Year": "year"}, inplace=True)
            if "date_known" in df.columns:
                df["date_known"] = pd.to_datetime(df["date_known"], errors="coerce")
        
        # 价格数据去重
        if table == "share_prices":
            df = df.drop_duplicates(subset=["Ticker", "Date"], keep="last")

        df.to_sql(table, con, if_exists="replace" if first else "append", index=False)
        first = False
        rows += len(df)
    return rows


def main():
    """主函数：优化版数据库加载"""
    print(f"Creating SQLite database at: {DB_PATH}")
    with sqlite3.connect(DB_PATH) as con:
        _fast_pragmas(con, fast=True)
        con.execute("BEGIN")

        # 财报数据
        print("Processing financial statements...")
        files = {
            "balance_sheet": DATA_DIR / "us-balance-ttm.csv",
            "cash_flow":     DATA_DIR / "us-cashflow-ttm.csv",
            "income":        DATA_DIR / "us-income-ttm.csv",
        }
        
        # 定义数据类型以减少SQLite类型推断开销
        financial_dtype = {
            "Ticker": "string",
            "Fiscal Year": "Int64",
        }
        
        for table, path in files.items():
            if path.exists():
                print(f"  Loading {path.name} -> {table}")
                rows = _load_csv_in_chunks(path, table, con, dtype=financial_dtype)
                print(f"    - Loaded {rows} rows into {table}")
            else:
                print(f"  [WARNING] File not found: {path}")

        # 价格数据
        print("Processing price data...")
        price_csv = DATA_DIR / "us-shareprices-daily.csv"
        if price_csv.exists():
            price_dtype = {
                "Ticker": "string",
            }
            rows = _load_csv_in_chunks(price_csv, "share_prices", con,
                                       parse_dates=["Date"], dtype=price_dtype)
            print(f"    - Loaded {rows} rows into share_prices")
        else:
            print(f"  [WARNING] File not found: {price_csv}")

        # 索引：一次性创建，且与查询对齐
        print("Creating optimized indexes...")
        con.executescript("""
        -- 财报表：按 Ticker, year 分组按 date_known 取最新
        CREATE INDEX IF NOT EXISTS idx_bs_ty_date  ON balance_sheet (Ticker, year, date_known DESC);
        CREATE INDEX IF NOT EXISTS idx_cf_ty_date  ON cash_flow     (Ticker, year, date_known DESC);
        CREATE INDEX IF NOT EXISTS idx_in_ty_date  ON income        (Ticker, year, date_known DESC);

        -- 价格表：主时间轴和按股票筛选都要快
        CREATE INDEX IF NOT EXISTS idx_prices_date        ON share_prices (Date);
        CREATE INDEX IF NOT EXISTS idx_prices_ticker_date ON share_prices (Ticker, Date);
        
        -- 可选：价格表唯一约束防止重复数据
        -- CREATE UNIQUE INDEX IF NOT EXISTS idx_prices_unique ON share_prices (Ticker, Date);
        """)

        con.execute("COMMIT")
        _fast_pragmas(con, fast=False)

    print("Database creation complete!")


if __name__ == "__main__":
    main()
