"""LongPort 调仓命令

处理仓位调整的命令逻辑。
"""

from pathlib import Path

from ..renderers.table import render_rebalance_plan
from ..services.account_snapshot import get_account_snapshot, get_quotes
from ..services.rebalancer import RebalanceService
from ..utils.excel import read_latest_sheet_tickers
from ..utils.logging import get_logger

logger = get_logger(__name__)


def run_lb_rebalance(
    input_file: str, account: str = "main", dry_run: bool = True, env: str = "test"
) -> int:
    """运行LongPort差额调仓

    基于真实账户快照，计算目标仓位与当前持仓的差额，执行调仓操作。
    无论test还是real环境，都统一走一条路径：先获取账户快照，计算差额，再决定是否真实下单。

    Args:
        input_file: AI选股结果文件路径
        account: 账户名称
        dry_run: 是否为干跑模式
        env: 环境选择（test或real）

    Returns:
        int: 退出码（0表示成功）
    """
    try:
        # 允许 Real 环境干跑：读取真实账户快照，但不下单
        if env == "real" and dry_run:
            logger.warning("Real 环境干跑：只读取真实账户快照，不会下单。")
        if env == "real" and not dry_run:
            logger.warning("警告：将实际在 REAL 环境下下单。风险自负。")

        logger.info(f"正在读取AI选股结果文件: {input_file}")
        logger.info(f"账户: {account}")
        logger.info(f"环境: {env.upper()}")
        logger.info(f"模式: {'干跑模式（只打印）' if dry_run else '实际执行模式'}")

        # 检查文件是否存在
        file_path = Path(input_file)
        if not file_path.exists():
            logger.error(f"文件不存在: {input_file}")
            return 1

        # 读取目标股票列表
        try:
            tickers, sheet_name = read_latest_sheet_tickers(file_path)
            logger.info(
                f"成功读取文件，使用 sheet: {sheet_name}，包含 {len(tickers)} 条记录"
            )
        except Exception as e:
            logger.error(f"读取Excel文件失败：{e}")
            return 1

        # 获取账户快照（不取行情，避免重复打点）
        account_snapshot = get_account_snapshot(env=env, include_quotes=False)

        # 统一一次性取行情：目标股票 + 现有持仓
        target_syms = {t.strip().upper() for t in tickers}
        held_syms = {p.symbol for p in account_snapshot.positions}
        all_syms = target_syms | held_syms
        if all_syms:
            quote_objs = get_quotes(list(all_syms), env)
            quote_map = {k: v.price for k, v in quote_objs.items()}
        else:
            quote_map = {}

        # 初始化调仓服务
        rebalance_service = RebalanceService(env=env)

        try:
            # 制定调仓计划
            rebalance_result = rebalance_service.plan_rebalance(
                tickers, account_snapshot, quotes=quote_map
            )
            rebalance_result.dry_run = dry_run
            rebalance_result.sheet_name = sheet_name

            # 执行订单
            executed_orders = rebalance_service.execute_orders(
                rebalance_result.orders, dry_run
            )
            rebalance_result.orders = executed_orders

            # 保存审计日志
            log_file = rebalance_service.save_audit_log(rebalance_result, dry_run)

            # 渲染输出
            output = render_rebalance_plan(rebalance_result)
            print(output)

            logger.info(f"审计日志已保存到: {log_file}")

            return 0

        finally:
            rebalance_service.close()

    except ImportError as e:
        logger.error(f"无法导入必要模块: {e}")
        return 1
    except Exception as e:
        logger.error(f"仓位调整失败：{e}")
        return 1
