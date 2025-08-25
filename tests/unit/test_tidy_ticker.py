"""tidy_ticker 函数的单元测试

测试数据清洗函数的核心功能：
- 大小写标准化
- 空白字符处理
- 后缀去除（_DELISTED等）
- 空值处理
- 幂等性验证
"""

import pandas as pd
import pytest

from stock_analysis.load_data_to_db import tidy_ticker


@pytest.mark.unit
@pytest.mark.parametrize("raw,expect", [
    # 用户提供的基础测试用例
    ([" aapl ", "MSFT_DELISTED", "", None], ["AAPL", "MSFT", pd.NA, pd.NA]),
    (["\tspy\n", "googl_delisted", "Se  "], ["SPY", "GOOGL", "SE"]),
    
    # 扩展测试用例
    # 测试各种空白字符
    (["  AMZN  ", "\t\nTSLA\r\n", "   "], ["AMZN", "TSLA", pd.NA]),
    
    # 测试大小写混合
    (["AaPl", "mSfT", "GoOgL"], ["AAPL", "MSFT", "GOOGL"]),
    
    # 测试各种DELISTED后缀
    (["AAPL_DELISTED", "msft_delisted", "GOOGL_Delisted"], ["AAPL", "MSFT", "GOOGL"]),
    
    # 测试混合情况
    ([" aapl_delisted ", "\tMSFT_DELISTED\n", "  googl  "], ["AAPL", "MSFT", "GOOGL"]),
    
    # 测试边界情况
    (["A", "AB", "ABC"], ["A", "AB", "ABC"]),  # 短股票代码
    (["BERKSHIRE.A", "BRK.B"], ["BERKSHIRE.A", "BRK.B"]),  # 包含点号
    
    # 测试空值的各种形式
    (["", "   ", "\t\n", None], [pd.NA, pd.NA, pd.NA, pd.NA]),
])
def test_tidy_ticker_basic(raw, expect):
    """测试tidy_ticker的基本功能"""
    out = tidy_ticker(pd.Series(raw)).tolist()
    
    # 处理pd.NA的比较
    for i, (actual, expected) in enumerate(zip(out, expect, strict=False)):
        if pd.isna(expected):
            assert pd.isna(actual), f"Index {i}: expected NA, got {actual}"
        else:
            assert actual == expected, f"Index {i}: expected {expected}, got {actual}"


@pytest.mark.unit
def test_tidy_ticker_idempotent():
    """测试tidy_ticker的幂等性：tidy(tidy(x)) == tidy(x)"""
    # 用户提供的测试用例
    s = pd.Series([" amzn_deListed ", "  "])
    once = tidy_ticker(s)
    twice = tidy_ticker(once)
    pd.testing.assert_series_equal(once, twice, check_names=False)
    
    # 扩展的幂等性测试
    test_cases = [
        [" AAPL ", "MSFT_delisted", "", "GOOGL", None],
        ["\tTSLA\n", "amzn_DELISTED", "   ", "NVDA"],
        ["already_clean", "ALSO_CLEAN", "clean_delisted"],
        # 已经清洗过的数据
        ["AAPL", "MSFT", "GOOGL"],
    ]
    
    for case in test_cases:
        original = pd.Series(case)
        first_clean = tidy_ticker(original)
        second_clean = tidy_ticker(first_clean)
        
        pd.testing.assert_series_equal(
            first_clean, second_clean, 
            check_names=False
        ), f"Idempotency failed for case: {case}"


@pytest.mark.unit
class TestTidyTickerProperties:
    """测试tidy_ticker的性质"""
    
    def test_only_affects_whitespace_case_suffix(self):
        """测试函数只影响空白、大小写和后缀，不改变其他字符"""
        # 包含特殊字符但不应被改变的股票代码
        test_cases = [
            "BRK.A",      # 点号应保留
            "BRK-B",      # 连字符应保留  
            "SOME123",    # 数字应保留
            "ABC&DEF",    # 特殊符号应保留（除了处理的后缀）
        ]
        
        for case in test_cases:
            # 添加需要清理的元素
            dirty = f"  {case.lower()}_delisted  "
            cleaned = tidy_ticker(pd.Series([dirty]))[0]
            
            # 应该得到大写的原始字符（去掉后缀）
            expected = case.upper()
            assert cleaned == expected, f"Expected {expected}, got {cleaned}"
    
    def test_preserves_series_length(self):
        """测试函数保持Series长度不变"""
        test_series = pd.Series([
            "AAPL", " MSFT ", "googl_delisted", "", None, "\t\n"
        ])
        
        result = tidy_ticker(test_series)
        assert len(result) == len(test_series)
    
    def test_handles_empty_series(self):
        """测试处理空Series"""
        empty_series = pd.Series([], dtype='object')
        result = tidy_ticker(empty_series)
        
        assert len(result) == 0
        assert result.dtype == 'string'
    
    def test_consistent_output_type(self):
        """测试输出类型的一致性"""
        test_cases = [
            ["AAPL", "MSFT"],
            [" aapl ", "msft_delisted"],
            ["", None],
            ["mixed", " CASE ", "test_delisted", ""]
        ]
        
        for case in test_cases:
            result = tidy_ticker(pd.Series(case))
            assert result.dtype == 'string', f"Wrong dtype for case {case}"
    
    def test_delisted_suffix_variations(self):
        """测试各种DELISTED后缀的处理"""
        variations = [
            "AAPL_DELISTED",
            "aapl_delisted", 
            "Aapl_Delisted",
            "AAPL_delisted",
            "aapl_DELISTED"
        ]
        
        results = tidy_ticker(pd.Series(variations))
        
        # 所有变体都应该清理为"AAPL"
        for result in results:
            assert result == "AAPL", f"Failed to clean delisted suffix: {result}"
    
    def test_no_false_positive_delisted_removal(self):
        """测试不会错误地移除非后缀的DELISTED字符串"""
        # 这些不应该被当作后缀处理
        false_positives = [
            "DELISTED_CORP",     # 前缀，不是后缀
            "SOME_DELISTED_CO",  # 中间，不是后缀
            "DELISTED",          # 整个名称，不是后缀
        ]
        
        results = tidy_ticker(pd.Series(false_positives))
        expected = ["DELISTED_CORP", "SOME_DELISTED_CO", "DELISTED"]
        
        for result, expect in zip(results, expected, strict=False):
            assert result == expect, f"Incorrectly removed DELISTED from {result}"


@pytest.mark.unit
class TestTidyTickerEdgeCases:
    """测试边界情况和异常情况"""
    
    def test_very_long_ticker(self):
        """测试很长的股票代码"""
        long_ticker = "A" * 50 + "_DELISTED"
        result = tidy_ticker(pd.Series([long_ticker]))[0]
        assert result == "A" * 50
    
    def test_unicode_characters(self):
        """测试Unicode字符的处理"""
        unicode_tickers = ["AAPL™", "MSFT®", "GOOGL©"]
        results = tidy_ticker(pd.Series(unicode_tickers))
        
        # Unicode字符应该被保留并转为大写
        expected = ["AAPL™", "MSFT®", "GOOGL©"]
        for result, expect in zip(results, expected, strict=False):
            assert result == expect
    
    def test_multiple_underscores(self):
        """测试多个下划线的情况"""
        test_cases = [
            "AAPL__DELISTED",     # 双下划线
            "AAPL_TEST_DELISTED", # 中间有下划线
            "AAPL_DELISTED_",     # 后面还有下划线
        ]
        
        results = tidy_ticker(pd.Series(test_cases))
        
        # 只有结尾的_DELISTED应该被移除
        expected = ["AAPL_", "AAPL_TEST", "AAPL_DELISTED_"]
        for result, expect in zip(results, expected, strict=False):
            assert result == expect, f"Expected {expect}, got {result}"
    
    def test_mixed_data_types_in_series(self):
        """测试Series中混合数据类型的处理"""
        # 虽然实际使用中应该都是字符串，但测试健壮性
        mixed_series = pd.Series(["AAPL", None, "", 123, "MSFT_delisted"])
        
        # 函数应该能处理而不崩溃
        result = tidy_ticker(mixed_series)
        assert len(result) == 5
        
        # 检查字符串元素被正确处理
        assert result.iloc[0] == "AAPL"
        assert pd.isna(result.iloc[1])
        assert pd.isna(result.iloc[2])
        # 数字会被转换为字符串
        assert result.iloc[3] == "123"
        assert result.iloc[4] == "MSFT"