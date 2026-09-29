"""群分析重点（GroupFocus）规则解析与提示词注入单元测试。

覆盖全局默认重点与逐群规则的合并、命中判定、结构化开关渲染，
以及分析器按开关把重点追加进提示词的行为。
"""

from src.domain.services.group_focus_resolver import GroupFocusResolver
from src.infrastructure.analysis.analyzers.base_analyzer import BaseAnalyzer

UMO = "onebot-main:GroupMessage:123456"


class _FakeConfig:
    """只提供群分析重点相关方法的最小配置替身。"""

    def __init__(self, *, enabled=True, rules=None, default=""):
        self._enabled = enabled
        self._rules = list(rules or [])
        self._default = default

    def get_group_focus_enabled(self):
        return self._enabled

    def get_group_focus_rules(self):
        return self._rules

    def get_default_group_focus(self):
        return self._default


class _DummyAnalyzer(BaseAnalyzer):
    """用于验证注入行为的极简分析器子类。"""

    def get_data_type(self):
        return "topic"

    def get_max_count(self):
        return 3

    def build_prompt(self, data):
        return "原始任务提示词"

    def extract_with_regex(self, result_text, max_count):
        return []

    def create_data_objects(self, data_list):
        return []


class _OptOutAnalyzer(_DummyAnalyzer):
    """主动声明不注入重点的分析器（模拟漫画分镜）。"""

    def should_apply_group_focus(self):
        return False


def test_resolve_returns_empty_when_disabled():
    """测试总开关关闭时不注入任何重点"""
    rules = [{"source_group": "", "extra_focus": "关注链接", "enabled": True}]

    result = GroupFocusResolver.resolve(
        UMO, rules, default_focus="全局要求", enabled=False
    )

    assert result == ""


def test_resolve_returns_empty_when_umo_blank():
    """测试缺少群标识时不做任何解析"""
    rules = [{"source_group": "", "extra_focus": "关注链接", "enabled": True}]

    assert GroupFocusResolver.resolve("", rules) == ""
    assert GroupFocusResolver.resolve("   ", rules) == ""


def test_resolve_returns_empty_when_nothing_configured():
    """测试既无全局默认重点也无命中规则时不注入"""
    assert GroupFocusResolver.resolve(UMO, []) == ""
    assert GroupFocusResolver.resolve(UMO, [], default_focus="   ") == ""


def test_resolve_applies_global_default_to_all_groups():
    """测试全局默认重点对所有群生效"""
    result = GroupFocusResolver.resolve(UMO, [], default_focus="多留意群里分享的工具")

    assert result.startswith("【本群分析重点】")
    assert "多留意群里分享的工具" in result


def test_resolve_matches_rule_by_group_number_and_full_umo():
    """测试源群既支持纯群号也支持完整会话 ID"""
    by_number = GroupFocusResolver.resolve(
        UMO, [{"source_group": "123456", "extra_focus": "盯链接", "enabled": True}]
    )
    by_umo = GroupFocusResolver.resolve(
        UMO,
        [
            {
                "source_group": "onebot-main:GroupMessage:123456",
                "extra_focus": "盯链接",
                "enabled": True,
            }
        ],
    )

    assert "盯链接" in by_number
    assert "盯链接" in by_umo


def test_resolve_skips_rule_for_other_group():
    """测试源群不匹配时不误注入"""
    result = GroupFocusResolver.resolve(
        UMO, [{"source_group": "999999", "extra_focus": "盯链接", "enabled": True}]
    )

    assert result == ""


def test_resolve_skips_disabled_rule():
    """测试规则行被停用后不生效"""
    result = GroupFocusResolver.resolve(
        UMO,
        [{"source_group": "123456", "extra_focus": "盯链接", "enabled": False}],
    )

    assert result == ""


def test_resolve_renders_structured_switches():
    """测试重点关注成员、链接、@全体与补充说明均被渲染"""
    result = GroupFocusResolver.resolve(
        UMO,
        [
            {
                "source_group": "123456",
                "focus_users": "张三, 李四",
                "focus_links": True,
                "focus_at_all": True,
                "extra_focus": "留意群里的活动报名情况",
                "enabled": True,
            }
        ],
    )

    assert "张三, 李四" in result
    assert "链接" in result
    assert "@全体成员" in result
    assert "留意群里的活动报名情况" in result


def test_resolve_merges_global_before_group_specific():
    """测试全局重点排在群级重点之前"""
    result = GroupFocusResolver.resolve(
        UMO,
        [{"source_group": "123456", "extra_focus": "群级要求", "enabled": True}],
        default_focus="全局要求",
    )

    assert "全局要求" in result
    assert "群级要求" in result
    assert result.index("全局要求") < result.index("群级要求")


def test_analyzer_injects_focus_into_prompt():
    """测试分析器把本群重点追加到提示词末尾且不破坏原文"""
    analyzer = _DummyAnalyzer(
        None,
        _FakeConfig(
            rules=[
                {
                    "source_group": "123456",
                    "focus_links": True,
                    "enabled": True,
                }
            ]
        ),
    )

    prompt = analyzer.apply_group_focus("原始任务提示词", UMO)

    assert prompt.startswith("原始任务提示词")
    assert "【本群分析重点】" in prompt


def test_analyzer_keeps_prompt_untouched_when_nothing_configured():
    """测试未配置重点时提示词保持原样"""
    analyzer = _DummyAnalyzer(None, _FakeConfig())

    assert analyzer.apply_group_focus("原始任务提示词", UMO) == "原始任务提示词"


def test_analyzer_keeps_prompt_untouched_without_umo():
    """测试缺少群标识时提示词保持原样"""
    analyzer = _DummyAnalyzer(None, _FakeConfig(default="全局要求"))

    assert analyzer.apply_group_focus("原始任务提示词", None) == "原始任务提示词"


def test_analyzer_opts_out_of_injection():
    """测试主动声明不注入的分析器不受重点影响"""
    analyzer = _OptOutAnalyzer(
        None,
        _FakeConfig(
            rules=[{"source_group": "123456", "focus_links": True, "enabled": True}]
        ),
    )

    assert analyzer.apply_group_focus("原始任务提示词", UMO) == "原始任务提示词"
