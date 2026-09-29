# 对原仓库的改造内容汇总

> 本仓库基于原项目 [SXP-Simon/astrbot_plugin_qq_group_daily_analysis](https://github.com/SXP-Simon/astrbot_plugin_qq_group_daily_analysis)
> （展示名「群聊日报」，基线版本 **v5.6.6**，对应上游 commit `e13ae844`）二次开发，
> 现已更名为 **`astrbot_plugin_group_digest`**（展示名「**群聊总结**」），当前版本 **v1.0.0**。
> 本文档汇总相对原仓库的全部改造内容，随版本迭代持续更新。

---

## 〇、上游基线能力（原仓库已有，本仓库完整保留）

原仓库在本仓库分叉时（v5.6.6）已具备以下能力，本仓库**全部继承**：

- **多平台支持**：OneBot (NapCat / LLOneBot / SnowLuma)、QQ 官方机器人（含 Markdown 报告与 T2I 概览图）、Telegram、Discord；
- **报告形态**：图片海报（T2I 渲染 + Jinja2 多主题模板：ATRI、BlueArchive、初音未来、手账、新艺术运动等）、HTML 网页报告、跨平台 Markdown 报告；
- **分析能力**：话题总结、用户画像（MBTI / SBTI / ACGTI）、金句 / 圣经识别、质量锐评、活跃度统计与直方图、表情统计；
- **每日群漫画**：分镜生成、生图供应商接入、角色方案与参考图、群相册上传；
- **增量分析**：按消息数量分批提取摘要、增量批次存储与游标推进、Checkpoint 断点续跑、`/增量状态` 指令；
- **WebUI 管理后台**：运行链路、历史报告、异常日志、数据审计、配置中心、OpenAPI 3.1 契约、独立前端开发环境；
- **工程化**：Trace 链路追踪、LLM 并发信号量与排他任务锁、配置迁移器、DDD 分层架构。

---

## 一、改造规模总览

以 **上游 v5.6.6（`e13ae844`）** 为基准，对本仓库 497 个文件与上游 476 个文件**逐文件比对**：

| 类别 | 数量 | 说明 |
| --- | --- | --- |
| 内容完全一致 | 346 | 未改动 |
| 内容有改动 | 124 | 详见下文各节 |
| 本仓库新增 | 25 | 新模块、新文档与新测试 |
| 本仓库删除 | 4 | 见「三、删除的文件」 |

> **核对口径**：先用 git blob SHA 逐文件比对（SHA 相同 = 内容逐字节一致），
> 再对 SHA 不同的文件拉取上游原文、**归一化换行符后**做内容比对——
> 因为上游仓库部分文本文件按 CRLF 存储，而本仓库 `.gitattributes` 强制 LF，
> 直接比 SHA 会把仅换行符不同的文件误判为「已改动」（实测有 2 个文件属此类）。

### 改动最集中的文件（按改动行数，排除二进制与构建产物）

| 文件 | 改动 | 对应改造 |
| --- | --- | --- |
| `_conf_schema.json` | +760 / -485 | 配置结构：12 → 13 个分组，271 → 296 个字段 |
| `dashboard/src/pages/config/ui/ConfigPage.tsx` | +438 / -60 | 配置中心页面：新增分组导航、特化布局 |
| `README.md` | +289 / -156 | 文档重写（指令一览、徽章、栏目精简） |
| `src/infrastructure/config/config_manager.py` | +294 / -123 | 新增配置项读写、Schema 分组容错 |
| `src/application/handlers/analysis_command_handler.py` | +308 / -46 | 分析指令与报告投递链路 |
| `dashboard/.../TemplateListRenderer.tsx` | +228 / -43 | 模板列表渲染（新增自定义模板支持） |
| `src/infrastructure/reporting/dispatcher.py` | +194 / -51 | 报告投递目标解析与分发 |
| `src/infrastructure/messaging/message_sender.py` | +136 / -0 | 跨会话投递通道 |
| `dashboard/.../FieldRenderer.tsx` | +126 / -46 | 配置字段渲染（新增组件类型） |
| `main.py` | +88 / -0 | 新增 5 条指令注册 |
| `src/infrastructure/persistence/history_manager.py` | +71 / -3 | 历史摘要索引与按索引清理 |
| `src/infrastructure/webui/routes/data_management_routes.py` | +71 / -0 | 数据管理路由（自动清理、存储概览） |
| `src/infrastructure/webui/plugin_page_bridge.py` | +66 / -0 | 新增 WebUI 桥接路由 |

---

## 二、新增模块清单（上游没有的文件，共 25 个）

**后端**

| 文件 | 用途 |
| --- | --- |
| `src/utils/time_utils.py` | 北京时间工具集（`BEIJING_TZ` / `now_local` / `format_local_date` / `from_timestamp_local`），用于统一时间语义 |
| `src/domain/value_objects/delivery_target.py` | 报告投递目标值对象 |
| `src/domain/services/delivery_target_resolver.py` | 投递目标解析（逐群规则、私聊、多目标、来源标识） |
| `src/domain/services/group_focus_resolver.py` | 群分析重点解析 |
| `src/application/handlers/remote_command_handler.py` | `/群列表`、`/远程分析` 指令实现 |
| `src/infrastructure/persistence/data_retention_service.py` | 统一数据保留与自动清理 |
| `src/infrastructure/storage/__init__.py`、`webdav_uploader.py` | WebDAV 归档上传 |
| `src/infrastructure/webui/routes/backup_routes.py` | 配置备份中心路由 |

**前端**

| 文件 | 用途 |
| --- | --- |
| `dashboard/src/entities/backup/api/backupApi.ts` | 备份 API 客户端 |
| `dashboard/src/pages/backup/ui/BackupCenterPage.tsx` | 备份中心页面 |
| `dashboard/src/pages/config/ui/ConfigGuidePanel.tsx` | 配置中心内置上手指南 |
| `dashboard/src/pages/plugin-data/ui/partitions/RetentionCard.tsx` | 自动清理策略卡片 |
| `dashboard/src/widgets/config-form/ui/CompactListEditor.tsx` | 紧凑列表编辑器（时间列表折叠展示） |

**文档与测试**

- 文档：`UPSTREAM_CHANGES.md`（本文档）、`docs/REPORT_DELIVERY_DESIGN.md`、`docs/HTML_REPORT_EXTERNAL_LINK_GUIDE.md`
- 测试（8 个）：`test_backup_webdav.py`、`test_data_retention.py`、`test_delivery_dispatch.py`、`test_delivery_target.py`、`test_group_focus.py`、`test_remote_command_handler.py`、`test_time_utils.py`、`test_webdav_uploader.py`

## 三、删除的文件（4 个）

| 文件 | 原因 |
| --- | --- |
| `assets/QQ.png`、`assets/TG.png` | README 已改用徽章与纯文本，不再需要平台配图 |
| `scripts/test_regional_rendering.py` | 上游遗留的验证脚本，本仓库内已无任何引用 |
| `src/domain/exceptions.py` | 定义了 26 个领域异常类，但全仓库**零引用**（实际代码使用内置异常），属死代码 |

---

## 四、插件标识

| 项目 | 原仓库 | 本仓库 |
| --- | --- | --- |
| 插件标识 (name) | `astrbot_plugin_qq_group_daily_analysis` | `astrbot_plugin_group_digest` |
| 展示名 | 群聊日报 | 群聊总结 |
| 仓库地址 | `SXP-Simon/astrbot_plugin_qq_group_daily_analysis` | `super-mortal/astrbot_plugin_group_digest` |

- 已核对插件市场现有插件，无标识重名。
- 旧备份格式兼容：配置备份的 `backup_format` 同时接受新旧两个 ID。

## 五、新增功能（原仓库没有的能力）

### 1. 报告投递（逐群规则表）

- 在 WebUI 中按群配置「报告发到哪」：可发回原群、发到其他群、或多处同时发送。
- 规则表按从上到下的顺序执行；源群留空表示对其余所有群生效。
- **私聊投递**：目标支持「私聊:QQ号」「好友:QQ号」「FriendMessage:QQ号」写法，也可开启「纯数字目标按私聊处理」后直接填 QQ 号。
- **多目标**：一个目标字段可用英文逗号分隔多个写法，一条规则同时投递到多个群 / 私聊。
- **来源标识**：投递到非源会话（如汇总到同一个私聊）时，自动在报告前加「【来自群 xxx】」标识，图片、HTML 文件、HTML 外链、纯文本四种形态全部覆盖。
- 通过跨会话投递通道实现，不改动各平台适配器签名，天然跨平台。

### 2. 私聊遥控分析

- `/群列表`：列出可遥控分析的群聊及编号。
- `/远程分析 <编号> [天数]`：在私聊中远程触发指定群的分析。
- 管理员无需进群即可手动触发任意已授权群聊的报告。

### 3. 群分析重点

- 总开关嵌入分组标题行右上角，不占用字段行。
- 全局默认重点：写给所有群的共同侧重（内置默认文案，可自行修改）。
- 逐群重点规则表：按群设置重点关注成员、关注链接、关注 @全体成员、补充说明，
  每条规则可单独启用/停用而无需删除；规则卡支持点击展开 / 收起。
- 源群支持直接从基础设置继承的群清单中选择，不必重复填写。

### 4. WebDAV 报告归档

- 支持坚果云 / Nextcloud / 群晖等标准 WebDAV 服务（Basic 认证）。
- 报告生成后自动归档到远程目录，独立于本地上传设置。
- 属于**静默增强能力**：任何失败只写日志，不影响报告本身的发送。

### 5. 配置备份中心

- 一键导出/导入全部插件配置（JSON）。
- 支持 WebDAV 远程备份：推送、列表、一键恢复。
- 内嵌 WebDAV 连接配置，与归档共用同一套连接信息。

### 6. 数据保留与自动清理

- 统一的「数据保留天数」开关，到期自动清理：
  - Trace 执行记录（`traces.db`）、过期 Checkpoint；
  - 历史报告目录中超期的图片 / HTML 文件；
  - KV 存储中的历史报告摘要与增量分析批次；
  - 群成员头像缓存与临时渲染缓存。
- 每天 04:17（北京时间）定时执行，插件启动后补跑一轮；关闭后数据永久保留。

### 7. 指令补充

- 在上游 `/群分析`、`/群漫画`、`/增量状态` 的基础上，新增 `/群列表`、`/远程分析`、
  `/设置格式`、`/设置模板`、`/查看模板`、`/分析设置` 共 6 条指令；
  其中 `/分析设置` 含 7 个子操作（`status` / `enable` / `disable` / `reload` / `test` /
  `incremental_debug` / `filter_bot`）。全部指令与参数见 README「⌨️ 斜杠命令一览」。

## 六、界面与体验改造

- **内嵌 WebUI 控制台**：运行总览、分析记录、统计与消耗、历史报告、运行日志、
  配置中心、数据管理七大板块，原生集成在 AstrBot 插件管理页，无需额外部署。
- **配置中心**：按使用流程重排的分组导航与即时搜索；配置项可视化确认；
  修改后未保存提醒；基础设置页组合卡布局（权限模式 / 定时 / 间隔、人格三件套等单行等分排布）。
- **数据管理页**：存储空间概览、增量分析批次管理、阶段产物快照（Checkpoint）管理，
  标签栏右侧内嵌自动清理策略控件（开关即存、天数失焦保存）。
- **使用说明**：配置中心内置分步上手指南，标注每项功能是否为本仓库新增。
- **备份中心**：入口位于配置中心左侧列表最底部，含导出/恢复两张功能卡与独立的 WebDAV 连接配置卡。

## 七、工程与质量

- **安装包瘦身**：通过 `.gitattributes` 的 `export-ignore` 规则，把前端源码、测试、
  设计文档、CI 配置，以及仅由 CDN 引用的模板素材（ATRI 约 34MB、初音未来约 6MB、
  模板预览图约 7MB）全部排除在发布包之外。
  **发布包实际为 243 个文件 / 约 1.98MB**，远低于插件市场 16MB 上传限制。
- **时间语义**：定时、日期格式统一使用北京时间（UTC+8），不依赖宿主机时区
  （集中封装在 `src/utils/time_utils.py`）。已修复崩溃恢复中「跨天判定」混用
  服务器本地时区与北京时间的缺陷——该缺陷会导致非 UTC+8 主机（如海外 VPS）
  把当天中断的任务误判为跨天归档。
- **测试门禁**：后端 pytest 495 个用例全通过、pyright 零错误；
  前端 typecheck / lint / 单元测试 / build 四项门禁全绿。
  CI 覆盖提交信息规范（Conventional Commits + Scope 白名单 + 原子化校验）。
- **仓库引用统一**：修正了更名过程中被误替换的仓库引用——报告模板页脚、
  配置提示中的链接、模板预览图 CDN 与 ATRI / 初音未来素材 CDN 的默认值，
  原先会拼出不存在的仓库地址，现已统一指向本仓库。

---

*最后更新：2026-09-29（v1.0.0）*
