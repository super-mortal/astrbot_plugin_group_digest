"""数据保留服务（DataRetentionService）单元测试。"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, Mock

from src.infrastructure.persistence.data_retention_service import DataRetentionService


def _build_config(enabled: bool = True, days: int = 7) -> SimpleNamespace:
    """构造带保留配置的最小配置管理器替身。"""
    return SimpleNamespace(
        get_enable_auto_cleanup=lambda: enabled,
        get_data_retention_days=lambda: days,
    )


def _make_report_file(root: Path, relative: str, age_days: float) -> Path:
    """在报告目录中生成一个指定“年龄”的文件。"""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    stamp = time.time() - age_days * 86400
    os.utime(path, (stamp, stamp))
    return path


def _run(service: DataRetentionService):
    return asyncio.run(service.run_cleanup())


def test_disabled_cleanup_touches_nothing(tmp_path: Path):
    """总开关关闭时不应调用任何清理，也不删除报告文件。"""
    trace_store = Mock()
    checkpoint_store = Mock()
    old_file = _make_report_file(tmp_path / "reports", "a/old.png", age_days=30)

    service = DataRetentionService(
        _build_config(enabled=False),
        trace_store,
        checkpoint_store,
        tmp_path / "reports",
    )
    stats = _run(service)

    trace_store.cleanup_old_traces.assert_not_called()
    checkpoint_store.cleanup_expired.assert_not_called()
    assert old_file.exists()
    assert stats.traces == 0 and stats.report_files == 0


def test_cleanup_removes_expired_traces_and_reports(tmp_path: Path):
    """开启后应按保留天数清理 Trace、过期 Checkpoint 与超期报告文件。"""
    reports = tmp_path / "reports"
    old_png = _make_report_file(reports, "20260901/old.png", age_days=10)
    fresh_png = _make_report_file(reports, "20260901/fresh.png", age_days=1)

    trace_store = Mock()
    trace_store.cleanup_old_traces.return_value = 42
    checkpoint_store = Mock()
    checkpoint_store.cleanup_expired.return_value = 3

    service = DataRetentionService(
        _build_config(enabled=True, days=7),
        trace_store,
        checkpoint_store,
        reports,
    )
    stats = _run(service)

    trace_store.cleanup_old_traces.assert_called_once_with(days=7)
    checkpoint_store.cleanup_expired.assert_called_once()
    assert stats.traces == 42
    assert stats.checkpoints == 3
    assert stats.report_files == 1
    assert stats.report_bytes > 0
    assert not old_png.exists()
    assert fresh_png.exists()


def test_cleanup_prunes_empty_dirs_but_keeps_root(tmp_path: Path):
    """清理后应移除变空的子目录，但保留根目录本身。"""
    reports = tmp_path / "reports"
    _make_report_file(reports, "group_a/old.html", age_days=20)

    service = DataRetentionService(_build_config(days=7), Mock(), Mock(), reports)
    _run(service)

    assert reports.exists()
    assert not (reports / "group_a").exists()


def test_store_failures_do_not_block_other_partitions(tmp_path: Path):
    """单个分区清理异常时，其余分区仍应继续执行。"""
    reports = tmp_path / "reports"
    old_file = _make_report_file(reports, "old.png", age_days=10)

    trace_store = Mock()
    trace_store.cleanup_old_traces.side_effect = RuntimeError("db locked")
    checkpoint_store = Mock()
    checkpoint_store.cleanup_expired.side_effect = RuntimeError("db locked")

    service = DataRetentionService(
        _build_config(days=7), trace_store, checkpoint_store, reports
    )
    stats = _run(service)

    assert stats.traces == 0 and stats.checkpoints == 0
    assert stats.report_files == 1
    assert not old_file.exists()


def test_missing_store_methods_are_tolerated(tmp_path: Path):
    """存储对象缺少清理方法时应视为零删除，而不是抛错。"""
    service = DataRetentionService(
        _build_config(days=7),
        SimpleNamespace(),
        SimpleNamespace(),
        tmp_path / "not-exist",
    )
    stats = _run(service)

    assert stats == type(stats)()


def test_cleanup_also_purges_kv_history_and_batches(tmp_path: Path):
    """KV 历史摘要与增量批次应纳入统一清理并计入统计。"""
    history_manager = SimpleNamespace(cleanup_old_history=AsyncMock(return_value=5))
    incremental_store = SimpleNamespace(
        get_tracked_groups=AsyncMock(return_value=["123456", "654321"]),
        cleanup_old_batches=AsyncMock(return_value=2),
    )

    service = DataRetentionService(
        _build_config(days=7),
        Mock(),
        Mock(),
        tmp_path / "reports",
        history_manager=history_manager,
        incremental_store=incremental_store,
    )
    stats = _run(service)

    history_manager.cleanup_old_history.assert_awaited_once_with(days=7)
    assert stats.history_summaries == 5
    assert stats.incremental_batches == 4  # 两个群各清 2 条
    incremental_store.cleanup_old_batches.assert_any_await("123456", ANY)
    incremental_store.cleanup_old_batches.assert_any_await("654321", ANY)


def test_cleanup_also_purges_expired_cache_files(tmp_path: Path):
    """头像缓存与临时渲染缓存中的超期文件应被统一清理。"""
    avatars = tmp_path / "cache" / "avatars"
    temp_dir = tmp_path / "temp"
    old_avatar = _make_report_file(avatars, "old_avatar.png", age_days=10)
    fresh_avatar = _make_report_file(avatars, "fresh_avatar.png", age_days=1)
    old_temp = _make_report_file(temp_dir, "io_temp_img_20260901.png", age_days=10)
    other_temp = _make_report_file(temp_dir, "unrelated_20260901.txt", age_days=10)

    service = DataRetentionService(
        _build_config(days=7),
        Mock(),
        Mock(),
        tmp_path / "reports",
        avatar_dir=avatars,
        temp_dir=temp_dir,
    )
    stats = _run(service)

    assert not old_avatar.exists()
    assert fresh_avatar.exists()
    assert not old_temp.exists()
    assert other_temp.exists()  # 非本插件前缀的文件不触碰
    assert stats.cache_files == 2


def test_kv_cleanup_failures_do_not_block_file_cleanup(tmp_path: Path):
    """KV 侧清理异常不应影响 Trace 与报告文件清理。"""
    reports = tmp_path / "reports"
    old_file = _make_report_file(reports, "old.png", age_days=10)

    history_manager = SimpleNamespace(
        cleanup_old_history=AsyncMock(side_effect=RuntimeError("kv down"))
    )
    incremental_store = SimpleNamespace(
        get_tracked_groups=AsyncMock(side_effect=RuntimeError("kv down"))
    )

    service = DataRetentionService(
        _build_config(days=7),
        Mock(),
        Mock(),
        reports,
        history_manager=history_manager,
        incremental_store=incremental_store,
    )
    stats = _run(service)

    assert stats.history_summaries == 0 and stats.incremental_batches == 0
    assert stats.report_files == 1
    assert not old_file.exists()
