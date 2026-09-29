"""遥控指令处理器（RemoteCommandHandler）单元测试。

覆盖可遥控群清单的解析、/群列表 输出，以及 /远程分析 的参数校验与委派行为。
"""

import asyncio
from types import SimpleNamespace

from src.application.handlers.remote_command_handler import RemoteCommandHandler


class FakeEvent:
    """记录回复内容的最小消息事件替身。"""

    def __init__(self, platform_id="onebot-main", umo=""):
        self._platform_id = platform_id
        self.unified_msg_origin = umo
        self.replies: list[str] = []

    def get_platform_id(self):
        return self._platform_id

    def plain_result(self, text):
        self.replies.append(text)
        return text


class FakeBotManager:
    """不提供适配器，使群名称回退为群号。"""

    def get_adapter(self, platform_id):
        return None


class FakeAnalysisHandler:
    """记录调用参数的群分析处理器替身。"""

    def __init__(self):
        self.calls: list = []

    async def handle_daily_analysis(self, event, days=None, target=None):
        self.calls.append((days, target))
        yield "分析完成"


def _build_handler(group_list, rules=None, delivery_enabled=False):
    config_manager = SimpleNamespace(
        get_group_list=lambda: list(group_list),
        get_delivery_rules=lambda: list(rules or []),
        get_delivery_enabled=lambda: delivery_enabled,
    )
    return RemoteCommandHandler(config_manager, FakeBotManager(), FakeAnalysisHandler())


def test_resolve_targets_parses_group_numbers_with_default_platform():
    """测试纯数字条目按当前事件所属平台解析为群聊目标"""

    async def scenario():
        handler = _build_handler(["123456", "654321"])
        targets = await handler._resolve_targets(FakeEvent("onebot-main"))

        assert [target.umo for target in targets] == [
            "onebot-main:GroupMessage:123456",
            "onebot-main:GroupMessage:654321",
        ]

    asyncio.run(scenario())


def test_resolve_targets_keeps_explicit_platform_and_deduplicates():
    """测试完整会话 ID 保留其声明平台，且重复与非法条目被过滤"""

    async def scenario():
        handler = _build_handler(
            [
                "telegram-main:GroupMessage:-1001234567890",
                "telegram-main:GroupMessage:-1001234567890",
                "123456",
                "   ",
                "不是群号",
                "onebot-main:FriendMessage:10001",
            ]
        )
        targets = await handler._resolve_targets(FakeEvent("onebot-main"))

        assert [target.umo for target in targets] == [
            "telegram-main:GroupMessage:-1001234567890",
            "onebot-main:GroupMessage:123456",
        ]

    asyncio.run(scenario())


def test_group_list_reports_empty_configuration():
    """测试白名单为空时给出配置指引而不是空列表"""

    async def scenario():
        handler = _build_handler([])
        event = FakeEvent()

        results = [item async for item in handler.handle_group_list(event)]

        assert len(results) == 1
        assert "暂无可遥控的群聊" in event.replies[0]

    asyncio.run(scenario())


def test_group_list_renders_numbered_entries_with_umo():
    """测试群列表输出编号、群名回退与完整会话 ID"""

    async def scenario():
        handler = _build_handler(["123456", "telegram-main:GroupMessage:-1001"])
        event = FakeEvent()

        await anext(handler.handle_group_list(event).__aiter__())

        rendered = event.replies[0]
        assert "1. 123456" in rendered
        assert "　　onebot-main:GroupMessage:123456" in rendered
        assert "2. -1001" in rendered
        assert "　　telegram-main:GroupMessage:-1001" in rendered

    asyncio.run(scenario())


def test_remote_analysis_requires_valid_index():
    """测试缺少编号或编号越界时给出明确提示且不触发分析"""

    async def scenario():
        handler = _build_handler(["123456"])
        event = FakeEvent()

        await anext(handler.handle_remote_analysis(event, None).__aiter__())
        await anext(handler.handle_remote_analysis(event, 5).__aiter__())

        assert "请指定群编号" in event.replies[0]
        assert "当前可选范围是 1 ~ 1" in event.replies[1]
        assert handler.analysis_handler.calls == []

    asyncio.run(scenario())


def test_remote_analysis_delegates_with_selected_target():
    """测试编号正确时按该群触发分析并透传天数"""

    async def scenario():
        handler = _build_handler(["123456", "654321"])
        event = FakeEvent()

        results = [item async for item in handler.handle_remote_analysis(event, 2, 3)]

        assert results == ["分析完成"]
        days, target = handler.analysis_handler.calls[0]
        assert days == 3
        assert target is not None
        assert target.umo == "onebot-main:GroupMessage:654321"

    asyncio.run(scenario())


def test_remote_analysis_hints_when_report_goes_to_origin_group():
    """测试未配置规则时报告回原群，遥控的私聊方会收到明确的去向提示"""

    async def scenario():
        handler = _build_handler(["123456"])
        event = FakeEvent(umo="onebot-main:FriendMessage:10001")

        results = [item async for item in handler.handle_remote_analysis(event, 1)]

        assert results == ["分析完成", event.replies[-1]]
        assert "发往了其他会话" in event.replies[-1]

    asyncio.run(scenario())


def test_remote_analysis_hints_when_rule_points_elsewhere():
    """测试规则把报告指向其他群时，遥控方同样收到去向提示"""

    async def scenario():
        handler = _build_handler(
            ["123456"],
            rules=[{"source_group": "", "target": "888888", "enabled": True}],
            delivery_enabled=True,
        )
        event = FakeEvent(umo="onebot-main:FriendMessage:10001")

        results = [item async for item in handler.handle_remote_analysis(event, 1)]

        assert results == ["分析完成", event.replies[-1]]
        assert "发往了其他会话" in event.replies[-1]

    asyncio.run(scenario())


def test_remote_analysis_has_no_hint_when_report_reaches_caller():
    """测试规则把报告指向发起会话本身时，不再追加多余提示"""

    async def scenario():
        caller = "onebot-main:FriendMessage:10001"
        handler = _build_handler(
            ["123456"],
            rules=[{"source_group": "", "target": caller, "enabled": True}],
            delivery_enabled=True,
        )
        event = FakeEvent(umo=caller)

        results = [item async for item in handler.handle_remote_analysis(event, 1)]

        assert results == ["分析完成"]
        assert event.replies == []

    asyncio.run(scenario())
