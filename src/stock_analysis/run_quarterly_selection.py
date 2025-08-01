import pandas as pd
import numpy as np
from scipy.stats import zscore
from pathlib import Path
from dateutil.relativedelta import relativedelta
import sqlite3
import yfinance as yf
import matplotlib.pyplot as plt          # ### 新增 ### 导入绘图库
import matplotlib.ticker as mticker    # ### 新增 ### 导入绘图库的ticker模块

# --- 路径配置 ---
# 假设脚本位于项目子目录中，PROJECT_ROOT 是项目根目录
try:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
except NameError:
    PROJECT_ROOT = Path('.').resolve().parent

DATA_DIR = PROJECT_ROOT / 'data'
OUTPUTS_DIR = PROJECT_ROOT / 'outputs'
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# --- 策略配置 ---
BACKTEST_FREQUENCY = 'QE'
ROLLING_WINDOW_YEARS = 5
MIN_REPORTS_IN_WINDOW = 5
OUTPUT_FILE_BASE = OUTPUTS_DIR / 'point_in_time_backtest_quarterly_sp500_filtered'


# --- 因子配置 ---
FACTOR_WEIGHTS = {'cfo': 1, 'ceq': 1, 'txt': 1, 'd_txt': 1, 'd_at': -1, 'd_rect': -1}

# --- S&P 500 成分股获取函数 ---
def get_sp500_tickers() -> list:
    """通过读取维基百科页面获取标普500成分股列表。"""
    print("正在从网络获取最新的S&P 500成分股列表...")
    try:
        payload = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
        sp500_tickers = payload[0]['Symbol'].values.tolist()
        sp500_tickers = [ticker.replace('.', '-') for ticker in sp500_tickers]
        print(f"成功获取 {len(sp500_tickers)} 只 S&P 500 成分股。")
        return sp500_tickers
    except Exception as e:
        print(f"[错误] 无法从维基百科获取S&P 500成分股列表: {e}")
        print("[提示] 请检查你的网络连接。脚本将继续运行，但不会进行S&P 500过滤。")
        return []

# --- Helper Functions (保持不变) ---
def tidy_ticker(col: pd.Series) -> pd.Series:
    return col.astype('string').str.upper().str.strip().str.replace(r'_DELISTED$', '', regex=True).replace({'': pd.NA})

def load_and_merge_financial_data(data_dir: Path) -> pd.DataFrame:
    print("正在从数据库加载并合并财务数据...")
    db_path = data_dir / 'financial_data.db'

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
        df_final = pd.read_sql_query(query, con, parse_dates=['date_known'])
    except Exception as e:
        print(f"[错误] 从数据库读取数据时出错: {e}")
        return pd.DataFrame()
    finally:
        if 'con' in locals():
            con.close()

    if df_final.empty: return df_final
    df_final = df_final.sort_values(['Ticker', 'year', 'date_known']).drop_duplicates(subset=['Ticker', 'year'], keep='last')
    df_final.loc[df_final['at'] <= 0, 'at'] = np.nan
    df_final.loc[df_final['ceq'] <= 0, 'ceq'] = np.nan
    print(f"从数据库合并后的数据包含 {len(df_final)} 行.")
    return df_final

def calculate_factors_point_in_time(df: pd.DataFrame) -> pd.DataFrame:
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
    """
    主执行函数 (季度调仓 + S&P 500 强制过滤 + 图表输出)
    """
    print("--- 正在运行股票选择脚本 (季度调仓 + S&P 500 强制过滤模式) ---")
    
    # 步骤 0: 获取 S&P 500 股票池
    sp500_list = get_sp500_tickers()
    
    # ### 关键修改 ###
    # 检查列表是否成功获取。如果失败，则直接退出，防止使用错误的股票池。
    if not sp500_list:
        print("\n[致命错误] 未能获取S&P 500成分股列表。")
        print("程序将终止，以避免基于不正确的股票池（全市场）进行计算。")
        print("请检查您的网络连接或稍后再试。")
        return # 直接退出函数

    # 步骤 1: 加载财务数据
    df_financials = load_and_merge_financial_data(DATA_DIR)
    if df_financials.empty:
        print("无法加载财务数据，程序退出。")
        return

    # 步骤 2: 应用 S&P 500 过滤器 (现在是强制执行)
    print("\n正在应用 S&P 500 过滤器...")
    initial_tickers_count = df_financials['Ticker'].nunique()
    
    # 执行过滤
    df_financials = df_financials[df_financials['Ticker'].isin(sp500_list)]
    
    filtered_tickers_count = df_financials['Ticker'].nunique()
    
    # 更清晰的日志输出
    print(f"  - 数据库中独特的公司总数: {initial_tickers_count}")
    print(f"  - 获取到的 S&P 500 列表包含 {len(sp500_list)} 个代码。")
    print(f"  - 过滤后，股票池中剩余 {filtered_tickers_count} 家公司用于后续分析。")

    # 步骤 3: 确定回测的时间范围
    min_date = df_financials['date_known'].min()
    max_date = df_financials['date_known'].max()

    if pd.isna(min_date) or pd.isna(max_date):
        print("\n[错误] 在S&P 500股票池中未找到有效的财报日期，无法确定回测范围。")
        return

    # 步骤 4: 生成固定的季度末调仓日期序列
    rebalance_dates = pd.date_range(start=min_date, end=max_date, freq=BACKTEST_FREQUENCY)
    trade_dates = [d + pd.offsets.BDay(2) for d in rebalance_dates]
    
    print(f"\n将使用 {BACKTEST_FREQUENCY} 频率在以下日期进行调仓计算: (共 {len(trade_dates)} 个)")
    print([d.date() for d in trade_dates[:5]], "...")

    all_period_portfolios = {}
    screening_stats = [] # 初始化列表以存储统计数据

    # 步骤 5: 遍历每个季度调仓日进行选股
    for trade_date in trade_dates:
        as_of_date = trade_date.normalize()
        
        df_agg_scores = calc_factor_scores(
            df_financials, 
            as_of_date=as_of_date, 
            window_years=ROLLING_WINDOW_YEARS, 
            min_reports_required=MIN_REPORTS_IN_WINDOW
        )

        # 记录统计数据
        num_eligible_stocks = len(df_agg_scores)
        screening_stats.append({'date': trade_date.date(), 'count': num_eligible_stocks})

        if df_agg_scores.empty:
            print(f"  - 调仓日 {trade_date.date()}: 无符合条件的股票，跳过。")
            continue
        
        print(f"  - 调仓日 {trade_date.date()}: {num_eligible_stocks} 只股票符合条件，正在排名...")
        
        # 排名并选择top N
        NUM_STOCKS_TO_SELECT = 20
        df_ranked = df_agg_scores.sort_values(by='avg_factor_score', ascending=False)
        top_stocks = df_ranked.head(NUM_STOCKS_TO_SELECT)
        
        all_period_portfolios[trade_date.date()] = top_stocks.reset_index()

    # 步骤 6: 保存结果到文件
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

    # 步骤 7: 生成并保存统计图表
    if screening_stats:
        print("\n正在生成合格股票数量的统计图表...")
        
        df_stats = pd.DataFrame(screening_stats)
        df_stats['date'] = pd.to_datetime(df_stats['date'])

        plt.style.use('ggplot')
        fig, ax = plt.subplots(figsize=(15, 8))

        ax.plot(df_stats['date'], df_stats['count'], marker='o', linestyle='-', markersize=4, label=f'Stocks with >= {MIN_REPORTS_IN_WINDOW} reports in last {ROLLING_WINDOW_YEARS} years')

        ax.set_title('Number of Eligible Stocks in S&P 500 Universe Over Time', fontsize=16, pad=20)
        ax.set_xlabel('Rebalance Date', fontsize=12)
        ax.set_ylabel('Count of Eligible Stocks', fontsize=12)
        ax.legend()
        ax.grid(True)
        
        ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
        plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
        
        # 确保Y轴的上限合理，不会因为一两个异常值变得很大
        # 这里设置为合格股票数最大值的1.1倍，且至少为20
        y_max = max(20, df_stats['count'].max() * 1.1)
        ax.set_ylim(bottom=0, top=y_max) 
        
        fig.tight_layout() # 自动调整布局

        chart_output_file = OUTPUT_FILE_BASE.with_suffix('.png')
        try:
            plt.savefig(chart_output_file, dpi=300)
            print(f"图表已成功保存至: {chart_output_file}")
        except Exception as e:
            print(f"\n[错误] 保存图表时出错: {e}")

if __name__ == "__main__":
    main()