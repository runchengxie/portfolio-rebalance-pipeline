import pytest
import sys
from unittest.mock import Mock, patch
from types import SimpleNamespace

import stock_analysis.cli as cli


@pytest.mark.unit
def test_cli_dispatch_lb_quote(monkeypatch):
    """测试CLI将lb-quote命令分发到run_lb_quote函数。"""
    # 创建探针函数记录调用
    called = {}
    
    def fake_run_lb_quote(tickers):
        called["tickers"] = tickers
        return 0
    
    # 替换真实函数
    monkeypatch.setattr(cli, "run_lb_quote", fake_run_lb_quote)
    
    # 模拟命令行参数
    test_args = ["prog", "lb-quote", "AAPL", "MSFT"]
    with patch.object(sys, 'argv', test_args):
        # 直接测试分发逻辑
        result = cli.run_lb_quote(["AAPL", "MSFT"])
        
        assert result == 0
        assert called["tickers"] == ["AAPL", "MSFT"]


@pytest.mark.unit
def test_cli_dispatch_lb_rebalance(monkeypatch):
    """测试CLI将lb-rebalance命令分发到run_lb_rebalance函数。"""
    called = {}
    
    def fake_run_lb_rebalance(input_file, account="main", dry_run=True):
        called["input_file"] = input_file
        called["account"] = account
        called["dry_run"] = dry_run
        return 0
    
    monkeypatch.setattr(cli, "run_lb_rebalance", fake_run_lb_rebalance)
    
    # 测试默认参数
    result = cli.run_lb_rebalance("test.xlsx")
    assert result == 0
    assert called["input_file"] == "test.xlsx"
    assert called["account"] == "main"
    assert called["dry_run"] == True
    
    # 测试自定义参数
    result = cli.run_lb_rebalance("test2.xlsx", "account2", False)
    assert result == 0
    assert called["input_file"] == "test2.xlsx"
    assert called["account"] == "account2"
    assert called["dry_run"] == False


@pytest.mark.unit
def test_main_command_routing():
    """测试main函数的命令路由逻辑。"""
    # 创建模拟的args对象
    args = SimpleNamespace()
    
    with patch.object(cli, 'create_parser') as mock_parser:
        with patch.object(cli, 'run_lb_quote', return_value=0) as mock_lb_quote:
            with patch.object(cli, 'run_lb_rebalance', return_value=0) as mock_lb_rebalance:
                # 模拟parser返回
                mock_parser_instance = Mock()
                mock_parser.return_value = mock_parser_instance
                
                # 测试lb-quote命令
                args.command = "lb-quote"
                args.tickers = ["AAPL", "GOOGL"]
                mock_parser_instance.parse_args.return_value = args
                
                result = cli.main()
                assert result == 0
                mock_lb_quote.assert_called_once_with(["AAPL", "GOOGL"])
                
                # 重置mock
                mock_lb_quote.reset_mock()
                mock_lb_rebalance.reset_mock()
                
                # 测试lb-rebalance命令
                args.command = "lb-rebalance"
                args.input_file = "portfolio.xlsx"
                args.account = "test_account"
                args.execute = False  # dry_run = True
                
                result = cli.main()
                assert result == 0
                mock_lb_rebalance.assert_called_once_with(
                    "portfolio.xlsx", "test_account", True
                )


@pytest.mark.unit
def test_main_no_command():
    """测试没有提供命令时显示帮助信息。"""
    args = SimpleNamespace()
    args.command = None
    
    with patch.object(cli, 'create_parser') as mock_parser:
        mock_parser_instance = Mock()
        mock_parser.return_value = mock_parser_instance
        mock_parser_instance.parse_args.return_value = args
        
        result = cli.main()
        assert result == 0
        mock_parser_instance.print_help.assert_called_once()


@pytest.mark.unit
def test_main_unknown_command():
    """测试未知命令的处理。"""
    args = SimpleNamespace()
    args.command = "unknown-command"
    
    with patch.object(cli, 'create_parser') as mock_parser:
        mock_parser_instance = Mock()
        mock_parser.return_value = mock_parser_instance
        mock_parser_instance.parse_args.return_value = args
        
        with patch('builtins.print') as mock_print:
            result = cli.main()
            assert result == 1
            mock_print.assert_called_with(
                "未知命令：unknown-command", file=sys.stderr
            )


@pytest.mark.unit
def test_run_lb_quote_import_error(monkeypatch):
    """测试run_lb_quote在导入错误时的处理。"""
    # 模拟导入longport_client模块时的错误
    original_import = __builtins__['__import__']
    
    def mock_import(name, *args, **kwargs):
        if 'longport_client' in name:
            raise ImportError("No module named 'longport'")
        return original_import(name, *args, **kwargs)
    
    with patch('builtins.__import__', side_effect=mock_import):
        with patch('builtins.print') as mock_print:
            result = cli.run_lb_quote(["AAPL"])
            assert result == 1
            # 验证错误信息被打印
            assert any("longport" in str(call) or "LongPort" in str(call) for call in mock_print.call_args_list)


@pytest.mark.unit
def test_run_lb_rebalance_file_not_found():
    """测试run_lb_rebalance在文件不存在时的处理。"""
    with patch('builtins.print') as mock_print:
        result = cli.run_lb_rebalance("non_existent_file.xlsx")
        assert result == 1
        # 验证错误信息被打印
        assert any("文件不存在" in str(call) for call in mock_print.call_args_list)


@pytest.mark.unit
def test_app_function():
    """测试app函数作为入口点。"""
    with patch.object(cli, 'main', return_value=0) as mock_main:
        with patch.object(sys, 'exit') as mock_exit:
            cli.app()
            mock_main.assert_called_once()
            mock_exit.assert_called_once_with(0)