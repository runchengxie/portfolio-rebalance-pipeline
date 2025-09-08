"""LongPort account command

Handles command logic for account information queries.
"""

from ..renderers.jsonout import render_multiple_account_snapshots_json
from ..renderers.table import render_multiple_account_snapshots
from ..services.account_snapshot import get_account_snapshot
from ..utils.logging import get_logger

logger = get_logger(__name__)


def run_lb_account(
    only_funds: bool = False,
    only_positions: bool = False,
    fmt: str = "table",
) -> int:
    """Run LongPort account overview

    Args:
        only_funds: Show only fund information
        only_positions: Show only position information
        fmt: Output format (table/json)

    Returns:
        int: Exit code (0 indicates success)
    """
    try:
        # Get real account snapshot
        snapshot = get_account_snapshot(env="real")
        snapshots = [snapshot]

        # Render output
        if fmt == "json":
            output = render_multiple_account_snapshots_json(snapshots)
        else:
            output = render_multiple_account_snapshots(
                snapshots, only_funds, only_positions
            )

        print(output)

        return 0

    except ImportError as e:
        logger.error(f"无法导入LongPort模块: {e}")
        logger.error("请确保已安装 longport 包：pip install longport")
        return 1
    except Exception as e:
        logger.error(f"账户总览失败：{e}")
        return 1
