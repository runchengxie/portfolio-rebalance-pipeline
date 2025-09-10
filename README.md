# AI 增强的多因子量化选股策略

该项目采用两阶段的量化选股策略。第一阶段使用传统的多因子模型进行初步筛选；第二阶段则利用`gemini-2.5-pro`模型，以后价值投资者的视角对初选列表进行深度分析和精选，最终构建投资组合并使用`backtrader`进行回测。

项目利用`SQLite`进行数据管理，并通过`config/config.yaml`进行统一的参数配置。所有核心操作都通过`stockq`命令行工具执行。

## 回测结果图

![AI策略回测示例](assets/ai_quarterly_strategy_returns.png)

相比SPY，该策略有相对更低的回撤和略微更高的总收益

```bash
==================================================
      AI Quarterly Strategy Backtest Results
==================================================
Time Period Covered:     2016-10-04 to 2025-08-31
Initial Portfolio Value: $1,000,000.00
Final Portfolio Value:   $4,649,106.03
--------------------------------------------------
Total Return:            153.67%
Annualized Return:       11.02%
Max Drawdown:            25.59%
==================================================

==================================================
       SPY Benchmark Results (Total Return)
==================================================
Time Period Covered:     2016-10-04 to 2025-08-29
Initial Portfolio Value: $1,000,000.00
Final Portfolio Value:   $3,411,410.08
--------------------------------------------------
Total Return:            122.71%
Annualized Return:       9.41%
Max Drawdown:            33.23%
==================================================
```

<!-- START doctoc generated TOC please keep comment here to allow auto update -->

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

## 快速开始

所有操作均通过`stockq`命令行工具完成。

常用辅助命令：

- `stockq export`: 在 Excel 和分期 JSON 之间双向转换。
- `stockq validate-exports`: 校验 Excel 与 JSON 的一致性。
- `stockq lb-config`: 显示 LongPort 相关环境配置。
- `stockq targets gen`: 从最新 AI 结果生成可编辑的 `targets.json`，推荐作为实盘起点。

### 配置环境

* 安装依赖: `uv sync`

* 复制 `.env.example` 为 `.env` 并填入你的 API 密钥。

* 复制 `config/template.yaml` 为 `config/config.yaml`。

环境变量要点（.env）：

| 变量 | 示例 | 说明 |
| --- | --- | --- |
| `GEMINI_API_KEY[_2|_3]` | `xxxx` | Gemini API 密钥（可多把，轮换限流） |
| `LONGPORT_REGION` | `cn` | 长桥区域：`hk` 或 `cn` |
| `LONGPORT_ENABLE_OVERNIGHT` | `true` | 是否启用隔夜行情（预览友好） |
| `LONGPORT_APP_KEY` / `LONGPORT_APP_SECRET` | `...` | 长桥应用凭据 |
| `LONGPORT_ACCESS_TOKEN` | `...` | 真实账户访问令牌 |
| `LONGPORT_DEFAULT_ENV` | `real` | 默认账户环境（当前实现仅使用 `real`） |
| `LONGPORT_MAX_NOTIONAL_PER_ORDER` | `20000` | 本地单笔名义金额上限（0=不限制） |
| `LONGPORT_MAX_QTY_PER_ORDER` | `500` | 本地单笔数量上限（0=不限制） |
| `LONGPORT_TRADING_WINDOW_START/END` | `09:30/16:00` | 本地交易时间窗（降级判定） |

可选成本模型与碎股预览（config.yaml）：

```yaml
# 复制 config/template.yaml 为 config/config.yaml 后可按需开启
fees:
  domicile: HK
  commission: 0.0
  platform_per_share: 0.005
  fractional_pct_lt1: 0.012
  fractional_cap_lt1: 0.99
  sell_reg_fees_bps: 0.0

fractional_preview:
  enable: true
  default_step: 0.001
```

> fractional_preview 功能用于在生成调仓计划时，预览如果支持碎股交易，理想的目标股数会是多少，以及当前整数股交易策略与理想状态的差异。


### 阶段一：数据准备与量化初筛

1. 步骤 1：只导财报数据进sqlite数据库，跳过价格

    ```bash
    stockq load-data --skip-prices
    ```

2. 步骤 2: 运行量化初筛策略

    此脚本执行多因子选股逻辑，并将每个季度的前20名候选股保存到`outputs/`目录的 Excel 总表和分期 JSON 文件中。

    ```bash
    stockq preliminary
    ```

### 阶段二：AI 精选与回测

3. 步骤 3: 运行 AI 筛选策略

    此脚本读取上一步生成的 Excel 文件，提交给`gemini-2.5-pro`进行分析，并将 AI 筛选的 10 只股票及其分析理由保存到新的 Excel 文件，同时输出对应的 JSON 文件。

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

    提示：AI JSON 可由 `stockq ai-pick` 直接生成，或通过
    `stockq export --from ai --direction excel-to-json` 从 AI 总表导出。

4. 导入价格数据进sqlite数据库

    ```bash
    生成白名单（从初筛 Excel 聚合去重，按时间窗筛 sheet）
    stockq gen-whitelist --from preliminary --out outputs/selected_tickers.txt --date-start 2016-10-01 --date-end 2025-09-01

    可选：AI 精选作为来源
    stockq gen-whitelist --from ai --out outputs/selected_tickers.txt --date-start 2016-10-01 --date-end 2025-09-01

    仅导白名单价格，并裁日期
    stockq load-data --only-prices --tickers-file outputs/selected_tickers.txt --date-start 2016-10-01 --date-end 2025-09-01
    ```

    * 不传 --excel 时，回测默认优先读取：

        * 初筛：`outputs/preliminary/`（按日期拆分的 JSON 文件）
        * AI：`outputs/ai_pick/`（按日期拆分的 JSON 文件）

      若上述目录不存在，则回退到 Excel：

        * 初筛：`outputs/point_in_time_backtest_quarterly_sp500_historical.xlsx`
        * AI：`outputs/point_in_time_ai_stock_picks_all_sheets.xlsx`

5. 步骤 5: 运行 AI 筛选组合的回测

    此脚本读取 AI 筛选的股票列表，使用`backtrader`引擎进行回测，并生成最终的累计收益图和性能指标。默认情况下，它会优先从 `outputs/ai_pick/` 和 `outputs/preliminary/` 目录中按日期读取 JSON 文件；若缺失则回退到对应的 Excel 文件。

    ```bash
    stockq backtest ai
    ```

### 阶段三：券商集成与实盘操作 (长桥)

5. 查看当下账户情况

    在执行任何交易操作前，先验证 API 连接和账户状态（默认连接真实账户，预览不下单）。

    ```bash
    # 查看LongPort相关环境配置（区域、隔夜、上限、交易时段等）
    stockq lb-config --show

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

6. 生成可编辑的调仓目标（targets JSON）

    为避免“回测产物 = 实盘目标”的耦合，推荐先从最新一期 AI 结果生成一份独立的 targets JSON（可手动修订）。

    ```bash
    # 生成 outputs/targets/{YYYY-MM-DD}.json（自动选取最新 AI JSON）
    stockq targets gen --from ai

    # 指定日期（按 outputs/ai_pick/YYYY/{asof}.json 匹配）
    stockq targets gen --from ai --asof 2025-09-05

    # 或显式指定 Excel/日期/输出位置（Excel 兜底/兼容旧流程）
    stockq targets gen --from ai \
      --excel outputs/point_in_time_ai_stock_picks_all_sheets.xlsx \
      --asof 2025-09-05 \
      --out outputs/targets/2025-09-05.json
    ```

    你可以手动编辑这份 JSON（增加/删除票、加权重/备注），AI 回测产物不会被污染。

7. 使用 targets JSON 干跑预览 / 执行调仓

    `lb-rebalance` 命令默认读取真实账户并生成调仓计划，但不下单；只有添加 `--execute` 时才会真实下单。输入文件支持 targets JSON（推荐）或 AI Excel（总表）。

    干跑预览（推荐先预览）:

    ```bash
    # 使用 targets JSON（推荐）
    stockq lb-rebalance outputs/targets/2025-07-02.json

    # 向后兼容：直接读取 AI Excel 最新期
    stockq lb-rebalance outputs/point_in_time_ai_stock_picks_all_sheets.xlsx
    ```

    审查输出后，如需执行真实交易（谨慎）:

    ```bash
    stockq lb-rebalance outputs/targets/2025-09-05.json --execute

    # 或：AI Excel 最新期
    stockq lb-rebalance outputs/point_in_time_ai_stock_picks_all_sheets.xlsx --execute
    ```

## 可选步骤

* 创建数据库（WSL/Linux 全量重建）

    使用一键全量重建脚本，跨平台、可重复：

    ```bash
    bash scripts/rebuild_db.sh
    ```

    该脚本将：
    - 用 `sqlite3 .import` 高速导入价格数据（`data/us-shareprices-daily.csv`）。

    - 调整并导入财报数据到 `balance_sheet`/`cash_flow`/`income`（通过现有 Python 逻辑完成字段重命名与清洗）。

    - 建立必要索引并优化数据库。

    如需最简方式也可执行（但由于没有调用sqlite原生基于C语言设计的导入机制，所以速度更慢）：

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

* 对比回测 2 (SPY 基准)：评估 AI 策略与 SPY 基准（S&P 500 ETF）的表现（含分红再投资）。

    ```bash
    # 基准含DRIP（分红再投），默认用 99% 仓位，留 1% 现金缓冲
    stockq backtest spy

    # 调整目标仓位 & 日志级别（仅对 backtest 生效）
    stockq backtest spy --target 1.0 --log-level debug

    # 同样可为策略回测调整日志级别（分红与再平衡日志更详细）
    stockq backtest ai --log-level info
    stockq backtest quant --log-level debug
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

## 项目流程图

```mermaid
graph TD;
    subgraph "阶段〇：数据准备"
        A[("CSV 数据源<br/>(财务、价格、成分股)")] -->|执行| B{"stockq load-data /<br/>rebuild_db.sh"};
        B -->|生成/更新| C[("SQLite 数据库<br/>financial_data.db")];
    end

    subgraph "阶段一：量化初筛"
        C -->|读取财务数据| D{"stockq preliminary"};
        D -->|生成| E(["初步候选池<br/>(JSON / Excel)"]);
    end

    subgraph "阶段二：AI 精选"
        E -->|作为输入| F{"stockq ai-pick"};
        F -- "调用 Gemini API" --> G(["AI 精选组合<br/>(JSON / Excel)"]);
    end

    subgraph "阶段三：策略应用"
        subgraph "路径 A：回测 (验证策略有效性)"
            G -->|用于回测| H{"stockq backtest ai"};
            H -->|生成| I[("回测报告 & 图表")];
        end

        subgraph "路径 B：实盘 (执行交易)"
            G -->|1. 生成可编辑目标| J{"stockq targets gen"};
            J -->|2. 生成| K(["<strong>Targets.json</strong><br/>(可手动编辑/审核)"]);
            K -->|3. 作为输入| L{"stockq lb-rebalance"};
            L -- "连接 LongPort API" --> M[("实盘交易")];
        end
    end

    %% --- 样式定义 ---
    %% 数据和产物节点
    classDef dataNode fill:#e6f3ff,stroke:#0055cc,stroke-width:2px
    class A,C,E,G,K dataNode;

    %% 最终输出节点
    classDef outputNode fill:#e6ffed,stroke:#006400,stroke-width:2px
    class I,M outputNode;

    %% 命令行节点
    classDef commandNode fill:#fff2cc,stroke:#d6b656,stroke-width:2px
    class B,D,F,H,J,L commandNode;
```

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

提示：请预留数 GB 级别的磁盘空间（取决于历史覆盖范围与价格频率）。
将上述 CSV 放入 `data/` 目录后再运行导入命令。建议在下载完成后检查列名/行数是否与示例相符，以避免因字段变更导致的导入失败。

## 输出文件

脚本执行成功后，会在`outputs/`目录下生成以下文件/目录：

* `preliminary/`：按调仓日拆分的量化初筛 JSON 文件（回测默认读取）。

* `ai_pick/`：按调仓日拆分的 AI 精选 JSON 文件（回测默认读取）。

* `point_in_time_backtest_quarterly_sp500_historical.xlsx`： [量化初筛结果] 每个季度筛选出的前 20 名候选股票。

* `point_in_time_ai_stock_picks_all_sheets.xlsx`： [AI 精选结果] AI 从候选池中筛选出的 10 只股票，包含置信度和详细理由。

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

    可选：本地风控与交易时段（不设置则为无限制或默认时段）

    ```dotenv
    # 0 表示无限制，仅做本地预防；实盘仍以券商风控为准
    LONGPORT_MAX_NOTIONAL_PER_ORDER="0"     # 单笔金额上限(USD)，如 20000
    LONGPORT_MAX_QTY_PER_ORDER="0"          # 单笔数量上限(股)，如 500

    # 交易时间窗（仅作为降级判定；若能获取到券商会话时间，以会话为准）
    LONGPORT_TRADING_WINDOW_START="09:30"
    LONGPORT_TRADING_WINDOW_END="16:00"
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
