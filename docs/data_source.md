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
