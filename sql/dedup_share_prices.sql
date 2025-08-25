.bail on
-- 可选：自动备份一份，真出岔子还能回滚
.backup 'data/financial_data.backup-before-dedup.db'

PRAGMA foreign_keys=OFF;
BEGIN IMMEDIATE;

-- 去重：每个 (Ticker, Date) 保留最后一条
CREATE TABLE share_prices_dedup AS
  SELECT * FROM share_prices
  WHERE rowid IN (
    SELECT MAX(rowid) FROM share_prices GROUP BY Ticker, Date
  );

-- 用新表替换旧表
DROP TABLE share_prices;
ALTER TABLE share_prices_dedup RENAME TO share_prices;

-- 护栏：以后禁止重复键
CREATE UNIQUE INDEX IF NOT EXISTS idx_prices_unique ON share_prices(Ticker, Date);

-- 需要的辅助索引（按需保留）
CREATE INDEX IF NOT EXISTS idx_prices_date ON share_prices(Date);
CREATE INDEX IF NOT EXISTS idx_prices_ticker_date ON share_prices(Ticker, Date);

COMMIT;

-- 清理、瘦身
PRAGMA wal_checkpoint(TRUNCATE);
VACUUM;
