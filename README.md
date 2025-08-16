# AI 增强的多因子量化选股策略

这是一个经过重构和优化的Python项目，实现了一个**两阶段**的量化选股策略。第一阶段使用传统的多因子模型进行初步筛选；第二阶段则利用 **gemini-2.5-pro** 模型，以后价值投资者的视角对初选列表进行深度分析和精选，最终构建投资组合并进行严格的**“时点”（Point-in-Time）**回测。

项目利用 **SQLite数据库** 进行高效的数据管理，并结合 **S&P 500历史成分股** 数据来动态确定每个调仓日的选股范围，确保回测的真实性和公平性。

## 核心策略流程

本策略结合了量化筛选的广度和AI深度分析的优势，分为两个核心阶段：

### 阶段一：多因子量化初筛 (Quantitative Screening)

此阶段利用财务数据快速筛选出一个具备良好基本面特征的股票池。

1. **多因子模型**: 结合多个财务指标来综合评估公司质量。本策略使用的因子及其权重在 `quarterly_selection.py` 的 `FACTOR_WEIGHTS` 中定义：

    * `cfo` (经营活动现金流): 正向因子，越高越好。

    * `ceq` (总股东权益): 正向因子，越高越好。

    * `txt` (所得税): 正向因子，正的所得税通常意味着公司在盈利。

    * `d_txt` (所得税变化量): 正向因子，所得税的增加可能意味着盈利能力的提升。

    * `d_at` (总资产变化量): 负向因子，总资产的过度扩张可能带来风险。

    * `d_rect` (应收账款变化量): 负向因子，应收账款的快速增加可能是销售质量下降的信号。

2. **动态投资范围**: 为了避免“幸存者偏差”，策略**只在每个调仓日当时属于S&P 500指数的成分股中进行选股**。

3. **时点（Point-in-Time）回测**: 严格使用财报的 **`Publish Date` (发布日期)** 作为判断信息是否可用的唯一标准，杜绝了使用未来数据的问题。

4. **滚动窗口平滑**: 采用 **5年滚动窗口**，计算每个股票过去5年内所有有效财报的因子得分的**平均值**，以获得更稳健的排名。

5. **回测启动阈值**: 为了保证选股的有效性，策略设置了一个启动阈值。只有当某个调仓日的S&P 500成分股中，满足5年滚动窗口数据要求的合格股票数量**首次超过250只**时，策略才开始正式进行选股和构建投资组合。此前的周期将被跳过，以确保在足够大的股票池中进行筛选。

6. **初步筛选**: 在每个季度，选出滚动平均因子分排名前 **20** 的股票，作为AI分析的候选列表。

### 阶段二：Gemini AI 精选与分析 (AI Refinement)

此阶段利用大型语言模型（LLM）对初选列表进行更深层次的定性与半定量分析。

1. **AI分析框架**: `ai_stock_pick.py` 脚本会为每个季度的前20名候选股构建一个详细的提示（Prompt），要求 Gemini 模型扮演价值投资者的角色，从以下四个维度进行分析：

    * **基本面分析**: 审视营收、利润率和现金流的健康状况。

    * **投资逻辑验证**: 阐述核心投资逻辑及主要风险。

    * **行业与宏观视角**: 结合当时的宏观经济环境（如利率、通胀）评估公司竞争力。

    * **催化因素观察**: 识别潜在的短期或中期催化剂。

2. **AI决策与精选**: Gemini 模型根据上述框架，从20只候选股中筛选出它认为**最具投资潜力的10只股票**，并为每只股票提供一个置信度分数和详细的选股理由。

3. **结构化输出**: AI的选股结果被解析为结构化的数据（JSON），包含股票代码、公司名称、置信度分数和详细的投资逻辑，便于后续分析和回测。

## 项目结构

```tree
your_project_root/
├── data/
│   ├── financial_data.db            # <== (由脚本生成) SQLite数据库
│   ├── sp500_historical_constituents.csv # S&P 500历史成分股
│   ├── us-balance-ttm.csv           # [原始数据] 资产负债表
│   ├── us-cashflow-ttm.csv          # [原始数据] 现金流量表
│   ├── us-income-ttm.csv            # [原始数据] 利润表
│   ├── us-shareprices-daily.csv     # [原始数据] 日频股价
│   └── us-companies.csv             # [原始数据] 公司基本信息
│
├── outputs/
│   └── (此目录由脚本自动创建，用于存放结果)
│
├── src/
│   └── stock_analysis/
│       ├── load_data_to_db.py           # 1. 数据加载脚本
│       ├── quarterly_selection.py       # 2. 量化初筛脚本
│       ├── ai_stock_pick.py             # 3. AI精选脚本
│       ├── backtest_quarterly_ai_pick.py    # 4. AI精选组合回测脚本
│       ├── backtest_quarterly_unpicked.py   # (可选) 量化初筛组合回测脚本 (用于对比)
│       └── enrich_selection_results.py  # (可选) 结果丰富脚本
│
├── tests/
│   ├── test_portfolio_constituents.py   # 测试组合成分股是否在S&P 500内
│   └── test_price_data_completeness.py  # 测试价格数据完整性
│
├── .env                             # 存储API Key的配置文件
├── pyproject.toml                   # 项目依赖与配置
└── README.md                        # 本文档
```

## 数据源

项目需要以下位于 `data/` 目录的**原始CSV文件**：

1. `us-balance-ttm.csv`: 资产负债表数据 (TTM)。

2. `us-cashflow-ttm.csv`: 现金流量表数据 (TTM)。

3. `us-income-ttm.csv`: 利润表数据 (TTM)。

4. `us-shareprices-daily.csv`: 日频股价数据。

5. `sp500_historical_constituents.csv`: S&P 500历史成分股数据。

6. `us-companies.csv`: 公司基本信息，用于丰富报告。

## 如何运行

这是一个多步骤的工作流。请严格按顺序执行以下脚本。

#### **准备工作: 环境设置**

1. **安装依赖库**:

    本项目推荐使用 Python 3.10 版本，项目依赖在 `pyproject.toml` 中定义。推荐使用虚拟环境，并通过以下命令安装：

    ```bash
    # 确保pip是最新版本
    pip install --upgrade pip
    # 从项目根目录运行
    pip install -e .
    ```

2. **配置API密钥**:

    在项目根目录下创建一个名为 `.env` 的文件，并在其中添加您的Google Gemini API密钥：

    ```yaml
    GEMINI_API_KEY="YOUR_API_KEY_HERE"
    ```

#### **执行步骤**

1. **步骤 1: 创建数据库**

    此脚本将所有原始CSV数据加载到SQLite数据库中。此步骤仅在初次运行或数据更新时需要执行。

    ```bash
    python src/stock_analysis/load_data_to_db.py
    ```

    执行成功后，会在 `data/` 目录下生成 `financial_data.db` 文件。

2. **步骤 2: 运行量化初筛策略**

    此脚本执行多因子选股逻辑，并将每个季度的**前20名**候选股保存到Excel文件中。

    ```bash
    python src/stock_analysis/quarterly_selection.py
    ```

3. **步骤 3: 运行AI精选策略**

    此脚本会读取上一步生成的Excel文件，将其作为输入提交给 Gemini AI 进行分析，并将AI精选的**10只股票**及其分析理由保存到一个新的Excel文件中。

    ```bash
    python src/stock_analysis/ai_stock_pick.py
    ```

4. **步骤 4: 运行AI精选组合的回测**

    此脚本读取AI精选的股票列表，使用 `backtrader` 引擎进行详细回测，并生成最终的累计收益图和性能指标。

    ```bash
    python src/stock_analysis/backtest_quarterly_ai_pick.py
    ```

#### **可选步骤**

* **对比回测 (量化初筛组合)**: 如果你想评估纯量化策略的表现（作为基准），可以运行此脚本。它将回测步骤2中生成的未经过AI筛选的20只股票组合。

    ```bash
    python src/stock_analysis/backtest_quarterly_unpicked.py
    ```

* **丰富初筛结果**: 为步骤2生成的Excel文件添加公司名称、行业等详细信息。

    ```bash
    python src/stock_analysis/enrich_selection_results.py
    ```

## 脚本执行流程

1. `load_data_to_db.py`: 读取 `data/` 目录下的CSV文件，进行数据清洗，并将它们写入 `data/financial_data.db` 数据库的不同表中，同时为关键列创建索引以提升性能。

2. `quarterly_selection.py`:

    * 连接数据库，一次性加载所有公司的财务数据。

    * 加载S&P 500历史成分股数据。

    * 按季度遍历每个调仓日，**动态确定**当时的S&P 500成分股作为选股范围。

    * 筛选出在该日期前**已发布**且属于当前成分股的财报。

    * 使用5年滚动窗口计算每个股票的平均因子分，选出**前20名**。

    * 结果输出至 `point_in_time_backtest_quarterly_sp500_historical.xlsx`。

3. `ai_stock_pick.py`:

    * 读取 `point_in_time_backtest_quarterly_sp500_historical.xlsx` 文件。

    * 对每个季度的工作表，将20只候选股列表与公司信息结合，构建详细的Prompt。

    * 调用 Gemini API，要求其根据指定的分析框架（基本面、宏观、风险等）选出**10只**最具潜力的股票。

    * 将AI返回的结构化JSON结果（包含选股理由和置信度）保存到新的Excel文件 `point_in_time_ai_stock_picks_all_sheets.xlsx`。

4. `backtest_quarterly_ai_pick.py`:

    * 读取 `point_in_time_ai_stock_picks_all_sheets.xlsx` 文件。

    * 从数据库加载所有AI入选股票的日频价格数据。

    * 使用 `backtrader` 框架，按季度调仓，构建等权重的 **10只** 股票投资组合。

    * 计算并输出最终的累计收益曲线图和详细的回测性能指标。

## 输出文件

脚本执行成功后，会在 `outputs/` 目录下生成以下文件：

* `point_in_time_backtest_quarterly_sp500_historical.xlsx`: **[量化初筛结果]** 原始候选池。每个季度筛选出的前20名候选股票，是AI分析的输入。

* `point_in_time_ai_stock_picks_all_sheets.xlsx`: **[AI精选结果]** 最终投资组合。AI从上述候选池中精选出的10只股票，包含置信度分数和详细理由，是回测的输入。

* `ai_quarterly_strategy_returns.png`: **[AI策略回测图]** 最终AI精选组合的累计收益曲线图，是项目的核心产出。

* `backtest_log_quarterly_ai_pick.txt`: AI策略回测的详细日志。

* `rebalancing_diagnostics_log.csv`: 回测诊断日志，记录模型选出的股票和实际可交易股票的差异。

* `quarterly_strategy_cumulative_returns.png`: **[量化策略回测图]** (可选) 未经AI筛选的量化组合的回测表现图。

## 项目测试

本项目包含一套 `pytest` 测试，用于验证核心逻辑的正确性。

* `test_portfolio_constituents.py`: 验证每个投资组合中的股票在当时确实是S&P 500的成员。

* `test_price_data_completeness.py`: 验证入选股票在持有期内是否有足够的价格数据用于回测。

你可以通过在项目根目录运行以下命令来执行所有测试：

```bash
pytest
```
