import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta
from scipy.stats import zscore

# --- Path Configuration ---
try:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
except NameError:
    PROJECT_ROOT = Path(".").resolve().parent

DATA_DIR = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# --- Strategy Configuration ---
BACKTEST_FREQUENCY = "QE"
ROLLING_WINDOW_YEARS = 5
MIN_REPORTS_IN_WINDOW = 5
OUTPUT_FILE_BASE = OUTPUTS_DIR / "point_in_time_backtest_quarterly_sp500_historical"

# --- Factor Configuration ---
FACTOR_WEIGHTS = {"cfo": 1, "ceq": 1, "txt": 1, "d_txt": 1, "d_at": -1, "d_rect": -1}


# Load S&P 500 historical constituents data from local CSV
def load_sp500_constituents(data_dir: Path) -> pd.DataFrame:
    """
    Load S&P 500 historical constituents data from local CSV file.
    The file should contain 'ticker', 'start_date', 'end_date' columns.
    """
    print("正在从本地CSV文件加载S&P 500历史成分股数据...")
    csv_path = data_dir / "sp500_historical_constituents.csv"
    try:
        df_constituents = pd.read_csv(csv_path)
        # Convert date columns to datetime objects, empty values (still in index) will become NaT
        df_constituents["start_date"] = pd.to_datetime(
            df_constituents["start_date"], errors="coerce"
        )
        df_constituents["end_date"] = pd.to_datetime(
            df_constituents["end_date"], errors="coerce"
        )

        # Clean ticker format to match financial data
        df_constituents["ticker"] = df_constituents["ticker"].str.upper().str.strip()

        print(f"成功加载 {len(df_constituents)} 条历史成分股记录。")
        return df_constituents
    except FileNotFoundError:
        print(f"[致命错误] S&P 500历史成分股文件未找到: {csv_path}")
        return None


# Get S&P 500 stock universe for a specific date
def get_universe_for_date(
    target_date: pd.Timestamp, df_constituents: pd.DataFrame
) -> list:
    """
    Filter the list of valid stocks at a given date from the historical constituents DataFrame.
    """
    target_date = target_date.normalize()  # Ensure date has no time component

    # Filter conditions:
    # 1. Stock's start date must be before (or on) the target date
    # 2. Stock's end date must be empty (NaT) or after the target date
    is_active = (df_constituents["start_date"] <= target_date) & (
        pd.isna(df_constituents["end_date"])
        | (df_constituents["end_date"] > target_date)
    )

    return df_constituents[is_active]["ticker"].tolist()


# --- Helper Functions ---
def tidy_ticker(col: pd.Series) -> pd.Series:
    return (
        col.astype("string")
        .str.upper()
        .str.strip()
        .str.replace(r"_DELISTED$", "", regex=True)
        .replace({"": pd.NA})
    )


def load_and_merge_financial_data(data_dir: Path) -> pd.DataFrame:
    print("正在从数据库加载并合并财务数据...")
    db_path = data_dir / "financial_data.db"

    if not db_path.exists():
        print(f"[错误] 数据库文件不存在: {db_path}")
        return pd.DataFrame()

    try:
        con = sqlite3.connect(db_path)
        query = """
        WITH latest_bs AS (
            SELECT *, ROW_NUMBER() OVER(PARTITION BY Ticker, year ORDER BY date_known DESC) as rn
            FROM balance_sheet
        ),
        latest_income AS (
            SELECT *, ROW_NUMBER() OVER(PARTITION BY Ticker, year ORDER BY date_known DESC) as rn
            FROM income
        ),
        latest_cf AS (
            SELECT *, ROW_NUMBER() OVER(PARTITION BY Ticker, year ORDER BY date_known DESC) as rn
            FROM cash_flow
        )
        SELECT
            bs.Ticker, bs.year, bs.date_known,
            bs."Total Equity" AS ceq, bs."Total Assets" AS at,
            bs."Accounts & Notes Receivable" AS rect,
            i."Income Tax (Expense) Benefit, Net" AS txt,
            cf."Net Cash from Operating Activities" AS cfo
        FROM (SELECT * FROM latest_bs WHERE rn = 1) AS bs
        INNER JOIN (SELECT * FROM latest_income WHERE rn = 1) AS i ON bs.Ticker = i.Ticker AND bs.year = i.year
        INNER JOIN (SELECT * FROM latest_cf WHERE rn = 1) AS cf ON bs.Ticker = cf.Ticker AND bs.year = cf.year
        """
        df_final = pd.read_sql_query(query, con, parse_dates=["date_known"])
    except Exception as e:
        print(f"[错误] 从数据库读取数据时出错: {e}")
        return pd.DataFrame()
    finally:
        if "con" in locals():
            con.close()

    if df_final.empty:
        return df_final
    # Clean Ticker format here
    df_final["Ticker"] = tidy_ticker(df_final["Ticker"])
    df_final = df_final.sort_values(["Ticker", "year", "date_known"]).drop_duplicates(
        subset=["Ticker", "year"], keep="last"
    )
    df_final.loc[df_final["at"] <= 0, "at"] = np.nan
    df_final.loc[df_final["ceq"] <= 0, "ceq"] = np.nan
    print(f"从数据库合并后的数据包含 {len(df_final)} 行.")
    return df_final


def calculate_factors_point_in_time(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(by=["Ticker", "date_known"])
    factor_components = list(FACTOR_WEIGHTS.keys())
    delta_features = [feat for feat in factor_components if feat.startswith("d_")]
    original_features = [feat.replace("d_", "") for feat in delta_features]

    for feat in original_features:
        df[f"d_{feat}"] = df.groupby("Ticker")[feat].diff()

    df_cleaned = df.dropna(subset=factor_components).copy()
    if df_cleaned.empty:
        return pd.DataFrame()

    df_zscores = pd.DataFrame(index=df_cleaned.index)
    for component in factor_components:
        df_zscores[f"z_{component}"] = zscore(df_cleaned[component])

    df_cleaned["factor_score"] = 0.0
    for component, weight in FACTOR_WEIGHTS.items():
        df_cleaned["factor_score"] += df_zscores[f"z_{component}"] * weight

    return df_cleaned[["Ticker", "date_known", "year", "factor_score"]]


def calc_factor_scores(
    df_financials: pd.DataFrame,
    as_of_date: pd.Timestamp,
    window_years: int,
    min_reports_required: int,
) -> pd.DataFrame:
    # 筛选在给定日期已知的数据
    known_data = df_financials[df_financials["date_known"] <= as_of_date].copy()
    if known_data.empty:
        return pd.DataFrame()

    known_data_with_factors = calculate_factors_point_in_time(known_data)
    if known_data_with_factors.empty:
        return pd.DataFrame()

    # Filter data within the backtest window
    window_start_date = as_of_date - relativedelta(years=window_years)
    historical_window_scores = known_data_with_factors[
        known_data_with_factors["date_known"] >= window_start_date
    ]
    if historical_window_scores.empty:
        return pd.DataFrame()

    df_agg_scores = historical_window_scores.groupby("Ticker")["factor_score"].agg(
        ["mean", "count"]
    )
    df_agg_scores.rename(
        columns={"mean": "avg_factor_score", "count": "num_reports"}, inplace=True
    )

    # Filter by number of reports
    df_agg_scores = df_agg_scores[df_agg_scores["num_reports"] >= min_reports_required]

    return df_agg_scores


def main():
    """
    Main execution function (using local historical CSV for quarterly rebalancing + dynamic S&P 500 filtering + chart output)
    """
    print("--- 正在运行股票选择脚本 (历史动态S&P 500过滤模式) ---")

    # Step 1: Load historical constituent data
    df_constituents = load_sp500_constituents(DATA_DIR)
    if df_constituents is None:
        print("无法加载S&P 500成分股数据，程序终止。")
        return

    # Step 2: Load financial data for all companies (one-time)
    df_all_financials = load_and_merge_financial_data(DATA_DIR)
    if df_all_financials.empty:
        print("无法加载财务数据，程序退出。")
        return

    # Step 3: Determine backtest time range
    min_date = df_all_financials["date_known"].min()
    max_date = df_all_financials["date_known"].max()

    if pd.isna(min_date) or pd.isna(max_date):
        print("\n[错误] 数据中未找到有效的财报日期，无法确定回测范围。")
        return

    # Step 4: Generate rebalancing date sequence
    rebalance_dates = pd.date_range(
        start=min_date, end=max_date, freq=BACKTEST_FREQUENCY
    )
    trade_dates = [d + pd.offsets.BDay(2) for d in rebalance_dates]

    print(
        f"\n将使用 {BACKTEST_FREQUENCY} 频率在以下日期进行调仓计算: (共 {len(trade_dates)} 个)"
    )
    print([d.date() for d in trade_dates[:5]], "...")

    all_period_portfolios = {}
    screening_stats = []

    # Flag to control whether stock selection has started
    selection_started = False

    # Step 5: Iterate through each rebalancing date for dynamic stock selection
    for trade_date in trade_dates:
        as_of_date = trade_date.normalize()

        # 5.1 Get current valid S&P 500 stock list
        current_sp500_list = get_universe_for_date(trade_date, df_constituents)
        if not current_sp500_list:
            print(f"  - 调仓日 {trade_date.date()}: S&P 500在当日无成分股数据，跳过。")
            continue

        # 5.2 Filter financial data for current S&P 500 constituents
        df_period_financials = df_all_financials[
            df_all_financials["Ticker"].isin(current_sp500_list)
        ]

        # 5.3 Calculate factor scores on current stock universe
        df_agg_scores = calc_factor_scores(
            df_period_financials,
            as_of_date=as_of_date,
            window_years=ROLLING_WINDOW_YEARS,
            min_reports_required=MIN_REPORTS_IN_WINDOW,
        )

        num_eligible_stocks = len(df_agg_scores)
        screening_stats.append(
            {"date": trade_date.date(), "count": num_eligible_stocks}
        )

        # Check if conditions for starting stock selection are met
        # If selection hasn't started, check if eligible stocks exceed 250
        if not selection_started and num_eligible_stocks > 250:
            print(
                f"  - 调仓日 {trade_date.date()}: 符合条件的股票数量 ({num_eligible_stocks}) 首次超过250，从现在开始进行选股。"
            )
            selection_started = True  # Set flag to True, will continue stock selection from now on

        # If df_agg_scores is empty or selection flag not enabled, print info and skip
        if df_agg_scores.empty or not selection_started:
            # Print different messages based on whether selection has started
            if not selection_started:
                print(
                    f"  - 调仓日 {trade_date.date()}: 在 {len(current_sp500_list)} 只成分股中，有 {num_eligible_stocks} 只符合条件，未达到启动阈值(>250)。"
                )
            else:  # This case shouldn't occur theoretically, as num_eligible_stocks must be >0 when selection_started is True
                print(
                    f"  - 调仓日 {trade_date.date()}: 在 {len(current_sp500_list)} 只成分股中，无符合条件的股票。"
                )
            continue

        # Only execute stock selection logic when selection_started is True
        print(
            f"  - 调仓日 {trade_date.date()}: 在 {len(current_sp500_list)} 只成分股中，有 {num_eligible_stocks} 只符合条件，正在排名..."
        )

        NUM_STOCKS_TO_SELECT = 20
        df_ranked = df_agg_scores.sort_values(by="avg_factor_score", ascending=False)
        top_stocks = df_ranked.head(NUM_STOCKS_TO_SELECT)

        all_period_portfolios[trade_date.date()] = top_stocks.reset_index()

    # Step 6: Save results to files
    if all_period_portfolios:
        output_excel_file = OUTPUT_FILE_BASE.with_suffix(".xlsx")
        output_txt_file = OUTPUT_FILE_BASE.with_suffix(".txt")
        try:
            with (
                pd.ExcelWriter(output_excel_file) as writer,
                open(output_txt_file, "w", encoding="utf-8") as txt_file,
            ):
                print("\n正在生成 Excel 和 TXT 输出文件...")
                for date, df_portfolio in all_period_portfolios.items():
                    df_portfolio.to_excel(writer, sheet_name=str(date), index=False)
                    txt_file.write(
                        f"--- Portfolio for {date} ({len(df_portfolio)} stocks) ---\n"
                    )
                    txt_file.write(df_portfolio.to_string(index=False))
                    txt_file.write("\n\n")
            print(
                f"股票选择完成。结果已保存至:\n  - Excel: {output_excel_file}\n  - TXT:   {output_txt_file}"
            )
        except Exception as e:
            print(f"\n[错误] 保存文件时出错: {e}")
    else:
        print("\n没有生成任何投资组合。")

    # Step 7: Generate and save statistical charts
    if screening_stats:
        print("\n正在生成合格股票数量的统计图表...")
        df_stats = pd.DataFrame(screening_stats)
        df_stats["date"] = pd.to_datetime(df_stats["date"])
        plt.style.use("ggplot")
        fig, ax = plt.subplots(figsize=(15, 8))
        ax.plot(
            df_stats["date"],
            df_stats["count"],
            marker="o",
            linestyle="-",
            markersize=4,
            label=f"Stocks with >= {MIN_REPORTS_IN_WINDOW} reports in last {ROLLING_WINDOW_YEARS} years",
        )

        # Add a threshold line to the chart
        ax.axhline(
            y=250, color="r", linestyle="--", label="Selection Threshold (250 stocks)"
        )

        ax.set_title(
            "Number of Eligible Stocks in Point-in-Time S&P 500 Universe",
            fontsize=16,
            pad=20,
        )
        ax.set_xlabel("Rebalance Date", fontsize=12)
        ax.set_ylabel("Count of Eligible Stocks", fontsize=12)
        ax.legend()
        ax.grid(True)
        ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
        plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
        y_max = max(260, df_stats["count"].max() * 1.1)  # Ensure threshold line is visible
        ax.set_ylim(bottom=0, top=y_max)
        fig.tight_layout()
        chart_output_file = OUTPUT_FILE_BASE.with_suffix(".png")
        try:
            plt.savefig(chart_output_file, dpi=300)
            print(f"图表已成功保存至: {chart_output_file}")
        except Exception as e:
            print(f"\n[错误] 保存图表时出错: {e}")


if __name__ == "__main__":
    main()
