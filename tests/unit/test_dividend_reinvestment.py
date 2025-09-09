import datetime
import pandas as pd
import pandas.testing as pdt

from stock_analysis.backtest.prep import DividendPandasData
from stock_analysis.backtest.engine import run_quarterly_backtest


def test_dividend_reinvestment():
    index = pd.to_datetime(["2022-01-03", "2022-01-04", "2022-01-05"])
    price = pd.DataFrame(
        {
            "Open": [100, 100, 100],
            "High": [100, 100, 100],
            "Low": [100, 100, 100],
            "Close": [100, 100, 100],
            "Volume": [1000, 1000, 1000],
            "Dividend": [0.0, 1.0, 0.0],
        },
        index=index,
    )

    feed = DividendPandasData(dataname=price, openinterest=None, name="TEST")
    portfolios = {datetime.date(2022, 1, 3): pd.DataFrame({"Ticker": ["TEST"]})}

    portfolio_value, _ = run_quarterly_backtest(
        portfolios,
        {"TEST": feed},
        initial_cash=100,
        start_date=datetime.date(2022, 1, 3),
        end_date=datetime.date(2022, 1, 5),
        use_logging=False,
    )

    expected_index = pd.to_datetime(
        ["2022-01-02", "2022-01-03", "2022-01-04", "2022-01-05"]
    )
    expected = pd.Series([100.0, 100.0, 100.0, 101.0], index=expected_index)

    pdt.assert_series_equal(portfolio_value, expected)
