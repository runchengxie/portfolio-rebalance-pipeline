-- 只干一件事：表结构
DROP TABLE IF EXISTS share_prices;

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