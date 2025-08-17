"""统一日志配置模块

提供统一的日志配置功能，解决不同脚本使用不同日志方式的问题。
"""

import logging
import sys
from pathlib import Path
from typing import Optional

from .paths import OUTPUTS_DIR


def setup_logging(
    name: str,
    log_file: Optional[str] = None,
    level: int = logging.INFO,
    use_console: bool = True
) -> logging.Logger:
    """设置统一的日志配置
    
    Args:
        name: 日志器名称
        log_file: 日志文件名（可选），如果提供则会在OUTPUTS_DIR下创建日志文件
        level: 日志级别
        use_console: 是否同时输出到控制台
        
    Returns:
        logging.Logger: 配置好的日志器
    """
    logger = logging.getLogger(name)
    
    # 避免重复添加处理器
    if logger.handlers:
        return logger
        
    logger.setLevel(level)
    
    # 创建格式器
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 控制台处理器
    if use_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    # 文件处理器
    if log_file:
        log_path = OUTPUTS_DIR / log_file
        file_handler = logging.FileHandler(log_path, encoding='utf-8')
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


class StrategyLogger:
    """策略日志器
    
    提供统一的策略日志接口，兼容原有的print和logging.info两种方式。
    """
    
    def __init__(self, use_logging: bool = True, logger_name: str = "strategy"):
        """初始化策略日志器
        
        Args:
            use_logging: 是否使用logging模块，False则使用print
            logger_name: 日志器名称
        """
        self.use_logging = use_logging
        if use_logging:
            self.logger = setup_logging(logger_name)
        else:
            self.logger = None
    
    def log(self, message: str, dt=None) -> None:
        """记录日志
        
        Args:
            message: 日志消息
            dt: 日期时间（可选），用于兼容原有接口
        """
        if dt:
            formatted_message = f"{dt.isoformat()} - {message}"
        else:
            formatted_message = message
            
        if self.use_logging and self.logger:
            self.logger.info(formatted_message)
        else:
            print(formatted_message)
    
    def info(self, message: str) -> None:
        """记录信息级别日志"""
        self.log(message)
    
    def warning(self, message: str) -> None:
        """记录警告级别日志"""
        if self.use_logging and self.logger:
            self.logger.warning(message)
        else:
            print(f"WARNING: {message}")
    
    def error(self, message: str) -> None:
        """记录错误级别日志"""
        if self.use_logging and self.logger:
            self.logger.error(message)
        else:
            print(f"ERROR: {message}", file=sys.stderr)