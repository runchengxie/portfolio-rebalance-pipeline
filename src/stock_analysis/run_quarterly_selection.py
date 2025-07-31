import pandas as pd
import numpy as np
from scipy.stats import zscore
from pathlib import Path
from dateutil.relativedelta import relativedelta
import sqlite3

# --- 路径配置 ---
# 假设脚本位于项目子目录中，PROJECT_ROOT 是项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
OUTPUTS_DIR = PROJECT_ROOT / 'outputs'
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# --- 策略配置 ---
BACKTEST_FREQUENCY = 'QE'
ROLLING_WINDOW_YEARS = 5
# 我们保留 MIN_REPORTS_IN_WINDOW 作为筛选条件。
MIN_REPORTS_IN_WINDOW = 5
OUTPUT_FILE_BASE = OUTPUTS_DIR / 'point_in_time_backtest_dynamic'


# --- 因子配置 ---
FACTOR_WEIGHTS = {'cfo': 1, 'ceq': 1, 'txt': 1, 'd_txt': 1, 'd_at': -1, 'd_rect': -1}

# --- Helper Functions ---
def tidy_ticker(col: pd.Series) -> pd.Series:
    """清理股票代码格式"""
    return col.astype('string').str.upper().str.strip().str.replace(r'_DELISTED$', '', regex=True).replace({'': pd.NA})

def clean_dataframe(df_raw: pd.DataFrame) -> pd.DataFrame:
    """清理DataFrame，处理数据类型和列名"""
    df = df_raw.copy()
    df['Ticker'] = tidy_ticker(df['Ticker'])
    df.rename(columns={'Publish Date': 'date_known', 'Fiscal Year': 'year'}, inplace=True)
    df['date_known'] = pd.to_datetime(df['date_known'], errors='coerce')
    numeric_cols = [c for c in df.columns if c not in ['Ticker', 'Currency', 'Fiscal Period', 'date_known']]
    df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors='coerce')
    df = df.dropna(subset=['Ticker', 'date_known', 'year'])
    df = df.astype({'year': 'int'})
    return df

def load_and_merge_financial_data(data_dir: Path) -> pd.DataFrame:
    """从 financial_data.db 加载、合并并清理财务数据。"""
    print("正在从数据库加载并合并财务数据...")
    db_path = data_dir / 'financial_data.db'

    if not db_path.exists():
        print(f"[错误] 数据库文件不存在: {db_path}")
        print("[提示] 请先运行 'tools/load_data_to_db.py' 脚本来创建数据库。")
        return pd.DataFrame()

    try:
        con = sqlite3.connect(db_path)
        
        # 您的分析是正确的，这里的关键是放宽对 `date_known` 的严格匹配。
        # 我们使用 CTE (Common Table Expressions) 先为每张表找出每个公司和财年的最新记录。
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
            bs.Ticker,
            bs.year,
            -- 我们保留资产负债表的发布日期作为基准
            bs.date_known,
            bs."Total Equity" AS ceq,
            bs."Total Assets" AS at,
            bs."Accounts & Notes Receivable" AS rect,
            i."Income Tax (Expense) Benefit, Net" AS txt,
            cf."Net Cash from Operating Activities" AS cfo
        FROM
            (SELECT * FROM latest_bs WHERE rn = 1) AS bs
        INNER JOIN
            (SELECT * FROM latest_income WHERE rn = 1) AS i ON bs.Ticker = i.Ticker AND bs.year = i.year
        INNER JOIN
            (SELECT * FROM latest_cf WHERE rn = 1) AS cf ON bs.Ticker = cf.Ticker AND bs.year = cf.year
        """
        
        df_final = pd.read_sql_query(query, con, parse_dates=['date_known'])

    except Exception as e:
        print(f"[错误] 从数据库读取数据时出错: {e}")
        return pd.DataFrame()
    finally:
        if 'con' in locals():
            con.close()

    if df_final.empty:
        print("从数据库加载的数据为空。")
        return df_final

    df_final = df_final.sort_values(['Ticker', 'year', 'date_known']).drop_duplicates(subset=['Ticker', 'year'], keep='last')
    
    df_final.loc[df_final['at'] <= 0, 'at'] = np.nan
    df_final.loc[df_final['ceq'] <= 0, 'ceq'] = np.nan
    
    print(f"从数据库合并后的数据包含 {len(df_final)} 行.")
    return df_final

def calculate_factors_point_in_time(df: pd.DataFrame) -> pd.DataFrame:
    """计算时间点上的因子值"""
    df = df.sort_values(by=['Ticker', 'date_known'])
    factor_components = list(FACTOR_WEIGHTS.keys())
    delta_features = [feat for feat in factor_components if feat.startswith('d_')]
    original_features = [feat.replace('d_', '') for feat in delta_features]
    
    for feat in original_features:
        df[f'd_{feat}'] = df.groupby('Ticker')[feat].diff()
        
    df_cleaned = df.dropna(subset=factor_components).copy()
    if df_cleaned.empty: return pd.DataFrame()

    df_zscores = pd.DataFrame(index=df_cleaned.index)
    for component in factor_components:
        df_zscores[f'z_{component}'] = zscore(df_cleaned[component])

    df_cleaned['factor_score'] = 0.0
    for component, weight in FACTOR_WEIGHTS.items():
        df_cleaned['factor_score'] += df_zscores[f'z_{component}'] * weight
        
    return df_cleaned[['Ticker', 'date_known', 'year', 'factor_score']]

def calc_factor_scores(df_financials: pd.DataFrame, as_of_date: pd.Timestamp, window_years: int, min_reports_required: int) -> pd.DataFrame:
    """根据已知数据计算聚合的因子分数"""
    known_data = df_financials[df_financials['date_known'] <= as_of_date].copy()
    if known_data.empty: return pd.DataFrame()

    known_data_with_factors = calculate_factors_point_in_time(known_data)
    if known_data_with_factors.empty: return pd.DataFrame()

    window_start_date = as_of_date - relativedelta(years=window_years)
    historical_window_scores = known_data_with_factors[known_data_with_factors['date_known'] >= window_start_date]
    if historical_window_scores.empty: return pd.DataFrame()

    df_agg_scores = historical_window_scores.groupby('Ticker')['factor_score'].agg(['mean', 'count'])
    df_agg_scores.rename(columns={'mean': 'avg_factor_score', 'count': 'num_reports'}, inplace=True)
    
    df_agg_scores = df_agg_scores[df_agg_scores['num_reports'] >= min_reports_required]

    return df_agg_scores

# --- Main Logic for Selection Script ---
def main():
    """主执行函数 (已修改为季度调仓)"""
    print("--- 正在运行股票选择脚本 (季度调仓模式) ---")
    df_financials = load_and_merge_financial_data(DATA_DIR)
    if df_financials.empty:
        print("无法加载财务数据，程序退出。")
        return

    # 1. 确定回测的时间范围
    # 使用数据中的最早和最晚“已知日期”来动态确定范围
    min_date = df_financials['date_known'].min()
    max_date = df_financials['date_known'].max()

    if pd.isna(min_date) or pd.isna(max_date):
        print("数据中缺少有效的日期，无法确定回测范围。")
        return

    # 2. 生成固定的季度末调仓日期序列
    # 'QE' 代表 Quarter-End (3, 6, 9, 12月最后一天)
    # 我们选择每个季度结束后2个工作日作为交易日，以确保季度末财报有时间发布
    rebalance_dates = pd.date_range(start=min_date, end=max_date, freq=BACKTEST_FREQUENCY)
    trade_dates = [d + pd.offsets.BDay(2) for d in rebalance_dates]
    
    print(f"将使用 {BACKTEST_FREQUENCY} 频率在以下日期进行调仓计算: (共 {len(trade_dates)} 个)")
    print([d.date() for d in trade_dates[:5]], "...") # 打印前5个示例日期

    all_period_portfolios = {}

    # 3. 遍历每个季度调仓日进行选股
    for trade_date in trade_dates:
        # 在每个调仓日，我们只使用当天之前已知的所有信息
        as_of_date = trade_date.normalize()
        
        df_agg_scores = calc_factor_scores(
            df_financials, 
            as_of_date=as_of_date, 
            window_years=ROLLING_WINDOW_YEARS, 
            min_reports_required=MIN_REPORTS_IN_WINDOW
        )

        if df_agg_scores.empty:
            print(f"  - 调仓日 {trade_date.date()}: 无符合条件的股票，跳过。")
            continue
        
        print(f"  - 调仓日 {trade_date.date()}: {len(df_agg_scores)} 只股票符合条件，正在排名...")
        
        # 4. 排名并选择top N
        # 这里的 NUM_STOCKS_TO_SELECT 是从另一个脚本引入的，我们直接用20
        NUM_STOCKS_TO_SELECT = 20 # 您可以根据需要调整这个数字
        df_ranked = df_agg_scores.sort_values(by='avg_factor_score', ascending=False)
        top_stocks = df_ranked.head(NUM_STOCKS_TO_SELECT)
        
        all_period_portfolios[trade_date.date()] = top_stocks.reset_index()

    # 5. 保存结果 (这部分逻辑和原来一样)
    if all_period_portfolios:
        output_excel_file = OUTPUT_FILE_BASE.with_suffix('.xlsx')
        output_txt_file = OUTPUT_FILE_BASE.with_suffix('.txt')

        try:
            with pd.ExcelWriter(output_excel_file) as writer, open(output_txt_file, 'w', encoding='utf-8') as txt_file:
                print("\n正在生成 Excel 和 TXT 输出文件...")
                for date, df_portfolio in all_period_portfolios.items():
                    df_portfolio.to_excel(writer, sheet_name=str(date), index=False)
                    txt_file.write(f"--- Portfolio for {date} ({len(df_portfolio)} stocks) ---\n")
                    txt_file.write(df_portfolio.to_string(index=False))
                    txt_file.write("\n\n")

            print("股票选择完成。结果已保存至:")
            print(f"  - Excel: {output_excel_file}")
            print(f"  - TXT:   {output_txt_file}")
            
        except Exception as e:
            print(f"\n[错误] 保存文件时出错: {e}")
            
    else:
        print("\n没有生成任何投资组合。")

if __name__ == "__main__":
    main()