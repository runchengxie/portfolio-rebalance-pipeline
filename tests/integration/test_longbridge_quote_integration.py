import pytest
import os
from datetime import date, timedelta

# 尝试导入longport，如果失败则跳过所有测试
longport = pytest.importorskip("longport")

from stock_analysis.broker.longport_client import LongPortClient, get_config


def check_longport_credentials():
    """检查LongPort API凭据是否配置。"""
    required_vars = ["LONGPORT_APP_KEY", "LONGPORT_APP_SECRET", "LONGPORT_ACCESS_TOKEN"]
    return all(os.getenv(var) for var in required_vars)


@pytest.mark.integration
@pytest.mark.skipif(
    not check_longport_credentials(),
    reason="LongPort API凭据未配置，跳过集成测试"
)
def test_get_config_from_env():
    """测试从环境变量获取LongPort配置。"""
    config = get_config()
    assert config is not None
    # 不直接检查凭据内容，只验证配置对象创建成功


@pytest.mark.integration
@pytest.mark.skipif(
    not check_longport_credentials(),
    reason="LongPort API凭据未配置，跳过集成测试"
)
def test_longport_client_initialization():
    """测试LongPortClient初始化。"""
    try:
        client = LongPortClient()
        assert client.cfg is not None
        assert client.q is not None
        assert client.t is not None
    except Exception as e:
        pytest.fail(f"LongPortClient初始化失败: {e}")


@pytest.mark.integration
@pytest.mark.skipif(
    not check_longport_credentials(),
    reason="LongPort API凭据未配置，跳过集成测试"
)
def test_quote_last_real_api():
    """测试真实API获取股票报价。
    
    注意：这个测试会调用真实的LongPort API，
    需要有效的API凭据和网络连接。
    """
    client = LongPortClient()
    
    # 使用常见的美股股票进行测试
    test_tickers = ["AAPL", "MSFT"]
    
    try:
        quotes = client.quote_last(test_tickers)
        
        # 验证返回结果的结构
        assert isinstance(quotes, dict)
        assert len(quotes) <= len(test_tickers)  # 可能有些股票不在交易时间
        
        for symbol, (price, timestamp) in quotes.items():
            # 验证数据类型和合理性
            assert isinstance(symbol, str)
            assert symbol.endswith((".US", ".HK", ".SG"))
            assert isinstance(price, (int, float))
            assert price > 0  # 股价应该为正数
            assert isinstance(timestamp, int)
            assert timestamp > 0  # 时间戳应该为正数
            
    except Exception as e:
        # 如果是网络错误或API限制，给出更友好的错误信息
        if "network" in str(e).lower() or "timeout" in str(e).lower():
            pytest.skip(f"网络连接问题，跳过测试: {e}")
        elif "rate limit" in str(e).lower() or "quota" in str(e).lower():
            pytest.skip(f"API限制，跳过测试: {e}")
        else:
            pytest.fail(f"获取报价失败: {e}")


@pytest.mark.integration
@pytest.mark.skipif(
    not check_longport_credentials(),
    reason="LongPort API凭据未配置，跳过集成测试"
)
def test_candles_real_api():
    """测试真实API获取历史K线数据。
    
    注意：这个测试会调用真实的LongPort API。
    """
    client = LongPortClient()
    
    # 获取最近30天的数据
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    
    try:
        candles = client.candles("AAPL", start_date, end_date)
        
        # 验证返回结果
        assert candles is not None
        # 具体的数据结构验证取决于longport库的返回格式
        # 这里只做基本的非空检查
        
    except Exception as e:
        if "network" in str(e).lower() or "timeout" in str(e).lower():
            pytest.skip(f"网络连接问题，跳过测试: {e}")
        elif "rate limit" in str(e).lower() or "quota" in str(e).lower():
            pytest.skip(f"API限制，跳过测试: {e}")
        elif "market closed" in str(e).lower() or "no data" in str(e).lower():
            pytest.skip(f"市场关闭或无数据，跳过测试: {e}")
        else:
            pytest.fail(f"获取K线数据失败: {e}")


@pytest.mark.integration
@pytest.mark.skipif(
    not check_longport_credentials(),
    reason="LongPort API凭据未配置，跳过集成测试"
)
def test_symbol_conversion_integration():
    """测试符号转换在真实API调用中的表现。"""
    client = LongPortClient()
    
    # 测试不同格式的股票代码
    test_cases = [
        "AAPL",      # 应该转换为 AAPL.US
        "MSFT.US",   # 应该保持不变
        "700.HK",    # 应该保持不变（如果有权限）
    ]
    
    for ticker in test_cases:
        try:
            quotes = client.quote_last([ticker])
            # 如果成功获取数据，验证返回的symbol格式
            for symbol in quotes.keys():
                assert symbol.endswith((".US", ".HK", ".SG")), f"符号格式不正确: {symbol}"
                
        except Exception as e:
            # 某些市场可能没有权限或不在交易时间，这是正常的
            if "permission" in str(e).lower() or "access" in str(e).lower():
                pytest.skip(f"无权限访问 {ticker}，跳过: {e}")
            elif "not found" in str(e).lower() or "invalid" in str(e).lower():
                pytest.skip(f"股票代码 {ticker} 无效或未找到，跳过: {e}")
            else:
                # 其他错误可能需要关注
                pytest.fail(f"测试 {ticker} 时出错: {e}")


@pytest.mark.integration
@pytest.mark.skipif(
    not check_longport_credentials(),
    reason="LongPort API凭据未配置，跳过集成测试"
)
def test_api_error_handling():
    """测试API错误处理。"""
    client = LongPortClient()
    
    # 测试无效的股票代码
    invalid_tickers = ["INVALID_TICKER_12345"]
    
    try:
        quotes = client.quote_last(invalid_tickers)
        # 如果没有抛出异常，检查返回结果是否为空或包含错误信息
        assert isinstance(quotes, dict)
        
    except Exception as e:
        # 预期会有错误，这是正常的
        assert "invalid" in str(e).lower() or "not found" in str(e).lower() or "error" in str(e).lower()


# 注意：submit_limit方法涉及真实交易，不在集成测试中测试
# 真实交易测试应该在专门的交易测试环境中进行，而不是在CI/CD中