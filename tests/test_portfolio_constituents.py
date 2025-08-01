import pandas as pd
from pathlib import Path
import sys

# --- 健壮的路径配置 ---
# 这个配置能确保无论脚本从哪里被调用，都能找到项目根目录。
try:
    # 当作为脚本运行时: /path/to/project/tests/verify_portfolio.py
    # .parent 是 tests 目录, .parent.parent 是项目根目录
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
except NameError:
    # 当在交互式环境 (如Jupyter Notebook) 中运行时
    # 假设 Notebook 在项目根目录或 tests 目录下
    if 'tests' in str(Path('.').resolve()):
         PROJECT_ROOT = Path('.').resolve().parent
    else:
         PROJECT_ROOT = Path('.').resolve()

# 将项目根目录下的 src 文件夹添加到Python的搜索路径中
# 这是一个好习惯，虽然在这个特定脚本里没用到，但在更复杂的测试中会很有用
sys.path.append(str(PROJECT_ROOT / 'src'))


# --- 文件路径定义 ---
DATA_DIR = PROJECT_ROOT / 'data'
OUTPUTS_DIR = PROJECT_ROOT / 'outputs'
PORTFOLIO_FILE = OUTPUTS_DIR / 'point_in_time_backtest_quarterly_sp500_historical.xlsx'
CONSTITUENTS_FILE = DATA_DIR / 'sp500_historical_constituents.csv'


def load_sp500_constituents(file_path: Path) -> pd.DataFrame | None:
    """
    从本地CSV文件加载S&P 500历史成分股数据。
    """
    print(f"Loading ground truth data from: {file_path}")
    try:
        df = pd.read_csv(file_path)
        df['start_date'] = pd.to_datetime(df['start_date'])
        df['end_date'] = pd.to_datetime(df['end_date'], errors='coerce')
        df['ticker'] = df['ticker'].str.upper().str.strip()
        return df
    except FileNotFoundError:
        print(f"[ERROR] Constituents file not found: {file_path}")
        return None

def verify_membership(portfolio_date: pd.Timestamp, 
                      portfolio_tickers: list, 
                      df_constituents: pd.DataFrame) -> list:
    """
    验证给定日期的一组股票是否都是S&P 500成员。
    """
    misfit_tickers = []
    check_date = portfolio_date.normalize()

    for ticker in portfolio_tickers:
        ticker_history = df_constituents[df_constituents['ticker'] == ticker]
        if ticker_history.empty:
            misfit_tickers.append(ticker)
            continue
            
        is_member = ((ticker_history['start_date'] <= check_date) & \
                     (pd.isna(ticker_history['end_date']) | (ticker_history['end_date'] > check_date))).any()

        if not is_member:
            misfit_tickers.append(ticker)
            
    return misfit_tickers


def main():
    """
    测试脚本的主函数。
    """
    print("--- Running S&P 500 Portfolio Verification Script ---")

    df_constituents = load_sp500_constituents(CONSTITUENTS_FILE)
    if df_constituents is None:
        return

    print(f"Loading portfolio data from: {PORTFOLIO_FILE}\n")
    try:
        xls = pd.ExcelFile(PORTFOLIO_FILE)
    except FileNotFoundError:
        print(f"[ERROR] Portfolio file not found: {PORTFOLIO_FILE}")
        print("Please run the main selection script first to generate the output.")
        return

    total_sheets_checked = 0
    total_errors_found = 0

    for sheet_name in xls.sheet_names:
        total_sheets_checked += 1
        portfolio_date = pd.to_datetime(sheet_name)
        df_portfolio = pd.read_excel(xls, sheet_name=sheet_name)
        tickers_to_check = df_portfolio['Ticker'].tolist()

        if not tickers_to_check:
            print(f"- Verifying portfolio for {portfolio_date.date()}... SKIP (Portfolio is empty)")
            continue

        misfit_tickers = verify_membership(portfolio_date, tickers_to_check, df_constituents)

        if not misfit_tickers:
            print(f"- Verifying portfolio for {portfolio_date.date()}... SUCCESS ({len(tickers_to_check)} stocks OK)")
        else:
            total_errors_found += 1
            print(f"- Verifying portfolio for {portfolio_date.date()}... FAILURE!")
            print(f"  [!!!] The following {len(misfit_tickers)} ticker(s) were NOT in the S&P 500 on this date:")
            print(f"        {', '.join(misfit_tickers)}")

    print("\n--- Verification Summary ---")
    print(f"Total portfolios checked: {total_sheets_checked}")
    if total_errors_found == 0:
        print("✅ ALL TESTS PASSED! All selected stocks were valid S&P 500 members on their respective dates.")
    else:
        print(f"❌ TEST FAILED! Found errors in {total_errors_found} portfolio(s).")
        print("Please review the logs above for details.")


if __name__ == "__main__":
    main()