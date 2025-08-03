# 多因子量化选股策略（数据库版 + 动态S&P 500成分股）

这是一个经过重构和优化的Python项目，用于实现一个基于多因子模型的量化选股策略，并进行严格的**“时点”（Point-in-Time）**回测。该项目现在使用**SQLite数据库**进行数据管理以提升性能，并利用**S&P 500历史成分股**数据来动态确定每个调仓日的选股范围，使回测更加贴近真实场景。

## 核心策略

本策略基于以下核心思想：

1. **多因子选股模型**: 结合多个财务指标来综合评估一家公司的质量。本脚本使用的因子及其权重在 `run_quarterly_selection.py` 的 `FACTOR_WEIGHTS` 中定义：
    * `cfo` (经营活动现金流): 正向因子，越高越好。
    * `ceq` (总股东权益): 正向因子，越高越好。
    * `txt` (所得税): 正向因子，正的所得税意味着公司在盈利。
    * `d_txt` (所得税变化量): 正向因子，所得税的增加可能意味着盈利能力的提升。
    * `d_at` (总资产变化量): 负向因子，总资产的过度扩张可能带来风险。
    * `d_rect` (应收账款变化量): 负向因子，应收账款的快速增加可能是销售质量下降的信号。

2. **动态投资范围**:
    * 为了确保回测的有效性和代表性，本策略**只在每个调仓日当时属于S&P 500指数的成分股中进行选股**。
    * 这避免了“生存者偏差”，并确保了策略的可投资性。

3. **数据标准化**: 为了综合不同量纲的因子，脚本使用 **Z-score** 方法对每个因子进行标准化处理。

4. **时点（Point-in-Time）回测**:
    * 严格使用财报的 **`Publish Date` (发布日期)** 作为判断信息是否可用的唯一标准，避免了使用财报期末日期而产生的“未来函数”问题。
    * 在每个回测时点，脚本只会筛选出在该时点之前已发布的所有财报数据。

5. **滚动窗口平滑**:
    * 为了使选股结果更加稳健，策略采用 **5年滚动窗口**。
    * 在每个调仓日，脚本会计算过去5年内所有有效财报的因子得分的**平均值**，并基于这个更平滑的平均分对股票进行排名。

6. **投资组合构建**:
    * 在每个调仓周期（默认为**季度**），根据滚动平均因子分对所有符合条件的S&P 500成分股进行排名。
    * 选取排名前 `N` 的股票（当前设为 **20** 支）构建等权重投资组合。

## 项目结构

```
your_project_root/
├── data/
│   ├── financial_data.db            # <== (由脚本生成) SQLite数据库
│   ├── sp500_historical_constituents.csv # S&P 500历史成分股
│   ├── us-balance-ttm.csv           # [原始数据] 资产负债表
│   ├── us-cashflow-ttm.csv          # [原始数据] 现金流量表
│   ├── us-income-ttm.csv            # [原始数据] 利润表
│   └── us-shareprices-daily.csv     # [原始数据] 日频股价
│
├── outputs/
│   └── (此目录由脚本自动创建，用于存放结果)
│
└── src/
    └── stock_analysis/
        ├── load_data_to_db.py           # 1. 数据加载脚本
        ├── run_quarterly_selection.py   # 2. 选股脚本
        ├── run_quarterly_backtest.py    # 3. 回测脚本
        └── enrich_selection_results.py  # (可选) 结果丰富脚本
```

## 数据源

项目需要以下位于 `data/` 目录的**原始CSV文件**来构建数据库：

1. `us-balance-ttm.csv`: 资产负债表数据。
2. `us-cashflow-ttm.csv`: 现金流量表数据。
3. `us-income-ttm.csv`: 利润表数据。
4. `us-shareprices-daily.csv`: 日频股价数据。
5. `sp500_historical_constituents.csv`: S&P 500历史成分股数据，包含 `ticker`, `start_date`, `end_date` 列。

## 如何运行

这是一个多步骤的工作流。请按顺序执行以下脚本。

1. **安装依赖库**:
    项目依赖在 `pyproject.toml` 中定义。推荐使用虚拟环境，并通过以下命令安装所有必需的库：

    ```bash
    # 确保你的pip是最新版本
    pip install --upgrade pip
    # 从项目根目录运行
    pip install -e .
    ```

2. **步骤 1: 创建数据库**:
    首先，运行脚本将所有原始CSV数据加载到SQLite数据库中。此步骤只需在数据更新时运行一次。

    ```bash
    python src/stock_analysis/load_data_to_db.py
    ```

    执行成功后，会在 `data/` 目录下生成一个 `financial_data.db` 文件。

3. **步骤 2: 运行选股策略**:
    此脚本会连接到数据库，执行多因子选股逻辑，并将每个季度的选股结果保存到一个Excel文件中。

    ```bash
    python src/stock_analysis/run_quarterly_selection.py
    ```

4. **步骤 3: 运行价格回测**:
    此脚本会读取上一步生成的Excel选股文件和数据库中的价格数据，使用 `backtrader` 引擎进行详细的回测，并生成最终的累计收益图。

    ```bash
    python src/stock_analysis/run_quarterly_backtest.py
    ```

5. **步骤 4 (可选): 丰富选股结果**:
    如果你想为选股结果添加公司名称、行业等详细信息，可以运行此脚本。它会读取选股Excel文件并生成一个带有“_enriched”后缀的新文件。

    ```bash
    python src/stock_analysis/enrich_selection_results.py
    ```

## 脚本执行流程

1. **`load_data_to_db.py`**:
    * 读取 `data/` 目录下的所有原始CSV文件。
    * 进行数据清洗和格式统一（如股票代码和日期）。
    * 将清洗后的数据写入到 `data/financial_data.db` 数据库的不同表中。
    * 为关键查询列创建索引，以大幅提升后续步骤的性能。

2. **`run_quarterly_selection.py`**:
    * 加载S&P 500历史成分股数据。
    * 从数据库中一次性加载所有公司的财务数据。
    * 根据数据范围生成季度调仓日期序列。
    * 在每个调仓日：
        * **动态确定**当时的S&P 500成分股作为选股范围。
        * 筛选出在该日期前**已知**且属于当前成分股的财报数据。
        * 使用5年滚动窗口，计算每个股票的平均因子分。
        * 对股票按平均分进行降序排名，选出前20名。
        * 存储当期的选股结果。

3. **`run_quarterly_backtest.py`**:
    * 读取选股策略生成的Excel文件，获取每个调仓日的股票列表。
    * 从数据库中加载所有相关股票的日频价格数据。
    * 使用`backtrader`框架，按季度进行调仓，构建等权重投资组合。
    * 计算每个周期的回报率，并最终生成一条累计收益曲线图和详细的回测性能指标。
    * 生成一份**调仓诊断日志** (`rebalancing_diagnostics_log.csv`)，记录模型选出的股票和实际可交易股票的差异。

## 输出文件

脚本执行成功后，会在 `outputs/` 目录下生成以下文件：

* `point_in_time_backtest_quarterly_sp500_historical.xlsx`:
  * 详细记录了每个调仓周期的选股结果。每个工作表以调仓日期命名。
* `point_in_time_backtest_quarterly_sp500_historical.txt`:
  * 与Excel内容相同的纯文本版本，便于快速查看。
* `point_in_time_backtest_quarterly_sp500_historical.png`:
  * 一张图表，展示了在回测期间，每个调仓日符合筛选条件的股票数量。
* `quarterly_strategy_cumulative_returns.png`:
  * 由`backtrader`生成的核心结果：策略累计收益的可视化曲线图。
* `rebalancing_diagnostics_log.csv`:
  * 回测诊断日志，用于分析选出股票无法交易的原因（如缺少价格数据）。
* `point_in_time_backtest_top_20_stocks_enriched.xlsx` (可选):
  * 添加了公司名和行业等信息的丰富化选股结果。

## 项目测试

本项目包含一套 `pytest` 测试，用于验证核心逻辑的正确性。

* `test_portfolio_constituents.py`: 验证每个投资组合中的股票在当时确实是S&P 500的成员。
* `test_price_data_completeness.py`: 验证入选股票在持有期内是否有足够的价格数据用于回测。

你可以通过在项目根目录运行以下命令来执行所有测试：

```bash
pytest
```
