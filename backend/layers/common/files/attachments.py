from __future__ import annotations

import hashlib
import warnings
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from pathlib import PurePosixPath
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from PIL import Image, UnidentifiedImageError


ALLOWED_MEDIA_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/jpeg",
    "image/png",
}
ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".jpg", ".jpeg", ".png"}
_MEDIA_EXTENSIONS = {
    "application/pdf": {".pdf"},
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {".xlsx"},
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
}
_MAGIC_SIGNATURES = {
    "application/pdf": (b"%PDF-",),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": (b"PK\x03\x04",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
}
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_OOXML_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_OOXML_COMPRESSION_RATIO = 100
_OOXML_REQUIRED_MEMBERS = {
    "[Content_Types].xml",
    "_rels/.rels",
    "xl/workbook.xml",
}
_PDF_ACTIVE_MARKERS = (
    b"/javascript",
    b"/js",
    b"/openaction",
    b"/aa",
    b"/launch",
    b"/richmedia",
)


class AttachmentError(ValueError):
    pass


@dataclass(frozen=True)
class AttachmentMetadata:
    storage_name: str
    original_name: str
    media_type: str
    size_bytes: int
    sha256: str


def _client_basename(value: str) -> str:
    name = Path(value.replace("\\", "/")).name.strip()
    if not name or any(ord(character) < 32 for character in name):
        raise AttachmentError("附件文件名无效")
    return name[:255]


def _validate_image(content: bytes) -> None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                width, height = image.size
                if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                    raise AttachmentError("图片像素尺寸超出安全限制")
                image.verify()
    except AttachmentError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise AttachmentError("图片像素尺寸超出安全限制") from None
    except (OSError, SyntaxError, UnidentifiedImageError, ValueError):
        raise AttachmentError("图片文件损坏或格式无效") from None


def _validate_pdf(content: bytes) -> None:
    if not content.rstrip().endswith(b"%%EOF"):
        raise AttachmentError("PDF 文件不完整")
    lowered = content.lower()
    if any(marker in lowered for marker in _PDF_ACTIVE_MARKERS):
        raise AttachmentError("PDF 包含不安全的活动内容")


def _validate_ooxml(content: bytes) -> None:
    try:
        with ZipFile(BytesIO(content)) as archive:
            members = archive.infolist()
            names = {member.filename for member in members}
            if not _OOXML_REQUIRED_MEMBERS.issubset(names):
                raise AttachmentError("Excel 文件结构不完整")

            total_uncompressed = 0
            for member in members:
                name = member.filename.replace("\\", "/")
                path = PurePosixPath(name)
                if path.is_absolute() or ".." in path.parts:
                    raise AttachmentError("Excel 压缩包包含非法路径")
                if member.flag_bits & 0x1:
                    raise AttachmentError("不支持加密的 Excel 文件")

                total_uncompressed += member.file_size
                if total_uncompressed > MAX_OOXML_UNCOMPRESSED_BYTES:
                    raise AttachmentError("Excel 解压后大小超出安全限制")
                if member.file_size:
                    if not member.compress_size:
                        raise AttachmentError("Excel 压缩比异常")
                    if member.file_size / member.compress_size > MAX_OOXML_COMPRESSION_RATIO:
                        raise AttachmentError("Excel 压缩比异常")

        workbook = load_workbook(BytesIO(content), read_only=True, data_only=False)
        workbook.close()
    except AttachmentError:
        raise
    except (BadZipFile, InvalidFileException, KeyError, OSError, ValueError, TypeError):
        raise AttachmentError("Excel 文件损坏或格式无效") from None


def _validate_content(media_type: str, content: bytes) -> None:
    if media_type in {"image/jpeg", "image/png"}:
        _validate_image(content)
    elif media_type == "application/pdf":
        _validate_pdf(content)
    elif media_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        _validate_ooxml(content)


def prepare_attachment(
    *, original_name: str, media_type: str, content: bytes
) -> AttachmentMetadata:
    if media_type not in ALLOWED_MEDIA_TYPES:
        raise AttachmentError("不支持的附件类型")
    if not content or len(content) > MAX_ATTACHMENT_BYTES:
        raise AttachmentError("附件大小必须在 1 字节到 20 MB 之间")
    safe_name = _client_basename(original_name)
    extension = Path(safe_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise AttachmentError("不支持的附件扩展名")
    if extension not in _MEDIA_EXTENSIONS[media_type]:
        raise AttachmentError("附件扩展名与声明类型不一致")
    signatures = _MAGIC_SIGNATURES.get(media_type, ())
    if signatures and not any(content.startswith(signature) for signature in signatures):
        raise AttachmentError("附件内容与声明类型不一致")
    _validate_content(media_type, content)
    return AttachmentMetadata(
        storage_name=uuid4().hex,
        original_name=safe_name,
        media_type=media_type,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )


def save_private_file(root: Path, metadata: AttachmentMetadata, content: bytes) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    destination = root.resolve() / metadata.storage_name
    if destination.parent != root.resolve():
        raise AttachmentError("附件存储路径无效")
    destination.write_bytes(content)
    return destination
