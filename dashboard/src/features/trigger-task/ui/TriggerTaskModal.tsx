import React from "react";
import { Modal, Form, Input, Select, Row, Col } from "antd";
import { ConnectedPlatform } from "../../../entities/task/api/taskApi";
import { LLMProviderItem } from "../../../entities/trace/api/traceApi";
import { ReportTemplateItem, formatTemplateOptions } from "../../../entities/report/model/templates";

interface TriggerTaskModalProps {
  open: boolean;
  groupId: string;
  groupName: string;
  platform: string;
  providerId?: string;
  templateName?: string;
  submitting: boolean;
  connectedPlatforms?: ConnectedPlatform[];
  loadingPlatforms?: boolean;
  providers?: LLMProviderItem[];
  loadingProviders?: boolean;
  templates?: ReportTemplateItem[];
  loadingTemplates?: boolean;
  onGroupIdChange: (val: string) => void;
  onGroupNameChange: (val: string) => void;
  onPlatformChange: (val: string) => void;
  onProviderChange?: (val: string) => void;
  onTemplateChange?: (val: string) => void;
  onClose: () => void;
  onSubmit: () => void;
}

export const TriggerTaskModal: React.FC<TriggerTaskModalProps> = ({
  open,
  groupId,
  groupName,
  platform,
  providerId = "auto",
  templateName = "auto",
  submitting,
  connectedPlatforms = [],
  loadingPlatforms = false,
  providers = [],
  loadingProviders = false,
  templates = [],
  loadingTemplates = false,
  onGroupIdChange,
  onGroupNameChange,
  onPlatformChange,
  onProviderChange,
  onTemplateChange,
  onClose,
  onSubmit,
}) => {
  const platformOptions = [
    { label: "自动识别 / 默认平台 (推荐)", value: "auto" },
    ...(connectedPlatforms.length > 0
      ? connectedPlatforms.map((p) => ({
          label: p.label,
          value: p.id,
        }))
      : [
          { label: "OneBot (aiocqhttp)", value: "aiocqhttp" },
          { label: "QQ 官方机器人", value: "qq_official" },
          { label: "Telegram", value: "telegram" },
          { label: "Discord", value: "discord" },
        ]),
  ];

  const providerOptions = [
    { label: "跟随系统默认配置 (推荐)", value: "auto" },
    ...providers.map((p) => ({
      label: p.label || `${p.name} (${p.id})`,
      value: p.id,
    })),
  ];

  const templateOptions = formatTemplateOptions(templates, true);

  return (
    <Modal
      title="手动触发群聊总结"
      open={open}
      onOk={onSubmit}
      onCancel={onClose}
      confirmLoading={submitting}
      okText="立即触发"
      cancelText="取消"
      destroyOnHidden
      centered
      width={720}
      styles={{ body: { maxHeight: "calc(100vh - 220px)", overflowY: "auto" } }}
    >
      <Form layout="vertical" style={{ marginTop: 12 }}>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item label="群号 / 会话标识" required>
              <Input
                placeholder="例如: 123456789"
                value={groupId}
                onChange={(e) => onGroupIdChange(e.target.value)}
                autoFocus
              />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item label="群名称 (选填)">
              <Input
                placeholder="例如: 核心交流群"
                value={groupName}
                onChange={(e) => onGroupNameChange(e.target.value)}
              />
            </Form.Item>
          </Col>
        </Row>

        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              label="接入平台"
              extra={
                connectedPlatforms.length > 0
                  ? `已自动检测到 ${connectedPlatforms.length} 个活跃平台实例`
                  : "自动调用当前已连接的 Bot 平台"
              }
            >
              <Select
                value={platform}
                onChange={onPlatformChange}
                loading={loadingPlatforms}
                options={platformOptions}
              />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              label="指定大模型 Provider (选填)"
              extra="留空则使用系统默认 Provider"
            >
              <Select
                value={providerId}
                onChange={onProviderChange}
                loading={loadingProviders}
                options={providerOptions}
              />
            </Form.Item>
          </Col>
        </Row>

        <Form.Item
          label="报告视觉模板 (选填)"
          extra="指定本次分析生成的报告模板主题，留空则使用基础配置中的默认模板"
          style={{ marginBottom: 0 }}
        >
          <Select
            value={templateName}
            onChange={onTemplateChange}
            loading={loadingTemplates}
            options={templateOptions}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
};

