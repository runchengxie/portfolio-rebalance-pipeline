"""账户快照服务

提供账户快照相关的业务逻辑，返回结构化数据。
"""

from ..broker.longport_client import LongPortClient
from ..models import AccountSnapshot, Position, Quote
from ..utils.logging import get_logger

logger = get_logger(__name__)


def get_account_snapshot(env: str) -> AccountSnapshot:
    """获取账户快照

    Args:
        env: 环境选择（test/real）

    Returns:
        AccountSnapshot: 账户快照数据

    Raises:
        Exception: 当无法获取账户数据时
    """
    try:
        client = LongPortClient(env=env)
        cash_usd, stock_position_map = client.portfolio_snapshot()

        # 股票持仓报价
        stock_quotes = {}
        if stock_position_map:
            stock_quotes = client.quote_last(list(stock_position_map.keys()))

        positions: list[Position] = []

        # 股票持仓 -> Position
        for symbol, quantity in stock_position_map.items():
            price, _ = stock_quotes.get(symbol, (0.0, ""))
            positions.append(
                Position(
                    symbol=symbol,
                    quantity=int(quantity),
                    last_price=float(price),
                    estimated_value=int(quantity) * float(price),
                    env=env,
                )
            )

        # 基金持仓 -> Position（使用净值作为价格）
        fund_map = client.fund_positions()
        for fsymbol, (units, nav, _ccy) in fund_map.items():
            qty_int = int(units)  # Position.quantity 为 int；如需更精确可扩展为 float
            positions.append(
                Position(
                    symbol=fsymbol,
                    quantity=qty_int,
                    last_price=float(nav),
                    estimated_value=units * float(nav),
                    env=env,
                )
            )

        client.close()

        return AccountSnapshot(env=env, cash_usd=cash_usd, positions=positions)

    except Exception as e:
        logger.error(f"无法获取 {env} 环境账户数据: {e}")
        # 让调用方感受到真实的痛苦，而不是假快乐
        raise RuntimeError(f"{env} 环境账户数据获取失败: {e}") from e


def get_multiple_account_snapshots(envs: list[str]) -> list[AccountSnapshot]:
    """获取多个环境的账户快照

    Args:
        envs: 环境列表

    Returns:
        List[AccountSnapshot]: 账户快照列表
    """
    snapshots = []
    for env in envs:
        if env in ("test", "real"):
            snapshot = get_account_snapshot(env)
            snapshots.append(snapshot)
    return snapshots


def get_quotes(symbols: list[str], env: str = "test") -> dict[str, Quote]:
    """获取股票报价

    Args:
        symbols: 股票代码列表
        env: 环境选择

    Returns:
        Dict[str, Quote]: 股票代码到报价的映射

    Raises:
        Exception: 当无法获取报价时
    """
    try:
        client = LongPortClient(env=env)
        quote_data = client.quote_last(symbols)
        client.close()

        quotes = {}
        for symbol, (price, timestamp) in quote_data.items():
            quotes[symbol] = Quote(
                symbol=symbol, price=float(price), timestamp=timestamp
            )

        return quotes

    except Exception as e:
        logger.error(f"获取报价失败: {e}")
        raise
