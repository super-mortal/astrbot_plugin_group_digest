"""插件统一时区工具单元测试。

验证北京时间固定偏移、与服务器时区无关，以及日期时间格式输出。
"""

from datetime import datetime, timedelta, timezone

from src.utils.time_utils import (
    BEIJING_TZ,
    format_local,
    format_local_date,
    now_local,
    to_local,
    today_local,
)


def test_beijing_tz_is_fixed_utc_plus_8():
    """测试北京时间使用固定 UTC+8 偏移，不依赖时区数据库"""
    assert BEIJING_TZ.utcoffset(None) == timedelta(hours=8)


def test_now_local_carries_beijing_offset():
    """测试当前时间带北京时间时区信息"""
    current = now_local()

    assert current.tzinfo is BEIJING_TZ
    assert current.utcoffset() == timedelta(hours=8)


def test_today_local_is_midnight():
    """测试当天零点保留时区且时分秒归零"""
    midnight = today_local()

    assert (midnight.hour, midnight.minute, midnight.second, midnight.microsecond) == (
        0,
        0,
        0,
        0,
    )
    assert midnight.tzinfo is BEIJING_TZ


def test_to_local_converts_other_timezones():
    """测试其他时区的时间被正确换算为北京时间"""
    # 纽约（UTC-4）中午 12:00 对应北京时间次日 00:00
    new_york_noon = datetime(2026, 9, 28, 12, 0, tzinfo=timezone(timedelta(hours=-4)))
    converted = to_local(new_york_noon)

    assert converted.hour == 0
    assert converted.day == 29
    assert converted.utcoffset() == timedelta(hours=8)


def test_format_helpers_use_plugin_formats():
    """测试格式化工具输出插件统一格式"""
    moment = datetime(2026, 9, 28, 21, 30, 5, tzinfo=BEIJING_TZ)

    assert format_local(moment) == "2026-09-28 21:30:05"
    assert format_local_date(moment) == "2026-09-28"
