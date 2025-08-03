import os
from pathlib import Path
import pandas as pd
import google.generativeai as genai
from pydantic import BaseModel, Field
from typing import List
from dotenv import load_dotenv

# --- 路径和配置 ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
INPUT_FILE = OUTPUTS_DIR / "point_in_time_backtest_quarterly_sp500_historical.xlsx"
OUTPUT_AI_FILE = OUTPUTS_DIR / "point_in_time_ai_stock_picks.xlsx"
COMPANY_INFO_FILE = DATA_DIR / "us-companies.txt" # 使用txt文件以匹配您的项目

# --- Gemini API 配置 ---
load_dotenv(PROJECT_ROOT / ".env")
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("请在项目根目录的.env文件中设置GEMINI_API_KEY")
genai.configure(api_key=API_KEY)


# --- 1. 定义结构化输出的Schema ---
class AIStockPick(BaseModel):
    """用于AI选股的结构化数据模型"""
    ticker: str = Field(description="股票代码")
    company_name: str = Field(description="公司名称")
    confidence_score: float = Field(description="AI对该股票的综合置信度评分（1-10分）")
    reasoning: str = Field(description="综合分析选股理由，必须结合基本面、投资逻辑、行业地位和当前宏观环境。")


# --- 2. Prompt构建函数 ---
def create_prompt(analysis_date, ticker_list_df):
    ticker_str = "\n".join([
        f"- {row['Ticker']} ({row['Company Name']})" 
        for _, row in ticker_list_df.iterrows()
    ])
    
    return f"""
    作为一名资深的量化策略投资分析师，你的任务是从以下列表中筛选出最具投资潜力的10只股票。

    # 分析时间点 (至关重要)
    请将你的知识和分析严格限制在 **{analysis_date}** 这个时间点。你需要评估在当时的市场环境下，哪些公司具备最佳的投资前景。

    # 候选股票列表 (共 {len(ticker_list_df)} 只)
    这是由一个多因子量化模型在 {analysis_date} 初步筛选出的股票：
    {ticker_str}

    # 你的分析框架必须严格遵循以下四点：
    1.  **基本面分析**：审视这些公司的营收增长潜力、毛利率与净利率的趋势，以及经营活动现金流的健康状况。
    2.  **投资逻辑验证**：阐述持有该股票的核心投资逻辑是什么，并指出其面临的主要风险。
    3.  **行业与宏观视角**：分析公司所处的行业现状，结合 **{analysis_date}** 当时的宏观经济趋势（例如利率环境、通胀预期、经济周期等），评估公司的市场地位和竞争力。
    4.  **催化因素观察**：基于你在 {analysis_date} 时所能获取的信息，判断是否存在任何短期或中期的潜在催化剂（如新产品发布、政策变动、市场预期变化等）。

    # 任务要求
    请根据上述分析框架，从列表中选出你认为最优秀的 **10** 只，并以JSON格式返回。每一只入选的股票都必须包含详细的、结合上述四点的综合选股理由。
    """

# --- 主逻辑 ---
def main():
    print("--- 正在运行AI精炼选股脚本 ---")

    # 加载公司信息用于丰富Prompt
    df_companies = pd.read_csv(COMPANY_INFO_FILE, sep=";", on_bad_lines="skip")
    df_companies = df_companies[["Ticker", "Company Name"]].dropna().drop_duplicates()

    # 加载量化策略选出的投资组合
    if not INPUT_FILE.exists():
        print(f"错误：找不到输入文件 {INPUT_FILE}。请先运行 `run_quarterly_selection.py`。")
        return

    xls = pd.read_excel(INPUT_FILE, sheet_name=None)
    
    ai_portfolios = {}

    model = genai.GenerativeModel('gemini-1.5-pro-latest')

    for sheet_name, df_portfolio in xls.items():
        print(f"\n--- 正在为季度 {sheet_name} 进行AI精选 ---")
        
        # 准备数据
        analysis_date = pd.to_datetime(sheet_name).date()
        tickers_df = df_portfolio[['Ticker']].merge(df_companies, on="Ticker", how="left").fillna({"Company Name": "N/A"})

        # 构建Prompt
        prompt = create_prompt(analysis_date, tickers_df)
        
        try:
            # 调用Gemini API并使用结构化输出
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    response_mime_type="application/json",
                    response_schema=List[AIStockPick]
                )
            )

            # 解析返回的Pydantic对象
            parsed_response = response.parsed
            if not parsed_response:
                print(f"警告：季度 {sheet_name} 的API返回为空，跳过。")
                continue

            # 转换为DataFrame并排序
            df_ai_picks = pd.DataFrame([p.model_dump() for p in parsed_response])
            df_ai_picks = df_ai_picks.sort_values(by="confidence_score", ascending=False)
            
            ai_portfolios[sheet_name] = df_ai_picks
            print(f"成功为季度 {sheet_name} 选出 {len(df_ai_picks)} 只股票。")

        except Exception as e:
            print(f"错误：在处理季度 {sheet_name} 时调用API失败: {e}")
            continue

    # 保存AI精选结果到新的Excel文件
    if ai_portfolios:
        with pd.ExcelWriter(OUTPUT_AI_FILE) as writer:
            for date, df_picks in ai_portfolios.items():
                df_picks.to_excel(writer, sheet_name=str(date), index=False)
        print(f"\n--- AI精选完成！结果已保存至: {OUTPUT_AI_FILE} ---")
    else:
        print("\n--- 未能生成任何AI投资组合 ---")


if __name__ == "__main__":
    main()