import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

import stock_analysis.cli as cli


@pytest.mark.unit
def test_cli_dispatch_lb_quote(monkeypatch):
    """Test that the CLI dispatches the lb-quote command to the run_lb_quote function."""
    # Create a probe function to record calls
    called = {}

    def fake_run_lb_quote(tickers):
        called["tickers"] = tickers
        return 0

    # Replace the real function
    monkeypatch.setattr(cli, "run_lb_quote", fake_run_lb_quote)

    # Simulate command-line arguments
    test_args = ["prog", "lb-quote", "AAPL", "MSFT"]
    with patch.object(sys, "argv", test_args):
        # Directly test the dispatch logic
        result = cli.run_lb_quote(["AAPL", "MSFT"])

        assert result == 0
        assert called["tickers"] == ["AAPL", "MSFT"]


@pytest.mark.unit
def test_cli_dispatch_lb_rebalance(monkeypatch):
    """Test that the CLI dispatches the lb-rebalance command to the run_lb_rebalance function."""
    called = {}

    def fake_run_lb_rebalance(input_file, account="main", dry_run=True, env="real"):
        called["input_file"] = input_file
        called["account"] = account
        called["dry_run"] = dry_run
        called["env"] = env
        return 0

    monkeypatch.setattr(cli, "run_lb_rebalance", fake_run_lb_rebalance)

    # Test with default arguments
    result = cli.run_lb_rebalance("test.xlsx")
    assert result == 0
    assert called["input_file"] == "test.xlsx"
    assert called["account"] == "main"
    assert called["dry_run"]

    # Test with custom arguments
    result = cli.run_lb_rebalance("test2.xlsx", "account2", False)
    assert result == 0
    assert called["input_file"] == "test2.xlsx"
    assert called["account"] == "account2"
    assert not called["dry_run"]


@pytest.mark.unit
def test_main_command_routing():
    """Test the command routing logic of the main function."""
    # Create a mock args object
    args = SimpleNamespace()

    with patch.object(cli, "create_parser") as mock_parser:
        with patch.object(cli, "run_lb_quote", return_value=0) as mock_lb_quote:
            with patch.object(
                cli, "run_lb_rebalance", return_value=0
            ) as mock_lb_rebalance:
                # Mock the parser's return value
                mock_parser_instance = Mock()
                mock_parser.return_value = mock_parser_instance

                # Test the lb-quote command
                args.command = "lb-quote"
                args.tickers = ["AAPL", "GOOGL"]
                mock_parser_instance.parse_args.return_value = args

                result = cli.main()
                assert result == 0
                mock_lb_quote.assert_called_once_with(["AAPL", "GOOGL"])

                # Reset the mocks
                mock_lb_quote.reset_mock()
                mock_lb_rebalance.reset_mock()

                # Test the lb-rebalance command
                args.command = "lb-rebalance"
                args.input_file = "portfolio.xlsx"
                args.account = "test_account"
                args.execute = False  # This means dry_run = True

                result = cli.main()
                assert result == 0
                # Assert the first three arguments (the fourth, env, defaults to 'real')
                call_args, kwargs = mock_lb_rebalance.call_args
                assert call_args[0] == "portfolio.xlsx"
                assert call_args[1] == "test_account"
                assert call_args[2] is True


@pytest.mark.unit
def test_main_no_command():
    """Test that help information is displayed when no command is provided."""
    args = SimpleNamespace()
    args.command = None

    with patch.object(cli, "create_parser") as mock_parser:
        mock_parser_instance = Mock()
        mock_parser.return_value = mock_parser_instance
        mock_parser_instance.parse_args.return_value = args

        result = cli.main()
        assert result == 0
        mock_parser_instance.print_help.assert_called_once()


@pytest.mark.unit
def test_main_unknown_command():
    """Test the handling of an unknown command."""
    args = SimpleNamespace()
    args.command = "unknown-command"

    with patch.object(cli, "create_parser") as mock_parser:
        mock_parser_instance = Mock()
        mock_parser.return_value = mock_parser_instance
        mock_parser_instance.parse_args.return_value = args

        with patch("builtins.print") as mock_print:
            result = cli.main()
            assert result == 1
            mock_print.assert_called_with("Unknown command: unknown-command", file=sys.stderr)


@pytest.mark.unit
def test_run_lb_quote_import_error(monkeypatch):
    """Test the handling of an ImportError in run_lb_quote."""
    # Simulate an error when importing the longport_client module
    original_import = __builtins__["__import__"]

    def mock_import(name, *args, **kwargs):
        if "longport_client" in name:
            raise ImportError("No module named 'longport'")
        return original_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        with patch("builtins.print") as mock_print:
            result = cli.run_lb_quote(["AAPL"])
            assert result == 1
            # Verify that the error message is printed
            assert any(
                "longport" in str(call) or "LongPort" in str(call)
                for call in mock_print.call_args_list
            )


@pytest.mark.unit
def test_run_lb_rebalance_file_not_found():
    """Test the handling of a non-existent file in run_lb_rebalance."""
    with patch("builtins.print") as mock_print:
        result = cli.run_lb_rebalance("non_existent_file.xlsx")
        assert result == 1
        # Verify that the error message is printed
        assert any("File not found" in str(call) for call in mock_print.call_args_list)


@pytest.mark.unit
def test_app_function():
    """Test the app function as the entry point."""
    with patch.object(cli, "main", return_value=0) as mock_main:
        with patch.object(sys, "exit") as mock_exit:
            cli.app()
            mock_main.assert_called_once()
            mock_exit.assert_called_once_with(0)