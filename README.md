# AI 增强的多因子量化选股策略

该项目采用两阶段的量化选股策略。第一阶段使用传统的多因子模型进行初步筛选；第二阶段则利用`gemini-2.5-pro`模型，以后价值投资者的视角对初选列表进行深度分析和精选，最终构建投资组合并使用`backtrader`进行回测。

项目利用`SQLite`进行数据管理，并通过`config/config.yaml`进行统一的参数配置。所有核心操作都通过`stockq`命令行工具执行。

## 回测结果图

![AI策略回测示例](outputs/ai_quarterly_strategy_returns.png)

*(上图为AI策略在2021-04-01至2025-07-01期间的回测表现示例)*

## 快速开始

所有操作均通过`stockq`命令行工具完成。

### 配置环境

* 安装依赖: `uv sync`

* 复制 `.env.example` 为 `.env` 并填入你的 API 密钥。

* 复制 `config/template.yaml` 为 `config/config.yaml`。

### 阶段一：数据准备与量化初筛

1. 步骤 1：只导财报数据进sqlite数据库，跳过价格

    ```bash
    stockq load-data --skip-prices
    ```

2. 步骤 2: 运行量化初筛策略

    此脚本执行多因子选股逻辑，并将每个季度的前20名候选股保存到`outputs/`目录的Excel文件中。

    ```bash
    stockq preliminary
    ```

### 阶段二：AI 精选与回测

3. 步骤 3: 运行 AI 筛选策略

    此脚本读取上一步生成的 Excel 文件，提交给`gemini-2.5-pro`进行分析，并将 AI 筛选的10只股票及其分析理由保存到新的Excel文件中。

    ```bash
    stockq ai-pick
    ```

    JSON/Excel 并行输出：

    - 默认同时写 Excel 总表和分期 JSON 文件。
    - 仅写 JSON：追加 `--no-excel`
    - 仅写 Excel：追加 `--no-json`

    目录结构（示例）：

    - `outputs/preliminary/YYYY/YYYY-MM-DD.json`
    - `outputs/ai_pick/YYYY/YYYY-MM-DD.json`

4. 导入价格数据进sqlite数据库

    ```bash
    生成白名单（从初筛 Excel 聚合去重，按时间窗筛 sheet）
    stockq gen-whitelist --from preliminary --out outputs/selected_tickers.txt --date-start 2015-01-01 --date-end 2025-07-02

    可选：AI 精选作为来源
    stockq gen-whitelist --from ai --out outputs/selected_tickers.txt --date-start 2015-01-01 --date-end
  2025-07-02

    仅导白名单价格，并裁日期
    stockq load-data --only-prices --tickers-file outputs/selected_tickers.txt --date-start 2015-01-01 --date-end 2025-07-02
    ```

    * 不传 --excel 时，默认读取：

        * 初筛：`outputs/point_in_time_backtest_quarterly_sp500_historical.xlsx`
        * AI：`outputs/point_in_time_ai_stock_picks_all_sheets.xlsx`

5. 步骤 4: 运行 AI 筛选组合的回测

    此脚本读取 AI 筛选的股票列表，使用`backtrader`引擎进行回测，并生成最终的累计收益图和性能指标。

    ```bash
    stockq backtest ai
    ```

### 阶段三：券商集成与实盘操作 (长桥)

5. 查看当下账户情况

    在执行任何交易操作前，先验证 API 连接和账户状态（默认连接真实账户，预览不下单）。

    ```bash
    # 验证API凭据和实时报价功能是否正常
    stockq lb-quote AAPL MSFT

    # 查看真实账户
    stockq lb-account

    # 只看资金或只看持仓
    stockq lb-account --funds
    stockq lb-account --positions

    # 机器可读
    stockq lb-account --format json
   ```

6. 执行仓位调整/交易: 为了最大限度地保障您的资金安全，`lb-rebalance`命令默认使用真实账户进行干跑预览，只有添加 `--execute` 时才会真实下单。

    请在执行前务必理解以下**行为矩阵**：

    | 命令组合 | 行为描述 |
    | :--- | :--- |
    | `stockq lb-rebalance ...` | 真实账户干跑：读取真实账户、统一抓取行情、生成等额调仓计划，但不下单。 |
    | `stockq lb-rebalance ... --execute` | 真实交易：在真实账户下按计划下单；所有风控（交易时段/最小单位/单笔上限）生效。 |

    推荐的执行流程：

    * 测试环境模拟（Dry-Run）:

        ```bash
        # 预览真实账户调仓计划（不下单）
        stockq lb-rebalance outputs/point_in_time_ai_stock_picks_all_sheets.xlsx
        ```

    3. 仔细检查输出: 审查上一步打印的交易计划，包括股票代码、数量和方向。

    4. 执行真实交易（谨慎操作）:

        ```bash
        # 确认所有信息无误后，才执行真实下单
        stockq lb-rebalance outputs/point_in_time_ai_stock_picks_all_sheets.xlsx --execute
        ```

## 可选步骤

* 创建数据库（WSL/Linux 全量重建）

    使用一键全量重建脚本，跨平台、可重复并且更快：

    ```bash
    bash scripts/rebuild_db.sh
    ```

    该脚本将：
    - 用 `sqlite3 .import` 高速导入价格数据（`data/us-shareprices-daily.csv`）。

    - 调整并导入财报数据到 `balance_sheet`/`cash_flow`/`income`（通过现有 Python 逻辑完成字段重命名与清洗）。

    - 建立必要索引并优化数据库。

    如需最简方式也可执行：

    ```bash
    stockq load-data
    ```

    可选参数：

    - 仅导入价格：`stockq load-data --only-prices`

    - 跳过价格（仅导入财报）：`stockq load-data --skip-prices`

    - 只导白名单价格（并裁日期）：`stockq load-data --only-prices --tickers-file outputs/selected_tickers.txt --date-start 2015-01-01 --date-end
  2025-07-02`

* 对比回测 1 (量化初筛组合): 评估纯量化策略（未经过 AI 筛选的 20 只股票组合）的表现。

    ```bash
    stockq backtest quant
    ```

* 对比回测 2 (SPY 基准)：评估 AI 策略与 SPY 基准（S&P 500 ETF）的表现。

    ```bash
    stockq backtest spy
    ```

### 导出与一致性校验（Excel ↔ JSON）

- Excel → 多个 JSON（按调仓日分文件）

    ```bash
    # 初筛
    stockq export --from preliminary --direction excel-to-json

    # AI 精选
    stockq export --from ai --direction excel-to-json
    ```

- 多个 JSON → Excel（每个调仓日一张工作表）

    ```bash
    # 初筛
    stockq export --from preliminary --direction json-to-excel

    # AI 精选
    stockq export --from ai --direction json-to-excel
    ```

- 校验 Excel 与 JSON 是否一致

    ```bash
    stockq validate-exports --source preliminary
    stockq validate-exports --source ai
    ```

可选参数：`--excel` 指定Excel路径，`--json-root` 指定JSON根目录，`--overwrite` 控制excel→json是否覆盖已存在文件。

额外的 JSON 健康检查（工具脚本）

- 深度校验 AI JSON 的字段规范、rank 连续性、候选映射与与 preliminary 的日期覆盖：

  ```bash
  python tools/validate_ai_pick_jsons.py
  ```
  非零退出码代表校验失败，方便在 CI 中使用。

## 核心特性

* 两阶段混合模型: 结合了基于财务报表数据的量化筛选和大型语言模型的深度分析，实现自动化、多维度的选股流程。

* 时点回测:

    * 避免幸存者偏差: 在每个调仓日，选股范围限定为当时的 S&P 500 指数成分股。

    * 杜绝未来数据: 使用财报的发布日期（Publish Date）作为判断信息是否可用的标准。

* AI筛选:

    * 多API密钥池: 支持配置多个Gemini API密钥，通过轮换机制分摊请求压力，最大化吞吐量。

    * 智能容错与限速: 内置一套API 管理系统，包括：

        * 滑动窗口限速器: 为每个API Key精确控制请求频率，避免超出 QPM (每分钟查询数) 限制。

        * 指数退避重试: 对临时性网络或服务器错误采用带“抖动”的指数退避策略进行重试。

        * 熔断器机制: 当某个 Key 连续失败时，系统会将其暂时“熔断”并移出工作池，防止连锁失败。

        * 分级错误处理: 系统能自动区分API Key认证失败（永久移除）、项目级限流（全局冷却）和临时性网络错误（单Key临时退避），确保在高并发请求下依然稳健运行。

* 命令行工具: 通过`stockq`命令及其子命令（如`load-data`, `ai-pick`, `backtest`, `lb-rebalance`）执行所有核心工作流，实现流程自动化。

* 集中化配置: 所有回测参数（如时间范围、初始资金）均在`config/config.yaml`中统一管理，便于快速调整和复现实验。

* 模块化与可测试的代码: 项目被重构为逻辑清晰的模块（如`backtest`, `utils`），并配备了`pytest`单元测试，保证了核心逻辑的正确性。

* 券商集成 (长桥): 项目已集成LongPort OpenAPI，可通过命令行工具直接获取股票的实时报价，并根据`gemini-2.5-pro`策略结果生成并执行调仓交易指令。

## 核心策略流程

本策略结合了量化筛选的广度和 AI 深度分析的优势，分为两个核心阶段：

### 阶段一：多因子量化初筛

此阶段利用财务数据快速筛选出一个具备良好基本面特征的股票池。

1. 多因子模型: 结合多个财务指标来综合评估公司质量。本策略使用的因子及其权重在 `src/stock_analysis/preliminary_selection.py` 的 `FACTOR_WEIGHTS` 中定义。

    * `cfo` (经营活动现金流): 正向因子，越高越好。

    * `ceq` (总股东权益): 正向因子，越高越好。

    * `txt` (所得税): 正向因子，正的所得税通常意味着公司在盈利。

    * `d_txt` (所得税变化量): 正向因子，所得税的增加可能意味着盈利能力的提升。

    * `d_at` (总资产变化量): 负向因子，总资产的过度扩张可能带来风险。

    * `d_rect` (应收账款变化量): 负向因子，应收账款的快速增加可能是销售质量下降的信号。

2. 滚动窗口平滑: 采用 5 年滚动窗口计算因子得分的平均值，以获得更稳健的排名。

3. 初步筛选: 在每个季度，选出滚动平均因子分排名前20的股票，作为 AI 分析的候选列表。

### 阶段二：Gemini AI 精选与分析

此阶段利用大型语言模型对初选列表进行更深层次的定性与半定量分析。

1. AI 分析框架: `ai_stock_pick.py` 脚本为每个季度的前20名候选股构建详细的提示，要求Gemini模型扮演价值投资者的角色，从基本面、投资逻辑、行业地位和催化因素四个维度进行分析。

    * 基本面分析: 审视营收、利润率和现金流的健康状况。

    * 投资逻辑验证: 阐述核心投资逻辑及主要风险。

    * 行业与宏观视角: 结合当时的宏观经济环境评估公司竞争力。

    * 催化因素观察: 识别潜在的短期或中期催化剂。

2. AI 决策: Gemini 模型根据上述框架，从20只候选股中筛选出它认为最具投资潜力的10只股票，并为每只股票提供一个置信度分数和详细的选股理由。

3. 结构化输出: AI 的选股结果被解析为结构化的 JSON 数据，便于后续分析和回测。

## 项目结构

```tree
.
├── config/
│   ├── config.yaml               # 核心配置文件
│   └── template.yaml             # 配置模板
├── data/
│   └── ... (原始CSV数据)
├── outputs/
│   └── ... (脚本生成的报告、图表和日志)
├── src/
│   └── stock_analysis/
│       ├── __init__.py
│       ├── ai_stock_pick.py      # AI选股与API管理核心逻辑
│       ├── cli.py                  # 命令行接口定义
│       ├── preliminary_selection.py  # 量化初筛逻辑
│       ├── backtest/               # 回测引擎与数据准备
│       │   ├── engine.py
│       │   └── prep.py
│       ├── broker/                 # 券商API客户端
│       │   └── longport_client.py
│       ├── commands/               # 命令处理层 (胶水代码)
│       │   ├── __init__.py
│       │   ├── ai_pick.py
│       │   ├── backtest.py
│       │   ├── lb_account.py
│       │   └── ...
│       ├── services/               # 业务逻辑层
│       │   ├── account_snapshot.py
│       │   └── rebalancer.py
│       ├── renderers/              # 输出渲染层
│       │   ├── diff.py             # Rebalance前后对比渲染
│       │   ├── jsonout.py
│       │   └── table.py
│       └── utils/                  # 通用工具 (配置、日志、路径)
│           ├── config.py
│           ├── logging.py
│           └── paths.py
├── .env
├── pyproject.toml
└── README.md
```

## 数据源

项目需要以下位于`data/`目录的原始 CSV 文件：

1. `us-balance-ttm.csv`: 资产负债表数据 (TTM)。

2. `us-cashflow-ttm.csv`: 现金流量表数据 (TTM)。

3. `us-income-ttm.csv`: 利润表数据 (TTM)。

4. `us-shareprices-daily.csv`: 日频股价数据。

5. `sp500_historical_constituents.csv`: S&P 500 历史成分股数据。

6. `us-companies.csv`: 公司基本信息，用于丰富报告。

*本项目使用的原始数据可从SimFin获取。请确保下载的CSV文件格式与说明一致。*

## 输出文件

脚本执行成功后，会在`outputs/`目录下生成以下文件：

* `point_in_time_backtest_quarterly_sp500_historical.xlsx`: [量化初筛结果] 每个季度筛选出的前 20 名候选股票。

* `point_in_time_ai_stock_picks_all_sheets.xlsx`: [AI 精选结果] AI 从候选池中筛选出的 10 只股票，包含置信度和详细理由。

* `ai_quarterly_strategy_returns.png`: [AI 策略回测图] 最终 AI 精选组合的累计收益曲线图。

* `quarterly_strategy_returns.png`: [量化策略回测图] (可选) 未经 AI 筛选的量化组合的回测表现图。

* `spy_benchmark_returns.png`: [SPY 基准回测图] (可选) SPY ETF 的同期表现图。

* `ai_backtest.log`: AI 策略回测期间的详细日志。

* `rebalancing_diagnostics_log.csv`: 回测诊断日志，记录模型选股与实际可交易股票的差异。


## 如何运行

这是一个多步骤的工作流。请严格按顺序执行以下命令。

### 准备工作: 环境设置

1. 安装依赖库:

    Python 版本: 项目要求 Python >=3.10 且 <3.11。
    安装: 项目依赖在 `pyproject.toml` 中定义。推荐使用虚拟环境，并通过以下命令安装（这会自动安装 `stockq` 命令行工具）：

    ```bash
    # 确保pip是最新版本
    pip install --upgrade pip
    
    # 从项目根目录运行
    pip install -e .


    # --- 或者使用uv ---
    # 开发环境下使用
    uv sync
    
    # CI/发布环境
    uv sync --no-dev

    # 仅安装开发的依赖
    uv sync --only-dev


    ```

2. 配置API密钥:

    在项目根目录下，将`.env.example`文件复制一份并重命名为`.env`。然后填入你的真实凭据。

    Gemini AI 凭据：

    ```dotenv
    # 你至少需要提供一个
    GEMINI_API_KEY="YOUR_API_KEY_HERE"

    # 可选，用于提高并发和稳定性
    GEMINI_API_KEY_2="YOUR_SECOND_API_KEY_HERE"
    GEMINI_API_KEY_3="YOUR_THIRD_API_KEY_HERE"
    ```

    LongPort OpenAPI 凭据：

    ```dotenv
    # 从 LongPort 开发者中心获取
    LONGPORT_APP_KEY="your_app_key_here"
    LONGPORT_APP_SECRET="your_app_secret_here"
    
    # 使用真实账户 Token 即可
    LONGPORT_ACCESS_TOKEN="your_real_access_token_here"
    ```

3. 配置回测参数:

    复制 config/template.yaml 为 config/config.yaml。根据您的需求修改回测的时间范围和初始资金。

    *回测周期在动态模式下会自行使用所有可用数据，考虑到不同的测试数据可能对应的可用数据的时间范围有所不用，建议探索出多个测试标的都存在有效数据的时间范围，然后使用固定模式限定回测周期。*

    ```yaml
    backtest:
    period_mode: fixed  # fixed 或 dynamic
    start: 2021-04-02
    end: 2025-07-02
    initial_cash: 1000000
    ```

## JSON格式选股提示词

```text
You will receive a single JSON document containing one period of preliminary results.

## Task
Based on **Buffett-style investment logic**, select exactly `{top_n}` (in this time, top_n = 10) most promising stocks **only from the provided candidates**, and produce one AI stock-pick JSON object.

## Analysis Time Point (Critical)
Limit all analysis to the market environment at **{analysis_date}**. If this date exceeds your training data cutoff, reason using timeless fundamentals and the provided JSON only. Do not use events after {analysis_date}.

## Candidate Set
You must select only from the tickers listed in the input JSON (field: rows[*].ticker). Do not invent tickers.

## Buffett Logic Checklist (use for your internal reasoning; do NOT output text)
- Moat and durability of cash flows
- ROIC and reinvestment runway
- Earnings quality and free cash flow conversion
- Capital allocation discipline and leverage prudence
- Valuation sanity relative to quality (margin of safety)
- Key risks and industry structure as of {analysis_date}
- Near- to mid-term catalysts consistent with the above

## Strict Output Contract
Return **one** JSON object with the following shape and nothing else:

{
  "schema_version": 1,
  "source": "ai_pick",
  "trade_date": "{trade_date}",
  "data_cutoff_date": "{data_cutoff_date}",
  "universe": "{universe}",
  "model": "{model_name_or_empty}",
  "prompt_version": "{prompt_version}",
  "params": {"top_n": {top_n}},
  "picks": [
    {
      "ticker": "<from candidates>",
      "rank": 1,
      "confidence": <integer 1-10>,
      "rationale": "<<= 80 words; concise, period-accurate>"
    }
    // exactly {top_n} items, ranks 1..{top_n} with no gaps
  ]
}

## Hard Rules
- Exactly {top_n} items in "picks".
- All "ticker" values must come from the candidate list.
- "rank" must be consecutive integers 1..{top_n}.
- "confidence" must be an **integer** from 1 to 10.
- "rationale" is concise, no empty fields, no placeholders.
- Output **only** the JSON object. No markdown, no prose, no code fences.

## Self-check (must enforce before returning)
- Count(picks) == {top_n}
- Unique(ticker) == {top_n}
- All ranks present and consecutive
- All confidence are integers in [1,10]
- No fields are null/empty
```

## 项目测试

本项目包含一套 pytest 测试。通过在项目根目录运行以下命令来执行所有测试：

```bash
pytest
```

### 测试分类

#### 单元测试 (Unit Tests)

- 标记: `@pytest.mark.unit`

- 特点: 快速、独立、不依赖外部资源

- 包含: 函数逻辑测试、数据处理测试、算法验证等

- 运行时间: 通常 < 1秒

#### 集成测试 (Integration Tests)

- 标记: `@pytest.mark.integration`

- 特点: 较慢、可能依赖外部API或数据库

- 包含: API调用测试、数据库操作测试、文件I/O测试

- 运行时间: 可能需要几秒到几分钟

- 注意: 默认情况下被跳过，需要显式运行

#### 端到端测试 (E2E Tests)

- 标记: `@pytest.mark.e2e`

- 特点: 测试完整的工作流程

- 包含: CLI命令测试、完整流程测试

- 运行时间: 可能需要较长时间

#### 其他标记

- `@pytest.mark.slow`: 运行时间较长的测试

- `@pytest.mark.requires_api`: 需要外部API访问的测试

- `@pytest.mark.requires_db`: 需要数据库访问的测试

### 运行测试

#### 默认运行（仅单元测试）

```bash
# 运行所有单元测试，跳过integration测试
pytest

# 或者显式指定
pytest -m "not integration"
```

#### 运行所有测试

```bash
# 运行包括integration测试在内的所有测试
pytest -m ""

# 或者
pytest --no-cov -m ""
```

#### 运行特定类型的测试

```bash
# 仅运行单元测试
pytest -m "unit"

# 仅运行集成测试
pytest -m "integration"

# 仅运行端到端测试
pytest -m "e2e"

# 运行快速测试（排除慢测试）
pytest -m "not slow"

# 运行不需要API的测试
pytest -m "not requires_api"
```

#### 运行特定目录的测试

```bash
# 仅运行单元测试目录
pytest tests/unit/

# 仅运行集成测试目录
pytest tests/integration/

# 仅运行端到端测试目录
pytest tests/e2e/
```

#### 覆盖率报告

```bash
# 生成详细的覆盖率报告
pytest --cov=stock_analysis --cov-report=html

# 查看未覆盖的行
pytest --cov=stock_analysis --cov-report=term-missing

# 设置覆盖率阈值
pytest --cov=stock_analysis --cov-fail-under=80
```

### CI/CD 配置

#### 默认行为

- CI默认只运行单元测试（快速反馈）

- 覆盖率要求达到75%

- 集成测试被跳过以避免外部依赖问题

#### 完整测试

在需要完整测试时（如发布前），可以运行：

```bash
pytest -m "" --cov=stock_analysis --cov-report=term-missing
```

### 测试编写指南

#### 标记测试

```python
import pytest

@pytest.mark.unit
def test_fast_function():
    """快速的单元测试"""
    assert True

@pytest.mark.integration
@pytest.mark.requires_api
def test_api_call():
    """需要API访问的集成测试"""
    # 测试代码
    pass

@pytest.mark.integration
@pytest.mark.requires_db
def test_database_operation():
    """需要数据库的集成测试"""
    # 测试代码
    pass

@pytest.mark.slow
def test_long_running_process():
    """运行时间较长的测试"""
    # 测试代码
    pass
```

#### 跳过条件

```python
@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("API_KEY"),
    reason="API密钥未配置，跳过集成测试"
)
def test_with_api_key():
    """需要API密钥的测试"""
    pass
```

#### 参数化测试

```python
@pytest.mark.unit
@pytest.mark.parametrize("input,expected", [
    ("test", "TEST"),
    ("hello", "HELLO"),
])
def test_uppercase(input, expected):
    assert input.upper() == expected
```

### 故障排除

#### 常见问题

1. 集成测试失败

   * 检查API密钥是否配置

   * 检查网络连接

   * 检查外部服务状态

2. 覆盖率不足

   * 运行 `pytest --cov=stock_analysis --cov-report=html` 查看详细报告

   * 添加缺失的测试用例

3. 测试运行缓慢

   - 使用 `pytest -m "not slow"` 跳过慢测试

   - 检查是否有未标记的慢测试

#### 调试测试

```bash
# 显示详细输出
pytest -v

# 显示print语句
pytest -s

# 在第一个失败时停止
pytest -x

# 显示最慢的10个测试
pytest --durations=10
```

### 最佳实践

1. 测试隔离: 每个测试应该独立，不依赖其他测试的状态

2. 快速反馈: 单元测试应该快速运行，提供即时反馈

3. 合理标记: 正确标记测试类型，确保CI效率

4. 模拟外部依赖: 在单元测试中使用mock避免外部依赖

5. 清晰命名: 测试名称应该清楚描述测试的内容和预期

6. 适当覆盖: 关注关键路径和边界情况的测试覆盖

### 示例测试结构

```
tests/
├── unit/                    # 单元测试
│   ├── test_tidy_ticker.py
│   ├── test_preliminary_selection.py
│   └── test_ai_result_parsing.py
├── integration/             # 集成测试
│   ├── test_db_io.py
│   ├── test_longbridge_quote_integration.py
│   └── test_price_data_completeness.py
├── e2e/                     # 端到端测试
│   ├── test_cli_smoke.py
│   └── test_cli_lb_e2e.py
└── README.md               # 本文件
```
