"""报告投递目标值对象。

描述一份报告最终要送达的会话，统一表达群聊与私聊，
使投递链路与各平台的会话标识格式解耦。
"""

from __future__ import annotations

from dataclasses import dataclass

GROUP_MESSAGE = "GroupMessage"
"""群聊会话类型标识，取值与 AstrBot UMO 中的 ``message_type`` 保持一致。"""

FRIEND_MESSAGE = "FriendMessage"
"""私聊会话类型标识，取值与 AstrBot UMO 中的 ``message_type`` 保持一致。"""

KNOWN_MESSAGE_TYPES = frozenset({GROUP_MESSAGE, FRIEND_MESSAGE})
"""插件认可的会话类型集合。"""

ORIGIN_ALIASES = frozenset({"origin", "原群", "本群", "本会话"})
"""配置中表示「发回被分析的那个会话」的写法（留空同样表示该含义）。"""

FRIEND_PREFIXES = ("私聊", "好友", "私")
"""目标写法中表示「私聊」的中文短前缀，如 ``私聊:123456``。"""

GROUP_PREFIXES = ("群聊", "群")
"""目标写法中表示「群聊」的中文短前缀，如 ``群:123456``。"""


@dataclass(frozen=True)
class DeliveryTarget:
    """值对象：报告投递目标（一个可寻址的会话）。

    一个投递目标同时能表达群聊与私聊，并可直接序列化为 AstrBot 的
    统一消息来源字符串（UMO），供 ``context.send_message`` 使用。

    Attributes:
        platform_id: 平台适配器实例 ID，对应 UMO 的第一段。
        message_type: 会话类型，取值为 ``GroupMessage`` 或 ``FriendMessage``。
        session_id: 会话 ID。群聊为群号，私聊为用户 ID。
    """

    platform_id: str
    message_type: str
    session_id: str

    @property
    def umo(self) -> str:
        """返回统一消息来源字符串，格式为 ``platform_id:message_type:session_id``。"""
        return f"{self.platform_id}:{self.message_type}:{self.session_id}"

    @property
    def is_group(self) -> bool:
        """判断该目标是否为群聊会话。"""
        return self.message_type == GROUP_MESSAGE

    @classmethod
    def for_group(cls, platform_id: str, group_id: str) -> DeliveryTarget:
        """构造一个群聊投递目标。

        Args:
            platform_id: 平台适配器实例 ID。
            group_id: 群号或平台侧群标识。

        Returns:
            DeliveryTarget: 群聊投递目标。
        """
        return cls(platform_id, GROUP_MESSAGE, group_id)

    @classmethod
    def for_friend(cls, platform_id: str, user_id: str) -> DeliveryTarget:
        """构造一个私聊投递目标。

        Args:
            platform_id: 平台适配器实例 ID。
            user_id: 私聊用户 ID。

        Returns:
            DeliveryTarget: 私聊投递目标。
        """
        return cls(platform_id, FRIEND_MESSAGE, user_id)

    @classmethod
    def parse(
        cls,
        raw: str,
        *,
        default_platform_id: str,
        numeric_as_private: bool = False,
    ) -> DeliveryTarget | None:
        """解析配置中填写的投递目标写法。

        支持以下写法：

        * 纯数字（如 ``123456``）：默认视为 ``default_platform_id`` 平台上的群聊；
          开启 ``numeric_as_private`` 时视为私聊 QQ 号。
        * 完整 UMO（如 ``aiocqhttp:FriendMessage:10001``）：精确指定群聊或私聊。
        * 两段式（如 ``FriendMessage:10001``）：省略平台 ID，使用默认平台。
        * 中文前缀（如 ``私聊:123456``、``好友:10001``、``群:123456``）：
          前缀决定会话类型，使用默认平台。

        Args:
            raw: 配置里填写的原始字符串。
            default_platform_id: 解析省略平台 ID 的写法时使用的默认平台 ID。
            numeric_as_private: 纯数字目标是否按私聊 QQ 号处理。

        Returns:
            DeliveryTarget | None: 解析成功返回目标对象；留空或写法不合法时返回 ``None``。
        """
        text = raw.strip()
        if not text:
            return None

        # 中文短前缀：私聊/好友/私 → 私聊；群聊/群 → 群聊
        for prefix in FRIEND_PREFIXES:
            if text.startswith(prefix):
                session_id = text[len(prefix) :].lstrip(":：").strip()
                if session_id and default_platform_id:
                    return cls.for_friend(default_platform_id, session_id)
                return None
        for prefix in GROUP_PREFIXES:
            if text.startswith(prefix):
                session_id = text[len(prefix) :].lstrip(":：").strip()
                if session_id and default_platform_id:
                    return cls.for_group(default_platform_id, session_id)
                return None

        if ":" in text:
            parts = text.split(":", 2)
            if len(parts) == 2:
                # 两段式：省略平台 ID，如 FriendMessage:10001
                message_type, session_id = (part.strip() for part in parts)
                if (
                    message_type in KNOWN_MESSAGE_TYPES
                    and session_id
                    and default_platform_id
                ):
                    return cls(default_platform_id, message_type, session_id)
                return None
            if len(parts) != 3:
                return None
            platform_id, message_type, session_id = (part.strip() for part in parts)
            if (
                not platform_id
                or not session_id
                or message_type not in KNOWN_MESSAGE_TYPES
            ):
                return None
            return cls(platform_id, message_type, session_id)
        if text.isdigit() and default_platform_id:
            if numeric_as_private:
                return cls.for_friend(default_platform_id, text)
            return cls.for_group(default_platform_id, text)
        return None
