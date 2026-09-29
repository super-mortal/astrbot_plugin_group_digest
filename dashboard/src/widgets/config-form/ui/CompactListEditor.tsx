import React, { useState } from "react";
import { Button, Input, Tag, Tooltip, Typography, theme } from "antd";
import {
  DownOutlined,
  PlusOutlined,
  UpOutlined,
  ClockCircleOutlined,
} from "@ant-design/icons";

const { Text } = Typography;

const SANS_MONO_FONT =
  "'JetBrains Mono', 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace";

/** 折叠态最多直接展示的时间条目数，超出的用「+N」省略。 */
const COLLAPSED_MAX_TAGS = 4;

interface CompactListEditorProps {
  value: string[];
  onChange: (val: string[]) => void;
  /** 折叠态列表为空时的占位文案 */
  emptyText?: string;
}

/**
 * 紧凑的时间列表编辑器（用于 auto_analysis_time 等「条目多但希望不占空间」的字段）：
 * - 折叠态：单行、高度与普通下拉一致，超出部分以「+N」省略，不换行；
 * - 点击整行展开，展示全部条目并可增删；再次点击收起。
 */
export const CompactListEditor: React.FC<CompactListEditorProps> = ({
  value,
  onChange,
  emptyText = "暂未设置，点击添加",
}) => {
  const { token } = theme.useToken();
  const [expanded, setExpanded] = useState(false);
  const [adding, setAdding] = useState(false);
  const [inputVal, setInputVal] = useState("");

  const listVal = Array.isArray(value) ? value : [];

  const commitAdd = () => {
    const trimmed = inputVal.trim();
    if (trimmed && !listVal.includes(trimmed)) {
      onChange([...listVal, trimmed]);
    }
    setInputVal("");
    setAdding(false);
  };

  const removeTag = (tag: string) => {
    onChange(listVal.filter((item) => item !== tag));
  };

  const extraCount = Math.max(0, listVal.length - COLLAPSED_MAX_TAGS);

  if (!expanded) {
    return (
      <div
        onClick={() => setExpanded(true)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          height: 32,
          padding: "0 8px 0 11px",
          border: `1px solid ${token.colorBorder}`,
          borderRadius: 6,
          background: token.colorBgContainer,
          cursor: "pointer",
          overflow: "hidden",
          transition: "border-color 0.2s",
        }}
        title="点击展开编辑全部时间"
      >
        <ClockCircleOutlined
          style={{ fontSize: 13, color: token.colorTextTertiary, flexShrink: 0 }}
        />
        {listVal.length === 0 ? (
          <Text type="secondary" style={{ fontSize: 13 }}>
            {emptyText}
          </Text>
        ) : (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 4,
              flex: 1,
              minWidth: 0,
              overflow: "hidden",
              whiteSpace: "nowrap",
            }}
          >
            {listVal.slice(0, COLLAPSED_MAX_TAGS).map((item) => (
              <Tag
                key={item}
                style={{
                  margin: 0,
                  fontSize: 12,
                  padding: "1px 7px",
                  borderRadius: 4,
                  lineHeight: "20px",
                  fontFamily: SANS_MONO_FONT,
                  flexShrink: 0,
                }}
              >
                {item}
              </Tag>
            ))}
            {extraCount > 0 && (
              <Tooltip title={`还有 ${extraCount} 个时间，点击展开查看全部`}>
                <Tag
                  style={{
                    margin: 0,
                    fontSize: 12,
                    padding: "1px 7px",
                    borderRadius: 4,
                    lineHeight: "20px",
                    borderStyle: "dashed",
                    color: token.colorTextSecondary,
                    flexShrink: 0,
                  }}
                >
                  +{extraCount} …
                </Tag>
              </Tooltip>
            )}
          </div>
        )}
        <Text
          type="secondary"
          style={{ fontSize: 11, flexShrink: 0, marginLeft: "auto" }}
        >
          共 {listVal.length} 个
        </Text>
        <DownOutlined
          style={{ fontSize: 11, color: token.colorTextTertiary, flexShrink: 0 }}
        />
      </div>
    );
  }

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "6px 8px",
        alignItems: "center",
        padding: "8px 10px",
        border: `1px solid ${token.colorBorder}`,
        borderRadius: 6,
        background: token.colorBgContainer,
      }}
    >
      {listVal.map((tag) => (
        <Tag
          key={tag}
          closable
          onClose={() => removeTag(tag)}
          style={{
            margin: 0,
            fontSize: 12,
            padding: "2px 8px",
            borderRadius: 4,
            fontFamily: SANS_MONO_FONT,
          }}
        >
          {tag}
        </Tag>
      ))}
      {adding ? (
        <Input
          size="small"
          placeholder="HH:MM，如 21:30"
          style={{ width: 130, fontFamily: SANS_MONO_FONT }}
          value={inputVal}
          onChange={(e) => setInputVal(e.target.value)}
          onBlur={commitAdd}
          onPressEnter={commitAdd}
          autoFocus
        />
      ) : (
        <Tag
          onClick={() => setAdding(true)}
          style={{
            borderStyle: "dashed",
            cursor: "pointer",
            margin: 0,
            padding: "2px 8px",
            borderRadius: 4,
          }}
        >
          <PlusOutlined style={{ marginRight: 4 }} /> 添加时间
        </Tag>
      )}
      <Button
        type="link"
        size="small"
        icon={<UpOutlined style={{ fontSize: 10 }} />}
        style={{ padding: "0 4px", fontSize: 11, marginLeft: "auto" }}
        onClick={() => setExpanded(false)}
      >
        收起
      </Button>
    </div>
  );
};
