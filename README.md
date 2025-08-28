# AI 增强的多因子量化选股策略

该项目采用两阶段的量化选股策略。第一阶段使用传统的多因子模型进行初步筛选；第二阶段则利用`gemini-2.5-pro`模型，以后价值投资者的视角对初选列表进行深度分析和精选，最终构建投资组合并使用`backtrader`进行回测。

项目利用`SQLite`进行数据管理，并通过`config/config.yaml`进行统一的参数配置。所有核心操作都通过`stockq`命令行工具执行。

## 回测结果图

![AI策略回测示例](outputs/ai_quarterly_strategy_returns.png)

*(上图为AI策略在2021-04-01至2025-07-01期间的回测表现示例)*

## 执行步骤

所有操作均通过`stockq`命令行工具完成。

### 阶段一：数据准备与量化初筛

1. 步骤 1: 创建数据库

    此脚本将所有原始CSV数据加载到`data/financial_data.db`文件中，并创建索引以加速后续查询。此步骤仅在初次运行时需要执行。

    ```bash
    stockq load-data
    ```

    为了更高效率推荐使用`sqlite3`，Windows用户可通过Powershell在项目根目录执行以下指令：

    ```bash
    sqlite3 "data\financial_data.db" ".read sql\schema.sql" ".separator ;" ".import --skip 1 data\us-shareprices-daily.csv share_prices" "CREATE INDEX IF NOT EXISTS idx_prices_ticker_date ON share_prices(Ticker, Date);"
    ```

    执行成功后，会在 `data/` 目录下生成 `financial_data.db` 文件。

    后续的股价数据更新

    ```bash
    sqlite3 "data\financial_data.db" ".read sql\rebuild_share_prices.sql"
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

4. 步骤 4: 运行 AI 筛选组合的回测

    此脚本读取 AI 筛选的股票列表，使用`backtrader`引擎进行回测，并生成最终的累计收益图和性能指标。

    ```bash
    stockq backtest ai
    ```

### 阶段三：券商集成与实盘操作 (长桥)

5. 查看当下账户情况

    在执行任何交易操作前，先验证 API 连接和账户状态。

    * 默认 `--env test`。

    * `--env real` 允许“只读展示”，但打印一个巨醒目的横幅，告诉你现在是在看真实账户数据。

    * `--env both` 时，除非显式允许 real，否则降级为只展示 test 并给出提示。

    ```bash
    # 验证API凭据和实时报价功能是否正常
    stockq lb-quote AAPL MSFT

    # 只看测试账户（默认）
    stockq lb-account

    # 明确查看真实账户（只读）
    stockq lb-account --env real

    # 同时查看两个账户，并并排输出
    stockq lb-account --env both

    # 只看资金或只看持仓
    stockq lb-account --funds
    stockq lb-account --positions

    # 机器可读
    stockq lb-account --format json
   ```

6. 执行仓位调整/交易: 为了最大限度地保障您的资金安全，`lb-rebalance`命令内置了一套严格的安全执行机制。该机制的核心原则是默认安全：让无风险的操作（如测试和模拟）变得简单，而让有风险的真实交易需要用户进行明确、多重确认。

    请在执行前务必理解以下**行为矩阵**：

    | 命令组合 | 行为描述 |
    | :--- | :--- |
    | `stockq lb-rebalance ... --env test` | 安全模拟: 无论是否添加 `--execute`，此命令都只会在测试环境中进行模拟操作。它用于验证 API 凭据、网络连接和调仓逻辑，绝不会触及您的真实资金。 |
    | `stockq lb-rebalance ... --env real` | 拒绝执行: 为了防止用户误操作（例如，以为自己执行了真实交易但实际上只是模拟），系统会明确拒绝此组合，并提示您必须添加 `--execute` 标志才能在真实环境下运行。这是一个关键的防呆设计。 |
    | `stockq lb-rebalance ... --env real --execute` | 真实交易: 这是唯一会触发真实下单的命令组合。执行此命令前，请务必确认您的调仓计划。所有在代码中定义的风控措施（如单笔最大金额、交易时间窗口）将在此模式下生效。 |

    推荐的执行流程：

    * 测试环境模拟（Dry-Run）:

        ```bash
        # 在一个完全隔离的环境中，检查调仓计划是否符合预期
        stockq lb-rebalance outputs/point_in_time_ai_stock_picks_all_sheets.xlsx --env test
        ```

    3. 仔细检查输出: 审查上一步打印的交易计划，包括股票代码、数量和方向。

    4. 执行真实交易（谨慎操作）:

        ```bash
        # 确认所有信息无误后，才执行真实下单
        stockq lb-rebalance outputs/point_in_time_ai_stock_picks_all_sheets.xlsx --env real --execute
        ```

## 可选步骤

* 对比回测 1 (量化初筛组合): 评估纯量化策略（未经过 AI 筛选的 20 只股票组合）的表现。

    ```bash
    stockq backtest quant
    ```

* 对比回测 2 (SPY 基准)：评估 AI 策略与 SPY 基准（S&P 500 ETF）的表现。

    ```bash
    stockq backtest spy
    ```

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
│       │   ├── lb_quote.py
│       │   ├── lb_rebalance.py
│       │   └── ...
│       ├── services/               # 业务逻辑层
│       │   ├── account_snapshot.py
│       │   └── rebalancer.py
│       ├── renderers/              # 输出渲染层
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

    # 或者使用uv，开发环境下使用
    uv sync
    # CI/发布环境
    uv sync --locked
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
    
    # 根据 --env test 或 --env real 参数自动读取对应 Token
    LONGPORT_ACCESS_TOKEN_TEST="your_test_access_token_here"
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

## 项目测试

本项目包含一套 pytest 测试。通过在项目根目录运行以下命令来执行所有测试：

```bash
pytest
```
