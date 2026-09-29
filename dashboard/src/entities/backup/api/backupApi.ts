import { apiGet, apiPost, extractData } from "../../../shared/api/bridge";

/** 当前配置概况（备份中心页头展示）。 */
export interface BackupOverview {
  group_count: number;
  field_count: number;
}

/** 备份文件负载结构（与后端 backup_routes 的导出格式一一对应）。 */
export interface BackupPayload {
  backup_format: string;
  backup_version: number;
  plugin_name: string;
  created_at: string;
  config: Record<string, Record<string, unknown>>;
}

/** 备份文件格式标识，用于前端快速校验用户选择的文件。 */
export const BACKUP_FORMAT_ID = "astrbot_plugin_group_digest_backup";

/** 旧版插件名导出的备份格式标识，上传校验时同样接受。 */
export const LEGACY_BACKUP_FORMAT_IDS = [
  "astrbot_plugin_qq_group_daily_analysis_backup",
];

export async function fetchBackupOverview(): Promise<BackupOverview | null> {
  const res = await apiGet<BackupOverview>("backup/overview");
  return extractData<BackupOverview>(res);
}

export async function exportBackup(): Promise<BackupPayload | null> {
  const res = await apiGet<BackupPayload>("backup/export");
  return extractData<BackupPayload>(res);
}

export async function importBackup(
  backup: BackupPayload
): Promise<{ restored_groups: number } | null> {
  const res = await apiPost<{ restored_groups: number }>("backup/import", {
    backup,
  });
  return extractData<{ restored_groups: number }>(res);
}

/** WebDAV 远端备份文件条目。 */
export interface WebDavBackupItem {
  name: string;
  size: number;
  modified: string;
}

/** WebDAV 连接配置（与「上传设置」分组同一份数据）。 */
export interface WebDavConnectionConfig {
  webdav_url: string;
  webdav_username: string;
  webdav_password: string;
}

/** 读取 WebDAV 连接配置。 */
export async function fetchWebDavConfig(): Promise<WebDavConnectionConfig | null> {
  const res = await apiGet<WebDavConnectionConfig>("backup/webdav/config");
  return extractData<WebDavConnectionConfig>(res);
}

/** 保存 WebDAV 连接配置（报告归档与配置备份一并生效）。 */
export async function saveWebDavConfig(
  config: WebDavConnectionConfig
): Promise<boolean> {
  const res = await apiPost<null>("backup/webdav/config", config);
  return res !== null;
}

/** 把当前配置备份推送到已配置的 WebDAV 服务器。 */
export async function pushBackupToWebDav(): Promise<{
  remote_key: string;
  filename: string;
} | null> {
  const res = await apiPost<{ remote_key: string; filename: string }>(
    "backup/webdav/push",
    {}
  );
  return extractData<{ remote_key: string; filename: string }>(res);
}

/** 列出 WebDAV 远端备份目录中的备份文件清单。 */
export async function listWebDavBackups(): Promise<WebDavBackupItem[] | null> {
  const res = await apiGet<WebDavBackupItem[]>("backup/webdav/list");
  return extractData<WebDavBackupItem[]>(res);
}

/** 从 WebDAV 远端备份文件恢复配置。 */
export async function restoreBackupFromWebDav(
  filename: string
): Promise<{ restored_groups: number; filename: string } | null> {
  const res = await apiPost<{ restored_groups: number; filename: string }>(
    "backup/webdav/restore",
    { filename }
  );
  return extractData<{ restored_groups: number; filename: string }>(res);
}
