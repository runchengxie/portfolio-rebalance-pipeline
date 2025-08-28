"""LongPort 账户命令

处理账户信息查询的命令逻辑。
"""

from ..renderers.jsonout import render_multiple_account_snapshots_json
from ..renderers.table import render_multiple_account_snapshots
from ..services.account_snapshot import get_multiple_account_snapshots
from ..utils.logging import get_logger

logger = get_logger(__name__)


def run_lb_account(
    env: str = "test",
    only_funds: bool = False,
    only_positions: bool = False,
    fmt: str = "table",
) -> int:
    """运行LongPort账户总览

    Args:
        env: 环境选择（test/real/both）
        only_funds: 只显示资金信息
        only_positions: 只显示持仓信息
        fmt: 输出格式（table/json）

    Returns:
        int: 退出码（0表示成功）
    """
    try:
        # 确定要查询的环境
        envs = ["test", "real"] if env == "both" else [env]

        # 获取账户快照
        snapshots = get_multiple_account_snapshots(envs)

        # 渲染输出
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
