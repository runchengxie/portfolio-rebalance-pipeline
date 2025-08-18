"""测试回测引擎核心行为模块

测试 backtest.engine 中的回测引擎核心功能，包括：
- 再平衡日对齐：仅在每个rebalance日调仓，持有到下季起点
- 现金初始化与累计价值曲线输出不为空
- 支持可选基准绘制的参数传递
- 无数据/部分股票无数据时的降级与日志告警
"""

import datetime
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest
import backtrader as bt

from stock_analysis.backtest.engine import (
    PointInTimeStrategy,
    BuyAndHoldStrategy,
    run_quarterly_backtest,
    run_benchmark_backtest,
    generate_report
)


class TestPointInTimeStrategy:
    """测试时点策略类"""
    
    def create_mock_data_feed(self, ticker: str, dates: list, prices: list) -> bt.feeds.PandasData:
        """创建模拟数据源
        
        Args:
            ticker: 股票代码
            dates: 日期列表
            prices: 价格列表
            
        Returns:
            bt.feeds.PandasData: Backtrader数据源
        """
        data = pd.DataFrame({
            'Open': prices,
            'High': [p * 1.02 for p in prices],
            'Low': [p * 0.98 for p in prices],
            'Close': prices,
            'Volume': [1000000] * len(prices),
            'Dividend': [0.0] * len(prices)
        }, index=pd.to_datetime(dates))
        
        return bt.feeds.PandasData(dataname=data, name=ticker)
    
    def test_rebalance_date_alignment(self):
        """测试再平衡日期对齐逻辑"""
        # 创建测试投资组合
        portfolios = {
            datetime.date(2022, 1, 3): pd.DataFrame({"Ticker": ["AAPL", "MSFT"]}),
            datetime.date(2022, 4, 1): pd.DataFrame({"Ticker": ["GOOGL", "TSLA"]}),
            datetime.date(2022, 7, 1): pd.DataFrame({"Ticker": ["AMZN", "META"]})
        }
        
        # 创建策略实例
        strategy = PointInTimeStrategy()
        strategy.p.portfolios = portfolios
        strategy.p.use_logging = False
        
        # 初始化策略
        strategy.__init__()
        
        # 验证再平衡日期排序
        expected_dates = [datetime.date(2022, 1, 3), datetime.date(2022, 4, 1), datetime.date(2022, 7, 1)]
        assert strategy.rebalance_dates == expected_dates
        
        # 验证初始状态
        assert strategy.next_rebalance_idx == 0
        assert strategy.next_rebalance_date == datetime.date(2022, 1, 3)
    
    def test_get_next_rebalance_date(self):
        """测试获取下一个再平衡日期的逻辑"""
        portfolios = {
            datetime.date(2022, 1, 3): pd.DataFrame({"Ticker": ["AAPL"]}),
            datetime.date(2022, 4, 1): pd.DataFrame({"Ticker": ["MSFT"]})
        }
        
        strategy = PointInTimeStrategy()
        strategy.p.portfolios = portfolios
        strategy.__init__()
        
        # 初始状态
        assert strategy.next_rebalance_date == datetime.date(2022, 1, 3)
        
        # 移动到下一个日期
        strategy.next_rebalance_idx = 1
        strategy.get_next_rebalance_date()
        assert strategy.next_rebalance_date == datetime.date(2022, 4, 1)
        
        # 超出范围
        strategy.next_rebalance_idx = 2
        strategy.get_next_rebalance_date()
        assert strategy.next_rebalance_date is None
    
    def test_missing_tickers_handling(self):
        """测试缺失股票代码的处理逻辑"""
        portfolios = {
            datetime.date(2022, 1, 3): pd.DataFrame({"Ticker": ["AAPL", "MISSING_TICKER"]})
        }
        
        # 创建模拟策略环境
        strategy = PointInTimeStrategy()
        strategy.p.portfolios = portfolios
        strategy.p.use_logging = False
        strategy.__init__()
        
        # 模拟数据源（只有AAPL）
        mock_data_aapl = MagicMock()
        mock_data_aapl._name = "AAPL"
        
        strategy.datas = [mock_data_aapl]
        strategy.timeline = mock_data_aapl
        strategy.timeline.datetime.date.return_value = datetime.date(2022, 1, 3)
        
        # 模拟getdatabyname方法
        def mock_getdatabyname(name):
            if name == "AAPL":
                return mock_data_aapl
            return None
        
        strategy.getdatabyname = mock_getdatabyname
        strategy.getposition = MagicMock(return_value=MagicMock(size=0))
        strategy.order_target_percent = MagicMock()
        
        # 执行策略逻辑
        strategy.next()
        
        # 验证日志记录了缺失的股票
        assert len(strategy.rebalance_log) == 1
        log_entry = strategy.rebalance_log[0]
        assert log_entry["model_tickers"] == 2
        assert log_entry["available_tickers"] == 1
        assert "MISSING_TICKER" in log_entry["missing_tickers_list"]
    
    def test_all_cash_period_handling(self):
        """测试全现金期间的处理（所有股票都缺失数据）"""
        portfolios = {
            datetime.date(2022, 1, 3): pd.DataFrame({"Ticker": ["MISSING1", "MISSING2"]})
        }
        
        strategy = PointInTimeStrategy()
        strategy.p.portfolios = portfolios
        strategy.p.use_logging = False
        strategy.__init__()
        
        # 模拟没有匹配的数据源
        mock_timeline = MagicMock()
        mock_timeline.datetime.date.return_value = datetime.date(2022, 1, 3)
        mock_timeline._name = "TIMELINE"
        
        strategy.datas = [mock_timeline]
        strategy.timeline = mock_timeline
        strategy.getdatabyname = MagicMock(return_value=None)
        
        # 执行策略逻辑
        strategy.next()
        
        # 验证进入全现金期间
        assert len(strategy.rebalance_log) == 1
        log_entry = strategy.rebalance_log[0]
        assert log_entry["available_tickers"] == 0
        assert log_entry["model_tickers"] == 2
        
        # 验证移动到下一个再平衡日期
        assert strategy.next_rebalance_idx == 1
        assert strategy.next_rebalance_date is None


class TestBuyAndHoldStrategy:
    """测试买入并持有策略"""
    
    def test_single_purchase_logic(self):
        """测试单次购买逻辑"""
        strategy = BuyAndHoldStrategy()
        strategy.__init__()
        
        # 模拟order_target_percent方法
        strategy.order_target_percent = MagicMock()
        
        # 初始状态
        assert not strategy.bought
        
        # 第一次调用next()
        strategy.next()
        assert strategy.bought
        strategy.order_target_percent.assert_called_once_with(target=0.99)
        
        # 第二次调用next()应该不再购买
        strategy.order_target_percent.reset_mock()
        strategy.next()
        strategy.order_target_percent.assert_not_called()


class TestRunQuarterlyBacktest:
    """测试季度回测运行函数"""
    
    def create_test_data_feeds(self) -> dict:
        """创建测试数据源"""
        dates = pd.date_range('2022-01-01', '2022-12-31', freq='D')
        
        data_feeds = {}
        for ticker in ['AAPL', 'MSFT', 'GOOGL']:
            # 创建模拟价格数据（随时间上涨）
            base_price = {'AAPL': 150, 'MSFT': 300, 'GOOGL': 2500}[ticker]
            prices = [base_price * (1 + 0.001 * i) for i in range(len(dates))]
            
            data = pd.DataFrame({
                'Open': prices,
                'High': [p * 1.01 for p in prices],
                'Low': [p * 0.99 for p in prices],
                'Close': prices,
                'Volume': [1000000] * len(dates),
                'Dividend': [0.0] * len(dates)
            }, index=dates)
            
            data_feeds[ticker] = bt.feeds.PandasData(dataname=data, name=ticker)
        
        return data_feeds
    
    def test_successful_backtest_execution(self):
        """测试成功的回测执行"""
        # 创建测试投资组合
        portfolios = {
            datetime.date(2022, 1, 3): pd.DataFrame({"Ticker": ["AAPL", "MSFT"]}),
            datetime.date(2022, 7, 1): pd.DataFrame({"Ticker": ["GOOGL", "MSFT"]})
        }
        
        data_feeds = self.create_test_data_feeds()
        initial_cash = 100000.0
        start_date = datetime.date(2022, 1, 1)
        end_date = datetime.date(2022, 12, 31)
        
        # 运行回测
        portfolio_value, metrics = run_quarterly_backtest(
            portfolios=portfolios,
            data_feeds=data_feeds,
            initial_cash=initial_cash,
            start_date=start_date,
            end_date=end_date,
            use_logging=False
        )
        
        # 验证返回值
        assert isinstance(portfolio_value, pd.Series)
        assert isinstance(metrics, dict)
        
        # 验证投资组合价值序列不为空
        assert len(portfolio_value) > 0
        assert portfolio_value.iloc[0] == initial_cash  # 初始值
        
        # 验证指标字典包含必要字段
        required_fields = [
            'start_date', 'end_date', 'initial_value', 'final_value',
            'total_return', 'annualized_return', 'max_drawdown'
        ]
        for field in required_fields:
            assert field in metrics
        
        # 验证指标值的合理性
        assert metrics['initial_value'] == initial_cash
        assert metrics['final_value'] > 0
        assert metrics['start_date'] == start_date
        assert metrics['end_date'] == end_date
    
    def test_cash_initialization(self):
        """测试现金初始化"""
        portfolios = {
            datetime.date(2022, 1, 3): pd.DataFrame({"Ticker": ["AAPL"]})
        }
        
        data_feeds = self.create_test_data_feeds()
        initial_cash = 50000.0
        
        portfolio_value, metrics = run_quarterly_backtest(
            portfolios=portfolios,
            data_feeds=data_feeds,
            initial_cash=initial_cash,
            start_date=datetime.date(2022, 1, 1),
            end_date=datetime.date(2022, 6, 30),
            use_logging=False
        )
        
        # 验证初始现金设置正确
        assert metrics['initial_value'] == initial_cash
        assert portfolio_value.iloc[0] == initial_cash
    
    def test_empty_portfolio_handling(self):
        """测试空投资组合的处理"""
        # 空投资组合字典
        portfolios = {}
        data_feeds = self.create_test_data_feeds()
        
        portfolio_value, metrics = run_quarterly_backtest(
            portfolios=portfolios,
            data_feeds=data_feeds,
            initial_cash=100000.0,
            start_date=datetime.date(2022, 1, 1),
            end_date=datetime.date(2022, 12, 31),
            use_logging=False
        )
        
        # 应该仍然返回有效结果（全现金策略）
        assert isinstance(portfolio_value, pd.Series)
        assert isinstance(metrics, dict)
        assert len(portfolio_value) > 0
    
    def test_add_observers_parameter(self):
        """测试添加观察器参数"""
        portfolios = {
            datetime.date(2022, 1, 3): pd.DataFrame({"Ticker": ["AAPL"]})
        }
        
        data_feeds = self.create_test_data_feeds()
        
        # 测试添加观察器
        portfolio_value, metrics = run_quarterly_backtest(
            portfolios=portfolios,
            data_feeds=data_feeds,
            initial_cash=100000.0,
            start_date=datetime.date(2022, 1, 1),
            end_date=datetime.date(2022, 6, 30),
            use_logging=False,
            add_observers=True
        )
        
        # 应该正常执行
        assert isinstance(portfolio_value, pd.Series)
        assert isinstance(metrics, dict)
    
    def test_add_annual_return_parameter(self):
        """测试添加年化收益分析器参数"""
        portfolios = {
            datetime.date(2022, 1, 3): pd.DataFrame({"Ticker": ["AAPL"]})
        }
        
        data_feeds = self.create_test_data_feeds()
        
        # 测试添加年化收益分析器
        portfolio_value, metrics = run_quarterly_backtest(
            portfolios=portfolios,
            data_feeds=data_feeds,
            initial_cash=100000.0,
            start_date=datetime.date(2022, 1, 1),
            end_date=datetime.date(2022, 12, 31),
            use_logging=False,
            add_annual_return=True
        )
        
        # 应该包含年化收益数据
        assert 'annual_returns' in metrics
        assert isinstance(metrics['annual_returns'], dict)


class TestRunBenchmarkBacktest:
    """测试基准回测运行函数"""
    
    def create_spy_data(self) -> pd.DataFrame:
        """创建SPY测试数据"""
        dates = pd.date_range('2022-01-01', '2022-12-31', freq='D')
        base_price = 400.0
        prices = [base_price * (1 + 0.0005 * i) for i in range(len(dates))]
        
        return pd.DataFrame({
            'Open': prices,
            'High': [p * 1.005 for p in prices],
            'Low': [p * 0.995 for p in prices],
            'Close': prices,
            'Volume': [50000000] * len(dates),
            'Dividend': [0.0] * len(dates)
        }, index=dates)
    
    def test_benchmark_backtest_execution(self):
        """测试基准回测执行"""
        spy_data = self.create_spy_data()
        initial_cash = 100000.0
        
        portfolio_value, metrics = run_benchmark_backtest(
            data=spy_data,
            initial_cash=initial_cash,
            ticker="SPY"
        )
        
        # 验证返回值
        assert isinstance(portfolio_value, pd.Series)
        assert isinstance(metrics, dict)
        
        # 验证投资组合价值序列
        assert len(portfolio_value) > 0
        assert portfolio_value.iloc[0] == initial_cash
        
        # 验证指标
        required_fields = [
            'start_date', 'end_date', 'initial_value', 'final_value',
            'total_return', 'annualized_return', 'max_drawdown'
        ]
        for field in required_fields:
            assert field in metrics
        
        assert metrics['initial_value'] == initial_cash
        assert metrics['final_value'] > 0
    
    def test_custom_ticker(self):
        """测试自定义股票代码"""
        data = self.create_spy_data()
        
        portfolio_value, metrics = run_benchmark_backtest(
            data=data,
            initial_cash=50000.0,
            ticker="QQQ"
        )
        
        # 应该正常执行，ticker参数主要用于日志显示
        assert isinstance(portfolio_value, pd.Series)
        assert isinstance(metrics, dict)
        assert metrics['initial_value'] == 50000.0


class TestGenerateReport:
    """测试报告生成函数"""
    
    def create_test_metrics(self) -> dict:
        """创建测试指标数据"""
        return {
            'start_date': datetime.date(2022, 1, 1),
            'end_date': datetime.date(2022, 12, 31),
            'initial_value': 100000.0,
            'final_value': 120000.0,
            'total_return': 0.20,
            'annualized_return': 0.18,
            'max_drawdown': 5.5
        }
    
    def create_test_portfolio_value(self) -> pd.Series:
        """创建测试投资组合价值序列"""
        dates = pd.date_range('2022-01-01', '2022-12-31', freq='M')
        values = [100000 * (1 + 0.015 * i) for i in range(len(dates))]
        return pd.Series(values, index=dates)
    
    @patch('matplotlib.pyplot.show')
    @patch('matplotlib.pyplot.savefig')
    def test_basic_report_generation(self, mock_savefig, mock_show):
        """测试基本报告生成"""
        metrics = self.create_test_metrics()
        portfolio_value = self.create_test_portfolio_value()
        
        # 测试基本报告生成（不保存文件）
        generate_report(
            metrics=metrics,
            title="Test Strategy Backtest",
            portfolio_value=portfolio_value
        )
        
        # 验证图表显示被调用
        mock_show.assert_called_once()
        mock_savefig.assert_not_called()
    
    @patch('matplotlib.pyplot.show')
    @patch('matplotlib.pyplot.savefig')
    def test_report_with_file_output(self, mock_savefig, mock_show, tmp_path):
        """测试带文件输出的报告生成"""
        metrics = self.create_test_metrics()
        portfolio_value = self.create_test_portfolio_value()
        output_path = tmp_path / "test_report.png"
        
        generate_report(
            metrics=metrics,
            title="Test Strategy with File Output",
            portfolio_value=portfolio_value,
            output_png=output_path
        )
        
        # 验证文件保存被调用
        mock_savefig.assert_called_once_with(output_path, dpi=300, bbox_inches="tight")
        mock_show.assert_called_once()
    
    @patch('matplotlib.pyplot.show')
    @patch('matplotlib.pyplot.savefig')
    def test_report_with_benchmark(self, mock_savefig, mock_show):
        """测试带基准的报告生成"""
        metrics = self.create_test_metrics()
        portfolio_value = self.create_test_portfolio_value()
        
        # 创建基准数据
        benchmark_value = self.create_test_portfolio_value() * 0.9  # 稍低的基准表现
        
        generate_report(
            metrics=metrics,
            title="Test Strategy vs Benchmark",
            portfolio_value=portfolio_value,
            benchmark_value=benchmark_value,
            benchmark_label="SPY Benchmark"
        )
        
        # 验证图表显示被调用
        mock_show.assert_called_once()


class TestEngineIntegration:
    """回测引擎集成测试"""
    
    def test_end_to_end_backtest_flow(self):
        """端到端回测流程测试"""
        # 1. 准备测试数据
        portfolios = {
            datetime.date(2022, 1, 3): pd.DataFrame({"Ticker": ["AAPL", "MSFT"]}),
            datetime.date(2022, 7, 1): pd.DataFrame({"Ticker": ["GOOGL"]})
        }
        
        # 2. 创建数据源
        dates = pd.date_range('2022-01-01', '2022-12-31', freq='D')
        data_feeds = {}
        
        for ticker in ['AAPL', 'MSFT', 'GOOGL']:
            base_price = {'AAPL': 150, 'MSFT': 300, 'GOOGL': 2500}[ticker]
            prices = [base_price * (1 + 0.001 * i) for i in range(len(dates))]
            
            data = pd.DataFrame({
                'Open': prices,
                'High': [p * 1.01 for p in prices],
                'Low': [p * 0.99 for p in prices],
                'Close': prices,
                'Volume': [1000000] * len(dates),
                'Dividend': [0.0] * len(dates)
            }, index=dates)
            
            data_feeds[ticker] = bt.feeds.PandasData(dataname=data, name=ticker)
        
        # 3. 运行季度回测
        portfolio_value, metrics = run_quarterly_backtest(
            portfolios=portfolios,
            data_feeds=data_feeds,
            initial_cash=100000.0,
            start_date=datetime.date(2022, 1, 1),
            end_date=datetime.date(2022, 12, 31),
            use_logging=False
        )
        
        # 4. 运行基准回测
        spy_data = pd.DataFrame({
            'Open': [400] * len(dates),
            'High': [405] * len(dates),
            'Low': [395] * len(dates),
            'Close': [400 * (1 + 0.0005 * i) for i in range(len(dates))],
            'Volume': [50000000] * len(dates),
            'Dividend': [0.0] * len(dates)
        }, index=dates)
        
        benchmark_value, benchmark_metrics = run_benchmark_backtest(
            data=spy_data,
            initial_cash=100000.0,
            ticker="SPY"
        )
        
        # 5. 验证结果
        assert isinstance(portfolio_value, pd.Series)
        assert isinstance(benchmark_value, pd.Series)
        assert len(portfolio_value) > 0
        assert len(benchmark_value) > 0
        
        # 验证指标合理性
        assert metrics['final_value'] > 0
        assert benchmark_metrics['final_value'] > 0
        assert metrics['total_return'] != 0  # 应该有收益变化
        assert benchmark_metrics['total_return'] != 0
        
        # 6. 测试报告生成（不实际显示）
        with patch('matplotlib.pyplot.show'):
            generate_report(
                metrics=metrics,
                title="Integration Test Strategy",
                portfolio_value=portfolio_value,
                benchmark_value=benchmark_value,
                benchmark_label="SPY"
            )