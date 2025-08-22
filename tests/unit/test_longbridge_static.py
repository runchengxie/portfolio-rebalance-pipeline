import pytest
from pathlib import Path


@pytest.mark.unit
def test_pyproject_longbridge_dependency():
    """测试pyproject.toml中包含longbridge依赖。"""
    pyproject_file = Path("pyproject.toml")
    assert pyproject_file.exists(), "pyproject.toml文件不存在"
    
    content = pyproject_file.read_text(encoding='utf-8')
    assert "longbridge>=0.2.77" in content, "longbridge>=0.2.77依赖未找到"


@pytest.mark.unit
def test_broker_directory_structure():
    """测试broker目录结构是否正确。"""
    project_root = Path(".")
    
    # 检查broker目录和文件
    broker_dir = project_root / "src" / "stock_analysis" / "broker"
    broker_init = broker_dir / "__init__.py"
    longbridge_client = broker_dir / "longbridge_client.py"
    
    assert broker_dir.exists(), "broker目录不存在"
    assert broker_init.exists(), "broker/__init__.py不存在"
    assert longbridge_client.exists(), "longbridge_client.py不存在"


@pytest.mark.unit
def test_cli_contains_longbridge_commands():
    """测试CLI文件包含LongBridge相关命令。"""
    cli_file = Path("src/stock_analysis/cli.py")
    assert cli_file.exists(), "CLI文件不存在"
    
    content = cli_file.read_text(encoding='utf-8')
    
    # 检查命令定义
    assert "lb-quote" in content, "lb-quote命令未找到"
    assert "lb-rebalance" in content, "lb-rebalance命令未找到"
    
    # 检查函数定义
    assert "def run_lb_quote" in content, "run_lb_quote函数未找到"
    assert "def run_lb_rebalance" in content, "run_lb_rebalance函数未找到"
    
    # 检查LongBridge相关导入或引用
    assert "LongBridge" in content, "LongBridge相关代码未找到"


@pytest.mark.unit
def test_longbridge_client_exports():
    """测试longbridge_client.py导出必要的函数和类。"""
    longbridge_client_file = Path("src/stock_analysis/broker/longbridge_client.py")
    assert longbridge_client_file.exists(), "longbridge_client.py文件不存在"
    
    content = longbridge_client_file.read_text(encoding='utf-8')
    
    # 检查关键函数和类定义
    assert "def _to_lb_symbol" in content, "_to_lb_symbol函数未找到"
    assert "def get_config" in content, "get_config函数未找到"
    assert "class LongBridgeClient" in content, "LongBridgeClient类未找到"
    
    # 检查关键方法
    assert "def quote_last" in content, "quote_last方法未找到"
    assert "def candles" in content, "candles方法未找到"
    assert "def submit_limit" in content, "submit_limit方法未找到"


@pytest.mark.unit
def test_pytest_markers_configured():
    """测试pytest标记是否在pyproject.toml中正确配置。"""
    pyproject_file = Path("pyproject.toml")
    assert pyproject_file.exists(), "pyproject.toml文件不存在"
    
    content = pyproject_file.read_text(encoding='utf-8')
    
    # 检查pytest标记配置
    assert "markers" in content, "pytest markers配置未找到"
    assert "unit" in content, "unit标记未配置"
    assert "integration" in content, "integration标记未配置"
    assert "e2e" in content, "e2e标记未配置"


@pytest.mark.unit
def test_longbridge_imports():
    """测试longbridge_client.py中的longbridge导入。"""
    longbridge_client_file = Path("src/stock_analysis/broker/longbridge_client.py")
    content = longbridge_client_file.read_text(encoding='utf-8')
    
    # 检查必要的longbridge导入
    required_imports = [
        "from longbridge.openapi import",
        "Config",
        "QuoteContext",
        "TradeContext",
        "OrderSide",
        "OrderType",
        "AdjustType",
        "Period",
        "TimeInForceType"
    ]
    
    for import_item in required_imports:
        assert import_item in content, f"缺少导入: {import_item}"


@pytest.mark.unit
def test_decimal_import():
    """测试Decimal导入用于精确的价格计算。"""
    longbridge_client_file = Path("src/stock_analysis/broker/longbridge_client.py")
    content = longbridge_client_file.read_text(encoding='utf-8')
    
    assert "from decimal import Decimal" in content, "缺少Decimal导入"
    assert "Decimal(str(" in content, "未使用Decimal进行价格转换"


@pytest.mark.unit
def test_env_example_file():
    """测试.env.example文件存在（用于配置示例）。"""
    env_example = Path(".env.example")
    # 这个文件可能存在也可能不存在，所以只是检查而不强制要求
    if env_example.exists():
        content = env_example.read_text(encoding='utf-8')
        # 如果存在，应该包含LongBridge相关的环境变量示例
        longbridge_vars = ["LONGBRIDGE_APP_KEY", "LONGBRIDGE_APP_SECRET", "LONGBRIDGE_ACCESS_TOKEN"]
        for var in longbridge_vars:
            if var in content:
                # 至少找到一个LongBridge变量就算通过
                break
        else:
            pytest.fail("如果.env.example存在，应该包含LongBridge环境变量示例")