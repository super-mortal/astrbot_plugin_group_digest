"""
历史记录管理器模块 - 基础设施持久化层
负责存储和查询群聊分析报告的摘要信息
使用 AstrBot 的 put_kv_data/get_kv_data 实现
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import TYPE_CHECKING, cast

from ...utils.logger import logger
from ...utils.time_utils import format_local_date, now_local

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from astrbot.api.star import Star

HISTORY_INDEX_KEY = "analysis_history_index"
"""摘要 key 索引，用于自动清理时枚举历史记录。"""

_KEY_DATE_PATTERN = re.compile(r"^analysis_.+?_(\d{4}-\d{2}-\d{2})_")


class HistoryManager:
    """核心组件：历史分析存档管理器。

    该类负责将每日生成的群消息分析报告摘要持久化存储，并提供查询接口。
    底层基于 AstrBot 提供的 KV 存储能力（put_kv_data/get_kv_data），
    确保即使在 Bot 重启后也能回溯历史数据。
    """

    plugin: Star

    def __init__(self, star_instance: Star) -> None:
        """初始化历史记录管理器。

        Args:
            star_instance: Star 插件实例，用于访问底层持久化引擎。
        """
        self.plugin = star_instance

    async def save_analysis(
        self,
        group_id: str,
        analysis_result: dict[str, object],
        date_str: str | None = None,
        time_str: str | None = None,
    ) -> bool:
        """
        序列化并存储一份分析报告摘要。

        摘要包含：发言总量、人数、提取的主题摘要及生成时间，不包含完整的原始消息流。

        Args:
            group_id (str): 群组 ID
            analysis_result (dict[str, object]): 包含 statistics, topics, user_titles 的完整分析对象
            date_str (str, optional): 归档日期 (YYYY-MM-DD)，缺省为当天
            time_str (str, optional): 归档时间点 (HH-MM)，缺省为当前时刻

        Returns:
            bool: 存储是否成功
        """
        try:
            now = now_local()
            if not date_str:
                date_str = now.strftime("%Y-%m-%d")
            if not time_str:
                time_str = now.strftime("%H-%M")

            # 消解非法字符，确保 Key 兼容性
            time_str = time_str.replace(":", "-")

            # 从分析结果中剥离非持久化字段，提取核心统计元数据
            stats = analysis_result.get("statistics")
            topics_raw = analysis_result.get("topics")
            topics = topics_raw if isinstance(topics_raw, list) else []
            user_titles_raw = analysis_result.get("user_titles")
            user_titles = user_titles_raw if isinstance(user_titles_raw, list) else []

            topics_summary = []
            for t in topics:
                if isinstance(t, dict):
                    topics_summary.append(
                        {
                            "topic": str(t.get("topic", "")),
                            "detail": str(t.get("detail", "")),
                        }
                    )
                elif hasattr(t, "topic"):
                    topics_summary.append(
                        {
                            "topic": str(getattr(t, "topic", "")),
                            "detail": str(getattr(t, "detail", "")),
                        }
                    )

            summary = {
                "message_count": getattr(stats, "message_count", 0) if stats else 0,
                "participant_count": getattr(stats, "participant_count", 0)
                if stats
                else 0,
                "topics": topics_summary,
                "user_titles_count": len(user_titles),
                "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            }

            key = f"analysis_{group_id}_{date_str}_{time_str}"
            await self.plugin.put_kv_data(key, summary)
            await self._register_key_in_index(key)

            logger.info(
                f"已保存群 {group_id} 在 {date_str} {time_str} 的分析摘要到历史记录 (Key: {key})"
            )
            return True
        except Exception as e:
            logger.error(f"保存历史分析记录失败: {e}", exc_info=True)
            return False

    async def _register_key_in_index(self, key: str) -> None:
        """把摘要 key 登记到索引，供按保留天数自动清理时枚举。"""
        try:
            index = await self.plugin.get_kv_data(HISTORY_INDEX_KEY, [])
            keys = index if isinstance(index, list) else []
            if key not in keys:
                keys.append(key)
                await self.plugin.put_kv_data(HISTORY_INDEX_KEY, keys)
        except Exception as e:
            # 索引维护失败不影响摘要本身的保存
            logger.warning(f"维护历史摘要索引失败: {e}")

    async def cleanup_old_history(self, *, days: int) -> int:
        """删除超过保留期的历史摘要 KV 数据，并同步收缩索引。

        依赖 AstrBot >= 4.9.2 提供的 ``delete_kv_data``；旧版本上无法删除，
        将保留索引原样并返回 0。

        Args:
            days: 保留天数上限。

        Returns:
            int: 实际删除的摘要条数。
        """
        try:
            index = await self.plugin.get_kv_data(HISTORY_INDEX_KEY, [])
            keys = index if isinstance(index, list) else []
            if not keys:
                return 0

            cutoff_date = format_local_date(now_local() - timedelta(days=days))
            deleter = getattr(self.plugin, "delete_kv_data", None)
            if not callable(deleter):
                logger.warning(
                    "当前 AstrBot 版本不支持 delete_kv_data，跳过历史摘要清理。"
                )
                return 0

            kept: list[str] = []
            removed = 0
            for key in keys:
                match = _KEY_DATE_PATTERN.match(key)
                if match and match.group(1) < cutoff_date:
                    await cast("Callable[[str], Awaitable[None]]", deleter)(key)
                    removed += 1
                else:
                    kept.append(key)

            if removed:
                await self.plugin.put_kv_data(HISTORY_INDEX_KEY, kept)
                logger.info(
                    f"[数据保留] 已清理 {removed} 条超期历史摘要（保留 {days} 天）"
                )
            return removed
        except Exception as e:
            logger.warning(f"清理历史摘要失败: {e}")
            return 0

    async def get_analysis(
        self, group_id: str, date_str: str, time_str: str | None = None
    ) -> dict[str, object] | None:
        """根据群组和日期获取分析数据。

        如果指定了 time_str 则按精确 key 读取，否则检索该日期的分析记录。
        """
        if time_str:
            return await self.get_history(group_id, date_str, time_str)

        # 尝试常见或最新的 time_str 归档，若无具体时间点则尝试默认前缀 key
        key_default = f"analysis_{group_id}_{date_str}"
        res = await self.plugin.get_kv_data(key_default, None)
        if res:
            return res
        return None

    async def get_history(
        self, group_id: str, date_str: str, time_str: str
    ) -> dict[str, object] | None:
        """
        根据群组、日期和时间点检索一份历史摘要。
        """
        time_str = time_str.replace(":", "-")
        key = f"analysis_{group_id}_{date_str}_{time_str}"
        return await self.plugin.get_kv_data(key, None)

    async def has_history(self, group_id: str, date_str: str, time_str: str) -> bool:
        """
        快速判定是否存在指定时间点的历史分析记录。
        """
        history = await self.get_history(group_id, date_str, time_str)
        return history is not None
