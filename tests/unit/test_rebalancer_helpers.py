import types
from decimal import Decimal
from unittest.mock import patch

import pytest
from stock_analysis.models import AccountSnapshot, Position, Quote
from stock_analysis.services.rebalancer import FeeSchedule, RebalanceService


def make_snapshot():
    pos = Position(symbol="AAA.US", quantity=1, last_price=10.0, estimated_value=10.0)
    return AccountSnapshot(env="test", cash_usd=100.0, positions=[pos])


def test_fetch_quotes():
    svc = RebalanceService()
    with (
        patch("stock_analysis.services.rebalancer.get_quotes") as mock_get,
        patch.object(RebalanceService, "_get_client", return_value=object()),
    ):
        mock_get.return_value = {
            "AAA.US": Quote(symbol="AAA.US", price=10.0, timestamp="")
        }
        quotes = svc._fetch_quotes(["AAA"])
        assert quotes == {"AAA.US": 10.0}
        mock_get.assert_called_once()


def test_compute_effective_total():
    svc = RebalanceService()
    snapshot = make_snapshot()
    quotes = {"AAA.US": 10.0}
    eff = svc._compute_effective_total(snapshot, quotes, 1.0)
    assert eff == pytest.approx(110.0)


def test_build_order():
    svc = RebalanceService()
    client = types.SimpleNamespace(lot_size=lambda s: 1)
    fs = FeeSchedule(0, 0, 0, 0, 0)
    position, order = svc._build_order(
        "AAA.US", 10.0, 0, 100.0, False, client, fs, True, Decimal("0.001")
    )
    assert position.quantity == 10
    assert order is not None
    assert order.quantity == 10
    assert order.side == "BUY"
