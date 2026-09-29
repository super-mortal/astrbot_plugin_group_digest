"""备份中心 WebDAV 通道单元测试。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from src.infrastructure.storage.webdav_uploader import WebDavUploader
from src.infrastructure.webui.routes.backup_routes import (
    BACKUP_FORMAT_ID,
    BACKUP_FORMAT_VERSION,
    BackupRoutes,
)


def _build_uploader() -> WebDavUploader:
    """构造带最小配置的 WebDAV 上传器替身。"""
    config = SimpleNamespace(
        get_webdav_url=lambda: "https://dav.example.com/dav/",
        get_webdav_username=lambda: "user",
        get_webdav_password=lambda: "pass",
        get_webdav_remote_dir=lambda: "reports/${group_id}",
        get_webdav_public_base_url=lambda: "",
        get_webdav_timeout=lambda: 5,
        get_webdav_verify_ssl=lambda: True,
        get_webdav_proxy=lambda: "",
        get_enable_webdav_upload=lambda: True,
        get_webdav_upload_image=lambda: True,
        get_webdav_upload_html=lambda: True,
        get_webdav_upload_comic=lambda: True,
    )
    return WebDavUploader(config)  # type: ignore[arg-type]


def test_parse_propfind_extracts_json_files_only():
    """PROPFIND 解析应只保留 JSON 文件，忽略目录并按名称倒序。"""
    xml = """<?xml version="1.0"?>
    <d:multistatus xmlns:d="DAV:">
      <d:response>
        <d:href>/dav/config_backups/</d:href>
        <d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat>
      </d:response>
      <d:response>
        <d:href>/dav/config_backups/config_backup_20260928_140000.json</d:href>
        <d:propstat><d:prop>
          <d:resourcetype/>
          <d:getcontentlength>1024</d:getcontentlength>
          <d:getlastmodified>Mon, 28 Sep 2026 14:00:00 GMT</d:getlastmodified>
        </d:prop></d:propstat>
      </d:response>
      <d:response>
        <d:href>/dav/config_backups/config_backup_20260927_120000.json</d:href>
        <d:propstat><d:prop>
          <d:resourcetype/>
          <d:getcontentlength>2048</d:getcontentlength>
          <d:getlastmodified>Sun, 27 Sep 2026 12:00:00 GMT</d:getlastmodified>
        </d:prop></d:propstat>
      </d:response>
      <d:response>
        <d:href>/dav/config_backups/readme.txt</d:href>
        <d:propstat><d:prop><d:resourcetype/></d:prop></d:propstat>
      </d:response>
    </d:multistatus>"""

    items = WebDavUploader._parse_propfind(xml)

    assert [item["name"] for item in items] == [
        "config_backup_20260928_140000.json",
        "config_backup_20260927_120000.json",
    ]
    assert items[0]["size"] == 1024
    assert "2026" in str(items[0]["modified"])


def test_parse_propfind_handles_invalid_xml():
    """非法 XML 应返回空列表而不是抛错。"""
    assert WebDavUploader._parse_propfind("not xml at all") == []


def _build_routes(config_dict: dict) -> tuple[BackupRoutes, Mock]:
    """构造带配置替身的备份路由。"""
    config_manager = SimpleNamespace(
        config=config_dict,
        save_config=Mock(),
    )
    routes = BackupRoutes(
        analysis_service=SimpleNamespace(config_manager=config_manager)
    )  # type: ignore[arg-type]
    return routes, config_manager.save_config


def test_webdav_restore_validates_and_applies_backup(tmp_path):
    """WebDAV 恢复应校验格式并按合并语义写入配置。"""
    routes, save_config = _build_routes({"basic": {"analysis_days": 1}})
    backup = {
        "backup_format": BACKUP_FORMAT_ID,
        "backup_version": BACKUP_FORMAT_VERSION,
        "plugin_name": "astrbot_plugin_group_digest",
        "created_at": "2026-09-28 14:00:00",
        "config": {
            "basic": {"analysis_days": 3},
            "delivery": {"delivery_enabled": True},
        },
    }

    routes._resolve_webdav_uploader = lambda: SimpleNamespace(  # type: ignore[method-assign]
        download_backup=AsyncMock(return_value=json.dumps(backup).encode("utf-8"))
    )

    import asyncio

    async def scenario():
        # 直接调用校验与应用核心，绕过 HTTP body 解析
        uploader = routes._resolve_webdav_uploader()
        assert uploader is not None
        content = await uploader.download_backup("x.json")
        assert content is not None
        validated, err = routes._validate_backup(json.loads(content.decode("utf-8")))
        assert validated is not None and err == ""
        return routes._apply_backup(validated)

    restored = asyncio.run(scenario())

    assert restored == 2
    save_config.assert_called_once()
    assert routes._resolve_config_manager().config["basic"]["analysis_days"] == 3  # type: ignore[union-attr]
    assert (
        routes._resolve_config_manager().config["delivery"]["delivery_enabled"] is True
    )  # type: ignore[union-attr]


def test_validate_backup_rejects_bad_payload():
    """格式标识不匹配与版本过新的备份都应被拒绝。"""
    _, err_new = BackupRoutes._validate_backup(
        {"backup_format": BACKUP_FORMAT_ID, "backup_version": 99, "config": {}}
    )
    assert "版本过新" in err_new

    _, err_fmt = BackupRoutes._validate_backup(
        {"backup_format": "other", "backup_version": 1, "config": {}}
    )
    assert "格式标识不匹配" in err_fmt

    _, err_empty = BackupRoutes._validate_backup({"config": {}})
    assert "格式标识不匹配" in err_empty


def test_webdav_connection_config_roundtrip(tmp_path):
    """备份中心读写 WebDAV 连接配置应落到「上传设置」分组。"""
    import asyncio

    config_dict: dict = {}
    routes, save_config = _build_routes(config_dict)

    async def save():
        # 模拟请求体
        from unittest.mock import patch

        async def fake_json():
            return {
                "webdav_url": "https://dav.example.com/dav/",
                "webdav_username": "user",
                "webdav_password": "pass",
            }

        with patch(
            "src.infrastructure.webui.routes.backup_routes.request"
        ) as mock_request:
            mock_request.json = fake_json
            return await routes.api_save_webdav_config()

    response = asyncio.run(save())
    assert response is not None
    assert save_config.called
    group = config_dict["upload_settings"]
    assert group["webdav_url"] == "https://dav.example.com/dav/"
    assert group["webdav_username"] == "user"
    assert group["webdav_password"] == "pass"
