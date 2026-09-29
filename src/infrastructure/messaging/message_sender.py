from __future__ import annotations

import os
from typing import TYPE_CHECKING

from ...utils.logger import logger

if TYPE_CHECKING:
    from collections.abc import Sequence

    from astrbot.api.event import MessageChain

    from ...domain.value_objects.delivery_target import DeliveryTarget
    from ..config.config_manager import ConfigManager
    from ..platform.bot_manager import BotManager


class MessageSender:
    """
    消息发送器
    封装了 PlatformAdapter 的底层调用，提供更高层的发送接口
    """

    bot_manager: BotManager
    config_manager: ConfigManager

    def __init__(
        self,
        bot_manager: BotManager,
        config_manager: ConfigManager,
    ) -> None:
        self.bot_manager = bot_manager
        self.config_manager = config_manager

    async def send_text(
        self, group_id: str, text: str, platform_id: str | None = None
    ) -> bool:
        """发送文本消息"""
        adapter = self.bot_manager.get_adapter(platform_id)
        if not adapter:
            logger.error(f"[MessageSender] 未找到平台 {platform_id} 的适配器")
            return False
        return await adapter.send_text(group_id, text)

    async def send_image_smart(
        self,
        group_id: str,
        image_url: str,
        caption: str = "",
        platform_id: str | None = None,
    ) -> bool:
        """智能发送图片，支持自动选择适配器"""
        adapter = self.bot_manager.get_adapter(platform_id)
        if not adapter:
            logger.error(f"[MessageSender] 未找到平台 {platform_id} 的适配器")
            return False
        return await adapter.send_image(group_id, image_url, caption)

    async def send_file(
        self,
        group_id: str,
        file_path: str,
        caption: str = "",
        platform_id: str | None = None,
    ) -> bool:
        """发送文件（HTML/PDF/其它文件）。支持可选 caption。"""
        adapter = self.bot_manager.get_adapter(platform_id)
        if not adapter:
            logger.error(f"[MessageSender] 未找到平台 {platform_id} 的适配器")
            return False

        # 首先发送文件，本方法的返回值只代表文件是否发送成功。
        file_sent = await adapter.send_file(group_id, file_path)

        if not file_sent:
            # 适配器返回 False，表示文件未成功发送
            return False

        # 文件已成功发送，下面的 caption 发送为尽力而为，不影响整体成功与否。
        if caption:
            try:
                caption_sent = await adapter.send_text(group_id, f"{caption}")
                if not caption_sent:
                    logger.warning(
                        "[MessageSender] 文件已发送，但 caption 发送失败（适配器返回 False）"
                    )
            except Exception as e:
                logger.warning(f"[MessageSender] 文件已发送，但 caption 发送异常: {e}")

        return True

    async def send_report_to_target(
        self,
        target: DeliveryTarget,
        *,
        image_ref: str = "",
        file_path: str = "",
        text: str = "",
        caption: str = "",
    ) -> bool:
        """把报告投递到任意会话（群聊或私聊）。

        该通道基于 AstrBot 的主动消息能力实现，与源会话所在的平台适配器解耦，
        因此天然支持跨群、跨私聊乃至跨平台投递。它只负责「把报告送到指定会话」，
        不承担群相册归档、群文件整理等平台专属增强，那些仍由原群投递链路处理。

        Args:
            target: 投递目标会话。
            image_ref: 图片引用，支持公网 URL、本地路径、``base64://`` 与 ``data:`` 形式。
            file_path: 需要作为文件发送的本地路径或公网 URL。
            text: 作为正文发送的文本内容。
            caption: 附在图片/文件之前的说明文本。

        Returns:
            bool: 投递成功返回 True；上下文不可用、内容为空或发送异常时返回 False。
        """
        context = self.bot_manager.get_context()
        if context is None:
            logger.error(
                f"[MessageSender] AstrBot 上下文不可用，无法向 {target.umo} 投递报告"
            )
            return False

        if not (image_ref or file_path or text or caption):
            logger.warning(f"[MessageSender] 投递内容为空，已跳过目标 {target.umo}")
            return False

        from astrbot.api.event import MessageChain

        chain = MessageChain()
        if caption:
            chain.message(caption)
        if text:
            chain.message(text)
        if image_ref:
            self._append_image(chain, image_ref)
        if file_path:
            self._append_file(chain, file_path)

        try:
            return bool(await context.send_message(target.umo, chain))
        except Exception as e:
            logger.error(
                f"[MessageSender] 向 {target.umo} 投递报告失败: {e}",
                exc_info=True,
            )
            return False

    async def deliver_to_targets(
        self,
        targets: Sequence[DeliveryTarget],
        *,
        image_ref: str = "",
        file_path: str = "",
        text: str = "",
        caption: str = "",
    ) -> int:
        """向多个投递目标批量发送同一份报告。

        Args:
            targets: 投递目标列表。
            image_ref: 图片引用，支持公网 URL、本地路径、``base64://`` 与 ``data:`` 形式。
            file_path: 需要作为文件发送的本地路径或公网 URL。
            text: 作为正文发送的文本内容。
            caption: 附在图片/文件之前的说明文本。

        Returns:
            int: 成功投递的目标数量。
        """
        if not targets:
            return 0

        succeeded = 0
        for target in targets:
            delivered = await self.send_report_to_target(
                target,
                image_ref=image_ref,
                file_path=file_path,
                text=text,
                caption=caption,
            )
            if delivered:
                succeeded += 1
                logger.info(f"[投递] 报告已投递到 {target.umo}")
            else:
                logger.warning(f"[投递] 报告投递失败：{target.umo}")
        return succeeded

    @staticmethod
    def _append_image(chain: MessageChain, image_ref: str) -> None:
        """按引用形态把图片追加到消息链。

        Args:
            chain: 待追加的消息链。
            image_ref: 图片引用，支持 base64、data URI、公网 URL 与本地路径。
        """
        if image_ref.startswith("base64://"):
            chain.base64_image(image_ref[len("base64://") :])
        elif image_ref.startswith("data:") and "," in image_ref:
            chain.base64_image(image_ref.split(",", 1)[1])
        elif image_ref.startswith(("http://", "https://")):
            chain.url_image(image_ref)
        else:
            chain.file_image(os.path.abspath(image_ref))

    @staticmethod
    def _append_file(chain: MessageChain, file_path: str) -> None:
        """把文件组件追加到消息链。

        Args:
            chain: 待追加的消息链。
            file_path: 文件的本地路径或公网 URL。
        """
        from astrbot.core.message.components import File

        name = os.path.basename(file_path) or "report"
        if file_path.startswith(("http://", "https://")):
            chain.chain.append(File(name=name, url=file_path))
        else:
            chain.chain.append(File(name=name, file=os.path.abspath(file_path)))

    def _get_available_platforms(self, group_id: str):
        """获取可用的平台列表 (Helper for Dispatcher)"""
        # 简单实现：返回所有已加载的平台
        return [(pid, None) for pid in self.bot_manager.get_platform_ids()]
