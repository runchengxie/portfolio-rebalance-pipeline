#!/usr/bin/env python3
"""
check_spy_dividends.py
----------------------------------
Quick sanity-check that your SPY data contains dividend cashflows
and show how much they matter versus price-only returns.

Usage:
  python tools/check_spy_dividends.py \
      --db data/financial_data.db \
      --start 2016-10-04 --end 2025-08-31 \
      --ticker SPY

Outputs a tiny report with:
- count and sum of non-zero dividend rows
- price-only return vs. total return (price + dividends reinvested)
- optional comparison to Adj. Close if present in DB
"""

from __future__ import annotations
import argparse
from dataclasses import dataclass
from pathlib import Path
import sqlite3
import sys
import pandas as pd


@dataclass
class Window:
    start: str
    end: str


def _read_window_from_config(config_path: Path) -> Window | None:
    """Best-effort parse of config/config.yaml without requiring pyyaml.
    Falls back to None if not found or parse fails.
    """
    try:
        txt = config_path.read_text(encoding="utf-8")
    except Exception:
        return None

    def _grab(key: str) -> str | None:
        import re
        m = re.search(rf'^{key}\s*:\s*([0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}})', txt, flags=re.M)
        return m.group(1) if m else None

    start = _grab("start")
    end = _grab("end")
    if start and end:
        return Window(start, end)
    return None


def load_spy_df(db_path: Path, ticker: str, start: str, end: str) -> pd.DataFrame:
    with sqlite3.connect(db_path) as con:
        q = """
        SELECT Date, Open, High, Low, Close, "Adj. Close", Volume, Dividend
        FROM share_prices
        WHERE Ticker = ? AND Date >= ? AND Date <= ?
        ORDER BY Date
        """
        df = pd.read_sql_query(q, con, params=[ticker, start, end], parse_dates=["Date"])
    if df.empty:
        raise SystemExit(f"No data for {ticker} in {db_path} between {start} and {end}.")
    df = df.set_index("Date").sort_index()
    # Make sure Dividend column exists
    if "Dividend" not in df.columns:
        df["Dividend"] = 0.0
    df["Dividend"] = df["Dividend"].fillna(0.0).astype(float)
    return df


def compute_total_return_series(close: pd.Series, dividend: pd.Series) -> pd.Series:
    """Daily total return with dividend reinvestment (price return + dividend yield)."""
    price_ret = close.pct_change().fillna(0.0)
    # Dividend per share paid on day t, divided by previous close -> yield on that day
    div_yield = (dividend / close.shift(1)).fillna(0.0)
    total_daily = (1.0 + price_ret + div_yield).clip(lower=0)  # guard tiny negatives
    total_curve = total_daily.cumprod()
    return total_curve


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=Path("data/financial_data.db"))
    ap.add_argument("--start", type=str, default=None)
    ap.add_argument("--end", type=str, default=None)
    ap.add_argument("--ticker", type=str, default="SPY")
    args = ap.parse_args()

    # Try to infer window from config/config.yaml if not explicitly provided
    if not args.start or not args.end:
        cfg = _read_window_from_config(Path("config/config.yaml"))
        if cfg:
            args.start = args.start or cfg.start
            args.end = args.end or cfg.end
    if not args.start or not args.end:
        print("[warn] Missing --start/--end and could not parse config/config.yaml; "
              "defaulting to entire range in DB for the ticker.", file=sys.stderr)

    df = load_spy_df(args.db, args.ticker.upper().strip(), args.start or "1900-01-01", args.end or "2100-12-31")

    has_adj = "Adj. Close" in df.columns and df["Adj. Close"].notna().any()
    nonzero_div = int((df["Dividend"].fillna(0) != 0).sum())
    div_sum = float(df["Dividend"].sum())

    # Build curves (normalized to 1 on first available row)
    close_curve = (1.0 + df["Close"].pct_change().fillna(0.0)).cumprod()
    tr_curve = compute_total_return_series(df["Close"], df["Dividend"])
    if has_adj:
        adj_curve = (1.0 + df["Adj. Close"].pct_change().fillna(0.0)).cumprod()
    else:
        adj_curve = None

    def _to_pct(x: float) -> str:
        return f"{x*100:.2f}%"

    price_only_ret = close_curve.iloc[-1] - 1.0
    total_ret = tr_curve.iloc[-1] - 1.0
    adj_ret = (adj_curve.iloc[-1] - 1.0) if adj_curve is not None else None

    print("\n=== SPY Dividend Sanity Check ===")
    print(f"DB:        {args.db}")
    print(f"Ticker:    {args.ticker}")
    print(f"Window:    {df.index.min().date()} -> {df.index.max().date()}")
    print(f"Div rows:  {nonzero_div} non-zero rows, sum per-share: {div_sum:.2f}")
    print("Returns over the window:")
    print(f" - Price-only (Close):        {_to_pct(price_only_ret)}")
    print(f" - Total return (Close+Div):  {_to_pct(total_ret)}")
    if adj_ret is not None:
        print(f" - Using Adj. Close:          {_to_pct(adj_ret)}")
    delta = total_ret - price_only_ret
    print(f"Dividend lift vs. price-only: {_to_pct(delta)}")

    if nonzero_div == 0 or abs(delta) < 1e-6:
        print("\n[hint] Your SPY path looks like **price-only**. "
              "If your benchmark backtest says 'Total Return' but this delta is ~0, "
              "your strategy probably isn't reinvesting dividends in the SPY path.")
    else:
        print("\n[ok] Dividends appear present and materially change returns.")

    print("\nPro tips:")
    print(" - To make SPY buy-and-hold dividend-aware in your backtest, "
          "handle the `dividend` line in the strategy and rebalance to target after adding cash.")
    print(" - Alternatively, feed a total-return price series (e.g., use Adj. Close if it is dividend-adjusted), "
          "but be consistent with your custom strategy so comparisons stay fair.")


if __name__ == "__main__":
    pd.set_option("display.width", 120)
    main()
