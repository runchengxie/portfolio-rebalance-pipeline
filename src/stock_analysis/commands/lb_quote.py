"""LongPort 报价命令

处理股票报价查询的命令逻辑。
"""

from ..renderers.table import render_quotes
from ..services.account_snapshot import get_quotes
from ..utils.logging import get_logger

logger = get_logger(__name__)


def run_lb_quote(tickers: list[str], env: str = "test") -> int:
    """运行LongPort实时报价查询
    
    Args:
        tickers: 股票代码列表
        env: 环境选择（test或real）
        
    Returns:
        int: 退出码（0表示成功）
    """
    try:
        logger.info(f"正在获取 {', '.join(tickers)} 的实时报价...")
        logger.info(f"环境: {env.upper()}")
        
        # 获取报价数据
        quotes_dict = get_quotes(tickers, env)
        quotes_list = list(quotes_dict.values())
        
        # 渲染输出
        output = render_quotes(quotes_list)
        print(output)
        
        return 0
        
    except ImportError as e:
        logger.error(f"无法导入LongPort模块: {e}")
        logger.error("请确保已安装 longport 包：pip install longport")
        return 1
    except Exception as e:
        logger.error(f"获取报价失败：{e}")
        return 1