-- 护栏：防止重复键
CREATE UNIQUE INDEX IF NOT EXISTS idx_prices_unique
  ON share_prices(Ticker, Date);

-- 查询用的辅助索引（按需保留）
CREATE INDEX IF NOT EXISTS idx_prices_date ON share_prices(Date);
CREATE INDEX IF NOT EXISTS idx_prices_ticker_date ON share_prices(Ticker, Date);