# 报告投递目标设计方案

> 状态：**已实现**（指令最终定稿为 `/远程分析 <群编号> [天数]`）

## 1. 一句话

报告发到哪，**完全由 WebUI 的配置决定**；不配置就完全维持现状。

## 2. 核心模型

投递目标 = 一个会话，直接用 AstrBot 的 UMO 字符串表达，群和私聊天然统一：

| 目标类型 | UMO 格式 | 示例 |
| :--- | :--- | :--- |
| 群聊 | `{platform_id}:GroupMessage:{group_id}` | `aiocqhttp:GroupMessage:123456` |
| 私聊 | `{platform_id}:FriendMessage:{user_id}` | `aiocqhttp:FriendMessage:10001` |

## 3. 投递规则：怎么决定报告发到哪

就是**一张表**，没有隐藏逻辑。**每一行 = 一个投递目标**。

- **有规则匹配到本次被分析的群** → 报告投递到这些规则列出的**全部目标**（一行一个目标，写几行就发几处）
- **没有规则匹配** → 报告发回**被分析的那个群**（默认行为：A 群 → A 群）

### 目标可以怎么写

| 写法 | 含义 |
| :--- | :--- |
| **留空** 或填 `原群` | **发回被分析的群本身** |
| **纯数字**（如 `123456`） | 投递到该群号的群 |
| **完整 UMO** | 精确投递到任意群或私聊 |

注意：**源群与目标是两个独立的列**，源群写的是"报告来自哪个群"，目标写的是"报告发到哪"。

### 实际效果举例

| 源群 | 目标 | 结果 |
| :--- | :--- | :--- |
| A 群 | 留空（原群） | A 群的报告发回 A 群 |
| A 群 | 留空 + X 群（写两行） | A 群的报告**同时**发到 A 群和 X 群 |
| A 群 | X 群 | A 群的报告**只**发到 X 群，A 群自己收不到 |
| A 群 | 我的私聊 UMO | A 群的报告只发到我的私聊 |
| *（留空）* | Y 群 | 除已单独配过的群外，其余群的报告都汇到 Y 群 |

**私聊里发起的遥控分析同样走这套规则**；一条规则都没配时，报告仍发回**被分析的那个群**。
若遥控方希望把报告收到自己的私聊，只需为那个群添加一条目标为私聊会话的规则。
遥控方在本会话中看不到报告时，插件会明确提示报告的真实去向。

**指令里可以临时指定目标**，优先级高于规则表；不指定就按规则表走。

## 4. 配置设计：新增「报告投递」配置组

插件的配置中心是从 `_conf_schema.json` 直接渲染的（`src/infrastructure/webui/routes/config_routes.py:80-95`），
因此**只需在 schema 中新增一个分组，WebUI 配置中心就会自动出现该分区，无需改动前端代码**。

新增分组 `delivery`，分组描述为「报告投递」：

| 字段 | 类型 | 默认 | 说明 |
| :--- | :--- | :--- | :--- |
| `delivery_enabled` | bool | `false` | 投递功能总开关。**默认关闭 = 完全维持现状** |
| `delivery_rules` | template_list | `[]` | 投递规则表，可自由增删行 |

### `delivery_rules` 每行的字段

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `source_group` | string | 源群（被分析的群）。**留空 = 对所有群生效** |
| `target` | string | 目标会话。**留空或填 `原群` = 发回被分析的群**；纯数字 = 该群号；完整 UMO = 任意群或私聊 |
| `enabled` | bool | 该行是否生效 |

规则表复用插件已有的 `template_list` 交互形态（与「绘图供应商配置表」同款，支持可视化添加/删除行），
管理员在 WebUI 中点选即可，无需手写 JSON。

> 说明：`template_list` 的单元格目前只支持 `string` / `int` / `bool` / `file` / `text` 五种类型，
> 不支持在单元格内填列表。因此「一个源群发往多个目标」通过**写多行**实现，行为等价。

### 目标怎么写

- **留空 / `原群`**：发回被分析的那个群
- **纯数字**（如 `123456`）：插件自动用**源群所在的平台**去投递
- **私聊目标 / 跨平台目标**：必须填完整 UMO，可在目标会话里用 `/sid` 获取
- 填错时日志明确报出，不静默失败

## 5. 指令

按 AstrBot 官方规范，指令参数是**空格分隔的位置参数**，不支持 `--to` 这类带横杠的写法
（见 `astrbot/core/star/filter/command.py` 的 `validate_and_convert_params`）。

| 指令 | 场景 | 说明 |
| :--- | :--- | :--- |
| `/群列表` | 私聊 / 群聊 | 列出可遥控的群 + 编号 + 完整 UMO |
| `/群分析 [天数]` | 群聊 | 分析本群，**现有行为完全不变** |
| `/远程分析 <群编号> [天数]` | 私聊 / 群聊 | 分析编号对应的群，编号必填 |

采用独立指令而非复用 `/群分析`，避免「群聊填天数、私聊填编号」的语义歧义。

「可遥控群清单」复用**现有群聊白名单**（`basic.group_list`），不新增配置项。

## 6. 投递链路改造

**现状**：`PlatformAdapterProtocol` 的发送方法第一个参数都是 `group_id`
（`src/domain/repositories/platform_adapter_repository.py:45-70`），
「报告属于哪个群」与「发到哪个会话」是同一个值，因此无法跨会话投递。

**最终实现**：不修改任何既有适配器签名，而是在 `MessageSender` 中新增一条通用投递通道
（`send_report_to_target` / `deliver_to_targets`），基于 AstrBot 官方
`context.send_message(umo, chain)` 实现跨群、跨私聊与跨平台投递。

- **默认路径（发原群）**：完全走原有适配器链路，群相册上传、群文件归档、
  QQ 官方 Markdown 卡片等平台增强能力**一律保留**，零改动、零回归风险
- **额外路径（跨会话投递）**：走通用通道，覆盖原路径不支持跨会话投递的场景

### 平台兼容

| 平台 | 群 → 群 | 群 → 私聊 | 说明 |
| :--- | :--- | :--- | :--- |
| OneBot（NapCat / LLOneBot / SnowLuma / Standard） | 支持 | 支持 | 官方 `send_by_session` 已区分群/私聊分派 |
| QQ 官方机器人 | 支持 | 视平台能力 | 官方 API 对主动消息有限制，失败时日志明确报出 |
| Telegram | 支持 | 支持 | |
| Discord | 支持 | 支持 | |

### 改动清单

| 层 | 文件 | 改动 |
| :--- | :--- | :--- |
| 配置 | `_conf_schema.json` | 新增 `delivery` 分组 |
| 配置 | `src/infrastructure/config/config_manager.py` | 新增 `get_delivery_enabled` / `get_delivery_rules` |
| 领域 | `src/domain/value_objects/delivery_target.py` | 新增 `DeliveryTarget` 值对象 |
| 领域 | `src/domain/services/delivery_target_resolver.py` | 新增投递规则解析服务 |
| 基础设施 | `src/infrastructure/messaging/message_sender.py` | 新增跨会话投递通道 |
| 基础设施 | `src/infrastructure/platform/bot_manager.py` | 新增 `get_context()` 公开访问器 |
| 基础设施 | `src/infrastructure/reporting/dispatcher.py` | 定时链路接入投递解析 |
| 应用 | `src/application/handlers/analysis_command_handler.py` | 指令链路接入投递解析；支持遥控目标 |
| 应用 | `src/application/handlers/remote_command_handler.py` | 新增 `/群列表` 与 `/远程分析` 处理器 |
| 入口 | `main.py` | 注册 `/群列表` 与 `/远程分析` 指令 |

## 7. 兼容性

- **默认路径不变**：`delivery_enabled` 默认 `false`，未配置时不产生任何行为变化，现有用户无感知
- **默认语义即原群**：规则表里目标留空、或整表为空，报告都发回被分析的群（A 群 → A 群）
- **升级安全**：新配置项均有默认值，旧配置文件缺字段时回落到现状

## 8. 不在本次范围

- **HTML 外链部署**：属于运维配置，与本功能无关。完整方案见
  [`HTML_REPORT_EXTERNAL_LINK_GUIDE.md`](./HTML_REPORT_EXTERNAL_LINK_GUIDE.md)
- **关闭 AstrBot「AI 对话总开关」后独立运行**：经查证**已天然满足**，无需改动代码

## 9. 已确认的决策

1. 指令独立为 `/远程分析 <群编号> [天数]`，不复用 `/群分析`
2. 私聊发起的遥控分析同样走投递规则表；未配置规则时报告仍发回被分析的那个群（默认 A 群 → A 群）
3. 目标可以填「原群」，因此支持「原群 + 其他群/私聊同时投递」
4. 可遥控群清单复用现有群聊白名单，不新增配置项
