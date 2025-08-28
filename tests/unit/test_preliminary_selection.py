"""preliminary_selection.py 的单元测试

测试因子筛选的核心功能：
- 滚动窗口计算的一致性
- 缺失值处理的稳定性
- 打分排序的可重复性
- tie-break规则的稳定性
"""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest
from dateutil.relativedelta import relativedelta

from stock_analysis.preliminary_selection import (
    calc_factor_scores,
    calculate_factors_point_in_time,
)


@pytest.mark.unit
class TestFactorCalculation:
    """测试因子计算的核心逻辑"""

    def test_calculate_factors_with_nan_handling(self):
        """测试NaN处理的稳定性"""
        # 构造包含NaN的测试数据
        df = pd.DataFrame(
            {
                "Ticker": ["AAPL", "AAPL", "MSFT", "MSFT", "GOOGL", "GOOGL"],
                "date_known": pd.to_datetime(
                    [
                        "2023-01-01",
                        "2023-04-01",
                        "2023-01-01",
                        "2023-04-01",
                        "2023-01-01",
                        "2023-04-01",
                    ]
                ),
                "year": [2022, 2023, 2022, 2023, 2022, 2023],
                "cfo": [100, 120, np.nan, 150, 80, 90],  # MSFT第一期缺失
                "ceq": [500, 550, 300, np.nan, 400, 420],  # MSFT第二期缺失
                "txt": [10, 12, 8, 15, 6, 7],
                "at": [1000, 1100, 800, 900, 700, 750],
                "rect": [50, 55, 40, 45, 35, 38],
            }
        )

        result = calculate_factors_point_in_time(df)

        # 验证NaN行被正确过滤，由于需要计算delta，实际结果会更少
        assert len(result) >= 2  # 至少有2行完整数据
        assert "AAPL" in result["Ticker"].values

        # 验证因子分数被正确计算
        assert "factor_score" in result.columns
        assert not result["factor_score"].isna().any()

    def test_factor_weights_consistency(self):
        """测试因子权重变更的可重复性"""
        # 构造标准测试数据
        df = pd.DataFrame(
            {
                "Ticker": ["A", "A", "B", "B"],
                "date_known": pd.to_datetime(["2023-01-01", "2023-04-01"] * 2),
                "year": [2022, 2023, 2022, 2023],
                "cfo": [100, 120, 80, 90],
                "ceq": [500, 550, 400, 420],
                "txt": [10, 12, 6, 7],
                "at": [1000, 1100, 700, 750],
                "rect": [50, 55, 35, 38],
            }
        )

        # 多次计算应该得到相同结果
        result1 = calculate_factors_point_in_time(df.copy())
        result2 = calculate_factors_point_in_time(df.copy())

        pd.testing.assert_frame_equal(result1, result2)

    def test_tie_break_stability(self):
        """测试相同分数的tie-break规则稳定性"""
        # 构造两个股票有相同因子分数的情况
        df = pd.DataFrame(
            {
                "Ticker": ["AAPL", "AAPL", "MSFT", "MSFT"],
                "date_known": pd.to_datetime(["2023-01-01", "2023-04-01"] * 2),
                "year": [2022, 2023, 2022, 2023],
                "cfo": [100, 120, 100, 120],  # 相同值
                "ceq": [500, 550, 500, 550],  # 相同值
                "txt": [10, 12, 10, 12],  # 相同值
                "at": [1000, 1100, 1000, 1100],  # 相同值
                "rect": [50, 55, 50, 55],  # 相同值
            }
        )

        result = calculate_factors_point_in_time(df)

        # 验证相同输入产生相同输出
        aapl_score = result[result["Ticker"] == "AAPL"]["factor_score"].iloc[0]
        msft_score = result[result["Ticker"] == "MSFT"]["factor_score"].iloc[0]

        # 由于输入完全相同，分数应该相等（如果都不是NaN）
        if not (pd.isna(aapl_score) or pd.isna(msft_score)):
            assert abs(aapl_score - msft_score) < 1e-10


@pytest.mark.unit
class TestRollingWindowLogic:
    """测试滚动窗口逻辑"""

    def test_rolling_window_consistency(self):
        """测试滚动窗口计算的一致性"""
        # 构造5年的测试数据
        base_date = datetime(2020, 1, 1)
        dates = [
            base_date + relativedelta(months=3 * i) for i in range(20)
        ]  # 5年季度数据

        df = pd.DataFrame(
            {
                "Ticker": ["AAPL"] * 20,
                "date_known": dates,
                "year": [d.year for d in dates],
                "cfo": np.random.randint(80, 120, 20),
                "ceq": np.random.randint(400, 600, 20),
                "txt": np.random.randint(5, 15, 20),
                "at": np.random.randint(800, 1200, 20),
                "rect": np.random.randint(30, 60, 20),
            }
        )

        # 添加delta计算需要的数据
        df_with_factors = calculate_factors_point_in_time(df)

        # 测试不同as_of_date的窗口计算
        as_of_date1 = pd.Timestamp("2023-01-01")
        as_of_date2 = pd.Timestamp("2023-01-01")  # 相同日期

        result1 = calc_factor_scores(df_with_factors, as_of_date1, 5, 5)
        result2 = calc_factor_scores(df_with_factors, as_of_date2, 5, 5)

        # 相同输入应该产生相同输出
        if not result1.empty and not result2.empty:
            pd.testing.assert_frame_equal(result1, result2)

    def test_min_reports_threshold(self):
        """测试最小报告数量阈值"""
        # 构造数据，其中一个股票报告数不足
        df = pd.DataFrame(
            {
                "Ticker": ["AAPL"] * 3 + ["MSFT"] * 8,  # AAPL只有3个报告，MSFT有8个
                "date_known": pd.to_datetime(
                    [
                        "2022-01-01",
                        "2022-04-01",
                        "2022-07-01",  # AAPL
                        "2021-01-01",
                        "2021-04-01",
                        "2021-07-01",
                        "2021-10-01",
                        "2022-01-01",
                        "2022-04-01",
                        "2022-07-01",
                        "2022-10-01",  # MSFT
                    ]
                ),
                "year": [2022] * 3 + [2021] * 4 + [2022] * 4,
                "factor_score": [1.0] * 11,
            }
        )

        as_of_date = pd.Timestamp("2023-01-01")
        result = calc_factor_scores(df, as_of_date, 5, 5)  # 要求至少5个报告

        # 只有MSFT应该通过筛选
        assert len(result) == 1
        assert result.index[0] == "MSFT"


@pytest.mark.unit
class TestTopNSelection:
    """测试TopN选择的稳定性"""

    def test_top_n_reproducibility(self):
        """测试TopN选择的可重复性"""
        # 构造有明确排序的数据
        df = pd.DataFrame(
            {
                "avg_factor_score": [3.0, 1.0, 2.0, 4.0, 0.5],
                "num_reports": [10, 8, 9, 12, 7],
            },
            index=["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"],
        )

        # 多次排序应该得到相同结果
        sorted1 = df.sort_values(by="avg_factor_score", ascending=False)
        sorted2 = df.sort_values(by="avg_factor_score", ascending=False)

        pd.testing.assert_frame_equal(sorted1, sorted2)

        # 验证排序顺序
        expected_order = ["AMZN", "AAPL", "GOOGL", "MSFT", "TSLA"]
        assert sorted1.index.tolist() == expected_order

    def test_tie_break_by_ticker(self):
        """测试相同分数时按ticker排序的tie-break"""
        # 构造有相同分数的数据
        df = pd.DataFrame(
            {
                "avg_factor_score": [2.0, 2.0, 1.0],  # AAPL和MSFT分数相同
                "num_reports": [10, 10, 8],
            },
            index=["MSFT", "AAPL", "GOOGL"],
        )  # 故意打乱顺序

        # 按分数降序，然后按ticker升序排序（稳定的tie-break）
        sorted_df = df.sort_values(
            by=["avg_factor_score", df.index], ascending=[False, True]
        )

        # 验证tie-break结果：相同分数时AAPL应该在MSFT前面（字母序）
        expected_order = ["AAPL", "MSFT", "GOOGL"]
        assert sorted_df.index.tolist() == expected_order


@pytest.mark.unit
class TestEdgeCases:
    """测试边界情况"""

    def test_empty_dataframe(self):
        """测试空DataFrame的处理"""
        empty_df = pd.DataFrame()
        result = calculate_factors_point_in_time(empty_df)
        assert result.empty

    def test_all_nan_factors(self):
        """测试所有因子都是NaN的情况"""
        df = pd.DataFrame(
            {
                "Ticker": ["AAPL", "MSFT"],
                "date_known": pd.to_datetime(["2023-01-01", "2023-01-01"]),
                "year": [2023, 2023],
                "cfo": [np.nan, np.nan],
                "ceq": [np.nan, np.nan],
                "txt": [np.nan, np.nan],
                "at": [np.nan, np.nan],
                "rect": [np.nan, np.nan],
            }
        )

        result = calculate_factors_point_in_time(df)
        assert result.empty

    def test_single_stock_multiple_periods(self):
        """测试单个股票多个时期的处理"""
        df = pd.DataFrame(
            {
                "Ticker": ["AAPL"] * 4,
                "date_known": pd.to_datetime(
                    ["2022-01-01", "2022-04-01", "2022-07-01", "2022-10-01"]
                ),
                "year": [2021, 2022, 2022, 2022],
                "cfo": [100, 110, 120, 130],
                "ceq": [500, 520, 540, 560],
                "txt": [10, 11, 12, 13],
                "at": [1000, 1020, 1040, 1060],
                "rect": [50, 52, 54, 56],
            }
        )

        result = calculate_factors_point_in_time(df)

        # 应该有3行结果（第一行没有delta，被过滤掉）
        assert len(result) == 3
        assert all(result["Ticker"] == "AAPL")
        assert not result["factor_score"].isna().any()
