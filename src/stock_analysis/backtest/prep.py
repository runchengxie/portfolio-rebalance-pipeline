"""数据准备模块

提供组合加载与数据对齐功能，统一处理Excel读取和数据库查询逻辑。
"""

import datetime
import sqlite3
import sys
from pathlib import Path
from typing import Dict, Set

import backtrader as bt
import pandas as pd

from ..utils.paths import DB_PATH


def tidy_ticker(col: pd.Series) -> pd.Series:
    """清洗股票代码
    
    Args:
        col: 包含股票代码的Series
        
    Returns:
        pd.Series: 清洗后的股票代码Series
    """
    return (
        col.astype("string")
        .str.upper()
        .str.strip()
        .str.replace(r"_DELISTED$", "", regex=True)
        .replace({"": pd.NA})
    )


def load_portfolios(
    portfolio_path: Path,
    is_ai_selection: bool = False
) -> Dict[datetime.date, pd.DataFrame]:
    """加载投资组合数据
    
    Args:
        portfolio_path: Excel文件路径
        is_ai_selection: 是否为AI精选版本，影响列名处理逻辑
        
    Returns:
        Dict[datetime.date, pd.DataFrame]: 以调仓日期为键的投资组合字典
        
    Raises:
        FileNotFoundError: 当文件不存在时
    """
    if not portfolio_path.exists():
        raise FileNotFoundError(f"Portfolio file not found: {portfolio_path}")
    
    xls = pd.read_excel(portfolio_path, sheet_name=None, engine="openpyxl")
    portfolios = {}
    
    for date_str, df in xls.items():
        if df.empty:
            continue
            
        # 处理列名兼容性问题
        if is_ai_selection:
            # AI版本：自动处理列名大小写，兼容 'ticker' 和 'Ticker'
            if 'ticker' in df.columns and 'Ticker' not in df.columns:
                df.rename(columns={'ticker': 'Ticker'}, inplace=True)
        
        # 检查是否包含必要的列
        if "Ticker" in df.columns:
            # 清洗Ticker列
            df["Ticker"] = tidy_ticker(df["Ticker"])
            # 移除空的Ticker
            df = df.dropna(subset=["Ticker"])
            
            if not df.empty:
                portfolios[pd.to_datetime(date_str).date()] = df
    
    return portfolios


def load_price_feeds(
    db_path: Path,
    tickers: Set[str],
    start_date: datetime.date,
    end_date: datetime.date
) -> Dict[str, bt.feeds.PandasData]:
    """从数据库加载价格数据并创建Backtrader数据源
    
    Args:
        db_path: 数据库文件路径
        tickers: 需要加载的股票代码集合
        start_date: 开始日期
        end_date: 结束日期
        
    Returns:
        Dict[str, bt.feeds.PandasData]: 以股票代码为键的数据源字典
        
    Raises:
        FileNotFoundError: 当数据库文件不存在时
        ValueError: 当没有找到交易日数据时
    """
    print(f"Loading and preparing all price data from {start_date} to {end_date}...")
    
    if not db_path.exists():
        print(f"[ERROR] 数据库文件不存在: {db_path}", file=sys.stderr)
        raise FileNotFoundError(f"Database file not found: {db_path}")
    
    con = sqlite3.connect(db_path)
    
    try:
        # 获取主交易日索引
        date_query = (
            "SELECT DISTINCT Date FROM share_prices "
            "WHERE Date >= ? AND Date <= ? ORDER BY Date"
        )
        master_dates_df = pd.read_sql_query(
            date_query,
            con,
            params=[start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")],
            parse_dates=["Date"],
        )
        
        if master_dates_df.empty:
            raise ValueError(
                "No trading days found in the database for the specified date range."
            )
        
        master_index = pd.to_datetime(master_dates_df["Date"])
        print(f"Master timeline created with {len(master_index)} trading days.")
        
        # 批量查询所有股票数据
        tickers_list = list(tickers)
        placeholders = ",".join(["?" for _ in tickers_list])
        bulk_query = f"""
            SELECT Date, Ticker, Open, High, Low, Close, Volume, Dividend 
            FROM share_prices 
            WHERE Ticker IN ({placeholders}) AND Date >= ? AND Date <= ? 
            ORDER BY Ticker, Date
        """
        
        params = tickers_list + [
            start_date.strftime("%Y-%m-%d"),
            end_date.strftime("%Y-%m-%d"),
        ]
        
        all_data = pd.read_sql_query(
            bulk_query, con, params=params, parse_dates=["Date"]
        )
        
        # 去重修复：移除可能的重复数据
        all_data.drop_duplicates(subset=["Ticker", "Date"], keep="last", inplace=True)
        
        # 为每个股票创建数据源
        data_feeds = {}
        
        for ticker, group in all_data.groupby("Ticker"):
            group = group.set_index("Date")
            
            # 重新索引到主交易日时间线，前向填充缺失数据
            group = group.reindex(master_index, method="ffill")
            
            # 填充红利列的缺失值
            group["Dividend"] = group["Dividend"].fillna(0.0)
            
            # 移除仍然缺失的行（通常是新上市股票的早期数据）
            group = group.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
            
            if not group.empty:
                # 创建Backtrader数据源
                bt_feed = bt.feeds.PandasData(
                    dataname=group,
                    openinterest=None,
                    name=ticker
                )
                data_feeds[ticker] = bt_feed
                print(f"Prepared data for {ticker}: {len(group)} rows")
            else:
                print(f"Warning: No valid data for {ticker} after processing")
        
        print(f"Successfully prepared data feeds for {len(data_feeds)} tickers")
        return data_feeds
        
    finally:
        con.close()


def load_spy_data(
    db_path: Path,
    start_date: datetime.datetime,
    end_date: datetime.datetime,
    ticker: str = "SPY"
) -> pd.DataFrame:
    """从数据库加载SPY数据
    
    Args:
        db_path: 数据库文件路径
        start_date: 开始日期
        end_date: 结束日期
        ticker: 股票代码，默认为SPY
        
    Returns:
        pd.DataFrame: SPY价格数据
        
    Raises:
        FileNotFoundError: 当数据库文件不存在时
        ValueError: 当没有找到数据时
    """
    print(f"Loading {ticker} data from database: {db_path.name}...")
    
    if not db_path.exists():
        raise FileNotFoundError(f"Database file not found: {db_path}")
    
    con = sqlite3.connect(db_path)
    
    try:
        query = """
        SELECT Date, Open, High, Low, Close, Volume, Dividend
        FROM share_prices 
        WHERE Ticker = ? AND Date >= ? AND Date <= ?
        ORDER BY Date
        """
        
        data = pd.read_sql_query(
            query,
            con,
            params=[
                ticker,
                start_date.strftime("%Y-%m-%d"),
                end_date.strftime("%Y-%m-%d"),
            ],
            parse_dates=["Date"],
        )
        
        if data.empty:
            raise ValueError(
                f"No {ticker} data found in database for the specified date range: "
                f"{start_date} to {end_date}"
            )
        
        data.set_index("Date", inplace=True)
        data["Dividend"] = data["Dividend"].fillna(0.0)
        
        print(
            f"Loaded {len(data)} rows for {ticker} from "
            f"{data.index.min().date()} to {data.index.max().date()}."
        )
        
        return data
        
    finally:
        con.close()