"""回测命令

处理回测分析的命令逻辑。
"""
from ..utils.logging import get_logger

logger = get_logger(__name__)


def run_backtest(strategy: str, config_path: str | None = None) -> int:
    """运行回测分析
    
    Args:
        strategy: 策略类型 ('ai', 'quant', 'spy')
        config_path: 配置文件路径（可选）
        
    Returns:
        int: 退出码（0表示成功）
    """
    try:
        logger.info(f"正在运行 {strategy.upper()} 策略回测...")
        
        if strategy == "ai":
            from ..backtest_quarterly_ai_pick import main as ai_main
            ai_main()
        elif strategy == "quant":
            from ..backtest_quarterly_unpicked import main as quant_main
            quant_main()
        elif strategy == "spy":
            from ..backtest_benchmark_spy import main as spy_main
            spy_main()
        
        logger.info(f"{strategy.upper()} 策略回测完成！")
        return 0
        
    except ImportError as e:
        logger.error(f"无法导入回测模块: {e}")
        return 1
    except Exception as e:
        logger.error(f"回测执行失败：{e}")
        return 1