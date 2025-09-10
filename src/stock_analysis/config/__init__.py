"""Configuration file loading module.

Provides unified configuration file loading functionality.
"""

import datetime
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None

from dateutil.relativedelta import relativedelta


def load_cfg() -> dict[str, Any]:
    """Load configuration file.

    Prioritize reading config/config.yaml, then config.yaml in project root

    Returns:
        Dict[str, Any]: Configuration dictionary
    """
    # Project root directory
    root = Path(__file__).resolve().parents[3]

    # Try to load config file from multiple locations
    candidates = [
        root / "config" / "config.yaml",  # Priority: config/config.yaml
        root / "config.yaml",  # Alternative: config.yaml in project root
    ]

    config_path = None
    for p in candidates:
        if p.exists():
            config_path = p
            break

    if config_path is None:
        # Default configuration: return to dynamic mode, consistent with existing logic
        return {
            "backtest": {
                "period_mode": "dynamic",
                "buffer": {"months": 3, "days": 10},
                "initial_cash": 1000000,  # Unified initial capital
            }
        }

    if yaml is None:
        raise ImportError(
            "PyYAML is required to read config.yaml. Install it with: pip install PyYAML"
        )

    try:
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        return config
    except Exception as e:
        print(
            f"[WARNING] Failed to load config.yaml: {e}. Using default configuration."
        )
        return {
            "backtest": {
                "period_mode": "dynamic",
                "buffer": {"months": 3, "days": 10},
                "initial_cash": {"ai": 1000000, "quant": 1000000, "spy": 100000},
            }
        }


def get_backtest_period(portfolios: dict = None) -> tuple[datetime.date, datetime.date]:
    """Get backtest time period.

    Args:
        portfolios: Portfolio dictionary, only used in dynamic mode

    Returns:
        Tuple[datetime.date, datetime.date]: (start_date, end_date)
    """
    config = load_cfg()
    backtest_config = config.get("backtest", {})

    period_mode = backtest_config.get("period_mode", "dynamic")

    if period_mode == "fixed":
        # Fixed time mode
        start_str = backtest_config.get("start", "2021-04-02")
        end_str = backtest_config.get("end", "2025-07-02")

        # Handle possible date formats
        if isinstance(start_str, str):
            start_date = datetime.datetime.strptime(start_str, "%Y-%m-%d").date()
        else:
            start_date = start_str  # Already a date object

        if isinstance(end_str, str):
            end_date = datetime.datetime.strptime(end_str, "%Y-%m-%d").date()
        else:
            end_date = end_str  # Already a date object

        return start_date, end_date

    else:
        # Dynamic time mode
        if not portfolios:
            raise ValueError("Dynamic mode requires portfolios data")

        # Get time range from portfolio data
        first_rebalance_date = min(portfolios.keys())
        last_rebalance_date = max(portfolios.keys())

        # Add buffer time
        buffer_config = backtest_config.get("buffer", {"months": 3, "days": 10})
        buffer_months = buffer_config.get("months", 3)
        buffer_days = buffer_config.get("days", 10)

        start_date = first_rebalance_date
        end_date = last_rebalance_date + relativedelta(
            months=buffer_months, days=buffer_days
        )

        return start_date, end_date


def get_initial_cash(strategy: str) -> float:
    """Get initial cash amount.

    Supports two configuration formats:
    1. Unified capital: initial_cash: 1000000
    2. Strategy-specific configuration: initial_cash: {ai: 1000000, quant: 1000000, spy: 1000000}

    Args:
        strategy: Strategy name ('ai', 'quant', 'spy')

    Returns:
        float: Initial cash amount
    """
    config = load_cfg()
    backtest_config = config.get("backtest", {})
    initial_cash_config = backtest_config.get("initial_cash", 1000000)

    # Support two formats: number (unified capital) or dictionary (strategy-specific configuration)
    if isinstance(initial_cash_config, dict):
        # Dictionary format: configure by strategy
        return float(initial_cash_config.get(strategy, 1000000))
    else:
        # Number format: unified capital
        return float(initial_cash_config)
