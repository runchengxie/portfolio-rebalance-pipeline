# cross_sectional_strategy_solutions

你没看错——美股公司的财报发布时间真的很「各唱各的调」，而且这种参差不齐会给截面量化策略带来 **两大麻烦**：

1. **发布时间差异**

   * 10-K （年报）最晚可在财年结束后 60 / 75 / 90 天才交卷，具体取决于公司市值和 SEC 对其“加速度”分类。
   * 10-Q （季报）则是 40 天或 45 天。([gibsondunn.com][1], [broadridge.com][2], [skadden.com][3])

2. **信息流不对称 → Look-ahead bias**
   如果你在 3 月 31 日就把所有美股公司的上一财年净利润拿来一起做因子打分，实际上你「提前偷看」了 2-3 个月后才会对外披露的数据，回测成绩会被严重美化。([corporatefinanceinstitute.com][4])

---

## 常见处理方案 & 实战建议

| 方案                         | 思路                                                                  | 优缺点                                                               |                                 |
| -------------------------- | ------------------------------------------------------------------- | ----------------------------------------------------------------- | ------------------------------- |
| **1. 只用 Point-in-Time 数据** | 购买/使用 Compustat Snapshot、Capital IQ PIT 等数据库；每条记录都带“首次可见时间 (dldte)” | 最干净；不便宜；下载量大 ([spglobal.com][5], [wrds-www.wharton.upenn.edu][6]) |                                 |
| **2. 人为加滞后**               | 把所有财务指标统一向后移 **n 天**（学术界常用 90 天，保守一点选 120-180 天）                    | 简单粗暴；会牺牲样本量，尤其是小盘/非 12 月年结公司                                      |                                 |
| **3. “异步更新”法**             | 对每只股票单独检测 `filing_date`，有新数据就刷新该行，否则沿用旧值；回测窗口内只用当时「已知」信息            | 代码相对复杂，但信息利用率最高                                                   |                                 |
| **4. 财报季后统一调仓**            | 例如只在 2 月 & 8 月（绝大部分公司已公布）做因子排序                                      | 降低频率，少折腾，适合长期因子                                                   |                                 |
| **5. 实时抓取 EDGAR**          | 用 SEC 实时 API / sec-api 流式接口秒级监听新 10-Q、10-K，并写入自己的「PIT 数据库」          | 自建成本高，但灵活；适合做事件驱动                                                 | ([sec.gov][7], [sec-api.io][8]) |
| **6. 引入“数据陈旧度”特征**         | 把「距上次财报发布日期的天数」作为额外因子，模型自行判断陈旧信息的权重                                 | 对 ML 友好；多一个特征要调参                                                  |                                 |

---

### 代码实现小抄（伪 pandas 示例）

```python
# df_fund = fundamental data with columns: ticker, fiscal_period_end, filing_date, value
# df_px   = daily prices

lag = pd.Timedelta(days=90)  # 滞后窗口
df_fund['available_from'] = df_fund['filing_date'] + lag

# 生成每日因子截面：对当天尚未公开的公司，用上一次公开值（or NaN）
df_factor = (
    df_px[['date', 'ticker']]
    .merge(df_fund, how='left', on='ticker')
    .query('available_from <= date')
    .sort_values(['ticker', 'available_from'])
    .groupby(['date', 'ticker'])
    .last()          # 取该日最新“已知”财务值
    .reset_index()
)
```

---

## 你可能忽略的细节

1. **财报重述 (restatement)**：只有 PIT 数据库才能让你看到「当时市场看到的旧数」，否则会被后来修订覆盖。
2. **非 12 月年结的公司**：简单滞后 90 天往往不够，建议按 `filing_date` 精确对齐。
3. **“晚交作业”罚单 NT-10K/NT-10Q**：个别公司申请延期，再等五天/十五天才真正公布，需要额外处理。([skadden.com][3])
4. **点对点事件与截面策略的混用**：如果你的模型既吃公告异动（事件驱动）又吃长期因子，最好分两个数据管道，避免同一个表里时钟错乱。
5. **交易成本 vs 更新频率**：信息越准，换手率往往越高；记得把 slippage 和佣金也纳入 backtest。

---

### 一句话总结

> **「财务数据不等速」这锅只能从源头吃干净：要么买（PIT 数据库），要么延迟（加滞后），要么自建（实时抓 EDGAR）。**
> 选哪条路看你的预算、团队规模和策略频率。做对了，回测少踩坑；做错了，年化 α 全是幻影。愿你用真数据赚真钱，别让时差掏空了模型的灵魂 😉

[1]: https://www.gibsondunn.com/wp-content/uploads/2024/09/SEC-Filing-Deadline-Calendar-2025.pdf?utm_source=chatgpt.com "[PDF] 2025 SEC Filing Deadlines - Gibson Dunn"
[2]: https://www.broadridge.com/resource/corporate-issuer/edgar-filing-calendar-2025?utm_source=chatgpt.com "EDGAR Filing Calendar 2025 | Broadridge"
[3]: https://www.skadden.com/-/media/files/publications/2024/10/2025-sec-filing/sec-filing-deadlines-financial-statement-staleness-calendars.pdf?rev=4464a12b95fb4eddbaf1765d0450ff62&utm_source=chatgpt.com "[PDF] 2025 SEC Filing Deadlines and Financial Statement Staleness Dates"
[4]: https://corporatefinanceinstitute.com/resources/career-map/sell-side/capital-markets/look-ahead-bias/?utm_source=chatgpt.com "Look-Ahead Bias - Definition and Practical Example"
[5]: https://www.spglobal.com/marketintelligence/en/documents/compustat-brochure_digital.pdf?utm_source=chatgpt.com "[PDF] Compustat® Data from S&P Global Market Intelligence"
[6]: https://wrds-www.wharton.upenn.edu/documents/398/CRSP_-_Compustat_Merged_Database_CCM.pdf?utm_source=chatgpt.com "[PDF] CRSP/Compustat Merged Database - WRDS"
[7]: https://www.sec.gov/search-filings/edgar-application-programming-interfaces?utm_source=chatgpt.com "EDGAR Application Programming Interfaces (APIs) - SEC.gov"
[8]: https://sec-api.io/?utm_source=chatgpt.com "SEC EDGAR Filings API"
