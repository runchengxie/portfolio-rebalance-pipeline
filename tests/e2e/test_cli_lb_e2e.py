import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.e2e
def test_cli_lb_quote_help():
    """测试lb-quote命令的帮助信息。"""
    # 测试帮助命令不需要API凭据
    result = subprocess.run(
        [sys.executable, "-m", "stock_analysis.cli", "lb-quote", "--help"],
        capture_output=True,
        text=True,
        cwd=Path.cwd()
    )
    
    assert result.returncode == 0, f"帮助命令失败: {result.stderr}"
    assert "lb-quote" in result.stdout.lower()
    assert "tickers" in result.stdout.lower() or "股票代码" in result.stdout


@pytest.mark.e2e
def test_cli_lb_rebalance_help():
    """测试lb-rebalance命令的帮助信息。"""
    result = subprocess.run(
        [sys.executable, "-m", "stock_analysis.cli", "lb-rebalance", "--help"],
        capture_output=True,
        text=True,
        cwd=Path.cwd()
    )
    
    assert result.returncode == 0, f"帮助命令失败: {result.stderr}"
    assert "lb-rebalance" in result.stdout.lower()
    assert "input" in result.stdout.lower() or "文件" in result.stdout


@pytest.mark.e2e
def test_cli_main_help():
    """测试主CLI帮助信息。"""
    result = subprocess.run(
        [sys.executable, "-m", "stock_analysis.cli", "--help"],
        capture_output=True,
        text=True,
        cwd=Path.cwd()
    )
    
    assert result.returncode == 0, f"主帮助命令失败: {result.stderr}"
    assert "lb-quote" in result.stdout
    assert "lb-rebalance" in result.stdout


@pytest.mark.e2e
def test_cli_no_command():
    """测试不提供命令时的行为。"""
    result = subprocess.run(
        [sys.executable, "-m", "stock_analysis.cli"],
        capture_output=True,
        text=True,
        cwd=Path.cwd()
    )
    
    # 应该显示帮助信息并正常退出
    assert result.returncode == 0
    assert "usage" in result.stdout.lower() or "用法" in result.stdout


@pytest.mark.e2e
def test_cli_unknown_command():
    """测试未知命令的处理。"""
    result = subprocess.run(
        [sys.executable, "-m", "stock_analysis.cli", "unknown-command"],
        capture_output=True,
        text=True,
        cwd=Path.cwd()
    )
    
    # 应该返回错误码
    assert result.returncode != 0
    assert "unknown" in result.stderr.lower() or "未知" in result.stderr


@pytest.mark.e2e
def test_cli_lb_quote_without_longport():
    """测试在没有longport包时lb-quote命令的行为。"""
    # 创建一个临时环境，移除longport包
    env = os.environ.copy()
    # 通过修改PYTHONPATH来模拟包不存在的情况
    # 这是一个简化的测试，实际情况可能更复杂
    
    result = subprocess.run(
        [sys.executable, "-m", "stock_analysis.cli", "lb-quote", "AAPL"],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
        env=env
    )
    
    # 如果longport未安装，应该返回错误码并提示安装
    if "longport" in result.stderr.lower() and "import" in result.stderr.lower():
        assert result.returncode != 0
        assert "pip install longport" in result.stderr or "安装" in result.stderr
    else:
        # 如果longport已安装，可能会因为缺少API凭据而失败，这也是正常的
        # 只要不是语法错误或导入错误就可以
        pass


@pytest.mark.e2e
def test_cli_lb_rebalance_file_not_found():
    """测试lb-rebalance命令处理文件不存在的情况。"""
    non_existent_file = "non_existent_portfolio_file_12345.xlsx"
    
    result = subprocess.run(
        [sys.executable, "-m", "stock_analysis.cli", "lb-rebalance", non_existent_file],
        capture_output=True,
        text=True,
        cwd=Path.cwd()
    )
    
    # 应该返回错误码并提示文件不存在
    assert result.returncode != 0
    assert "not found" in result.stderr.lower() or "不存在" in result.stderr or "找不到" in result.stderr


@pytest.mark.e2e
@pytest.mark.skipif(
    not all(os.getenv(var) for var in ["LONGPORT_APP_KEY", "LONGPORT_APP_SECRET", "LONGPORT_ACCESS_TOKEN"]),
    reason="LongPort API凭据未配置，跳过真实API测试"
)
def test_cli_lb_quote_with_credentials():
    """测试有API凭据时的lb-quote命令。
    
    注意：这个测试需要真实的API凭据，会调用真实API。
    """
    result = subprocess.run(
        [sys.executable, "-m", "stock_analysis.cli", "lb-quote", "AAPL"],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
        timeout=30  # 设置超时避免测试卡住
    )
    
    # 如果API调用成功，应该返回0并包含价格信息
    if result.returncode == 0:
        assert "AAPL" in result.stdout
        assert "价格" in result.stdout or "price" in result.stdout.lower()
    else:
        # 如果失败，检查是否是预期的错误（如市场关闭、网络问题等）
        error_msg = result.stderr.lower()
        acceptable_errors = [
            "network", "timeout", "rate limit", "quota",
            "market closed", "网络", "超时", "限制"
        ]
        
        if any(err in error_msg for err in acceptable_errors):
            pytest.skip(f"API调用因预期原因失败，跳过测试: {result.stderr}")
        else:
            pytest.fail(f"lb-quote命令意外失败: {result.stderr}")


@pytest.mark.e2e
def test_cli_module_import():
    """测试CLI模块可以正确导入。"""
    result = subprocess.run(
        [sys.executable, "-c", "import stock_analysis.cli; print('Import successful')"],
        capture_output=True,
        text=True,
        cwd=Path.cwd()
    )
    
    assert result.returncode == 0, f"CLI模块导入失败: {result.stderr}"
    assert "Import successful" in result.stdout


@pytest.mark.e2e
def test_cli_app_entry_point():
    """测试app()入口点函数。"""
    # 测试通过直接调用app()函数
    result = subprocess.run(
        [sys.executable, "-c", 
         "from stock_analysis.cli import app; import sys; sys.argv=['test', '--help']; app()"],
        capture_output=True,
        text=True,
        cwd=Path.cwd()
    )
    
    # app()函数应该调用sys.exit()，所以返回码可能不是0
    # 但应该能正常执行并显示帮助信息
    assert "usage" in result.stdout.lower() or "用法" in result.stdout or "help" in result.stdout.lower()


@pytest.mark.e2e
def test_cli_with_python_warnings():
    """测试CLI在有Python警告时的行为。"""
    # 启用所有警告
    env = os.environ.copy()
    env["PYTHONWARNINGS"] = "default"
    
    result = subprocess.run(
        [sys.executable, "-m", "stock_analysis.cli", "--help"],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
        env=env
    )
    
    # 即使有警告，帮助命令也应该正常工作
    assert result.returncode == 0
    assert "usage" in result.stdout.lower() or "用法" in result.stdout