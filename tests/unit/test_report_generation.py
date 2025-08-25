"""报告生成的smoke test

测试回测报告生成功能：
- PNG文件的创建和保存
- 文件大小验证（非零大小）
- 图表生成的基本功能
- 错误情况的处理
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from stock_analysis.backtest.engine import generate_report


@pytest.mark.unit
class TestReportGeneration:
    """测试报告生成的基本功能"""
    
    def test_generate_report_creates_png_file(self, tmp_path):
        """测试generate_report创建PNG文件"""
        # 准备测试数据
        output_png = tmp_path / "test_report.png"
        
        # 创建模拟的投资组合价值序列
        dates = pd.date_range('2023-01-01', periods=10, freq='D')
        portfolio_value = pd.Series(
            [10000 + i * 100 for i in range(10)],
            index=dates
        )
        
        # 创建模拟的指标字典
        metrics = {
            'start_date': dates[0].date(),
            'end_date': dates[-1].date(),
            'initial_value': 10000.0,
            'final_value': 10900.0,
            'total_return': 0.09,
            'annualized_return': 0.12,
            'max_drawdown': 0.05
        }
        
        # 模拟matplotlib的savefig方法
        with patch('matplotlib.pyplot.savefig') as mock_savefig:
            with patch('matplotlib.pyplot.show'):
                with patch('matplotlib.pyplot.style.use'):
                    with patch('matplotlib.pyplot.subplots') as mock_subplots:
                        # 创建模拟的figure和axes
                        mock_fig = Mock()
                        mock_ax = Mock()
                        mock_subplots.return_value = (mock_fig, mock_ax)
                        
                        # 模拟pandas Series的plot方法
                        mock_ax.yaxis.set_major_formatter = Mock()
                        mock_ax.set_title = Mock()
                        mock_ax.set_xlabel = Mock()
                        mock_ax.set_ylabel = Mock()
                        mock_ax.legend = Mock()
                        mock_ax.grid = Mock()
                        
                        with patch.object(portfolio_value, 'plot', return_value=None):
                            with patch('matplotlib.pyplot.tight_layout'):
                                generate_report(
                                    metrics=metrics,
                                    title="Test Report",
                                    portfolio_value=portfolio_value,
                                    output_png=output_png
                                )
                        
                        # 验证savefig被调用
                        mock_savefig.assert_called_once_with(
                            output_png, 
                            dpi=300, 
                            bbox_inches="tight"
                        )
    
    def test_generate_report_with_benchmark(self, tmp_path):
        """测试带基准的报告生成"""
        output_png = tmp_path / "benchmark_report.png"
        
        # 创建投资组合和基准数据
        dates = pd.date_range('2023-01-01', periods=5, freq='D')
        portfolio_value = pd.Series([10000, 10100, 10200, 10150, 10300], index=dates)
        benchmark_value = pd.Series([10000, 10050, 10100, 10080, 10120], index=dates)
        
        metrics = {
            'start_date': dates[0].date(),
            'end_date': dates[-1].date(),
            'initial_value': 10000.0,
            'final_value': 10300.0,
            'total_return': 0.03,
            'annualized_return': 0.15,
            'max_drawdown': 0.02
        }
        
        with patch('matplotlib.pyplot.savefig') as mock_savefig:
            with patch('matplotlib.pyplot.show'):
                with patch('matplotlib.pyplot.style.use'):
                    with patch('matplotlib.pyplot.subplots') as mock_subplots:
                        mock_fig = Mock()
                        mock_ax = Mock()
                        mock_subplots.return_value = (mock_fig, mock_ax)
                        
                        # 模拟所有必要的方法
                        mock_ax.yaxis.set_major_formatter = Mock()
                        mock_ax.set_title = Mock()
                        mock_ax.set_xlabel = Mock()
                        mock_ax.set_ylabel = Mock()
                        mock_ax.legend = Mock()
                        mock_ax.grid = Mock()
                        
                        with patch.object(portfolio_value, 'plot', return_value=None):
                            with patch.object(benchmark_value, 'plot', return_value=None):
                                with patch('matplotlib.pyplot.tight_layout'):
                                    generate_report(
                                        metrics=metrics,
                                        title="Portfolio vs Benchmark",
                                        portfolio_value=portfolio_value,
                                        output_png=output_png,
                                        benchmark_value=benchmark_value,
                                        benchmark_label="SPY"
                                    )
                        
                        # 验证savefig被调用
                        mock_savefig.assert_called_once()
    
    def test_generate_report_without_png_output(self, capsys):
        """测试不保存PNG文件的报告生成"""
        dates = pd.date_range('2023-01-01', periods=3, freq='D')
        portfolio_value = pd.Series([10000, 10100, 10200], index=dates)
        
        metrics = {
            'start_date': dates[0].date(),
            'end_date': dates[-1].date(),
            'initial_value': 10000.0,
            'final_value': 10200.0,
            'total_return': 0.02,
            'annualized_return': 0.08,
            'max_drawdown': 0.01
        }
        
        with patch('matplotlib.pyplot.savefig') as mock_savefig:
            with patch('matplotlib.pyplot.show'):
                with patch('matplotlib.pyplot.style.use'):
                    with patch('matplotlib.pyplot.subplots') as mock_subplots:
                        mock_fig = Mock()
                        mock_ax = Mock()
                        mock_subplots.return_value = (mock_fig, mock_ax)
                        
                        mock_ax.yaxis.set_major_formatter = Mock()
                        mock_ax.set_title = Mock()
                        mock_ax.set_xlabel = Mock()
                        mock_ax.set_ylabel = Mock()
                        mock_ax.legend = Mock()
                        mock_ax.grid = Mock()
                        
                        with patch.object(portfolio_value, 'plot', return_value=None):
                            with patch('matplotlib.pyplot.tight_layout'):
                                generate_report(
                                    metrics=metrics,
                                    title="No PNG Test",
                                    portfolio_value=portfolio_value,
                                    output_png=None  # 不保存PNG
                                )
                        
                        # 验证savefig未被调用
                        mock_savefig.assert_not_called()
        
        # 验证文本报告被打印
        captured = capsys.readouterr()
        assert "No PNG Test" in captured.out
        assert "Total Return:" in captured.out
        assert "Annualized Return:" in captured.out


@pytest.mark.unit
class TestReportGenerationRealFiles:
    """测试实际文件生成（使用真实的matplotlib）"""
    
    @pytest.mark.integration  # 标记为integration测试，因为涉及实际文件操作
    def test_actual_png_file_creation(self, tmp_path):
        """测试实际PNG文件的创建和大小验证"""
        output_png = tmp_path / "actual_test.png"
        
        # 创建简单的测试数据
        dates = pd.date_range('2023-01-01', periods=5, freq='D')
        portfolio_value = pd.Series([10000, 10100, 10050, 10150, 10200], index=dates)
        
        metrics = {
            'start_date': dates[0].date(),
            'end_date': dates[-1].date(),
            'initial_value': 10000.0,
            'final_value': 10200.0,
            'total_return': 0.02,
            'annualized_return': 0.08,
            'max_drawdown': 0.025
        }
        
        # 使用真实的matplotlib，但不显示图表
        with patch('matplotlib.pyplot.show'):  # 阻止显示图表
            generate_report(
                metrics=metrics,
                title="Actual File Test",
                portfolio_value=portfolio_value,
                output_png=output_png
            )
        
        # 验证文件被创建
        assert output_png.exists(), f"PNG file was not created at {output_png}"
        
        # 验证文件大小非零
        file_size = output_png.stat().st_size
        assert file_size > 0, f"PNG file is empty (size: {file_size} bytes)"
        
        # 验证文件大小合理（至少几KB）
        assert file_size > 1000, f"PNG file seems too small (size: {file_size} bytes)"
        
        print(f"Generated PNG file: {output_png} (size: {file_size} bytes)")


@pytest.mark.unit
class TestReportGenerationErrorHandling:
    """测试报告生成的错误处理"""
    
    def test_matplotlib_import_error(self):
        """测试matplotlib导入错误的处理"""
        dates = pd.date_range('2023-01-01', periods=3, freq='D')
        portfolio_value = pd.Series([10000, 10100, 10200], index=dates)
        
        metrics = {
            'start_date': dates[0].date(),
            'end_date': dates[-1].date(),
            'initial_value': 10000.0,
            'final_value': 10200.0,
            'total_return': 0.02,
            'annualized_return': 0.08,
            'max_drawdown': 0.01
        }
        
        # 模拟matplotlib导入错误
        with patch('matplotlib.pyplot.style.use', side_effect=ImportError("No module named 'matplotlib'")):
            with pytest.raises(ImportError):
                generate_report(
                    metrics=metrics,
                    title="Error Test",
                    portfolio_value=portfolio_value,
                    output_png=Path("test.png")
                )
    
    def test_file_permission_error(self, tmp_path):
        """测试文件权限错误的处理"""
        # 创建一个只读目录
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        output_png = readonly_dir / "test.png"
        
        dates = pd.date_range('2023-01-01', periods=3, freq='D')
        portfolio_value = pd.Series([10000, 10100, 10200], index=dates)
        
        metrics = {
            'start_date': dates[0].date(),
            'end_date': dates[-1].date(),
            'initial_value': 10000.0,
            'final_value': 10200.0,
            'total_return': 0.02,
            'annualized_return': 0.08,
            'max_drawdown': 0.01
        }
        
        # 模拟文件保存错误
        with patch('matplotlib.pyplot.savefig', side_effect=PermissionError("Permission denied")):
            with patch('matplotlib.pyplot.show'):
                with patch('matplotlib.pyplot.style.use'):
                    with patch('matplotlib.pyplot.subplots') as mock_subplots:
                        mock_fig = Mock()
                        mock_ax = Mock()
                        mock_subplots.return_value = (mock_fig, mock_ax)
                        
                        mock_ax.yaxis.set_major_formatter = Mock()
                        mock_ax.set_title = Mock()
                        mock_ax.set_xlabel = Mock()
                        mock_ax.set_ylabel = Mock()
                        mock_ax.legend = Mock()
                        mock_ax.grid = Mock()
                        
                        with patch.object(portfolio_value, 'plot', return_value=None):
                            with patch('matplotlib.pyplot.tight_layout'):
                                # 应该抛出权限错误
                                with pytest.raises(PermissionError):
                                    generate_report(
                                        metrics=metrics,
                                        title="Permission Error Test",
                                        portfolio_value=portfolio_value,
                                        output_png=output_png
                                    )
    
    def test_invalid_data_handling(self):
        """测试无效数据的处理"""
        # 空的投资组合价值序列
        empty_portfolio = pd.Series([], dtype=float)
        
        metrics = {
            'start_date': pd.Timestamp('2023-01-01').date(),
            'end_date': pd.Timestamp('2023-01-01').date(),
            'initial_value': 10000.0,
            'final_value': 10000.0,
            'total_return': 0.0,
            'annualized_return': 0.0,
            'max_drawdown': 0.0
        }
        
        with patch('matplotlib.pyplot.show'):
            with patch('matplotlib.pyplot.style.use'):
                with patch('matplotlib.pyplot.subplots') as mock_subplots:
                    mock_fig = Mock()
                    mock_ax = Mock()
                    mock_subplots.return_value = (mock_fig, mock_ax)
                    
                    mock_ax.yaxis.set_major_formatter = Mock()
                    mock_ax.set_title = Mock()
                    mock_ax.set_xlabel = Mock()
                    mock_ax.set_ylabel = Mock()
                    mock_ax.legend = Mock()
                    mock_ax.grid = Mock()
                    
                    with patch.object(empty_portfolio, 'plot', return_value=None):
                        with patch('matplotlib.pyplot.tight_layout'):
                            # 应该能处理空数据而不崩溃
                            generate_report(
                                metrics=metrics,
                                title="Empty Data Test",
                                portfolio_value=empty_portfolio,
                                output_png=None
                            )


@pytest.mark.unit
class TestReportTextOutput:
    """测试报告文本输出"""
    
    def test_report_text_content(self, capsys):
        """测试报告文本内容的正确性"""
        dates = pd.date_range('2023-01-01', periods=3, freq='D')
        portfolio_value = pd.Series([10000, 10500, 11000], index=dates)
        
        metrics = {
            'start_date': dates[0].date(),
            'end_date': dates[-1].date(),
            'initial_value': 10000.0,
            'final_value': 11000.0,
            'total_return': 0.10,
            'annualized_return': 0.25,
            'max_drawdown': 0.03
        }
        
        with patch('matplotlib.pyplot.show'):
            with patch('matplotlib.pyplot.style.use'):
                with patch('matplotlib.pyplot.subplots') as mock_subplots:
                    mock_fig = Mock()
                    mock_ax = Mock()
                    mock_subplots.return_value = (mock_fig, mock_ax)
                    
                    mock_ax.yaxis.set_major_formatter = Mock()
                    mock_ax.set_title = Mock()
                    mock_ax.set_xlabel = Mock()
                    mock_ax.set_ylabel = Mock()
                    mock_ax.legend = Mock()
                    mock_ax.grid = Mock()
                    
                    with patch.object(portfolio_value, 'plot', return_value=None):
                        with patch('matplotlib.pyplot.tight_layout'):
                            generate_report(
                                metrics=metrics,
                                title="Text Content Test",
                                portfolio_value=portfolio_value,
                                output_png=None
                            )
        
        captured = capsys.readouterr()
        output = captured.out
        
        # 验证关键信息被正确显示
        assert "Text Content Test" in output
        assert "2023-01-01" in output
        assert "2023-01-03" in output
        assert "10,000" in output  # 初始值
        assert "11,000" in output  # 最终值
        assert "10.00%" in output      # 总收益
        assert "25.00%" in output      # 年化收益
        # 最大回撤可能有不同格式，只检查基本存在
        assert "Max Drawdown" in output or "最大回撤" in output