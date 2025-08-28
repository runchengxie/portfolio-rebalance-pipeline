"""测试路径管理和日志功能模块

测试 utils.paths 和 utils.logging 中的功能，包括：
- utils.paths 的项目根、输出目录创建、数据库路径常量
- 日志器 setup_logging 正常落地到 outputs/ai_backtest.log 的 smoke test（临时目录）
"""

import logging
from pathlib import Path
from unittest.mock import patch

from stock_analysis.utils.logging import StrategyLogger, setup_logging
from stock_analysis.utils.paths import (
    AI_PORTFOLIO_FILE,
    DATA_DIR,
    DB_PATH,
    DEFAULT_INITIAL_CASH,
    OUTPUTS_DIR,
    PROJECT_ROOT,
    QUANT_PORTFOLIO_FILE,
    SPY_INITIAL_CASH,
    get_project_root,
)


class TestPaths:
    """测试路径管理功能"""

    def test_get_project_root(self):
        """测试获取项目根目录"""
        root = get_project_root()

        # 验证返回的是Path对象
        assert isinstance(root, Path)

        # 验证路径存在
        assert root.exists()

        # 验证是绝对路径
        assert root.is_absolute()

    def test_get_project_root_in_interactive_environment(self):
        """测试在交互式环境中获取项目根目录"""
        # 模拟NameError（如在Jupyter中）
        with patch("stock_analysis.utils.paths.Path") as mock_path:
            # 模拟__file__不存在的情况
            mock_path.side_effect = NameError("name '__file__' is not defined")

            # 应该回退到使用cwd()
            with patch("stock_analysis.utils.paths.Path.cwd") as mock_cwd:
                mock_cwd.return_value = Path("/mock/current/dir")

                # 重新导入以触发异常处理
                import importlib

                import stock_analysis.utils.paths

                importlib.reload(stock_analysis.utils.paths)

    def test_project_root_constant(self):
        """测试PROJECT_ROOT常量"""
        assert isinstance(PROJECT_ROOT, Path)
        assert PROJECT_ROOT.is_absolute()

    def test_data_dir_path(self):
        """测试DATA_DIR路径"""
        assert isinstance(DATA_DIR, Path)
        assert DATA_DIR == PROJECT_ROOT / "data"
        assert DATA_DIR.is_absolute()

    def test_outputs_dir_creation(self):
        """测试OUTPUTS_DIR自动创建"""
        assert isinstance(OUTPUTS_DIR, Path)
        assert OUTPUTS_DIR == PROJECT_ROOT / "outputs"
        assert OUTPUTS_DIR.is_absolute()

        # 验证目录存在（应该被自动创建）
        assert OUTPUTS_DIR.exists()
        assert OUTPUTS_DIR.is_dir()

    def test_db_path_constant(self):
        """测试数据库路径常量"""
        assert isinstance(DB_PATH, Path)
        assert DB_PATH == DATA_DIR / "financial_data.db"
        assert DB_PATH.suffix == ".db"

    def test_portfolio_file_paths(self):
        """测试投资组合文件路径"""
        # AI投资组合文件
        assert isinstance(AI_PORTFOLIO_FILE, Path)
        assert (
            AI_PORTFOLIO_FILE
            == OUTPUTS_DIR / "point_in_time_ai_stock_picks_all_sheets.xlsx"
        )
        assert AI_PORTFOLIO_FILE.suffix == ".xlsx"

        # 量化投资组合文件
        assert isinstance(QUANT_PORTFOLIO_FILE, Path)
        assert (
            QUANT_PORTFOLIO_FILE
            == OUTPUTS_DIR / "point_in_time_backtest_quarterly_sp500_historical.xlsx"
        )
        assert QUANT_PORTFOLIO_FILE.suffix == ".xlsx"

    def test_initial_cash_constants(self):
        """测试初始资金常量"""
        assert isinstance(DEFAULT_INITIAL_CASH, float)
        assert DEFAULT_INITIAL_CASH == 1_000_000.0

        assert isinstance(SPY_INITIAL_CASH, float)
        assert SPY_INITIAL_CASH == 100_000.0

        # 验证合理性
        assert DEFAULT_INITIAL_CASH > 0
        assert SPY_INITIAL_CASH > 0

    def test_path_relationships(self):
        """测试路径之间的关系"""
        # 验证所有路径都基于PROJECT_ROOT
        assert DATA_DIR.is_relative_to(PROJECT_ROOT)
        assert OUTPUTS_DIR.is_relative_to(PROJECT_ROOT)

        # 验证文件路径基于正确的目录
        assert DB_PATH.is_relative_to(DATA_DIR)
        assert AI_PORTFOLIO_FILE.is_relative_to(OUTPUTS_DIR)
        assert QUANT_PORTFOLIO_FILE.is_relative_to(OUTPUTS_DIR)


class TestSetupLogging:
    """测试日志设置功能"""

    def test_basic_logger_setup(self):
        """测试基本日志器设置"""
        logger = setup_logging("test_logger")

        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_logger"
        assert logger.level == logging.INFO
        assert len(logger.handlers) > 0

    def test_logger_with_file_output(self, tmp_path):
        """测试带文件输出的日志器"""
        # 临时修改OUTPUTS_DIR
        with patch("stock_analysis.utils.logging.OUTPUTS_DIR", tmp_path):
            logger = setup_logging("file_logger", log_file="test.log")

            # 测试日志记录
            logger.info("Test message")

            # 验证日志文件被创建
            log_file = tmp_path / "test.log"
            assert log_file.exists()

            # 验证日志内容
            log_content = log_file.read_text(encoding="utf-8")
            assert "Test message" in log_content
            assert "file_logger" in log_content

    def test_logger_without_console(self):
        """测试不输出到控制台的日志器"""
        logger = setup_logging("no_console_logger", use_console=False)

        # 应该没有StreamHandler
        stream_handlers = [
            h for h in logger.handlers if isinstance(h, logging.StreamHandler)
        ]
        assert len(stream_handlers) == 0

    def test_logger_custom_level(self):
        """测试自定义日志级别"""
        logger = setup_logging("debug_logger", level=logging.DEBUG)

        assert logger.level == logging.DEBUG

        # 验证处理器也设置了正确的级别
        for handler in logger.handlers:
            assert handler.level == logging.DEBUG

    def test_logger_duplicate_setup_prevention(self):
        """测试防止重复设置日志器"""
        # 第一次设置
        logger1 = setup_logging("duplicate_test")
        initial_handler_count = len(logger1.handlers)

        # 第二次设置同名日志器
        logger2 = setup_logging("duplicate_test")

        # 应该返回同一个日志器，且处理器数量不变
        assert logger1 is logger2
        assert len(logger2.handlers) == initial_handler_count

    def test_logger_formatter(self, tmp_path):
        """测试日志格式器"""
        with patch("stock_analysis.utils.logging.OUTPUTS_DIR", tmp_path):
            logger = setup_logging("format_test", log_file="format_test.log")
            logger.info("Format test message")

            log_file = tmp_path / "format_test.log"
            log_content = log_file.read_text(encoding="utf-8")

            # 验证格式包含预期元素
            assert "format_test" in log_content  # logger name
            assert "INFO" in log_content  # log level
            assert "Format test message" in log_content  # message
            # 验证时间戳格式（YYYY-MM-DD HH:MM:SS）
            import re

            timestamp_pattern = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"
            assert re.search(timestamp_pattern, log_content)

    def test_ai_backtest_log_smoke_test(self, tmp_path):
        """AI回测日志的烟雾测试"""
        with patch("stock_analysis.utils.logging.OUTPUTS_DIR", tmp_path):
            # 模拟AI回测日志设置
            logger = setup_logging("ai_backtest", log_file="ai_backtest.log")

            # 模拟一些典型的AI回测日志消息
            logger.info("Starting AI backtest...")
            logger.info("Loading portfolios from Excel file")
            logger.info("Processing quarter 2022-Q1")
            logger.warning("Missing price data for TICKER_XYZ")
            logger.info("Backtest completed successfully")

            # 验证日志文件存在且包含预期内容
            log_file = tmp_path / "ai_backtest.log"
            assert log_file.exists()

            log_content = log_file.read_text(encoding="utf-8")
            assert "Starting AI backtest" in log_content
            assert "Loading portfolios" in log_content
            assert "Processing quarter" in log_content
            assert "Missing price data" in log_content
            assert "Backtest completed" in log_content


class TestStrategyLogger:
    """测试策略日志器"""

    def test_strategy_logger_with_logging(self, tmp_path):
        """测试使用logging模块的策略日志器"""
        with patch("stock_analysis.utils.logging.OUTPUTS_DIR", tmp_path):
            strategy_logger = StrategyLogger(
                use_logging=True, logger_name="test_strategy"
            )

            assert strategy_logger.use_logging
            assert strategy_logger.logger is not None
            assert isinstance(strategy_logger.logger, logging.Logger)

    def test_strategy_logger_with_print(self):
        """测试使用print的策略日志器"""
        strategy_logger = StrategyLogger(use_logging=False)

        assert not strategy_logger.use_logging
        assert strategy_logger.logger is None

    def test_strategy_logger_log_method_with_datetime(self, capsys):
        """测试带日期时间的日志方法"""
        import datetime

        strategy_logger = StrategyLogger(use_logging=False)
        test_date = datetime.date(2022, 1, 15)

        strategy_logger.log("Test message", dt=test_date)

        captured = capsys.readouterr()
        assert "2022-01-15" in captured.out
        assert "Test message" in captured.out

    def test_strategy_logger_log_method_without_datetime(self, capsys):
        """测试不带日期时间的日志方法"""
        strategy_logger = StrategyLogger(use_logging=False)

        strategy_logger.log("Simple test message")

        captured = capsys.readouterr()
        assert "Simple test message" in captured.out

    def test_strategy_logger_info_method(self, capsys):
        """测试info方法"""
        strategy_logger = StrategyLogger(use_logging=False)

        strategy_logger.info("Info message")

        captured = capsys.readouterr()
        assert "Info message" in captured.out

    def test_strategy_logger_warning_method(self, capsys):
        """测试warning方法"""
        strategy_logger = StrategyLogger(use_logging=False)

        strategy_logger.warning("Warning message")

        captured = capsys.readouterr()
        assert "WARNING: Warning message" in captured.out

    def test_strategy_logger_error_method(self, capsys):
        """测试error方法"""
        strategy_logger = StrategyLogger(use_logging=False)

        strategy_logger.error("Error message")

        captured = capsys.readouterr()
        assert "ERROR: Error message" in captured.err

    def test_strategy_logger_with_real_logging(self, tmp_path):
        """测试使用真实logging的策略日志器"""
        with patch("stock_analysis.utils.logging.OUTPUTS_DIR", tmp_path):
            # 创建使用logging的策略日志器
            strategy_logger = StrategyLogger(
                use_logging=True, logger_name="real_logging_test"
            )

            # 设置文件日志
            strategy_logger.logger = setup_logging(
                "real_logging_test", log_file="strategy_test.log"
            )

            # 测试各种日志方法
            strategy_logger.info("Strategy info message")
            strategy_logger.warning("Strategy warning message")
            strategy_logger.error("Strategy error message")

            # 验证日志文件
            log_file = tmp_path / "strategy_test.log"
            assert log_file.exists()

            log_content = log_file.read_text(encoding="utf-8")
            assert "Strategy info message" in log_content
            assert "Strategy warning message" in log_content
            assert "Strategy error message" in log_content


class TestLoggingIntegration:
    """日志功能集成测试"""

    def test_multiple_loggers_isolation(self, tmp_path):
        """测试多个日志器的隔离性"""
        with patch("stock_analysis.utils.logging.OUTPUTS_DIR", tmp_path):
            # 创建两个不同的日志器
            logger1 = setup_logging("logger1", log_file="log1.log")
            logger2 = setup_logging("logger2", log_file="log2.log")

            # 记录不同的消息
            logger1.info("Message from logger1")
            logger2.info("Message from logger2")

            # 验证日志文件分离
            log1_content = (tmp_path / "log1.log").read_text(encoding="utf-8")
            log2_content = (tmp_path / "log2.log").read_text(encoding="utf-8")

            assert "Message from logger1" in log1_content
            assert "Message from logger1" not in log2_content

            assert "Message from logger2" in log2_content
            assert "Message from logger2" not in log1_content

    def test_strategy_logger_compatibility(self, tmp_path):
        """测试策略日志器与标准日志器的兼容性"""
        with patch("stock_analysis.utils.logging.OUTPUTS_DIR", tmp_path):
            # 创建标准日志器
            standard_logger = setup_logging("standard", log_file="standard.log")

            # 创建策略日志器
            strategy_logger = StrategyLogger(
                use_logging=True, logger_name="strategy_compat"
            )
            strategy_logger.logger = setup_logging(
                "strategy_compat", log_file="strategy.log"
            )

            # 两者都记录消息
            standard_logger.info("Standard logger message")
            strategy_logger.info("Strategy logger message")

            # 验证两个日志文件都正常工作
            standard_content = (tmp_path / "standard.log").read_text(encoding="utf-8")
            strategy_content = (tmp_path / "strategy.log").read_text(encoding="utf-8")

            assert "Standard logger message" in standard_content
            assert "Strategy logger message" in strategy_content

    def test_logging_performance_smoke_test(self, tmp_path):
        """日志性能烟雾测试"""
        import time

        with patch("stock_analysis.utils.logging.OUTPUTS_DIR", tmp_path):
            logger = setup_logging("performance_test", log_file="performance.log")

            # 记录大量日志消息的时间
            start_time = time.time()

            for i in range(1000):
                logger.info(f"Performance test message {i}")

            elapsed_time = time.time() - start_time

            # 验证性能合理（1000条消息应该在合理时间内完成）
            assert elapsed_time < 5.0  # 5秒内完成

            # 验证所有消息都被记录
            log_content = (tmp_path / "performance.log").read_text(encoding="utf-8")
            assert "Performance test message 0" in log_content
            assert "Performance test message 999" in log_content

    def test_unicode_logging_support(self, tmp_path):
        """测试Unicode字符日志支持"""
        with patch("stock_analysis.utils.logging.OUTPUTS_DIR", tmp_path):
            logger = setup_logging("unicode_test", log_file="unicode.log")

            # 记录包含Unicode字符的消息
            unicode_messages = [
                "测试中文日志消息",
                "Тест русского сообщения",
                "Test émojis: 📈📊💰",
                "Special chars: ñáéíóú",
            ]

            for msg in unicode_messages:
                logger.info(msg)

            # 验证Unicode字符正确保存
            log_content = (tmp_path / "unicode.log").read_text(encoding="utf-8")

            for msg in unicode_messages:
                assert msg in log_content
