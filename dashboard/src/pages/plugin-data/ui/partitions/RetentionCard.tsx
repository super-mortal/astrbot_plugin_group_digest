import React, { useEffect, useRef, useState } from "react";
import { InputNumber, Space, Switch, Tooltip, Typography, message } from "antd";
import { QuestionCircleOutlined } from "@ant-design/icons";
import { fetchRetentionConfig, saveRetentionConfig } from "../../../../entities/plugin-data/api/pluginDataApi";

const { Text } = Typography;

/**
 * 自动清理策略控件：内嵌在数据管理页标签栏右侧的紧凑形态。
 * 设置项与原「数据保留」配置组同源（总开关 + 保留天数）。
 * 无保存按钮：开关切换即保存；保留天数在输入完成（失焦/回车）后保存。
 */
export const RetentionCard: React.FC = () => {
  const [enabled, setEnabled] = useState(true);
  const [days, setDays] = useState<number>(7);
  const [saving, setSaving] = useState(false);
  // 保存最新一次已提交到服务端的值，避免失焦时用旧 state 重复提交
  const committedRef = useRef({ enabled: true, days: 7 });

  useEffect(() => {
    fetchRetentionConfig().then((cfg) => {
      if (cfg) {
        setEnabled(cfg.enable_auto_cleanup);
        setDays(cfg.data_retention_days);
        committedRef.current = {
          enabled: cfg.enable_auto_cleanup,
          days: cfg.data_retention_days,
        };
      }
    });
  }, []);

  const commit = async (nextEnabled: boolean, nextDays: number) => {
    const last = committedRef.current;
    if (last.enabled === nextEnabled && last.days === nextDays) return;
    setSaving(true);
    try {
      const ok = await saveRetentionConfig({
        enable_auto_cleanup: nextEnabled,
        data_retention_days: nextDays,
      });
      if (ok) {
        committedRef.current = { enabled: nextEnabled, days: nextDays };
        message.success("自动清理策略已保存");
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <Space size={10} align="center" wrap>
      <Tooltip
        title={
          <div style={{ fontSize: 12, lineHeight: 1.6 }}>
            自动清理范围（保存在这台服务器上的全部运行数据）：
            Trace 执行记录（traces.db）、过期 Checkpoint、历史报告目录中超期的图片/HTML 文件、
            KV 存储中的历史报告摘要与增量分析批次、群成员头像缓存与临时渲染缓存；
            每天 04:17（北京时间）执行，插件启动后也会先跑一轮。
            关闭开关则数据永久保留，可随时在「存储空间概览」表格中手动清理。
          </div>
        }
      >
        <Text style={{ fontSize: 13, cursor: "help" }}>
          自动清理 <QuestionCircleOutlined style={{ fontSize: 11, color: "#8c8c8c" }} />
        </Text>
      </Tooltip>
      <Switch
        size="small"
        checked={enabled}
        loading={saving}
        onChange={(checked) => {
          setEnabled(checked);
          commit(checked, days);
        }}
      />
      <Space size={4} align="center">
        <Text type="secondary" style={{ fontSize: 12 }}>
          保留
        </Text>
        <InputNumber
          size="small"
          min={1}
          max={365}
          value={days}
          onChange={(v) => setDays(Number(v) || 7)}
          onBlur={() => commit(enabled, days)}
          onPressEnter={() => commit(enabled, days)}
          style={{ width: 70 }}
        />
        <Text type="secondary" style={{ fontSize: 12 }}>
          天
        </Text>
      </Space>
    </Space>
  );
};
