"""LongPort账户概览输出（REAL-only）测试

更新为 real-only 模式：
- lb-account 不再接受 --env 参数
- 默认展示真实账户数据；预览/执行逻辑在其他命令
本测试通过 patch get_account_snapshot 返回构造的快照，验证渲染输出。
"""

import json
from unittest.mock import patch

import pytest

from stock_analysis import cli
from stock_analysis.models import AccountSnapshot, Position


def make_snapshot(
    cash: float, positions: list[tuple[str, int, float]]
) -> AccountSnapshot:
    pos = [
        Position(symbol=s, quantity=q, last_price=p, estimated_value=q * p, env="real")
        for s, q, p in positions
    ]
    return AccountSnapshot(env="real", cash_usd=cash, positions=pos)


@pytest.mark.unit
class TestLBAccountTableOutput:
    def test_lb_account_prints_positions_table(self, capsys):
        snap = make_snapshot(1234.56, [("AAPL.US", 10, 199.99)])
        with patch(
            "stock_analysis.commands.lb_account.get_account_snapshot",
            return_value=snap,
        ):
            assert (
                cli.run_lb_account(only_funds=False, only_positions=False, fmt="table")
                == 0
            )

        out = capsys.readouterr().out
        assert "现金" in out and "持仓" in out and "AAPL.US" in out

    def test_table_output_with_funds_and_positions(self, capsys):
        snap = make_snapshot(5000.0, [("AAPL.US", 10, 150.0), ("MSFT.US", 5, 300.0)])
        with patch(
            "stock_analysis.commands.lb_account.get_account_snapshot",
            return_value=snap,
        ):
            result = cli.run_lb_account(
                only_funds=False, only_positions=False, fmt="table"
            )

        assert result == 0
        out = capsys.readouterr().out
        assert "现金(USD): $5,000.00" in out
        assert "AAPL.US" in out and "MSFT.US" in out
        assert "150.00" in out and "300.00" in out

    def test_table_output_only_funds(self, capsys):
        snap = make_snapshot(2500.75, [("AAPL.US", 10, 150.0)])
        with patch(
            "stock_analysis.commands.lb_account.get_account_snapshot",
            return_value=snap,
        ):
            result = cli.run_lb_account(
                only_funds=True, only_positions=False, fmt="table"
            )

        assert result == 0
        out = capsys.readouterr().out
        assert "现金(USD): $2,500.75" in out
        assert "Symbol" not in out and "AAPL.US" not in out

    def test_table_output_only_positions(self, capsys):
        snap = make_snapshot(1000.0, [("GOOGL.US", 2, 2500.0), ("AMZN.US", 1, 3000.0)])
        with patch(
            "stock_analysis.commands.lb_account.get_account_snapshot",
            return_value=snap,
        ):
            result = cli.run_lb_account(
                only_funds=False, only_positions=True, fmt="table"
            )

        assert result == 0
        out = capsys.readouterr().out
        assert "现金(USD)" not in out
        assert "GOOGL.US" in out and "AMZN.US" in out
        assert "2500.00" in out and "3000.00" in out

    def test_table_output_no_positions(self, capsys):
        snap = make_snapshot(1000.0, [])
        with patch(
            "stock_analysis.commands.lb_account.get_account_snapshot",
            return_value=snap,
        ):
            result = cli.run_lb_account(
                only_funds=False, only_positions=False, fmt="table"
            )

        assert result == 0
        out = capsys.readouterr().out
        assert "无持仓" in out


@pytest.mark.unit
class TestLBAccountJsonOutput:
    def test_json_output_single_env(self, capsys):
        snap = make_snapshot(1500.5, [("AAPL.US", 10, 150.05)])
        with patch(
            "stock_analysis.commands.lb_account.get_account_snapshot",
            return_value=snap,
        ):
            result = cli.run_lb_account(fmt="json")

        assert result == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, list) and len(data) == 1
        assert data[0]["env"] == "real"
        assert data[0]["cash_usd"] == 1500.5
        assert data[0]["positions"][0]["symbol"] == "AAPL.US"


@pytest.mark.unit
class TestLBAccountErrorHandling:
    def test_import_error_handling(self, capsys):
        with patch(
            "builtins.__import__", side_effect=ImportError("No module named 'longport'")
        ):
            result = cli.run_lb_account()

        assert result == 1
        err = capsys.readouterr().err
        assert "无法导入LongPort模块" in err
        assert "pip install longport" in err

    def test_client_connection_error(self, capsys):
        with patch(
            "stock_analysis.commands.lb_account.get_account_snapshot",
            side_effect=Exception("Connection failed"),
        ):
            result = cli.run_lb_account(fmt="table")

        assert result == 1
        err = capsys.readouterr().err
        assert "账户总览失败" in err

    def test_portfolio_snapshot_error_no_fallback(self, capsys):
        with patch(
            "stock_analysis.commands.lb_account.get_account_snapshot",
            side_effect=Exception("API Error"),
        ):
            result = cli.run_lb_account(fmt="json")

        assert result == 1
        captured = capsys.readouterr()
        assert "账户总览失败" in captured.err


@pytest.mark.unit
class TestLBAccountParameterValidation:
    def test_format_parameter_validation(self, capsys):
        snap = make_snapshot(1000.0, [])
        with patch(
            "stock_analysis.commands.lb_account.get_account_snapshot",
            return_value=snap,
        ):
            result = cli.run_lb_account(fmt="xml")

        assert result == 0
        out = capsys.readouterr().out
        assert "现金(USD)" in out
        assert "{" not in out

    def test_conflicting_flags(self, capsys):
        snap = make_snapshot(1000.0, [("AAPL.US", 10, 150.0)])
        with patch(
            "stock_analysis.commands.lb_account.get_account_snapshot",
            return_value=snap,
        ):
            result = cli.run_lb_account(
                only_funds=True, only_positions=True, fmt="table"
            )

        assert result == 0
        out = capsys.readouterr().out
        assert "现金(USD)" in out
        assert "Symbol" not in out
        assert "AAPL.US" not in out
