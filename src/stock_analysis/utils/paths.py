"""统一路径配置模块

提供项目中所有路径的统一配置，消除重复的路径设置代码。
"""

from pathlib import Path


def get_project_root() -> Path:
    """获取项目根目录路径
    
    Returns:
        Path: 项目根目录路径
    """
    try:
        # 假设脚本位于根目录的 'src/stock_analysis/' 文件夹下
        return Path(__file__).resolve().parent.parent.parent.parent
    except NameError:
        # 如果在交互式环境（如Jupyter）中运行，则使用当前工作目录
        return Path.cwd()


# 全局路径配置
PROJECT_ROOT = get_project_root()
DATA_DIR = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

# 确保输出目录存在
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# 数据库路径
DB_PATH = DATA_DIR / "financial_data.db"

# 默认的组合文件路径
AI_PORTFOLIO_FILE = OUTPUTS_DIR / "point_in_time_ai_stock_picks_all_sheets.xlsx"
QUANT_PORTFOLIO_FILE = OUTPUTS_DIR / "point_in_time_backtest_quarterly_sp500_historical.xlsx"

# 回测配置常量
DEFAULT_INITIAL_CASH = 1_000_000.0
SPY_INITIAL_CASH = 100_000.0