# SQLite CLI 快速导入指南

## 概述

本项目已优化支持使用 SQLite CLI 进行大文件快速导入，特别适用于处理 755MB+ 的价格数据文件。

## 自动检测机制

`load_data_to_db.py` 脚本会自动检测系统环境：

1. **优先使用 SQLite CLI**：如果系统安装了 `sqlite3` 命令行工具
2. **自动回退 Pandas**：如果 CLI 不可用，使用分块导入方式

## 安装 SQLite CLI（可选，用于最佳性能）

### Windows

1. 下载 SQLite 预编译二进制文件：
   - 访问 https://www.sqlite.org/download.html
   - 下载 "Precompiled Binaries for Windows" 中的 sqlite-tools

2. 解压并添加到 PATH：
   ```cmd
   # 解压到 C:\sqlite
   # 将 C:\sqlite 添加到系统 PATH 环境变量
   ```

3. 验证安装：
   ```cmd
   sqlite3 --version
   ```

### 使用 Chocolatey（推荐）

```powershell
choco install sqlite
```

## 性能对比

| 导入方式 | 755MB 文件 | 内存使用 | 特点 |
|---------|-----------|----------|------|
| SQLite CLI | 2-5 分钟 | 极低 | 最快，直接导入 |
| Pandas 分块 | 5-10 分钟 | 中等 | 稳定，自动回退 |

## 文件结构

```
project/
├── schema.sql                    # SQLite 表结构和性能优化
├── src/stock_analysis/
│   └── load_data_to_db.py       # 智能导入脚本
└── data/
    ├── us-shareprices-daily.csv  # 755MB 价格数据
    └── financial_data.db         # 输出数据库
```

## 使用方法

```bash
# 运行数据导入（自动选择最佳方式）
python -m src.stock_analysis.load_data_to_db
```

## 技术细节

### SQLite CLI 导入命令

```sql
-- 性能优化设置
PRAGMA journal_mode=OFF;
PRAGMA synchronous=OFF;
PRAGMA cache_size=-500000;

-- 导入数据
.separator ;
.import --skip 1 data.csv share_prices

-- 创建索引
CREATE INDEX idx_prices_date ON share_prices(Date);
CREATE INDEX idx_prices_ticker_date ON share_prices(Ticker, Date);
```

### 数据格式支持

- **分隔符**：分号 (`;`)
- **编码**：UTF-8
- **表头**：自动跳过第一行
- **列数**：11 列（Ticker, SimFinId, Date, Open, High, Low, Close, Adj. Close, Volume, Dividend, Shares Outstanding）

## 故障排除

### 常见问题

1. **"sqlite3 not found"**
   - 系统未安装 SQLite CLI
   - 脚本会自动回退到 Pandas 导入

2. **"too many SQL variables"**
   - Pandas 导入时 chunksize 过大
   - 已优化为 200,000 行/块

3. **"no transaction is active"**
   - 已修复：移除手动事务控制
   - 使用上下文管理器自动处理

### 性能调优

- **大文件**：优先安装 SQLite CLI
- **内存限制**：使用 Pandas 分块导入
- **并发读取**：导入完成后自动恢复 WAL 模式

## 验证导入结果

```python
import sqlite3
import pandas as pd

# 连接数据库
con = sqlite3.connect('data/financial_data.db')

# 检查数据量
print("Price data rows:", pd.read_sql("SELECT COUNT(*) FROM share_prices", con).iloc[0,0])
print("Date range:", pd.read_sql("SELECT MIN(Date), MAX(Date) FROM share_prices", con))
print("Unique tickers:", pd.read_sql("SELECT COUNT(DISTINCT Ticker) FROM share_prices", con).iloc[0,0])

con.close()
```

## 注意事项

1. **数据备份**：大文件导入前建议备份原始数据
2. **磁盘空间**：确保有足够空间存储数据库文件（约 1GB+）
3. **内存要求**：Pandas 方式需要至少 4GB 可用内存
4. **索引创建**：在数据导入完成后统一创建索引以提高性能