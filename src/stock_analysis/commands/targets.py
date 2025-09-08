"""Targets command

Generate and manage live rebalance target files (JSON), decoupled from
backtest AI pick outputs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

import pandas as pd

from ..utils.logging import get_logger
from ..utils.paths import AI_PORTFOLIO_FILE, OUTPUTS_DIR
from ..utils.targets import write_targets_json
from ..utils.excel import (
    get_sheet_names,
    pick_latest_sheet,
    read_excel_data,
)

logger = get_logger(__name__)


def _extract_tickers_from_df(df: pd.DataFrame) -> list[str]:
    cols = {str(c).lower(): str(c) for c in df.columns}
    col = cols.get("ticker") or cols.get("symbol")
    if not col:
        raise ValueError("未找到 ticker 或 symbol 列")
    vals = (
        df[col].astype(str).str.upper().str.strip().dropna().tolist()
        if not df.empty
        else []
    )
    return [v for v in vals if v and v != "NAN"]


def _latest_sheet_and_tickers(xlsx: Path) -> Tuple[str, list[str]]:
    sheet = pick_latest_sheet(get_sheet_names(xlsx))
    df = read_excel_data(xlsx, sheet_name=sheet)
    tickers = _extract_tickers_from_df(df)
    return sheet, tickers


def run_targets_gen(
    source: str = "ai",
    excel: str | None = None,
    out: str | None = None,
    asof: str | None = None,
) -> int:
    """Generate a targets JSON from latest (or specified) AI/prelim sheet.

    Args:
        source: "ai" or "preliminary" (currently only used for semantics; path default is AI)
        excel: Optional Excel path; defaults to AI portfolio workbook
        out: Output JSON path; defaults to outputs/targets/{asof}.json
        asof: Optional sheet name/date (YYYY-MM-DD). Defaults to latest sheet.
    """
    try:
        xlsx = Path(excel) if excel else AI_PORTFOLIO_FILE
        if not xlsx.exists():
            logger.error(f"文件不存在: {xlsx}")
            return 1

        if asof:
            df = read_excel_data(xlsx, sheet_name=asof)
            tickers = _extract_tickers_from_df(df)
            sheet = asof
        else:
            sheet, tickers = _latest_sheet_and_tickers(xlsx)

        if not tickers:
            logger.error("未找到有效的股票代码")
            return 1

        out_path = Path(out) if out else (OUTPUTS_DIR / "targets" / f"{sheet}.json")
        write_targets_json(out_path, tickers=tickers, asof=sheet, source=("ai_pick" if source == "ai" else source))
        logger.info(f"已生成调仓目标 JSON: {out_path}")
        return 0
    except Exception as e:
        logger.error(f"生成调仓目标失败：{e}")
        return 1

