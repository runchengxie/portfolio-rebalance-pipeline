import argparse
import sys


def create_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器
    
    Returns:
        argparse.ArgumentParser: 配置好的参数解析器
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
  stockq lb-rebalance results.xlsx 仓位调整（干跑模式）
  stockq lb-rebalance results.xlsx --plan --budget 50000  计划模式（不受交易时段限制）
        """
    )
    
    # 添加版本信息
    parser.add_argument(
        "--version", 
        action="version", 
        version="%(prog)s 0.1.0"
    )
    
    # 创建子命令
    subparsers = parser.add_subparsers(
        dest="command",
        help="可用的命令",
        metavar="COMMAND"
    )
    
    # 回测命令
    backtest_parser = subparsers.add_parser(
        "backtest",
        help="运行回测分析",
        description="运行不同策略的回测分析"
    )
    backtest_parser.add_argument(
        "strategy",
        choices=["ai", "quant", "spy"],
        help="回测策略类型：ai(AI选股), quant(量化初选), spy(SPY基准)"
    )
    backtest_parser.add_argument(
        "--config",
        type=str,
        help="配置文件路径（可选）"
    )
    
    # 数据加载命令
    load_parser = subparsers.add_parser(
        "load-data",
        help="加载数据到数据库",
        description="从CSV文件加载财务数据和价格数据到SQLite数据库"
    )
    load_parser.add_argument(
        "--data-dir",
        type=str,
        help="数据目录路径（可选，默认使用项目data目录）"
    )
    
    # 量化初筛命令
    prelim_parser = subparsers.add_parser(
        "preliminary",
        help="运行量化初筛选股",
        description="执行多因子量化初筛，生成候选股票池"
    )
    prelim_parser.add_argument(
        "--output-dir",
        type=str,
        help="输出目录路径（可选，默认使用项目outputs目录）"
    )
    
    # AI选股命令
    ai_parser = subparsers.add_parser(
        "ai-pick",
        help="运行AI选股分析",
        description="使用AI模型进行股票筛选和分析"
    )
    ai_parser.add_argument(
        "--quarter",
        type=str,
        help="指定季度（格式：YYYY-QX，如2024-Q1）"
    )
    ai_parser.add_argument(
        "--output",
        type=str,
        help="输出文件路径（可选）"
    )
    
    # LongPort 报价命令
    lb_quote_parser = subparsers.add_parser(
        "lb-quote",
        help="获取LongPort实时报价",
        description="通过LongPort API获取指定股票的实时报价"
    )
    lb_quote_parser.add_argument(
        "tickers",
        nargs="+",
        help="股票代码列表（如 AAPL MSFT 700.HK）"
    )
    lb_quote_parser.add_argument(
        "--env", choices=["test", "real"], default="test",
        help="环境选择：test 纸交易 / real 实盘（默认 test）"
    )
    
    # LongPort 仓位调整命令
    lb_rebalance_parser = subparsers.add_parser(
        "lb-rebalance",
        help="根据AI选股结果调整仓位",
        description="读取AI选股结果文件，生成仓位调整订单（默认干跑模式）"
    )
    lb_rebalance_parser.add_argument(
        "input_file",
        type=str,
        help="AI选股结果文件路径（如 outputs/point_in_time_ai_stock_picks_all_sheets.xlsx）"
    )
    lb_rebalance_parser.add_argument(
        "--account",
        type=str,
        default="main",
        help="账户名称（默认：main）"
    )
    lb_rebalance_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="干跑模式，只打印不实际下单（默认开启）"
    )
    lb_rebalance_parser.add_argument(
        "--execute",
        action="store_true",
        help="实际执行交易（关闭干跑模式）"
    )
    lb_rebalance_parser.add_argument(
        "--plan",
        action="store_true",
        help="计划模式，只计算和显示投资计划，不受交易时段限制"
    )
    lb_rebalance_parser.add_argument(
        "--budget",
        type=float,
        default=100000.0,
        help="投资预算金额（默认：100,000）"
    )
    lb_rebalance_parser.add_argument(
        "--env", choices=["test", "real"], default="test",
        help="环境选择：test 纸交易 / real 实盘（默认 test）"
    )
    
    return parser


def run_backtest(strategy: str, config_path: str | None = None) -> int:
    """运行回测分析
    
    Args:
        strategy: 策略类型 ('ai', 'quant', 'spy')
        config_path: 配置文件路径（可选）
        
    Returns:
        int: 退出码（0表示成功）
    """
    try:
        print(f"正在运行 {strategy.upper()} 策略回测...")
        
        if strategy == "ai":
            from .backtest_quarterly_ai_pick import main as ai_main
            ai_main()
        elif strategy == "quant":
            from .backtest_quarterly_unpicked import main as quant_main
            quant_main()
        elif strategy == "spy":
            from .backtest_benchmark_spy import main as spy_main
            spy_main()
        
        print(f"{strategy.upper()} 策略回测完成！")
        return 0
        
    except ImportError as e:
        print(f"错误：无法导入回测模块 - {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"回测执行失败：{e}", file=sys.stderr)
        return 1


def run_load_data(data_dir: str | None = None) -> int:
    """运行数据加载
    
    Args:
        data_dir: 数据目录路径（可选）
        
    Returns:
        int: 退出码（0表示成功）
    """
    try:
        print("正在加载数据到数据库...")
        
        if data_dir:
            # 如果指定了数据目录，需要临时修改路径配置
            print(f"使用指定数据目录：{data_dir}")
            # 这里可以添加路径配置逻辑
        
        from .load_data_to_db import main as load_main
        load_main()
        
        print("数据加载完成！")
        return 0
        
    except ImportError as e:
        print(f"错误：无法导入数据加载模块 - {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"数据加载失败：{e}", file=sys.stderr)
        return 1


def run_preliminary(output_dir: str | None = None) -> int:
    """运行量化初筛选股
    
    Args:
        output_dir: 输出目录路径（可选）
        
    Returns:
        int: 退出码（0表示成功）
    """
    try:
        print("正在运行量化初筛选股...")
        
        if output_dir:
            print(f"输出目录：{output_dir}")
            # 这里可以添加输出目录配置逻辑
        
        from .preliminary_selection import main as prelim_main
        prelim_main()
        
        print("量化初筛选股完成！")
        return 0
        
    except ImportError as e:
        print(f"错误：无法导入量化初筛模块 - {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"量化初筛选股失败：{e}", file=sys.stderr)
        return 1


def run_ai_pick(quarter: str | None = None, output: str | None = None) -> int:
    """运行AI选股分析
    
    Args:
        quarter: 指定季度（可选）
        output: 输出文件路径（可选）
        
    Returns:
        int: 退出码（0表示成功）
    """
    try:
        print("正在运行AI选股分析...")
        
        if quarter:
            print(f"指定季度：{quarter}")
        if output:
            print(f"输出文件：{output}")
        
        from .ai_stock_pick import main as ai_pick_main
        ai_pick_main()
        
        print("AI选股分析完成！")
        return 0
        
    except ImportError as e:
        print(f"错误：无法导入AI选股模块 - {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"AI选股分析失败：{e}", file=sys.stderr)
        return 1


def run_lb_quote(tickers: list[str], env: str = "test") -> int:
    """运行LongPort实时报价查询
    
    Args:
        tickers: 股票代码列表
        env: 环境选择（test或real）
        
    Returns:
        int: 退出码（0表示成功）
    """
    try:
        print(f"正在获取 {', '.join(tickers)} 的实时报价...")
        print(f"环境: {env.upper()}")
        
        from .broker.longport_client import LongPortClient
        
        client = LongPortClient(env=env)
        quotes = client.quote_last(tickers)
        
        print("\n实时报价:")
        print("-" * 50)
        for symbol, (price, timestamp) in quotes.items():
            print(f"{symbol:12} | 价格: {price:>10} | 时间: {timestamp}")
        
        return 0
        
    except ImportError as e:
        print(f"错误：无法导入LongPort模块 - {e}", file=sys.stderr)
        print("请确保已安装 longport 包：pip install longport", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"获取报价失败：{e}", file=sys.stderr)
        return 1


def run_lb_rebalance(input_file: str, account: str = "main", dry_run: bool = True, env: str = "test", plan: bool = False, budget: float = 100000.0) -> int:
    """运行LongPort仓位调整
    
    Args:
        input_file: AI选股结果文件路径
        account: 账户名称
        dry_run: 是否为干跑模式
        env: 环境选择（test或real）
        plan: 是否为计划模式（只计算不下单）
        budget: 投资预算金额
        
    Returns:
        int: 退出码（0表示成功）
    """
    try:
        from pathlib import Path

        import pandas as pd
        
        # 真环境必须显式 --env real 且 --execute
        if env == "real" and dry_run:
            print("拒绝执行：你选择了 real 环境但仍是干跑模式。请加 --execute 再来。", file=sys.stderr)
            return 1
        if env == "real" and not dry_run:
            print("警告：将实际在 REAL 环境下下单。风险自负。")
        
        print(f"正在读取AI选股结果文件: {input_file}")
        print(f"账户: {account}")
        print(f"环境: {env.upper()}")
        print(f"模式: {'干跑模式（只打印）' if dry_run else '实际执行模式'}")
        
        # 检查文件是否存在
        file_path = Path(input_file)
        if not file_path.exists():
            print(f"错误：文件不存在 - {input_file}", file=sys.stderr)
            return 1
        
        # 读取所有 sheet 并选择最新一季
        import re
        
        try:
            xls = pd.ExcelFile(file_path)
            
            def pick_latest_sheet(sheet_names):
                candidates = []
                for s in sheet_names:
                    try:
                        d = pd.to_datetime(s).date()
                        candidates.append((d, s))
                    except Exception:
                        # 尝试匹配 yyyy-mm-dd
                        m = re.search(r"\d{4}-\d{2}-\d{2}", s)
                        if m:
                            d = pd.to_datetime(m.group(0)).date()
                            candidates.append((d, s))
                if candidates:
                    return max(candidates)[1]
                return sheet_names[-1]  # 兜底
            
            sheet_to_use = pick_latest_sheet(xls.sheet_names)
            df = pd.read_excel(xls, sheet_name=sheet_to_use)
            print(f"成功读取文件，使用 sheet: {sheet_to_use}，包含 {len(df)} 条记录")
            
            # 识别 ticker 列
            cols = {c.lower(): c for c in df.columns}
            ticker_col = cols.get("ticker") or cols.get("symbol")
            if not ticker_col:
                raise ValueError("未找到 ticker/symbol 列")
            
            tickers = df[ticker_col].astype(str).str.upper().str.strip().tolist()
            
        except Exception as e:
            print(f"读取Excel文件失败：{e}", file=sys.stderr)
            return 1
        
        # 初始化LongPort客户端
        from .broker.longport_client import LongPortClient
        client = LongPortClient(env=env)
        
        # 计划模式：只计算不下单
        if plan:
            print(f"\n=== 计划模式（不下单） - {sheet_to_use} ===")
            print(f"预算: ${budget:,.2f} | 等权重分配 | 标的数: {len(tickers)}")
            print("-" * 80)
            
            # 1) 拉取实时价格（带错误处理）
            from .broker.longport_client import _to_lb_symbol
            lb_symbols = [_to_lb_symbol(t) for t in tickers]
            
            try:
                px_map = client.quote_last(lb_symbols)
            except Exception as e:
                print(f"警告：无法连接到LongPort API ({e})，使用模拟价格数据进行演示")
                # 使用模拟价格数据
                import random
                px_map = {}
                for lb_sym in lb_symbols:
                    # 生成合理的股价范围（50-500美元）
                    mock_price = round(random.uniform(50, 500), 2)
                    mock_timestamp = "2024-01-01T09:30:00"
                    px_map[lb_sym] = (mock_price, mock_timestamp)
                print("注意：当前使用模拟价格数据，仅供演示计划模式功能")
                print("-" * 80)
            
            # 2) 计算等权重分配
            N = len(tickers)
            per_weight = 1.0 / N if N > 0 else 0.0
            plan_rows = []
            
            print("Symbol   | RefPx    | Time                | Qty(frac) | Qty(int) | Notional(int)")
            print("-" * 80)
            
            total_notional_int = 0.0
            for i, t in enumerate(tickers):
                sym = t.upper().strip()
                lb_sym = _to_lb_symbol(sym)
                
                px, ts = px_map.get(lb_sym, (0.0, ""))
                # 确保价格是float类型
                px = float(px) if px else 0.0
                if px <= 0:
                     # 格式化时间戳显示（处理无价格情况）
                     if ts:
                         if hasattr(ts, 'strftime'):  # datetime对象
                             time_display_na = ts.strftime("%Y-%m-%d %H:%M:%S")
                         else:  # 字符串
                             time_display_na = str(ts)[:19]
                     else:
                         time_display_na = "N/A"
                     print(f"{sym:8s} | {'N/A':8s} | {time_display_na:19s} | {'N/A':9s} | {'N/A':8s} | {'N/A':>13s}")
                     plan_rows.append((sym, ts, None, None, "NO_PRICE"))
                     continue
                
                # 3) 目标名义金额与碎股数量
                target_notional = budget * per_weight
                qty_frac = round(target_notional / px, 3)  # 碎股数量（仅规划参考）
                
                # 4) 整手数量：按最小交易单位向下取整
                try:
                    static_info = client.quote.static_info([lb_sym])
                    lot = max(1, static_info[0].lot_size or 1) if static_info else 1
                except Exception:
                    lot = 1  # 默认最小交易单位为1
                
                qty_int = (int(target_notional // px) // lot) * lot
                notional_int = qty_int * px
                total_notional_int += notional_int
                
                # 格式化时间戳显示
                if ts:
                    if hasattr(ts, 'strftime'):  # datetime对象
                        time_display = ts.strftime("%Y-%m-%d %H:%M:%S")
                    else:  # 字符串
                        time_display = str(ts)[:19]
                else:
                    time_display = "N/A"
                
                print(f"{sym:8s} | {px:8.2f} | {time_display:19s} | {qty_frac:9.3f} | {qty_int:8d} | ${notional_int:>11,.2f}")
                plan_rows.append((sym, ts, px, qty_frac, qty_int))
            
            print("-" * 80)
            print(f"总计划投资金额: ${total_notional_int:,.2f} / ${budget:,.2f} ({total_notional_int/budget*100:.1f}%)")
            print(f"\n注意：")
            print(f"- Qty(frac): 碎股数量，仅供参考，当前系统不支持碎股交易")
            print(f"- Qty(int): 整手数量，实际可交易的数量")
            print(f"- 计划模式不受交易时段限制，可随时执行")
            
            # 关闭客户端连接
            client.close()
            return 0
        
        # 原有的下单逻辑
        print(f"\n=== {'干跑模式' if dry_run else '实际执行模式'} - {sheet_to_use} 仓位调整 ===")
        print("-" * 60)
        
        # 下单逻辑
        orders = []
        for t in tickers:
            # 简化示例：等权分配，这里可以根据实际需求计算目标数量
            target_qty = 10  # 简化示例，实际应该根据资金和价格计算
            side = "BUY"  # 简化示例
            try:
                res = client.place_order(t, target_qty, side, dry_run=dry_run)
                orders.append(res)
                status = 'DRY' if res['dry_run'] else 'LIVE'
                est_px = res.get('est_px', 0)
                est_notional = res.get('est_notional', 0)
                print(f"{status} | {t:<8} {side} x{target_qty} | 估价: ${est_px:.2f} | 金额: ${est_notional:.2f} | OK")
            except Exception as e:
                print(f"下单跳过 {t}: {e}", file=sys.stderr)
        
        # 写审计日志
        import json
        import datetime
        log_dir = Path("outputs/orders")
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        log_file = log_dir / f"{stamp}_{env}_{'dry' if dry_run else 'live'}.jsonl"
        
        with open(log_file, "w", encoding="utf-8") as f:
            for o in orders:
                f.write(json.dumps(o, ensure_ascii=False) + "\n")
        
        print(f"\n审计日志已保存到: {log_file}")
        print(f"总计处理 {len(orders)} 个订单")
        
        if dry_run:
            print("\n注意：这是干跑模式，未实际下单")
            print("使用 --execute 参数可实际执行交易")
        else:
            print("\n警告：已实际下单，请检查券商账户确认执行情况")
        
        # 关闭客户端连接
        client.close()
        
        return 0
        
    except ImportError as e:
        print(f"错误：无法导入必要模块 - {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"仓位调整失败：{e}", file=sys.stderr)
        return 1


def main() -> int:
    """主入口函数
    
    Returns:
        int: 退出码（0表示成功）
    """
    parser = create_parser()
    args = parser.parse_args()
    
    # 如果没有提供命令，显示帮助信息
    if not args.command:
        parser.print_help()
        return 0
    
    # 根据命令执行相应的功能
    if args.command == "backtest":
        return run_backtest(args.strategy, getattr(args, 'config', None))
    elif args.command == "load-data":
        return run_load_data(getattr(args, 'data_dir', None))
    elif args.command == "preliminary":
        return run_preliminary(getattr(args, 'output_dir', None))
    elif args.command == "ai-pick":
        return run_ai_pick(
            getattr(args, 'quarter', None),
            getattr(args, 'output', None)
        )
    elif args.command == "lb-quote":
        return run_lb_quote(args.tickers, getattr(args, 'env', 'test'))
    elif args.command == "lb-rebalance":
        # 如果指定了 --execute，则关闭干跑模式
        dry_run = not getattr(args, 'execute', False)
        return run_lb_rebalance(
            args.input_file,
            getattr(args, 'account', 'main'),
            dry_run,
            getattr(args, 'env', 'test'),
            getattr(args, 'plan', False),
            getattr(args, 'budget', 100000.0)
        )
    else:
        print(f"未知命令：{args.command}", file=sys.stderr)
        return 1


def app() -> None:
    """应用入口点（用于pyproject.toml中的scripts配置）
    
    这个函数是pyproject.toml中stockq命令的实际入口点。
    """
    sys.exit(main())


if __name__ == "__main__":
    app()