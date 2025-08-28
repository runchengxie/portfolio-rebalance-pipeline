import json
import os
import random
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
from dotenv import dotenv_values
from google import genai
from pydantic import BaseModel, Field

# --- 路径和配置 ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
INPUT_FILE = OUTPUTS_DIR / "point_in_time_backtest_quarterly_sp500_historical.xlsx"
OUTPUT_AI_FILE = OUTPUTS_DIR / "point_in_time_ai_stock_picks_all_sheets.xlsx"
COMPANY_INFO_FILE = DATA_DIR / "us-companies.csv"

# --- Gemini API 配置：仅本地文件读取，不注入全局环境 ---
_local_env = {}
try:
    _local_env = dotenv_values(PROJECT_ROOT / ".env") or {}
except Exception:
    _local_env = {}


def _pick(k, default=None):
    return (_local_env.get(k) if _local_env else None) or os.getenv(k) or default


# API限制配置
MAX_QPM = int(_pick("MAX_QPM", "24"))  # 每分钟最大请求数
MAX_RETRIES = int(_pick("MAX_RETRIES", "6"))  # 最大重试次数
REQUEST_TIMEOUT = int(_pick("REQUEST_TIMEOUT", "120"))  # 请求超时时间（秒）

# 线程锁用于保护Excel写入操作
WRITE_LOCK = threading.Lock()


# --- 定义结构化输出的Schema ---
class AIStockPick(BaseModel):
    """用于AI选股的结构化数据模型"""

    ticker: str = Field(description="股票代码")
    company_name: str = Field(description="公司名称")
    confidence_score: int = Field(
        description="AI对该股票的综合置信度评分（1-10的整数）", ge=1, le=10
    )
    reasoning: str = Field(description="详细分析，无长度限制")


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


# --- 熔断器类 ---
class Circuit:
    """熔断器，用于API key的故障保护"""

    def __init__(self, fail_threshold=3, cooldown=30):
        self.fail_threshold = fail_threshold
        self.cooldown = cooldown
        self.failures = 0
        self.open_until = 0

    def allow(self):
        """检查熔断器是否允许请求通过"""
        return time.time() >= self.open_until

    def record_success(self):
        """记录成功，重置失败计数"""
        self.failures = 0
        self.open_until = 0

    def record_failure(self):
        """记录失败，达到阈值时开启熔断"""
        self.failures += 1
        if self.failures >= self.fail_threshold:
            self.open_until = time.time() + self.cooldown
            self.failures = 0


# --- API Key槽位类 ---
class KeySlot:
    """管理单个API key的状态和资源"""

    def __init__(self, name, api_key, client, limiter):
        self.name = name
        self.api_key = api_key
        self.client = client
        self.limiter = limiter
        self.circuit = Circuit()
        self.dead = False  # 401/403 永久移除
        self.next_ok_at = 0  # 软退避时间


# --- API Key池管理器 ---
class KeyPool:
    """管理多个API key的轮换和熔断"""

    def __init__(self, slots):
        self.slots = slots
        self.lock = threading.Lock()
        self.project_cooldown_until = 0  # 项目级冷却时间

    def acquire(self):
        """获取一个可用的API key槽位"""
        while True:
            now = time.time()
            with self.lock:
                # 选一个可用的 key：没死、熔断已过、时间窗已到
                candidates = [
                    s
                    for s in self.slots
                    if not s.dead and s.circuit.allow() and now >= s.next_ok_at
                ]

                if not candidates:
                    # 找最早 next_ok_at 的那个
                    future_ready = [s.next_ok_at for s in self.slots if not s.dead]
                    sleep_for = (
                        max(0.05, min(future_ready) - now) if future_ready else 0.5
                    )
                else:
                    # 简单轮询：选一个并等待限速许可
                    slot = random.choice(candidates)
                    slot.limiter.wait()
                    return slot

            time.sleep(min(2.0, sleep_for or 0.2))

    def report_success(self, slot):
        """报告API调用成功"""
        slot.circuit.record_success()
        slot.next_ok_at = time.time()

    def report_failure(self, slot, err):
        """报告API调用失败，进行错误分级处理"""
        # 解析错误，决定 key 级 or 项目级退避
        msg = str(err).lower()
        is_auth = (
            "401" in msg or "403" in msg or "permission" in msg or "unauthorized" in msg
        )
        is_429 = "429" in msg or "rate_limit" in msg
        is_project_scope = (
            "perprojectperregion" in msg
            or "per project per region" in msg
            or "consumer 'project_number" in msg
        )

        if is_auth:
            # 认证错误，永久移除该key
            slot.dead = True
            print(f"  ⚠️ API Key {slot.name} 认证失败，已永久移除")
            return

        if is_429 and is_project_scope:
            # 项目级限流，全局冷却
            with self.lock:
                cooldown = random.uniform(60, 120)
                self.project_cooldown_until = max(
                    self.project_cooldown_until, time.time() + cooldown
                )
                for s in self.slots:
                    s.next_ok_at = self.project_cooldown_until
                print(f"  🚨 检测到项目级限流，全局冷却 {cooldown:.1f} 秒")
            return

        # key 级退避/熔断
        slot.circuit.record_failure()
        slot.next_ok_at = time.time() + random.uniform(5, 15)
        print(f"  ⚠️ API Key {slot.name} 失败，进入退避状态")


# --- 使用Key池的API调用函数 ---
def call_with_pool(keypool, do_call, max_retries=6):
    """使用Key池进行带重试的API调用"""
    last_err = None
    for attempt in range(1, max_retries + 1):
        slot = keypool.acquire()
        try:
            start_time = time.time()
            resp = do_call(slot.client)
            elapsed_time = time.time() - start_time

            keypool.report_success(slot)
            if attempt > 1:
                print(
                    f"  重试成功 (第{attempt}次尝试，使用{slot.name}，耗时{elapsed_time:.2f}秒)"
                )
            else:
                print(f"  API调用成功 (使用{slot.name}，耗时{elapsed_time:.2f}秒)")
            return resp
        except Exception as e:
            keypool.report_failure(slot, e)
            last_err = e

            if attempt < max_retries:
                # 指数退避 + 抖动
                sleep_s = min(60, (2**attempt) * 0.5) + random.uniform(0, 0.5)
                print(
                    f"  第{attempt}次尝试失败 (使用{slot.name})，等待 {sleep_s:.2f} 秒后重试..."
                )
                time.sleep(sleep_s)

    raise RuntimeError(f"重试次数已用尽，最后错误: {last_err}")


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
            with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
                df_ai_picks.to_excel(writer, sheet_name=str(sheet_name), index=False)
        else:
            # 文件存在，追加新sheet
            with pd.ExcelWriter(
                output_file, engine="openpyxl", mode="a", if_sheet_exists="replace"
            ) as writer:
                df_ai_picks.to_excel(writer, sheet_name=str(sheet_name), index=False)

        print(f"  ✓ 结果已保存到 {output_file} 的 {sheet_name} sheet")
        return True
    except Exception as e:
        print(f"  ✗ 保存结果失败: {e}")
        return False


# --- 创建Key池 ---
def create_key_pool():
    """创建并初始化API Key池"""
    # 先看本地文件里的 key，再回退到系统环境变量
    keys = [
        _pick("GEMINI_API_KEY"),
        _pick("GEMINI_API_KEY_2"),
        _pick("GEMINI_API_KEY_3"),
    ]
    keys = [k for k in keys if k]

    if not keys:
        raise ValueError(
            "没有可用的 Gemini API key。请在本地 .env 或系统环境变量里提供 GEMINI_API_KEY[_2|_3]。"
        )

    print(f"发现 {len(keys)} 个可用的API Key")

    # 给每个 key 分配自己的 QPM 份额
    per_key_qpm = max(1, MAX_QPM // len(keys))
    print(f"每个Key分配QPM: {per_key_qpm}")

    slots = []
    for idx, k in enumerate(keys):
        client = genai.Client(api_key=k)
        limiter = RateLimiter(per_key_qpm)
        slot = KeySlot(f"Key-{idx + 1}", k, client, limiter)
        slots.append(slot)
        print(f"  初始化 {slot.name}")

    return KeyPool(slots)


# --- 强健的响应解析 ---
def parse_response_robust(response):
    """更强健的响应解析，支持fallback到text解析"""
    try:
        # 首先尝试使用parsed属性
        if hasattr(response, "parsed") and response.parsed:
            return response.parsed

        # 如果parsed为空，尝试从text中解析JSON
        if hasattr(response, "text") and response.text:
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


# --- 处理单个季度的函数 ---
def process_one_sheet(sheet_name, df_companies, keypool):
    """处理单个季度的选股任务"""
    try:
        # 读取该季度的候选股票
        xls = pd.ExcelFile(INPUT_FILE)
        df_portfolio = pd.read_excel(xls, sheet_name=sheet_name)

        # 准备数据
        analysis_date = pd.to_datetime(sheet_name).date()
        tickers_df = (
            df_portfolio[["Ticker"]]
            .merge(df_companies, on="Ticker", how="left")
            .fillna({"Company Name": "N/A"})
        )

        print(f"  候选股票数量: {len(tickers_df)}")

        # 构建Prompt
        prompt = create_prompt(analysis_date, tickers_df)

        # 使用Key池调用API
        def _do_call(client):
            return client.models.generate_content(
                model="gemini-2.5-pro",
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": list[AIStockPick],
                },
            )

        print("  调用AI分析...")
        response = call_with_pool(keypool, _do_call, max_retries=MAX_RETRIES)

        # 强健的响应解析
        parsed_response = parse_response_robust(response)

        if parsed_response and len(parsed_response) > 0:
            df_ai_picks = pd.DataFrame([p.model_dump() for p in parsed_response])
            df_ai_picks = df_ai_picks.sort_values(
                by="confidence_score", ascending=False
            )

            # 线程安全保存结果
            if save_sheet_result_threadsafe(sheet_name, df_ai_picks, OUTPUT_AI_FILE):
                return (sheet_name, "success", len(df_ai_picks))
            else:
                return (sheet_name, "save_failed", None)
        else:
            # 尝试从response.text获取更多信息
            error_info = "API返回为空或解析失败"
            if hasattr(response, "text") and response.text:
                error_info += f" (原始响应: {response.text[:200]}...)"
            return (sheet_name, "parse_failed", error_info)

    except Exception as e:
        return (sheet_name, "error", str(e))


# --- Prompt构建函数 ---
def create_prompt(analysis_date, ticker_list_df):
    ticker_str = "\n".join(
        [
            f"- {row['Ticker']} ({row['Company Name']})"
            for _, row in ticker_list_df.iterrows()
        ]
    )

    # 优化后的提示词，限制输出长度和结构
    return f"""
    请你从巴菲特投资逻辑出发，从以下列表中筛选出最具投资潜力的10只股票。

    # 分析时间点 (至关重要)
    请将分析限制在 **{analysis_date}** 这个时间点的市场环境。对应的时间可能超出了你的训练数据截至日期范围，如果如此的话，请基于你的认知和合理推测进行分析。
    
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
    - 每个字段必须填写，不能为空
    - 返回标准JSON格式的数组
    
    请严格按照AIStockPick模型格式返回结果。
    """


# --- 主逻辑 ---
def main():
    print("--- 并发版AI精炼选股脚本 (Key池轮换) ---")
    print(
        f"配置: MAX_QPM={MAX_QPM}, MAX_RETRIES={MAX_RETRIES}, TIMEOUT={REQUEST_TIMEOUT}s"
    )

    # 创建Key池
    try:
        keypool = create_key_pool()
    except ValueError as e:
        print(f"错误: {e}")
        return

    # 加载公司信息用于丰富Prompt
    df_companies = pd.read_csv(COMPANY_INFO_FILE, sep=";", on_bad_lines="skip")
    df_companies = df_companies[["Ticker", "Company Name"]].dropna().drop_duplicates()

    # 加载量化策略选出的投资组合
    if not INPUT_FILE.exists():
        print(
            f"错误：找不到输入文件 {INPUT_FILE}。请先运行 `run_quarterly_selection.py`。"
        )
        return

    xls = pd.ExcelFile(INPUT_FILE)
    sheet_names = xls.sheet_names

    if not sheet_names:
        print("错误：Excel文件中没有任何工作表。")
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

    # 过滤出需要处理的季度
    pending_sheets = [s for s in sheet_names if s not in processed_sheets]
    print(f"待处理季度: {len(pending_sheets)} 个")

    if not pending_sheets:
        print("所有季度都已处理完成！")
        return

    # 使用线程池并发处理
    success_count = 0
    skip_count = len(processed_sheets)
    error_count = 0

    # 线程数等于可用key数，避免过度并发
    max_workers = len(keypool.slots)
    print(f"使用 {max_workers} 个工作线程进行并发处理")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        futures = []
        for sheet_name in pending_sheets:
            future = executor.submit(
                process_one_sheet, sheet_name, df_companies, keypool
            )
            futures.append(future)

        # 收集结果
        for i, future in enumerate(as_completed(futures), 1):
            sheet_name, status, result = future.result()

            print(f"\n[{i}/{len(pending_sheets)}] --- 季度 {sheet_name} ---")

            if status == "success":
                success_count += 1
                print(f"  ✓ 处理完成，选出 {result} 只股票")
            elif status == "save_failed":
                error_count += 1
                print("  ✗ 保存失败")
            elif status == "parse_failed":
                error_count += 1
                print(f"  ✗ {result}")
            else:  # error
                error_count += 1
                print(f"  ✗ 处理失败: {result}")

    # 最终统计
    print("\n=== 处理完成 ===")
    print(f"成功处理: {success_count} 个季度")
    print(f"跳过已处理: {skip_count} 个季度")
    print(f"处理失败: {error_count} 个季度")

    if success_count > 0 or skip_count > 0:
        print(f"结果文件: {OUTPUT_AI_FILE}")
        print("提示: 如果有失败的季度，可以重新运行脚本进行断点续跑")
    else:
        print("未能成功处理任何季度")


if __name__ == "__main__":
    main()
