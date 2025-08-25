.bail on
-- 可选：自动备份
-- .backup 'data/financial_data.auto-backup.db'

-- 导入阶段的快车设置：只在本脚本里开，别污染别处
PRAGMA journal_mode=OFF;
PRAGMA synchronous=OFF;
PRAGMA temp_store=MEMORY;
PRAGMA cache_size=-500000;
PRAGMA locking_mode=EXCLUSIVE;

-- 重建空表
.read sql/schema_prices.sql

.mode csv
.separator ;

-- 直接导入到正式表（严格模式：如果 CSV 有重复，后面的唯一索引会报错）
.import --skip 1 data/us-shareprices-daily.csv share_prices

-- 如果你想"宽容"一点，用 staging + UPSERT（替换上面那行）：
-- DROP TABLE IF EXISTS share_prices_stage;
-- CREATE TABLE share_prices_stage AS SELECT * FROM share_prices WHERE 0;
-- .import --skip 1 data/us-shareprices-daily.csv share_prices_stage
-- INSERT INTO share_prices SELECT * FROM share_prices_stage
--   ON CONFLICT(Ticker, Date) DO NOTHING;
-- DROP TABLE share_prices_stage;

-- 创建索引（含唯一索引护栏）
.read sql/indexes_prices.sql

-- 收尾：把 WAL 残留切干净并瘦身
PRAGMA wal_checkpoint(TRUNCATE);
VACUUM;