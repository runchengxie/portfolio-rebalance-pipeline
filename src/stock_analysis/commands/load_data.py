"""Data loading command

Handles command logic for data loading.
"""

from ..utils.logging import get_logger

logger = get_logger(__name__)


def run_load_data(
    data_dir: str | None = None, skip_prices: bool = False, only_prices: bool = False
) -> int:
    """Run data loading

    Args:
        data_dir: Data directory path (optional)

    Returns:
        int: Exit code (0 indicates success)
    """
    try:
        logger.info("正在加载数据到数据库...")

        if data_dir:
            # If data directory is specified, need to temporarily modify path configuration
            logger.info(f"使用指定数据目录：{data_dir}")
            # Path configuration logic can be added here

        from ..load_data_to_db import main as load_main

        # Execute loading (supports importing only prices or skipping prices)
        load_main(skip_prices=skip_prices, only_prices=only_prices)

        logger.info("数据加载完成！")
        return 0

    except ImportError as e:
        logger.error(f"无法导入数据加载模块: {e}")
        return 1
    except Exception as e:
        logger.error(f"数据加载失败：{e}")
        return 1
