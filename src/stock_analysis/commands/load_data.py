"""数据加载命令

处理数据加载的命令逻辑。
"""

from ..utils.logging import get_logger

logger = get_logger(__name__)


def run_load_data(
    data_dir: str | None = None, skip_prices: bool = False, only_prices: bool = False
) -> int:
    """运行数据加载

    Args:
        data_dir: 数据目录路径（可选）

    Returns:
        int: 退出码（0表示成功）
    """
    try:
        logger.info("正在加载数据到数据库...")

        if data_dir:
            # 如果指定了数据目录，需要临时修改路径配置
            logger.info(f"使用指定数据目录：{data_dir}")
            # 这里可以添加路径配置逻辑

        from ..load_data_to_db import main as load_main

        # 执行加载（支持只导入价格或跳过价格）
        load_main(skip_prices=skip_prices, only_prices=only_prices)

        logger.info("数据加载完成！")
        return 0

    except ImportError as e:
        logger.error(f"无法导入数据加载模块: {e}")
        return 1
    except Exception as e:
        logger.error(f"数据加载失败：{e}")
        return 1
