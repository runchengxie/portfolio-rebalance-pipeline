"""Targets command

Generate and manage live rebalance target files (JSON), decoupled from
backtest AI pick outputs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

import pandas as pd

from ..logging import get_logger
from ..utils.paths import AI_PORTFOLIO_FILE, OUTPUTS_DIR, AI_PORTFOLIO_JSON_DIR
from ..utils.targets import write_targets_json
from ..io.excel import (
    get_sheet_names,
    pick_latest_sheet,
    read_excel_data,
)
from ..utils.portfolio_json import (
    pick_latest_ai_json,
    read_ai_json_tickers,
    find_ai_json_for_date,
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
    """Generate a targets JSON from latest (or specified) AI/prelim result.

    Default behavior (source=ai):
    - Prefer per-date AI JSON under outputs/ai_pick by filename date.
      If `asof` is provided, pick that date's JSON; otherwise pick the latest.
    - If `excel` is explicitly provided, fall back to reading the Excel sheet.

    Args:
        source: "ai" or "preliminary" (currently only used for semantics; default is ai)
        excel: Optional Excel path override (forces Excel workflow)
        out: Output JSON path; defaults to outputs/targets/{asof}.json
        asof: Optional date (YYYY-MM-DD). Defaults to date from latest JSON filename.
    """
    try:
        # 1) JSON-first for AI picks
        if source == "ai" and excel is None:
            # Find file by asof or pick latest
            json_fp: Path | None
            if asof:
                json_fp = find_ai_json_for_date(asof, AI_PORTFOLIO_JSON_DIR)
                if not json_fp:
                    logger.error(
                        f"未找到指定日期的AI JSON: {AI_PORTFOLIO_JSON_DIR}/**/{asof}.json"
                    )
                    return 1
            else:
                json_fp = pick_latest_ai_json(AI_PORTFOLIO_JSON_DIR)
                if not json_fp:
                    logger.error(
                        f"未找到AI JSON文件，请先运行 ai-pick 或 export excel-to-json 生成。根目录: {AI_PORTFOLIO_JSON_DIR}"
                    )
                    return 1

            ai = read_ai_json_tickers(json_fp)
            tickers = ai.tickers
            asof_date = ai.asof

            if not tickers:
                logger.error("未找到有效的股票代码")
                return 1

            out_path = Path(out) if out else (OUTPUTS_DIR / "targets" / f"{asof_date}.json")
            write_targets_json(
                out_path, tickers=tickers, asof=asof_date, source="ai_pick"
            )
            logger.info(
                f"已从AI JSON生成调仓目标: {json_fp.name} -> {out_path}（{len(tickers)} 只）"
            )
            return 0

        # 2) Excel fallback (explicit) or for preliminary flow
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
        write_targets_json(
            out_path,
            tickers=tickers,
            asof=sheet,
            source=("ai_pick" if source == "ai" else source),
        )
        logger.info(f"已生成调仓目标 JSON: {out_path}")
        return 0
    except Exception as e:
        logger.error(f"生成调仓目标失败：{e}")
        return 1
