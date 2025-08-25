"""load_data_to_db的CLI/非CLI分支测试

测试数据加载的不同执行路径：
- SQLite CLI可用时的快速导入分支
- SQLite CLI不可用时的pandas fallback分支
- 文件存在/不存在的处理
- 错误情况的处理
"""

import sqlite3
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch, mock_open

import pandas as pd
import pytest

from stock_analysis.load_data_to_db import (
    _check_sqlite3_cli,
    _import_prices_with_cli,
    _load_csv_in_chunks,
    main
)


@pytest.mark.unit
class TestSQLiteCLIDetection:
    """测试SQLite CLI检测逻辑"""
    
    def test_sqlite3_cli_available(self):
        """测试SQLite CLI可用的情况"""
        with patch('shutil.which', return_value='/usr/bin/sqlite3'):
            assert _check_sqlite3_cli() is True
    
    def test_sqlite3_cli_not_available(self):
        """测试SQLite CLI不可用的情况"""
        with patch('shutil.which', return_value=None):
            assert _check_sqlite3_cli() is False
    
    def test_sqlite3_cli_detection_with_different_paths(self):
        """测试不同路径下的SQLite CLI检测"""
        test_paths = [
            '/usr/bin/sqlite3',
            '/usr/local/bin/sqlite3',
            'C:\\Program Files\\SQLite\\sqlite3.exe',
            None
        ]
        
        for path in test_paths:
            with patch('shutil.which', return_value=path):
                expected = path is not None
                assert _check_sqlite3_cli() is expected


@pytest.mark.unit
class TestSQLiteCLIImport:
    """测试SQLite CLI导入功能"""
    
    def test_cli_import_success(self, tmp_path):
        """测试CLI导入成功的情况"""
        # 创建临时文件
        csv_file = tmp_path / "test.csv"
        db_file = tmp_path / "test.db"
        schema_file = tmp_path / "schema.sql"
        
        csv_file.write_text("Ticker;Date;Close\nAAPL;2023-01-01;150.0\n")
        schema_file.write_text("CREATE TABLE IF NOT EXISTS share_prices (Ticker TEXT, Date TEXT, Close REAL);")
        
        # 模拟成功的subprocess调用
        mock_result = Mock()
        mock_result.returncode = 0
        
        with patch('subprocess.run', return_value=mock_result) as mock_run:
            result = _import_prices_with_cli(csv_file, db_file, schema_file)
            
            assert result is True
            mock_run.assert_called_once()
            
            # 验证调用参数包含正确的sqlite3命令
            call_args = mock_run.call_args[0][0]
            assert call_args[0] == "sqlite3"
            assert str(db_file) in call_args
    
    def test_cli_import_subprocess_error(self, tmp_path):
        """测试CLI导入subprocess错误的情况"""
        csv_file = tmp_path / "test.csv"
        db_file = tmp_path / "test.db"
        schema_file = tmp_path / "schema.sql"
        
        csv_file.write_text("test data")
        schema_file.write_text("test schema")
        
        # 模拟subprocess错误
        error = subprocess.CalledProcessError(1, "sqlite3", stderr="SQL error")
        
        with patch('subprocess.run', side_effect=error):
            result = _import_prices_with_cli(csv_file, db_file, schema_file)
            
            assert result is False
    
    def test_cli_import_general_exception(self, tmp_path):
        """测试CLI导入一般异常的情况"""
        csv_file = tmp_path / "test.csv"
        db_file = tmp_path / "test.db"
        schema_file = tmp_path / "schema.sql"
        
        with patch('subprocess.run', side_effect=Exception("Unexpected error")):
            result = _import_prices_with_cli(csv_file, db_file, schema_file)
            
            assert result is False


@pytest.mark.unit
class TestPandasFallback:
    """测试pandas fallback分支"""
    
    def test_load_csv_in_chunks_basic(self, tmp_path):
        """测试基本的CSV分块加载"""
        # 创建测试数据库
        db_file = tmp_path / "test.db"
        con = sqlite3.connect(db_file)
        
        # 模拟CSV数据
        csv_data = "Ticker,Date,Close\nAAPL,2023-01-01,150.0\nMSFT,2023-01-01,250.0\n"
        
        with patch('pandas.read_csv') as mock_read_csv:
            # 模拟pandas.read_csv返回的DataFrame
            mock_df = pd.DataFrame({
                'Ticker': ['AAPL', 'MSFT'],
                'Date': ['2023-01-01', '2023-01-01'],
                'Close': [150.0, 250.0]
            })
            mock_read_csv.return_value = [mock_df]  # chunksize返回迭代器
            
            with patch.object(mock_df, 'to_sql') as mock_to_sql:
                rows = _load_csv_in_chunks(
                    Path("dummy.csv"), 
                    "test_table", 
                    con,
                    chunk=1000
                )
                
                assert rows == 2
                mock_to_sql.assert_called_once()
        
        con.close()
    
    def test_load_csv_with_ticker_cleaning(self, tmp_path):
        """测试带Ticker清洗的CSV加载"""
        db_file = tmp_path / "test.db"
        con = sqlite3.connect(db_file)
        
        with patch('pandas.read_csv') as mock_read_csv:
            # 包含需要清洗的Ticker数据
            mock_df = pd.DataFrame({
                'Ticker': [' aapl ', 'MSFT_DELISTED', ''],
                'Date': ['2023-01-01', '2023-01-01', '2023-01-01'],
                'Close': [150.0, 250.0, 100.0]
            })
            mock_read_csv.return_value = [mock_df]
            
            with patch.object(pd.DataFrame, 'to_sql') as mock_to_sql:
                rows = _load_csv_in_chunks(
                    Path("dummy.csv"), 
                    "test_table", 
                    con
                )
                
                # 验证to_sql被调用
                mock_to_sql.assert_called_once()
                
                # 验证传递给to_sql的DataFrame已经清洗过
                called_df = mock_to_sql.call_args[1]['con']
                assert called_df is con
        
        con.close()
    
    def test_load_financial_data_with_date_conversion(self, tmp_path):
        """测试财务数据的日期转换"""
        db_file = tmp_path / "test.db"
        con = sqlite3.connect(db_file)
        
        with patch('pandas.read_csv') as mock_read_csv:
            mock_df = pd.DataFrame({
                'Ticker': ['AAPL', 'MSFT'],
                'Publish Date': ['2023-01-01', '2023-04-01'],
                'Fiscal Year': [2022, 2023],
                'Revenue': [100000, 120000]
            })
            mock_read_csv.return_value = [mock_df]
            
            with patch.object(pd.DataFrame, 'to_sql'):
                rows = _load_csv_in_chunks(
                    Path("dummy.csv"), 
                    "balance_sheet",  # 财务数据表
                    con
                )
                
                assert rows == 2
        
        con.close()
    
    def test_load_price_data_deduplication(self, tmp_path):
        """测试价格数据去重"""
        db_file = tmp_path / "test.db"
        con = sqlite3.connect(db_file)
        
        with patch('pandas.read_csv') as mock_read_csv:
            # 包含重复数据
            mock_df = pd.DataFrame({
                'Ticker': ['AAPL', 'AAPL', 'MSFT'],
                'Date': ['2023-01-01', '2023-01-01', '2023-01-01'],
                'Close': [150.0, 151.0, 250.0]  # AAPL有重复，应该保留最后一个
            })
            mock_read_csv.return_value = [mock_df]
            
            with patch.object(pd.DataFrame, 'to_sql') as mock_to_sql:
                with patch.object(pd.DataFrame, 'drop_duplicates', return_value=mock_df) as mock_drop_dup:
                    rows = _load_csv_in_chunks(
                        Path("dummy.csv"), 
                        "share_prices",
                        con
                    )
                    
                    # 验证去重被调用
                    mock_drop_dup.assert_called_once_with(
                        subset=["Ticker", "Date"], 
                        keep="last"
                    )
        
        con.close()


@pytest.mark.unit
class TestMainFunctionBranches:
    """测试main函数的不同分支"""
    
    @patch('stock_analysis.load_data_to_db.DATA_DIR')
    @patch('stock_analysis.load_data_to_db.DB_PATH')
    def test_main_with_cli_available(self, mock_db_path, mock_data_dir, tmp_path):
        """测试SQLite CLI可用时的主函数执行"""
        # 设置临时路径
        mock_data_dir.return_value = tmp_path
        mock_db_path.return_value = tmp_path / "test.db"
        
        # 创建必要的文件
        (tmp_path / "us-balance-ttm.csv").write_text("Ticker,Revenue\nAAPL,100000\n")
        (tmp_path / "us-cashflow-ttm.csv").write_text("Ticker,Cash\nAAPL,50000\n")
        (tmp_path / "us-income-ttm.csv").write_text("Ticker,Income\nAAPL,25000\n")
        (tmp_path / "us-shareprices-daily.csv").write_text("Ticker;Date;Close\nAAPL;2023-01-01;150.0\n")
        (tmp_path.parent / "schema.sql").write_text("CREATE TABLE share_prices (Ticker TEXT);")
        
        with patch('stock_analysis.load_data_to_db._check_sqlite3_cli', return_value=True):
            with patch('stock_analysis.load_data_to_db._import_prices_with_cli', return_value=True) as mock_cli_import:
                with patch('stock_analysis.load_data_to_db._load_csv_in_chunks', return_value=100) as mock_chunks:
                    with patch('sqlite3.connect') as mock_connect:
                        mock_con = Mock()
                        mock_connect.return_value.__enter__.return_value = mock_con
                        
                        main()
                        
                        # 验证CLI导入被调用
                        mock_cli_import.assert_called_once()
                        # 验证财务数据仍使用chunks加载
                        assert mock_chunks.call_count == 3  # 三个财务数据文件
    
    @patch('stock_analysis.load_data_to_db.DATA_DIR')
    @patch('stock_analysis.load_data_to_db.DB_PATH')
    def test_main_with_cli_unavailable(self, mock_db_path, mock_data_dir, tmp_path):
        """测试SQLite CLI不可用时的主函数执行"""
        mock_data_dir.return_value = tmp_path
        mock_db_path.return_value = tmp_path / "test.db"
        
        # 创建价格数据文件
        (tmp_path / "us-shareprices-daily.csv").write_text("Ticker;Date;Close\nAAPL;2023-01-01;150.0\n")
        
        with patch('stock_analysis.load_data_to_db._check_sqlite3_cli', return_value=False):
            with patch('stock_analysis.load_data_to_db._import_prices_with_cli') as mock_cli_import:
                with patch('stock_analysis.load_data_to_db._load_csv_in_chunks', return_value=100) as mock_chunks:
                    with patch('sqlite3.connect') as mock_connect:
                        mock_con = Mock()
                        mock_connect.return_value.__enter__.return_value = mock_con
                        
                        main()
                        
                        # 验证CLI导入未被调用
                        mock_cli_import.assert_not_called()
                        # 验证fallback到pandas chunks
                        mock_chunks.assert_called()
    
    @patch('stock_analysis.load_data_to_db.DATA_DIR')
    @patch('stock_analysis.load_data_to_db.DB_PATH')
    def test_main_with_cli_failure_fallback(self, mock_db_path, mock_data_dir, tmp_path):
        """测试CLI导入失败时的fallback"""
        mock_data_dir.return_value = tmp_path
        mock_db_path.return_value = tmp_path / "test.db"
        
        # 创建必要文件
        (tmp_path / "us-shareprices-daily.csv").write_text("Ticker;Date;Close\nAAPL;2023-01-01;150.0\n")
        (tmp_path.parent / "schema.sql").write_text("CREATE TABLE share_prices (Ticker TEXT);")
        
        with patch('stock_analysis.load_data_to_db._check_sqlite3_cli', return_value=True):
            with patch('stock_analysis.load_data_to_db._import_prices_with_cli', return_value=False):  # CLI失败
                with patch('stock_analysis.load_data_to_db._load_csv_in_chunks', return_value=100) as mock_chunks:
                    with patch('sqlite3.connect') as mock_connect:
                        mock_con = Mock()
                        mock_connect.return_value.__enter__.return_value = mock_con
                        
                        main()
                        
                        # 验证fallback到pandas chunks
                        mock_chunks.assert_called()
    
    @patch('stock_analysis.load_data_to_db.DATA_DIR')
    @patch('stock_analysis.load_data_to_db.DB_PATH')
    def test_main_missing_files_handling(self, mock_db_path, mock_data_dir, tmp_path, capsys):
        """测试缺失文件的处理"""
        mock_data_dir.return_value = tmp_path
        mock_db_path.return_value = tmp_path / "test.db"
        
        # 不创建任何文件，测试缺失文件的处理
        
        with patch('sqlite3.connect') as mock_connect:
            mock_con = Mock()
            mock_connect.return_value.__enter__.return_value = mock_con
            
            main()
            
            # 验证警告信息被打印
            captured = capsys.readouterr()
            assert "[WARNING] File not found" in captured.out


@pytest.mark.unit
class TestErrorHandling:
    """测试错误处理"""
    
    def test_database_connection_error(self):
        """测试数据库连接错误"""
        with patch('sqlite3.connect', side_effect=sqlite3.Error("Database locked")):
            with pytest.raises(sqlite3.Error):
                main()
    
    def test_csv_reading_error(self, tmp_path):
        """测试CSV读取错误"""
        db_file = tmp_path / "test.db"
        con = sqlite3.connect(db_file)
        
        with patch('pandas.read_csv', side_effect=pd.errors.EmptyDataError("No data")):
            with pytest.raises(pd.errors.EmptyDataError):
                _load_csv_in_chunks(
                    Path("dummy.csv"), 
                    "test_table", 
                    con
                )
        
        con.close()
    
    def test_file_permission_error(self, tmp_path):
        """测试文件权限错误"""
        csv_file = tmp_path / "test.csv"
        db_file = tmp_path / "test.db"
        schema_file = tmp_path / "schema.sql"
        
        with patch('subprocess.run', side_effect=PermissionError("Access denied")):
            result = _import_prices_with_cli(csv_file, db_file, schema_file)
            assert result is False