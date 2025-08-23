import pytest
from decimal import Decimal
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

from stock_analysis.broker.longport_client import LongPortClient


@pytest.mark.unit
def test_quote_last_mapping():
    """测试quote_last方法的数据映射逻辑。"""
    # 创建假的响应数据
    fake_resp = [
        SimpleNamespace(symbol="AAPL.US", last_done=189.5, timestamp=1234567890),
        SimpleNamespace(symbol="MSFT.US", last_done=350.2, timestamp=1234567891)
    ]
    
    # 创建mock的QuoteContext
    mock_quote_context = Mock()
    mock_quote_context.quote.return_value = fake_resp
    
    # 创建客户端实例并替换QuoteContext
    with patch('stock_analysis.broker.longport_client.get_config'):
        client = LongPortClient.__new__(LongPortClient)
        client.q = mock_quote_context
        client.t = Mock()  # TradeContext也需要mock
        
        # 测试方法调用
        result = client.quote_last(["AAPL", "MSFT"])
        
        # 验证调用参数
        mock_quote_context.quote.assert_called_once_with(["AAPL.US", "MSFT.US"])
        
        # 验证返回结果
        assert result == {
            "AAPL.US": (189.5, 1234567890),
            "MSFT.US": (350.2, 1234567891)
        }


@pytest.mark.unit
def test_candles_parameters():
    """测试candles方法的参数传递。"""
    mock_quote_context = Mock()
    mock_quote_context.history_candlesticks_by_date.return_value = []
    
    with patch('stock_analysis.broker.longport_client.get_config'):
        client = LongPortClient.__new__(LongPortClient)
        client.q = mock_quote_context
        client.t = Mock()
        
        start_date = date(2023, 1, 1)
        end_date = date(2023, 12, 31)
        custom_period = Mock()
        
        # 测试方法调用 - 重点是验证_to_lb_symbol被正确调用和参数传递
        client.candles("AAPL", start_date, end_date, custom_period)
        
        # 验证history_candlesticks_by_date被调用，第一个参数应该是转换后的符号
        mock_quote_context.history_candlesticks_by_date.assert_called_once()
        call_args = mock_quote_context.history_candlesticks_by_date.call_args
        
        # 验证第一个参数是转换后的符号
        assert call_args[0][0] == "AAPL.US"
        # 验证日期参数
        assert call_args[0][3] == start_date
        assert call_args[0][4] == end_date
        # 验证period参数
        assert call_args[0][1] == custom_period


@pytest.mark.unit
def test_submit_limit_buy_order():
    """测试提交买入限价单。"""
    from longbridge.openapi import OrderType, OrderSide, TimeInForceType
    
    mock_trade_context = Mock()
    mock_trade_context.submit_order.return_value = SimpleNamespace(order_id="12345")
    
    with patch('stock_analysis.broker.longport_client.get_config'):
        client = LongPortClient.__new__(LongPortClient)
        client.q = Mock()
        client.t = mock_trade_context
        
        # 测试买入订单（正数量）
        result = client.submit_limit("AAPL", 150.0, 100)
        
        mock_trade_context.submit_order.assert_called_with(
            symbol="AAPL.US",
            order_type=OrderType.LO,
            side=OrderSide.Buy,
            submitted_price=Decimal('150.0'),
            submitted_quantity=Decimal('100'),
            time_in_force=TimeInForceType.Day,
            remark=None
        )
        
        assert result.order_id == "12345"


@pytest.mark.unit
def test_submit_limit_sell_order():
    """测试提交卖出限价单。"""
    from longbridge.openapi import OrderType, OrderSide, TimeInForceType
    
    mock_trade_context = Mock()
    mock_trade_context.submit_order.return_value = SimpleNamespace(order_id="67890")
    
    with patch('stock_analysis.broker.longport_client.get_config'):
        client = LongPortClient.__new__(LongPortClient)
        client.q = Mock()
        client.t = mock_trade_context
        
        # 测试卖出订单（负数量）
        result = client.submit_limit("MSFT", 300.0, -50, remark="test sell")
        
        mock_trade_context.submit_order.assert_called_with(
            symbol="MSFT.US",
            order_type=OrderType.LO,
            side=OrderSide.Sell,
            submitted_price=Decimal('300.0'),
            submitted_quantity=Decimal('50'),  # 绝对值
            time_in_force=TimeInForceType.Day,
            remark="test sell"
        )
        
        assert result.order_id == "67890"


@pytest.mark.unit
def test_submit_limit_with_custom_tif():
    """测试自定义时效的限价单。"""
    # 使用mock对象避免导入longbridge枚举
    mock_order_type = Mock()
    mock_order_side = Mock()
    mock_tif_gtc = Mock()
    
    mock_trade_context = Mock()
    mock_trade_context.submit_order.return_value = SimpleNamespace(order_id="11111")
    
    with patch('stock_analysis.broker.longport_client.get_config'):
        with patch('stock_analysis.broker.longport_client.OrderType') as mock_ot:
            with patch('stock_analysis.broker.longport_client.OrderSide') as mock_os:
                with patch('stock_analysis.broker.longport_client.TimeInForceType') as mock_tif:
                    mock_ot.LO = mock_order_type
                    mock_os.Buy = mock_order_side
                    mock_tif.GTC = mock_tif_gtc
                    
                    client = LongPortClient.__new__(LongPortClient)
                    client.q = Mock()
                    client.t = mock_trade_context
                    
                    # 测试GTC订单
                    client.submit_limit("GOOGL", 2500.0, 10, mock_tif_gtc)
                    
                    mock_trade_context.submit_order.assert_called_with(
                        symbol="GOOGL.US",
                        order_type=mock_order_type,
                        side=mock_order_side,
                        submitted_price=Decimal('2500.0'),
                        submitted_quantity=Decimal('10'),
                        time_in_force=mock_tif_gtc,
                        remark=None
                    )


@pytest.mark.unit
def test_decimal_precision():
    """测试价格和数量的Decimal精度处理。"""
    from longbridge.openapi import OrderType, OrderSide, TimeInForceType
    
    mock_trade_context = Mock()
    mock_trade_context.submit_order.return_value = SimpleNamespace(order_id="22222")
    
    with patch('stock_analysis.broker.longport_client.get_config'):
        client = LongPortClient.__new__(LongPortClient)
        client.q = Mock()
        client.t = mock_trade_context
        
        # 测试浮点数精度
        client.submit_limit("TSLA", 199.99, 25)
        
        # 验证Decimal转换
        call_args = mock_trade_context.submit_order.call_args
        assert call_args.kwargs['submitted_price'] == Decimal('199.99')
        assert call_args.kwargs['submitted_quantity'] == Decimal('25')
        assert isinstance(call_args.kwargs['submitted_price'], Decimal)
        assert isinstance(call_args.kwargs['submitted_quantity'], Decimal)