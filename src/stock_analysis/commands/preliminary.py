"""量化初筛命令

处理量化初筛选股的命令逻辑。
"""

from ..utils.logging import get_logger

logger = get_logger(__name__)


def run_preliminary(output_dir: str | None = None) -> int:
    """运行量化初筛选股

    Args:
        output_dir: 输出目录路径（可选）

    Returns:
        int: 退出码（0表示成功）
    """
    try:
        logger.info("正在运行量化初筛选股...")

        if output_dir:
            logger.info(f"输出目录：{output_dir}")
            # 这里可以添加输出目录配置逻辑

        from ..preliminary_selection import main as prelim_main

        prelim_main()

        logger.info("量化初筛选股完成！")
        return 0

    except ImportError as e:
        logger.error(f"无法导入量化初筛模块: {e}")
        return 1
    except Exception as e:
        logger.error(f"量化初筛选股失败：{e}")
        return 1
