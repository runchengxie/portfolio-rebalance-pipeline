"""Command line interface module.

Responsible only for argument parsing and command dispatching, without business logic.
"""

import argparse
import sys

# Re-export command entry functions for tests and external callers
from .commands.ai_pick import run_ai_pick  # noqa: F401
from .commands.backtest import run_backtest  # noqa: F401
from .commands.load_data import run_load_data  # noqa: F401
from .commands.gen_whitelist import run_gen_whitelist  # noqa: F401
from .commands.lb_quote import run_lb_quote  # noqa: F401
from .commands.lb_rebalance import run_lb_rebalance  # noqa: F401
from .commands.lb_account import run_lb_account  # noqa: F401


def create_parser() -> argparse.ArgumentParser:
    """Create command line argument parser.

    Returns:
        argparse.ArgumentParser: Configured argument parser
    """
    parser = argparse.ArgumentParser(
        prog="stockq",
        description="股票量化分析工具 - 基于财务基本面的AI选股与回测系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  stockq --help                    显示帮助信息
  stockq preliminary               运行量化初筛选股
  stockq backtest ai               运行AI选股回测
  stockq backtest quant            运行量化初选回测  
  stockq backtest spy              运行SPY基准回测
  stockq load-data                 加载数据到数据库
  stockq ai-pick                   运行AI选股分析
  stockq lb-quote AAPL MSFT        获取实时报价
  stockq lb-account                查看真实账户总览
  stockq lb-account --funds        只显示资金信息
  stockq lb-account --format json  JSON格式输出
  stockq lb-rebalance results.xlsx             真实账户干跑预览 (Dry-Run)
  stockq lb-rebalance results.xlsx --execute   真实账户实际执行 (谨慎操作)
        """,
    )

    # Add version information
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")

    # Create subcommands
    subparsers = parser.add_subparsers(
        dest="command", help="可用的命令", metavar="COMMAND"
    )

    # Backtest command
    backtest_parser = subparsers.add_parser(
        "backtest", help="运行回测分析", description="运行不同策略的回测分析"
    )
    backtest_parser.add_argument(
        "strategy",
        choices=["ai", "quant", "spy"],
        help="回测策略类型：ai(AI选股), quant(量化初选), spy(SPY基准)",
    )
    backtest_parser.add_argument("--config", type=str, help="配置文件路径（可选）")

    # Data loading command
    load_parser = subparsers.add_parser(
        "load-data",
        help="加载数据到数据库",
        description="从CSV文件加载财务数据和价格数据到SQLite数据库",
    )
    load_parser.add_argument(
        "--data-dir", type=str, help="数据目录路径（可选，默认使用项目data目录）"
    )
    load_parser.add_argument(
        "--tickers-file",
        type=str,
        help="仅导入此清单中的股价（支持 .txt/.csv/.xlsx；文本按行一个ticker）",
    )
    load_parser.add_argument(
        "--date-start",
        type=str,
        help="价格导入起始日期（YYYY-MM-DD，可选）",
    )
    load_parser.add_argument(
        "--date-end",
        type=str,
        help="价格导入结束日期（YYYY-MM-DD，可选）",
    )
    group = load_parser.add_mutually_exclusive_group()
    group.add_argument(
        "--skip-prices",
        action="store_true",
        help="跳过股价数据导入（仅导入财报类表）",
    )
    group.add_argument(
        "--only-prices",
        action="store_true",
        help="仅导入股价数据（跳过财报类表）",
    )

    # Preliminary screening command
    prelim_parser = subparsers.add_parser(
        "preliminary",
        help="运行量化初筛选股",
        description="执行多因子量化初筛，生成候选股票池",
    )
    prelim_parser.add_argument(
        "--output-dir", type=str, help="输出目录路径（可选，默认使用项目outputs目录）"
    )
    prelim_parser.add_argument(
        "--no-excel", action="store_true", help="仅生成JSON，不写Excel/TXT"
    )
    prelim_parser.add_argument(
        "--no-json", action="store_true", help="仅生成Excel/TXT，不写JSON"
    )

    # AI stock picking command
    ai_parser = subparsers.add_parser(
        "ai-pick", help="运行AI选股分析", description="使用AI模型进行股票筛选和分析"
    )
    ai_parser.add_argument(
        "--quarter", type=str, help="指定季度（格式：YYYY-QX，如2024-Q1）"
    )
    ai_parser.add_argument("--output", type=str, help="输出文件路径（可选）")
    ai_parser.add_argument(
        "--no-excel", action="store_true", help="仅生成JSON，不写Excel"
    )
    ai_parser.add_argument(
        "--no-json", action="store_true", help="仅生成Excel，不写JSON"
    )

    # Export command
    export_parser = subparsers.add_parser(
        "export",
        help="导出Excel/JSON",
        description="在Excel与分期JSON之间进行双向导出",
    )
    export_parser.add_argument(
        "--from",
        dest="source",
        choices=["preliminary", "ai"],
        default="preliminary",
        help="数据来源：preliminary 或 ai",
    )
    export_parser.add_argument(
        "--direction",
        choices=["excel-to-json", "json-to-excel"],
        default="excel-to-json",
        help="导出方向（默认 excel-to-json）",
    )
    export_parser.add_argument(
        "--excel", type=str, help="指定Excel路径（可选，默认读取/写入项目既定路径）"
    )
    export_parser.add_argument(
        "--json-root", type=str, help="指定JSON根目录（可选，默认在outputs下）"
    )
    export_parser.add_argument(
        "--overwrite", action="store_true", help="excel->json 时覆盖已存在文件"
    )

    # Validate exports command
    validate_parser = subparsers.add_parser(
        "validate-exports",
        help="校验Excel与JSON一致性",
        description="检查同一调仓日在Excel与JSON中的股票集合是否一致",
    )
    validate_parser.add_argument(
        "--source",
        choices=["preliminary", "ai"],
        default="preliminary",
        help="数据来源：preliminary 或 ai",
    )
    validate_parser.add_argument("--excel", type=str, help="Excel路径（可选）")
    validate_parser.add_argument("--json-root", type=str, help="JSON根目录（可选）")

    # Generate whitelist command
    gen_parser = subparsers.add_parser(
        "gen-whitelist",
        help="从结果文件生成Ticker白名单",
        description="汇总 preliminary 或 AI 结果中的全部Ticker，去重并输出白名单文件",
    )
    gen_parser.add_argument(
        "--from",
        dest="source",
        choices=["preliminary", "ai"],
        default="preliminary",
        help="读取哪类结果文件（默认：preliminary）",
    )
    gen_parser.add_argument(
        "--excel",
        type=str,
        help=(
            "结果Excel路径（默认：outputs/point_in_time_backtest_quarterly_sp500_historical.xlsx 或 "
            "outputs/point_in_time_ai_stock_picks_all_sheets.xlsx）"
        ),
    )
    gen_parser.add_argument(
        "--date-start", type=str, help="起始日期（YYYY-MM-DD，可选）"
    )
    gen_parser.add_argument(
        "--date-end", type=str, help="结束日期（YYYY-MM-DD，可选）"
    )
    gen_parser.add_argument(
        "--out",
        type=str,
        help="输出白名单路径（默认：outputs/selected_tickers.txt）",
    )

    # LongPort quote command
    lb_quote_parser = subparsers.add_parser(
        "lb-quote",
        help="获取LongPort实时报价",
        description="通过LongPort API获取指定股票的实时报价",
    )
    lb_quote_parser.add_argument(
        "tickers", nargs="+", help="股票代码列表（如 AAPL MSFT 700.HK）"
    )

    # LongPort rebalance command
    lb_rebalance_parser = subparsers.add_parser(
        "lb-rebalance",
        help="根据AI选股结果调整仓位",
        description="读取AI选股结果文件，生成仓位调整订单（默认干跑模式）",
    )
    lb_rebalance_parser.add_argument(
        "input_file",
        type=str,
        help="AI选股结果文件路径（如 outputs/point_in_time_ai_stock_picks_all_sheets.xlsx）",
    )
    lb_rebalance_parser.add_argument(
        "--account", type=str, default="main", help="账户名称（默认：main）"
    )
    lb_rebalance_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="干跑模式，只打印不实际下单（默认开启）",
    )
    lb_rebalance_parser.add_argument(
        "--execute", action="store_true", help="实际执行交易（关闭干跑模式）"
    )
    lb_rebalance_parser.add_argument(
        "--target-gross-exposure",
        type=float,
        default=1.0,
        help="目标总敞口比例（0-1，默认1.0表示用现金+基金+股票总资产进行等额分配）",
    )

    # No longer expose env, default to real; --execute controls actual order execution

    # LongPort account overview command
    lb_account_parser = subparsers.add_parser(
        "lb-account",
        help="查看 LongPort 真实账户概览",
        description="展示真实账户的资金与持仓",
    )
    lb_account_parser.add_argument("--funds", action="store_true", help="只看资金")
    lb_account_parser.add_argument("--positions", action="store_true", help="只看持仓")
    lb_account_parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="输出格式：table 表格 / json JSON格式",
    )

    return parser


def main() -> int:
    """Main entry function - responsible only for argument parsing and command dispatching.

    Returns:
        int: Exit code (0 indicates success)
    """
    parser = create_parser()
    args = parser.parse_args()

    # Show help if no command is provided
    if not args.command:
        parser.print_help()
        return 0

    # Dispatch to corresponding handler function based on command
    try:
        if args.command == "backtest":
            from .commands.backtest import run_backtest

            return run_backtest(args.strategy, getattr(args, "config", None))
        elif args.command == "load-data":
            from .commands.load_data import run_load_data

            return run_load_data(
                getattr(args, "data_dir", None),
                getattr(args, "skip_prices", False),
                getattr(args, "only_prices", False),
                getattr(args, "tickers_file", None),
                getattr(args, "date_start", None),
                getattr(args, "date_end", None),
            )
        elif args.command == "preliminary":
            from .commands.preliminary import run_preliminary

            return run_preliminary(
                getattr(args, "output_dir", None),
                getattr(args, "no_excel", False),
                getattr(args, "no_json", False),
            )
        elif args.command == "ai-pick":
            from .commands.ai_pick import run_ai_pick

            return run_ai_pick(
                getattr(args, "quarter", None),
                getattr(args, "output", None),
                getattr(args, "no_excel", False),
                getattr(args, "no_json", False),
            )
        elif args.command == "export":
            from .commands.export import run_export

            return run_export(
                getattr(args, "source", "preliminary"),
                getattr(args, "direction", "excel-to-json"),
                getattr(args, "overwrite", False),
                getattr(args, "excel", None),
                getattr(args, "json_root", None),
            )
        elif args.command == "validate-exports":
            from .commands.validate_exports import run_validate_exports

            return run_validate_exports(
                getattr(args, "source", "preliminary"),
                getattr(args, "excel", None),
                getattr(args, "json_root", None),
            )
        elif args.command == "gen-whitelist":
            from .commands.gen_whitelist import run_gen_whitelist
            return run_gen_whitelist(
                getattr(args, "source", "preliminary"),
                getattr(args, "excel", None),
                getattr(args, "date_start", None),
                getattr(args, "date_end", None),
                getattr(args, "out", None),
            )
        elif args.command == "lb-quote":
            from .commands.lb_quote import run_lb_quote
            return run_lb_quote(args.tickers)
        elif args.command == "lb-rebalance":
            from .commands.lb_rebalance import run_lb_rebalance

            # If --execute is specified, disable dry-run mode
            dry_run = not getattr(args, "execute", False)
            return run_lb_rebalance(
                args.input_file,
                getattr(args, "account", "main"),
                dry_run,
                "real",
                getattr(args, "target_gross_exposure", 1.0),
            )
        elif args.command == "lb-account":
            from .commands.lb_account import run_lb_account
            return run_lb_account(
                only_funds=getattr(args, "funds", False),
                only_positions=getattr(args, "positions", False),
                fmt=getattr(args, "format", "table"),
            )
        else:
            from .utils.logging import get_logger

            logger = get_logger(__name__)
            logger.error(f"未知命令：{args.command}")
            return 1
    except ImportError as e:
        from .utils.logging import get_logger

        logger = get_logger(__name__)
        logger.error(f"无法导入命令模块: {e}")
        return 1


def app() -> None:
    """Application entry point (for scripts configuration in pyproject.toml).

    This function is the actual entry point for the stockq command in pyproject.toml.
    """
    sys.exit(main())


if __name__ == "__main__":
    app()
