"""配置文件读取模块

统一管理回测配置，确保三个回测脚本使用相同的时间区间和参数。
"""

import datetime
from pathlib import Path
from typing import Dict, Any, Tuple

try:
    import yaml
except ImportError:
    yaml = None

from dateutil.relativedelta import relativedelta


def load_cfg() -> Dict[str, Any]:
    """加载配置文件
    
    优先读取 config/config.yaml，其次项目根的 config.yaml
    
    Returns:
        Dict[str, Any]: 配置字典
    """
    # 项目根目录
    root = Path(__file__).resolve().parents[3]
    
    # 配置文件候选路径（按优先级排序）
    candidates = [
        root / "config" / "config.yaml",  # 优先：config/config.yaml
        root / "config.yaml"              # 备选：项目根的config.yaml
    ]
    
    config_path = None
    for p in candidates:
        if p.exists():
            config_path = p
            break
    
    if config_path is None:
        # 默认配置：回到dynamic模式，与现有逻辑一致
        return {
            "backtest": {
                "period_mode": "dynamic",
                "buffer": {"months": 3, "days": 10},
                "initial_cash": 1000000  # 统一初始资金
            }
        }
    
    if yaml is None:
        raise ImportError("PyYAML is required to read config.yaml. Install it with: pip install PyYAML")
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        return config
    except Exception as e:
        print(f"[WARNING] Failed to load config.yaml: {e}. Using default configuration.")
        return {
            "backtest": {
                "period_mode": "dynamic",
                "buffer": {"months": 3, "days": 10},
                "initial_cash": {
                    "ai": 1000000,
                    "quant": 1000000,
                    "spy": 100000
                }
            }
        }


def get_backtest_period(portfolios: Dict = None) -> Tuple[datetime.date, datetime.date]:
    """获取回测时间区间
    
    Args:
        portfolios: 投资组合字典，仅在dynamic模式下使用
        
    Returns:
        Tuple[datetime.date, datetime.date]: (开始日期, 结束日期)
    """
    config = load_cfg()
    backtest_config = config.get("backtest", {})
    
    period_mode = backtest_config.get("period_mode", "dynamic")
    
    if period_mode == "fixed":
        # 固定时间模式
        start_str = backtest_config.get("start", "2021-04-02")
        end_str = backtest_config.get("end", "2025-07-02")
        
        # 处理可能的日期格式
        if isinstance(start_str, str):
            start_date = datetime.datetime.strptime(start_str, "%Y-%m-%d").date()
        else:
            start_date = start_str  # 已经是date对象
            
        if isinstance(end_str, str):
            end_date = datetime.datetime.strptime(end_str, "%Y-%m-%d").date()
        else:
            end_date = end_str  # 已经是date对象
        
        return start_date, end_date
    
    else:
        # 动态时间模式
        if not portfolios:
            raise ValueError("Dynamic mode requires portfolios data")
        
        # 从投资组合数据中获取时间范围
        first_rebalance_date = min(portfolios.keys())
        last_rebalance_date = max(portfolios.keys())
        
        # 添加缓冲时间
        buffer_config = backtest_config.get("buffer", {"months": 3, "days": 10})
        buffer_months = buffer_config.get("months", 3)
        buffer_days = buffer_config.get("days", 10)
        
        start_date = first_rebalance_date
        end_date = last_rebalance_date + relativedelta(months=buffer_months, days=buffer_days)
        
        return start_date, end_date


def get_initial_cash(strategy: str) -> float:
    """获取指定策略的初始资金
    
    支持两种配置格式：
    1. 统一资金：initial_cash: 1000000
    2. 分策略配置：initial_cash: {ai: 1000000, quant: 1000000, spy: 1000000}
    
    Args:
        strategy: 策略名称 ('ai', 'quant', 'spy')
        
    Returns:
        float: 初始资金金额
    """
    config = load_cfg()
    backtest_config = config.get("backtest", {})
    initial_cash_config = backtest_config.get("initial_cash", 1000000)
    
    # 支持两种格式：数字（统一资金）或字典（分策略配置）
    if isinstance(initial_cash_config, dict):
        # 字典格式：按策略分别配置
        return float(initial_cash_config.get(strategy, 1000000))
    else:
        # 数字格式：统一资金
        return float(initial_cash_config)