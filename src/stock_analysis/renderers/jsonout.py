"""JSON 渲染器

提供 JSON 格式的数据渲染功能。
"""

import json
from typing import Any

from ..models import AccountSnapshot, Order, Quote, RebalanceResult


def _serialize_dataclass(obj: Any) -> dict[str, Any]:
    """序列化 dataclass 对象为字典

    Args:
        obj: 要序列化的对象

    Returns:
        Dict[str, Any]: 序列化后的字典
    """
    if hasattr(obj, "__dataclass_fields__"):
        result = {}
        for field_name in obj.__dataclass_fields__:
            value = getattr(obj, field_name)
            if hasattr(value, "__dataclass_fields__"):
                result[field_name] = _serialize_dataclass(value)
            elif isinstance(value, list):
                result[field_name] = [
                    _serialize_dataclass(item)
                    if hasattr(item, "__dataclass_fields__")
                    else item
                    for item in value
                ]
            elif hasattr(value, "isoformat"):  # datetime objects
                result[field_name] = value.isoformat()
            else:
                result[field_name] = value
        return result
    return obj


def render_quotes_json(quotes: list[Quote]) -> str:
    """渲染股票报价 JSON

    Args:
        quotes: 报价列表

    Returns:
        str: JSON 字符串
    """
    data = [_serialize_dataclass(quote) for quote in quotes]
    return json.dumps(data, ensure_ascii=False, indent=2)


def render_account_snapshot_json(snapshot: AccountSnapshot) -> str:
    """渲染账户快照 JSON

    Args:
        snapshot: 账户快照

    Returns:
        str: JSON 字符串
    """
    data = _serialize_dataclass(snapshot)
    return json.dumps(data, ensure_ascii=False, indent=2)


def render_multiple_account_snapshots_json(snapshots: list[AccountSnapshot]) -> str:
    """渲染多个账户快照 JSON

    Args:
        snapshots: 账户快照列表

    Returns:
        str: JSON 字符串
    """
    data = [_serialize_dataclass(snapshot) for snapshot in snapshots]
    return json.dumps(data, ensure_ascii=False, indent=2)


def render_rebalance_result_json(result: RebalanceResult) -> str:
    """渲染调仓结果 JSON

    Args:
        result: 调仓结果

    Returns:
        str: JSON 字符串
    """
    data = _serialize_dataclass(result)
    return json.dumps(data, ensure_ascii=False, indent=2)


def render_orders_json(orders: list[Order]) -> str:
    """渲染订单列表 JSON

    Args:
        orders: 订单列表

    Returns:
        str: JSON 字符串
    """
    data = [_serialize_dataclass(order) for order in orders]
    return json.dumps(data, ensure_ascii=False, indent=2)


def render_json(data: Any) -> str:
    """通用 JSON 渲染器

    Args:
        data: 要渲染的数据

    Returns:
        str: JSON 字符串
    """
    if hasattr(data, "__dataclass_fields__"):
        serialized = _serialize_dataclass(data)
    elif isinstance(data, list) and data and hasattr(data[0], "__dataclass_fields__"):
        serialized = [_serialize_dataclass(item) for item in data]
    else:
        serialized = data

    return json.dumps(serialized, ensure_ascii=False, indent=2)
