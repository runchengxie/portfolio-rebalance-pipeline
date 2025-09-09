"""LongPort quote command

Handles command logic for stock quote queries.
"""

from ..renderers.table import render_quotes
from ..services.account_snapshot import get_quotes
from ..utils.logging import get_logger

logger = get_logger(__name__)


def run_lb_quote(tickers: list[str]) -> int:
    """Run LongPort real-time quote query

    Args:
        tickers: List of stock symbols
        env: Environment selection (test or real)

    Returns:
        int: Exit code (0 indicates success)
    """
    try:
        logger.info(f"正在获取 {', '.join(tickers)} 的实时报价... (REAL)")

        # Get quote data
        quotes_dict = get_quotes(tickers)
        quotes_list = list(quotes_dict.values())

        # Render output
        output = render_quotes(quotes_list)
        print(output)

        return 0

    except ImportError as e:
        logger.error(f"无法导入LongPort模块: {e}")
        logger.error("请确保已安装 longport 包：pip install longport")
        print(f"Error importing LongPort module: {e}")
        return 1
    except Exception as e:
        logger.error(f"获取报价失败：{e}")
        return 1
