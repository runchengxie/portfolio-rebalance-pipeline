# src/stock_analysis/utils/logging.py
from __future__ import annotations

import logging
import sys
from pathlib import Path

# 这个模块其他地方已经在用
try:
    from .paths import OUTPUTS_DIR
except Exception:
    # 兜底，别因为路径模块问题再炸一次
    OUTPUTS_DIR = Path.cwd() / "outputs"

__all__ = ["setup_logging", "get_logger", "StrategyLogger"]

_DEFAULT_FMT = "[%(asctime)s] %(levelname)s %(name)s: %(message)s"
_DEFAULT_DATEFMT = "%Y-%m-%d %H:%M:%S"


def _ensure_outputs_dir() -> Path:
    try:
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        # 最坏情况回到当前目录
        return Path.cwd()
    return OUTPUTS_DIR


def setup_logging(
    name: str, filename: str | None = None, level: int = logging.INFO
) -> logging.Logger:
    """
    创建/获取一个带控制台输出与可选文件输出的 logger。
    多次调用不会重复加 handler。
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 已经配置过就直接用，避免重复 handler
    if getattr(logger, "_configured", False):
        return logger

    formatter = logging.Formatter(_DEFAULT_FMT, datefmt=_DEFAULT_DATEFMT)

    # 控制台
    sh = logging.StreamHandler(stream=sys.stdout)
    sh.setLevel(level)
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    # 文件
    if filename:
        out_dir = _ensure_outputs_dir()
        fh_path = out_dir / filename
        fh = logging.FileHandler(fh_path, encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    logger._configured = True  # type: ignore[attr-defined]
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    兼容老代码的获取函数。不给文件名的话，只配控制台。
    需要落盘的地方自己先调一次 setup_logging(name, 'xxx.log')。
    """
    return setup_logging(name, filename=None)


class StrategyLogger:
    """
    给回测策略用的小包装：可以走 logging，也可以退回 print。
    """

    def __init__(self, use_logging: bool = True, logger_name: str = "strategy"):
        self.use_logging = use_logging
        if use_logging:
            # 确保至少有控制台输出；文件输出让上层自行决定
            self.logger = setup_logging(logger_name)
        else:
            self.logger = None

    def log(self, txt: str, dt=None) -> None:
        if self.use_logging and self.logger:
            if dt is not None:
                self.logger.info(f"{dt} - {txt}")
            else:
                self.logger.info(txt)
        else:
            prefix = f"{dt} - " if dt is not None else ""
            print(prefix + txt)
