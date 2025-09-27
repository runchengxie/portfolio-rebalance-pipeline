#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rf_tools.py
A single-file utility that can be BOTH:
- imported by your backtest to get risk-free (3M T-Bill, DGS3MO) and compute Sharpe;
- run as a CLI to seed/extend cache based on config or explicit dates.

Env:
  FRED_API_KEY  your FRED API key (required when fetching)

Install:
  pip install pandas fredapi pyyaml

Examples:
  # 1) Seed/extend cache by reading your config and aligning to your price calendar
  python rf_tools.py seed-cache --config config/config.yaml \
    --align-with data/us-shareprices-daily.csv --date-col Date \
    --cache data/risk_free_usd.csv

  # 2) Seed/extend cache by explicit date range
  python rf_tools.py fetch --start 2016-01-01 --end 2025-12-31 --cache data/risk_free_usd.csv

  # 3) Compute Sharpe given an equity CSV (date + equity value)
  python rf_tools.py calc-sharpe --equity-csv outputs/equity.csv --date-col date --value-col equity \
    --cache data/risk_free_usd.csv

  # 4) Programmatic use
  from rf_tools import get_rf_daily_for_index, compute_sharpe_from_equity
"""

from __future__ import annotations
import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import pandas as pd

PERIODS = 252
SERIES_ID = "DGS3MO"  # 3M T-Bill (investment basis)

@dataclass
class RFConfig:
    cache_path: str = "data/risk_free_usd.csv"
    meta_path: str = "data/risk_free_usd.csv.meta.json"
    series_id: str = SERIES_ID

# ---------------- core helpers ----------------

def _annual_to_daily(s: pd.Series, periods: int = PERIODS) -> pd.Series:
    return (1.0 + s).pow(1.0 / periods) - 1.0

def _load_cache(path: str) -> Optional[pd.DataFrame]:
    try:
        df = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
        return df
    except Exception:
        return None

def _write_cache(df: pd.DataFrame, cfg: RFConfig, source: str, args: dict) -> None:
    df_out = df.reset_index().rename(columns={"index": "date"})
    Path(cfg.cache_path).parent.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(cfg.cache_path, index=False)
    meta = {
        "source": source,
        "series_id": cfg.series_id,
        "periods_per_year": PERIODS,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "args": args,
        "rows": int(df_out.shape[0]),
    }
    with open(cfg.meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

def _fetch_from_fred(start: str, end: str, series_id: str = SERIES_ID) -> pd.Series:
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        raise RuntimeError("FRED_API_KEY not set in environment.")
    try:
        from fredapi import Fred  # type: ignore
    except Exception as e:
        raise RuntimeError("fredapi is not installed. pip install fredapi") from e
    fred = Fred(api_key=api_key)
    s = fred.get_series(series_id, observation_start=start, observation_end=end)
    s = s.astype(float).div(100.0)  # percent -> decimal
    s.index = pd.to_datetime(s.index)
    s.name = "rf_annual"
    return s.sort_index()

def _ensure_coverage(existing: Optional[pd.DataFrame], need_start: pd.Timestamp, need_end: pd.Timestamp, cfg: RFConfig) -> pd.DataFrame:
    if existing is None or existing.empty:
        s = _fetch_from_fred(need_start.strftime("%Y-%m-%d"), need_end.strftime("%Y-%m-%d"), cfg.series_id)
        df = pd.DataFrame({"rf_annual": s}).sort_index()
        df["rf_daily"] = _annual_to_daily(df["rf_annual"])
        _write_cache(df, cfg, source="FRED", args={"start": str(need_start.date()), "end": str(need_end.date())})
        return df

    have_start, have_end = existing.index.min(), existing.index.max()
    frames = [existing]
    need_fetch = False
    if need_start < have_start:
        s_fetch = _fetch_from_fred((need_start - pd.Timedelta(days=3)).strftime("%Y-%m-%d"),
                                   (have_start + pd.Timedelta(days=3)).strftime("%Y-%m-%d"),
                                   cfg.series_id)
        df_add = pd.DataFrame({"rf_annual": s_fetch}).sort_index()
        df_add["rf_daily"] = _annual_to_daily(df_add["rf_annual"])
        frames.append(df_add); need_fetch = True
    if need_end > have_end:
        s_fetch = _fetch_from_fred((have_end - pd.Timedelta(days=3)).strftime("%Y-%m-%d"),
                                   (need_end + pd.Timedelta(days=3)).strftime("%Y-%m-%d"),
                                   cfg.series_id)
        df_add = pd.DataFrame({"rf_annual": s_fetch}).sort_index()
        df_add["rf_daily"] = _annual_to_daily(df_add["rf_annual"])
        frames.append(df_add); need_fetch = True

    merged = pd.concat(frames, axis=0).sort_index().drop_duplicates(keep="last")
    if need_fetch:
        _write_cache(merged, cfg, source="FRED", args={"start": str(need_start.date()), "end": str(need_end.date())})
    return merged

def get_rf_daily_for_index(index: pd.DatetimeIndex, cache_path: str = "data/risk_free_usd.csv") -> pd.Series:
    """Return rf_daily aligned to provided index. Fetches and caches FRED if needed."""
    if not isinstance(index, pd.DatetimeIndex):
        raise TypeError("index must be a pandas.DatetimeIndex")
    cfg = RFConfig(cache_path=cache_path, meta_path=f"{cache_path}.meta.json")
    cache = _load_cache(cfg.cache_path)
    need_start, need_end = pd.to_datetime(index.min()), pd.to_datetime(index.max())
    df = _ensure_coverage(cache, need_start, need_end, cfg)
    return df["rf_daily"].reindex(index).ffill().bfill()

def compute_sharpe_from_equity(equity_curve: pd.Series, rf_daily: pd.Series, periods: int = PERIODS) -> float:
    ret = equity_curve.pct_change().dropna()
    ex = ret - rf_daily.reindex(ret.index).ffill().bfill()
    mu, sigma = ex.mean(), ex.std(ddof=1)
    return float("nan") if sigma == 0 else (mu / sigma) * (periods ** 0.5)

# ---------------- config-driven seeding ----------------

def _parse_date(s: Any) -> Optional[pd.Timestamp]:
    if s is None:
        return None
    try:
        return pd.to_datetime(s)
    except Exception:
        return None

DATE_KEYS_START = {"start", "start_date", "from", "window_start", "begin", "begin_date"}
DATE_KEYS_END   = {"end", "end_date", "to", "window_end", "finish", "finish_date"}

def _search_dates(obj: Any) -> Tuple[Optional[pd.Timestamp], Optional[pd.Timestamp]]:
    start, end = None, None
    def rec(o: Any):
        nonlocal start, end
        if isinstance(o, dict):
            for k, v in o.items():
                kl = str(k).strip().lower().replace("-", "_")
                if kl in DATE_KEYS_START and start is None:
                    start = _parse_date(v) or start
                if kl in DATE_KEYS_END and end is None:
                    end = _parse_date(v) or end
            for _, v in o.items():
                rec(v)
        elif isinstance(o, list):
            for it in o:
                rec(it)
    rec(obj)
    return start, end

def _load_yaml(path: str) -> Optional[Dict[str, Any]]:
    try:
        import yaml  # PyYAML
    except Exception:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None

def _infer_window_from_config(cfg_path: Optional[str]) -> Tuple[Optional[pd.Timestamp], Optional[pd.Timestamp]]:
    if not cfg_path:
        return None, None
    data = _load_yaml(cfg_path)
    if not data:
        return None, None
    return _search_dates(data)

def _build_index(start: Optional[pd.Timestamp], end: Optional[pd.Timestamp],
                 align_with: Optional[str], date_col: Optional[str]) -> pd.DatetimeIndex:
    if align_with:
        ref = pd.read_csv(align_with)
        candidates = [date_col] if date_col else []
        candidates += ["date", "Date", "DATE", "pricedate", "timestamp", "datetime"]
        dcol = next((c for c in candidates if c and c in ref.columns), None)
        if not dcol:
            raise RuntimeError("Could not infer date column from --align-with file; specify --date-col.")
        ref[dcol] = pd.to_datetime(ref[dcol])
        return pd.DatetimeIndex(sorted(ref[dcol].dropna().unique()))
    if start is not None and end is not None:
        return pd.bdate_range(start, end, freq="B")
    raise RuntimeError("No dates found. Provide --start/--end or --align-with.")

# ---------------- CLI ----------------

def _cli_seed_cache(args: argparse.Namespace) -> None:
    start = pd.to_datetime(args.start) if args.start else None
    end   = pd.to_datetime(args.end) if args.end else None
    if not (start and end) and args.config:
        c_start, c_end = _infer_window_from_config(args.config)
        start = start or c_start
        end   = end or c_end
    index = _build_index(start, end, args.align_with, args.date_col)
    rf = get_rf_daily_for_index(index, cache_path=args.cache)
    print(f"RF cache ready at {args.cache} with {len(rf)} aligned rows.")

def _cli_fetch(args: argparse.Namespace) -> None:
    if not args.start or not args.end:
        raise SystemExit("--start and --end are required for fetch")
    # Build a simple business-day index in range to drive coverage
    index = pd.bdate_range(pd.to_datetime(args.start), pd.to_datetime(args.end), freq="B")
    rf = get_rf_daily_for_index(index, cache_path=args.cache)
    print(f"Fetched/updated RF cache at {args.cache} with {len(rf)} aligned rows.")

def _cli_calc_sharpe(args: argparse.Namespace) -> None:
    df = pd.read_csv(args.equity_csv)
    dcol = args.date_col or "date"
    vcol = args.value_col or "equity"
    if dcol not in df.columns or vcol not in df.columns:
        raise SystemExit(f"Columns not found. Need --date-col and --value-col. Got: {list(df.columns)[:6]} ...")
    df[dcol] = pd.to_datetime(df[dcol])
    equity = df.set_index(dcol)[vcol].sort_index()
    rf_daily = get_rf_daily_for_index(equity.index, cache_path=args.cache)
    sharpe = compute_sharpe_from_equity(equity, rf_daily, periods=args.periods)
    print(f"Sharpe (annualized): {sharpe:.6f}")

def main():
    ap = argparse.ArgumentParser(prog="rf_tools", description="Risk-free loader and Sharpe utilities (FRED DGS3MO).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_seed = sub.add_parser("seed-cache", help="Seed/extend cache using config and/or alignment CSV.")
    ap_seed.add_argument("--config", type=str, default="config/config.yaml")
    ap_seed.add_argument("--align-with", type=str, default=None)
    ap_seed.add_argument("--date-col", type=str, default=None)
    ap_seed.add_argument("--start", type=str, default=None)
    ap_seed.add_argument("--end", type=str, default=None)
    ap_seed.add_argument("--cache", type=str, default="data/risk_free_usd.csv")
    ap_seed.set_defaults(func=_cli_seed_cache)

    ap_fetch = sub.add_parser("fetch", help="Fetch/extend cache for an explicit date range.")
    ap_fetch.add_argument("--start", type=str, required=True)
    ap_fetch.add_argument("--end", type=str, required=True)
    ap_fetch.add_argument("--cache", type=str, default="data/risk_free_usd.csv")
    ap_fetch.set_defaults(func=_cli_fetch)

    ap_sharpe = sub.add_parser("calc-sharpe", help="Compute Sharpe from an equity CSV.")
    ap_sharpe.add_argument("--equity-csv", type=str, required=True)
    ap_sharpe.add_argument("--date-col", type=str, default="date")
    ap_sharpe.add_argument("--value-col", type=str, default="equity")
    ap_sharpe.add_argument("--cache", type=str, default="data/risk_free_usd.csv")
    ap_sharpe.add_argument("--periods", type=int, default=PERIODS)
    ap_sharpe.set_defaults(func=_cli_calc_sharpe)

    args = ap.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
