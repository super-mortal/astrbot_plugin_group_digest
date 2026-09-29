"""数据保留与自动清理服务。

按「数据保留」配置定期清理插件运行过程中产生的占盘数据，覆盖全部本地数据：

1. ``traces.db`` 中的 Trace 执行记录（按保留天数）；
2. 已过期的增量分析 Checkpoint（按记录自身 TTL，与保留天数无关）；
3. 报告文件目录（``plugin_data/reports``）中超期的图片 / HTML 报告文件；
4. KV 存储中的历史报告摘要（按摘要 key 中的日期判定保留期，需索引登记）；
5. KV 存储中的增量分析批次（按批次时间戳，逐群清理）；
6. 群成员头像缓存与临时渲染缓存（按文件修改时间，超期即删）。

另有两类不按天数：配置升级备份按数量保留（最新 5 份），已在生成流程结束时
用完即删的临时文件不经过本服务。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from time import time
from typing import TYPE_CHECKING, Protocol

from ...utils.logger import logger

if TYPE_CHECKING:
    from ..config.config_manager import ConfigManager

_TEMP_FILE_PREFIX = "io_temp_img_"
"""AstrBot 全局 temp 目录中属于本插件临时渲染缓存的文件前缀。"""


class _TraceCleanupProtocol(Protocol):
    """Trace 存储所需的清理能力。"""

    def cleanup_old_traces(self, *, days: int) -> int:
        """按保留天数删除过期 Trace 记录。"""
        ...


class _CheckpointCleanupProtocol(Protocol):
    """Checkpoint 存储所需的清理能力。"""

    def cleanup_expired(self) -> int:
        """删除已过期的 Checkpoint 记录。"""
        ...


class _HistoryCleanupProtocol(Protocol):
    """历史摘要管理器所需的清理能力。"""

    async def cleanup_old_history(self, *, days: int) -> int:
        """按保留天数删除过期摘要并收缩索引。"""
        ...


class _BatchCleanupProtocol(Protocol):
    """增量批次存储所需的清理能力。"""

    async def get_tracked_groups(self) -> list[str]:
        """列出所有登记过批次的群号。"""
        ...

    async def cleanup_old_batches(self, group_id: str, before_timestamp: float) -> int:
        """删除指定群早于时间戳的全部批次。"""
        ...


@dataclass(frozen=True)
class CleanupStats:
    """一轮清理的统计结果。

    Attributes:
        traces: 删除的 Trace 记录条数。
        checkpoints: 删除的过期 Checkpoint 条数。
        report_files: 删除的报告文件个数。
        report_bytes: 释放的报告文件字节数。
        history_summaries: 删除的 KV 历史摘要条数。
        incremental_batches: 删除的 KV 增量批次条数。
        cache_files: 删除的缓存文件个数（头像 + 临时渲染图）。
    """

    traces: int = 0
    checkpoints: int = 0
    report_files: int = 0
    report_bytes: int = 0
    history_summaries: int = 0
    incremental_batches: int = 0
    cache_files: int = 0


class DataRetentionService:
    """基础设施服务：执行插件运行数据的周期性清理。"""

    def __init__(
        self,
        config_manager: ConfigManager,
        trace_store: _TraceCleanupProtocol | None,
        checkpoint_store: _CheckpointCleanupProtocol | None,
        report_output_dir: Path | None,
        history_manager: _HistoryCleanupProtocol | None = None,
        incremental_store: _BatchCleanupProtocol | None = None,
        avatar_dir: Path | None = None,
        temp_dir: Path | None = None,
    ) -> None:
        """初始化清理服务。

        Args:
            config_manager: 配置管理器，提供保留开关与天数。
            trace_store: Trace SQLite 存储实例，需具备 ``cleanup_old_traces`` 方法。
            checkpoint_store: Checkpoint 存储实例，需具备 ``cleanup_expired`` 方法。
            report_output_dir: 报告文件输出目录，留空表示跳过文件清理。
            history_manager: 历史摘要管理器（KV 存储），需具备 ``cleanup_old_history`` 方法。
            incremental_store: 增量批次存储，需具备 ``get_tracked_groups`` 与
                ``cleanup_old_batches`` 方法。
            avatar_dir: 群成员头像缓存目录。
            temp_dir: AstrBot 全局 temp 目录，仅清理本插件产生的临时渲染图。
        """
        self.config_manager = config_manager
        self.trace_store: _TraceCleanupProtocol | None = trace_store
        self.checkpoint_store: _CheckpointCleanupProtocol | None = checkpoint_store
        self.report_output_dir = report_output_dir
        self.history_manager: _HistoryCleanupProtocol | None = history_manager
        self.incremental_store: _BatchCleanupProtocol | None = incremental_store
        self.avatar_dir = avatar_dir
        self.temp_dir = temp_dir

    async def run_cleanup(self) -> CleanupStats:
        """执行一轮清理，返回各项删除量统计。

        Returns:
            CleanupStats: 各分区删除量；总开关关闭时返回全零统计。
        """
        if not self.config_manager.get_enable_auto_cleanup():
            return CleanupStats()

        days = self.config_manager.get_data_retention_days()

        (
            traces,
            checkpoints,
            report_files,
            report_bytes,
            cache_files,
        ) = await asyncio.to_thread(self._run_sync_cleanups, days)
        history_summaries = await self._cleanup_history(days)
        incremental_batches = await self._cleanup_batches(days)

        stats = CleanupStats(
            traces=traces,
            checkpoints=checkpoints,
            report_files=report_files,
            report_bytes=report_bytes,
            history_summaries=history_summaries,
            incremental_batches=incremental_batches,
            cache_files=cache_files,
        )
        logger.info(
            f"[数据保留] 自动清理完成（保留 {days} 天）："
            f"Trace {stats.traces} 条、过期 Checkpoint {stats.checkpoints} 条、"
            f"报告文件 {stats.report_files} 个"
            f"（释放 {stats.report_bytes / 1024 / 1024:.2f} MB）、"
            f"历史摘要 {stats.history_summaries} 条、增量批次 {stats.incremental_batches} 条、"
            f"缓存文件 {stats.cache_files} 个"
        )
        return stats

    def _run_sync_cleanups(self, days: int) -> tuple[int, int, int, int, int]:
        """执行同步类清理，返回 (traces, checkpoints, files, bytes, cache_files)。"""
        return (
            self._cleanup_traces(days),
            self._cleanup_checkpoints(),
            *self._cleanup_report_files(days),
            self._cleanup_cache_files(days),
        )

    def _cleanup_traces(self, days: int) -> int:
        """按保留天数清理 Trace 记录，失败时不影响其它分区。"""
        store = self.trace_store
        if store is None:
            return 0
        try:
            return int(store.cleanup_old_traces(days=days))
        except Exception as e:
            logger.warning(f"[数据保留] 清理 Trace 记录失败：{e}")
            return 0

    def _cleanup_checkpoints(self) -> int:
        """清理已过期的 Checkpoint，失败时不影响其它分区。"""
        store = self.checkpoint_store
        if store is None:
            return 0
        try:
            return int(store.cleanup_expired())
        except Exception as e:
            logger.warning(f"[数据保留] 清理过期 Checkpoint 失败：{e}")
            return 0

    def _cleanup_report_files(self, days: int) -> tuple[int, int]:
        """删除报告目录中超期的文件，并清掉因此变空的子目录。

        Args:
            days: 保留天数上限。

        Returns:
            tuple[int, int]: (删除文件个数, 释放字节数)。
        """
        root = self.report_output_dir
        if root is None or not root.exists():
            return 0, 0

        cutoff = time() - days * 86400
        deleted_files = 0
        freed_bytes = 0
        try:
            for path in sorted(root.rglob("*")):
                if path.is_file() and path.stat().st_mtime < cutoff:
                    size = path.stat().st_size
                    path.unlink()
                    deleted_files += 1
                    freed_bytes += size

            # 自底向上移除因清理而变空的子目录（保留根目录本身）
            for dir_path in sorted(
                (p for p in root.rglob("*") if p.is_dir()),
                key=lambda p: len(p.parts),
                reverse=True,
            ):
                if not any(dir_path.iterdir()):
                    dir_path.rmdir()
        except Exception as e:
            logger.warning(f"[数据保留] 清理报告文件失败：{e}")
            return deleted_files, freed_bytes
        return deleted_files, freed_bytes

    def _cleanup_cache_files(self, days: int) -> int:
        """按保留天数清理头像缓存与临时渲染缓存文件。

        临时渲染缓存只删本插件产生的前缀文件（``io_temp_img_*``），
        不触碰 AstrBot 全局 temp 目录中的其它内容。

        Args:
            days: 保留天数上限。

        Returns:
            int: 删除的缓存文件个数。
        """
        cutoff = time() - days * 86400
        removed = 0
        for directory, prefix_only in (
            (self.avatar_dir, False),
            (self._resolve_temp_dir(), True),
        ):
            if directory is None or not directory.exists():
                continue
            try:
                for path in directory.rglob("*"):
                    if not path.is_file():
                        continue
                    if prefix_only and not path.name.startswith(_TEMP_FILE_PREFIX):
                        continue
                    if path.stat().st_mtime < cutoff:
                        path.unlink()
                        removed += 1
            except Exception as e:
                logger.warning(f"[数据保留] 清理缓存目录 {directory} 失败：{e}")
        return removed

    def _resolve_temp_dir(self) -> Path | None:
        """惰性解析 AstrBot 全局 temp 目录，失败时返回 None。"""
        if self.temp_dir is not None:
            return self.temp_dir
        try:
            from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

            return Path(get_astrbot_temp_path())
        except Exception:
            return None

    async def _cleanup_history(self, days: int) -> int:
        """按保留天数清理 KV 中的历史报告摘要。"""
        manager = self.history_manager
        if manager is None:
            return 0
        try:
            return int(await manager.cleanup_old_history(days=days))
        except Exception as e:
            logger.warning(f"[数据保留] 清理历史摘要失败：{e}")
            return 0

    async def _cleanup_batches(self, days: int) -> int:
        """按保留天数清理 KV 中各群的增量分析批次。"""
        store = self.incremental_store
        if store is None:
            return 0

        try:
            group_ids = await store.get_tracked_groups()
        except Exception as e:
            logger.warning(f"[数据保留] 枚举增量批次群组失败：{e}")
            return 0

        cutoff = time() - days * 86400
        removed = 0
        for group_id in group_ids:
            try:
                removed += int(await store.cleanup_old_batches(group_id, cutoff))
            except Exception as e:
                logger.warning(f"[数据保留] 清理群 {group_id} 增量批次失败：{e}")
        return removed
