import React, { useCallback, useState } from "react";
import {
  Button,
  Card,
  Empty,
  Input,
  Modal,
  Space,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  Upload,
  message,
} from "antd";
import {
  CloudDownloadOutlined,
  CloudServerOutlined,
  CloudUploadOutlined,
  DeleteOutlined,
  InboxOutlined,
  InfoCircleOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import {
  BACKUP_FORMAT_ID,
  LEGACY_BACKUP_FORMAT_IDS,
  BackupPayload,
  WebDavBackupItem,
  exportBackup,
  importBackup,
  listWebDavBackups,
  pushBackupToWebDav,
  restoreBackupFromWebDav,
  saveWebDavConfig,
} from "../../../entities/backup/api/backupApi";
import { useTheme } from "../../../shared/lib/useTheme";

const { Text, Paragraph, Title } = Typography;

/**
 * 备份中心页面。
 *
 * 核心功能只有两个：导出备份、从备份文件恢复；
 * 每个功能都提供「本机文件」与「WebDAV（第三方协议）」两条通道。
 */
export const BackupCenterPage: React.FC = () => {
  const { isDark } = useTheme();
  const [pending, setPending] = useState<BackupPayload | null>(null);
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [pushing, setPushing] = useState(false);
  const [remoteList, setRemoteList] = useState<WebDavBackupItem[] | null>(null);
  const [remoteLoading, setRemoteLoading] = useState(false);
  const [restoringName, setRestoringName] = useState("");
  const [davUrl, setDavUrl] = useState("");
  const [davUser, setDavUser] = useState("");
  const [davPass, setDavPass] = useState("");
  const [davSaving, setDavSaving] = useState(false);

  const handleSaveDavConfig = async () => {
    if (!davUrl.trim()) {
      message.error("WebDAV 地址不能为空");
      return;
    }
    setDavSaving(true);
    try {
      const ok = await saveWebDavConfig({
        webdav_url: davUrl.trim(),
        webdav_username: davUser.trim(),
        webdav_password: davPass,
      });
      if (ok) {
        message.success("WebDAV 连接配置已保存，报告归档与配置备份一并生效");
      }
    } finally {
      setDavSaving(false);
    }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const payload = await exportBackup();
      if (!payload) {
        message.error("导出失败，请检查后端日志");
        return;
      }
      const blob = new Blob([JSON.stringify(payload, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `群聊总结配置备份_${payload.created_at.replace(
        /[: ]/g,
        "-"
      )}.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      message.success("备份文件已开始下载，请妥善保存");
    } finally {
      setExporting(false);
    }
  };

  const handleImport = async () => {
    if (!pending) return;
    setImporting(true);
    try {
      const result = await importBackup(pending);
      if (result) {
        message.success(`已恢复 ${result.restored_groups} 个配置分组并保存生效`);
        setPending(null);
      }
    } finally {
      setImporting(false);
    }
  };

  const handleFileSelected = (file: File) => {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = JSON.parse(String(reader.result)) as BackupPayload;
        const acceptedIds = [BACKUP_FORMAT_ID, ...LEGACY_BACKUP_FORMAT_IDS];
        if (!acceptedIds.includes(parsed.backup_format)) {
          message.error("这不是本插件导出的备份文件");
          return;
        }
        if (!parsed.config || typeof parsed.config !== "object") {
          message.error("备份文件中没有配置数据");
          return;
        }
        setPending(parsed);
      } catch {
        message.error("文件解析失败，请确认选择的是有效的 JSON 备份文件");
      }
    };
    reader.readAsText(file);
  };

  const handlePushToWebDav = async () => {
    setPushing(true);
    try {
      const result = await pushBackupToWebDav();
      if (result) {
        message.success(`备份已推送到 WebDAV：${result.remote_key}`);
        handleListRemote();
      }
    } finally {
      setPushing(false);
    }
  };

  const handleListRemote = useCallback(async () => {
    setRemoteLoading(true);
    try {
      const items = await listWebDavBackups();
      if (items !== null) {
        setRemoteList(items);
      }
    } finally {
      setRemoteLoading(false);
    }
  }, []);

  const handleRestoreRemote = async (filename: string) => {
    setRestoringName(filename);
    try {
      const result = await restoreBackupFromWebDav(filename);
      if (result) {
        message.success(
          `已从 ${filename} 恢复 ${result.restored_groups} 个配置分组并保存生效`
        );
      }
    } finally {
      setRestoringName("");
    }
  };

  const groupCount = pending ? Object.keys(pending.config).length : 0;

  const cardTitle = (icon: React.ReactNode, text: string) => (
    <Space size={8}>
      {icon}
      <span style={{ fontSize: 14, fontWeight: 600 }}>{text}</span>
    </Space>
  );

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 12,
        width: "100%",
      }}
    >
      {/* 页头：标题 + 问号悬浮说明 */}
      <div
        style={{
          paddingBottom: 12,
          borderBottom: `1px solid ${isDark ? "#303030" : "#f0f0f0"}`,
        }}
      >
        <Title level={4} style={{ margin: 0, fontSize: 16 }}>
          备份中心
          <Tooltip
            title={
              <div style={{ fontSize: 12, lineHeight: 1.7 }}>
                备份包含插件的<strong>全部配置项</strong>（分组与字段取值），
                用于在新的服务器上安装插件后一键恢复。运行数据（历史报告、增量分析状态等）
                与旧服务器的群消息绑定，不包含在备份内。恢复时只覆盖备份中存在的分组，
                备份里没有的分组（例如新版插件新增项）不会被清空。
              </div>
            }
          >
            <InfoCircleOutlined
              style={{
                fontSize: 14,
                color: "#1677ff",
                cursor: "help",
                marginLeft: 8,
              }}
            />
          </Tooltip>
        </Title>
        <Paragraph type="secondary" style={{ margin: "6px 0 0 0", fontSize: 12 }}>
          导出备份、从备份文件恢复，各有「本机文件」与「WebDAV（第三方协议）」两条通道。
        </Paragraph>
      </div>

      {/* WebDAV 连接配置：与上传设置共享同一批字段，放在页面最顶部供先配置连接 */}
      <Card
        size="small"
        title={cardTitle(
          <CloudServerOutlined style={{ color: "#1677ff" }} />,
          "WebDAV 连接配置"
        )}
      >
        <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 12 }}>
          与「上传设置」里的 WebDAV 是同一份值，在任意一处修改均会同步生效。默认留空，按需填写。
        </Paragraph>
        <Space size={12} style={{ width: "100%" }} wrap>
          <Input
            placeholder="WebDAV 地址，例如: https://dav.jianguoyun.com/dav/群聊总结"
            value={davUrl}
            onChange={(e) => setDavUrl(e.target.value)}
            style={{ fontFamily: "monospace", width: 420, minWidth: 240 }}
          />
          <Input
            placeholder="用户名"
            value={davUser}
            onChange={(e) => setDavUser(e.target.value)}
            style={{ width: 180 }}
          />
          <Input.Password
            placeholder="密码"
            value={davPass}
            onChange={(e) => setDavPass(e.target.value)}
            style={{ width: 180 }}
          />
          <Button type="primary" loading={davSaving} onClick={handleSaveDavConfig}>
            保存连接配置
          </Button>
        </Space>
      </Card>

      <Card
        size="small"
        title={cardTitle(
          <CloudDownloadOutlined style={{ color: "#1677ff" }} />,
          "导出备份"
        )}
      >
        <Tabs
          size="small"
          items={[
            {
              key: "local",
              label: "本机文件",
              children: (
                <div>
                  <Paragraph
                    type="secondary"
                    style={{ fontSize: 12, marginBottom: 12 }}
                  >
                    把当前生效的全部配置打包成一个 JSON 文件，下载到浏览器所在电脑。
                  </Paragraph>
                  <Button
                    type="primary"
                    icon={<CloudDownloadOutlined />}
                    loading={exporting}
                    onClick={handleExport}
                  >
                    导出并下载
                  </Button>
                </div>
              ),
            },
            {
              key: "webdav",
              label: "WebDAV（第三方协议）",
              children: (
                <div>
                  <Paragraph
                    type="secondary"
                    style={{ fontSize: 12, marginBottom: 12 }}
                  >
                    把配置备份推送到 WebDAV 服务器（存放在 config_backups
                    目录，与报告归档互不干扰）。连接配置在下方填写。
                  </Paragraph>
                  <Button
                    type="primary"
                    icon={<CloudServerOutlined />}
                    loading={pushing}
                    onClick={handlePushToWebDav}
                  >
                    备份到 WebDAV
                  </Button>
                </div>
              ),
            },
          ]}
        />
      </Card>

      <Card
        size="small"
        title={cardTitle(
          <CloudUploadOutlined style={{ color: "#1677ff" }} />,
          "从备份文件恢复"
        )}
      >
        <Tabs
          size="small"
          items={[
            {
              key: "local",
              label: "本机文件",
              children: (
                <div>
                  <Upload.Dragger
                    accept=".json,application/json"
                    maxCount={1}
                    showUploadList={false}
                    beforeUpload={(file) => {
                      handleFileSelected(file);
                      return false;
                    }}
                    style={{ marginBottom: pending ? 12 : 0 }}
                  >
                    <p className="ant-upload-drag-icon">
                      <InboxOutlined />
                    </p>
                    <p className="ant-upload-text" style={{ fontSize: 13 }}>
                      点击或拖拽备份 JSON 文件到此处
                    </p>
                  </Upload.Dragger>

                  {pending && (
                    <Card
                      size="small"
                      style={{
                        borderColor: "#1677ff",
                        background: isDark ? "#111d2c" : "#f0f7ff",
                      }}
                    >
                      <Space direction="vertical" size={6} style={{ width: "100%" }}>
                        <Space size={16} wrap>
                          <Tag color="blue">备份时间：{pending.created_at}</Tag>
                          <Tag color="blue">配置分组：{groupCount} 组</Tag>
                          <Tag color="default">来源：{pending.plugin_name}</Tag>
                          <Tag color="default">格式版本：v{pending.backup_version}</Tag>
                        </Space>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          确认后会把备份中的配置覆盖写入当前插件并立即保存生效，此操作不可撤销。
                        </Text>
                        <Space>
                          <Button
                            type="primary"
                            danger
                            icon={<CloudUploadOutlined />}
                            loading={importing}
                            onClick={handleImport}
                          >
                            确认恢复
                          </Button>
                          <Button
                            icon={<DeleteOutlined />}
                            disabled={importing}
                            onClick={() => setPending(null)}
                          >
                            放弃
                          </Button>
                        </Space>
                      </Space>
                    </Card>
                  )}
                </div>
              ),
            },
            {
              key: "webdav",
              label: "WebDAV（第三方协议）",
              children: (
                <div>
                  <Space style={{ marginBottom: 12 }}>
                    <Button
                      size="small"
                      icon={<ReloadOutlined />}
                      loading={remoteLoading}
                      onClick={handleListRemote}
                    >
                      刷新远端列表
                    </Button>
                  </Space>

                  {remoteList === null ? (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          点击「刷新远端列表」查看 WebDAV 上的备份文件
                        </Text>
                      }
                    />
                  ) : remoteList.length === 0 ? (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          远端还没有备份文件，先在上方「导出备份」里推送一份
                        </Text>
                      }
                    />
                  ) : (
                    <Table<WebDavBackupItem>
                      size="small"
                      rowKey="name"
                      dataSource={remoteList}
                      pagination={false}
                      columns={[
                        {
                          title: "备份文件",
                          dataIndex: "name",
                          render: (v: string) => (
                            <span
                              style={{ fontFamily: "monospace", fontSize: 12 }}
                            >
                              {v}
                            </span>
                          ),
                        },
                        {
                          title: "服务器时间",
                          dataIndex: "modified",
                          width: 230,
                          render: (v: string) => (
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              {v || "-"}
                            </Text>
                          ),
                        },
                        {
                          title: "大小",
                          dataIndex: "size",
                          width: 100,
                          render: (v: number) => (
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              {v > 0 ? `${(v / 1024).toFixed(1)} KB` : "-"}
                            </Text>
                          ),
                        },
                        {
                          title: "操作",
                          width: 110,
                          render: (_, record: WebDavBackupItem) => (
                            <Button
                              size="small"
                              type="primary"
                              ghost
                              loading={restoringName === record.name}
                              onClick={() => {
                                Modal.confirm({
                                  title: "确认从 WebDAV 恢复配置？",
                                  content: `将用 ${record.name} 中的配置覆盖当前插件配置并立即保存生效，此操作不可撤销。`,
                                  okText: "确认恢复",
                                  okButtonProps: { danger: true },
                                  cancelText: "取消",
                                  onOk: () => handleRestoreRemote(record.name),
                                });
                              }}
                            >
                              恢复
                            </Button>
                          ),
                        },
                      ]}
                    />
                  )}
                </div>
              ),
            },
          ]}
        />
      </Card>

      <Text type="secondary" style={{ fontSize: 11 }}>
        提示：备份文件包含 WebDAV、报告投递等分组的账号类信息，请妥善保管，不要分享给不可信的人。
      </Text>
    </div>
  );
};
