"""群分析重点领域服务。

依据管理员在「群分析重点」配置中维护的全局默认重点与逐群重点规则，
解析出该群本轮分析应当额外侧重的内容，渲染为一段可直接追加到提示词的文本。

未启用、未命中任何规则且未设置全局默认重点时返回空字符串，
调用方据此保持原有提示词不变。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

FOCUS_HEADER = "【本群分析重点】"
"""追加段落标题，便于模型区分「通用任务」与「本群附加要求」。"""

FOCUS_PREAMBLE = (
    "除完成上述任务外，请在本轮分析中额外侧重以下方面。"
    "这些要求只影响内容侧重，不得改变原有的输出结构与格式约束："
)

_SCOPE_NOTE = "重点要求仅对当前这一个群生效，不要套用到其他群。"

USERS_TEMPLATE = "重点关注以下成员的发言，他们的观点请单独点名并适当展开：{users}。"
LINKS_TEMPLATE = (
    "重点关注群里分享的链接：请提炼链接指向的内容与相关讨论，"
    "并在最终总结里完整写出链接地址（保持原样，不要截断或省略）。"
)
AT_ALL_TEMPLATE = (
    "重点关注 @全体成员 的消息：请在报告中完整写出这类消息的原文内容，"
    "并分析其发布意图与群友反应。"
)


class GroupFocusResolver:
    """领域服务：把「全局默认重点 + 逐群重点规则」解析为补充要求文本。"""

    @staticmethod
    def resolve(
        umo: str,
        rules: Sequence[Mapping[str, object]],
        *,
        default_focus: str = "",
        enabled: bool = True,
    ) -> str:
        """解析某个群本轮分析要追加的重点要求。

        解析规则：

        1. 总开关关闭或 ``umo`` 为空时返回空字符串；
        2. 全局默认重点对所有群生效，排在群级重点之前；
        3. 逐条读取规则表，取其中命中该群且已启用的规则，多条命中会依次合并；
        4. 各项均未产出内容时返回空字符串。

        Args:
            umo: 被分析群的统一消息来源字符串，形如 ``platform:GroupMessage:123456``。
            rules: 逐群重点规则表，每项包含 ``source_group`` / ``focus_users`` /
                ``focus_links`` / ``focus_at_all`` / ``extra_focus`` / ``enabled``。
            default_focus: 对所有群生效的全局默认重点文本。
            enabled: 群分析重点功能总开关。

        Returns:
            str: 可直接追加到提示词末尾的补充要求文本；无需追加时返回空字符串。
        """
        if not enabled or not umo.strip():
            return ""

        fragments: list[str] = []

        global_text = default_focus.strip()
        if global_text:
            fragments.append(global_text)

        focus_lines: list[str] = []
        for rule in rules:
            if not bool(rule.get("enabled", True)):
                continue
            if not GroupFocusResolver._matches(umo, rule):
                continue
            focus_lines.extend(GroupFocusResolver._render_rule(rule))

        if focus_lines:
            numbered = "\n".join(
                f"{index}. {line}" for index, line in enumerate(focus_lines, start=1)
            )
            fragments.append(f"{FOCUS_PREAMBLE}\n{numbered}\n{_SCOPE_NOTE}")

        if not fragments:
            return ""

        return f"{FOCUS_HEADER}\n" + "\n\n".join(fragments)

    @staticmethod
    def _matches(umo: str, rule: Mapping[str, object]) -> bool:
        """判断一条规则是否命中该群。

        源群字段留空时表示该规则对所有群生效。

        Args:
            umo: 被分析群的统一消息来源字符串。
            rule: 单条重点规则。

        Returns:
            bool: 规则命中该群时返回 ``True``。
        """
        source = str(rule.get("source_group") or "").strip()
        if not source:
            return True
        session_id = umo.rsplit(":", 1)[-1]
        return source in {umo, session_id}

    @staticmethod
    def _render_rule(rule: Mapping[str, object]) -> list[str]:
        """把单条规则渲染为若干条自然语言要求。

        Args:
            rule: 单条重点规则。

        Returns:
            list[str]: 该规则产出的要求条目，可能为空列表。
        """
        lines: list[str] = []

        users = str(rule.get("focus_users") or "").strip()
        if users:
            lines.append(USERS_TEMPLATE.format(users=users))

        if bool(rule.get("focus_links", False)):
            lines.append(LINKS_TEMPLATE)

        if bool(rule.get("focus_at_all", False)):
            lines.append(AT_ALL_TEMPLATE)

        extra = str(rule.get("extra_focus") or "").strip()
        if extra:
            lines.append(extra)

        return lines
