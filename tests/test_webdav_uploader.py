"""WebDAV 报告上传单元测试。

覆盖开关判定、远程目录渲染与净化、公网链接构造、目录逐级创建、PUT 收发
以及失败静默等关键行为。通过替换 httpx.AsyncClient 避免真实网络请求。
"""

import asyncio
import base64
import os
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from src.infrastructure.storage.webdav_uploader import (
    KIND_COMIC,
    KIND_HTML,
    KIND_IMAGE,
    WebDavUploader,
)


class FakeResponse:
    """仅携带状态码的响应替身。"""

    def __init__(self, status_code: int):
        self.status_code = status_code


class FakeAsyncClient:
    """记录 MKCOL 与 PUT 调用的 httpx.AsyncClient 替身。"""

    instances: list["FakeAsyncClient"] = []
    mkcol_status = 201
    put_status = 201

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.mkcols: list[str] = []
        self.puts: list[tuple[str, bytes]] = []
        FakeAsyncClient.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def request(self, method: str, url: str):
        self.mkcols.append(url)
        return FakeResponse(FakeAsyncClient.mkcol_status)

    async def put(self, url: str, content=None, headers=None):
        self.puts.append((url, content or b""))
        return FakeResponse(FakeAsyncClient.put_status)


@pytest.fixture
def fake_http(monkeypatch):
    """把 httpx.AsyncClient 替换为记录型替身。"""
    FakeAsyncClient.instances = []
    FakeAsyncClient.mkcol_status = 201
    FakeAsyncClient.put_status = 201
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    return FakeAsyncClient


def _config(**overrides):
    """构造一个字段齐全的假配置管理器。"""
    values = {
        "get_enable_webdav_upload": lambda: True,
        "get_webdav_url": lambda: "https://dav.example.com/reports",
        "get_webdav_username": lambda: "user",
        "get_webdav_password": lambda: "pass",
        "get_webdav_remote_dir": lambda: "${group_id}/${date}",
        "get_webdav_upload_image": lambda: True,
        "get_webdav_upload_html": lambda: True,
        "get_webdav_upload_comic": lambda: False,
        "get_webdav_public_base_url": lambda: "",
        "get_webdav_verify_ssl": lambda: True,
        "get_webdav_proxy": lambda: "",
        "get_webdav_timeout": lambda: 30,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_is_enabled_respects_master_and_kind_switches():
    """测试总开关、地址完整性与类型开关共同决定是否上传"""
    assert WebDavUploader(_config()).is_enabled(KIND_IMAGE) is True
    assert WebDavUploader(_config()).is_enabled(KIND_COMIC) is False
    assert (
        WebDavUploader(_config(get_enable_webdav_upload=lambda: False)).is_enabled(
            KIND_IMAGE
        )
        is False
    )
    assert (
        WebDavUploader(_config(get_webdav_url=lambda: "   ")).is_enabled(KIND_IMAGE)
        is False
    )
    assert (
        WebDavUploader(_config(get_webdav_upload_image=lambda: False)).is_enabled(
            KIND_IMAGE
        )
        is False
    )


def test_remote_dir_renders_variables_and_sanitizes_segments():
    """测试远程目录按变量渲染，并剔除路径穿越与非法字符"""
    uploader = WebDavUploader(_config())

    rendered = uploader._remote_dir("123456")
    segments = rendered.split("/")
    assert segments[0] == "123456"
    assert len(segments[1]) == 10 and segments[1].count("-") == 2

    assert (
        WebDavUploader(_config(get_webdav_remote_dir=lambda: ""))._remote_dir("1") == ""
    )
    assert (
        WebDavUploader(_config(get_webdav_remote_dir=lambda: "../坏:名"))._remote_dir(
            "1"
        )
        == "坏名"
    )


def test_public_url_requires_configured_prefix():
    """测试未配置公网前缀时只上传不产出链接"""
    plain = WebDavUploader(_config())
    assert plain._build_public_url("a/b.html") == ""

    with_prefix = WebDavUploader(
        _config(get_webdav_public_base_url=lambda: "https://cdn.example.com/")
    )
    assert (
        with_prefix._build_public_url("a/报告 x.html")
        == "https://cdn.example.com/a/%E6%8A%A5%E5%91%8A%20x.html"
    )


def test_upload_file_creates_collections_and_puts_content(fake_http, tmp_path):
    """测试上传前逐级创建目录，并 PUT 文件内容"""
    html_file = tmp_path / "report.html"
    html_file.write_bytes(b"<html>ok</html>")

    async def scenario():
        uploader = WebDavUploader(_config())
        result = await uploader.upload_file(
            str(html_file), group_id="123456", kind=KIND_HTML
        )

        assert result == ""
        client = fake_http.instances[0]
        assert client.mkcols == [
            "https://dav.example.com/reports/123456",
            client.mkcols[1],
        ]
        assert client.mkcols[1].startswith("https://dav.example.com/reports/123456/")

        url, content = client.puts[0]
        assert url.endswith("/report.html")
        assert content == b"<html>ok</html>"

    asyncio.run(scenario())


def test_upload_file_returns_public_url_when_prefix_configured(fake_http, tmp_path):
    """测试配置公网前缀后返回可点击链接"""
    html_file = tmp_path / "report.html"
    html_file.write_text("<html></html>", encoding="utf-8")

    async def scenario():
        uploader = WebDavUploader(
            _config(get_webdav_public_base_url=lambda: "https://cdn.example.com")
        )
        result = await uploader.upload_file(str(html_file), group_id="123456")

        assert result.startswith("https://cdn.example.com/123456/")
        assert result.endswith("/report.html")

    asyncio.run(scenario())


def test_upload_degrades_silently_on_put_failure(fake_http, tmp_path):
    """测试 PUT 失败时返回空字符串且不抛出异常"""
    fake_http.put_status = 500
    html_file = tmp_path / "report.html"
    html_file.write_text("<html></html>", encoding="utf-8")

    async def scenario():
        uploader = WebDavUploader(
            _config(get_webdav_public_base_url=lambda: "https://cdn.example.com")
        )
        assert await uploader.upload_file(str(html_file), group_id="1") == ""

    asyncio.run(scenario())


def test_upload_skips_when_disabled(fake_http, tmp_path):
    """测试未启用时直接返回且不发起任何请求"""
    html_file = tmp_path / "report.html"
    html_file.write_text("<html></html>", encoding="utf-8")

    async def scenario():
        uploader = WebDavUploader(_config(get_enable_webdav_upload=lambda: False))
        assert await uploader.upload_file(str(html_file), group_id="1") == ""
        assert fake_http.instances == []

    asyncio.run(scenario())


def test_upload_image_decodes_base64_and_cleans_temp_file(fake_http):
    """测试 base64 图片被解码上传，且临时文件会被清理"""
    payload = b"\x89PNG\r\n\x1a\npayload"
    image_ref = "base64://" + base64.b64encode(payload).decode()
    captured: dict[str, str] = {}

    async def scenario():
        uploader = WebDavUploader(_config())
        await uploader.upload_image(image_ref, group_id="123456")

        client = fake_http.instances[0]
        url, content = client.puts[0]
        assert content == payload
        captured["temp_path"] = url

    asyncio.run(scenario())

    temp_dir = str(Path(os.environ.get("TEMP", "/tmp")))
    leftovers = [
        n for n in os.listdir(temp_dir) if n.startswith("webdav_report_123456")
    ]
    assert leftovers == []
    assert captured["temp_path"]


def test_upload_image_passes_through_local_path(fake_http, tmp_path):
    """测试本地图片路径被直接读取上传，不被删除"""

    image_file = tmp_path / "report.png"
    image_file.write_bytes(b"png-bytes")

    async def scenario():
        uploader = WebDavUploader(_config())
        await uploader.upload_image(str(image_file), group_id="1")

        _, content = fake_http.instances[0].puts[0]
        assert content == b"png-bytes"

    asyncio.run(scenario())
    assert image_file.exists()


def test_upload_returns_empty_for_unknown_image_reference(fake_http):
    """测试无法识别的图片引用被安全跳过"""

    async def scenario():
        uploader = WebDavUploader(_config())
        assert await uploader.upload_image("not-a-real-ref", group_id="1") == ""
        assert fake_http.instances == []

    asyncio.run(scenario())
