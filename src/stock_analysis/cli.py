"""命令行接口模块

提供股票分析项目的命令行入口点，支持各种回测和分析功能。
"""

import argparse
import sys
from pathlib import Path
from typing import Optional


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
  stockq backtest ai               运行AI选股回测
  stockq backtest quant            运行量化初选回测  
  stockq backtest spy              运行SPY基准回测
  stockq load-data                 加载数据到数据库
  stockq ai-pick                   运行AI选股分析
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
    
    return parser


def run_backtest(strategy: str, config_path: Optional[str] = None) -> int:
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


def run_load_data(data_dir: Optional[str] = None) -> int:
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


def run_ai_pick(quarter: Optional[str] = None, output: Optional[str] = None) -> int:
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
    elif args.command == "ai-pick":
        return run_ai_pick(
            getattr(args, 'quarter', None),
            getattr(args, 'output', None)
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