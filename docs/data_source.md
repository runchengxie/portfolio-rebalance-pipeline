Below is a menu of places I actually use (or have audited for clients) when I need U.S. fundamentals in bulk. I’ve ranked them roughly by **cost → convenience → cleanliness** so you can see how trade-offs stack up.

---

## 1. Raw & Free (DIY-friendly, time-expensive)

| Source                         | What you get                                                                                | Access path                                                                                         | The catch                                                                                                                                                                                              |
| ------------------------------ | ------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **SEC EDGAR XBRL filings**     | Every 10-K, 10-Q, 8-K, etc. exactly as filed, going back to the mid-1990s                   | • RSS / FTP bulk download  • `sec-api.io` REST endpoints (handy for Python) ([sec-api.io][1])       | You’re parsing *raw* XBRL. That means hundreds of company-specific tags (“OperatingIncomeLossGaapRep” … seriously) and restatements. Expect a weekend (or three) with `pandas`, `networkx` and coffee. |
| **OpenBB Platform**            | 100+ data connectors (Alpha Vantage, FMP, Polygon, …) behind a uniform Python API           | `pip install openbb` then `from openbb import obb` ([algotrading101.com][2], [tinztwinshub.com][3]) | Still subject to each upstream vendor’s limits; some endpoints require your own keys. Great for prototyping, not for nightly production ETL.                                                           |
| **Yahoo Finance (unofficial)** | Point-in-time income, balance-sheet & cash-flow statements; \~20 yrs depth for most tickers | `yfinance`, `yahooquery` or similar wrappers ([github.com][4])                                      | Not an official API; endpoints change without notice, and license forbids redistribution. OK for classroom notebooks, shaky for client deliverables.                                                   |
| **SimFin free tier**           | Standardized statements & common ratios for ≈3 000 U.S. tickers, 20 yrs history             | CSV bulk dumps or REST API after sign-up ([simfin.com][5], [simfin.com][6])                         | Free data are delayed \~1 year and capped at 25 k API calls/day.                                                                                                                                       |
| **Kaggle snapshots**           | Community-curated dumps (e.g., “Full US Fundamentals 1990-2024”)                            | Direct CSV download                                                                                 | One-off static files: great for ML practice, but no incremental updates or corporate actions. Quality varies—always checksum totals.                                                                   |

---

## 2. Budget-Friendly “Prosumer” APIs (≤ \$1 k / yr)

| Vendor                              | Ball-park price                                                                                         | Why people like it                                                                                                                   | Watch-outs                                                 |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------- |
| **Sharadar SF1 (Nasdaq Data Link)** | \$49 / mo personal; 30-day free trial ([data.nasdaq.com][7])                                            | Nice GAAP-to-common-metrics mapping (e.g., `revenue`, `ebit`, `fcf` already computed); covers delisted tickers; CSV, REST, or Python | Slightly lagged (\~1-2 days after EDGAR) and U.S. only.    |
| **Financial Modeling Prep (FMP)**   | Free < 250 calls/day; \~\$200 / yr unlimited                                                            | Fast updates (often same-day) plus alt-data like ESG scores                                                                          | Schema drifts happen—version-pin your code.                |
| **Tiingo Fundamentals**             | \~\$10–20 / mo add-on                                                                                   | Simple JSON, good historical splits/dividends                                                                                        | Only \~5 k U.S. equities; depth limited for micro-caps.    |
| **Koyfin**                          | Free core tier; Pro ≈ \$790 / yr ([koyfin.com][8], [koyfin.com][9], [koyfin.com][10], [getapp.com][11]) | Slick UI *and* (beta) API. Global coverage, pre-calculated ratios, transcript search                                                 | API rate limits still evolving; export currently CSV only. |

---

## 3. Institutional / Academic-Grade (price of a small car)

| Platform                                                             | Typical access route                                                                                            | Why it’s the gold standard                                                                                                                                                           |
| -------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **S\&P Compustat / CRSP (via WRDS)**                                 | University login or corporate site license ([wrds-www.wharton.upenn.edu][12], [wrds-www.wharton.upenn.edu][13]) | 60 + years, survivorship-bias-free, ticker-CUSIP-PERMNO mapping, quarterly *and* monthly fundamentals, corporate actions, industry-level macros. Essential for publishable research. |
| **Bloomberg Terminal / S\&P Capital IQ / FactSet / Refinitiv Eikon** | Dedicated hardware or desktop client (≈ \$24–35 k / seat / yr)                                                  | Intra-day refresh, peer grouping, segment-level breakouts, consensus forecasts, point-in-time revisions. If you need these, you already know why.                                    |
| **Snowflake Marketplace datasets**                                   | SQL read-share                                                                                                  | Same vendors as above, but pay-by-query. Handy if your infra already lives in Snowflake.                                                                                             |

---

## How I’d choose for *machine-learning practice*

1. **First sandbox** → **SimFin** (bulk CSV) or **Sharadar SF1** (clean, cheap, still “real”).
2. **Add raw noise** → Pull the matching filings from **SEC EDGAR** to learn how to reconcile tag drift.
3. **Stress-test models** → Use **OpenBB** as a router to five different vendors and measure how models degrade when definitions change (excellent lesson in data leakage).
4. **Production-grade back-test** → If you have academic access, graduate to **CRSP/Compustat Merged**; otherwise budget for Sharadar + an institutional price feed.

---

### A word on “incomparable line items” you mentioned last time

* **U.S. GAAP ≠ IFRS** and *even within GAAP* firms invent tags (“PretaxIncomeBeforeSpecialSauce”).
* Providers solve this in two ways:

  1. **Taxonomy mapping** (Sharadar, Compustat) – they roll weird tags into canonical fields.
  2. **Leave it raw** (SEC, Yahoo) – you map it yourself.

For ML experiments, consistency beats fidelity: start with a vendor-standardized dataset, then move to raw filings only when you *need* those bespoke metrics.

---

### Quick sanity checklist before you model

* Re-scale everything (common-size statements or z-scores) so model weights aren’t just “big companies good”.
* Handle negative denominators (e.g., ROE when equity < 0) explicitly.
* Watch fiscal-year alignment; many U.S. firms close in late January.
* Lag fundamentals by at least one filing period when predicting returns to avoid peeking.

Happy number-crunching—may your gradients descend and your back-tests not lie!

[1]: https://sec-api.io/?utm_source=chatgpt.com "SEC EDGAR Filings API"
[2]: https://algotrading101.com/learn/openbb-platform-guide/?utm_source=chatgpt.com "OpenBB Platform - A Complete Guide - AlgoTrading101 Blog"
[3]: https://tinztwinshub.com/investment-research/openbb-platform/?utm_source=chatgpt.com "A Beginner's Guide to the OpenBB Platform - Tinz Twins Hub"
[4]: https://github.com/ranaroussi/yfinance?utm_source=chatgpt.com "ranaroussi/yfinance: Download market data from Yahoo! Finance's API"
[5]: https://www.simfin.com/en/fundamental-data-download/?utm_source=chatgpt.com "Financial Data API - Download Stock Fundamental Data - SimFin"
[6]: https://www.simfin.com/en/?utm_source=chatgpt.com "Financial Insights with Fundamental Data & Portfolio Analysis"
[7]: https://data.nasdaq.com/databases/SF1?utm_source=chatgpt.com "Core US Fundamentals Data"
[8]: https://www.koyfin.com/pricing/?utm_source=chatgpt.com "Pricing plans and subscription FAQ - Koyfin"
[9]: https://www.koyfin.com/pricing/plans-comparison/?utm_source=chatgpt.com "Pricing and plans comparison - Koyfin"
[10]: https://www.koyfin.com/?utm_source=chatgpt.com "Koyfin: Comprehensive financial data analysis"
[11]: https://www.getapp.com/business-intelligence-analytics-software/a/koyfin/?utm_source=chatgpt.com "Koyfin 2025 Pricing, Features, Reviews & Alternatives | GetApp"
[12]: https://wrds-www.wharton.upenn.edu/?utm_source=chatgpt.com "Wharton Research Data Services"
[13]: https://wrds-www.wharton.upenn.edu/pages/about/data-vendors/center-for-research-in-security-prices-crsp/?utm_source=chatgpt.com "Center for Research in Security Prices, LLC (CRSP)"

---

## 美股基本面数据源 (免费 vs 付费)

以下列举多种获取美国上市公司财报数据的常见渠道，并对其特点、优缺点、价格及适用场景进行对比。主要关注收入、净利、资产负债表、现金流等原始报表数据，以及PE、ROE、自由现金流、估值等指标数据，尽量覆盖较长的时间跨度（一般目标>10年）。数据获取方式可包括API调用、CSV/Excel下载或网页抓取。

## 免费数据源

| 数据源 | 费用 | 数据内容 | 历史跨度 | 覆盖范围 | 获取方式 | 优缺点 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **SimFin** | 免费 (注册) | 原始财报 (资产负债表、利润表、现金流表); 财务指标 (70+项) | 免费版约5年历史 ¹ | 约5,000只美股 ² | Python API/ CSV/Excel | **优点:**<br> • 数据质量高，可追溯原始SEC报告<br> • 覆盖大盘股，开发友好 ²<br> • 免费版提供基础数据。<br>**缺点:**<br> • 免费账号历史数据仅限5年，更长需付费升级。 |
| **Alpha Vantage** | 免费 (API Key) | 原始财报 (年/季损益表、资产负债表、现金流表); 公司概况与财务比率 (P/E等) | ~20+年历史 ³ | 全球各市场 (NASDAQ等) | REST API (JSON/CSV) | **优点:**<br> • 免费API，涵盖20年以上股价和财务数据 ³<br> • 提供多种财务报表接口 ⁴<br> • 文档完善。<br>**缺点:**<br> • 免费调用频率极限 (如每日限制25次)，适合小规模查询<br> • 无官方技术支持。 |
| **Yahoo Finance (yfinance)** | 免费 | 主要财务指标 (P/E、PB等) 和部分财报摘要 | 无明确历史 (实时/近年) | 大盘及中小盘美股、ETF等 | 第三方库抓取 (如 yfinance, yahoo_fin) | **优点:**<br> • 完全免费、覆盖面广 ⁵<br> • 易用的Python库(yfinance)可快速获取指标和价格。<br>**缺点:**<br> • 官方API已下线 ⁶，需非官方方式抓取<br> • 原始报表数据有限，深度不够<br> • 数据有时不稳定。 |
| **FinancialModelingPrep (FMP)** | 部分免费 (API Key) | 原始财报 (季/年报损益、资产负债表、现金流); 财务比率 | 免费基础版支持少量数据; 付费版30年以上 ⁷ | 主要美股 (高级版含UK/CA) | REST API (JSON/CSV) | **优点:**<br> • 提供标准化审计财报数据 ⁸<br> • 免费版支持有限查询，付费版价格相对低廉<br> • 覆盖范围广 (8万+股票) ⁸。<br>**缺点:**<br> • 免费额度低 (Basic版仅基本资料)<br> • 完整数据需付费 (Starter版约5年历史、$22/月 ⁹; Premium版30年、$59/月 ⁷)<br> • 免费/API调用限制较多。 |
| **Finnhub** | 免费 (API Key) | 标准化财报 (资产负债表、损益表、现金流表); 估值指标 | 30+年历史 (全球公司) | 全球美股及其他市场 | REST API (JSON) | **优点:**<br> • 免费且调用限制宽松<br> • 覆盖全球公司财报，标准化处理，历史跨度长 ¹⁰<br> • 含新闻、另类数据等。<br>**缺点:**<br> • 免费限速 (分钟级)，需要API Key<br> • 中文文档较少。 |
| **SEC EDGAR** | 免费 | 原始10-K/10-Q/XBRL报告 | 1990年代至今 | 美国所有SEC注册公司 | 官方网站下载 / SEC API | **优点:**<br> • 权威原始数据，覆盖最全 (包含OTC等仅注册公司)<br> • 完全免费。<br>**缺点:**<br> • 数据为原始文件 (HTML/XBRL)，需自行解析<br> • 使用复杂。 |
| **公开数据集 (如Kaggle)** | 免费 | 已清洗的财报数据集 | 视具体数据集而定 | 不同来源 (S&P/NASDAQ等) | 下载CSV | **优点:**<br> • 无需编程，可快速获历史数据，用于教学或原型。<br>**缺点:**<br> • 往往不是实时更新<br> • 覆盖和维护不如专业服务<br> • 可能没有完整的最新数据。 |

## 付费数据源

| 数据源 | 费用 | 数据内容 | 历史跨度 | 覆盖范围 | 获取方式 | 优缺点 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **SimFin Pro/付费** | $71+/月 (起) | 同上 (原始财报和数千指标) | 20+年 ² | ~5,000只美国主流股 | 同上 (API/CSV) | **优点:**<br> • 全量访问，无调用限额<br> • 最高20年+历史，数据质量高，可导出CSV ² ¹¹<br> • 适合构建数据库和模型训练。<br>**缺点:**<br> • 需付费订阅，企业级许可昂贵。 |
| **FMP (Starter/ Premium)** | $22/月起 | 同上 (完整版财报+指标) | Starter 5年 ⁹;<br>Premium 30年 ⁷ | 国际市场 | 同上 | **优点:**<br> • 较便宜的付费选项 (Starter $22/月)，提供完整年度报表和比率 ⁹ ⁷<br> • Premium版覆盖全球、历史超30年。<br>**缺点:**<br> • Starter只含年度数据，无季度报表<br> • API调用有等级限制。 |
| **Tiingo 基础数据** | $30/月 (个人版) | 标准化财报 (季/年报) + 财务指标 | 20+年历史 | 约5,500只美股及ADR | REST API | **优点:**<br> • 财报历史长 (20+年)，覆盖S&P500及更多<br> • 另含每日估值指标、风格因子等<br> • API稳定。<br>**缺点:**<br> • 需付费订阅才能获取基本面数据；免费额度无此功能 ¹²。 |
| **Bloomberg/ FactSet等终端** | 极高 (数万/年) | 全面金融数据 (包括财报、估值、分析师数据) | 多十年历史 | 全球市场 (Bloomberg可追溯250,000+股票) | 终端软件/API | **优点:**<br> • 数据极其齐全全面，覆盖面广，服务质量高。<br>**缺点:**<br> • 价格极高，一般机构使用，个人项目难以承受<br> • 数据获取通常通过专有接口。 |
| **Quandl (Nasdaq Data Link) / Sharadar SF1** | 付费 (年费) | 详细历史报表及指标 (Sharadar SF1数据) | 数十年历史 | 美股主流 | CSV/API (需授权) | **优点:**<br> • 结构化良好，包含原始和标准化报表<br> • 可批量下载。<br>**缺点:**<br> • 需付费订阅 (Sharadar SF1部分免费或试用)<br> • 更新依赖供应商。 |
| **Intrinio** | 付费 (多种套餐) | 财报、估值、估算等 | 视计划而定 (一般10年以上) | 美股、中概等 | REST API | **优点:**<br> • 商业API，覆盖广泛指标<br> • 灵活套餐可选。<br>**缺点:**<br> • 免费额度很低，获取原始财报需要高价订阅<br> • 调用受限。 |
| **其他专有服务** | 视具体服务 | (如 Morningstar, Refinitiv, S&P Capital IQ等) | 通常几十年 | 全球市场 | 各自API/终端 | **优点:**<br> • 数据量大、可靠性高。<br>**缺点:**<br> • 成本非常高，一般面向金融机构，个人难以获得。 |

## 推荐用途

* **教学练习 / 原型开发:** 可优先使用 **Yahoo Finance (yfinance)**、**Alpha Vantage** 这类完全免费的API。尽管调用受限或数据深度有限，但易上手，适合做示范、教学和快速实验。**SEC EDGAR** 和 **Kaggle** 公开数据集也适合基础练习。

* **小型项目 / 本地数据库:** **SimFin (免费)** 和 **FMP (免费/低价)** 等平台对数据质量和覆盖度均较好，可用于构建个人量化数据库。SimFin允许CSV批量下载验证数据，FMP免费+付费组合可灵活获取所需财报。**Finnhub** 免费版也可尝试获取较长的标准化财报数据。

* **模型训练 / 大规模回测:** 建议选择有长历史和稳定API的数据源。如 **SimFin付费版** (20年以上历史)、**FMP Premium** (30年)、**Tiingo** 等。这些服务可持续获取完整财务报表和关键指标，适合训练机器学习模型或执行系统性研究。

* **生产部署 / 机构应用:** 可考虑成熟商业数据源，如 **Bloomberg**、**FactSet**、**Refinitiv**、**S&P** 等。虽然费用高昂，但提供最全面、最及时的数据，并有专业支持，适合对数据精度要求极高的环境。对于一般量化团队而言，**Tiingo** 或 **Quandl** 等付费API也是性价比较高的选择。

## 参考资料

1. Get the Most Value with SimFin's Affordable Analytics and Data API Package - `https://www.simfin.com/en/prices/`
2. Financial Data API - Download Stock Fundamental Data - `https://www.simfin.com/en/fundamental-data-download/`
3. API Documentation | Alpha Vantage - `https://www.alphavantage.co/documentation/`
4. (同上)
5. yfinance Library - A Complete Guide - AlgoTrading101 Blog - `https://algotrading101.com/learn/yfinance-guide/`
6. (同上)
7. Pricing | Financial Modeling Prep | FMP - `https://site.financialmodelingprep.com/developer/docs/pricing`
8. Free Stock Market API and Financial Statements API... | FMP - `https://site.financialmodelingprep.com/developer/docs`
9. (参考资料 7)
10. Global Company Financial Statements - Finnhub - `https://finnhub.io/docs/api/financials`
11. (参考资料 1)
12. Evaluating Data Coverage with Tiingo | QuantStart - `https://www.quantstart.com/articles/evaluating-data-coverage-with-tiingo/`
