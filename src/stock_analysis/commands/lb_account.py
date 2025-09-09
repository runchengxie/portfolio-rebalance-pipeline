"""LongPort account command

Handles command logic for account information queries.
"""

import sys

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
        # Resolve conflicting flags: funds take precedence over positions
        if only_funds and only_positions:
            only_positions = False

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
        msg = f"Failed to import LongPort module: {e}"
        logger.error(msg)
        print(msg, file=sys.stderr)
        fix_msg = "Please ensure the 'longport' package is installed: pip install longport"
        logger.error(fix_msg)
        print(fix_msg, file=sys.stderr)
        return 1
    except Exception as e:
        msg = f"Failed to get account overview: {e}"
        logger.error(msg)
        print(msg, file=sys.stderr)
        return 1
