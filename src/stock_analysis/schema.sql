-- SQLite性能优化设置
PRAGMA journal_mode=OFF;
PRAGMA synchronous=OFF;
PRAGMA temp_store=MEMORY;
PRAGMA cache_size=-500000;  -- 约500MB缓存
PRAGMA locking_mode=EXCLUSIVE;

-- 删除已存在的表
DROP TABLE IF EXISTS share_prices;

-- 创建价格数据表
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

-- 创建索引（在数据导入后执行）
-- CREATE INDEX IF NOT EXISTS idx_prices_date ON share_prices(Date);
-- CREATE INDEX IF NOT EXISTS idx_prices_ticker_date ON share_prices(Ticker, Date);
-- 可选唯一约束，防止重复数据：
-- CREATE UNIQUE INDEX IF NOT EXISTS idx_prices_unique ON share_prices(Ticker, Date);