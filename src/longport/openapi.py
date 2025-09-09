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
