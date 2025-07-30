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
        
        query = """
        SELECT
            bs.Ticker,
            bs.year,
            bs.date_known,
            bs."Total Equity" AS ceq,
            bs."Total Assets" AS at,
            bs."Accounts & Notes Receivable" AS rect,
            i."Income Tax (Expense) Benefit, Net" AS txt,
            cf."Net Cash from Operating Activities" AS cfo
        FROM
            balance_sheet AS bs
        INNER JOIN
            income AS i ON bs.Ticker = i.Ticker AND bs.year = i.year AND bs.date_known = i.date_known
        INNER JOIN
            cash_flow AS cf ON bs.Ticker = cf.Ticker AND bs.year = cf.year AND bs.date_known = cf.date_known
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
    """主执行函数"""
    print("--- 正在运行股票选择脚本 ---")
    df_financials = load_and_merge_financial_data(DATA_DIR)
    if df_financials.empty:
        print("无法加载财务数据，程序退出。")
        return

    print("正在寻找可行的回测开始日期...")
    
    possible_publish_dates = sorted(df_financials['date_known'].unique())

    backtest_start_date = None
    viable_rebalance_dates = []

    for publish_date in possible_publish_dates:
        rebalance_day = publish_date + pd.offsets.BDay(3)
        scores = calc_factor_scores(df_financials, publish_date, ROLLING_WINDOW_YEARS, MIN_REPORTS_IN_WINDOW)
        
        # 只要有任何股票符合条件 (>=1)，就认为该日期可行
        if not scores.empty:  # 等价于 len(scores) > 0
            if backtest_start_date is None:
                backtest_start_date = rebalance_day
                print(f"找到一个可行的开始日期: {backtest_start_date.date()}. 当期可选股票数: {len(scores)}")
            viable_rebalance_dates.append(rebalance_day)

    if backtest_start_date is None:
        print("在任何时期都找不到符合条件的股票 (5年内至少有5份财报)，程序退出。")
        return

    all_period_portfolios = {}
    latest_known = df_financials['date_known'].max().normalize()

    print(f"开始从 {backtest_start_date.date()} 到 {latest_known.date()} 进行选择...")
    for i, rebalance_day in enumerate(viable_rebalance_dates):
        publish_date_for_calc = rebalance_day - pd.offsets.BDay(3)

        df_agg_scores = calc_factor_scores(df_financials, publish_date_for_calc, ROLLING_WINDOW_YEARS, MIN_REPORTS_IN_WINDOW)
        if df_agg_scores.empty:
            print(f"  - 处理调仓日 {rebalance_day.date()}... 无符合条件的股票，跳过。")
            continue
        
        # NOTE: 打印出当期可选的股票数量
        print(f"  - 处理调仓日 {rebalance_day.date()} (基于 {publish_date_for_calc.date()} 前的数据) - {len(df_agg_scores)} 只股票符合条件")
        
        df_ranked = df_agg_scores.sort_values(by='avg_factor_score', ascending=False)
        
        # 不再使用 .head() 来限制数量，所有符合条件的股票都入选
        top_stocks = df_ranked
        
        # NOTE (Optional): 如果你仍想设置一个数量上限（例如最多20只），可以使用下面这行代码代替上面一行
        # top_stocks = df_ranked.head(20)
        
        all_period_portfolios[rebalance_day.date()] = top_stocks.reset_index()

    if all_period_portfolios:
        # 定义输出文件的完整路径
        output_excel_file = OUTPUT_FILE_BASE.with_suffix('.xlsx')
        output_txt_file = OUTPUT_FILE_BASE.with_suffix('.txt')

        try:
            # 使用 with 语句同时管理 Excel 和 txt 文件的写入
            with pd.ExcelWriter(output_excel_file) as writer, open(output_txt_file, 'w', encoding='utf-8') as txt_file:
                print("\n正在生成 Excel 和 TXT 输出文件...")
                for date, df_portfolio in all_period_portfolios.items():
                    # 1. 写入到 Excel 的不同工作表
                    df_portfolio.to_excel(writer, sheet_name=str(date), index=False)
                    
                    # 2. 追加到同一个 TXT 文件
                    txt_file.write(f"--- Portfolio for {date} ({len(df_portfolio)} stocks) ---\n")
                    # 使用 to_string() 方法可以获得更好的格式对齐
                    txt_file.write(df_portfolio.to_string(index=False))
                    txt_file.write("\n\n") # 在每个表格后添加空行以分隔

            print("股票选择完成。结果已保存至:")
            print(f"  - Excel: {output_excel_file}")
            print(f"  - TXT:   {output_txt_file}")

        except Exception as e:
            print(f"\n[错误] 保存文件时出错: {e}")
            
    else:
        print("\n没有生成任何投资组合。")

if __name__ == "__main__":
    main()