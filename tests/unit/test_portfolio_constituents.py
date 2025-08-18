# tests/test_portfolio_verification.py

from pathlib import Path

import pandas as pd
import pytest  # 导入 pytest 库

# --- 路径配置 ---
try:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
except NameError:
    PROJECT_ROOT = (
        Path(".").resolve().parent
        if "tests" in str(Path(".").resolve())
        else Path(".").resolve()
    )

DATA_DIR = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
PORTFOLIO_FILE = OUTPUTS_DIR / "point_in_time_backtest_quarterly_sp500_historical.xlsx"
CONSTITUENTS_FILE = DATA_DIR / "sp500_historical_constituents.csv"


# --- Pytest Fixtures: 准备测试所需的数据 ---


@pytest.fixture(
    scope="session"
)  # scope="session" 表示这个fixture在整个测试会话中只执行一次
def sp500_constituents() -> pd.DataFrame:
    """
    加载S&P 500历史成分股数据，作为一个可复用的测试资源。
    """
    if not CONSTITUENTS_FILE.exists():
        pytest.skip(f"Ground truth file not found, skipping tests: {CONSTITUENTS_FILE}")

    df = pd.read_csv(CONSTITUENTS_FILE)
    df["start_date"] = pd.to_datetime(df["start_date"])
    df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce")
    df["ticker"] = df["ticker"].str.upper().str.strip()
    return df


@pytest.fixture(scope="session")
def portfolio_excel_file() -> pd.ExcelFile:
    """
    加载投资组合Excel文件，作为一个可复用的测试资源。
    """
    if not PORTFOLIO_FILE.exists():
        pytest.skip(f"Portfolio file not found, skipping tests: {PORTFOLIO_FILE}")

    return pd.ExcelFile(PORTFOLIO_FILE)


# --- 参数化：动态生成测试用例 ---


def get_portfolio_sheet_names():
    """帮助函数：读取Excel文件的工作表名列表，用于参数化。"""
    if not PORTFOLIO_FILE.exists():
        return []
    xls = pd.ExcelFile(PORTFOLIO_FILE)
    return xls.sheet_names


# --- 核心测试逻辑 ---


def verify_membership(
    portfolio_date: pd.Timestamp, portfolio_tickers: list, df_constituents: pd.DataFrame
) -> list:
    """
    (Helper function) 验证给定日期的一组股票是否都是S&P 500成员。
    返回不符合条件的股票列表。
    """
    misfit_tickers = []
    check_date = portfolio_date.normalize()

    for ticker in portfolio_tickers:
        ticker_history = df_constituents[df_constituents["ticker"] == ticker]
        if ticker_history.empty:
            misfit_tickers.append(ticker)
            continue

        is_member = (
            (ticker_history["start_date"] <= check_date)
            & (
                pd.isna(ticker_history["end_date"])
                | (ticker_history["end_date"] > check_date)
            )
        ).any()

        if not is_member:
            misfit_tickers.append(ticker)

    return misfit_tickers


# --- Pytest 测试函数 ---


@pytest.mark.parametrize("sheet_name", get_portfolio_sheet_names())
def test_portfolio_stocks_are_valid_sp500_members(
    sheet_name: str,
    portfolio_excel_file: pd.ExcelFile,
    sp500_constituents: pd.DataFrame,
):
    """
    这是一个参数化的测试。
    对于Excel中的每一个工作表(sheet_name)，本测试都会独立运行一次。
    它验证该工作表中的所有股票在对应的日期都是S&P 500的有效成员。
    """
    # 1. 从测试参数和Fixtures中准备数据
    portfolio_date = pd.to_datetime(sheet_name)
    df_portfolio = portfolio_excel_file.parse(sheet_name)
    tickers_to_check = df_portfolio["Ticker"].tolist()

    if not tickers_to_check:
        pytest.skip("Portfolio is empty for this date.")

    # 2. 执行核心验证逻辑
    misfit_tickers = verify_membership(
        portfolio_date, tickers_to_check, sp500_constituents
    )

    # 3. 使用 assert 声明期望的结果
    # 如果 misfit_tickers 不是空列表，assert会失败，pytest会报告错误。
    assert not misfit_tickers, (
        f"On {portfolio_date.date()}, found tickers that were not S&P 500 members: {misfit_tickers}"
    )
