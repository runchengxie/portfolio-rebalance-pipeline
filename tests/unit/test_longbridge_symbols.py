import pytest

from stock_analysis.broker.longport_client import _to_lb_symbol


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw,expect",
    [
        ("AAPL", "AAPL.US"),
        ("MSFT", "MSFT.US"),
        ("700.HK", "700.HK"),
        ("TSLA.US", "TSLA.US"),
        ("aapl", "AAPL.US"),
        ("  GOOGL  ", "GOOGL.US"),
        ("BABA.HK", "BABA.HK"),
        ("SE.SG", "SE.SG"),
        ("nvda", "NVDA.US"),
        ("\tAMZN\n", "AMZN.US"),  # 测试各种空白字符
    ],
)
def test_to_lb_symbol(raw, expect):
    """测试股票代码转换为LongPort格式的函数。

    测试规则：
    - 默认补全 .US 后缀
    - 已有 .US/.HK/.SG 后缀的保持不变
    - 自动转换为大写
    - 去除前后空白字符
    """
    assert _to_lb_symbol(raw) == expect


@pytest.mark.unit
def test_to_lb_symbol_edge_cases():
    """测试边界情况。"""
    # 空字符串应该返回 .US
    assert _to_lb_symbol("") == ".US"

    # 只有空格的字符串
    assert _to_lb_symbol("   ") == ".US"

    # 测试混合大小写
    assert _to_lb_symbol("TsLa.us") == "TSLA.US"
    assert _to_lb_symbol("baba.hk") == "BABA.HK"
    assert _to_lb_symbol("se.sg") == "SE.SG"
