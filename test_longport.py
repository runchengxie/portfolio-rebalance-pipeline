import sys
from pathlib import Path

def test_file_structure():
    """Test that all required files are created."""
    print("=== 测试文件结构 ===")
    
    project_root = Path(".")
    
    # 检查broker目录和文件
    broker_dir = project_root / "src" / "stock_analysis" / "broker"
    broker_init = broker_dir / "__init__.py"
    longport_client = broker_dir / "longport_client.py"
    
    files_to_check = [
        (broker_dir, "broker目录"),
        (broker_init, "broker/__init__.py"),
        (longport_client, "longport_client.py")
    ]
    
    for file_path, description in files_to_check:
        if file_path.exists():
            print(f"✓ {description} 存在")
        else:
            print(f"✗ {description} 不存在")
    print()

def test_cli_structure():
    """Test CLI structure without importing longbridge."""
    print("=== 测试CLI结构 ===")
    
    try:
        # 读取CLI文件内容，检查是否包含新命令
        cli_file = Path("src/stock_analysis/cli.py")
        if cli_file.exists():
            content = cli_file.read_text(encoding='utf-8')
            
            checks = [
                ("lb-quote" in content, "lb-quote 命令"),
                ("lb-rebalance" in content, "lb-rebalance 命令"),
                ("run_lb_quote" in content, "run_lb_quote 函数"),
                ("run_lb_rebalance" in content, "run_lb_rebalance 函数"),
                ("LongPort" in content, "LongPort 相关代码")
            ]
            
            for check, description in checks:
                if check:
                    print(f"✓ {description} 已添加")
                else:
                    print(f"✗ {description} 未找到")
        else:
            print("✗ CLI文件不存在")
            
    except Exception as e:
        print(f"✗ 检查CLI结构时出错: {e}")
    print()

def test_pyproject_dependency():
    """Test that longbridge dependency is in pyproject.toml."""
    print("=== 测试依赖配置 ===")
    
    try:
        pyproject_file = Path("pyproject.toml")
        if pyproject_file.exists():
            content = pyproject_file.read_text(encoding='utf-8')
            
            if "longbridge>=0.2.77" in content:
                print("✓ longbridge 依赖已配置")
            else:
                print("✗ longbridge 依赖未找到")
        else:
            print("✗ pyproject.toml 文件不存在")
            
    except Exception as e:
        print(f"✗ 检查依赖配置时出错: {e}")
    print()

def test_symbol_conversion_logic():
    """Test symbol conversion logic without importing the module."""
    print("=== 测试符号转换逻辑 ===")
    
    # 直接实现转换逻辑进行测试
    def _to_lb_symbol(ticker: str) -> str:
        t = ticker.strip().upper()
        if t.endswith((".US", ".HK", ".SG")):
            return t
        return f"{t}.US"
    
    test_cases = [
        ("AAPL", "AAPL.US"),
        ("MSFT", "MSFT.US"), 
        ("700.HK", "700.HK"),
        ("TSLA.US", "TSLA.US"),
        ("aapl", "AAPL.US"),
        ("  GOOGL  ", "GOOGL.US")
    ]
    
    all_passed = True
    for input_ticker, expected in test_cases:
        result = _to_lb_symbol(input_ticker)
        if result == expected:
            print(f"✓ {input_ticker:12} -> {result}")
        else:
            print(f"✗ {input_ticker:12} -> {result} (期望: {expected})")
            all_passed = False
    
    if all_passed:
        print("✓ 所有符号转换测试通过")
    else:
        print("✗ 部分符号转换测试失败")
    print()

def main():
    """Run all tests."""
    print("LongPort 集成结构测试")
    print("=" * 50)
    
    test_file_structure()
    test_cli_structure()
    test_pyproject_dependency()
    test_symbol_conversion_logic()
    
    print("结构测试完成！")
    print("\n下一步：")
    print("1. 安装 longbridge 包: pip install longbridge")
    print("2. 在 .env 文件中配置 LongPort API 凭据:")
    print("   LONGPORT_APP_KEY=...")
    print("   LONGPORT_APP_SECRET=...")
    print("   LONGPORT_ACCESS_TOKEN=...")
    print("3. 使用 'stockq lb-quote AAPL MSFT' 测试实时报价")
    print("4. 使用 'stockq lb-rebalance file.xlsx' 测试仓位调整")

if __name__ == "__main__":
    main()