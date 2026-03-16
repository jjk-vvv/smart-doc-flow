from __future__ import annotations

import sys
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile


MODULE4_DIR = Path(__file__).resolve().parents[1]
if str(MODULE4_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE4_DIR))

from app.services.input_normalizer import UploadInputNormalizer


def test_normalize_txt_upload_reads_real_file_content(tmp_path: Path) -> None:
    source = tmp_path / "report.txt"
    source.write_text("第一段文本\n\n第二段文本", encoding="utf-8")

    result = UploadInputNormalizer().normalize_uploads(
        [
            {
                "file_name": "report.txt",
                "file_hash": "hash-001",
                "artifact_path": str(source),
            }
        ]
    )

    assert len(result.normalized) == 1
    assert result.failed == []
    assert "第一段文本" in result.normalized[0].text_content
    assert "第二段文本" in result.normalized[0].text_content


def test_normalize_unsupported_legacy_office_file_fails_explicitly(tmp_path: Path) -> None:
    source = tmp_path / "legacy.doc"
    source.write_bytes(b"fake doc binary")

    result = UploadInputNormalizer().normalize_uploads(
        [
            {
                "file_name": "legacy.doc",
                "file_hash": "hash-legacy",
                "artifact_path": str(source),
            }
        ]
    )

    assert result.normalized == []
    assert len(result.failed) == 1
    assert "Unsupported legacy Office format" in result.failed[0].error


def test_normalize_docx_with_missing_footnotes_part_falls_back_to_xml(tmp_path: Path) -> None:
    from docx import Document

    source = tmp_path / "missing-footnotes.docx"
    document = Document()
    document.add_paragraph("Main body paragraph")
    document.save(source)

    with ZipFile(source, "r") as archive:
        files = {name: archive.read(name) for name in archive.namelist()}

    rels_name = "word/_rels/document.xml.rels"
    rels_root = ET.fromstring(files[rels_name])
    ET.SubElement(
        rels_root,
        "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship",
        {
            "Id": "rId999",
            "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes",
            "Target": "footnotes.xml",
        },
    )
    files[rels_name] = ET.tostring(rels_root, encoding="utf-8", xml_declaration=True)

    with ZipFile(source, "w", compression=ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)

    result = UploadInputNormalizer().normalize_uploads(
        [
            {
                "file_name": source.name,
                "file_hash": "hash-docx-footnote",
                "artifact_path": str(source),
            }
        ]
    )

    assert len(result.normalized) == 1
    assert result.failed == []
    assert "Main body paragraph" in result.normalized[0].text_content
