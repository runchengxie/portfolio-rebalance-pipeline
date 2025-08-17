"""测试投资组合加载与清洗模块

测试 backtest.prep 中的投资组合加载逻辑，包括：
- load_portfolios：空sheet跳过、ticker大小写兼容、_DELISTED去尾、NaN过滤、sheet名到调仓日解析
- tidy_ticker：大小写、空白、后缀清理
"""

import datetime
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from stock_analysis.backtest.prep import load_portfolios, tidy_ticker


class TestTidyTicker:
    """测试股票代码清洗函数"""
    
    def test_uppercase_conversion(self):
        """测试大小写转换"""
        input_series = pd.Series(["aapl", "MSFT", "googl", "TsLa"])
        result = tidy_ticker(input_series)
        expected = pd.Series(["AAPL", "MSFT", "GOOGL", "TSLA"], dtype="string")
        pd.testing.assert_series_equal(result, expected)
    
    def test_whitespace_stripping(self):
        """测试空白字符清理"""
        input_series = pd.Series(["  AAPL  ", "\tMSFT\n", " GOOGL", "TSLA "])
        result = tidy_ticker(input_series)
        expected = pd.Series(["AAPL", "MSFT", "GOOGL", "TSLA"], dtype="string")
        pd.testing.assert_series_equal(result, expected)
    
    def test_delisted_suffix_removal(self):
        """测试_DELISTED后缀去除"""
        input_series = pd.Series(["AAPL_DELISTED", "MSFT", "GOOGL_DELISTED", "TSLA"])
        result = tidy_ticker(input_series)
        expected = pd.Series(["AAPL", "MSFT", "GOOGL", "TSLA"], dtype="string")
        pd.testing.assert_series_equal(result, expected)
    
    def test_empty_string_to_na(self):
        """测试空字符串转换为NA"""
        input_series = pd.Series(["AAPL", "", "MSFT", "   ", "GOOGL"])
        result = tidy_ticker(input_series)
        expected = pd.Series(["AAPL", pd.NA, "MSFT", pd.NA, "GOOGL"], dtype="string")
        pd.testing.assert_series_equal(result, expected)
    
    def test_combined_cleaning(self):
        """测试组合清洗逻辑"""
        input_series = pd.Series([
            "  aapl_DELISTED  ",
            "\tMSFT\n",
            "",
            "googl_DELISTED",
            "   ",
            "TSLA"
        ])
        result = tidy_ticker(input_series)
        expected = pd.Series([
            "AAPL",
            "MSFT", 
            pd.NA,
            "GOOGL",
            pd.NA,
            "TSLA"
        ], dtype="string")
        pd.testing.assert_series_equal(result, expected)
    
    def test_numeric_input_conversion(self):
        """测试数值输入的字符串转换"""
        input_series = pd.Series([123, 456.0, "AAPL"])
        result = tidy_ticker(input_series)
        expected = pd.Series(["123", "456.0", "AAPL"], dtype="string")
        pd.testing.assert_series_equal(result, expected)


class TestLoadPortfolios:
    """测试投资组合加载函数"""
    
    def create_test_excel(self, tmp_path: Path, sheets_data: dict) -> Path:
        """创建测试用Excel文件
        
        Args:
            tmp_path: 临时目录路径
            sheets_data: 工作表数据字典，格式为 {sheet_name: DataFrame}
            
        Returns:
            Path: Excel文件路径
        """
        excel_path = tmp_path / "test_portfolios.xlsx"
        
        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            for sheet_name, df in sheets_data.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        return excel_path
    
    def test_file_not_found(self, tmp_path):
        """测试文件不存在时的异常处理"""
        non_existent_path = tmp_path / "non_existent.xlsx"
        
        with pytest.raises(FileNotFoundError, match="Portfolio file not found"):
            load_portfolios(non_existent_path)
    
    def test_empty_sheets_skipped(self, tmp_path):
        """测试空工作表被跳过"""
        sheets_data = {
            "2022-01-01": pd.DataFrame(),  # 空DataFrame
            "2022-04-01": pd.DataFrame({"Ticker": ["AAPL", "MSFT"]}),
            "2022-07-01": pd.DataFrame()   # 另一个空DataFrame
        }
        
        excel_path = self.create_test_excel(tmp_path, sheets_data)
        portfolios = load_portfolios(excel_path)
        
        # 只有非空的工作表应该被包含
        assert len(portfolios) == 1
        assert datetime.date(2022, 4, 1) in portfolios
        assert datetime.date(2022, 1, 1) not in portfolios
        assert datetime.date(2022, 7, 1) not in portfolios
    
    def test_ticker_column_missing(self, tmp_path):
        """测试缺少Ticker列的工作表被跳过"""
        sheets_data = {
            "2022-01-01": pd.DataFrame({"Symbol": ["AAPL", "MSFT"]}),  # 错误的列名
            "2022-04-01": pd.DataFrame({"Ticker": ["GOOGL", "TSLA"]}),  # 正确的列名
        }
        
        excel_path = self.create_test_excel(tmp_path, sheets_data)
        portfolios = load_portfolios(excel_path)
        
        # 只有包含Ticker列的工作表应该被包含
        assert len(portfolios) == 1
        assert datetime.date(2022, 4, 1) in portfolios
        assert datetime.date(2022, 1, 1) not in portfolios
    
    def test_ticker_cleaning_and_nan_filtering(self, tmp_path):
        """测试Ticker清洗和NaN过滤"""
        sheets_data = {
            "2022-01-01": pd.DataFrame({
                "Ticker": ["  aapl_DELISTED  ", "MSFT", "", "googl", None, "   "]
            })
        }
        
        excel_path = self.create_test_excel(tmp_path, sheets_data)
        portfolios = load_portfolios(excel_path)
        
        assert len(portfolios) == 1
        df = portfolios[datetime.date(2022, 1, 1)]
        
        # 应该只保留有效的ticker，并且已经清洗
        expected_tickers = ["AAPL", "MSFT", "GOOGL"]
        actual_tickers = df["Ticker"].tolist()
        assert actual_tickers == expected_tickers
    
    def test_sheet_name_to_date_parsing(self, tmp_path):
        """测试工作表名称到日期的解析"""
        sheets_data = {
            "2022-01-01": pd.DataFrame({"Ticker": ["AAPL"]}),
            "2022-04-01": pd.DataFrame({"Ticker": ["MSFT"]}),
            "2022-07-01": pd.DataFrame({"Ticker": ["GOOGL"]}),
            "2022-10-01": pd.DataFrame({"Ticker": ["TSLA"]})
        }
        
        excel_path = self.create_test_excel(tmp_path, sheets_data)
        portfolios = load_portfolios(excel_path)
        
        expected_dates = [
            datetime.date(2022, 1, 1),
            datetime.date(2022, 4, 1),
            datetime.date(2022, 7, 1),
            datetime.date(2022, 10, 1)
        ]
        
        assert len(portfolios) == 4
        for date in expected_dates:
            assert date in portfolios
    
    def test_ai_selection_column_compatibility(self, tmp_path):
        """测试AI选股版本的列名兼容性"""
        sheets_data = {
            "2022-01-01": pd.DataFrame({
                "ticker": ["AAPL", "MSFT"],  # 小写ticker列
                "score": [0.85, 0.92]
            })
        }
        
        excel_path = self.create_test_excel(tmp_path, sheets_data)
        
        # 测试AI选股模式
        portfolios = load_portfolios(excel_path, is_ai_selection=True)
        
        assert len(portfolios) == 1
        df = portfolios[datetime.date(2022, 1, 1)]
        
        # 应该自动将ticker重命名为Ticker
        assert "Ticker" in df.columns
        assert "ticker" not in df.columns
        assert df["Ticker"].tolist() == ["AAPL", "MSFT"]
    
    def test_ai_selection_existing_ticker_column(self, tmp_path):
        """测试AI选股版本中已存在Ticker列的情况"""
        sheets_data = {
            "2022-01-01": pd.DataFrame({
                "Ticker": ["AAPL", "MSFT"],  # 已经是大写Ticker
                "score": [0.85, 0.92]
            })
        }
        
        excel_path = self.create_test_excel(tmp_path, sheets_data)
        portfolios = load_portfolios(excel_path, is_ai_selection=True)
        
        assert len(portfolios) == 1
        df = portfolios[datetime.date(2022, 1, 1)]
        
        # 应该保持原有的Ticker列
        assert "Ticker" in df.columns
        assert df["Ticker"].tolist() == ["AAPL", "MSFT"]
    
    def test_non_ai_selection_mode(self, tmp_path):
        """测试非AI选股模式不处理列名兼容性"""
        sheets_data = {
            "2022-01-01": pd.DataFrame({
                "ticker": ["AAPL", "MSFT"],  # 小写ticker列
                "weight": [0.5, 0.5]
            })
        }
        
        excel_path = self.create_test_excel(tmp_path, sheets_data)
        
        # 测试非AI选股模式（默认）
        portfolios = load_portfolios(excel_path, is_ai_selection=False)
        
        # 由于没有Ticker列，应该跳过这个工作表
        assert len(portfolios) == 0
    
    def test_mixed_valid_invalid_sheets(self, tmp_path):
        """测试混合有效和无效工作表的情况"""
        sheets_data = {
            "2022-01-01": pd.DataFrame({"Ticker": ["AAPL", "MSFT"]}),  # 有效
            "2022-04-01": pd.DataFrame(),  # 空工作表
            "2022-07-01": pd.DataFrame({"Symbol": ["GOOGL"]}),  # 错误列名
            "2022-10-01": pd.DataFrame({"Ticker": ["", "   ", None]}),  # 全是无效ticker
            "2022-12-01": pd.DataFrame({"Ticker": ["TSLA", "NVDA"]})  # 有效
        }
        
        excel_path = self.create_test_excel(tmp_path, sheets_data)
        portfolios = load_portfolios(excel_path)
        
        # 只有真正有效的工作表应该被包含
        assert len(portfolios) == 2
        assert datetime.date(2022, 1, 1) in portfolios
        assert datetime.date(2022, 12, 1) in portfolios
        
        # 验证数据内容
        assert portfolios[datetime.date(2022, 1, 1)]["Ticker"].tolist() == ["AAPL", "MSFT"]
        assert portfolios[datetime.date(2022, 12, 1)]["Ticker"].tolist() == ["TSLA", "NVDA"]
    
    def test_preserve_additional_columns(self, tmp_path):
        """测试保留额外列的功能"""
        sheets_data = {
            "2022-01-01": pd.DataFrame({
                "Ticker": ["AAPL", "MSFT"],
                "Weight": [0.6, 0.4],
                "Sector": ["Technology", "Technology"],
                "Score": [0.85, 0.92]
            })
        }
        
        excel_path = self.create_test_excel(tmp_path, sheets_data)
        portfolios = load_portfolios(excel_path)
        
        assert len(portfolios) == 1
        df = portfolios[datetime.date(2022, 1, 1)]
        
        # 应该保留所有列
        expected_columns = ["Ticker", "Weight", "Sector", "Score"]
        assert list(df.columns) == expected_columns
        
        # 验证数据完整性
        assert df["Weight"].tolist() == [0.6, 0.4]
        assert df["Sector"].tolist() == ["Technology", "Technology"]
        assert df["Score"].tolist() == [0.85, 0.92]


class TestLoadPortfoliosIntegration:
    """集成测试：模拟真实使用场景"""
    
    def test_quarterly_rebalancing_scenario(self, tmp_path):
        """测试季度调仓场景"""
        # 模拟一年四个季度的投资组合
        sheets_data = {
            "2022-01-03": pd.DataFrame({
                "Ticker": ["AAPL", "MSFT", "GOOGL"],
                "Weight": [0.4, 0.3, 0.3]
            }),
            "2022-04-01": pd.DataFrame({
                "Ticker": ["AAPL", "TSLA", "NVDA"],  # 调仓：MSFT,GOOGL -> TSLA,NVDA
                "Weight": [0.5, 0.25, 0.25]
            }),
            "2022-07-01": pd.DataFrame({
                "Ticker": ["MSFT", "GOOGL", "AMZN"],  # 完全换仓
                "Weight": [0.33, 0.33, 0.34]
            }),
            "2022-10-03": pd.DataFrame({
                "Ticker": ["SPY"],  # 转为指数投资
                "Weight": [1.0]
            })
        }
        
        excel_path = tmp_path / "quarterly_portfolios.xlsx"
        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            for sheet_name, df in sheets_data.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        portfolios = load_portfolios(excel_path)
        
        # 验证所有季度都被正确加载
        assert len(portfolios) == 4
        
        expected_dates = [
            datetime.date(2022, 1, 3),
            datetime.date(2022, 4, 1),
            datetime.date(2022, 7, 1),
            datetime.date(2022, 10, 3)
        ]
        
        for date in expected_dates:
            assert date in portfolios
        
        # 验证每个季度的股票数量
        assert len(portfolios[datetime.date(2022, 1, 3)]) == 3
        assert len(portfolios[datetime.date(2022, 4, 1)]) == 3
        assert len(portfolios[datetime.date(2022, 7, 1)]) == 3
        assert len(portfolios[datetime.date(2022, 10, 3)]) == 1
        
        # 验证最后一个季度的数据
        final_portfolio = portfolios[datetime.date(2022, 10, 3)]
        assert final_portfolio["Ticker"].iloc[0] == "SPY"
        assert final_portfolio["Weight"].iloc[0] == 1.0