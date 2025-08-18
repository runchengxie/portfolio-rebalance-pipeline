# AI 增强的多因子量化选股策略

该项目采用两阶段的量化选股策略。第一阶段使用传统的多因子模型进行初步筛选；第二阶段则利用 Gemini-2.5-Pro 模型，以后价值投资者的视角对初选列表进行深度分析和精选，最终构建投资组合并使用 backtrader 进行回测。

项目利用 SQLite 进行数据管理，并通过 config/config.yaml 进行统一的参数配置。所有核心操作都通过 stockq 命令行工具执行。

## 核心特性

* 两阶段混合模型: 结合了基于财务报表数据的量化筛选和大型语言模型的深度分析，实现自动化、多维度的选股流程。

* 时点（Point-in-Time）回测:

  * 避免幸存者偏差: 在每个调仓日，选股范围限定为当时的 S&P 500 指数成分股。

  * 杜绝未来数据: 使用财报的发布日期（Publish Date）作为判断信息是否可用的标准。

* AI筛选:

  * 多 API 密钥池: 支持配置多个 Gemini API 密钥，通过轮换和熔断机制提高请求成功率和稳定性。

  * 智能容错与限速: 内置滑动窗口限速器、指数退避重试和熔断器。系统自动区分 API Key 认证失败（永久移除）、项目级限流（全局冷却）和临时性网络错误（单 Key 临时退避），确保在高并发请求下依然稳健运行。

* 命令行工具 (CLI): 通过 stockq 命令及其子命令（如 load-data, ai-pick, backtest）执行所有核心工作流。

* 集中化配置: 所有回测参数（如时间范围、初始资金）均在 config/config.yaml 中统一管理，便于快速调整和复现实验。

* 模块化与可测试的代码: 项目被重构为逻辑清晰的模块（如 backtest, utils），并配备了 pytest 单元测试，保证了核心逻辑的正确性。

## 核心策略流程

本策略结合了量化筛选的广度和 AI 深度分析的优势，分为两个核心阶段：

### 阶段一：多因子量化初筛

此阶段利用财务数据快速筛选出一个具备良好基本面特征的股票池。

1. 多因子模型: 结合多个财务指标来综合评估公司质量。本策略使用的因子及其权重在 src/stock_analysis/preliminary_selection.py 的 FACTOR_WEIGHTS 中定义：

    * `cfo` (经营活动现金流): 正向因子，越高越好。

    * `ceq` (总股东权益): 正向因子，越高越好。

    * `txt` (所得税): 正向因子，正的所得税通常意味着公司在盈利。

    * `d_txt` (所得税变化量): 正向因子，所得税的增加可能意味着盈利能力的提升。

    * `d_at` (总资产变化量): 负向因子，总资产的过度扩张可能带来风险。

    * `d_rect` (应收账款变化量): 负向因子，应收账款的快速增加可能是销售质量下降的信号。

2. 滚动窗口平滑: 采用 5 年滚动窗口计算因子得分的平均值，以获得更稳健的排名。

3. 初步筛选: 在每个季度，选出滚动平均因子分排名前 20 的股票，作为 AI 分析的候选列表。

### 阶段二：Gemini AI 精选与分析

此阶段利用大型语言模型对初选列表进行更深层次的定性与半定量分析。

1. AI 分析框架: ai_stock_pick.py 脚本为每个季度的前 20 名候选股构建详细的提示（Prompt），要求 Gemini 模型扮演价值投资者的角色，从以下四个维度进行分析：

    * 基本面分析: 审视营收、利润率和现金流的健康状况。

    * 投资逻辑验证: 阐述核心投资逻辑及主要风险。

    * 行业与宏观视角: 结合当时的宏观经济环境评估公司竞争力。

    * 催化因素观察: 识别潜在的短期或中期催化剂。

2. AI 决策: Gemini 模型根据上述框架，从 20 只候选股中筛选出它认为最具投资潜力的 10 只股票，并为每只股票提供一个置信度分数和详细的选股理由。

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
│       ├── ai_stock_pick.py
│       ├── cli.py                  # 命令行接口实现
│       ├── preliminary_selection.py
│       ├── backtest/
│       │   ├── engine.py           # 回测策略类与运行器
│       │   └── prep.py             # 投资组合加载与数据对齐
│       └── utils/
│           ├── config.py           # 配置加载器
│           ├── paths.py            # 全局路径管理
│           └── ...
├── tests/
│   └── ... (单元测试)
├── .env
├── pyproject.toml
└── README.md
```

## 数据源

项目需要以下位于 data/ 目录的原始 CSV 文件：

1. us-balance-ttm.csv: 资产负债表数据 (TTM)。

2. us-cashflow-ttm.csv: 现金流量表数据 (TTM)。

3. us-income-ttm.csv: 利润表数据 (TTM)。

4. us-shareprices-daily.csv: 日频股价数据。

5. sp500_historical_constituents.csv: S&P 500 历史成分股数据。

6. us-companies.csv: 公司基本信息，用于丰富报告。

## 如何运行

这是一个多步骤的工作流。请严格按顺序执行以下命令。

### 准备工作: 环境设置

1. 安装依赖库:

    Python 版本: 项目要求 Python >=3.10 且 <3.11。
    安装: 项目依赖在 pyproject.toml 中定义。推荐使用虚拟环境，并通过以下命令安装：

    ```bash
    # 确保pip是最新版本
    pip install --upgrade pip
    # 从项目根目录运行
    pip install -e .
    ```

2. 配置API密钥:

    在项目根目录下创建一个名为 .env 的文件。该项目支持最多三个API密钥以提高请求的稳健性。

    ```yaml
    # 您至少需要提供一个
    GEMINI_API_KEY="YOUR_API_KEY_HERE"

    # 可选，用于提高并发和稳定性
    GEMINI_API_KEY_2="YOUR_SECOND_API_KEY_HERE"
    GEMINI_API_KEY_3="YOUR_THIRD_API_KEY_HERE"
    ```

    此命令会自动安装 stockq 命令行工具。

3. 配置回测参数:

    复制 config/template.yaml 为 config/config.yaml。根据您的需求修改回测的时间范围和初始资金。

    ```yaml
    backtest:
    period_mode: fixed  # fixed 或 dynamic
    start: 2021-04-02
    end: 2025-07-02
    initial_cash: 1000000
    ```

### 执行步骤

所有操作均通过 stockq 命令行工具完成。

1. 步骤 1: 创建数据库

    此脚本将所有原始 CSV 数据加载到 data/financial_data.db 文件中，并创建索引以加速后续查询。此步骤仅在初次运行时需要执行。

    ```bash
    stockq load-data
    ```

    执行成功后，会在 `data/` 目录下生成 `financial_data.db` 文件。

2. 步骤 2: 运行量化初筛策略

    此脚本执行多因子选股逻辑，并将每个季度的前 20 名候选股保存到 outputs/ 目录的 Excel 文件中。

    ```bash
    bash python -m src.stock_analysis.preliminary_selection
    ```

3. 步骤 3: 运行 AI 筛选策略

    此脚本读取上一步生成的 Excel 文件，提交给 Gemini AI 进行分析，并将 AI 筛选的 10 只股票及其分析理由保存到新的 Excel 文件中。

    ```bash
    stockq ai-pick
    ```

4. 步骤 4: 运行 AI 筛选组合的回测

    此脚本读取 AI 筛选的股票列表，使用 backtrader 引擎进行回测，并生成最终的累计收益图和性能指标。

    ```bash
    stockq backtest ai
    ```

### 可选步骤

* 对比回测 1 (量化初筛组合): 评估纯量化策略（未经过 AI 筛选的 20 只股票组合）的表现。

    ```bash
    stockq backtest quant
    ```

* 对比回测 2 (SPY 基准)：评估 AI 策略与 SPY 基准（S&P 500 ETF）的表现。

    ```bash
    stockq backtest spy
    ```

* 丰富初筛结果: 为步骤2生成的Excel文件添加公司名称、行业等详细信息。

    ```bash
    python -m src.stock_analysis.enrich_selection_results
    ```

## 输出文件

脚本执行成功后，会在 outputs/ 目录下生成以下文件：

* point_in_time_backtest_quarterly_sp500_historical.xlsx: [量化初筛结果] 每个季度筛选出的前 20 名候选股票。

* point_in_time_ai_stock_picks_all_sheets.xlsx: [AI 精选结果] AI 从候选池中筛选出的 10 只股票，包含置信度和详细理由。

* ai_quarterly_strategy_returns.png: [AI 策略回测图] 最终 AI 精选组合的累计收益曲线图。

* quarterly_strategy_returns.png: [量化策略回测图] (可选) 未经 AI 筛选的量化组合的回测表现图。

* spy_benchmark_returns.png: [SPY 基准回测图] (可选) SPY ETF 的同期表现图。

* ai_backtest.log: AI 策略回测期间的详细日志。

* rebalancing_diagnostics_log.csv: 回测诊断日志，记录模型选股与实际可交易股票的差异。

## 项目测试

本项目包含一套 pytest 测试。通过在项目根目录运行以下命令来执行所有测试：

```bash
pytest
```
