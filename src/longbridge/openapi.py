class Config:
    @staticmethod
    def from_env():
        return Config()

class Market:
    US = 'US'
    HK = 'HK'
    CN = 'CN'
    SG = 'SG'

class QuoteContext:
    def __init__(self, config):
        pass

class TradeContext:
    def __init__(self, config):
        pass


# Simple enum stubs to satisfy imports in tests. They mimic the
# interfaces provided by the real ``longbridge`` package but contain only
# the attributes exercised by the unit tests.
class OrderSide:
    Buy = "Buy"
    Sell = "Sell"


class OrderType:
    LO = "LO"


class TimeInForceType:
    Day = "Day"
    GTC = "GTC"
