"""WebDAV 报告上传。

把生成的报告产物（图片报告、HTML 报告、每日群漫画）上传到用户自建的
WebDAV 服务器（坚果云、Nextcloud、群晖、Alist 等），便于长期归档与自建外链；
同时提供配置备份文件的上传、列表与下载能力，供备份中心的 WebDAV 通道使用。

设计约定：

* 与本地上传（群文件/群相册）相互独立，可同时开启，且不受平台限制；
* 失败只记录日志并返回空字符串，绝不影响报告本身的发送；
* 远程目录与文件名支持 ``${group_id}`` / ``${date}`` / ``${trace_id}`` / ``${ulid}`` 变量；
* 配置备份固定存放在 ``config_backups/`` 目录，与报告归档目录互不干扰。
"""

from __future__ import annotations

import base64
import mimetypes
import os
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote, unquote

from ...utils.logger import logger
from ...utils.template_utils import render_template
from ...utils.time_utils import format_local_date, format_local_pattern

if TYPE_CHECKING:
    import httpx

    from ..config.config_manager import ConfigManager

KIND_IMAGE = "image"
"""图片报告。"""

KIND_HTML = "html"
"""HTML 报告。"""

KIND_COMIC = "comic"
"""每日群漫画。"""

BACKUP_REMOTE_DIR = "config_backups"
"""配置备份文件在 WebDAV 上的固定存放目录。"""

BACKUP_CONTENT_TYPE = "application/json"
"""配置备份文件的 Content-Type。"""

_MAX_IMAGE_PAYLOAD_BYTES = 20 * 1024 * 1024
"""单个 base64 图片载荷的大小上限，避免超大内容撑爆内存。"""

_MKCOL_ACCEPTED_STATUS = frozenset({200, 201, 204, 301, 405})
"""创建目录时可接受的状态码，405 表示目录已存在。"""

_PUT_ACCEPTED_STATUS = frozenset({200, 201, 204})


class WebDavUploader:
    """把报告产物上传到 WebDAV 服务器。

    Attributes:
        config_manager: 配置管理器，用于读取 WebDAV 相关配置。
    """

    config_manager: ConfigManager

    def __init__(self, config_manager: ConfigManager) -> None:
        """初始化上传器。

        Args:
            config_manager: 配置管理器。
        """
        self.config_manager = config_manager

    def is_enabled(self, kind: str) -> bool:
        """判断指定类型的内容是否需要上传。

        Args:
            kind: 内容类型，取值为 ``image`` / ``html`` / ``comic``。

        Returns:
            bool: 总开关与对应类型开关均已开启、且 WebDAV 地址非空时返回 True。
        """
        if not self.config_manager.get_enable_webdav_upload():
            return False
        if not self._base_url():
            return False
        if kind == KIND_IMAGE:
            return self.config_manager.get_webdav_upload_image()
        if kind == KIND_HTML:
            return self.config_manager.get_webdav_upload_html()
        if kind == KIND_COMIC:
            return self.config_manager.get_webdav_upload_comic()
        return False

    async def upload_image(
        self,
        image_ref: str,
        *,
        group_id: str,
        kind: str = KIND_IMAGE,
        filename: str = "",
    ) -> str:
        """上传图片报告或群漫画。

        Args:
            image_ref: 图片引用，支持公网 URL 之外的本地路径、``base64://`` 与 ``data:`` 形式。
            group_id: 来源群号，用于渲染远程目录。
            kind: 内容类型，决定使用哪种上传开关。
            filename: 指定的文件名；留空时自动按群号与时间生成。

        Returns:
            str: 上传成功时的公网访问链接；未配置公网前缀、未启用或失败时返回空字符串。
        """
        if not self.is_enabled(kind):
            return ""

        local_path, is_temp = self._materialize_image(image_ref, group_id)
        if not local_path:
            return ""

        try:
            return await self._upload(
                local_path,
                group_id=group_id,
                filename=filename or Path(local_path).name,
            )
        finally:
            if is_temp:
                try:
                    os.remove(local_path)
                except OSError:
                    pass

    async def upload_file(
        self,
        local_path: str,
        *,
        group_id: str,
        kind: str = KIND_HTML,
        filename: str = "",
    ) -> str:
        """上传本地文件（如 HTML 报告）。

        Args:
            local_path: 本地文件路径。
            group_id: 来源群号，用于渲染远程目录。
            kind: 内容类型，决定使用哪种上传开关。
            filename: 指定的远程文件名；留空时使用源文件名。

        Returns:
            str: 上传成功时的公网访问链接；未配置公网前缀、未启用或失败时返回空字符串。
        """
        if not self.is_enabled(kind):
            return ""

        if not local_path or not os.path.isfile(local_path):
            logger.warning(f"[WebDAV] 待上传文件不存在，已跳过：{local_path!r}")
            return ""

        return await self._upload(
            local_path,
            group_id=group_id,
            filename=filename or Path(local_path).name,
        )

    # ==================== 配置备份通道 ====================

    def is_available(self) -> bool:
        """判断 WebDAV 通道是否可用于配置备份。

        配置备份只要求填写了 WebDAV 地址，不依赖报告上传的各类型开关。

        Returns:
            bool: WebDAV 地址非空时返回 True。
        """
        return bool(self._base_url())

    async def upload_backup_data(self, filename: str, content: bytes) -> str:
        """上传配置备份文件到固定目录。

        Args:
            filename: 备份文件名（如 ``config_backup_20260928_140000.json``）。
            content: 备份 JSON 的字节内容。

        Returns:
            str: 相对 WebDAV 根地址的远程路径；失败时返回空字符串。
        """
        import httpx

        base_url = self._base_url()
        if not base_url:
            logger.warning("[WebDAV] 未配置 WebDAV 地址，无法上传配置备份。")
            return ""

        safe_name = self._sanitize_component(filename)
        if not safe_name.endswith(".json"):
            safe_name = f"{safe_name}.json"
        remote_key = f"{BACKUP_REMOTE_DIR}/{safe_name}"
        remote_dir = BACKUP_REMOTE_DIR
        timeout = self.config_manager.get_webdav_timeout()
        proxy = self.config_manager.get_webdav_proxy().strip() or None

        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                verify=self.config_manager.get_webdav_verify_ssl(),
                proxy=proxy,
                auth=self._build_auth(),
            ) as client:
                if not await self._ensure_collections(client, base_url, remote_dir):
                    return ""
                response = await client.put(
                    f"{base_url}/{quote(remote_key, safe='/')}",
                    content=content,
                    headers={"Content-Type": BACKUP_CONTENT_TYPE},
                )
                if response.status_code not in _PUT_ACCEPTED_STATUS:
                    logger.warning(
                        f"[WebDAV] 配置备份上传失败（HTTP {response.status_code}）：{safe_name}"
                    )
                    return ""
        except Exception as e:
            logger.warning(f"[WebDAV] 配置备份上传异常：{e}")
            return ""

        logger.info(f"[WebDAV] 配置备份上传成功：{remote_key}")
        return remote_key

    async def list_backups(self) -> list[dict[str, object]]:
        """列出远程备份目录中的备份文件。

        Returns:
            list[dict[str, object]]: 每项包含 ``name`` / ``size`` / ``modified``；
            未配置或请求失败时返回空列表。
        """
        import httpx

        base_url = self._base_url()
        if not base_url:
            return []

        timeout = self.config_manager.get_webdav_timeout()
        proxy = self.config_manager.get_webdav_proxy().strip() or None
        url = f"{base_url}/{quote(BACKUP_REMOTE_DIR, safe='/')}/"

        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                verify=self.config_manager.get_webdav_verify_ssl(),
                proxy=proxy,
                auth=self._build_auth(),
            ) as client:
                response = await client.request(
                    "PROPFIND",
                    url,
                    headers={"Depth": "1"},
                )
                if response.status_code not in frozenset({207, 200}):
                    logger.warning(
                        f"[WebDAV] 列举配置备份失败（HTTP {response.status_code}）。"
                    )
                    return []
        except Exception as e:
            logger.warning(f"[WebDAV] 列举配置备份异常：{e}")
            return []

        return self._parse_propfind(response.text)

    async def download_backup(self, filename: str) -> bytes | None:
        """从远程备份目录下载指定备份文件。

        Args:
            filename: 备份文件名（不含目录）。

        Returns:
            bytes | None: 文件内容；失败时返回 None。
        """
        import httpx

        base_url = self._base_url()
        if not base_url:
            return None

        safe_name = self._sanitize_component(filename)
        if not safe_name:
            logger.warning("[WebDAV] 备份文件名非法，已取消下载。")
            return None
        remote_key = f"{BACKUP_REMOTE_DIR}/{safe_name}"
        timeout = self.config_manager.get_webdav_timeout()
        proxy = self.config_manager.get_webdav_proxy().strip() or None

        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                verify=self.config_manager.get_webdav_verify_ssl(),
                proxy=proxy,
                auth=self._build_auth(),
            ) as client:
                response = await client.get(f"{base_url}/{quote(remote_key, safe='/')}")
                if response.status_code != 200:
                    logger.warning(
                        f"[WebDAV] 下载配置备份失败（HTTP {response.status_code}）：{safe_name}"
                    )
                    return None
                return response.content
        except Exception as e:
            logger.warning(f"[WebDAV] 下载配置备份异常：{e}")
            return None

    @staticmethod
    def _parse_propfind(xml_text: str) -> list[dict[str, object]]:
        """解析 PROPFIND 响应，提取备份文件清单。

        Args:
            xml_text: WebDAV 服务器返回的 multistatus XML 文本。

        Returns:
            list[dict[str, object]]: 每项包含 ``name`` / ``size`` / ``modified``；
            目录条目与解析失败时被跳过的条目不会出现。
        """
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.warning(f"[WebDAV] 解析备份清单 XML 失败：{e}")
            return []

        results: list[dict[str, object]] = []
        # 命名空间在不同服务器上不一致，按本地名匹配即可
        for response_node in root.iter():
            if not response_node.tag.endswith("}response"):
                continue

            href = ""
            size = 0
            modified = ""
            is_collection = False
            for node in response_node.iter():
                tag = node.tag.rsplit("}", 1)[-1]
                if tag == "href":
                    href = unquote((node.text or "").strip())
                elif tag == "getcontentlength":
                    try:
                        size = int(node.text or "0")
                    except ValueError:
                        size = 0
                elif tag == "getlastmodified":
                    modified = (node.text or "").strip()
                elif tag == "collection":
                    is_collection = True

            filename = href.rstrip("/").rsplit("/", 1)[-1]
            if not filename or is_collection or not filename.endswith(".json"):
                continue
            results.append({"name": filename, "size": size, "modified": modified})

        return sorted(results, key=lambda item: str(item["name"]), reverse=True)

    # ==================== 内部实现 ====================

    def _base_url(self) -> str:
        """获取 WebDAV 根地址（已去除尾部斜杠）。"""
        return self.config_manager.get_webdav_url().strip().rstrip("/")

    def _remote_dir(self, group_id: str) -> str:
        """渲染并净化远程子目录。

        Args:
            group_id: 来源群号。

        Returns:
            str: 以 ``/`` 分隔的相对目录，首尾无斜杠；未配置时返回空字符串。
        """
        template = self.config_manager.get_webdav_remote_dir().strip()
        if not template:
            return ""
        rendered = render_template(
            template,
            group_id=group_id,
            date=format_local_date(),
            trace_id=str(self._current_trace_id()),
            ulid=self._new_ulid(),
        )
        segments = [self._sanitize_component(part) for part in rendered.split("/")]
        return "/".join(part for part in segments if part)

    def _materialize_image(self, image_ref: str, group_id: str) -> tuple[str, bool]:
        """把图片引用统一落成磁盘文件。

        Args:
            image_ref: 图片引用。
            group_id: 来源群号，用于生成临时文件名。

        Returns:
            tuple[str, bool]: (本地路径, 是否为需要清理的临时文件)。无法处理时路径为空字符串。
        """
        ref = image_ref.strip()
        if not ref:
            return "", False

        if os.path.isfile(ref):
            return os.path.abspath(ref), False

        if ref.startswith("file:///"):
            candidate = ref[len("file:///") :]
            if os.path.isfile(candidate):
                return os.path.abspath(candidate), False

        payload: bytes | None = None
        if ref.startswith("base64://"):
            encoded = ref[len("base64://") :]
            if len(encoded) * 3 / 4 > _MAX_IMAGE_PAYLOAD_BYTES:
                logger.warning("[WebDAV] 图片载荷超过上限，已跳过上传。")
                return "", False
            payload = self._decode_base64(encoded)
        elif ref.startswith("data:") and "," in ref:
            encoded = ref.split(",", 1)[1]
            if len(encoded) * 3 / 4 > _MAX_IMAGE_PAYLOAD_BYTES:
                logger.warning("[WebDAV] 图片载荷超过上限，已跳过上传。")
                return "", False
            payload = self._decode_base64(encoded)

        if payload is None:
            logger.warning("[WebDAV] 无法识别的图片引用，已跳过上传。")
            return "", False

        suffix = ".jpg" if (".jpg" in ref.lower() or ".jpeg" in ref.lower()) else ".png"
        timestamp = format_local_pattern("%Y%m%d_%H%M%S")
        path = os.path.join(
            tempfile.gettempdir(),
            f"webdav_report_{group_id}_{timestamp}{suffix}",
        )
        try:
            with open(path, "wb") as handle:
                handle.write(payload)
        except OSError as e:
            logger.warning(f"[WebDAV] 写入临时图片失败：{e}")
            return "", False
        return path, True

    @staticmethod
    def _decode_base64(encoded: str) -> bytes | None:
        """解码 base64 字符串，失败返回 None。"""
        try:
            return base64.b64decode(encoded)
        except Exception:
            return None

    @staticmethod
    def _sanitize_component(component: str) -> str:
        """净化单个路径片段，剔除路径穿越与非法字符。"""
        cleaned = component.strip().strip(".")
        for char in '\\:*?"<>|':
            cleaned = cleaned.replace(char, "")
        return cleaned

    def _new_ulid(self) -> str:
        """生成用于文件名的随机排序 ID，失败时回退为时间戳。"""
        try:
            import ulid

            return str(ulid.new())
        except Exception:
            return datetime.now().strftime("%f")

    @staticmethod
    def _current_trace_id() -> str:
        """获取当前链路 ID，无链路上下文时返回空字符串。"""
        from ...shared.trace_context import TraceContext

        return str(TraceContext.get() or "")

    async def _upload(self, local_path: str, *, group_id: str, filename: str) -> str:
        """执行一次 WebDAV 上传。

        Args:
            local_path: 本地文件路径。
            group_id: 来源群号。
            filename: 远程文件名。

        Returns:
            str: 公网链接；上传失败或未配置公网前缀时返回空字符串。
        """
        import httpx

        base_url = self._base_url()
        remote_dir = self._remote_dir(group_id)
        safe_name = self._sanitize_component(filename) or Path(local_path).name
        remote_key = f"{remote_dir}/{safe_name}" if remote_dir else safe_name

        try:
            content = Path(local_path).read_bytes()
        except OSError as e:
            logger.warning(f"[WebDAV] 读取待上传文件失败：{e}")
            return ""

        headers = {
            "Content-Type": mimetypes.guess_type(safe_name)[0]
            or "application/octet-stream"
        }
        timeout = self.config_manager.get_webdav_timeout()
        proxy = self.config_manager.get_webdav_proxy().strip() or None

        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                verify=self.config_manager.get_webdav_verify_ssl(),
                proxy=proxy,
                auth=self._build_auth(),
            ) as client:
                if not await self._ensure_collections(client, base_url, remote_dir):
                    return ""
                response = await client.put(
                    f"{base_url}/{quote(remote_key, safe='/')}",
                    content=content,
                    headers=headers,
                )
                if response.status_code not in _PUT_ACCEPTED_STATUS:
                    logger.warning(
                        f"[WebDAV] 上传失败（HTTP {response.status_code}）：{filename}"
                    )
                    return ""
        except Exception as e:
            logger.warning(f"[WebDAV] 上传异常：{e}")
            return ""

        logger.info(f"[WebDAV] 上传成功：{remote_key}")
        return self._build_public_url(remote_key)

    def _build_auth(self) -> httpx.BasicAuth | None:
        """构造 Basic 认证对象，未配置用户名时返回 None。"""
        import httpx

        username = self.config_manager.get_webdav_username().strip()
        if not username:
            return None
        return httpx.BasicAuth(username, self.config_manager.get_webdav_password())

    async def _ensure_collections(
        self, client: httpx.AsyncClient, base_url: str, remote_dir: str
    ) -> bool:
        """逐级创建远程目录（已存在时视为成功）。

        Args:
            client: 已构造的 HTTP 客户端（认证信息已挂在客户端上）。
            base_url: WebDAV 根地址。
            remote_dir: 相对目录，以 ``/`` 分隔。

        Returns:
            bool: 目录就绪返回 True，创建失败返回 False。
        """
        accumulated = ""
        for segment in remote_dir.split("/"):
            if not segment:
                continue
            accumulated = f"{accumulated}/{segment}" if accumulated else segment
            url = f"{base_url}/{quote(accumulated, safe='/')}"
            try:
                response = await client.request("MKCOL", url)
            except Exception as e:
                logger.warning(f"[WebDAV] 创建目录 {accumulated} 异常：{e}")
                return False
            if response.status_code not in _MKCOL_ACCEPTED_STATUS:
                logger.warning(
                    f"[WebDAV] 创建目录 {accumulated} 失败"
                    f"（HTTP {response.status_code}），已跳过本次上传。"
                )
                return False
        return True

    def _build_public_url(self, remote_key: str) -> str:
        """按公网前缀构造可访问链接。

        Args:
            remote_key: 相对 WebDAV 根地址的路径。

        Returns:
            str: 公网链接；未配置前缀时返回空字符串。
        """
        public_base = self.config_manager.get_webdav_public_base_url().strip()
        if not public_base:
            return ""
        return f"{public_base.rstrip('/')}/{quote(remote_key, safe='/')}"
