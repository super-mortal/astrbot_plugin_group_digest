"""
WebUI 配置备份与恢复路由 (Backup Routes)
把插件当前配置导出为单个 JSON 备份文件，并支持从备份文件恢复，
便于把整套配置迁移到新的服务器。

提供两条通道：浏览器下载 / 上传（离线文件），以及 WebDAV 远程备份
（推送到已配置的 WebDAV 服务器，并从远端清单一键恢复）。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ....shared.constants import PLUGIN_NAME
from ....utils.logger import logger
from ....utils.time_utils import format_local_pattern
from ..web_compat import WebApiResponse, error_response, json_response, request

if TYPE_CHECKING:
    from ....application.services.analysis_application_service import (
        AnalysisApplicationService,
    )
    from ...config.config_manager import ConfigManager
    from ...reporting.dispatcher import ReportDispatcher
    from ...storage.webdav_uploader import WebDavUploader

BACKUP_FORMAT_ID = "astrbot_plugin_group_digest_backup"
"""备份文件格式标识，导入时用于校验文件确实来自本插件。"""

LEGACY_BACKUP_FORMAT_IDS = frozenset({"astrbot_plugin_qq_group_daily_analysis_backup"})
"""旧版插件名导出的备份格式标识，恢复时同样接受以便跨改名迁移。"""

BACKUP_FORMAT_VERSION = 1
"""备份文件结构版本号；字段仅增不减时递增，导入时拒绝更新版本的文件。"""

BACKUP_FILENAME_PATTERN = "config_backup_%Y%m%d_%H%M%S.json"
"""WebDAV 备份文件的命名格式。"""


def _accepted_format_ids() -> frozenset[str]:
    """返回所有可接受的备份格式标识（含旧版插件名）。"""
    return frozenset({BACKUP_FORMAT_ID, *LEGACY_BACKUP_FORMAT_IDS})


class BackupRoutes:
    """配置备份与恢复 Web API 路由处理器。"""

    analysis_service: AnalysisApplicationService | None
    report_dispatcher: ReportDispatcher | None

    def __init__(
        self,
        analysis_service: AnalysisApplicationService | None = None,
        report_dispatcher: ReportDispatcher | None = None,
    ) -> None:
        self.analysis_service = analysis_service
        self.report_dispatcher = report_dispatcher

    def _resolve_config_manager(self) -> ConfigManager | None:
        """按优先级取得配置管理器实例。"""
        if self.analysis_service:
            return self.analysis_service.config_manager
        if self.report_dispatcher:
            return self.report_dispatcher.config_manager
        return None

    def _resolve_webdav_uploader(self) -> WebDavUploader | None:
        """按需构造 WebDAV 上传器；未配置地址时返回 None。"""
        cfg_mgr = self._resolve_config_manager()
        if not cfg_mgr:
            return None
        from ...storage.webdav_uploader import WebDavUploader

        uploader = WebDavUploader(cfg_mgr)
        if not uploader.is_available():
            return None
        return uploader

    def _build_backup_payload(self) -> dict[str, object] | None:
        """把当前配置打包成备份负载；配置管理器不可用时返回 None。"""
        cfg_mgr = self._resolve_config_manager()
        if not cfg_mgr:
            return None
        config_dict = {str(k): v for k, v in cfg_mgr.config.items()}
        return {
            "backup_format": BACKUP_FORMAT_ID,
            "backup_version": BACKUP_FORMAT_VERSION,
            "plugin_name": PLUGIN_NAME,
            "created_at": format_local_pattern("%Y-%m-%d %H:%M:%S"),
            "config": config_dict,
        }

    def _apply_backup(self, backup: dict[str, object]) -> int:
        """把备份负载中的配置覆盖写入当前插件并保存。

        恢复采用合并语义：备份中存在的分组被覆盖写入，备份中没有的分组
        （例如新版插件新增的分组）保留当前值，避免旧备份清空新功能配置。

        Args:
            backup: 已通过格式校验的备份负载。

        Returns:
            int: 恢复写入的分组数量。
        """
        cfg_mgr = self._resolve_config_manager()
        if not cfg_mgr:
            raise RuntimeError("配置管理器未初始化")

        new_config = backup.get("config")
        if not isinstance(new_config, dict) or not new_config:
            raise ValueError("备份文件中没有配置数据")

        config_obj = cfg_mgr.config
        restored_groups = 0
        for group_key, group_value in new_config.items():
            config_obj[str(group_key)] = group_value
            restored_groups += 1

        cfg_mgr.save_config()
        logger.info(f"备份中心已从备份恢复 {restored_groups} 个配置分组。")
        return restored_groups

    @staticmethod
    def _validate_backup(backup: object) -> tuple[dict[str, object] | None, str]:
        """校验备份负载的格式标识与版本号。

        Args:
            backup: 待校验的负载对象。

        Returns:
            tuple[dict[str, object] | None, str]: (校验通过的负载, 错误消息)；
            校验通过时错误消息为空字符串。
        """
        if not isinstance(backup, dict):
            return None, "缺少有效的备份内容"
        if backup.get("backup_format") not in _accepted_format_ids():
            return None, "这不是本插件导出的备份文件（格式标识不匹配）"
        version = backup.get("backup_version")
        if not isinstance(version, int) or version > BACKUP_FORMAT_VERSION:
            return None, f"备份文件版本过新（{version}），请先升级插件后再恢复"
        if not isinstance(backup.get("config"), dict):
            return None, "备份文件中没有配置数据"
        return backup, ""

    async def api_get_backup_overview(self) -> WebApiResponse:
        """返回当前配置概况，供备份中心页面展示。"""
        try:
            cfg_mgr = self._resolve_config_manager()
            if not cfg_mgr:
                return error_response("配置管理器未初始化", status_code=500)

            config_dict = {str(k): v for k, v in cfg_mgr.config.items()}
            field_count = sum(
                len(v) if isinstance(v, dict) else 1 for v in config_dict.values()
            )
            return json_response(
                {
                    "status": "ok",
                    "data": {
                        "group_count": len(config_dict),
                        "field_count": field_count,
                    },
                }
            )
        except Exception as e:
            logger.error(f"获取备份概况异常: {e}", exc_info=True)
            return error_response(str(e), status_code=500)

    async def api_export_backup(self) -> WebApiResponse:
        """导出当前配置为备份 JSON，由前端触发浏览器下载。"""
        try:
            payload = self._build_backup_payload()
            if payload is None:
                return error_response("配置管理器未初始化", status_code=500)

            logger.info("备份中心已导出当前配置备份。")
            return json_response({"status": "ok", "data": payload})
        except Exception as e:
            logger.error(f"导出配置备份异常: {e}", exc_info=True)
            return error_response(str(e), status_code=500)

    async def api_import_backup(self) -> WebApiResponse:
        """从备份 JSON 恢复配置（浏览器上传通道）。"""
        try:
            try:
                body = await request.json()
            except Exception:
                body = {}

            backup, err = self._validate_backup(body.get("backup"))
            if backup is None:
                return error_response(err, status_code=400)

            restored_groups = self._apply_backup(backup)
            return json_response(
                {
                    "status": "ok",
                    "message": f"已恢复 {restored_groups} 个配置分组并保存生效",
                    "data": {"restored_groups": restored_groups},
                }
            )
        except Exception as e:
            logger.error(f"恢复配置备份异常: {e}", exc_info=True)
            return error_response(str(e), status_code=500)

    # ==================== WebDAV 备份通道 ====================

    async def api_get_webdav_config(self) -> WebApiResponse:
        """返回 WebDAV 连接配置，供备份中心页面直接查看与编辑。

        与「上传设置」分组读取的是同一份配置值，两处修改互相同步。
        """
        try:
            cfg_mgr = self._resolve_config_manager()
            if not cfg_mgr:
                return error_response("配置管理器未初始化", status_code=500)

            return json_response(
                {
                    "status": "ok",
                    "data": {
                        "webdav_url": cfg_mgr.get_webdav_url(),
                        "webdav_username": cfg_mgr.get_webdav_username(),
                        "webdav_password": cfg_mgr.get_webdav_password(),
                    },
                }
            )
        except Exception as e:
            logger.error(f"读取 WebDAV 连接配置异常: {e}", exc_info=True)
            return error_response(str(e), status_code=500)

    async def api_save_webdav_config(self) -> WebApiResponse:
        """保存备份中心页面上编辑的 WebDAV 连接配置。

        写入的是「上传设置」分组的同一批字段，因此在此处修改后，
        上传设置页与 WebDAV 报告归档会一并生效。
        """
        try:
            try:
                body = await request.json()
            except Exception:
                body = {}

            url = str(body.get("webdav_url") or "").strip()
            username = str(body.get("webdav_username") or "").strip()
            password = str(body.get("webdav_password") or "")

            if not url:
                return error_response("WebDAV 地址不能为空", status_code=400)

            cfg_mgr = self._resolve_config_manager()
            if not cfg_mgr:
                return error_response("配置管理器未初始化", status_code=500)

            config_obj = cfg_mgr.config
            group = config_obj.get("upload_settings")
            if not isinstance(group, dict):
                group = {}
                config_obj["upload_settings"] = group
            group["webdav_url"] = url
            group["webdav_username"] = username
            group["webdav_password"] = password
            cfg_mgr.save_config()

            logger.info("备份中心已更新 WebDAV 连接配置。")
            return json_response(
                {
                    "status": "ok",
                    "message": "WebDAV 连接配置已保存，报告归档与配置备份一并生效",
                }
            )
        except Exception as e:
            logger.error(f"保存 WebDAV 连接配置异常: {e}", exc_info=True)
            return error_response(str(e), status_code=500)

    async def api_webdav_push_backup(self) -> WebApiResponse:
        """把当前配置备份推送到已配置的 WebDAV 服务器。"""
        try:
            payload = self._build_backup_payload()
            if payload is None:
                return error_response("配置管理器未初始化", status_code=500)

            uploader = self._resolve_webdav_uploader()
            if uploader is None:
                return error_response(
                    "尚未配置 WebDAV 地址，请先在「上传设置」中完成 WebDAV 配置",
                    status_code=400,
                )

            filename = format_local_pattern(BACKUP_FILENAME_PATTERN)
            content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            remote_key = await uploader.upload_backup_data(filename, content)
            if not remote_key:
                return error_response(
                    "备份上传失败，请检查 WebDAV 地址与账号配置", status_code=502
                )

            logger.info(f"备份中心已推送配置备份到 WebDAV：{remote_key}")
            return json_response(
                {
                    "status": "ok",
                    "message": "备份已推送到 WebDAV",
                    "data": {"remote_key": remote_key, "filename": filename},
                }
            )
        except Exception as e:
            logger.error(f"推送 WebDAV 配置备份异常: {e}", exc_info=True)
            return error_response(str(e), status_code=500)

    async def api_webdav_list_backups(self) -> WebApiResponse:
        """列出 WebDAV 远端备份目录中的备份文件清单。"""
        try:
            uploader = self._resolve_webdav_uploader()
            if uploader is None:
                return error_response(
                    "尚未配置 WebDAV 地址，请先在「上传设置」中完成 WebDAV 配置",
                    status_code=400,
                )

            backups = await uploader.list_backups()
            return json_response({"status": "ok", "data": backups})
        except Exception as e:
            logger.error(f"列举 WebDAV 配置备份异常: {e}", exc_info=True)
            return error_response(str(e), status_code=500)

    async def api_webdav_restore_backup(self) -> WebApiResponse:
        """从 WebDAV 远端备份文件恢复配置。"""
        try:
            try:
                body = await request.json()
            except Exception:
                body = {}

            filename = str(body.get("filename") or "").strip()
            if not filename or "/" in filename or "\\" in filename:
                return error_response("备份文件名非法", status_code=400)

            uploader = self._resolve_webdav_uploader()
            if uploader is None:
                return error_response(
                    "尚未配置 WebDAV 地址，请先在「上传设置」中完成 WebDAV 配置",
                    status_code=400,
                )

            content = await uploader.download_backup(filename)
            if content is None:
                return error_response(
                    "从 WebDAV 下载备份失败，请检查文件是否存在", status_code=502
                )

            try:
                backup = json.loads(content.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                return error_response(f"备份文件解析失败：{e}", status_code=400)

            validated, err = self._validate_backup(backup)
            if validated is None:
                return error_response(err, status_code=400)

            restored_groups = self._apply_backup(validated)
            return json_response(
                {
                    "status": "ok",
                    "message": f"已从 {filename} 恢复 {restored_groups} 个配置分组并保存生效",
                    "data": {"restored_groups": restored_groups, "filename": filename},
                }
            )
        except Exception as e:
            logger.error(f"从 WebDAV 恢复配置备份异常: {e}", exc_info=True)
            return error_response(str(e), status_code=500)
