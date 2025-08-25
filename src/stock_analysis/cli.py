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
  stockq lb-account                查看账户总览（默认test环境）
  stockq lb-account --env real     查看真实账户总览
  stockq lb-account --env both     同时查看test和real环境
  stockq lb-account --funds        只显示资金信息
  stockq lb-account --format json  JSON格式输出
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
        "--env", choices=["test", "real"], default="test",
        help="环境选择：test 纸交易 / real 实盘（默认 test）"
    )
    
    # LongPort 账户总览命令
    lb_account_parser = subparsers.add_parser(
        "lb-account",
        help="查看 LongPort 账户概览",
        description="展示资金与持仓（默认 test 环境）"
    )
    lb_account_parser.add_argument(
        "--env", choices=["test", "real", "both"], default="test",
        help="环境选择：test / real / both"
    )
    lb_account_parser.add_argument(
        "--funds", action="store_true", 
        help="只看资金"
    )
    lb_account_parser.add_argument(
        "--positions", action="store_true", 
        help="只看持仓"
    )
    lb_account_parser.add_argument(
        "--format", choices=["table", "json"], default="table",
        help="输出格式：table 表格 / json JSON格式"
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


def run_lb_rebalance(input_file: str, account: str = "main", dry_run: bool = True, env: str = "test") -> int:
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
        
        # 1) 获取账户快照（现金+持仓）
        print(f"\n=== {'干跑模式' if dry_run else '实际执行模式'} - {sheet_to_use} 差额调仓 ===")
        print("-" * 80)
        
        try:
            cash_usd, current_positions = client.portfolio_snapshot()
            print(f"账户快照: 现金 ${cash_usd:,.2f} | 持仓 {len(current_positions)} 只")
        except Exception as e:
            print(f"警告：无法获取账户快照 ({e})，使用模拟数据")
            cash_usd = 100000.0  # 模拟现金
            current_positions = {}  # 模拟空仓
        
        # 2) 获取实时价格
        from .broker.longport_client import _to_lb_symbol
        lb_symbols = [_to_lb_symbol(t) for t in tickers]
        
        try:
            px_map = client.quote_last(lb_symbols)
        except Exception as e:
            print(f"警告：无法获取实时价格 ({e})，跳过调仓")
            client.close()
            return 1
        
        # 3) 计算当前持仓市值
        current_market_value = 0.0
        for symbol, qty in current_positions.items():
            px, _ = px_map.get(symbol, (0.0, ""))
            current_market_value += float(px) * qty
        
        total_portfolio_value = cash_usd + current_market_value
        print(f"当前持仓市值: ${current_market_value:,.2f} | 总资产: ${total_portfolio_value:,.2f}")
        
        # 4) 计算等权重目标仓位
        N = len(tickers)
        if N == 0:
            print("错误：没有目标股票")
            client.close()
            return 1
        
        target_value_per_stock = total_portfolio_value / N
        print(f"等权重分配: 每只股票目标市值 ${target_value_per_stock:,.2f}")
        print("-" * 80)
        
        # 5) 计算差额并生成调仓订单
        orders = []
        print("Symbol   | 当前价格 | 当前持仓 | 目标持仓 | 差额    | 操作")
        print("-" * 80)
        
        for t in tickers:
            sym = t.upper().strip()
            lb_sym = _to_lb_symbol(sym)
            
            px, _ = px_map.get(lb_sym, (0.0, ""))
            px = float(px) if px else 0.0
            
            if px <= 0:
                print(f"{sym:8s} | {'N/A':8s} | {'N/A':8s} | {'N/A':8s} | {'N/A':7s} | 跳过（无价格）")
                continue
            
            # 当前持仓数量
            current_qty = current_positions.get(lb_sym, 0)
            
            # 目标持仓数量（按最小交易单位取整）
            target_qty_raw = target_value_per_stock / px
            lot = client.lot_size(lb_sym)
            target_qty = (int(target_qty_raw) // lot) * lot
            
            # 计算差额
            delta_qty = target_qty - current_qty
            
            if abs(delta_qty) < lot:
                # 差额小于最小交易单位，跳过
                print(f"{sym:8s} | {px:8.2f} | {current_qty:8d} | {target_qty:8d} | {delta_qty:7d} | 跳过（差额太小）")
                continue
            
            # 确定买卖方向
            if delta_qty > 0:
                side = "BUY"
                qty_to_trade = delta_qty
            else:
                side = "SELL"
                qty_to_trade = abs(delta_qty)
            
            print(f"{sym:8s} | {px:8.2f} | {current_qty:8d} | {target_qty:8d} | {delta_qty:7d} | {side} {qty_to_trade}")
            
            # 执行订单
            try:
                res = client.place_order(sym, qty_to_trade, side, dry_run=dry_run)
                orders.append(res)
            except Exception as e:
                print(f"  -> 下单失败: {e}", file=sys.stderr)
        
        # 写审计日志
        import datetime
        import json
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


def run_lb_account(env: str = "test", only_funds: bool = False, only_positions: bool = False, fmt: str = "table") -> int:
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
        import json

        from .broker.longport_client import LongPortClient
        
        def snap(one_env: str):
            """获取单个环境的账户快照"""
            try:
                c = LongPortClient(env=one_env)
                cash_usd, pos_map = c.portfolio_snapshot()
                quotes = c.quote_last(pos_map.keys()) if pos_map else {}
                # 组装展示结构：symbol, qty, last, est_value
                rows = []
                for sym, qty in pos_map.items():
                    last = quotes.get(sym, (0.0, ""))[0]
                    rows.append({
                        "env": one_env, 
                        "symbol": sym, 
                        "qty": qty, 
                        "last": last, 
                        "est_value": round(qty * last, 2)
                    })
                c.close()
                return {"env": one_env, "cash_usd": cash_usd, "positions": rows}
            except Exception as e:
                print(f"警告：无法获取 {one_env} 环境账户数据 ({e})，使用模拟数据", file=sys.stderr)
                return {"env": one_env, "cash_usd": 0.0, "positions": []}
        
        envs = ["test", "real"] if env == "both" else [env]
        
        # 只读横幅
        if env in ("real", "both"):
            print("!!! REAL ACCOUNT DATA (READ-ONLY) !!!")
        
        payload = [snap(e) for e in envs if e in ("test", "real")]
        
        # 输出
        if fmt == "json":
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            # 简单表格输出
            for block in payload:
                print(f"\n[{block['env'].upper()}] 现金(USD): ${block['cash_usd']:,.2f}")
                if not only_funds:
                    if block['positions']:
                        if not only_positions:
                            print("Symbol        Qty        Last       Est.Value")
                            print("-" * 50)
                        for r in block["positions"]:
                            print(f"{r['symbol']:12} {r['qty']:10} {r['last']:10.2f} ${r['est_value']:>10,.2f}")
                    else:
                        print("无持仓")
        
        return 0
        
    except ImportError as e:
        print(f"错误：无法导入LongPort模块 - {e}", file=sys.stderr)
        print("请确保已安装 longport 包：pip install longport", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"账户总览失败：{e}", file=sys.stderr)
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
            getattr(args, 'env', 'test')
        )
    elif args.command == "lb-account":
        return run_lb_account(
            getattr(args, 'env', 'test'),
            getattr(args, 'funds', False),
            getattr(args, 'positions', False),
            getattr(args, 'format', 'table')
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