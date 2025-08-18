import sqlite3
from pathlib import Path

import pandas as pd
import pytest

# --- 路径配置 ---
from stock_analysis.utils.paths import PROJECT_ROOT, DATA_DIR, OUTPUTS_DIR, DB_PATH, QUANT_PORTFOLIO_FILE
PORTFOLIO_FILE = QUANT_PORTFOLIO_FILE

# --- 测试常量配置 ---
# 一个季度大约有 252/4 = 63 个交易日
TRADING_DAYS_IN_QUARTER = 63
# 我们要求价格数据的覆盖率至少达到90%，以容忍节假日或少数数据缺失
MIN_COVERAGE_RATIO = 0.90


# --- Pytest Fixtures: 准备测试所需的数据和连接 ---


@pytest.fixture(scope="session")
def db_connection():
    """
    创建一个数据库连接的 Fixture。
    它在整个测试会话中只会被创建一次，并在结束后自动关闭。
    """
    if not DB_PATH.exists():
        pytest.skip(f"数据库文件未找到，跳过此测试: {DB_PATH}")

    con = sqlite3.connect(DB_PATH)
    yield con
    con.close()


@pytest.fixture(scope="session")
def portfolio_excel_file() -> pd.ExcelFile:
    """加载投资组合Excel文件，作为一个可复用的测试资源。"""
    if not PORTFOLIO_FILE.exists():
        pytest.skip(f"投资组合文件未找到，跳过此测试: {PORTFOLIO_FILE}")

    return pd.ExcelFile(PORTFOLIO_FILE)


# --- 动态生成测试用例的辅助函数 ---


def get_portfolio_sheet_names():
    """帮助函数：读取Excel文件的工作表名列表，用于参数化。"""
    if not PORTFOLIO_FILE.exists():
        return []
    xls = pd.ExcelFile(PORTFOLIO_FILE)
    return xls.sheet_names


# --- Pytest 测试函数 ---


@pytest.mark.parametrize("sheet_name", get_portfolio_sheet_names())
def test_price_data_is_complete_for_holding_period(
    sheet_name: str,
    db_connection: sqlite3.Connection,
    portfolio_excel_file: pd.ExcelFile,
):
    """
    对于投资组合中的每只股票，验证其在下一个持有期内的价格数据是否完整。
    """
    # 1. 准备测试周期和参数
    rebalance_date = pd.to_datetime(sheet_name)
    period_start = rebalance_date
    # 持有周期为下一个季度
    period_end = period_start + pd.DateOffset(months=3)

    # 计算本周期需要的最少价格数据点
    min_required_days = int(TRADING_DAYS_IN_QUARTER * MIN_COVERAGE_RATIO)

    # 从Excel中读取本周期的股票列表
    df_portfolio = portfolio_excel_file.parse(sheet_name)
    if "Ticker" not in df_portfolio.columns or df_portfolio.empty:
        pytest.skip(f"在 {sheet_name} 中找不到股票或内容为空。")

    portfolio_tickers = df_portfolio["Ticker"].unique().tolist()

    # 2. 遍历每只股票，检查其数据完整性
    data_completeness_errors = []

    for ticker in portfolio_tickers:
        # 使用参数化查询以防止SQL注入
        query = """
        SELECT COUNT(Date) 
        FROM share_prices 
        WHERE Ticker = ? AND Date >= ? AND Date < ?
        """

        # 将日期转换为SQLite可识别的字符串格式
        params = (ticker, str(period_start.date()), str(period_end.date()))

        cursor = db_connection.cursor()
        cursor.execute(query, params)
        count = cursor.fetchone()[0]

        if count < min_required_days:
            error_msg = (
                f"{ticker}: 价格数据不完整 "
                f"({period_start.date()} to {period_end.date()}). "
                f"期望至少 {min_required_days} 天, 实际只有 {count} 天。"
            )
            data_completeness_errors.append(error_msg)

    # 3. 在所有检查完成后，进行最终断言
    assert not data_completeness_errors, (
        f"\n在调仓日 {rebalance_date.date()} 后的持有期内发现价格数据缺失问题:\n"
        + "\n".join(f"  - {err}" for err in data_completeness_errors)
    )
