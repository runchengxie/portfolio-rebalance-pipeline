"""LongPort账户概览输出格式测试

测试lb-account命令的不同输出格式：
- table格式的表头和字段验证
- json格式的结构验证
- 资金/持仓的不同显示分支
- 错误情况的处理
"""

import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from stock_analysis import cli


@pytest.mark.unit
class TestLBAccountTableOutput:
    """测试table格式输出"""
    
    def test_lb_account_prints_positions_table(self, capsys):
        """测试账户概览打印持仓表格（用户提供的示例）"""
        fake = SimpleNamespace(
            cash=1234.56,
            positions=[{"symbol": "AAPL.US", "qty": 10, "last": 199.99, "est_value": 1999.9}]
        )
        with patch("stock_analysis.cli.LongPortClient") as M:
            M.return_value = SimpleNamespace(account_overview=lambda env: fake)
            assert cli.run_lb_account(env="test", only_funds=False, only_positions=False, fmt="table") == 0
        
        out = capsys.readouterr().out
        assert "现金" in out and "持仓" in out and "AAPL.US" in out
    
    def test_table_output_with_funds_and_positions(self, capsys):
        """测试完整的资金和持仓表格输出"""
        # 模拟LongPortClient的portfolio_snapshot和quote_last方法
        mock_client = Mock()
        mock_client.portfolio_snapshot.return_value = (
            5000.0,  # cash_usd
            {"AAPL.US": 10, "MSFT.US": 5}  # positions
        )
        mock_client.quote_last.return_value = {
            "AAPL.US": (150.0, "USD"),
            "MSFT.US": (300.0, "USD")
        }
        mock_client.close.return_value = None
        
        with patch("stock_analysis.cli.LongPortClient", return_value=mock_client):
            result = cli.run_lb_account(env="test", only_funds=False, only_positions=False, fmt="table")
        
        assert result == 0
        out = capsys.readouterr().out
        
        # 验证表头和关键信息
        assert "[TEST] 现金(USD): $5,000.00" in out
        assert "Symbol" in out and "Qty" in out and "Last" in out and "Est.Value" in out
        assert "AAPL.US" in out and "MSFT.US" in out
        assert "10" in out and "5" in out  # 数量
        assert "150.00" in out and "300.00" in out  # 价格
    
    def test_table_output_only_funds(self, capsys):
        """测试只显示资金信息"""
        mock_client = Mock()
        mock_client.portfolio_snapshot.return_value = (2500.75, {"AAPL.US": 10})
        mock_client.close.return_value = None
        
        with patch("stock_analysis.cli.LongPortClient", return_value=mock_client):
            result = cli.run_lb_account(env="test", only_funds=True, only_positions=False, fmt="table")
        
        assert result == 0
        out = capsys.readouterr().out
        
        # 应该显示资金，不显示持仓表格
        assert "[TEST] 现金(USD): $2,500.75" in out
        assert "Symbol" not in out  # 不应该有持仓表头
        assert "AAPL.US" not in out  # 不应该有持仓信息
    
    def test_table_output_only_positions(self, capsys):
        """测试只显示持仓信息"""
        mock_client = Mock()
        mock_client.portfolio_snapshot.return_value = (
            1000.0,
            {"GOOGL.US": 2, "AMZN.US": 1}
        )
        mock_client.quote_last.return_value = {
            "GOOGL.US": (2500.0, "USD"),
            "AMZN.US": (3000.0, "USD")
        }
        mock_client.close.return_value = None
        
        with patch("stock_analysis.cli.LongPortClient", return_value=mock_client):
            result = cli.run_lb_account(env="test", only_funds=False, only_positions=True, fmt="table")
        
        assert result == 0
        out = capsys.readouterr().out
        
        # 应该显示持仓，但不显示资金信息的表头
        assert "现金" not in out  # 不应该显示资金信息
        assert "GOOGL.US" in out and "AMZN.US" in out
        assert "2500.00" in out and "3000.00" in out
    
    def test_table_output_no_positions(self, capsys):
        """测试无持仓的情况"""
        mock_client = Mock()
        mock_client.portfolio_snapshot.return_value = (1000.0, {})  # 无持仓
        mock_client.close.return_value = None
        
        with patch("stock_analysis.cli.LongPortClient", return_value=mock_client):
            result = cli.run_lb_account(env="test", only_funds=False, only_positions=False, fmt="table")
        
        assert result == 0
        out = capsys.readouterr().out
        
        assert "[TEST] 现金(USD): $1,000.00" in out
        assert "无持仓" in out
    
    def test_table_output_real_environment_warning(self, capsys):
        """测试real环境的警告信息"""
        mock_client = Mock()
        mock_client.portfolio_snapshot.return_value = (5000.0, {})
        mock_client.close.return_value = None
        
        with patch("stock_analysis.cli.LongPortClient", return_value=mock_client):
            result = cli.run_lb_account(env="real", only_funds=True, only_positions=False, fmt="table")
        
        assert result == 0
        out = capsys.readouterr().out
        
        # 应该显示实盘警告
        assert "!!! REAL ACCOUNT DATA (READ-ONLY) !!!" in out
        assert "[REAL] 现金(USD): $5,000.00" in out
    
    def test_table_output_both_environments(self, capsys):
        """测试同时显示test和real环境"""
        mock_client = Mock()
        # 模拟两次调用返回不同数据
        mock_client.portfolio_snapshot.side_effect = [
            (1000.0, {"AAPL.US": 5}),  # test环境
            (2000.0, {"MSFT.US": 3})   # real环境
        ]
        mock_client.quote_last.side_effect = [
            {"AAPL.US": (200.0, "USD")},
            {"MSFT.US": (300.0, "USD")}
        ]
        mock_client.close.return_value = None
        
        with patch("stock_analysis.cli.LongPortClient", return_value=mock_client):
            result = cli.run_lb_account(env="both", only_funds=False, only_positions=False, fmt="table")
        
        assert result == 0
        out = capsys.readouterr().out
        
        # 应该显示两个环境的数据
        assert "!!! REAL ACCOUNT DATA (READ-ONLY) !!!" in out
        assert "[TEST] 现金(USD): $1,000.00" in out
        assert "[REAL] 现金(USD): $2,000.00" in out
        assert "AAPL.US" in out and "MSFT.US" in out


@pytest.mark.unit
class TestLBAccountJSONOutput:
    """测试JSON格式输出"""
    
    def test_lb_account_outputs_json(self, capsys):
        """测试账户概览输出JSON格式（用户提供的示例）"""
        fake = SimpleNamespace(cash=0.0, positions=[])
        with patch("stock_analysis.cli.LongPortClient") as M:
            M.return_value = SimpleNamespace(account_overview=lambda env: fake)
            assert cli.run_lb_account(env="test", only_funds=True, only_positions=False, fmt="json") == 0
        
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data[0]["cash_usd"] == 0.0 and data[0]["positions"] == []
    
    def test_json_output_structure(self, capsys):
        """测试JSON输出的完整结构"""
        mock_client = Mock()
        mock_client.portfolio_snapshot.return_value = (
            1500.50,
            {"AAPL.US": 10, "MSFT.US": 5}
        )
        mock_client.quote_last.return_value = {
            "AAPL.US": (150.0, "USD"),
            "MSFT.US": (250.0, "USD")
        }
        mock_client.close.return_value = None
        
        with patch("stock_analysis.cli.LongPortClient", return_value=mock_client):
            result = cli.run_lb_account(env="test", only_funds=False, only_positions=False, fmt="json")
        
        assert result == 0
        out = capsys.readouterr().out
        
        # 解析JSON并验证结构
        data = json.loads(out)
        assert isinstance(data, list)
        assert len(data) == 1
        
        account_data = data[0]
        assert account_data["env"] == "test"
        assert account_data["cash_usd"] == 1500.50
        assert isinstance(account_data["positions"], list)
        assert len(account_data["positions"]) == 2
        
        # 验证持仓数据结构
        positions = account_data["positions"]
        aapl_pos = next(p for p in positions if p["symbol"] == "AAPL.US")
        assert aapl_pos["qty"] == 10
        assert aapl_pos["last"] == 150.0
        assert aapl_pos["est_value"] == 1500.0
        
        msft_pos = next(p for p in positions if p["symbol"] == "MSFT.US")
        assert msft_pos["qty"] == 5
        assert msft_pos["last"] == 250.0
        assert msft_pos["est_value"] == 1250.0
    
    def test_json_output_empty_positions(self, capsys):
        """测试JSON输出无持仓的情况"""
        mock_client = Mock()
        mock_client.portfolio_snapshot.return_value = (500.0, {})
        mock_client.close.return_value = None
        
        with patch("stock_analysis.cli.LongPortClient", return_value=mock_client):
            result = cli.run_lb_account(env="test", only_funds=False, only_positions=False, fmt="json")
        
        assert result == 0
        out = capsys.readouterr().out
        
        data = json.loads(out)
        assert data[0]["cash_usd"] == 500.0
        assert data[0]["positions"] == []
    
    def test_json_output_both_environments(self, capsys):
        """测试JSON输出两个环境的数据"""
        mock_client = Mock()
        mock_client.portfolio_snapshot.side_effect = [
            (1000.0, {"AAPL.US": 5}),
            (2000.0, {"MSFT.US": 3})
        ]
        mock_client.quote_last.side_effect = [
            {"AAPL.US": (200.0, "USD")},
            {"MSFT.US": (300.0, "USD")}
        ]
        mock_client.close.return_value = None
        
        with patch("stock_analysis.cli.LongPortClient", return_value=mock_client):
            result = cli.run_lb_account(env="both", only_funds=False, only_positions=False, fmt="json")
        
        assert result == 0
        out = capsys.readouterr().out
        
        data = json.loads(out)
        assert len(data) == 2
        
        # 验证test环境数据
        test_data = next(d for d in data if d["env"] == "test")
        assert test_data["cash_usd"] == 1000.0
        assert len(test_data["positions"]) == 1
        assert test_data["positions"][0]["symbol"] == "AAPL.US"
        
        # 验证real环境数据
        real_data = next(d for d in data if d["env"] == "real")
        assert real_data["cash_usd"] == 2000.0
        assert len(real_data["positions"]) == 1
        assert real_data["positions"][0]["symbol"] == "MSFT.US"


@pytest.mark.unit
class TestLBAccountErrorHandling:
    """测试错误处理"""
    
    def test_import_error_handling(self, capsys):
        """测试导入错误的处理"""
        with patch('builtins.__import__', side_effect=ImportError("No module named 'longport'")):
            result = cli.run_lb_account()
        
        assert result == 1
        err = capsys.readouterr().err
        assert "无法导入LongPort模块" in err
        assert "pip install longport" in err
    
    def test_client_connection_error(self, capsys):
        """测试客户端连接错误"""
        with patch("stock_analysis.cli.LongPortClient", side_effect=Exception("Connection failed")):
            result = cli.run_lb_account(env="test", fmt="table")
        
        assert result == 1
        err = capsys.readouterr().err
        assert "账户总览失败" in err
    
    def test_portfolio_snapshot_error_fallback(self, capsys):
        """测试portfolio_snapshot错误时的fallback处理"""
        mock_client = Mock()
        mock_client.portfolio_snapshot.side_effect = Exception("API Error")
        mock_client.close.return_value = None
        
        with patch("stock_analysis.cli.LongPortClient", return_value=mock_client):
            result = cli.run_lb_account(env="test", fmt="json")
        
        assert result == 0  # 应该成功，使用模拟数据
        out = capsys.readouterr().out
        err = capsys.readouterr().err
        
        # 应该有警告信息
        assert "警告：无法获取 test 环境账户数据" in err
        
        # JSON输出应该包含模拟数据
        data = json.loads(out)
        assert data[0]["cash_usd"] == 0.0
        assert data[0]["positions"] == []


@pytest.mark.unit
class TestLBAccountParameterValidation:
    """测试参数验证"""
    
    def test_invalid_environment(self, capsys):
        """测试无效环境参数"""
        mock_client = Mock()
        mock_client.portfolio_snapshot.return_value = (1000.0, {})
        mock_client.close.return_value = None
        
        with patch("stock_analysis.cli.LongPortClient", return_value=mock_client):
            # 传入无效环境，应该被过滤掉
            result = cli.run_lb_account(env="invalid", fmt="table")
        
        assert result == 0
        out = capsys.readouterr().out
        
        # 无效环境应该被忽略，不应该有任何输出
        assert "[INVALID]" not in out
        assert "现金" not in out
    
    def test_format_parameter_validation(self, capsys):
        """测试格式参数的处理"""
        mock_client = Mock()
        mock_client.portfolio_snapshot.return_value = (1000.0, {})
        mock_client.close.return_value = None
        
        with patch("stock_analysis.cli.LongPortClient", return_value=mock_client):
            # 测试非json格式，应该默认为table
            result = cli.run_lb_account(env="test", fmt="xml")
        
        assert result == 0
        out = capsys.readouterr().out
        
        # 应该使用table格式输出
        assert "[TEST] 现金(USD)" in out
        assert "{" not in out  # 不应该是JSON格式
    
    def test_conflicting_flags(self, capsys):
        """测试冲突的标志参数"""
        mock_client = Mock()
        mock_client.portfolio_snapshot.return_value = (
            1000.0,
            {"AAPL.US": 10}
        )
        mock_client.quote_last.return_value = {"AAPL.US": (150.0, "USD")}
        mock_client.close.return_value = None
        
        with patch("stock_analysis.cli.LongPortClient", return_value=mock_client):
            # 同时指定only_funds和only_positions
            result = cli.run_lb_account(
                env="test", 
                only_funds=True, 
                only_positions=True, 
                fmt="table"
            )
        
        assert result == 0
        out = capsys.readouterr().out
        
        # only_funds优先级更高，不应该显示持仓
        assert "[TEST] 现金(USD)" in out
        assert "Symbol" not in out
        assert "AAPL.US" not in out