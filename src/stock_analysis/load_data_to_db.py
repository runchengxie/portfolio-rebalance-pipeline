import os
import shutil
import sqlite3
import subprocess
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

# Use unified path configuration within the project
from .utils.paths import DATA_DIR, DB_PATH  # ← 用已有模块，别重复造轮子


def tidy_ticker(col: pd.Series) -> pd.Series:
    """Data cleaning function: standardize stock symbols"""
    return (
        col.astype("string")
        .str.upper()
        .str.strip()
        .str.replace(r"_DELISTED$", "", regex=True)
        .replace({"": pd.NA})
    )


def _fast_pragmas(con: sqlite3.Connection, fast: bool = True) -> None:
    """Set SQLite performance optimization parameters"""
    if fast:
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA synchronous=NORMAL;")
    else:
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA temp_store=MEMORY;")
    con.execute("PRAGMA cache_size=-200000;")  # Approximately 200MB


def _check_sqlite3_cli() -> bool:
    """Check if sqlite3 command line tool is available"""
    return shutil.which("sqlite3") is not None


def _import_prices_with_cli(csv_path: Path, db_path: Path, schema_path: Path) -> bool:
    """Import price data using SQLite CLI (fastest method)"""
    try:
        print("    - Using SQLite CLI for fast import...")

        # Build SQLite commands
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

        # Execute SQLite commands
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
    *,
    tickers_whitelist: set[str] | None = None,
    date_start: pd.Timestamp | None = None,
    date_end: pd.Timestamp | None = None,
) -> int:
    """Load CSV file to database in chunks"""
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

        # Financial statement field renaming logic
        if table in {"balance_sheet", "cash_flow", "income"}:
            if "Publish Date" in df.columns:
                df.rename(columns={"Publish Date": "date_known"}, inplace=True)
            if "Fiscal Year" in df.columns:
                df.rename(columns={"Fiscal Year": "year"}, inplace=True)
            if "date_known" in df.columns:
                df["date_known"] = pd.to_datetime(df["date_known"], errors="coerce")

        # Remove duplicates from price data and apply optional filters
        if table == "share_prices":
            # Ensure Date is datetime if present
            if "Date" in df.columns and not pd.api.types.is_datetime64_any_dtype(
                df["Date"]
            ):
                df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

            # Apply ticker whitelist
            if tickers_whitelist:
                df = df[df["Ticker"].isin(tickers_whitelist)]

            # Apply date range
            if date_start is not None:
                df = df[df["Date"] >= date_start]
            if date_end is not None:
                df = df[df["Date"] <= date_end]

            df = df.drop_duplicates(subset=["Ticker", "Date"], keep="last")

        df.to_sql(table, con, if_exists="replace" if first else "append", index=False)
        first = False
        rows += len(df)
    return rows


def main(
    *,
    skip_prices: bool = False,
    only_prices: bool = False,
    tickers_whitelist: Iterable[str] | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
):
    """Main function: optimized database loading

    Args:
        skip_prices: Skip stock price data import (only import financial statement tables)
        only_prices: Only import stock price data (skip financial statement tables)
        tickers_whitelist: Optional iterable of tickers to include for price import only
        date_start: Optional start date (YYYY-MM-DD) for price import
        date_end: Optional end date (YYYY-MM-DD) for price import
    """
    print(f"Creating SQLite database at: {DB_PATH}")
    with sqlite3.connect(DB_PATH) as con:
        _fast_pragmas(con, fast=True)

        # Financial statement data
        if not only_prices:
            print("Processing financial statements...")
            files = {
                "balance_sheet": DATA_DIR / "us-balance-ttm.csv",
                "cash_flow": DATA_DIR / "us-cashflow-ttm.csv",
                "income": DATA_DIR / "us-income-ttm.csv",
            }

            # Define data types to reduce SQLite type inference overhead
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

        # Price data - optional skip (for external script pre-import)
        if os.getenv("SKIP_PRICES") or skip_prices:
            print("Skipping price data import due to SKIP_PRICES=1")
        else:
            print("Processing price data...")
            price_csv = DATA_DIR / "us-shareprices-daily.csv"
            # Schema file (prefer schema_prices.sql, compatible with old schema.sql) located in project root
            sql_dir = DATA_DIR.parent / "sql"
            preferred = sql_dir / "schema_prices.sql"
            fallback = sql_dir / "schema.sql"
            schema_sql = preferred if preferred.exists() else fallback

            if price_csv.exists():
                # Check file size, prioritize CLI import for large files
                file_size_mb = price_csv.stat().st_size / (1024 * 1024)
                print(f"    - Price data file size: {file_size_mb:.1f} MB")

                # Normalize whitelist and date boundaries once
                wl: set[str] | None = (
                    {str(t).upper().strip() for t in tickers_whitelist}
                    if tickers_whitelist
                    else None
                )
                ds = pd.to_datetime(date_start) if date_start else None
                de = pd.to_datetime(date_end) if date_end else None

                # Determine if filters are provided; if so, skip CLI fast path
                has_filters = (wl is not None and len(wl) > 0) or (ds is not None) or (
                    de is not None
                )

                cli_success = False
                if not has_filters and _check_sqlite3_cli() and schema_sql.exists():
                    print("    - SQLite CLI available, attempting fast import...")
                    cli_success = _import_prices_with_cli(price_csv, DB_PATH, schema_sql)

                if not cli_success:
                    if has_filters:
                        print(
                            "    - Filters provided (tickers/date); using pandas chunked import with filtering..."
                        )
                    else:
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
                        tickers_whitelist=wl,
                        date_start=ds,
                        date_end=de,
                    )
                    print(f"    - Loaded {rows} rows into share_prices")

                    # Create indexes for pandas import
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

        # Financial statement indexes: create once and align with queries
        if not only_prices:
            print("Creating optimized indexes for financial data...")
            con.executescript("""
            -- Financial statements: group by Ticker, year and take latest by date_known
            CREATE INDEX IF NOT EXISTS idx_bs_ty_date  ON balance_sheet (Ticker, year, date_known DESC);
            CREATE INDEX IF NOT EXISTS idx_cf_ty_date  ON cash_flow     (Ticker, year, date_known DESC);
            CREATE INDEX IF NOT EXISTS idx_in_ty_date  ON income        (Ticker, year, date_known DESC);
            """)

        _fast_pragmas(con, fast=False)

    print("Database creation complete!")


if __name__ == "__main__":
    main()
