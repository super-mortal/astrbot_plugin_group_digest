"""插件统一时区工具。

插件面向中文用户，所有**用户可见的时间语义**（定时任务触发时刻、报告日期、
统计的分日边界、增量分析的滑动窗口）一律采用北京时间，与服务器所在时区无关。

实现要点：北京没有夏令时，直接使用固定 UTC+8 偏移即可，
不依赖系统时区数据库（Windows 上 ZoneInfo 常常缺少 tzdata）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

BEIJING_TZ = timezone(timedelta(hours=8))
"""北京时间时区（固定 UTC+8）。"""

BEIJING_TZ_LABEL = "北京时间（UTC+8）"
"""用于日志与提示文案的时区标签。"""

DATE_FORMAT = "%Y-%m-%d"
"""插件统一使用的日期格式。"""

DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
"""插件统一使用的日期时间格式。"""


def now_local() -> datetime:
    """获取当前北京时间（带时区信息）。

    Returns:
        datetime: 当前北京时间，tzinfo 为固定 UTC+8 偏移。
    """
    return datetime.now(BEIJING_TZ)


def today_local() -> datetime:
    """获取北京时间当天零点（带时区信息）。

    Returns:
        datetime: 北京时间当日 00:00:00。
    """
    return now_local().replace(hour=0, minute=0, second=0, microsecond=0)


def to_local(value: datetime) -> datetime:
    """把任意时间转换到北京时间。

    无时区信息（naive）的时间按服务器本地时区解释，与插件原有行为保持一致。

    Args:
        value: 待转换的时间对象。

    Returns:
        datetime: 转换后的北京时间。
    """
    if value.tzinfo is None:
        value = value.astimezone()
    return value.astimezone(BEIJING_TZ)


def format_local(value: datetime | None = None) -> str:
    """按插件统一格式输出北京时间字符串。

    Args:
        value: 待格式化的时间，留空表示当前时间。

    Returns:
        str: 形如 ``2026-09-28 21:30:00`` 的字符串。
    """
    return (value or now_local()).strftime(DATETIME_FORMAT)


def format_local_date(value: datetime | None = None) -> str:
    """按插件统一格式输出北京时间的日期部分。

    Args:
        value: 待格式化的时间，留空表示当前时间。

    Returns:
        str: 形如 ``2026-09-28`` 的字符串。
    """
    return (value or now_local()).strftime(DATE_FORMAT)


def format_local_pattern(pattern: str, value: datetime | None = None) -> str:
    """按自定义格式输出北京时间字符串。

    Args:
        pattern: strftime 格式串，例如 ``"%Y年%m月%d日"``。
        value: 待格式化的时间，留空表示当前时间。

    Returns:
        str: 格式化后的字符串。
    """
    return (value or now_local()).strftime(pattern)


def from_timestamp_local(timestamp: float) -> datetime:
    """把 Unix 时间戳转换为北京时间。

    与内置 ``datetime.fromtimestamp`` 不同，本函数不依赖服务器本地时区。

    Args:
        timestamp: Unix 时间戳（秒）。

    Returns:
        datetime: 对应的北京时间。
    """
    return datetime.fromtimestamp(timestamp, BEIJING_TZ)
