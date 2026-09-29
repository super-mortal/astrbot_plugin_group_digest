"""遥控指令处理器 (Remote Command Handler)。

处理「群列表查询」与「远程触发指定群分析」两条指令，
使管理员可以在私聊等任意会话中遥控插件分析指定群聊。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...domain.services.delivery_target_resolver import DeliveryTargetResolver
from ...domain.value_objects.delivery_target import DeliveryTarget
from ...utils.logger import logger

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from astrbot.api.event import AstrMessageEvent, MessageEventResult

    from ...infrastructure.config.config_manager import ConfigManager
    from ...infrastructure.platform.bot_manager import BotManager
    from .analysis_command_handler import AnalysisCommandHandler

MAX_REMOTE_GROUPS = 50
"""单次列出的可遥控群数量上限，避免超长消息刷屏。"""


class RemoteCommandHandler:
    """遥控指令应用层处理器。

    Attributes:
        config_manager: 配置管理器，用于读取群聊白名单。
        bot_manager: Bot 管理器，用于获取平台适配器与群名称。
        analysis_handler: 群分析指令处理器，复用其完整分析流程。
    """

    config_manager: ConfigManager
    bot_manager: BotManager
    analysis_handler: AnalysisCommandHandler

    def __init__(
        self,
        config_manager: ConfigManager,
        bot_manager: BotManager,
        analysis_handler: AnalysisCommandHandler,
    ) -> None:
        """初始化遥控指令处理器。

        Args:
            config_manager: 配置管理器。
            bot_manager: Bot 管理器。
            analysis_handler: 群分析指令处理器。
        """
        self.config_manager = config_manager
        self.bot_manager = bot_manager
        self.analysis_handler = analysis_handler

    def _get_platform_id_from_event(self, event: AstrMessageEvent) -> str:
        """获取事件所属平台 ID，作为群号的默认平台。

        Args:
            event: AstrBot 消息事件对象。

        Returns:
            str: 平台实例 ID，获取失败时回退为 default。
        """
        try:
            return event.get_platform_id()
        except Exception:
            platform_meta = getattr(event, "platform_meta", None)
            platform_meta_id = getattr(platform_meta, "id", None)
            return str(platform_meta_id) if platform_meta_id else "default"

    async def _resolve_targets(self, event: AstrMessageEvent) -> list[DeliveryTarget]:
        """把群聊白名单解析为可遥控的群聊目标列表。

        复用插件现有的「基础设置 → 群组白/黑名单列表」作为可遥控群清单：
        纯数字条目按当前平台推断，完整会话 ID 条目按其中声明的平台解析。

        Args:
            event: AstrBot 消息事件对象，用于推断默认平台。

        Returns:
            list[DeliveryTarget]: 去重后的群聊目标列表（最多 MAX_REMOTE_GROUPS 个）。
        """
        default_platform = self._get_platform_id_from_event(event)
        targets: list[DeliveryTarget] = []
        seen: set[str] = set()

        for raw in self.config_manager.get_group_list():
            entry = str(raw).strip()
            if not entry:
                continue
            parsed = DeliveryTarget.parse(entry, default_platform_id=default_platform)
            if parsed is None or not parsed.is_group:
                logger.warning(f"[遥控] 跳过无法解析的群条目：{entry!r}")
                continue
            if parsed.umo in seen:
                continue
            seen.add(parsed.umo)
            targets.append(parsed)
            if len(targets) >= MAX_REMOTE_GROUPS:
                logger.info(
                    f"[遥控] 可遥控群数量超过 {MAX_REMOTE_GROUPS} 个，仅列出前 "
                    f"{MAX_REMOTE_GROUPS} 个。"
                )
                break

        return targets

    async def _get_group_display_name(self, target: DeliveryTarget) -> str:
        """尽力获取群名称，获取不到时回退为群号。

        Args:
            target: 群聊投递目标。

        Returns:
            str: 用于展示的群名称。
        """
        try:
            adapter = self.bot_manager.get_adapter(target.platform_id)
            if adapter:
                info = await adapter.get_group_info(target.session_id)
                if info and info.group_name:
                    return info.group_name
        except Exception as e:
            logger.debug(f"[遥控] 获取群 {target.umo} 的名称失败：{e}")
        return target.session_id

    async def handle_group_list(
        self, event: AstrMessageEvent
    ) -> AsyncGenerator[MessageEventResult]:
        """处理 /群列表 指令，列出可遥控的群聊及编号。

        Args:
            event: AstrBot 消息事件对象。

        Yields:
            MessageEventResult: 群列表消息。
        """
        targets = await self._resolve_targets(event)
        if not targets:
            yield event.plain_result(
                "📋 暂无可遥控的群聊。\n"
                "请先在插件配置的「基础设置 → 群组白/黑名单列表」中加入目标群，"
                "可填群号，也可填完整会话 ID（如 aiocqhttp:GroupMessage:123456）。"
            )
            return

        lines = ["📋 可遥控的群聊列表：", ""]
        for index, target in enumerate(targets, start=1):
            name = await self._get_group_display_name(target)
            lines.append(f"{index}. {name}")
            lines.append(f"　　{target.umo}")
        lines.append("")
        lines.append("发送 /远程分析 <编号> [天数] 即可触发分析。")
        yield event.plain_result("\n".join(lines))

    async def handle_remote_analysis(
        self,
        event: AstrMessageEvent,
        index: int | None = None,
        days: int | None = None,
    ) -> AsyncGenerator[MessageEventResult]:
        """处理 /远程分析 指令，分析指定编号的群聊。

        Args:
            event: AstrBot 消息事件对象。
            index: 群编号，与 /群列表 输出的序号对应。
            days: 分析回溯天数（可选），留空使用配置中的默认天数。

        Yields:
            MessageEventResult: 分析流程的响应消息。
        """
        targets = await self._resolve_targets(event)
        if not targets:
            yield event.plain_result(
                "❌ 暂无可遥控的群聊，请先在「基础设置 → 群组白/黑名单列表」中配置。"
            )
            return

        if index is None:
            yield event.plain_result("❌ 请指定群编号，可先发送 /群列表 查看编号。")
            return

        if index < 1 or index > len(targets):
            yield event.plain_result(
                f"❌ 群编号 {index} 不存在，当前可选范围是 1 ~ {len(targets)}。"
            )
            return

        target = targets[index - 1]
        logger.info(f"[遥控] 触发 {target.umo} 的分析，天数={days}")

        async for result in self.analysis_handler.handle_daily_analysis(
            event, days, target=target
        ):
            yield result

        notice = await self._build_delivery_notice(event, target)
        if notice:
            yield event.plain_result(notice)

    async def _build_delivery_notice(
        self, event: AstrMessageEvent, target: DeliveryTarget
    ) -> str:
        """在报告不会回到当前会话时，告知遥控方报告的真实去向。

        Args:
            event: AstrBot 消息事件对象（遥控发起的会话）。
            target: 被分析的群聊目标。

        Returns:
            str: 需要追加的提示文本；报告本就会回到当前会话时返回空字符串。
        """
        current_umo = str(getattr(event, "unified_msg_origin", "") or "")
        if not current_umo:
            return ""

        origin = DeliveryTarget.for_group(target.platform_id, target.session_id)
        resolved = DeliveryTargetResolver.resolve(
            origin,
            self.config_manager.get_delivery_rules(),
            enabled=self.config_manager.get_delivery_enabled(),
        )
        if current_umo in {item.umo for item in resolved}:
            return ""

        return (
            f"ℹ️「{target.session_id}」的报告按当前投递规则发往了其他会话。\n"
            "如需发到本会话，请在插件后台的「报告投递」中添加一条指向本会话的规则。"
        )
