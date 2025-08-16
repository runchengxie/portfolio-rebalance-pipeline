import os
import time
import random
import json
import threading
from pathlib import Path
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
from google import genai
from pydantic import BaseModel, Field
from typing import List
from dotenv import load_dotenv

# --- 路径和配置 ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
INPUT_FILE = OUTPUTS_DIR / "point_in_time_backtest_quarterly_sp500_historical.xlsx"
OUTPUT_AI_FILE = OUTPUTS_DIR / "point_in_time_ai_stock_picks_all_sheets.xlsx"
COMPANY_INFO_FILE = DATA_DIR / "us-companies.csv"

# --- Gemini API 配置 ---
load_dotenv(PROJECT_ROOT / ".env")

# API限制配置
MAX_QPM = int(os.getenv("MAX_QPM", "24"))  # 每分钟最大请求数
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "6"))  # 最大重试次数
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "120"))  # 请求超时时间（秒）

# 线程锁用于保护Excel写入操作
WRITE_LOCK = threading.Lock()

# --- 1. 定义结构化输出的Schema ---
class AIStockPick(BaseModel):
    """用于AI选股的结构化数据模型"""
    ticker: str = Field(description="股票代码")
    company_name: str = Field(description="公司名称")
    confidence_score: int = Field(description="AI对该股票的综合置信度评分（1-10的整数）", ge=1, le=10)
    reasoning: str = Field(description="详细分析，无长度限制")


# --- 多API Key客户端管理 ---
def get_clients_and_limiters():
    """获取多个API key对应的客户端和限速器"""
    # 读取最多三个 key，缺哪个就跳过
    keys = [os.getenv("GEMINI_API_KEY"),
            os.getenv("GEMINI_API_KEY_2"),
            os.getenv("GEMINI_API_KEY_3")]
    keys = [k for k in keys if k]
    
    if not keys:
        raise ValueError("没有可用的 GEMINI_API_KEY*")
    
    print(f"发现 {len(keys)} 个可用的API Key")
    
    # 给每个 key 分到自己的 QPM 份额
    per_key_qpm = max(1, MAX_QPM // len(keys))
    print(f"每个API Key分配QPM: {per_key_qpm}")
    
    clients = []
    for i, k in enumerate(keys, 1):
        c = genai.Client(api_key=k)
        limiter = RateLimiter(per_key_qpm)
        clients.append((c, limiter))
        print(f"  API Key {i}: 已初始化 (QPM={per_key_qpm})")
    
    return clients  # list of (client, limiter)


# --- 限速器类 ---
class RateLimiter:
    """滑动窗口限速器"""
    def __init__(self, max_calls, per_seconds=60):
        self.max_calls = max_calls
        self.per = per_seconds
        self.calls = deque()
    
    def wait(self):
        now = time.monotonic()
        # 滑动窗口移除过期调用
        while self.calls and now - self.calls[0] > self.per:
            self.calls.popleft()
        
        if len(self.calls) >= self.max_calls:
            sleep_for = self.per - (now - self.calls[0])
            if sleep_for > 0:
                print(f"限速等待 {sleep_for:.2f} 秒...")
                time.sleep(sleep_for)
        
        self.calls.append(time.monotonic())


# --- 带重试的API调用函数 ---
def call_with_retries(client, model, prompt, schema, sheet_name=""):
    """带指数退避重试的API调用"""
    backoff_base = 0.5
    
    for attempt in range(MAX_RETRIES):
        try:
            start_time = time.time()
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": schema,
                },
            )
            elapsed_time = time.time() - start_time
            
            if attempt > 0:
                print(f"  重试成功 (第{attempt+1}次尝试，耗时{elapsed_time:.2f}秒)")
            else:
                print(f"  API调用成功 (耗时{elapsed_time:.2f}秒)")
            
            return response
            
        except Exception as e:
            # 尝试从异常中提取状态码和Retry-After头
            status = getattr(e, "status_code", None)
            resp = getattr(e, "response", None)
            if not status and hasattr(resp, "status_code"):
                status = resp.status_code
            
            retry_after = None
            if hasattr(resp, "headers") and resp.headers:
                retry_after = resp.headers.get("Retry-After")
            
            # 对于可重试的错误进行重试
            if status in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES - 1:
                if retry_after:
                    sleep_for = float(retry_after)
                    print(f"  服务端要求等待 {sleep_for} 秒 (状态码: {status})")
                else:
                    sleep_for = min(60, backoff_base * (2 ** attempt)) + random.uniform(0, 0.5)
                    print(f"  第{attempt+1}次重试失败 (状态码: {status})，等待 {sleep_for:.2f} 秒后重试...")
                
                time.sleep(sleep_for)
                continue
            
            # 其他错误或重试次数用尽，直接抛出
            print(f"  ✗ API调用失败: {e}")
            if attempt == MAX_RETRIES - 1:
                raise RuntimeError(f"重试次数已用尽，最后错误: {e}")
            raise
    
    raise RuntimeError("重试次数已用尽")


# --- 线程安全的保存函数 ---
def save_sheet_result_threadsafe(sheet_name, df_ai_picks, output_file):
    """线程安全的保存单个sheet结果"""
    with WRITE_LOCK:
        return save_sheet_result(sheet_name, df_ai_picks, output_file)


# --- 保存单个sheet结果 ---
def save_sheet_result(sheet_name, df_ai_picks, output_file):
    """保存单个sheet的结果到Excel文件"""
    try:
        # 如果文件不存在，创建新文件
        if not output_file.exists():
            with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
                df_ai_picks.to_excel(writer, sheet_name=str(sheet_name), index=False)
        else:
            # 文件存在，追加新sheet
            with pd.ExcelWriter(output_file, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                df_ai_picks.to_excel(writer, sheet_name=str(sheet_name), index=False)
        
        print(f"  ✓ 结果已保存到 {output_file} 的 {sheet_name} sheet")
        return True
    except Exception as e:
        print(f"  ✗ 保存结果失败: {e}")
        return False


# --- 强健的响应解析 ---
def parse_response_robust(response):
    """更强健的响应解析，支持fallback到text解析"""
    try:
        # 首先尝试使用parsed属性
        if hasattr(response, 'parsed') and response.parsed:
            return response.parsed
        
        # 如果parsed为空，尝试从text中解析JSON
        if hasattr(response, 'text') and response.text:
            try:
                json_data = json.loads(response.text)
                # 手动构造AIStockPick对象列表
                if isinstance(json_data, list):
                    return [AIStockPick(**item) for item in json_data]
                else:
                    print("  响应不是列表格式，尝试提取...")
                    return None
            except json.JSONDecodeError as e:
                print(f"  JSON解析失败: {e}")
                return None
        
        return None
    except Exception as e:
        print(f"  响应解析异常: {e}")
        return None


# --- 单个季度处理函数 ---
def process_one_sheet(sheet_name, df_companies, client, limiter, processed_sheets=None):
    """处理单个季度的股票分析"""
    try:
        # 断点续跑：跳过已处理的sheets
        if processed_sheets and sheet_name in processed_sheets:
            return (sheet_name, "skip", "已处理，跳过")
        
        # 读取该季度的候选股票
        xls = pd.ExcelFile(INPUT_FILE)
        df_portfolio = pd.read_excel(xls, sheet_name=sheet_name)
        analysis_date = pd.to_datetime(sheet_name).date()
        tickers_df = (df_portfolio[['Ticker']]
                     .merge(df_companies, on="Ticker", how="left")
                     .fillna({"Company Name": "N/A"}))
        
        print(f"  [{sheet_name}] 候选股票数量: {len(tickers_df)}")
        
        # 构建Prompt
        prompt = create_prompt(analysis_date, tickers_df)
        
        # 限速并调用API
        print(f"  [{sheet_name}] 等待API限速...")
        limiter.wait()
        
        print(f"  [{sheet_name}] 调用AI分析...")
        response = call_with_retries(
            client=client,
            model="gemini-2.5-pro",
            prompt=prompt,
            schema=list[AIStockPick],
            sheet_name=sheet_name
        )
        
        # 解析响应
        parsed = parse_response_robust(response)
        if not parsed:
            return (sheet_name, None, "解析失败或空响应")
        
        df_ai_picks = pd.DataFrame([p.model_dump() for p in parsed]).sort_values(
            by="confidence_score", ascending=False
        )
        
        # 线程安全保存结果
        ok = save_sheet_result_threadsafe(sheet_name, df_ai_picks, OUTPUT_AI_FILE)
        if ok:
            return (sheet_name, "ok", f"选出 {len(df_ai_picks)} 只股票")
        else:
            return (sheet_name, None, "保存失败")
            
    except Exception as e:
        return (sheet_name, None, f"处理异常: {str(e)}")


# --- 2. Prompt构建函数 ---
def create_prompt(analysis_date, ticker_list_df):
    ticker_str = "\n".join([
        f"- {row['Ticker']} ({row['Company Name']})" 
        for _, row in ticker_list_df.iterrows()
    ])
    
    # 优化后的提示词，限制输出长度和结构
    return f"""
    请你从巴菲特投资逻辑出发，从以下列表中筛选出最具投资潜力的10只股票。

    # 分析时间点 (至关重要)
    请将分析限制在 **{analysis_date}** 这个时间点的市场环境。

    # 候选股票列表 (共 {len(ticker_list_df)} 只)
    基于财务基本面在 {analysis_date} 初步筛选的股票：
    {ticker_str}

    # 分析框架：
    1. **基本面分析**：营收增长、盈利能力、现金流健康状况
    2. **投资逻辑**：核心投资理由和主要风险
    3. **行业地位**：结合 {analysis_date} 宏观环境的竞争优势
    4. **催化因素**：短中期潜在催化剂

    # 严格要求：
    - 必须选择恰好10只股票
    - confidence_score必须是1-10的整数
    - reasoning字段限制在200字以内
    - 每个字段必须填写，不能为空
    - 返回标准JSON格式的数组
    
    请严格按照AIStockPick模型格式返回结果。
    """

# --- 主逻辑 ---
def main():
    print("--- 并发版 AI 精炼选股 ---")
    print(f"配置: MAX_QPM={MAX_QPM}, MAX_RETRIES={MAX_RETRIES}, TIMEOUT={REQUEST_TIMEOUT}s")

    # 获取多个API Key的客户端和限速器
    try:
        clients = get_clients_and_limiters()  # [(client, limiter), ...]
    except ValueError as e:
        print(f"错误: {e}")
        return
    
    # 加载公司信息用于丰富Prompt
    df_companies = pd.read_csv(COMPANY_INFO_FILE, sep=";", on_bad_lines="skip")
    df_companies = df_companies[["Ticker", "Company Name"]].dropna().drop_duplicates()

    # 加载量化策略选出的投资组合
    if not INPUT_FILE.exists():
        print(f"错误：找不到输入文件 {INPUT_FILE}")
        return

    sheet_names = pd.ExcelFile(INPUT_FILE).sheet_names
    if not sheet_names:
        print("错误：Excel中没有任何工作表")
        return
    
    print(f"发现 {len(sheet_names)} 个季度需要处理")
    
    # 检查已处理的sheets（断点续跑支持）
    processed_sheets = set()
    if OUTPUT_AI_FILE.exists():
        try:
            existing_xls = pd.ExcelFile(OUTPUT_AI_FILE)
            processed_sheets = set(existing_xls.sheet_names)
            print(f"发现已处理的季度: {len(processed_sheets)} 个")
        except Exception as e:
            print(f"读取现有结果文件失败: {e}")
    
    # 把季度均匀分配给不同的 key：slice 分片
    buckets = [sheet_names[i::len(clients)] for i in range(len(clients))]
    print(f"任务分配: {[len(bucket) for bucket in buckets]} (每个API Key处理的季度数)")
    
    success = skip = failed = 0
    
    # 使用线程池并发处理
    with ThreadPoolExecutor(max_workers=len(clients)) as executor:
        futures = []
        
        # 为每个客户端分配任务
        for (client, limiter), bucket in zip(clients, buckets):
            for sheet_name in bucket:
                future = executor.submit(
                    process_one_sheet, 
                    sheet_name, 
                    df_companies, 
                    client, 
                    limiter, 
                    processed_sheets
                )
                futures.append(future)
        
        # 收集结果
        for future in as_completed(futures):
            try:
                sheet_name, status, message = future.result()
                
                if status == "ok":
                    success += 1
                    print(f"  ✓ 季度 {sheet_name} 处理完成: {message}")
                elif status == "skip":
                    skip += 1
                    print(f"  - 季度 {sheet_name} 跳过: {message}")
                else:
                    failed += 1
                    print(f"  ✗ 季度 {sheet_name} 失败: {message}")
                    
            except Exception as e:
                failed += 1
                print(f"  ✗ 处理任务时发生异常: {e}")
    
    # 最终统计
    print(f"\n=== 处理完成 ===")
    print(f"成功处理: {success} 个季度")
    print(f"跳过已处理: {skip} 个季度")
    print(f"处理失败: {failed} 个季度")
    print(f"结果文件: {OUTPUT_AI_FILE}")
    
    if failed > 0:
        print("提示: 如果有失败的季度，可以重新运行脚本进行断点续跑")


if __name__ == "__main__":
    main()