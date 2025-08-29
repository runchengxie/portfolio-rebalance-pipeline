#!/usr/bin/env bash
set -euo pipefail

# Cross-platform full rebuild of SQLite DB from CSVs (optimized for WSL/Linux)

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_PATH="$ROOT_DIR/data/financial_data.db"
CSV_DIR="$ROOT_DIR/data"
SQL_DIR="$ROOT_DIR/sql"

if ! command -v sqlite3 >/dev/null 2>&1; then
  echo "[ERROR] sqlite3 CLI not found. Please install sqlite3." >&2
  exit 1
fi

echo "Rebuilding database at: $DB_PATH"
rm -f "$DB_PATH"

# Initialize DB and create share_prices schema with fast pragmas
sqlite3 "$DB_PATH" <<'SQL'
PRAGMA journal_mode=OFF;
PRAGMA synchronous=OFF;
PRAGMA temp_store=MEMORY;
PRAGMA cache_size=-800000;
.read sql/schema.sql
SQL

echo "Importing CSVs using sqlite3 .import (price data)..."

# Import price data (semicolon-separated)
sqlite3 "$DB_PATH" \
  ".mode csv" \
  ".separator ;" \
  ".import --skip 1 $CSV_DIR/us-shareprices-daily.csv share_prices"

# Index and optimize
sqlite3 "$DB_PATH" \
  "CREATE INDEX IF NOT EXISTS idx_prices_ticker_date ON share_prices(Ticker, Date);" \
  "CREATE INDEX IF NOT EXISTS idx_prices_date ON share_prices(Date);" \
  "ANALYZE;" \
  "VACUUM;"

echo "Importing financial statements via Python loader (with cleanup/renames)..."
# Use the existing Python import for financial tables (handles renames and types)
# Skip prices to avoid duplicate work
SKIP_PRICES=1 "$ROOT_DIR/.venv/bin/python" -c "from stock_analysis.load_data_to_db import main; main()" 2>/dev/null \
  || SKIP_PRICES=1 stockq load-data

echo "Done. Database rebuilt at: $DB_PATH"

