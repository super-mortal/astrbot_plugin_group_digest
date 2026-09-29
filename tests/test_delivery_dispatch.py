"""报告投递通道与分发规则集成测试。

覆盖 MessageSender 的跨会话投递能力，以及 ReportDispatcher 按投递规则
决定「是否仍发原群」与「额外投递到哪些会话」的行为。
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from src.domain.value_objects.delivery_target import DeliveryTarget
from src.infrastructure.messaging.message_sender import MessageSender
from src.infrastructure.reporting.dispatcher import ReportDispatcher


class FakeContext:
    """记录 AstrBot 主动消息调用的最小上下文替身。"""

    def __init__(self):
        self.sent: list = []

    async def send_message(self, session, chain):
        self.sent.append((session, chain))
        return True


class FakeBotManager:
    """仅暴露投递所需能力的管理器替身。"""

    def __init__(self, context):
        self._context = context

    def get_context(self):
        return self._context

    def get_adapter(self, platform_id):
        return None

    def get_platform_ids(self):
        return []


def _build_dispatcher(config_manager, message_sender, text_report="报告正文"):
    report_generator = SimpleNamespace(
        generate_text_report=Mock(return_value=text_report),
        generate_markdown_report=AsyncMock(return_value=(text_report, "")),
    )
    return ReportDispatcher(config_manager, report_generator, message_sender)


def test_message_sender_delivers_to_every_target():
    """测试批量投递会逐个会话发送，并按目标类型生成正确的 UMO"""

    async def scenario():
        context = FakeContext()
        sender = MessageSender(FakeBotManager(context), SimpleNamespace())
        targets = [
            DeliveryTarget.for_group("onebot-main", "888888"),
            DeliveryTarget.for_friend("onebot-main", "10001"),
        ]

        succeeded = await sender.deliver_to_targets(
            targets,
            image_ref="https://example.com/report.png",
            caption="每日报告",
        )

        assert succeeded == 2
        assert [session for session, _ in context.sent] == [
            "onebot-main:GroupMessage:888888",
            "onebot-main:FriendMessage:10001",
        ]
        # 说明文本 + 图片组件
        assert len(context.sent[0][1].chain) == 2

    asyncio.run(scenario())


def test_message_sender_degrades_gracefully_without_context():
    """测试上下文不可用时投递失败而非抛出异常"""

    async def scenario():
        sender = MessageSender(FakeBotManager(None), SimpleNamespace())
        target = DeliveryTarget.for_group("onebot-main", "888888")

        assert await sender.send_report_to_target(target, text="x") is False
        assert await sender.deliver_to_targets([target], text="x") == 0

    asyncio.run(scenario())


def test_dispatcher_skips_origin_when_rule_points_elsewhere():
    """测试规则把我群指向其他群时，原群不再收到报告"""

    async def scenario():
        config_manager = SimpleNamespace(
            get_output_format=Mock(return_value=["text"]),
            get_delivery_rules=Mock(
                return_value=[{"source_group": "", "target": "888888", "enabled": True}]
            ),
            get_delivery_enabled=Mock(return_value=True),
        )
        message_sender = SimpleNamespace(
            bot_manager=FakeBotManager(None),
            send_text=AsyncMock(return_value=True),
            deliver_to_targets=AsyncMock(return_value=1),
        )
        dispatcher = _build_dispatcher(config_manager, message_sender)

        ok = await dispatcher.dispatch("123456", {}, "onebot-main")

        assert ok is True
        message_sender.send_text.assert_not_awaited()
        delivered = message_sender.deliver_to_targets.await_args.args[0]
        assert [target.umo for target in delivered] == [
            "onebot-main:GroupMessage:888888"
        ]

    asyncio.run(scenario())


def test_dispatcher_sends_to_origin_and_extra_target_together():
    """测试规则同时包含原群与其他群时，两处都会收到报告"""

    async def scenario():
        config_manager = SimpleNamespace(
            get_output_format=Mock(return_value=["text"]),
            get_delivery_rules=Mock(
                return_value=[
                    {"source_group": "123456", "target": "", "enabled": True},
                    {"source_group": "123456", "target": "888888", "enabled": True},
                ]
            ),
            get_delivery_enabled=Mock(return_value=True),
        )
        message_sender = SimpleNamespace(
            bot_manager=FakeBotManager(None),
            send_text=AsyncMock(return_value=True),
            deliver_to_targets=AsyncMock(return_value=1),
        )
        dispatcher = _build_dispatcher(config_manager, message_sender)

        ok = await dispatcher.dispatch("123456", {}, "onebot-main")

        assert ok is True
        message_sender.send_text.assert_awaited_once()
        delivered = message_sender.deliver_to_targets.await_args.args[0]
        assert [target.umo for target in delivered] == [
            "onebot-main:GroupMessage:888888"
        ]

    asyncio.run(scenario())


def test_dispatcher_keeps_legacy_behaviour_when_delivery_disabled():
    """测试投递未启用时完全走原有路径，不产生额外投递"""

    async def scenario():
        config_manager = SimpleNamespace(
            get_output_format=Mock(return_value=["text"]),
            get_delivery_rules=Mock(return_value=[]),
            get_delivery_enabled=Mock(return_value=False),
        )
        message_sender = SimpleNamespace(
            bot_manager=FakeBotManager(None),
            send_text=AsyncMock(return_value=True),
            deliver_to_targets=AsyncMock(return_value=0),
        )
        dispatcher = _build_dispatcher(config_manager, message_sender)

        ok = await dispatcher.dispatch("123456", {}, "onebot-main")

        assert ok is True
        message_sender.send_text.assert_awaited_once()
        message_sender.deliver_to_targets.assert_not_awaited()

    asyncio.run(scenario())
