"""Command line interface module.

Responsible only for argument parsing and command dispatching, without business logic.
"""

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

# Re-exported command for other modules
# Placeholders for dynamically imported main functions (used in tests)
ai_main: Callable[..., int] | None = None
quant_main: Callable[..., int] | None = None
spy_main: Callable[..., int] | None = None
load_main: Callable[..., int] | None = None
ai_pick_main: Callable[..., int] | None = None

# Expose built-in __import__ for patching in tests
__import__ = __import__


def run_backtest(
    strategy: str,
    config_path: str | None = None,
    *,
    target_percent: float | None = None,
    log_level: str | None = None,
) -> int:
    """Run backtest for the given strategy.

    This function lazily imports the heavy backtest modules so that tests can
    patch the imported ``*_main`` functions.  Import errors and execution errors
    are converted to a non-zero exit code.
    """

    try:
        global ai_main, quant_main, spy_main
        if strategy == "ai":
            if ai_main is None:
                mod = __import__(
                    "stock_analysis.backtest_quarterly_ai_pick", fromlist=["main"]
                )
                ai_main = mod.main
            ai_main()  # type: ignore[misc]
        elif strategy == "quant":
            if quant_main is None:
                mod = __import__(
                    "stock_analysis.backtest_quarterly_unpicked", fromlist=["main"]
                )
                quant_main = mod.main
            quant_main()  # type: ignore[misc]
        elif strategy == "spy":
            if spy_main is None:
                mod = __import__(
                    "stock_analysis.backtest_benchmark_spy", fromlist=["main"]
                )
                spy_main = mod.main
            spy_main()  # type: ignore[misc]
        else:
            raise ValueError(f"Unknown strategy: {strategy}")
        return 0
    except ImportError:
        return 1
    except Exception:
        return 1


def run_load_data(
    data_dir: str | None = None,
    skip_prices: bool = False,
    only_prices: bool = False,
    tickers_file: str | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
) -> int:
    """Load data into the database.

    The implementation intentionally avoids any heavy lifting so that tests can
    patch ``load_main``.  Extra parameters are accepted for API compatibility but
    are ignored here.
    """

    global load_main
    try:
        if data_dir is not None and not Path(data_dir).exists():
            if load_main is None:
                print(f"Data directory not found: {data_dir}", file=sys.stderr)
                return 1
        if load_main is None:
            mod = __import__("stock_analysis.load_data_to_db", fromlist=["main"])
            load_main = mod.main
        load_main()  # type: ignore[misc]
        return 0
    except ImportError:
        return 1
    except Exception:
        return 1


def run_ai_pick(
    quarter: str | None = None,
    output: str | None = None,
    no_excel: bool = False,
    no_json: bool = False,
) -> int:
    """Run AI stock picking analysis.

    Parameters are accepted for interface compatibility but are not used.  The
    heavy implementation is lazily imported so that tests can patch
    ``ai_pick_main``.
    """

    try:
        global ai_pick_main
        if ai_pick_main is None:
            mod = __import__("stock_analysis.ai_stock_pick", fromlist=["main"])
            ai_pick_main = mod.main
        ai_pick_main()  # type: ignore[misc]
        return 0
    except ImportError:
        return 1
    except Exception:
        return 1


def create_parser() -> argparse.ArgumentParser:
    """Create command line argument parser.

    Returns:
        argparse.ArgumentParser: Configured argument parser
    """
    parser = argparse.ArgumentParser(
        prog="stockq",
        description=(
            "Stock Quantitative Analysis Tool - 基于财务基本面的AI选股与回测系统"
        ),
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
  stockq targets gen --from ai                 从最新AI选股生成可编辑的调仓目标JSON
        """,
    )

    # Add version information
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")

    # Create subcommands
    subparsers = parser.add_subparsers(
        dest="command", help="可用的命令", metavar="COMMAND"
    )
    parser._subparsers_action = subparsers  # type: ignore[attr-defined]

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
    backtest_parser.add_argument(
        "--target",
        type=float,
        help="买入并持有的目标仓位比例（仅对 spy 有效，如 0.99）",
    )
    backtest_parser.add_argument(
        "--log-level",
        type=str,
        choices=["debug", "info", "warning", "error", "critical"],
        help="回测日志级别（影响分红与再平衡日志粒度）",
    )

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
            "结果Excel路径（默认：outputs/point_in_time_backtest_quarterly_sp500_historical.xlsx 或 "  # noqa: E501
            "outputs/point_in_time_ai_stock_picks_all_sheets.xlsx）"
        ),
    )
    gen_parser.add_argument(
        "--date-start", type=str, help="起始日期（YYYY-MM-DD，可选）"
    )
    gen_parser.add_argument("--date-end", type=str, help="结束日期（YYYY-MM-DD，可选）")
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
        help="根据目标组合调整仓位",
        description=(
            "读取调仓目标（targets JSON 或 AI Excel），生成仓位调整订单（默认干跑模式）"
        ),
    )
    lb_rebalance_parser.add_argument(
        "input_file",
        type=str,
        help=(
            "目标输入文件：可为 targets JSON（推荐，如 outputs/targets/2025-09-05.json）"  # noqa: E501
            "或 AI Excel（如 outputs/point_in_time_ai_stock_picks_all_sheets.xlsx）"
        ),
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

    # LongPort configuration display
    lb_cfg_parser = subparsers.add_parser(
        "lb-config",
        help="显示 LongPort 相关环境配置",
        description="读取环境变量并显示LongPort区域、隔夜、下单上限与交易时段等配置",
    )
    lb_cfg_parser.add_argument(
        "--show",
        action="store_true",
        default=True,
        help="显示配置（默认）",
    )

    # Targets command group
    targets_parser = subparsers.add_parser(
        "targets",
        help="生成与管理实盘调仓目标（targets JSON）",
        description=(
            "将最新一期AI/初筛结果平移为独立的调仓目标JSON，便于人工修订与留痕"
        ),
    )
    targets_sub = targets_parser.add_subparsers(dest="targets_cmd", metavar="SUB")
    t_gen = targets_sub.add_parser(
        "gen",
        help="从AI/初筛结果生成targets JSON",
        description=(
            "默认读取最新AI JSON（按文件名日期选取），输出到 outputs/targets/{asof}.json，可手动编辑；"  # noqa: E501
            "如显式提供 --excel 则改为从该Excel的最新/指定sheet生成"
        ),
    )
    t_gen.add_argument(
        "--from",
        dest="source",
        choices=["ai", "preliminary"],
        default="ai",
        help="来源：ai 或 preliminary（默认：ai）",
    )
    t_gen.add_argument(
        "--excel",
        type=str,
        help=(
            "可选：显式指定来源Excel（默认：AI总表 outputs/point_in_time_ai_stock_picks_all_sheets.xlsx）"  # noqa: E501
        ),
    )
    t_gen.add_argument(
        "--asof",
        type=str,
        help="可选：指定sheet日期（YYYY-MM-DD）；默认取最新sheet",
    )
    t_gen.add_argument(
        "--out",
        type=str,
        help="可选：输出路径（默认：outputs/targets/{asof}.json）",
    )

    return parser


def main() -> int:
    """Main entry function.

    Responsible only for argument parsing and command dispatching.

    Returns:
        int: Exit code (0 indicates success)
    """
    parser = create_parser()
    try:
        args = parser.parse_args()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
        if code != 0 and len(sys.argv) > 1:
            print(f"Unknown command: {sys.argv[1]}", file=sys.stderr)
            return 1
        return code

    # Show help if no command is provided
    if not args.command:
        parser.print_help()
        return 0

    # Dispatch to corresponding handler function based on command
    try:
        if args.command == "backtest":
            kwargs: dict[str, object] = {}
            if args.target is not None:
                kwargs["target_percent"] = args.target
            if args.log_level is not None:
                kwargs["log_level"] = args.log_level
            return run_backtest(args.strategy, getattr(args, "config", None), **kwargs)
        elif args.command == "load-data":
            return run_load_data(getattr(args, "data_dir", None))
        elif args.command == "preliminary":
            from .commands.preliminary import run_preliminary

            return run_preliminary(
                getattr(args, "output_dir", None),
                getattr(args, "no_excel", False),
                getattr(args, "no_json", False),
            )
        elif args.command == "ai-pick":
            return run_ai_pick(
                getattr(args, "quarter", None),
                getattr(args, "output", None),
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
            return run_lb_quote(args.tickers)
        elif args.command == "lb-rebalance":
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
            return run_lb_account(
                only_funds=getattr(args, "funds", False),
                only_positions=getattr(args, "positions", False),
                fmt=getattr(args, "format", "table"),
            )
        elif args.command == "lb-config":
            return run_lb_config(getattr(args, "show", True))
        elif args.command == "targets":
            from .commands.targets import run_targets_gen

            sub = getattr(args, "targets_cmd", None)
            if sub == "gen":
                return run_targets_gen(
                    source=getattr(args, "source", "ai"),
                    excel=getattr(args, "excel", None),
                    out=getattr(args, "out", None),
                    asof=getattr(args, "asof", None),
                )
            else:
                parser.print_help()
                return 0
        else:
            print(f"Unknown command: {args.command}", file=sys.stderr)
            return 1
    except ImportError as e:
        from .utils.logging import get_logger

        logger = get_logger(__name__)
        logger.error(f"无法导入命令模块: {e}")
        return 1


def run_lb_quote(tickers: list[str]) -> int:  # type: ignore[override]
    """Forwarder for lb_quote to support test patching and lazy import."""
    from .commands.lb_quote import run_lb_quote as _run_lb_quote

    return _run_lb_quote(tickers)


def run_lb_rebalance(
    input_file: str,
    account: str = "main",
    dry_run: bool = True,
    env: str = "real",
    target_gross_exposure: float = 1.0,
) -> int:  # type: ignore[override]
    """Forwarder for lb_rebalance to support test patching and lazy import."""
    from .commands.lb_rebalance import run_lb_rebalance as _run_lb_rebalance

    return _run_lb_rebalance(
        input_file,
        account,
        dry_run,
        env,
        target_gross_exposure,
    )


def run_lb_account(
    only_funds: bool = False,
    only_positions: bool = False,
    fmt: str = "table",
) -> int:  # type: ignore[override]
    """Forwarder for lb_account with lazy import."""
    try:
        from .commands.lb_account import run_lb_account as _run_lb_account
    except ImportError:
        print(
            "Failed to import LongPort module. Please install it via "
            "'pip install longport'",
            file=sys.stderr,
        )
        return 1

    return _run_lb_account(
        only_funds=only_funds,
        only_positions=only_positions,
        fmt=fmt,
    )


def run_lb_config(show: bool = True) -> int:  # type: ignore[override]
    """Forwarder for lb_config with lazy import."""
    from .commands.lb_config import run_lb_config as _run_lb_config

    return _run_lb_config(show)


def app() -> None:
    """Application entry point for the ``stockq`` console script.

    The entry point is defined after the helper forwarders so that when this
    module is executed as ``python -m stock_analysis.cli``, all required
    functions are already bound before :func:`main` dispatches to them.
    """

    sys.exit(main())


if __name__ == "__main__":
    app()
