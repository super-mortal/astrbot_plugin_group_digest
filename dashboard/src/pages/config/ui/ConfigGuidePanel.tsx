import React from "react";
import { Typography, Tag } from "antd";
import {
  RocketOutlined,
  QuestionCircleOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";

const { Title, Text, Paragraph } = Typography;

/** 快速上手步骤：按左侧配置分组的顺序依次引导。 */
const QUICK_START: {
  title: string;
  desc: string;
  groupKey: string;
  optional?: boolean;
}[] = [
  {
    title: "确定要分析哪些群、几点出报告",
    desc: "在「基础设置」里选好群聊权限模式并填入要分析的群聊标识（QQ 群可以直接填群号，QQ 官方机器人等平台请先在目标会话里用 /sid 获取完整会话 ID 再填），设好分析天数与输出格式；自动出报告的时间点也在这组的底部填写（24 小时制，如 21:30）。",
    groupKey: "basic",
  },
  {
    title: "确认使用哪个大模型",
    desc: "在「LLM 设置」里选择用于分析的 Provider。不确定就保持默认，插件会按 配置的 Provider → 主 Provider → 当前会话 Provider 逐级回退。",
    groupKey: "llm",
  },
  {
    title: "挑选报告里要出现的内容",
    desc: "在「分析内容功能开关」里决定是否生成话题总结、群友称号、金句与聊天质量锐评，以及各内容的数量上限。",
    groupKey: "analysis_features",
  },
  {
    title: "给每个群设置分析侧重（可选）",
    desc: "在「群分析重点」里为不同的群单独指定：重点关注某位成员、群里的链接、@全体成员，或用自然语言补充要求。",
    groupKey: "group_focus",
  },
  {
    title: "活跃大群开启增量分析（可选）",
    desc: "每天几百上千条消息的大群，在「增量分析设置」里开启增量模式：按消息量分批分析，最后合并成日报；小群保持默认即可。",
    groupKey: "incremental",
  },
  {
    title: "选择报告的呈现样式",
    desc: "在「图片渲染策略」里决定出图样式与渲染超时；需要网页版报告时，在「HTML 设置」里启用并配置外链。",
    groupKey: "t2i_rendering",
  },
  {
    title: "配置报告发到哪（可选）",
    desc: "在「报告投递」里添加规则：一行代表一个目标，可以发到其他群、你的私聊，或同时投递到多处；不配置就发回被分析的群。",
    groupKey: "delivery",
  },
  {
    title: "配置报告归档（可选）",
    desc: "在「上传设置」里把报告上传到群文件、群相册，或通过 WebDAV 备份到你自己的服务器。",
    groupKey: "upload_settings",
  },
  {
    title: "先手动跑一次看看效果",
    desc: "点右上角「手动触发分析」，填入目标群聊的会话标识（QQ 群填群号，其他平台用 /sid 获取）即可立刻生成一份报告，不用等到定时时间。",
    groupKey: "",
  },
];

/** 功能概览条目。isFork = 本仓库相对上游新增的功能。 */
const FEATURES: { title: string; desc: string; isFork?: boolean }[] = [
  {
    title: "群聊总结",
    desc: "把群里一段时间的聊天交给大模型，产出话题总结、群友称号、金句、24 小时活跃度图表与聊天质量锐评。",
  },
  {
    title: "多平台支持",
    desc: "支持 OneBot（NapCat / LLOneBot / SnowLuma 等）、QQ 官方机器人、Telegram、Discord 五类平台。",
  },
  {
    title: "三种报告形态",
    desc: "图片、纯文本、HTML 网页可任选其一或同时输出；HTML 配合自建外链还能直接发可点击的网址。",
  },
  {
    title: "每日群漫画",
    desc: "把当日话题改编成一张群漫画，可直接生成，也可在出报告后自动联动。",
  },
  {
    title: "报告投递与遥控",
    desc: "报告默认发回被分析的群，也可改发到其他群、私聊或同时投递多处；还能在私聊里用 /群列表、/远程分析 遥控分析指定群。",
    isFork: true,
  },
  {
    title: "群分析重点",
    desc: "为每个群单独指定分析侧重：重点关注某位成员、群里的链接、@全体成员，或用自然语言补充，重点要求自动注入该群的提示词。",
    isFork: true,
  },
  {
    title: "WebDAV 备份",
    desc: "报告可上传到群文件、群相册，也可通过 WebDAV 备份到你自建的服务器（坚果云、Nextcloud、群晖、Alist 等），不受平台限制。",
    isFork: true,
  },
  {
    title: "配置备份中心",
    desc: "一键把全部配置导出为 JSON 文件，或推送到 WebDAV 远端；换服务器时从文件或远端清单一键恢复。",
    isFork: true,
  },
  {
    title: "数据保留自动清理",
    desc: "Trace 记录、报告文件、KV 历史摘要与增量批次等运行数据按保留天数自动清理，防止长期运行占满磁盘。",
    isFork: true,
  },
];

/** 常见疑问。 */
const FAQ: { q: string; a: string; groupKey: string }[] = [
  {
    q: "定时任务到点了却没出报告？",
    a: "先检查「基础设置 → 群聊权限模式」：如果选了白名单但列表是空的，等于没有任何群被允许，定时任务不会启动。日志里会有明确提示。",
    groupKey: "basic",
  },
  {
    q: "报告想发到别的群或者我的私聊？",
    a: "在「报告投递」里配置规则表：一行代表一个目标，源群留空表示对所有群生效，目标留空表示发回原群。",
    groupKey: "delivery",
  },
  {
    q: "群太多、消息量太大，一次分析吃不下？",
    a: "打开「增量分析设置 → 启用增量分析」，再在「走增量模式的群」里只填需要的那几个群。插件会按设定条数分批分析后再合并成日报。",
    groupKey: "incremental",
  },
  {
    q: "怎么让报告里的时间、日期按北京时间走？",
    a: "无需设置。定时触发与报告中的日期、统计口径一律使用北京时间（UTC+8），与服务器所在时区无关。",
    groupKey: "basic",
  },
  {
    q: "每个群想关注的重点不一样？",
    a: "在「群分析重点」里为每个群单独配置：可以重点关注某位成员、群里的链接、@全体成员，也能用自由文本补充要求。",
    groupKey: "group_focus",
  },
  {
    q: "报告想存到自己的服务器？",
    a: "在「上传设置」里填好 WebDAV 地址与账号即可；备份中心还支持把配置一起备份到 WebDAV，恢复也是一键的。",
    groupKey: "upload_settings",
  },
];

interface ConfigGuidePanelProps {
  categories: { key: string; label: string; totalFields: number }[];
  isDark: boolean;
  /** 点击跳转到某个配置分组。 */
  onNavigate: (groupKey: string) => void;
}

export const ConfigGuidePanel: React.FC<ConfigGuidePanelProps> = ({
  categories,
  isDark,
  onNavigate,
}) => {
  const borderColor = isDark ? "#303030" : "#f0f0f0";
  const subTextColor = isDark ? "#8c8c8c" : "#595959";
  const cardBg = isDark ? "#1a1a1a" : "#fafafa";

  const sectionStyle: React.CSSProperties = {
    marginBottom: 24,
  };

  const sectionTitle: React.CSSProperties = {
    fontSize: 15,
    fontWeight: 600,
    margin: "0 0 10px 0",
    display: "flex",
    alignItems: "center",
    gap: 8,
  };

  const jumpButton = (groupKey: string, label: string) => (
    <Tag
      color="blue"
      style={{ cursor: "pointer", margin: 0, fontSize: 11, padding: "1px 8px" }}
      onClick={() => groupKey && onNavigate(groupKey)}
    >
      {label}
    </Tag>
  );

  return (
    <div style={{ width: "100%" }}>
      {/* 页头 */}
      <div
        style={{
          marginBottom: 20,
          paddingBottom: 12,
          borderBottom: `1px solid ${borderColor}`,
        }}
      >
        <Title level={4} style={{ margin: 0, fontSize: 16 }}>
          <RocketOutlined style={{ color: "#1677ff", marginRight: 8 }} />
          使用说明
        </Title>
        <Paragraph
          type="secondary"
          style={{ margin: "6px 0 0 0", fontSize: 12 }}
        >
          下面是这个插件的功能概览与上手步骤，顺序与左侧配置分组一致，每一项都可以点击跳转。
          带有「本仓库新增」标记的是相对上游新增的能力。
        </Paragraph>
      </div>

      {/* 一、能做什么 */}
      <div style={sectionStyle}>
        <h3 style={sectionTitle}>
          <ThunderboltOutlined style={{ color: "#1677ff" }} />
          这个插件能做什么
        </h3>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
            gap: 10,
          }}
        >
          {FEATURES.map((item) => (
            <div
              key={item.title}
              style={{
                background: cardBg,
                border: `1px solid ${borderColor}`,
                borderRadius: 6,
                padding: "10px 12px",
              }}
            >
              <div
                style={{
                  fontSize: 13,
                  fontWeight: 600,
                  marginBottom: 4,
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  flexWrap: "wrap",
                }}
              >
                {item.title}
                {item.isFork && (
                  <Tag color="green" style={{ margin: 0, fontSize: 10 }}>
                    本仓库新增
                  </Tag>
                )}
              </div>
              <div style={{ fontSize: 12, lineHeight: 1.7, color: subTextColor }}>
                {item.desc}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 二、快速上手 */}
      <div style={sectionStyle}>
        <h3 style={sectionTitle}>
          <RocketOutlined style={{ color: "#1677ff" }} />
          快速上手（按左侧顺序依次设置）
        </h3>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {QUICK_START.map((step, index) => (
            <div
              key={step.title}
              style={{
                display: "flex",
                gap: 12,
                background: cardBg,
                border: `1px solid ${borderColor}`,
                borderRadius: 6,
                padding: "10px 12px",
                alignItems: "flex-start",
              }}
            >
              <span
                style={{
                  flex: "none",
                  width: 20,
                  height: 20,
                  marginTop: 1,
                  borderRadius: "50%",
                  background: "#1677ff",
                  color: "#fff",
                  fontSize: 11,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                {index + 1}
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    flexWrap: "wrap",
                    marginBottom: 4,
                  }}
                >
                  <span style={{ fontSize: 13, fontWeight: 600 }}>
                    {step.title}
                  </span>
                  {step.optional && (
                    <Tag style={{ margin: 0, fontSize: 10 }}>可选</Tag>
                  )}
                  {step.groupKey
                    ? jumpButton(step.groupKey, "去配置")
                    : jumpButton("", "点右上角按钮")}
                </div>
                <div
                  style={{ fontSize: 12, lineHeight: 1.7, color: subTextColor }}
                >
                  {step.desc}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 三、常见问题 */}
      <div style={sectionStyle}>
        <h3 style={sectionTitle}>
          <QuestionCircleOutlined style={{ color: "#1677ff" }} />
          常见问题
        </h3>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {FAQ.filter(
            (item) =>
              !item.groupKey || categories.some((c) => c.key === item.groupKey)
          ).map((item) => (
            <div
              key={item.q}
              style={{
                background: cardBg,
                border: `1px solid ${borderColor}`,
                borderRadius: 6,
                padding: "10px 12px",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  flexWrap: "wrap",
                  marginBottom: 4,
                }}
              >
                <span style={{ fontSize: 13, fontWeight: 600 }}>{item.q}</span>
                {item.groupKey && jumpButton(item.groupKey, "去配置")}
              </div>
              <div style={{ fontSize: 12, lineHeight: 1.7, color: subTextColor }}>
                {item.a}
              </div>
            </div>
          ))}
        </div>
      </div>

      <Text type="secondary" style={{ fontSize: 11 }}>
        配置修改后需点击右上角「保存配置」才会生效；重新读取会丢弃未保存的改动。
      </Text>
    </div>
  );
};
