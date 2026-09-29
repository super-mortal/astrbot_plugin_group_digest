"""投递目标领域服务。

依据管理员在「报告投递」配置中维护的规则表，解析一份报告最终要送达的会话集合。
规则表未启用或未命中任何规则时，报告发回被分析的那个会话，即插件原有行为。
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ...utils.logger import logger
from ..value_objects.delivery_target import ORIGIN_ALIASES, DeliveryTarget

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


class DeliveryTargetResolver:
    """领域服务：把「源会话 + 投递规则表」解析为去重后的投递目标列表。"""

    @staticmethod
    def resolve(
        origin: DeliveryTarget,
        rules: Sequence[Mapping[str, object]],
        *,
        enabled: bool = True,
        numeric_as_private: bool = False,
    ) -> list[DeliveryTarget]:
        """解析报告应投递到的全部会话。

        解析规则：

        1. 总开关关闭时直接返回源会话；
        2. 逐条读取规则表，取其中命中源会话且已启用的规则；
        3. 每条规则的目标为空或写「原群」时，解析为源会话本身；
        4. 未命中任何有效规则时回退为源会话。

        Args:
            origin: 被分析的源会话，同时作为默认投递目标。
            rules: 投递规则表，每项包含 ``source_group`` / ``target`` / ``enabled`` 等键。
            enabled: 投递功能总开关。
            numeric_as_private: 纯数字目标是否按私聊 QQ 号处理。

        Returns:
            list[DeliveryTarget]: 去重且保持规则表顺序的投递目标列表，至少包含源会话。
        """
        if not enabled:
            return [origin]

        resolved: list[DeliveryTarget] = []
        for rule in rules:
            if not bool(rule.get("enabled", True)):
                continue
            if not DeliveryTargetResolver._matches_source(origin, rule):
                continue

            # 目标支持英文逗号分隔的多值（中文逗号亦容错），一个群可投递到多个目标
            raw_target = str(rule.get("target") or "").strip()
            if not raw_target or raw_target.lower() in ORIGIN_ALIASES:
                parsed_targets: list[DeliveryTarget] = [origin]
            else:
                parsed_targets = []
                for part in re.split(r"[,，]", raw_target):
                    part = part.strip()
                    if not part:
                        continue
                    if part.lower() in ORIGIN_ALIASES:
                        parsed_targets.append(origin)
                        continue
                    target = DeliveryTargetResolver._parse_target(
                        origin, part, numeric_as_private=numeric_as_private
                    )
                    if target is None:
                        logger.warning(
                            "[投递] 规则中的目标「"
                            f"{part}」无法解析，已跳过。请填写群号、QQ 号"
                            "（开启纯数字私聊后）或形如 "
                            "aiocqhttp:GroupMessage:123456 / 私聊:10001 的会话写法。"
                        )
                    else:
                        parsed_targets.append(target)
            if not parsed_targets:
                continue
            for target in parsed_targets:
                if target not in resolved:
                    resolved.append(target)

        return resolved or [origin]

    @staticmethod
    def _matches_source(origin: DeliveryTarget, rule: Mapping[str, object]) -> bool:
        """判断一条规则是否命中本次被分析的源会话。

        源群字段留空时表示该规则对所有群生效。

        Args:
            origin: 被分析的源会话。
            rule: 单条投递规则。

        Returns:
            bool: 规则命中源会话时返回 ``True``。
        """
        source = str(rule.get("source_group") or "").strip()
        if not source:
            return True
        return source in {origin.session_id, origin.umo}

    @staticmethod
    def _parse_target(
        origin: DeliveryTarget,
        raw_target: object,
        *,
        numeric_as_private: bool = False,
    ) -> DeliveryTarget | None:
        """解析规则中的目标字段。

        留空或写「原群」/``origin`` 时回落到源会话本身。

        Args:
            origin: 被分析的源会话。
            raw_target: 规则中填写的目标原始值。
            numeric_as_private: 纯数字目标是否按私聊 QQ 号处理。

        Returns:
            DeliveryTarget | None: 解析成功返回目标对象；写法不合法时返回 ``None``。
        """
        raw = str(raw_target or "").strip()
        if not raw or raw.lower() in ORIGIN_ALIASES:
            return origin
        return DeliveryTarget.parse(
            raw,
            default_platform_id=origin.platform_id,
            numeric_as_private=numeric_as_private,
        )
