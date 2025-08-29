import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pandas as pd

# 统一用项目内的路径配置
from .utils.paths import DATA_DIR, DB_PATH  # ← 用已有模块，别重复造轮子


def tidy_ticker(col: pd.Series) -> pd.Series:
    """数据清洗函数：标准化股票代码"""
    return (
        col.astype("string")
        .str.upper()
        .str.strip()
        .str.replace(r"_DELISTED$", "", regex=True)
        .replace({"": pd.NA})
    )


def _fast_pragmas(con: sqlite3.Connection, fast: bool = True) -> None:
    """设置SQLite性能优化参数"""
    if fast:
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA synchronous=NORMAL;")
    else:
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA temp_store=MEMORY;")
    con.execute("PRAGMA cache_size=-200000;")  # 约200MB


def _check_sqlite3_cli() -> bool:
    """检查是否有sqlite3命令行工具可用"""
    return shutil.which("sqlite3") is not None


def _import_prices_with_cli(csv_path: Path, db_path: Path, schema_path: Path) -> bool:
    """使用SQLite CLI导入价格数据（最快方式）"""
    try:
        print("    - Using SQLite CLI for fast import...")

        # 构建SQLite命令
        indexes_path = schema_path.parent / "indexes_prices.sql"
        commands = [
            f".read {schema_path.as_posix()}",
            ".separator ;",
            ".mode ascii",
            f".import --skip 1 {csv_path.as_posix()} share_prices",
        ]
        if indexes_path.exists():
            commands.append(f".read {indexes_path.as_posix()}")
        commands.extend([
            "PRAGMA journal_mode=WAL;",
            "PRAGMA synchronous=NORMAL;",
        ])

        # 执行SQLite命令
        cmd = ["sqlite3", str(db_path)]
        for command in commands:
            cmd.extend(["-cmd", command])
        cmd.append(".quit")

        subprocess.run(cmd, capture_output=True, text=True, check=True)
        print("    - SQLite CLI import completed successfully")
        return True

    except subprocess.CalledProcessError as e:
        print(f"    - SQLite CLI import failed: {e}")
        print(f"    - stderr: {e.stderr}")
        return False
    except Exception as e:
        print(f"    - SQLite CLI import error: {e}")
        return False


def _load_csv_in_chunks(
    csv_path: Path,
    table: str,
    con: sqlite3.Connection,
    parse_dates=None,
    sep=";",
    dtype=None,
    chunk=200_000,
) -> int:
    """分块加载CSV文件到数据库"""
    rows = 0
    first = True
    for df in pd.read_csv(
        csv_path,
        sep=sep,
        on_bad_lines="skip",
        parse_dates=parse_dates,
        dtype=dtype,
        chunksize=chunk,
    ):
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


def main(*, skip_prices: bool = False, only_prices: bool = False):
    """主函数：优化版数据库加载

    Args:
        skip_prices: 跳过股价数据导入（仅导入财报类表）
        only_prices: 仅导入股价数据（跳过财报类表）
    """
    print(f"Creating SQLite database at: {DB_PATH}")
    with sqlite3.connect(DB_PATH) as con:
        _fast_pragmas(con, fast=True)

        # 财报数据
        if not only_prices:
            print("Processing financial statements...")
            files = {
                "balance_sheet": DATA_DIR / "us-balance-ttm.csv",
                "cash_flow": DATA_DIR / "us-cashflow-ttm.csv",
                "income": DATA_DIR / "us-income-ttm.csv",
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

        # 价格数据 - 可选跳过（用于外部脚本先行导入）
        if os.getenv("SKIP_PRICES") or skip_prices:
            print("Skipping price data import due to SKIP_PRICES=1")
        else:
            print("Processing price data...")
            price_csv = DATA_DIR / "us-shareprices-daily.csv"
            # schema文件（优先使用 schema_prices.sql，兼容旧 schema.sql）位于项目根目录
            sql_dir = DATA_DIR.parent / "sql"
            preferred = sql_dir / "schema_prices.sql"
            fallback = sql_dir / "schema.sql"
            schema_sql = preferred if preferred.exists() else fallback

            if price_csv.exists():
                # 检查文件大小，大文件优先使用CLI导入
                file_size_mb = price_csv.stat().st_size / (1024 * 1024)
                print(f"    - Price data file size: {file_size_mb:.1f} MB")

                cli_success = False
                if _check_sqlite3_cli() and schema_sql.exists():
                    print("    - SQLite CLI available, attempting fast import...")
                    cli_success = _import_prices_with_cli(price_csv, DB_PATH, schema_sql)

                if not cli_success:
                    print("    - Falling back to pandas chunked import...")
                    price_dtype = {
                        "Ticker": "string",
                    }
                    rows = _load_csv_in_chunks(
                        price_csv,
                        "share_prices",
                        con,
                        parse_dates=["Date"],
                        dtype=price_dtype,
                    )
                    print(f"    - Loaded {rows} rows into share_prices")

                    # 为pandas导入创建索引
                    print("    - Creating indexes for pandas import...")
                    con.execute(
                        "CREATE INDEX IF NOT EXISTS idx_prices_date ON share_prices(Date);"
                    )
                    con.execute(
                        "CREATE INDEX IF NOT EXISTS idx_prices_ticker_date ON share_prices(Ticker, Date);"
                    )
                else:
                    print("    - SQLite CLI import completed with indexes")
            else:
                print(f"  [WARNING] File not found: {price_csv}")
                if not schema_sql.exists():
                    print(f"  [WARNING] Schema file not found: {schema_sql}")

        # 财报表索引：一次性创建，且与查询对齐
        if not only_prices:
            print("Creating optimized indexes for financial data...")
            con.executescript("""
            -- 财报表：按 Ticker, year 分组按 date_known 取最新
            CREATE INDEX IF NOT EXISTS idx_bs_ty_date  ON balance_sheet (Ticker, year, date_known DESC);
            CREATE INDEX IF NOT EXISTS idx_cf_ty_date  ON cash_flow     (Ticker, year, date_known DESC);
            CREATE INDEX IF NOT EXISTS idx_in_ty_date  ON income        (Ticker, year, date_known DESC);
            """)

        _fast_pragmas(con, fast=False)

    print("Database creation complete!")


if __name__ == "__main__":
    main()
