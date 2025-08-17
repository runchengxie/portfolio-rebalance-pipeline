"""测试配置读取模块

测试 utils/config.py 中的配置读取逻辑，包括：
- period_mode=fixed/dynamic 的时间区间计算
- 日期字符串与 date 对象的处理
- buffer 月/日逻辑
- 统一资金 vs 分策略资金的两种配置格式
"""

import datetime
import tempfile
import yaml
from pathlib import Path
from unittest.mock import patch

import pytest
from dateutil.relativedelta import relativedelta

from stock_analysis.utils.config import load_cfg, get_backtest_period, get_initial_cash


class TestLoadCfg:
    """测试配置文件加载"""
    
    def test_load_cfg_with_config_dir_yaml(self, tmp_path):
        """测试优先读取 config/config.yaml"""
        # 创建临时配置文件
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        
        config_data = {
            "backtest": {
                "period_mode": "fixed",
                "start": "2021-01-01",
                "end": "2023-12-31",
                "initial_cash": 500000
            }
        }
        
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f)
        
        # Mock 项目根目录
        with patch("stock_analysis.utils.config.Path") as mock_path:
            mock_path(__file__).resolve.return_value.parents = [None, None, None, tmp_path]
            
            config = load_cfg()
            assert config["backtest"]["period_mode"] == "fixed"
            assert config["backtest"]["initial_cash"] == 500000
    
    def test_load_cfg_fallback_to_root_yaml(self, tmp_path):
        """测试回退到项目根的 config.yaml"""
        # 只在项目根创建配置文件
        config_file = tmp_path / "config.yaml"
        
        config_data = {
            "backtest": {
                "period_mode": "dynamic",
                "buffer": {"months": 6, "days": 15},
                "initial_cash": {"ai": 800000, "spy": 200000}
            }
        }
        
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f)
        
        with patch("stock_analysis.utils.config.Path") as mock_path:
            mock_path(__file__).resolve.return_value.parents = [None, None, None, tmp_path]
            
            config = load_cfg()
            assert config["backtest"]["period_mode"] == "dynamic"
            assert config["backtest"]["buffer"]["months"] == 6
    
    def test_load_cfg_no_config_file(self):
        """测试无配置文件时使用默认配置"""
        with patch("stock_analysis.utils.config.Path") as mock_path:
            # Mock 不存在的路径
            mock_path(__file__).resolve.return_value.parents = [None, None, None, Path("/nonexistent")]
            
            config = load_cfg()
            assert config["backtest"]["period_mode"] == "dynamic"
            assert config["backtest"]["buffer"]["months"] == 3
            assert config["backtest"]["buffer"]["days"] == 10
            assert config["backtest"]["initial_cash"] == 1000000
    
    def test_load_cfg_yaml_parse_error(self, tmp_path):
        """测试 YAML 解析错误时的降级处理"""
        config_file = tmp_path / "config.yaml"
        
        # 写入无效的 YAML
        with open(config_file, "w", encoding="utf-8") as f:
            f.write("invalid: yaml: content: [")
        
        with patch("stock_analysis.utils.config.Path") as mock_path:
            mock_path(__file__).resolve.return_value.parents = [None, None, None, tmp_path]
            
            config = load_cfg()
            # 应该返回默认配置
            assert config["backtest"]["period_mode"] == "dynamic"
            assert isinstance(config["backtest"]["initial_cash"], dict)


class TestGetBacktestPeriod:
    """测试回测时间区间计算"""
    
    def test_fixed_mode_with_string_dates(self):
        """测试固定模式下的字符串日期解析"""
        config_data = {
            "backtest": {
                "period_mode": "fixed",
                "start": "2021-04-02",
                "end": "2025-07-02"
            }
        }
        
        with patch("stock_analysis.utils.config.load_cfg", return_value=config_data):
            start, end = get_backtest_period()
            
            assert start == datetime.date(2021, 4, 2)
            assert end == datetime.date(2025, 7, 2)
    
    def test_fixed_mode_with_date_objects(self):
        """测试固定模式下的 date 对象处理"""
        config_data = {
            "backtest": {
                "period_mode": "fixed",
                "start": datetime.date(2020, 1, 1),
                "end": datetime.date(2024, 12, 31)
            }
        }
        
        with patch("stock_analysis.utils.config.load_cfg", return_value=config_data):
            start, end = get_backtest_period()
            
            assert start == datetime.date(2020, 1, 1)
            assert end == datetime.date(2024, 12, 31)
    
    def test_dynamic_mode_with_buffer(self):
        """测试动态模式下的缓冲时间计算"""
        config_data = {
            "backtest": {
                "period_mode": "dynamic",
                "buffer": {"months": 3, "days": 10}
            }
        }
        
        # 模拟投资组合数据
        portfolios = {
            datetime.date(2022, 1, 1): ["AAPL", "MSFT"],
            datetime.date(2022, 4, 1): ["GOOGL", "TSLA"],
            datetime.date(2022, 7, 1): ["AMZN", "META"]
        }
        
        with patch("stock_analysis.utils.config.load_cfg", return_value=config_data):
            start, end = get_backtest_period(portfolios)
            
            assert start == datetime.date(2022, 1, 1)
            expected_end = datetime.date(2022, 7, 1) + relativedelta(months=3, days=10)
            assert end == expected_end
    
    def test_dynamic_mode_without_portfolios(self):
        """测试动态模式下缺少投资组合数据时的异常"""
        config_data = {
            "backtest": {
                "period_mode": "dynamic"
            }
        }
        
        with patch("stock_analysis.utils.config.load_cfg", return_value=config_data):
            with pytest.raises(ValueError, match="Dynamic mode requires portfolios data"):
                get_backtest_period()
    
    def test_dynamic_mode_default_buffer(self):
        """测试动态模式下默认缓冲时间"""
        config_data = {
            "backtest": {
                "period_mode": "dynamic"
                # 没有 buffer 配置，应使用默认值
            }
        }
        
        portfolios = {
            datetime.date(2023, 1, 15): ["SPY"]
        }
        
        with patch("stock_analysis.utils.config.load_cfg", return_value=config_data):
            start, end = get_backtest_period(portfolios)
            
            assert start == datetime.date(2023, 1, 15)
            expected_end = datetime.date(2023, 1, 15) + relativedelta(months=3, days=10)
            assert end == expected_end


class TestGetInitialCash:
    """测试初始资金获取"""
    
    def test_unified_cash_format(self):
        """测试统一资金格式"""
        config_data = {
            "backtest": {
                "initial_cash": 1500000
            }
        }
        
        with patch("stock_analysis.utils.config.load_cfg", return_value=config_data):
            assert get_initial_cash("ai") == 1500000.0
            assert get_initial_cash("quant") == 1500000.0
            assert get_initial_cash("spy") == 1500000.0
    
    def test_strategy_specific_cash_format(self):
        """测试分策略资金格式"""
        config_data = {
            "backtest": {
                "initial_cash": {
                    "ai": 2000000,
                    "quant": 1500000,
                    "spy": 500000
                }
            }
        }
        
        with patch("stock_analysis.utils.config.load_cfg", return_value=config_data):
            assert get_initial_cash("ai") == 2000000.0
            assert get_initial_cash("quant") == 1500000.0
            assert get_initial_cash("spy") == 500000.0
    
    def test_strategy_specific_with_missing_strategy(self):
        """测试分策略格式下缺少指定策略时的默认值"""
        config_data = {
            "backtest": {
                "initial_cash": {
                    "ai": 2000000,
                    "spy": 500000
                    # 缺少 "quant" 策略
                }
            }
        }
        
        with patch("stock_analysis.utils.config.load_cfg", return_value=config_data):
            assert get_initial_cash("ai") == 2000000.0
            assert get_initial_cash("quant") == 1000000.0  # 默认值
            assert get_initial_cash("spy") == 500000.0
    
    def test_no_initial_cash_config(self):
        """测试无初始资金配置时的默认值"""
        config_data = {
            "backtest": {
                "period_mode": "fixed"
                # 没有 initial_cash 配置
            }
        }
        
        with patch("stock_analysis.utils.config.load_cfg", return_value=config_data):
            assert get_initial_cash("ai") == 1000000.0
            assert get_initial_cash("quant") == 1000000.0
            assert get_initial_cash("spy") == 1000000.0


class TestConfigIntegration:
    """集成测试：使用真实配置文件格式"""
    
    def test_real_config_format_fixed_mode(self, tmp_path):
        """测试真实配置文件格式 - 固定模式"""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        
        # 使用与 template.yaml 相似的真实格式
        config_content = """
backtest:
  period_mode: fixed
  start: 2021-04-02
  end: 2025-07-02
  buffer:
    months: 3
    days: 10
  initial_cash: 1000000
"""
        
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(config_content)
        
        with patch("stock_analysis.utils.config.Path") as mock_path:
            mock_path(__file__).resolve.return_value.parents = [None, None, None, tmp_path]
            
            # 测试时间区间
            start, end = get_backtest_period()
            assert start == datetime.date(2021, 4, 2)
            assert end == datetime.date(2025, 7, 2)
            
            # 测试统一资金
            assert get_initial_cash("ai") == 1000000.0
            assert get_initial_cash("spy") == 1000000.0
    
    def test_real_config_format_dynamic_mode(self, tmp_path):
        """测试真实配置文件格式 - 动态模式"""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        
        config_content = """
backtest:
  period_mode: dynamic
  buffer:
    months: 6
    days: 15
  initial_cash:
    ai: 1000000
    quant: 1000000
    spy: 1000000
"""
        
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(config_content)
        
        with patch("stock_analysis.utils.config.Path") as mock_path:
            mock_path(__file__).resolve.return_value.parents = [None, None, None, tmp_path]
            
            # 测试动态时间区间
            portfolios = {
                datetime.date(2022, 3, 1): ["AAPL"],
                datetime.date(2022, 9, 1): ["MSFT"]
            }
            
            start, end = get_backtest_period(portfolios)
            assert start == datetime.date(2022, 3, 1)
            expected_end = datetime.date(2022, 9, 1) + relativedelta(months=6, days=15)
            assert end == expected_end
            
            # 测试分策略资金
            assert get_initial_cash("ai") == 1000000.0
            assert get_initial_cash("quant") == 1000000.0
            assert get_initial_cash("spy") == 1000000.0