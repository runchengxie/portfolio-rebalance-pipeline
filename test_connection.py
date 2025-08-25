from stock_analysis.broker.longport_client import LongPortClient
c = LongPortClient(env="test")
print("asset:", getattr(c.trade, "asset", None) and c.trade.asset())
print("positions:", getattr(c.trade, "position_list", None) and c.trade.position_list())
c.close()