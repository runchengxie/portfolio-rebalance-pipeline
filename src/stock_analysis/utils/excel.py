"""Excel 工具函数

提供 Excel 文件处理相关的工具函数。
"""
import re
from pathlib import Path
from typing import List, Tuple

import pandas as pd

from .logging import get_logger

logger = get_logger(__name__)


def pick_latest_sheet(sheet_names: List[str]) -> str:
    """从 sheet 名称列表中选择最新的季度
    
    Args:
        sheet_names: sheet 名称列表
        
    Returns:
        str: 最新的 sheet 名称
    """
    candidates = []
    
    for sheet_name in sheet_names:
        try:
            # 尝试直接解析为日期
            date = pd.to_datetime(sheet_name).date()
            candidates.append((date, sheet_name))
        except Exception:
            # 尝试匹配 yyyy-mm-dd 格式
            match = re.search(r"\d{4}-\d{2}-\d{2}", sheet_name)
            if match:
                try:
                    date = pd.to_datetime(match.group(0)).date()
                    candidates.append((date, sheet_name))
                except Exception:
                    continue
    
    if candidates:
        # 返回日期最新的 sheet
        return max(candidates)[1]
    
    # 兜底：返回最后一个 sheet
    return sheet_names[-1] if sheet_names else ""


def read_latest_sheet_tickers(file_path: Path) -> Tuple[List[str], str]:
    """读取 Excel 文件中最新 sheet 的股票代码列表
    
    Args:
        file_path: Excel 文件路径
        
    Returns:
        Tuple[List[str], str]: (股票代码列表, sheet名称)
        
    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 文件格式错误或找不到股票代码列
    """
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    try:
        # 读取所有 sheet
        excel_file = pd.ExcelFile(file_path)
        
        # 选择最新的 sheet
        sheet_name = pick_latest_sheet(excel_file.sheet_names)
        logger.info(f"选择 sheet: {sheet_name}")
        
        # 读取数据
        df = pd.read_excel(excel_file, sheet_name=sheet_name)
        
        # 识别 ticker 列
        columns_lower = {col.lower(): col for col in df.columns}
        ticker_column = columns_lower.get("ticker") or columns_lower.get("symbol")
        
        if not ticker_column:
            raise ValueError("未找到 ticker 或 symbol 列")
        
        # 提取股票代码
        tickers = (
            df[ticker_column]
            .astype(str)
            .str.upper()
            .str.strip()
            .dropna()
            .tolist()
        )
        
        # 过滤空值
        tickers = [ticker for ticker in tickers if ticker and ticker != "NAN"]
        
        if not tickers:
            raise ValueError("未找到有效的股票代码")
        
        logger.info(f"成功读取 {len(tickers)} 个股票代码")
        return tickers, sheet_name
        
    except Exception as e:
        logger.error(f"读取 Excel 文件失败: {e}")
        raise


def read_excel_data(file_path: Path, sheet_name: str = None) -> pd.DataFrame:
    """读取 Excel 文件数据
    
    Args:
        file_path: Excel 文件路径
        sheet_name: sheet 名称，如果为 None 则读取第一个 sheet
        
    Returns:
        pd.DataFrame: Excel 数据
        
    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 文件格式错误
    """
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    try:
        if sheet_name:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
        else:
            df = pd.read_excel(file_path)
        
        logger.info(f"成功读取 Excel 文件，包含 {len(df)} 行数据")
        return df
        
    except Exception as e:
        logger.error(f"读取 Excel 文件失败: {e}")
        raise


def get_sheet_names(file_path: Path) -> List[str]:
    """获取 Excel 文件中所有 sheet 名称
    
    Args:
        file_path: Excel 文件路径
        
    Returns:
        List[str]: sheet 名称列表
        
    Raises:
        FileNotFoundError: 文件不存在
    """
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    try:
        excel_file = pd.ExcelFile(file_path)
        return excel_file.sheet_names
    except Exception as e:
        logger.error(f"读取 Excel sheet 名称失败: {e}")
        raise