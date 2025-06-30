# 工作流

## 1. 通过多层感知机（MLP）机器学习挖掘解释力强的因子

* 当期盈利 (Earning)：这是最重要的预测因子，符合所有盈利预测模型的直觉。即今年的盈利水平是预测明年盈利的最佳起点。
* 所得税费用 (Income Tax)：所得税费用及其变化量的重要性排在第二和第四位。这背后有深刻的经济学含义：
  * 所得税基于应税收入计算，而应税收入通常比会计利润受到更少的盈余管理操纵。
  * 因此，所得税费用可以被看作是盈利质量（Earnings Quality）和持续性（Persistence）的一个强有力的代理变量。
  * 这个发现与近年来会计领域关于“税收信息含量”的研究趋势不谋而合。
* 经营活动现金流 (Operating Cash Flow)：重要性排在第三位。这也是一个经典的因子，因为现金流是盈利的有力验证，高现金流通常意味着盈利质量更高、持续性更强。
* 普通股权益 (Common Equity)：即公司的账面价值，在早期（如1975年）非常重要，但在后期其重要性有所下降。
* 资产和应收账款的变化量 (Changes in Total Assets / Receivables)：这些变量的变化也提供了关于公司未来增长和盈利质量的重要线索。

## 2. 转化为具体的选股逻辑

| 因子     | 财务指标                                                     | 权重   | 选股逻辑                                                     |
| -------- | ------------------------------------------------------------ | ------ | ------------------------------------------------------------ |
| `cfo`    | 经营活动现金流量净额 (Net Cash from Operating Activities) | +1 | 越高越好。 这是公司主营业务“造血”能力的直接体现，是利润质量的重要保障。充裕的经营现金流代表公司健康。 |
| `ceq`    | 总股东权益 (Total Equity)                                | +1 | 越高越好。 代表公司的净资产，是财务稳定性的基石。较高的股东权益意味着较低的财务杠杆和更强的抗风险能力。 |
| `txt`    | 所得税费用 (Income Tax Expense)                          | +1 | 越高越好。 能够持续缴纳所得税，是公司持续盈利的有力旁证。一个获得大量“税收优惠（负值）”的公司，往往是因为当年亏损。 |
| `d_txt`  | 所得税费用的年度变化 (Change in Income Tax Expense)      | +1 | 越高越好。 所得税费用的增加，通常意味着公司的应税利润在增长，这是一个积极的盈利增长信号。 |
| `d_at`   | 总资产的年度变化 (Change in Total Assets)                | -1 | 越低越好。 这是典型的“应计”类指标。如果公司资产增长过快，但没有相应的利润或现金流支撑，可能意味着低效投资或激进的会计处理。策略偏好稳健增长而非盲目扩张的公司。 |
| `d_rect` | 应收账款的年度变化 (Change in Accounts Receivable)       | -1 | 越低越好。 如果应收账款增长过快（快于销售增长），可能说明公司放宽了信用政策来刺激销售，或者下游客户回款困难。这会增加坏账风险，降低利润质量。 |

## 3. 通过选股逻辑筛选股票

1. Boston Omaha Corporation (BOMN) - 波士顿奥马哈
2. AT&T Inc. (T) - 美国电话电报公司
3. AerSale Corporation (ASLE) - 航空销售公司
4. Exxon Mobil Corporation (XOM) - 埃克森美孚
5. Intel Corporation (INTC) - 英特尔
6. Chevron Corporation (CVX) - 雪佛龙
7. Pfizer Inc. (PFE) - 辉瑞
8. Salesforce, Inc. (CRM) - 赛富时
9. Johnson & Johnson (JNJ) - 强生
10. Comcast Corporation (CMCSA) - 康卡斯特
11. RTX Corporation (RTX) - RTX公司（前身为雷神技术）
12. Berkshire Hathaway Inc. (BRK-A / BRK-B) - 伯克希尔·哈撒韦
13. General Motors Company (GM) - 通用汽车
14. Alphabet Inc. (GOOG / GOOGL) - 谷歌母公司Alphabet
15. GE Aerospace (GE) - GE航空航天（前身为通用电气）
16. Meta Platforms, Inc. (META) - Meta平台（前身为Facebook）
17. Apple Inc. (AAPL) - 苹果公司
18. International Business Machines Corporation (IBM) - IBM
19. Tesla, Inc. (TSLA) - 特斯拉
20. PayPal Holdings, Inc. (PYPL) - 贝宝

## 4. 调用open o3 的投资判定（预先用巴菲特的所有年报股东信内容和文章内容作为提示词，让gemini整理成一个巴菲特的提示词）

*（巴菲特语料库在根目录/buffett_text/）*

## 5. 最后的选股

*（15%的SPY是我的默认设置）*

| 序号 | 代码      | 权重     | 角色定位                  | 要点 & 我对它的“关键假设”                                    |
| ---- | --------- | -------- | ------------------------- | ------------------------------------------------------------ |
| 1    | SPY   | 15 % | 综合核心                  | -                                                            |
| 2    | TSLA  | 10 %     | 高波动期权            | Robotaxi 首发即被监管盯上 ([theguardian.com](https://www.theguardian.com/technology/2025/jun/29/elon-musk-tesla-robotaxi?utm_source=chatgpt.com))                        |
| 3    | GOOG  | 8 %      | AI + Cloud 双引擎         | 监管阴影常在，但生成式 AI 的 TPU+Gemini 跑在自家硬件上是壁垒 |
| 4    | JNJ   | 7 %      | 医疗防御 & 增长           | AAA 信用 + >60 年加息股息王；专利悬崖靠新管线填补            |
| 5    | XOM   | 6 %      | 资源周期核心              | 圭亚那油田现金流+碳捕捉押注；油价波动用股息兜底              |
| 6    | RTX   | 6 %      | 国防+航太                 | 地缘政治顺风，但普惠 GTF 召回仍是黑天鹅 ([reuters.com](https://www.reuters.com/business/aerospace-defense/rtx-expects-3-bln-hit-q3-pratt-whitney-gtf-engine-issues-2023-09-11/?utm_source=chatgpt.com)) |
| 7    | CVX   | 5 %      | 资源周期对冲              | 收购 Hess 锁定圭亚那储量，仲裁仍在拉锯 ([reuters.com](https://www.reuters.com/business/energy/exxon-says-it-is-confident-it-will-win-dispute-over-chevron-hess-deal-2025-05-29/?utm_source=chatgpt.com)) |
| 8    | CRM   | 5 %      | SaaS 现金牛               | Einstein 1 AI 平台驱动提价和黏性 ([salesforce.com](https://www.salesforce.com/news/stories/what-is-einstein-1-platform/?utm_source=chatgpt.com)) |
| 9    | PFE   | 5 %      | 价值 + 高息               | Seagen 并表、ADC 管线能否补上“疫苗悬崖” ([pfizer.com](https://www.pfizer.com/news/press-release/press-release-detail/pfizer-provides-full-year-2025-guidance-and-reaffirms-full?utm_source=chatgpt.com)) |
| 10   | META  | 5 %      | 社交广告+VR 可选成长      | 现金回购+Threads/TikTok 争霸；Reality Labs 仍烧钱            |
| 11   | BOMN  | 4 %      | “小伯克希尔”成长票        | AireBeam 光纤 & 保险 float 早期扩张阶段 ([bostonomaha.com](https://www.bostonomaha.com/businesses/broadband/?utm_source=chatgpt.com)) |
| 12   | INTC  | 4 %      | 翻身仗 / 代工期权         | 18A 工艺按计划推进，Foundry 是 0 or 1 的杠杆 ([newsroom.intel.com](https://newsroom.intel.com/intel-foundry/intel-foundry-achieves-major-milestones?utm_source=chatgpt.com)) |
| 13   | CMCSA | 4 %      | 宽带现金牛 + 主题公园成长 | Peacock 烧钱但宽带壁垒深                                     |
| 14   | GE    | 4 %      | 纯航空发动机              | 拆分后更纯粹，全球机队后市场锁现金流                         |
| 15   | ASLE  | 2 %      | 航空后市场“小型增速股”    | P2F 改装受电商货运拉动                                       |
| 16   | IBM   | 3 %      | 红帽混合云 + 量子占位     | 低估值、稳股息，把“老蓝”当债券看                             |
| 17   | AAPL  | 3 %      | 高波动期权                | 生态+服务毛利；Vision/AI 只是免费期权 |
| 18   | PYPL  | 2 %      | 价值反转票                | 新 CEO 成败未卜，给它一口气                                  |
| 19   | T     | 2 %      | 高息防御                  | 光纤净增 261 k 户/季，债务高但现金流稳 ([rcrwireless.com](https://www.rcrwireless.com/20250424/business/att-q1?utm_source=chatgpt.com)) |

## 6. 回测效果

![回测图表](./outputs/portfolio_performance.png)

```text
--- Backtest Results (2019-01-02 00:00:00 to 2025-06-30) ---
Initial Capital: $100,000.00
Investment Period: 6.48 years

--- Your Portfolio ---
Final Value: $403,172.71
Total Return: 303.17%
Annualized Return (CAGR): 23.99%

--- SPY Benchmark ---
Final Value: $271,740.42
Total Return: 171.74%
Annualized Return (CAGR): 16.67%

--- Performance Comparison ---
Portfolio Alpha (vs Benchmark CAGR): 7.32%
```

## 7. 可供改进

1. 探索变量之间存在很强的交互效应，例如：

    * 销售收入变化 & 销货成本变化：两者共同反映了公司毛利率的变化趋势。

    * 销货成本 & 存货：反映了公司的存货管理效率和成本控制能力。

    * 销售收入 & 应付账款：反映了公司与其供应商的关系和议价能力。

    * 固定资产 & 折旧摊销：反映了公司的资本投资策略和资产回报率。

2. 采用其他深度学习网络模型来挖掘具有解释性的因子
