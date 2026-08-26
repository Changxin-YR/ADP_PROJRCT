from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from openpyxl import Workbook
from PIL import Image

from backend.layers.common.files.attachments import AttachmentError, prepare_attachment


def _png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (2, 2), "white").save(output, format="PNG")
    return output.getvalue()


def _xlsx_bytes() -> bytes:
    output = BytesIO()
    workbook = Workbook()
    workbook.active.append(["凭证编号", "金额"])
    workbook.active.append(["TEST-001", 12.34])
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def test_valid_image_and_workbook_pass_deep_validation() -> None:
    png = _png_bytes()
    workbook = _xlsx_bytes()

    assert prepare_attachment(
        original_name="现场.png", media_type="image/png", content=png
    ).size_bytes == len(png)
    assert prepare_attachment(
        original_name="台账.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        content=workbook,
    ).size_bytes == len(workbook)


def test_image_with_only_a_valid_magic_header_is_rejected() -> None:
    with pytest.raises(AttachmentError, match="图片文件损坏"):
        prepare_attachment(
            original_name="损坏.png",
            media_type="image/png",
            content=b"\x89PNG\r\n\x1a\nnot-a-real-image",
        )


@pytest.mark.parametrize(
    "content, message",
    [
        (b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n", "PDF 文件不完整"),
        (
            b"%PDF-1.4\n1 0 obj\n<< /OpenAction 2 0 R >>\nendobj\n%%EOF\n",
            "PDF 包含不安全的活动内容",
        ),
    ],
)
def test_incomplete_or_active_pdf_is_rejected(content: bytes, message: str) -> None:
    with pytest.raises(AttachmentError, match=message):
        prepare_attachment(
            original_name="凭证.pdf", media_type="application/pdf", content=content
        )


def test_ooxml_path_traversal_member_is_rejected() -> None:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("_rels/.rels", "<Relationships/>")
        archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr("../payload.exe", b"payload")

    with pytest.raises(AttachmentError, match="非法路径"):
        prepare_attachment(
            original_name="恶意.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            content=output.getvalue(),
        )


def test_ooxml_extreme_compression_ratio_is_rejected() -> None:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("_rels/.rels", "<Relationships/>")
        archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr("xl/worksheets/sheet1.xml", b"0" * (1024 * 1024))

    with pytest.raises(AttachmentError, match="压缩比异常"):
        prepare_attachment(
            original_name="压缩炸弹.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            content=output.getvalue(),
        )
