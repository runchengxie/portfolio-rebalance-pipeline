from unittest.mock import patch

from stock_analysis.services import account_snapshot


def test_get_multiple_account_snapshots():
    with patch(
        "stock_analysis.services.account_snapshot.get_account_snapshot"
    ) as mock_get:
        mock_get.side_effect = ["snap1", "snap2"]
        snaps = account_snapshot.get_multiple_account_snapshots(["env1", "env2"])
        assert snaps == ["snap1", "snap2"]
        mock_get.assert_any_call(env="env1")
        mock_get.assert_any_call(env="env2")
