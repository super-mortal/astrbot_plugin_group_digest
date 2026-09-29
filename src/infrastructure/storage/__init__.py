"""存储类基础设施模块。

包含报告产物的远程归档能力（如 WebDAV 上传）。
"""

from .webdav_uploader import KIND_COMIC, KIND_HTML, KIND_IMAGE, WebDavUploader

__all__ = [
    "KIND_COMIC",
    "KIND_HTML",
    "KIND_IMAGE",
    "WebDavUploader",
]
