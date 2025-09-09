"""LongPort account command

Handles command logic for account information queries.
"""

import sys

from ..renderers.jsonout import render_multiple_account_snapshots_json
from ..renderers.table import render_multiple_account_snapshots
from ..utils.logging import get_logger

try:  # pragma: no cover - optional dependency
    from ..services.account_snapshot import get_account_snapshot
except Exception:  # pragma: no cover

    def get_account_snapshot(*args, **kwargs):  # type: ignore[override]
        raise ImportError("longport dependencies are not installed")


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
        msg1 = f"Failed to import LongPort module: {e}"
        msg2 = (
            "Please make sure the 'longport' package is installed: pip install longport"
        )
        logger.error(msg1)
        logger.error(msg2)
        print(msg1, file=sys.stderr)
        print(msg2, file=sys.stderr)
        return 1
    except Exception as e:
        msg = f"Failed to get account overview: {e}"
        logger.error(msg)
        print(msg, file=sys.stderr)
        return 1
