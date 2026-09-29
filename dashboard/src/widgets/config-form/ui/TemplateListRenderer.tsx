import React, { useState } from "react";
import {
  Card,
  Button,
  Space,
  Tag,
  Typography,
  Dropdown,
  Popconfirm,
  Empty,
  MenuProps,
  theme,
} from "antd";
import {
  PlusOutlined,
  DeleteOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
  SettingOutlined,
  DownOutlined,
} from "@ant-design/icons";
import { SchemaFieldItem } from "../../../entities/config/model/types";
import {
  AvailableProvider,
  AvailablePersona,
} from "../../../entities/config/api/configApi";
import { FieldRenderer } from "./FieldRenderer";

const { Text } = Typography;

/**
 * 特定规则模板的定制行布局：
 * fullRowFirst 的子字段独占整行；quadRow 的子字段在同一行内四等分（各占 1/4）；
 * 其余子字段仍走通用规则（text 等长字段整行）。
 */
const TEMPLATE_ROW_LAYOUTS: Record<
  string,
  { fullRowFirst: string[]; quadRow: string[] }
> = {
  group_focus_rules: {
    fullRowFirst: ["source_group"],
    quadRow: ["focus_users", "focus_links", "focus_at_all", "enabled"],
  },
};

interface TemplateListRendererProps {
  fieldKey: string;
  fieldSchema: SchemaFieldItem;
  value: unknown;
  providers?: AvailableProvider[];
  personas?: AvailablePersona[];
  fullKeyPath?: string;
  /** 透传给条目内单行文本字段的可选输入建议（如基础设置的群清单）。 */
  suggestions?: string[];
  onChange: (val: unknown) => void;
}

export const TemplateListRenderer: React.FC<TemplateListRendererProps> = ({
  fieldKey,
  fieldSchema,
  value,
  providers = [],
  personas = [],
  fullKeyPath,
  suggestions,
  onChange,
}) => {
  const { token } = theme.useToken();
  const [activeItemIndex, setActiveItemIndex] = useState<number | null>(null);
  // 收起/展开：默认全部收起，仅展示关键信息摘要；点击卡片头部切换
  const [collapsedSet, setCollapsedSet] = useState<ReadonlySet<number>>(new Set());

  const toggleCollapsed = (index: number) => {
    setCollapsedSet((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };

  const removeCollapsed = (index: number) => {
    setCollapsedSet((prev) => {
      if (!prev.has(index)) return prev;
      const next = new Set<number>();
      prev.forEach((i) => {
        if (i < index) next.add(i);
        else if (i > index) next.add(i - 1);
      });
      return next;
    });
  };

  const swapCollapsed = (a: number, b: number) => {
    setCollapsedSet((prev) => {
      const next = new Set<number>();
      prev.forEach((i) => {
        if (i === a) next.add(b);
        else if (i === b) next.add(a);
        else next.add(i);
      });
      return next;
    });
  };

  const rawList: Record<string, unknown>[] = Array.isArray(value)
    ? (value as Record<string, unknown>[])
    : Array.isArray(fieldSchema.default)
      ? (fieldSchema.default as Record<string, unknown>[])
      : [];

  const templates = (fieldSchema.templates as Record<
    string,
    {
      name?: string;
      description?: string;
      display_item?: string;
      items?: Record<string, SchemaFieldItem>;
    }
  >) || {};

  const templateKeys = Object.keys(templates);

  // 根据条目数据匹配模板 Key
  const findTemplateKey = (item: Record<string, unknown>): string | null => {
    if (item.__template_key && templates[String(item.__template_key)]) {
      return String(item.__template_key);
    }
    if (item.name && templates[String(item.name)]) {
      return String(item.name);
    }
    for (const [key, tpl] of Object.entries(templates)) {
      if (tpl.name === item.name || key === item.name) {
        return key;
      }
    }
    return templateKeys.length > 0 ? templateKeys[0] : null;
  };

  // 根据条目数据匹配模板定义
  const findTemplateForItem = (item: Record<string, unknown>) => {
    const key = findTemplateKey(item);
    return key ? templates[key] || null : null;
  };

  // 添加新条目
  const handleAddItem = (templateKey: string) => {
    const tpl = templates[templateKey];
    if (!tpl) return;

    const newItem: Record<string, unknown> = {
      __template_key: templateKey,
      name: tpl.name || templateKey,
    };

    if (tpl.items) {
      for (const [subKey, subField] of Object.entries(tpl.items)) {
        if (subField.default !== undefined) {
          newItem[subKey] = subField.default;
        }
      }
    }

    const nextList = [...rawList, newItem].map((item) => ({
      ...item,
      __template_key: findTemplateKey(item) || templateKey,
    }));
    onChange(nextList);
    setActiveItemIndex(nextList.length - 1);
    // 新添加的条目默认展开，便于立即编辑
    const newIndex = nextList.length - 1;
    setCollapsedSet((prev) => {
      if (!prev.has(newIndex)) return prev;
      const next = new Set(prev);
      next.delete(newIndex);
      return next;
    });
  };

  // 修改条目内字段
  const handleItemFieldChange = (
    index: number,
    subFieldKey: string,
    subVal: unknown
  ) => {
    const nextList = rawList.map((item, idx) => {
      const tplKey = findTemplateKey(item) || templateKeys[0] || "character";
      if (idx !== index) {
        return {
          ...item,
          __template_key: tplKey,
        };
      }
      return {
        ...item,
        __template_key: tplKey,
        [subFieldKey]: subVal,
      };
    });
    onChange(nextList);
  };

  // 删除条目
  const handleDeleteItem = (index: number) => {
    const nextList = rawList
      .filter((_, idx) => idx !== index)
      .map((item) => ({
        ...item,
        __template_key: findTemplateKey(item) || templateKeys[0] || "character",
      }));
    onChange(nextList);
    removeCollapsed(index);
    if (activeItemIndex === index) {
      setActiveItemIndex(null);
    } else if (activeItemIndex !== null && activeItemIndex > index) {
      setActiveItemIndex(activeItemIndex - 1);
    }
  };

  // 上移条目
  const handleMoveUp = (index: number) => {
    if (index <= 0) return;
    const nextList = [...rawList].map((item) => ({
      ...item,
      __template_key: findTemplateKey(item) || templateKeys[0] || "character",
    }));
    const temp = nextList[index - 1];
    nextList[index - 1] = nextList[index];
    nextList[index] = temp;
    onChange(nextList);
    swapCollapsed(index - 1, index);
    if (activeItemIndex === index) setActiveItemIndex(index - 1);
  };

  // 下移条目
  const handleMoveDown = (index: number) => {
    if (index >= rawList.length - 1) return;
    const nextList = [...rawList].map((item) => ({
      ...item,
      __template_key: findTemplateKey(item) || templateKeys[0] || "character",
    }));
    const temp = nextList[index + 1];
    nextList[index + 1] = nextList[index];
    nextList[index] = temp;
    onChange(nextList);
    swapCollapsed(index, index + 1);
    if (activeItemIndex === index) setActiveItemIndex(index + 1);
  };

  // 添加下拉菜单项
  const menuItems: MenuProps["items"] = templateKeys.map((tplKey) => {
    const tpl = templates[tplKey];
    return {
      key: tplKey,
      label: (
        <div>
          <div style={{ fontWeight: 600, fontSize: 12 }}>
            {tpl.name || tplKey}
          </div>
          {tpl.description && (
            <div style={{ fontSize: 11, color: token.colorTextSecondary }}>
              {tpl.description}
            </div>
          )}
        </div>
      ),
      onClick: () => handleAddItem(tplKey),
    };
  });

  return (
    <div style={{ width: "100%" }}>
      {rawList.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="暂无配置条目，请点击下方按钮添加"
          style={{
            margin: "12px 0",
            padding: "16px",
            background: token.colorFillAlter,
            borderRadius: 6,
            border: `1px dashed ${token.colorBorderSecondary}`,
          }}
        />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 12 }}>
          {rawList.map((item, index) => {
            const itemTemplateKey = findTemplateKey(item) || templateKeys[0] || "character";
            const tpl = findTemplateForItem(item);
            const subItems = tpl?.items || {};
            const rowLayout = TEMPLATE_ROW_LAYOUTS[fieldKey];

            // 标题展示
            const displayName =
              String(item.name || tpl?.name || `条目 #${index + 1}`);
            const priorityVal = item.priority !== undefined ? item.priority : null;
            const enableTagVal =
              item.enable !== undefined
                ? Boolean(item.enable)
                : item.enabled !== undefined
                  ? Boolean(item.enabled)
                  : null;
            const isCollapsed = collapsedSet.has(index);

            // 收起态的关键信息摘要：布尔只展示勾选项，文本截断展示
            const summaryChips = Object.entries(subItems)
              .filter(
                ([k]) =>
                  k !== "__template_key" &&
                  k !== "name" &&
                  k !== "enabled" &&
                  k !== "enable"
              )
              .flatMap(([k, f]) => {
                const v = item[k] !== undefined ? item[k] : f.default;
                if (f.type === "bool") {
                  return v
                    ? [{ key: k, text: `✓ ${f.description || k}`, color: "blue" }]
                    : [];
                }
                const text =
                  v === undefined || v === null ? "" : String(v).trim();
                if (!text) return [];
                const short = text.length > 20 ? `${text.slice(0, 20)}…` : text;
                return [
                  {
                    key: k,
                    text: `${f.description || k}: ${short}`,
                    color: "default",
                  },
                ];
              });

            const renderSubField = (
              subKey: string,
              subField: SchemaFieldItem,
              wrapperStyle?: React.CSSProperties
            ) => (
              <div key={subKey} style={wrapperStyle}>
                <FieldRenderer
                  fieldKey={subKey}
                  fieldSchema={subField}
                  value={item[subKey] !== undefined ? item[subKey] : subField.default}
                  providers={providers}
                  personas={personas}
                  isSubField={true}
                  fullKeyPath={`${fullKeyPath || fieldKey}.templates.${itemTemplateKey}.${subKey}`}
                  suggestions={suggestions}
                  onChange={(newSubVal) =>
                    handleItemFieldChange(index, subKey, newSubVal)
                  }
                />
              </div>
            );

            const isFullWidthSub = (
              subKey: string,
              subField: SchemaFieldItem
            ) =>
              subField.type === "template_list" ||
              subField.type === "text" ||
              subField.type === "file" ||
              subKey.includes("prompt") ||
              subKey.includes("image") ||
              subKey.includes("url") ||
              subKey.includes("key");

            return (
              <Card
                key={`${fieldKey}_item_${index}`}
                size="small"
                style={{
                  border: `1px solid ${token.colorBorderSecondary}`,
                  borderRadius: 6,
                  background: token.colorFillAlter,
                }}
                styles={{ body: { padding: "12px 14px" } }}
              >
                {/* 头部标题与控制按钮（点击头部可展开/收起条目） */}
                <div
                  onClick={() => toggleCollapsed(index)}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: isCollapsed ? 0 : 12,
                    paddingBottom: isCollapsed ? 0 : 8,
                    borderBottom: isCollapsed
                      ? undefined
                      : `1px solid ${token.colorBorderSecondary}`,
                    cursor: "pointer",
                    userSelect: "none",
                  }}
                >
                  <Space size={8} align="center">
                    <SettingOutlined style={{ color: "#2563eb", fontSize: 13 }} />
                    <Text strong style={{ fontSize: 13 }}>
                      {displayName}
                    </Text>
                    {priorityVal !== null && (
                      <Tag color="blue" style={{ margin: 0, fontSize: 10 }}>
                        优先级: {String(priorityVal)}
                      </Tag>
                    )}
                    {enableTagVal !== null && (
                      <Tag
                        color={enableTagVal ? "success" : "default"}
                        style={{ margin: 0, fontSize: 10 }}
                      >
                        {enableTagVal ? "已启用" : "已禁用"}
                      </Tag>
                    )}
                    <DownOutlined
                      style={{
                        fontSize: 11,
                        color: token.colorTextTertiary,
                        transform: isCollapsed ? "none" : "rotate(180deg)",
                        transition: "transform 0.2s",
                      }}
                    />
                  </Space>

                  <Space
                    size={4}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <Button
                      size="small"
                      type="text"
                      icon={<ArrowUpOutlined style={{ fontSize: 11 }} />}
                      disabled={index === 0}
                      onClick={() => handleMoveUp(index)}
                    />
                    <Button
                      size="small"
                      type="text"
                      icon={<ArrowDownOutlined style={{ fontSize: 11 }} />}
                      disabled={index === rawList.length - 1}
                      onClick={() => handleMoveDown(index)}
                    />
                    <Popconfirm
                      title="确认删除此配置条目？"
                      onConfirm={() => handleDeleteItem(index)}
                      okText="删除"
                      cancelText="取消"
                      okButtonProps={{ danger: true, size: "small" }}
                      cancelButtonProps={{ size: "small" }}
                    >
                      <Button
                        size="small"
                        type="text"
                        danger
                        icon={<DeleteOutlined style={{ fontSize: 11 }} />}
                      />
                    </Popconfirm>
                  </Space>
                </div>

                {/* 收起态：仅展示关键信息摘要 */}
                {isCollapsed ? (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                    {summaryChips.length > 0 ? (
                      summaryChips.map((chip) => (
                        <Tag
                          key={chip.key}
                          color={chip.color}
                          style={{ margin: 0, fontSize: 11, maxWidth: "100%" }}
                        >
                          {chip.text}
                        </Tag>
                      ))
                    ) : (
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        （未填写内容，点击展开进行配置）
                      </Text>
                    )}
                  </div>
                ) : (
                  <>
                {/* 条目内部各字段渲染 */}
                {rowLayout && rowLayout.quadRow.every((k) => subItems[k]) ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {rowLayout.fullRowFirst
                      .filter((k) => subItems[k])
                      .map((k) => renderSubField(k, subItems[k]))}
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
                        gap: "10px 12px",
                      }}
                    >
                      {rowLayout.quadRow.map((k) =>
                        renderSubField(k, subItems[k])
                      )}
                    </div>
                    {Object.entries(subItems)
                      .filter(
                        ([k]) =>
                          !rowLayout.fullRowFirst.includes(k) &&
                          !rowLayout.quadRow.includes(k)
                      )
                      .map(([k, f]) =>
                        renderSubField(
                          k,
                          f,
                          isFullWidthSub(k, f) ? { gridColumn: "1 / -1" } : undefined
                        )
                      )}
                  </div>
                ) : (
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "10px 16px" }}>
                    {Object.entries(subItems).map(([subKey, subField]) => {
                      const isFullWidth = isFullWidthSub(subKey, subField);

                      return renderSubField(
                        subKey,
                        subField,
                        isFullWidth ? { gridColumn: "1 / -1" } : undefined
                      );
                    })}
                  </div>
                )}
                </>
                )}
              </Card>
            );
          })}
        </div>
      )}

      {/* 底部添加条目按钮 */}
      {templateKeys.length > 1 ? (
        <Dropdown menu={{ items: menuItems }} placement="bottomLeft">
          <Button
            type="dashed"
            icon={<PlusOutlined />}
            style={{ width: "100%" }}
          >
            添加配置项 <DownOutlined style={{ fontSize: 10, marginLeft: 4 }} />
          </Button>
        </Dropdown>
      ) : templateKeys.length === 1 ? (
        <Button
          type="dashed"
          icon={<PlusOutlined />}
          style={{ width: "100%" }}
          onClick={() => handleAddItem(templateKeys[0])}
        >
          添加 {templates[templateKeys[0]]?.name || "新条目"}
        </Button>
      ) : null}
    </div>
  );
};
