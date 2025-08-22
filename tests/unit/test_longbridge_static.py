import pytest
from pathlib import Path


@pytest.mark.unit
def test_pyproject_longport_dependency():
    """测试pyproject.toml中包含longport依赖。"""
    pyproject_file = Path("pyproject.toml")
    assert pyproject_file.exists(), "pyproject.toml文件不存在"
    
    content = pyproject_file.read_text(encoding='utf-8')
    assert "longport>=0.2.77" in content, "longport>=0.2.77依赖未找到"


@pytest.mark.unit
def test_broker_directory_structure():
    """测试broker目录结构是否正确。"""
    project_root = Path(".")
    
    # 检查broker目录和文件
    broker_dir = project_root / "src" / "stock_analysis" / "broker"
    broker_init = broker_dir / "__init__.py"
    longport_client = broker_dir / "longport_client.py"
    
    assert broker_dir.exists(), "broker目录不存在"
    assert broker_init.exists(), "broker/__init__.py不存在"
    assert longport_client.exists(), "longport_client.py不存在"


@pytest.mark.unit
def test_cli_contains_longport_commands():
    """测试CLI文件包含LongPort相关命令。"""
    cli_file = Path("src/stock_analysis/cli.py")
    assert cli_file.exists(), "CLI文件不存在"
    
    content = cli_file.read_text(encoding='utf-8')
    
    # 检查命令定义
    assert "lb-quote" in content, "lb-quote命令未找到"
    assert "lb-rebalance" in content, "lb-rebalance命令未找到"
    
    # 检查函数定义
    assert "def run_lb_quote" in content, "run_lb_quote函数未找到"
    assert "def run_lb_rebalance" in content, "run_lb_rebalance函数未找到"
    
    # 检查LongPort相关导入或引用
    assert "LongPort" in content, "LongPort相关代码未找到"


@pytest.mark.unit
def test_longport_client_exports():
    """测试longport_client.py导出必要的函数和类。"""
    longport_client_file = Path("src/stock_analysis/broker/longport_client.py")
    assert longport_client_file.exists(), "longport_client.py文件不存在"
    
    content = longport_client_file.read_text(encoding='utf-8')
    
    # 检查关键函数和类定义
    assert "def _to_lb_symbol" in content, "_to_lb_symbol函数未找到"
    assert "def getenv_both" in content, "getenv_both函数未找到"
    assert "class LongPortClient" in content, "LongPortClient类未找到"
    
    # 检查关键方法
    assert "def quote_last" in content, "quote_last方法未找到"
    assert "def place_order" in content, "place_order方法未找到"


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
def test_longport_imports():
    """测试longport_client.py中的兼容性导入。"""
    longport_client_file = Path("src/stock_analysis/broker/longport_client.py")
    content = longport_client_file.read_text(encoding='utf-8')
    
    # 检查兼容性导入结构
    assert "try:" in content, "缺少兼容性导入的try语句"
    assert "from longport.openapi import" in content, "缺少longport导入"
    assert "except ImportError:" in content, "缺少ImportError处理"
    assert "from longbridge.openapi import" in content, "缺少longbridge兼容导入"
    
    # 检查必要的类导入
    required_imports = [
        "Config",
        "QuoteContext",
        "TradeContext"
    ]
    
    for import_item in required_imports:
        assert import_item in content, f"缺少导入: {import_item}"


@pytest.mark.unit
def test_environment_compatibility():
    """测试环境变量兼容性函数。"""
    longport_client_file = Path("src/stock_analysis/broker/longport_client.py")
    content = longport_client_file.read_text(encoding='utf-8')
    
    assert "def getenv_both" in content, "缺少环境变量兼容性函数"
    assert "LONGPORT_" in content, "缺少新环境变量前缀"
    assert "LONGBRIDGE_" in content, "缺少旧环境变量前缀兼容"


@pytest.mark.unit
def test_env_example_file():
    """测试.env.example文件存在（用于配置示例）。"""
    env_example = Path(".env.example")
    # 这个文件可能存在也可能不存在，所以只是检查而不强制要求
    if env_example.exists():
        content = env_example.read_text(encoding='utf-8')
        # 如果存在，应该包含LongPort相关的环境变量示例
        longport_vars = ["LONGPORT_APP_KEY", "LONGPORT_APP_SECRET", "LONGPORT_ACCESS_TOKEN"]
        for var in longport_vars:
            if var in content:
                # 至少找到一个LongPort变量就算通过
                break
        else:
            pytest.fail("如果.env.example存在，应该包含LongPort环境变量示例")