"""报告投递目标（DeliveryTarget）与投递规则解析单元测试。

覆盖投递目标的 UMO 序列化、配置写法解析，以及规则表到投递目标列表的解析行为。
"""

from src.domain.services.delivery_target_resolver import DeliveryTargetResolver
from src.domain.value_objects.delivery_target import DeliveryTarget


def test_delivery_target_umo_and_group_detection():
    """测试投递目标的 UMO 序列化与群聊/私聊判定"""
    group_target = DeliveryTarget.for_group("onebot-main", "123456")
    assert group_target.umo == "onebot-main:GroupMessage:123456"
    assert group_target.is_group is True

    friend_target = DeliveryTarget.for_friend("onebot-main", "10001")
    assert friend_target.umo == "onebot-main:FriendMessage:10001"
    assert friend_target.is_group is False


def test_delivery_target_parse_accepts_group_number():
    """测试纯数字写法被解析为默认平台上的群聊目标"""
    target = DeliveryTarget.parse("123456", default_platform_id="onebot-main")

    assert target is not None
    assert target.umo == "onebot-main:GroupMessage:123456"


def test_delivery_target_parse_accepts_full_umo():
    """测试完整 UMO 写法被精确解析，群聊与私聊均支持"""
    group_target = DeliveryTarget.parse(
        "onebot-main:GroupMessage:123456", default_platform_id="ignored"
    )
    assert group_target is not None
    assert group_target.is_group is True
    assert group_target.session_id == "123456"

    friend_target = DeliveryTarget.parse(
        "  onebot-main : FriendMessage : 10001  ", default_platform_id="ignored"
    )
    assert friend_target is not None
    assert friend_target.is_group is False
    assert friend_target.umo == "onebot-main:FriendMessage:10001"


def test_delivery_target_parse_rejects_invalid_input():
    """测试空值、缺段与未知会话类型均被拒绝"""
    assert DeliveryTarget.parse("", default_platform_id="onebot-main") is None
    assert DeliveryTarget.parse("   ", default_platform_id="onebot-main") is None
    assert (
        DeliveryTarget.parse("onebot-main:GroupMessage", default_platform_id="p")
        is None
    )
    assert (
        DeliveryTarget.parse("onebot-main:UnknownType:123", default_platform_id="p")
        is None
    )
    assert DeliveryTarget.parse("onebot-main::123", default_platform_id="p") is None
    assert DeliveryTarget.parse("不是群号", default_platform_id="onebot-main") is None
    assert DeliveryTarget.parse("123456", default_platform_id="") is None


def test_resolver_returns_origin_when_disabled_or_no_rule():
    """测试总开关关闭、规则表为空或全部未命中时，报告发回源会话"""
    origin = DeliveryTarget.for_group("onebot-main", "123456")
    rules = [
        {"source_group": "999999", "target": "888888", "enabled": True},
    ]

    assert DeliveryTargetResolver.resolve(origin, rules, enabled=False) == [origin]
    assert DeliveryTargetResolver.resolve(origin, []) == [origin]
    assert DeliveryTargetResolver.resolve(origin, rules) == [origin]


def test_resolver_blank_target_means_origin_group():
    """测试目标留空或写「原群」时回落到被分析的那个群"""
    origin = DeliveryTarget.for_group("onebot-main", "123456")

    blank_target = [{"source_group": "", "target": "", "enabled": True}]
    assert DeliveryTargetResolver.resolve(origin, blank_target) == [origin]

    alias_target = [{"source_group": "123456", "target": "原群", "enabled": True}]
    assert DeliveryTargetResolver.resolve(origin, alias_target) == [origin]

    english_alias = [{"source_group": "123456", "target": "origin", "enabled": True}]
    assert DeliveryTargetResolver.resolve(origin, english_alias) == [origin]


def test_resolver_matches_source_by_group_id_and_umo():
    """测试源群字段支持群号与完整 UMO 两种写法"""
    origin = DeliveryTarget.for_group("onebot-main", "123456")

    by_group_id = [{"source_group": "123456", "target": "888888", "enabled": True}]
    assert DeliveryTargetResolver.resolve(origin, by_group_id) == [
        DeliveryTarget.for_group("onebot-main", "888888")
    ]

    by_umo = [
        {
            "source_group": "onebot-main:GroupMessage:123456",
            "target": "888888",
            "enabled": True,
        }
    ]
    assert DeliveryTargetResolver.resolve(origin, by_umo) == [
        DeliveryTarget.for_group("onebot-main", "888888")
    ]


def test_resolver_supports_multiple_targets_for_same_source():
    """测试同一源群写多行时，报告同时投递到多个目标"""
    origin = DeliveryTarget.for_group("onebot-main", "123456")
    rules = [
        {"source_group": "123456", "target": "", "enabled": True},
        {"source_group": "123456", "target": "888888", "enabled": True},
        {
            "source_group": "123456",
            "target": "onebot-main:FriendMessage:10001",
            "enabled": True,
        },
    ]

    resolved = DeliveryTargetResolver.resolve(origin, rules)

    assert resolved == [
        origin,
        DeliveryTarget.for_group("onebot-main", "888888"),
        DeliveryTarget.for_friend("onebot-main", "10001"),
    ]


def test_resolver_keeps_rule_order_and_deduplicates():
    """测试多目标按规则表顺序返回且自动去重"""
    origin = DeliveryTarget.for_group("onebot-main", "123456")
    rules = [
        {"source_group": "", "target": "888888", "enabled": True},
        {"source_group": "", "target": "777777", "enabled": True},
        {"source_group": "", "target": "888888", "enabled": True},
    ]

    resolved = DeliveryTargetResolver.resolve(origin, rules)

    assert resolved == [
        DeliveryTarget.for_group("onebot-main", "888888"),
        DeliveryTarget.for_group("onebot-main", "777777"),
    ]


def test_resolver_skips_disabled_and_invalid_rules():
    """测试已停用的规则与写法非法的目标被跳过，且不影响其余规则"""
    origin = DeliveryTarget.for_group("onebot-main", "123456")
    rules = [
        {"source_group": "", "target": "888888", "enabled": False},
        {"source_group": "", "target": "不是目标", "enabled": True},
        {"source_group": "", "target": "777777", "enabled": True},
    ]

    resolved = DeliveryTargetResolver.resolve(origin, rules)

    assert resolved == [DeliveryTarget.for_group("onebot-main", "777777")]


def test_resolver_falls_back_to_origin_when_all_targets_invalid():
    """测试所有目标都非法时回退为源会话，避免报告丢失"""
    origin = DeliveryTarget.for_group("onebot-main", "123456")
    rules = [{"source_group": "", "target": "非法目标", "enabled": True}]

    assert DeliveryTargetResolver.resolve(origin, rules) == [origin]


def test_delivery_target_parse_accepts_private_prefix():
    """测试「私聊:QQ号」「好友:QQ号」等中文前缀写法按私聊解析"""
    for raw in ("私聊:10001", "好友:10001", "私:10001", "私聊：10001"):
        target = DeliveryTarget.parse(raw, default_platform_id="onebot-main")
        assert target is not None
        assert target.umo == "onebot-main:FriendMessage:10001"
        assert target.is_group is False


def test_delivery_target_parse_accepts_group_prefix():
    """测试「群:群号」前缀写法按群聊解析"""
    for raw in ("群:123456", "群聊:123456", "群聊：123456"):
        target = DeliveryTarget.parse(raw, default_platform_id="onebot-main")
        assert target is not None
        assert target.umo == "onebot-main:GroupMessage:123456"
        assert target.is_group is True


def test_delivery_target_parse_accepts_two_segment_umo():
    """测试两段式写法（省略平台 ID）按默认平台解析"""
    friend_target = DeliveryTarget.parse(
        "FriendMessage:10001", default_platform_id="onebot-main"
    )
    assert friend_target is not None
    assert friend_target.umo == "onebot-main:FriendMessage:10001"

    group_target = DeliveryTarget.parse(
        "GroupMessage:123456", default_platform_id="onebot-main"
    )
    assert group_target is not None
    assert group_target.umo == "onebot-main:GroupMessage:123456"

    # 未知会话类型仍被拒绝
    assert (
        DeliveryTarget.parse("UnknownType:123456", default_platform_id="onebot-main")
        is None
    )


def test_delivery_target_parse_numeric_as_private_flag():
    """测试纯数字目标在开启开关后按私聊 QQ 号处理，默认仍按群号处理"""
    group_target = DeliveryTarget.parse("10001", default_platform_id="onebot-main")
    assert group_target is not None
    assert group_target.is_group is True

    friend_target = DeliveryTarget.parse(
        "10001", default_platform_id="onebot-main", numeric_as_private=True
    )
    assert friend_target is not None
    assert friend_target.umo == "onebot-main:FriendMessage:10001"


def test_resolver_supports_comma_separated_multi_targets():
    """测试目标字段用英文逗号分隔时可一次投递到多个目标（中文逗号容错）"""
    origin = DeliveryTarget.for_group("onebot-main", "123456")

    english = [{"source_group": "123456", "target": "888888,私聊:10001", "enabled": True}]
    assert DeliveryTargetResolver.resolve(origin, english) == [
        DeliveryTarget.for_group("onebot-main", "888888"),
        DeliveryTarget.for_friend("onebot-main", "10001"),
    ]

    chinese = [{"source_group": "123456", "target": "888888，777777", "enabled": True}]
    assert DeliveryTargetResolver.resolve(origin, chinese) == [
        DeliveryTarget.for_group("onebot-main", "888888"),
        DeliveryTarget.for_group("onebot-main", "777777"),
    ]

    mixed = [
        {"source_group": "123456", "target": "888888, 原群 ,777777", "enabled": True}
    ]
    assert DeliveryTargetResolver.resolve(origin, mixed) == [
        DeliveryTarget.for_group("onebot-main", "888888"),
        origin,
        DeliveryTarget.for_group("onebot-main", "777777"),
    ]


def test_resolver_passes_numeric_as_private_to_parse():
    """测试解析器把纯数字私聊开关透传给目标解析"""
    origin = DeliveryTarget.for_group("onebot-main", "123456")
    rules = [{"source_group": "123456", "target": "10001", "enabled": True}]

    resolved = DeliveryTargetResolver.resolve(
        origin, rules, numeric_as_private=True
    )
    assert resolved == [DeliveryTarget.for_friend("onebot-main", "10001")]

    resolved_default = DeliveryTargetResolver.resolve(origin, rules)
    assert resolved_default == [DeliveryTarget.for_group("onebot-main", "10001")]
