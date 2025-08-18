-- SQLite性能优化设置
PRAGMA journal_mode=OFF;
PRAGMA synchronous=OFF;
PRAGMA temp_store=MEMORY;
PRAGMA cache_size=-500000;  -- 约500MB缓存
PRAGMA locking_mode=EXCLUSIVE;

-- 删除已存在的表
DROP TABLE IF EXISTS share_prices;

-- 创建价格数据表结构
CREATE TABLE share_prices (
  Ticker TEXT,
  SimFinId INTEGER,
  Date TEXT,
  Open REAL,
  High REAL,
  Low REAL,
  Close REAL,
  "Adj. Close" REAL,
  Volume INTEGER,
  Dividend REAL,
  "Shares Outstanding" INTEGER
);

-- 注意：索引将在数据导入完成后创建，以提高导入性能
-- CREATE INDEX IF NOT EXISTS idx_prices_date ON share_prices(Date);
-- CREATE INDEX IF NOT EXISTS idx_prices_ticker_date ON share_prices(Ticker, Date);
-- CREATE UNIQUE INDEX IF NOT EXISTS idx_prices_unique ON share_prices(Ticker, Date);