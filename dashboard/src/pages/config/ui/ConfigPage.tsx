import React, { useState, useEffect } from "react";
import {
  Card,
  Row,
  Col,
  Input,
  Typography,
  Space,
  Button,
  Tag,
  Empty,
  Badge,
  Spin,
  Alert,
  Switch,
  Tooltip,
  theme,
} from "antd";
import {
  SaveOutlined,
  ReloadOutlined,
  SearchOutlined,
  SettingOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  AppstoreOutlined,
  DownOutlined,
  UpOutlined,
  BulbOutlined,
  CloudServerOutlined,
  QuestionCircleOutlined,
} from "@ant-design/icons";
import { useConfigViewModel } from "../model/useConfigViewModel";
import { FieldRenderer } from "../../../widgets/config-form/ui/FieldRenderer";
import { useTheme } from "../../../shared/lib/useTheme";
import { MarkdownHint } from "../../../shared/ui/MarkdownHint";
import { ConfigGuidePanel } from "./ConfigGuidePanel";
import { BackupCenterPage } from "../../backup/ui/BackupCenterPage";
import { SchemaFieldItem } from "../../../entities/config/model/types";

const { Title, Text, Paragraph } = Typography;

/** 左侧列表末尾的「备份中心」特殊入口 key（非 schema 分组）。 */
const BACKUP_KEY = "__backup_center__";

/** 左侧导航中「使用说明」项的伪分组 key（不对应任何真实 schema 分组）。 */
const GUIDE_KEY = "__guide__";

/**
 * 需要把某个布尔字段提升到分组标题行右侧的分组的开关。
 * 如「群分析重点」页：启用开关不再单独占一行，而是嵌在标题右侧的专属区域。
 */
const HEADER_SWITCH_FIELDS: Record<string, string> = {
  group_focus: "group_focus_enabled",
  incremental: "enable_incremental_analysis",
};

interface ConfigPageProps {
  viewModel: ReturnType<typeof useConfigViewModel>;
}

export const ConfigPage: React.FC<ConfigPageProps> = ({ viewModel }) => {
  const { isDark } = useTheme();
  const [isMobileScreen, setIsMobileScreen] = useState(() =>
    typeof window !== "undefined" ? window.innerWidth < 768 : false
  );
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    const handleResize = () => {
      setIsMobileScreen(window.innerWidth < 768);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const {
    loading,
    saving,
    isDirty,
    formData,
    categories,
    providers,
    personas,
    activeCategory,
    currentGroupFields,
    activeGroupMeta,
    searchQuery,
    errors,
    groupErrorCounts,
    setSearchQuery,
    setActiveCategory,
    handleFieldChange,
    handleSave,
    handleReload,
  } = viewModel;

  const activeCategoryInfo = categories.find((c) => c.key === activeCategory);

  // 标题行开关：当前分组若配置了 HEADER_SWITCH_FIELDS，则该字段不再进入字段列表
  const headerSwitchKey = HEADER_SWITCH_FIELDS[activeCategory];
  const headerSwitchSchema = headerSwitchKey
    ? viewModel.schema[activeCategory]?.items?.[headerSwitchKey]
    : undefined;
  const headerSwitchValue = headerSwitchKey
    ? formData[activeCategory]?.[headerSwitchKey] ??
      headerSwitchSchema?.default
    : undefined;
  const displayFields = headerSwitchKey
    ? currentGroupFields.filter((f) => f.key !== headerSwitchKey)
    : currentGroupFields;

  // 报告投递规则的「来源群 / 目标」下拉建议：实时来自基础设置的群名单编辑值
  const groupSuggestions: string[] = (() => {
    const raw = formData?.basic?.group_list;
    if (!Array.isArray(raw)) return [];
    return raw
      .map((item) => String(item).trim())
      .filter((item) => item.length > 0);
  })();

  return (
    <div
      className="config-page-root"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 12,
        width: "100%",
        height: isMobileScreen ? undefined : "100%",
        minHeight: 0,
        overflow: isMobileScreen ? undefined : "hidden",
        position: "relative",
      }}
    >
      {/* 让 Spin 包裹层继承高度，保证左右两栏各自独立滚动 */}
      <style>{`
        .config-page-root .ant-spin-nested-loading,
        .config-page-root .ant-spin-container {
          height: 100%;
        }
      `}</style>
      {/* 顶部概览与全局操作栏 (常驻固定，不随表单滚动) */}
      <Card
        size="small"
        style={{
          flexShrink: 0,
          background: isDark ? "#141414" : "#ffffff",
          borderRadius: 6,
          boxShadow: isDark
            ? "0 4px 12px rgba(0, 0, 0, 0.45)"
            : "0 4px 12px rgba(0, 0, 0, 0.06)",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: 12,
          }}
        >
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <SettingOutlined style={{ color: "#1677ff", fontSize: 18 }} />
              <Title level={4} style={{ margin: 0, fontSize: 16 }}>
                群聊分析配置中心
              </Title>
              {isDirty && (
                <Tag color="warning" icon={<ExclamationCircleOutlined />}>
                  存在未保存的修改
                </Tag>
              )}
            </div>
            <Paragraph
              type="secondary"
              style={{ margin: "4px 0 0 0", fontSize: 12 }}
            >
              基于最新版 <code>_conf_schema.json</code> 动态生成，升级新增字段会自动显示。修改后请点击右上角保存。
            </Paragraph>
          </div>

          <Space size="small">
            <Tag color="blue" style={{ fontSize: 12, padding: "2px 8px" }}>
              {categories.length} 个配置分组
            </Tag>
            <Button
              size="middle"
              icon={<ReloadOutlined spin={loading} />}
              onClick={handleReload}
              disabled={loading || saving}
            >
              重新读取
            </Button>
            <Button
              size="middle"
              type="primary"
              icon={isDirty ? <SaveOutlined /> : <CheckCircleOutlined />}
              onClick={handleSave}
              loading={saving}
              disabled={!isDirty || loading}
            >
              {isDirty ? "保存配置" : "配置已同步"}
            </Button>
          </Space>
        </div>
      </Card>

      {/* 主体配置工作区 (双栏布局：左侧分组导航 + 右侧动态表单，两栏各自独立滚动) */}
      <Card
        size="small"
        style={{ flex: isMobileScreen ? undefined : "1 1 auto", minHeight: 0 }}
        styles={{ body: { padding: 0, height: "100%" } }}
      >
        <Spin spinning={loading}>
          <Row
            align="stretch"
            style={{
              height: isMobileScreen ? undefined : "100%",
              minHeight: isMobileScreen ? 600 : 0,
            }}
          >
            {/* 左侧：搜索与分组导航 (独立滚动区，移动端支持一键收纳展开) */}
            <Col
              xs={24}
              md={5}
              style={{
                borderRight: !isMobileScreen ? `1px solid ${isDark ? "#303030" : "#f0f0f0"}` : undefined,
                borderBottom: isMobileScreen ? `1px solid ${isDark ? "#303030" : "#f0f0f0"}` : undefined,
                padding: isMobileScreen ? "12px 16px" : "16px 12px",
                background: isDark ? "#141414" : "#fafafa",
                maxHeight: isMobileScreen ? undefined : "100%",
                overflowY: isMobileScreen ? undefined : "auto",
                zIndex: 10,
              }}
            >
              {/* 移动端分组切换与收纳指示栏 */}
              {isMobileScreen && (
                <div
                  onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "8px 12px",
                    borderRadius: 6,
                    background: isDark ? "#1f1f1f" : "#f0f2f5",
                    cursor: "pointer",
                    marginBottom: mobileMenuOpen ? 12 : 0,
                    border: `1px solid ${isDark ? "#303030" : "#e4e7eb"}`,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 8, overflow: "hidden" }}>
                    <AppstoreOutlined style={{ color: "#1677ff", fontSize: 16, flexShrink: 0 }} />
                    <span style={{ fontSize: 13, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      当前分组:{" "}
                      {activeCategoryInfo?.label ||
                        (activeCategory === GUIDE_KEY
                          ? "使用说明"
                          : activeCategory)}
                    </span>
                    {activeCategoryInfo && (
                      <Tag color="blue" style={{ margin: 0, fontSize: 11, padding: "0 6px" }}>
                        {activeCategoryInfo.totalFields} 项
                      </Tag>
                    )}
                    {(groupErrorCounts[activeCategory] || 0) > 0 && (
                      <Badge count={groupErrorCounts[activeCategory]} />
                    )}
                  </div>
                  <Button
                    size="small"
                    type="link"
                    icon={mobileMenuOpen ? <UpOutlined /> : <DownOutlined />}
                    style={{ padding: 0, fontSize: 12, flexShrink: 0 }}
                  >
                    {mobileMenuOpen ? "收起分组" : "切换分组"}
                  </Button>
                </div>
              )}

              {/* 搜索框与分组列表 (桌面端常驻，移动端点击展开后显示) */}
              {(!isMobileScreen || mobileMenuOpen) && (
                <>
                  {/* 搜索框（2/3）+ 使用说明入口（1/3），点击在右侧展开 */}
                  <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
                    <Input
                      placeholder="搜索配置名称或说明"
                      prefix={<SearchOutlined style={{ color: "#8c8c8c" }} />}
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      allowClear
                      style={{ flex: 2, minWidth: 0 }}
                    />
                    <Button
                      icon={<BulbOutlined style={{ flexShrink: 0 }} />}
                      onClick={() => {
                        setActiveCategory(GUIDE_KEY);
                        if (isMobileScreen) {
                          setMobileMenuOpen(false);
                        }
                      }}
                      style={{
                        flex: 1,
                        minWidth: 0,
                        padding: "0 8px",
                        fontSize: 12,
                        fontWeight: 500,
                        background:
                          activeCategory === GUIDE_KEY
                            ? "#1677ff"
                            : isDark
                              ? "#1f1f1f"
                              : "#eef4ff",
                        borderColor:
                          activeCategory === GUIDE_KEY
                            ? "#1677ff"
                            : isDark
                              ? "#1f1f1f"
                              : "#b8d8ff",
                        color:
                          activeCategory === GUIDE_KEY
                            ? "#ffffff"
                            : isDark
                              ? "#d9d9d9"
                              : "#0958d9",
                      }}
                    >
                      使用说明
                    </Button>
                  </div>

                  {/* 分组列表 */}
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    {categories.map((cat) => {
                      const isActive = activeCategory === cat.key;
                      const isVisible =
                        cat.matchCount === undefined || cat.matchCount > 0;
                      const errCount = groupErrorCounts[cat.key] || 0;

                      if (!isVisible) return null;

                      return (
                        <div
                          key={cat.key}
                          onClick={() => {
                            setActiveCategory(cat.key);
                            if (isMobileScreen) {
                              setMobileMenuOpen(false);
                            }
                          }}
                          style={{
                            padding: "9px 12px",
                            borderRadius: 6,
                            cursor: "pointer",
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            fontSize: 13,
                            fontWeight: isActive ? 600 : 400,
                            background: isActive
                              ? "#1677ff"
                              : isDark
                                ? "transparent"
                                : "transparent",
                            color: isActive
                              ? "#ffffff"
                              : isDark
                                ? "#d9d9d9"
                                : "#262626",
                            transition: "all 0.15s ease",
                          }}
                        >
                          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {cat.label}
                          </span>
                          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            {errCount > 0 && (
                              <Badge
                                count={errCount}
                                title={`${errCount} 项填写有误`}
                                style={{
                                  backgroundColor: "#ff4d4f",
                                  boxShadow: "none",
                                }}
                              />
                            )}
                            {cat.matchCount !== undefined ? (
                              <Badge
                                count={cat.matchCount}
                                style={{
                                  backgroundColor: isActive ? "#ffffff" : "#1677ff",
                                  color: isActive ? "#1677ff" : "#ffffff",
                                }}
                              />
                            ) : errCount === 0 ? (
                              <Text
                                style={{
                                  fontSize: 11,
                                  color: isActive ? "rgba(255, 255, 255, 0.75)" : "#8c8c8c",
                                }}
                              >
                                {cat.totalFields} 项
                              </Text>
                            ) : null}
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {/* 备份中心：固定在分组列表最底部，独立于 schema 分组 */}
                  <div
                    onClick={() => {
                      setActiveCategory(BACKUP_KEY);
                      if (isMobileScreen) {
                        setMobileMenuOpen(false);
                      }
                    }}
                    style={{
                      padding: "9px 12px",
                      borderRadius: 6,
                      cursor: "pointer",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      fontSize: 13,
                      fontWeight: activeCategory === BACKUP_KEY ? 600 : 500,
                      marginTop: 8,
                      borderTop: `1px dashed ${isDark ? "#303030" : "#e0e0e0"}`,
                      paddingTop: 12,
                      background: activeCategory === BACKUP_KEY ? "#1677ff" : "transparent",
                      color:
                        activeCategory === BACKUP_KEY
                          ? "#ffffff"
                          : isDark
                            ? "#d9d9d9"
                            : "#262626",
                      transition: "all 0.15s ease",
                    }}
                  >
                    <span
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      <CloudServerOutlined style={{ fontSize: 13, flexShrink: 0 }} />
                      备份中心
                    </span>
                  </div>
                </>
              )}
            </Col>

            {/* 右侧：分组详情与表单项 (独立滚动区，不与左侧联动) */}
            <Col
              xs={24}
              md={19}
              style={{
                padding: "20px 24px",
                maxHeight: isMobileScreen ? undefined : "100%",
                overflowY: isMobileScreen ? undefined : "auto",
              }}
            >
              {activeCategory === GUIDE_KEY && (
                <ConfigGuidePanel
                  categories={categories}
                  isDark={isDark}
                  onNavigate={(key) => {
                    setActiveCategory(key);
                    if (isMobileScreen) {
                      setMobileMenuOpen(false);
                    }
                  }}
                />
              )}

              {activeCategory === BACKUP_KEY && <BackupCenterPage />}

              {activeCategory !== GUIDE_KEY && activeCategory !== BACKUP_KEY && (
              <>
              {activeGroupMeta && (
                <div
                  style={{
                    marginBottom: 20,
                    paddingBottom: 12,
                    borderBottom: `1px solid ${isDark ? "#282828" : "#f0f0f0"}`,
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "flex-end",
                    flexWrap: "wrap",
                    gap: 8,
                  }}
                >
                  <div style={{ flex: 1, marginRight: 12 }}>
                    <Title level={4} style={{ margin: 0, fontSize: 16 }}>
                      {activeGroupMeta.description || activeCategory}
                    </Title>
                    {activeGroupMeta.hint && (
                      <MarkdownHint
                        content={activeGroupMeta.hint}
                        style={{
                          fontSize: 12,
                          display: "block",
                          marginTop: 4,
                          color: isDark ? "#8c8c8c" : "#595959",
                          lineHeight: 1.6,
                        }}
                      />
                    )}
                  </div>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 12,
                      flexShrink: 0,
                    }}
                  >
                    {headerSwitchKey && headerSwitchSchema && (
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                          padding: "6px 12px",
                          border: `1px solid ${isDark ? "#303030" : "#f0f0f0"}`,
                          borderRadius: 6,
                          background: isDark ? "#1f1f1f" : "#fafafa",
                        }}
                      >
                        <Text strong style={{ fontSize: 13, whiteSpace: "nowrap" }}>
                          {headerSwitchSchema.description}
                        </Text>
                        {headerSwitchSchema.hint && (
                          <Tooltip
                            title={
                              <div style={{ maxWidth: 360, fontSize: 12, lineHeight: 1.7 }}>
                                <MarkdownHint content={headerSwitchSchema.hint} />
                              </div>
                            }
                          >
                            <QuestionCircleOutlined
                              style={{ fontSize: 12, color: "#1677ff", cursor: "help" }}
                            />
                          </Tooltip>
                        )}
                        <Switch
                          size="small"
                          checked={Boolean(headerSwitchValue)}
                          onChange={(v) =>
                            handleFieldChange(activeCategory, headerSwitchKey, v)
                          }
                        />
                      </div>
                    )}
                    <Tag color="default" style={{ margin: 0 }}>
                      字段数: {currentGroupFields.length}
                    </Tag>
                  </div>
                </div>
              )}

              {groupErrorCounts[activeCategory] > 0 && (
                <Alert
                  type="error"
                  showIcon
                  message={`当前分组内有 ${groupErrorCounts[activeCategory]} 项配置填写有误，请核对并修改标红字段。`}
                  style={{ marginBottom: 16, borderRadius: 6 }}
                />
              )}

              {currentGroupFields.length === 0 ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={
                    searchQuery
                      ? "未找到匹配该关键词的配置项"
                      : "该分组下暂无可配置字段"
                  }
                  style={{ margin: "60px 0" }}
                />
              ) : (
                <ConfigGroupFields
                  activeCategory={activeCategory}
                  fields={displayFields}
                  providers={providers}
                  personas={personas}
                  errors={errors}
                  groupSuggestions={groupSuggestions}
                  onFieldChange={(fieldKey, newVal) =>
                    handleFieldChange(activeCategory, fieldKey, newVal)
                  }
                />
              )}
              </>
              )}
            </Col>
          </Row>
        </Spin>
      </Card>
    </div>
  );
};

interface FieldVM {
  key: string;
  schema: SchemaFieldItem;
  value: unknown;
}

interface BasicGroupOrFieldsProps {
  activeCategory: string;
  fields: FieldVM[];
  providers: { id: string; name: string; type?: string; label?: string }[];
  personas: { id: string; name: string; label?: string }[];
  errors: Record<string, Record<string, string>>;
  groupSuggestions: string[];
  onFieldChange: (fieldKey: string, newVal: unknown) => void;
}

/** 组合卡段定义：key 为字段 key，flex 控制宽度分配，boxed 表示该段内嵌一个小边框。 */
interface CardSectionSpec {
  key: string;
  flex: string;
  boxed?: boolean;
}

/**
 * 各分组的单行组合卡布局：每张卡与普通字段卡同高、段间竖分隔线、禁止换行。
 * 未出现在这里的字段按常规半行/整行流式排布；未配置组合卡的分组维持原通用网格。
 */
const COMBINED_CARD_ROWS: Record<string, CardSectionSpec[][]> = {
  basic: [
    [
      { key: "group_list_mode", flex: "0 0 240px" },
      { key: "auto_analysis_time", flex: "1 1 auto" },
      { key: "stagger_minutes", flex: "0 0 270px" },
    ],
    [
      { key: "analysis_days", flex: "1 1 0" },
      { key: "max_messages", flex: "1 1 0" },
      { key: "min_messages_threshold", flex: "1 1 0" },
    ],
    [
      { key: "profile_display_mode", flex: "1 1 0" },
      { key: "profile_image_opacity", flex: "1 1 0" },
      { key: "profile_image_size_mode", flex: "1 1 0" },
    ],
  ],
  delivery: [
    [
      { key: "delivery_numeric_as_private", flex: "1 1 auto" },
      { key: "delivery_enabled", flex: "0 0 280px", boxed: true },
    ],
  ],
};

const ConfigGroupFields: React.FC<BasicGroupOrFieldsProps> = ({
  activeCategory,
  fields,
  providers,
  personas,
  errors,
  groupSuggestions,
  onFieldChange,
}) => {
  const { token } = theme.useToken();
  const isBasic = activeCategory === "basic";
  const cardRows = COMBINED_CARD_ROWS[activeCategory] || [];
  const cardKeySet = new Set(cardRows.flat().map((s) => s.key));
  const restFields = fields.filter((f) => !cardKeySet.has(f.key));

  const renderField = (field: FieldVM, borderless = false) => (
    <FieldRenderer
      fieldKey={field.key}
      fieldSchema={field.schema}
      value={field.value}
      providers={providers}
      personas={personas}
      borderless={borderless}
      fullKeyPath={`${activeCategory}.${field.key}`}
      error={errors[activeCategory]?.[field.key]}
      subErrors={errors[activeCategory]}
      suggestions={
        // 报告投递 / 群分析重点 / 增量设置等需要填群号的分组，
        // 统一继承基础设置里已配置的群聊作为下拉建议
        ["delivery", "group_focus", "incremental"].includes(activeCategory)
          ? groupSuggestions
          : undefined
      }
      onChange={(newVal) => onFieldChange(field.key, newVal)}
    />
  );

  // 单行工具条式组合卡：与普通字段卡同高，段间竖分隔线，禁止换行；boxed 段内嵌小边框
  const renderCombinedCard = (
    sections: { spec: CardSectionSpec; field: FieldVM }[],
    keyPrefix: string
  ) => (
    <Col xs={24} key={keyPrefix}>
      <div
        style={{
          border: `1px solid ${token.colorBorderSecondary}`,
          borderRadius: 6,
          background: token.colorBgContainer,
          boxShadow: "0 1px 2px rgba(0, 0, 0, 0.02)",
          padding: "12px 14px",
          display: "flex",
          flexWrap: "nowrap",
          alignItems: "stretch",
          marginBottom: 12,
          overflow: "hidden",
        }}
      >
        {sections.map((s, idx) => (
          <div
            key={s.spec.key}
            style={{
              flex: s.spec.flex,
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
              borderLeft:
                idx > 0 ? `1px solid ${token.colorBorderSecondary}` : undefined,
              paddingLeft: idx > 0 ? 14 : 0,
              paddingRight: idx < sections.length - 1 ? 14 : 0,
            }}
          >
            {s.spec.boxed ? (
              <div
                style={{
                  border: `1px solid ${token.colorBorderSecondary}`,
                  borderRadius: 6,
                  background: token.colorFillAlter,
                  padding: "8px 12px",
                  width: "100%",
                }}
              >
                {renderField(s.field, true)}
              </div>
            ) : (
              renderField(s.field, true)
            )}
          </div>
        ))}
      </div>
    </Col>
  );

  return (
    <Row gutter={[16, 0]}>
      {cardRows.map((sections, ci) => {
        const resolved = sections
          .map((spec) => ({ spec, field: fields.find((f) => f.key === spec.key) }))
          .filter(
            (s): s is { spec: CardSectionSpec; field: FieldVM } =>
              Boolean(s.field)
          );
        if (resolved.length === 0) return null;
        return renderCombinedCard(resolved, `combined-card-${ci}`);
      })}
      {restFields.map((field) => {
        // 只有结构性复杂控件占满整行，其余一律半行（一行两个）；
        // Provider / Persona 选择框同样走半行，与基础设置保持一致的密度。
        const isLongField =
          field.schema.type === "template_list" ||
          field.schema.type === "object" ||
          field.schema.type === "list" ||
          field.schema.type === "text" ||
          field.schema.type === "file" ||
          field.key.includes("prompt") ||
          field.key.includes("template");
        // 基础设置里的「屏蔽用户ID列表」固定半行，与开关类字段组成 2×2；
        // 各类专用 Provider ID 选择框固定半行（如绘图提示词专用不再独占整行）
        const forceHalf =
          field.key.endsWith("_provider_id") ||
          (isBasic && field.key === "bot_self_ids");

        return (
          <Col key={field.key} xs={24} lg={forceHalf ? 12 : isLongField ? 24 : 12}>
            {renderField(field)}
          </Col>
        );
      })}
    </Row>
  );
};
