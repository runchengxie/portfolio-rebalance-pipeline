"""Smoke test for report generation.

This module tests the backtest report generation functionality, covering:
- Creation and saving of PNG files.
- File size validation (non-zero size).
- Basic functionality of chart generation.
- Handling of error conditions.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from stock_analysis.backtest.engine import generate_report


@pytest.mark.unit
class TestReportGeneration:
    """Tests the basic functionality of report generation."""

    def test_generate_report_creates_png_file(self, tmp_path):
        """Tests that generate_report creates a PNG file."""
        # Prepare test data
        output_png = tmp_path / "test_report.png"

        # Create a mock portfolio value series
        dates = pd.date_range("2023-01-01", periods=10, freq="D")
        portfolio_value = pd.Series([10000 + i * 100 for i in range(10)], index=dates)

        # Create a mock metrics dictionary
        metrics = {
            "start_date": dates[0].date(),
            "end_date": dates[-1].date(),
            "initial_value": 10000.0,
            "final_value": 10900.0,
            "total_return": 0.09,
            "annualized_return": 0.12,
            "max_drawdown": 0.05,
        }

        # Mock matplotlib's savefig method
        with patch("matplotlib.pyplot.savefig") as mock_savefig:
            with patch("matplotlib.pyplot.show"):
                with patch("matplotlib.pyplot.style.use"):
                    with patch("matplotlib.pyplot.subplots") as mock_subplots:
                        # Create mock figure and axes
                        mock_fig = Mock()
                        mock_ax = Mock()
                        mock_subplots.return_value = (mock_fig, mock_ax)

                        # Mock the plot method of the pandas Series
                        mock_ax.yaxis.set_major_formatter = Mock()
                        mock_ax.set_title = Mock()
                        mock_ax.set_xlabel = Mock()
                        mock_ax.set_ylabel = Mock()
                        mock_ax.legend = Mock()
                        mock_ax.grid = Mock()

                        with patch.object(portfolio_value, "plot", return_value=None):
                            with patch("matplotlib.pyplot.tight_layout"):
                                generate_report(
                                    metrics=metrics,
                                    title="Test Report",
                                    portfolio_value=portfolio_value,
                                    output_png=output_png,
                                )

                        # Verify that savefig was called
                        mock_savefig.assert_called_once_with(
                            output_png, dpi=300, bbox_inches="tight"
                        )

    def test_generate_report_with_benchmark(self, tmp_path):
        """Tests report generation with a benchmark comparison."""
        output_png = tmp_path / "benchmark_report.png"

        # Create portfolio and benchmark data
        dates = pd.date_range("2023-01-01", periods=5, freq="D")
        portfolio_value = pd.Series([10000, 10100, 10200, 10150, 10300], index=dates)
        benchmark_value = pd.Series([10000, 10050, 10100, 10080, 10120], index=dates)

        metrics = {
            "start_date": dates[0].date(),
            "end_date": dates[-1].date(),
            "initial_value": 10000.0,
            "final_value": 10300.0,
            "total_return": 0.03,
            "annualized_return": 0.15,
            "max_drawdown": 0.02,
        }

        with patch("matplotlib.pyplot.savefig") as mock_savefig:
            with patch("matplotlib.pyplot.show"):
                with patch("matplotlib.pyplot.style.use"):
                    with patch("matplotlib.pyplot.subplots") as mock_subplots:
                        mock_fig = Mock()
                        mock_ax = Mock()
                        mock_subplots.return_value = (mock_fig, mock_ax)

                        # Mock all necessary methods
                        mock_ax.yaxis.set_major_formatter = Mock()
                        mock_ax.set_title = Mock()
                        mock_ax.set_xlabel = Mock()
                        mock_ax.set_ylabel = Mock()
                        mock_ax.legend = Mock()
                        mock_ax.grid = Mock()

                        with patch.object(portfolio_value, "plot", return_value=None):
                            with patch.object(
                                benchmark_value, "plot", return_value=None
                            ):
                                with patch("matplotlib.pyplot.tight_layout"):
                                    generate_report(
                                        metrics=metrics,
                                        title="Portfolio vs Benchmark",
                                        portfolio_value=portfolio_value,
                                        output_png=output_png,
                                        benchmark_value=benchmark_value,
                                        benchmark_label="SPY",
                                    )

                        # Verify that savefig was called
                        mock_savefig.assert_called_once()

    def test_generate_report_without_png_output(self, capsys):
        """Tests report generation without saving a PNG file."""
        dates = pd.date_range("2023-01-01", periods=3, freq="D")
        portfolio_value = pd.Series([10000, 10100, 10200], index=dates)

        metrics = {
            "start_date": dates[0].date(),
            "end_date": dates[-1].date(),
            "initial_value": 10000.0,
            "final_value": 10200.0,
            "total_return": 0.02,
            "annualized_return": 0.08,
            "max_drawdown": 0.01,
        }

        with patch("matplotlib.pyplot.savefig") as mock_savefig:
            with patch("matplotlib.pyplot.show"):
                with patch("matplotlib.pyplot.style.use"):
                    with patch("matplotlib.pyplot.subplots") as mock_subplots:
                        mock_fig = Mock()
                        mock_ax = Mock()
                        mock_subplots.return_value = (mock_fig, mock_ax)

                        mock_ax.yaxis.set_major_formatter = Mock()
                        mock_ax.set_title = Mock()
                        mock_ax.set_xlabel = Mock()
                        mock_ax.set_ylabel = Mock()
                        mock_ax.legend = Mock()
                        mock_ax.grid = Mock()

                        with patch.object(portfolio_value, "plot", return_value=None):
                            with patch("matplotlib.pyplot.tight_layout"):
                                generate_report(
                                    metrics=metrics,
                                    title="No PNG Test",
                                    portfolio_value=portfolio_value,
                                    output_png=None,  # Do not save a PNG file
                                )

                        # Verify that savefig was not called
                        mock_savefig.assert_not_called()

        # Verify that the text report was printed to stdout
        captured = capsys.readouterr()
        assert "No PNG Test" in captured.out
        assert "Total Return:" in captured.out
        assert "Annualized Return:" in captured.out


@pytest.mark.unit
class TestReportGenerationRealFiles:
    """Tests actual file generation (using the real matplotlib)."""

    @pytest.mark.integration  # Mark as an integration test because it involves real file I/O
    def test_actual_png_file_creation(self, tmp_path):
        """Tests the actual creation and size validation of a PNG file."""
        output_png = tmp_path / "actual_test.png"

        # Create simple test data
        dates = pd.date_range("2023-01-01", periods=5, freq="D")
        portfolio_value = pd.Series([10000, 10100, 10050, 10150, 10200], index=dates)

        metrics = {
            "start_date": dates[0].date(),
            "end_date": dates[-1].date(),
            "initial_value": 10000.0,
            "final_value": 10200.0,
            "total_return": 0.02,
            "annualized_return": 0.08,
            "max_drawdown": 0.025,
        }

        # Use the real matplotlib, but don't show the plot
        with patch("matplotlib.pyplot.show"):  # Prevent the plot from being displayed
            generate_report(
                metrics=metrics,
                title="Actual File Test",
                portfolio_value=portfolio_value,
                output_png=output_png,
            )

        # Verify the file was created
        assert output_png.exists(), f"PNG file was not created at {output_png}"

        # Verify the file size is not zero
        file_size = output_png.stat().st_size
        assert file_size > 0, f"PNG file is empty (size: {file_size} bytes)"

        # Verify the file size is reasonable (at least a few KB)
        assert file_size > 1000, f"PNG file seems too small (size: {file_size} bytes)"

        print(f"Generated PNG file: {output_png} (size: {file_size} bytes)")


@pytest.mark.unit
class TestReportGenerationErrorHandling:
    """Tests error handling during report generation."""

    def test_matplotlib_import_error(self):
        """Tests the handling of a matplotlib ImportError."""
        dates = pd.date_range("2023-01-01", periods=3, freq="D")
        portfolio_value = pd.Series([10000, 10100, 10200], index=dates)

        metrics = {
            "start_date": dates[0].date(),
            "end_date": dates[-1].date(),
            "initial_value": 10000.0,
            "final_value": 10200.0,
            "total_return": 0.02,
            "annualized_return": 0.08,
            "max_drawdown": 0.01,
        }

        # Simulate a matplotlib import error
        with patch(
            "matplotlib.pyplot.style.use",
            side_effect=ImportError("No module named 'matplotlib'"),
        ):
            with pytest.raises(ImportError):
                generate_report(
                    metrics=metrics,
                    title="Error Test",
                    portfolio_value=portfolio_value,
                    output_png=Path("test.png"),
                )

    def test_file_permission_error(self, tmp_path):
        """Tests the handling of a file permission error."""
        # Create a read-only directory to trigger a permission error
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        output_png = readonly_dir / "test.png"

        dates = pd.date_range("2023-01-01", periods=3, freq="D")
        portfolio_value = pd.Series([10000, 10100, 10200], index=dates)

        metrics = {
            "start_date": dates[0].date(),
            "end_date": dates[-1].date(),
            "initial_value": 10000.0,
            "final_value": 10200.0,
            "total_return": 0.02,
            "annualized_return": 0.08,
            "max_drawdown": 0.01,
        }

        # Simulate a file saving error
        with patch(
            "matplotlib.pyplot.savefig",
            side_effect=PermissionError("Permission denied"),
        ):
            with patch("matplotlib.pyplot.show"):
                with patch("matplotlib.pyplot.style.use"):
                    with patch("matplotlib.pyplot.subplots") as mock_subplots:
                        mock_fig = Mock()
                        mock_ax = Mock()
                        mock_subplots.return_value = (mock_fig, mock_ax)

                        mock_ax.yaxis.set_major_formatter = Mock()
                        mock_ax.set_title = Mock()
                        mock_ax.set_xlabel = Mock()
                        mock_ax.set_ylabel = Mock()
                        mock_ax.legend = Mock()
                        mock_ax.grid = Mock()

                        with patch.object(portfolio_value, "plot", return_value=None):
                            with patch("matplotlib.pyplot.tight_layout"):
                                # This should raise a PermissionError
                                with pytest.raises(PermissionError):
                                    generate_report(
                                        metrics=metrics,
                                        title="Permission Error Test",
                                        portfolio_value=portfolio_value,
                                        output_png=output_png,
                                    )

    def test_invalid_data_handling(self):
        """Tests handling of invalid or empty data."""
        # An empty portfolio value series
        empty_portfolio = pd.Series([], dtype=float)

        metrics = {
            "start_date": pd.Timestamp("2023-01-01").date(),
            "end_date": pd.Timestamp("2023-01-01").date(),
            "initial_value": 10000.0,
            "final_value": 10000.0,
            "total_return": 0.0,
            "annualized_return": 0.0,
            "max_drawdown": 0.0,
        }

        with patch("matplotlib.pyplot.show"):
            with patch("matplotlib.pyplot.style.use"):
                with patch("matplotlib.pyplot.subplots") as mock_subplots:
                    mock_fig = Mock()
                    mock_ax = Mock()
                    mock_subplots.return_value = (mock_fig, mock_ax)

                    mock_ax.yaxis.set_major_formatter = Mock()
                    mock_ax.set_title = Mock()
                    mock_ax.set_xlabel = Mock()
                    mock_ax.set_ylabel = Mock()
                    mock_ax.legend = Mock()
                    mock_ax.grid = Mock()

                    with patch.object(empty_portfolio, "plot", return_value=None):
                        with patch("matplotlib.pyplot.tight_layout"):
                            # The function should handle empty data without crashing
                            generate_report(
                                metrics=metrics,
                                title="Empty Data Test",
                                portfolio_value=empty_portfolio,
                                output_png=None,
                            )


@pytest.mark.unit
class TestReportTextOutput:
    """Tests the text output of the report."""

    def test_report_text_content(self, capsys):
        """Tests the correctness of the report's text content."""
        dates = pd.date_range("2023-01-01", periods=3, freq="D")
        portfolio_value = pd.Series([10000, 10500, 11000], index=dates)

        metrics = {
            "start_date": dates[0].date(),
            "end_date": dates[-1].date(),
            "initial_value": 10000.0,
            "final_value": 11000.0,
            "total_return": 0.10,
            "annualized_return": 0.25,
            "max_drawdown": 0.03,
        }

        with patch("matplotlib.pyplot.show"):
            with patch("matplotlib.pyplot.style.use"):
                with patch("matplotlib.pyplot.subplots") as mock_subplots:
                    mock_fig = Mock()
                    mock_ax = Mock()
                    mock_subplots.return_value = (mock_fig, mock_ax)

                    mock_ax.yaxis.set_major_formatter = Mock()
                    mock_ax.set_title = Mock()
                    mock_ax.set_xlabel = Mock()
                    mock_ax.set_ylabel = Mock()
                    mock_ax.legend = Mock()
                    mock_ax.grid = Mock()

                    with patch.object(portfolio_value, "plot", return_value=None):
                        with patch("matplotlib.pyplot.tight_layout"):
                            generate_report(
                                metrics=metrics,
                                title="Text Content Test",
                                portfolio_value=portfolio_value,
                                output_png=None,
                            )

        captured = capsys.readouterr()
        output = captured.out

        # Verify that key information is displayed correctly
        assert "Text Content Test" in output
        assert "2023-01-01" in output
        assert "2023-01-03" in output
        assert "10,000" in output  # Initial value
        assert "11,000" in output  # Final value
        assert "10.00%" in output  # Total return
        assert "25.00%" in output  # Annualized return
        # Max drawdown might have different formatting, so just check for its presence
        assert "Max Drawdown" in output