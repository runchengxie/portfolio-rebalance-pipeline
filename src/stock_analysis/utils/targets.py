"""Targets JSON utilities.

Defines a minimal, editable schema for live rebalance targets that is
decoupled from AI pick/backtest artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import json


SCHEMA_VERSION = 1


@dataclass
class Targets:
    tickers: list[str]
    asof: str | None = None
    source: str | None = None
    weights: dict[str, float] | None = None
    notes: str | None = None


def write_targets_json(
    out_path: Path,
    tickers: list[str],
    asof: str | None = None,
    source: str | None = "ai_pick",
    weights: dict[str, float] | None = None,
    notes: str | None = None,
) -> Path:
    """Write targets JSON in a simple, editable format.

    Schema:
    {
      "schema_version": 1,
      "source": "ai_pick|manual|preliminary",
      "asof": "YYYY-MM-DD",
      "tickers": ["AAPL", ...],
      "weights": {"AAPL": 0.12, ...} | null,
      "notes": "..." | null
    }
    """
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source": source,
        "asof": asof,
        "tickers": [str(t).upper().strip() for t in (tickers or []) if str(t).strip()],
        "weights": weights or None,
        "notes": notes or None,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


def read_targets_json(path: Path) -> Targets:
    """Read targets JSON and return structured data."""
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    tickers = [str(t).upper().strip() for t in (raw.get("tickers") or []) if t]
    asof = raw.get("asof") or None
    source = raw.get("source") or None
    weights = raw.get("weights") or None
    notes = raw.get("notes") or None
    return Targets(tickers=tickers, asof=asof, source=source, weights=weights, notes=notes)

