"""测试数据库读取与数据源准备模块

测试数据库操作相关功能，包括：
- load_spy_data 和 load_price_feeds：数据库不存在时报错、有但无数据时报错、填补Dividend空值、返回索引为Date
- load_data_to_db：建表入库成功并建了复合索引
"""

import datetime
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from stock_analysis.backtest.prep import load_price_feeds, load_spy_data
from stock_analysis.load_data_to_db import main as load_data_main


class TestLoadSpyData:
    """测试SPY数据加载函数"""
    
    def create_test_database(self, db_path: Path, include_data: bool = True) -> None:
        """创建测试数据库
        
        Args:
            db_path: 数据库文件路径
            include_data: 是否包含测试数据
        """
        con = sqlite3.connect(db_path)
        
        # 创建表结构
        con.execute("""
            CREATE TABLE share_prices (
                Date TEXT,
                Ticker TEXT,
                Open REAL,
                High REAL,
                Low REAL,
                Close REAL,
                Volume INTEGER,
                Dividend REAL
            )
        """)
        
        if include_data:
            # 插入测试数据
            test_data = [
                ('2022-01-03', 'SPY', 477.71, 479.98, 477.51, 478.96, 76196200, 0.0),
                ('2022-01-04', 'SPY', 478.31, 478.65, 474.73, 475.01, 99310400, 0.0),
                ('2022-01-05', 'SPY', 474.17, 474.17, 467.04, 467.94, 134235000, 0.0),
                ('2022-01-06', 'SPY', 467.71, 470.58, 462.66, 463.04, 111598600, 0.0),
                ('2022-01-07', 'SPY', 464.26, 466.47, 461.72, 462.32, 86185500, 0.0),
                # 包含一些有红利的数据
                ('2022-03-18', 'SPY', 440.00, 445.00, 439.00, 444.00, 50000000, 1.57),
                ('2022-06-17', 'SPY', 370.00, 375.00, 368.00, 372.00, 60000000, 1.61),
                # 包含一些Dividend为NULL的数据
                ('2022-01-10', 'SPY', 465.00, 467.00, 463.00, 465.50, 75000000, None),
                ('2022-01-11', 'SPY', 466.00, 468.00, 464.00, 467.20, 80000000, None),
            ]
            
            con.executemany(
                "INSERT INTO share_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                test_data
            )
        
        con.commit()
        con.close()
    
    def test_database_not_found(self, tmp_path):
        """测试数据库文件不存在时的异常处理"""
        non_existent_db = tmp_path / "non_existent.db"
        start_date = datetime.datetime(2022, 1, 1)
        end_date = datetime.datetime(2022, 12, 31)
        
        with pytest.raises(FileNotFoundError, match="Database file not found"):
            load_spy_data(non_existent_db, start_date, end_date)
    
    def test_no_data_found(self, tmp_path):
        """测试数据库存在但无数据时的异常处理"""
        db_path = tmp_path / "empty.db"
        self.create_test_database(db_path, include_data=False)
        
        start_date = datetime.datetime(2022, 1, 1)
        end_date = datetime.datetime(2022, 12, 31)
        
        with pytest.raises(ValueError, match="No SPY data found in database"):
            load_spy_data(db_path, start_date, end_date)
    
    def test_successful_data_loading(self, tmp_path):
        """测试成功加载数据"""
        db_path = tmp_path / "test.db"
        self.create_test_database(db_path, include_data=True)
        
        start_date = datetime.datetime(2022, 1, 1)
        end_date = datetime.datetime(2022, 12, 31)
        
        result = load_spy_data(db_path, start_date, end_date)
        
        # 验证返回的DataFrame结构
        assert isinstance(result, pd.DataFrame)
        assert isinstance(result.index, pd.DatetimeIndex)
        
        expected_columns = ['Open', 'High', 'Low', 'Close', 'Volume', 'Dividend']
        assert list(result.columns) == expected_columns
        
        # 验证数据内容
        assert len(result) == 9  # 应该有9行数据
        assert result.index.name == 'Date'
        
        # 验证日期范围
        assert result.index.min().date() >= start_date.date()
        assert result.index.max().date() <= end_date.date()
    
    def test_dividend_null_filling(self, tmp_path):
        """测试Dividend空值填充"""
        db_path = tmp_path / "test.db"
        self.create_test_database(db_path, include_data=True)
        
        start_date = datetime.datetime(2022, 1, 1)
        end_date = datetime.datetime(2022, 12, 31)
        
        result = load_spy_data(db_path, start_date, end_date)
        
        # 验证Dividend列没有空值
        assert not result['Dividend'].isna().any()
        
        # 验证NULL值被填充为0.0
        dividend_values = result['Dividend'].values
        assert 0.0 in dividend_values  # 原本为NULL的应该变成0.0
        assert 1.57 in dividend_values  # 原本有值的应该保持不变
        assert 1.61 in dividend_values
    
    def test_date_filtering(self, tmp_path):
        """测试日期范围过滤"""
        db_path = tmp_path / "test.db"
        self.create_test_database(db_path, include_data=True)
        
        # 测试较小的日期范围
        start_date = datetime.datetime(2022, 1, 3)
        end_date = datetime.datetime(2022, 1, 7)
        
        result = load_spy_data(db_path, start_date, end_date)
        
        # 应该只包含指定日期范围内的数据
        assert len(result) == 5
        assert result.index.min().date() == datetime.date(2022, 1, 3)
        assert result.index.max().date() == datetime.date(2022, 1, 7)
    
    def test_custom_ticker(self, tmp_path):
        """测试自定义股票代码"""
        db_path = tmp_path / "test.db"
        con = sqlite3.connect(db_path)
        
        # 创建包含多个股票的数据
        con.execute("""
            CREATE TABLE share_prices (
                Date TEXT, Ticker TEXT, Open REAL, High REAL, 
                Low REAL, Close REAL, Volume INTEGER, Dividend REAL
            )
        """)
        
        test_data = [
            ('2022-01-03', 'AAPL', 177.83, 182.88, 177.71, 182.01, 104487900, 0.0),
            ('2022-01-04', 'AAPL', 182.63, 182.94, 179.12, 179.70, 99310400, 0.0),
            ('2022-01-03', 'SPY', 477.71, 479.98, 477.51, 478.96, 76196200, 0.0),
            ('2022-01-04', 'SPY', 478.31, 478.65, 474.73, 475.01, 99310400, 0.0),
        ]
        
        con.executemany(
            "INSERT INTO share_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            test_data
        )
        con.commit()
        con.close()
        
        start_date = datetime.datetime(2022, 1, 1)
        end_date = datetime.datetime(2022, 12, 31)
        
        # 测试加载AAPL数据
        result = load_spy_data(db_path, start_date, end_date, ticker="AAPL")
        
        assert len(result) == 2
        assert result['Close'].iloc[0] == 182.01
        assert result['Close'].iloc[1] == 179.70


class TestLoadPriceFeeds:
    """测试价格数据源加载函数"""
    
    def create_multi_ticker_database(self, db_path: Path) -> None:
        """创建包含多个股票的测试数据库"""
        con = sqlite3.connect(db_path)
        
        con.execute("""
            CREATE TABLE share_prices (
                Date TEXT, Ticker TEXT, Open REAL, High REAL,
                Low REAL, Close REAL, Volume INTEGER, Dividend REAL
            )
        """)
        
        # 创建多个股票的测试数据
        test_data = [
            # AAPL数据
            ('2022-01-03', 'AAPL', 177.83, 182.88, 177.71, 182.01, 104487900, 0.0),
            ('2022-01-04', 'AAPL', 182.63, 182.94, 179.12, 179.70, 99310400, 0.0),
            ('2022-01-05', 'AAPL', 179.61, 180.17, 174.64, 174.92, 94537600, 0.0),
            # MSFT数据
            ('2022-01-03', 'MSFT', 331.62, 336.06, 330.59, 334.75, 23454000, 0.0),
            ('2022-01-04', 'MSFT', 334.15, 334.91, 329.93, 331.30, 37811700, 0.0),
            ('2022-01-05', 'MSFT', 330.70, 331.47, 325.83, 325.87, 49047300, 0.0),
            # GOOGL数据（部分缺失）
            ('2022-01-03', 'GOOGL', 2752.88, 2810.00, 2752.88, 2804.18, 1469600, 0.0),
            ('2022-01-05', 'GOOGL', 2800.00, 2825.00, 2750.00, 2751.25, 1500000, 0.0),
            # 包含红利数据
            ('2022-01-06', 'AAPL', 175.00, 176.00, 174.00, 175.50, 80000000, None),
            ('2022-01-06', 'MSFT', 326.00, 328.00, 325.00, 327.20, 45000000, 0.68),
        ]
        
        con.executemany(
            "INSERT INTO share_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            test_data
        )
        con.commit()
        con.close()
    
    def test_database_not_found(self, tmp_path):
        """测试数据库文件不存在时的异常处理"""
        non_existent_db = tmp_path / "non_existent.db"
        tickers = {"AAPL", "MSFT"}
        start_date = datetime.date(2022, 1, 1)
        end_date = datetime.date(2022, 12, 31)
        
        with pytest.raises(FileNotFoundError, match="Database file not found"):
            load_price_feeds(non_existent_db, tickers, start_date, end_date)
    
    def test_no_trading_days_found(self, tmp_path):
        """测试没有找到交易日数据时的异常处理"""
        db_path = tmp_path / "empty.db"
        con = sqlite3.connect(db_path)
        con.execute("""
            CREATE TABLE share_prices (
                Date TEXT, Ticker TEXT, Open REAL, High REAL,
                Low REAL, Close REAL, Volume INTEGER, Dividend REAL
            )
        """)
        con.commit()
        con.close()
        
        tickers = {"AAPL", "MSFT"}
        start_date = datetime.date(2022, 1, 1)
        end_date = datetime.date(2022, 12, 31)
        
        with pytest.raises(ValueError, match="No trading days found in the database"):
            load_price_feeds(db_path, tickers, start_date, end_date)
    
    def test_successful_data_loading(self, tmp_path):
        """测试成功加载多个股票的数据源"""
        db_path = tmp_path / "test.db"
        self.create_multi_ticker_database(db_path)
        
        tickers = {"AAPL", "MSFT", "GOOGL"}
        start_date = datetime.date(2022, 1, 1)
        end_date = datetime.date(2022, 12, 31)
        
        result = load_price_feeds(db_path, tickers, start_date, end_date)
        
        # 验证返回的数据源字典
        assert isinstance(result, dict)
        assert len(result) == 3  # 应该有3个股票的数据源
        
        # 验证每个股票都有对应的数据源
        for ticker in tickers:
            assert ticker in result
            # 验证数据源类型（这里我们主要验证结构，不深入测试backtrader内部）
            assert hasattr(result[ticker], 'dataname')
    
    def test_dividend_filling(self, tmp_path):
        """测试红利数据填充"""
        db_path = tmp_path / "test.db"
        self.create_multi_ticker_database(db_path)
        
        tickers = {"AAPL", "MSFT"}
        start_date = datetime.date(2022, 1, 1)
        end_date = datetime.date(2022, 12, 31)
        
        result = load_price_feeds(db_path, tickers, start_date, end_date)
        
        # 验证数据源被正确创建
        assert "AAPL" in result
        assert "MSFT" in result
        
        # 验证数据源包含预期的数据
        aapl_data = result["AAPL"].dataname
        msft_data = result["MSFT"].dataname
        
        # 验证Dividend列存在且没有NaN值
        assert "Dividend" in aapl_data.columns
        assert "Dividend" in msft_data.columns
        assert not aapl_data["Dividend"].isna().any()
        assert not msft_data["Dividend"].isna().any()
    
    def test_data_deduplication(self, tmp_path):
        """测试数据去重功能"""
        db_path = tmp_path / "test.db"
        con = sqlite3.connect(db_path)
        
        con.execute("""
            CREATE TABLE share_prices (
                Date TEXT, Ticker TEXT, Open REAL, High REAL,
                Low REAL, Close REAL, Volume INTEGER, Dividend REAL
            )
        """)
        
        # 插入重复数据
        test_data = [
            ('2022-01-03', 'AAPL', 177.83, 182.88, 177.71, 182.01, 104487900, 0.0),
            ('2022-01-03', 'AAPL', 177.83, 182.88, 177.71, 182.01, 104487900, 0.0),  # 重复
            ('2022-01-03', 'AAPL', 178.00, 183.00, 178.00, 182.50, 105000000, 0.0),  # 同日期不同数据
            ('2022-01-04', 'AAPL', 182.63, 182.94, 179.12, 179.70, 99310400, 0.0),
        ]
        
        con.executemany(
            "INSERT INTO share_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            test_data
        )
        con.commit()
        con.close()
        
        tickers = {"AAPL"}
        start_date = datetime.date(2022, 1, 1)
        end_date = datetime.date(2022, 12, 31)
        
        result = load_price_feeds(db_path, tickers, start_date, end_date)
        
        # 验证去重后的数据
        aapl_data = result["AAPL"].dataname
        
        # 应该只有2行数据（去重后）
        assert len(aapl_data) == 2
        
        # 验证保留的是最后一条记录（keep='last'）
        jan_3_data = aapl_data.loc[aapl_data.index.date == datetime.date(2022, 1, 3)]
        assert len(jan_3_data) == 1
        assert jan_3_data['Close'].iloc[0] == 182.50  # 应该是最后一条记录的值


class TestLoadDataToDb:
    """测试数据库创建和索引建立"""
    
    def test_database_creation_and_indexes(self, tmp_path):
        """测试数据库创建和索引建立"""
        # 创建临时数据目录和文件
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        
        # 创建最小的测试CSV文件
        balance_sheet_data = "Ticker;Total Assets;Total Liabilities;Publish Date;Fiscal Year\nAAPL;100000;50000;2022-01-01;2022\nMSFT;200000;80000;2022-01-01;2022"
        cash_flow_data = "Ticker;Operating Cash Flow;Publish Date;Fiscal Year\nAAPL;50000;2022-01-01;2022\nMSFT;60000;2022-01-01;2022"
        income_data = "Ticker;Revenue;Net Income;Publish Date;Fiscal Year\nAAPL;300000;80000;2022-01-01;2022\nMSFT;400000;90000;2022-01-01;2022"
        price_data = "Date;Ticker;Open;High;Low;Close;Volume;Dividend\n2022-01-03;AAPL;177.83;182.88;177.71;182.01;104487900;0.0\n2022-01-03;MSFT;331.62;336.06;330.59;334.75;23454000;0.0"
        
        (data_dir / "us-balance-ttm.csv").write_text(balance_sheet_data)
        (data_dir / "us-cashflow-ttm.csv").write_text(cash_flow_data)
        (data_dir / "us-income-ttm.csv").write_text(income_data)
        (data_dir / "us-shareprices-daily.csv").write_text(price_data)
        
        db_path = data_dir / "financial_data.db"
        
        # Mock 路径配置
        with patch('stock_analysis.load_data_to_db.PROJECT_ROOT', tmp_path):
            with patch('stock_analysis.load_data_to_db.DATA_DIR', data_dir):
                with patch('stock_analysis.load_data_to_db.DB_PATH', db_path):
                    # 执行数据库创建
                    load_data_main()
        
        # 验证数据库文件被创建
        assert db_path.exists()
        
        # 验证表和索引
        con = sqlite3.connect(db_path)
        
        try:
            # 检查表是否存在
            tables_query = "SELECT name FROM sqlite_master WHERE type='table'"
            tables = [row[0] for row in con.execute(tables_query).fetchall()]
            
            expected_tables = ['balance_sheet', 'cash_flow', 'income', 'share_prices']
            for table in expected_tables:
                assert table in tables
            
            # 检查索引是否存在
            indexes_query = "SELECT name FROM sqlite_master WHERE type='index'"
            indexes = [row[0] for row in con.execute(indexes_query).fetchall()]
            
            expected_indexes = [
                'idx_balance_sheet_ticker_date',
                'idx_cash_flow_ticker_date', 
                'idx_income_ticker_date',
                'idx_prices_ticker_date'
            ]
            
            for index in expected_indexes:
                assert index in indexes
            
            # 验证数据被正确插入
            balance_count = con.execute("SELECT COUNT(*) FROM balance_sheet").fetchone()[0]
            assert balance_count == 2
            
            price_count = con.execute("SELECT COUNT(*) FROM share_prices").fetchone()[0]
            assert price_count == 2
            
            # 验证ticker清洗功能
            tickers = [row[0] for row in con.execute("SELECT DISTINCT Ticker FROM share_prices").fetchall()]
            assert "AAPL" in tickers
            assert "MSFT" in tickers
            
        finally:
            con.close()
    
    def test_index_performance_verification(self, tmp_path):
        """验证索引确实被创建并可以提升查询性能"""
        # 创建一个包含更多数据的测试数据库
        db_path = tmp_path / "test_performance.db"
        con = sqlite3.connect(db_path)
        
        # 创建表
        con.execute("""
            CREATE TABLE share_prices (
                Date TEXT, Ticker TEXT, Open REAL, High REAL,
                Low REAL, Close REAL, Volume INTEGER, Dividend REAL
            )
        """)
        
        # 插入大量测试数据
        import random
        test_data = []
        tickers = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'AMZN'] * 100  # 500个记录
        dates = ['2022-01-01', '2022-01-02', '2022-01-03', '2022-01-04', '2022-01-05'] * 100
        
        for i in range(500):
            test_data.append((
                dates[i], tickers[i], 
                random.uniform(100, 200), random.uniform(200, 300),
                random.uniform(90, 190), random.uniform(110, 210),
                random.randint(1000000, 10000000), 0.0
            ))
        
        con.executemany(
            "INSERT INTO share_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            test_data
        )
        
        # 创建索引
        con.execute("CREATE INDEX idx_prices_ticker_date ON share_prices (Ticker, Date)")
        con.commit()
        
        # 验证索引存在
        indexes = [row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()]
        assert 'idx_prices_ticker_date' in indexes
        
        # 验证查询计划使用了索引
        explain_result = con.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM share_prices WHERE Ticker = 'AAPL' AND Date = '2022-01-01'"
        ).fetchall()
        
        # 查询计划应该提到使用了索引
        plan_text = ' '.join([str(row) for row in explain_result])
        assert 'idx_prices_ticker_date' in plan_text or 'INDEX' in plan_text.upper()
        
        con.close()


class TestDatabaseIntegration:
    """数据库操作集成测试"""
    
    def test_end_to_end_data_flow(self, tmp_path):
        """端到端测试：从数据库创建到数据加载"""
        # 1. 创建测试数据库
        db_path = tmp_path / "integration_test.db"
        con = sqlite3.connect(db_path)
        
        con.execute("""
            CREATE TABLE share_prices (
                Date TEXT, Ticker TEXT, Open REAL, High REAL,
                Low REAL, Close REAL, Volume INTEGER, Dividend REAL
            )
        """)
        
        # 插入测试数据
        test_data = [
            ('2022-01-03', 'SPY', 477.71, 479.98, 477.51, 478.96, 76196200, 0.0),
            ('2022-01-04', 'SPY', 478.31, 478.65, 474.73, 475.01, 99310400, 0.0),
            ('2022-01-03', 'AAPL', 177.83, 182.88, 177.71, 182.01, 104487900, 0.0),
            ('2022-01-04', 'AAPL', 182.63, 182.94, 179.12, 179.70, 99310400, 0.0),
            ('2022-01-03', 'MSFT', 331.62, 336.06, 330.59, 334.75, 23454000, None),
            ('2022-01-04', 'MSFT', 334.15, 334.91, 329.93, 331.30, 37811700, 0.68),
        ]
        
        con.executemany(
            "INSERT INTO share_prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            test_data
        )
        con.commit()
        con.close()
        
        # 2. 测试SPY数据加载
        start_date = datetime.datetime(2022, 1, 1)
        end_date = datetime.datetime(2022, 12, 31)
        
        spy_data = load_spy_data(db_path, start_date, end_date)
        assert len(spy_data) == 2
        assert not spy_data['Dividend'].isna().any()
        
        # 3. 测试多股票数据源加载
        tickers = {'AAPL', 'MSFT'}
        price_feeds = load_price_feeds(db_path, tickers, start_date.date(), end_date.date())
        
        assert len(price_feeds) == 2
        assert 'AAPL' in price_feeds
        assert 'MSFT' in price_feeds
        
        # 验证数据完整性
        aapl_data = price_feeds['AAPL'].dataname
        msft_data = price_feeds['MSFT'].dataname
        
        assert len(aapl_data) == 2
        assert len(msft_data) == 2
        
        # 验证Dividend填充
        assert not aapl_data['Dividend'].isna().any()
        assert not msft_data['Dividend'].isna().any()
        assert msft_data['Dividend'].iloc[1] == 0.68  # 原有值保持不变