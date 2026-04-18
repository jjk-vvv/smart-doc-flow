from __future__ import annotations

import importlib.util
import io
import json
import sys
import zipfile
from pathlib import Path


def _load_module(path_parts: list[str], module_name: str):
    module_path = Path(__file__).resolve().parents[1]
    for part in path_parts:
        module_path = module_path / part
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


office_pdf_module = _load_module(
    ["app", "modules", "module2", "core", "format", "office_pdf.py"],
    "_smart_doc_flow_module2_office_pdf_runtime",
)


def _build_docx_bytes(*, media_count: int, drawing_count: int, section_count: int) -> bytes:
    document_xml = "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
    document_xml += "<w:body>"
    document_xml += "<w:p><w:r><w:t>sample</w:t></w:r></w:p>"
    document_xml += "<w:drawing/>" * drawing_count
    document_xml += "<w:sectPr/>" * section_count
    document_xml += "</w:body></w:document>"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("[Content_Types].xml", "<Types/>")
        for idx in range(media_count):
            zf.writestr(f"word/media/image{idx + 1}.png", b"fake")
        zf.writestr("word/footnotes.xml", "<footnotes/>")
        zf.writestr("word/endnotes.xml", "<endnotes/>")
    return buf.getvalue()


def test_word_pdf_backend_order_prefers_word_com_when_auto(monkeypatch) -> None:
    monkeypatch.delenv("MODULE2_WORD_TO_PDF_PREFERRED_BACKEND", raising=False)

    assert office_pdf_module._word_pdf_backend_order() == ("word_com", "libreoffice")


def test_doc_to_docx_backend_order_prefers_word_com_when_auto(monkeypatch) -> None:
    monkeypatch.delenv("MODULE2_DOC_TO_DOCX_PREFERRED_BACKEND", raising=False)
    monkeypatch.delenv("MODULE2_WORD_TO_PDF_PREFERRED_BACKEND", raising=False)

    assert office_pdf_module._doc_to_docx_backend_order() == ("word_com", "libreoffice")


def test_word_pdf_backend_order_supports_libreoffice_only(monkeypatch) -> None:
    monkeypatch.setenv("MODULE2_WORD_TO_PDF_PREFERRED_BACKEND", "libreoffice_only")

    assert office_pdf_module._word_pdf_backend_order() == ("libreoffice",)


def test_doc_to_docx_backend_order_supports_libreoffice_only(monkeypatch) -> None:
    monkeypatch.setenv("MODULE2_DOC_TO_DOCX_PREFERRED_BACKEND", "libreoffice_only")

    assert office_pdf_module._doc_to_docx_backend_order() == ("libreoffice",)


def test_load_cached_pdf_ignores_incompatible_word_com_cache(monkeypatch, tmp_path: Path) -> None:
    file_hash = "a" * 64
    pdf_path = tmp_path / "preview" / "op" / file_hash[:2] / f"{file_hash}.pdf"
    meta_path = pdf_path.with_suffix(".json")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.4\ncache\n")
    meta_path.write_text(
        json.dumps(
            {
                "converter": "word_com",
                "elapsed_ms": 17,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("MODULE2_WORD_TO_PDF_PREFERRED_BACKEND", "libreoffice_only")
    monkeypatch.setenv("MODULE2_ARTIFACT_ROOT_DIR", str(tmp_path))
    office_pdf_module._artifact_root_dir.cache_clear()
    try:
        assert office_pdf_module._load_cached_pdf(file_hash) is None
    finally:
        office_pdf_module._artifact_root_dir.cache_clear()


def test_convert_with_word_com_uses_isolated_process_before_warm_worker(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setenv("MODULE2_WORD_COM_ISOLATED_PROCESS_ENABLE", "true")
    monkeypatch.setenv("MODULE2_WORD_COM_WARM_WORKER_ENABLE", "true")
    monkeypatch.setattr(
        office_pdf_module,
        "_convert_with_word_com_isolated",
        lambda **kwargs: calls.append(("isolated", dict(kwargs))),
    )
    monkeypatch.setattr(
        office_pdf_module._WORD_COM_WARM_WORKER,
        "submit",
        lambda **kwargs: calls.append(("warm", dict(kwargs))),
    )
    monkeypatch.setattr(
        office_pdf_module,
        "_convert_with_word_com_direct",
        lambda **kwargs: calls.append(("direct", dict(kwargs))),
    )

    office_pdf_module._convert_with_word_com(
        input_path=Path("input.docx"),
        output_path=Path("output.pdf"),
        timeout_sec=120.0,
    )

    assert [kind for kind, _ in calls] == ["isolated"]
    assert calls[0][1]["operation"] == "pdf"


def test_convert_with_word_com_to_docx_uses_isolated_process_before_warm_worker(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setenv("MODULE2_WORD_COM_ISOLATED_PROCESS_ENABLE", "true")
    monkeypatch.setenv("MODULE2_WORD_COM_WARM_WORKER_ENABLE", "true")
    monkeypatch.setattr(
        office_pdf_module,
        "_convert_with_word_com_isolated",
        lambda **kwargs: calls.append(("isolated", dict(kwargs))),
    )
    monkeypatch.setattr(
        office_pdf_module._WORD_COM_WARM_WORKER,
        "submit",
        lambda **kwargs: calls.append(("warm", dict(kwargs))),
    )
    monkeypatch.setattr(
        office_pdf_module,
        "_convert_with_word_com_to_docx_direct",
        lambda **kwargs: calls.append(("direct", dict(kwargs))),
    )

    office_pdf_module._convert_with_word_com_to_docx(
        input_path=Path("input.doc"),
        output_path=Path("output.docx"),
        timeout_sec=120.0,
    )

    assert [kind for kind, _ in calls] == ["isolated"]
    assert calls[0][1]["operation"] == "docx"


def test_resolve_word_conversion_timeout_scales_for_complex_docx(monkeypatch) -> None:
    monkeypatch.setenv("MODULE2_WORD_COM_DYNAMIC_TIMEOUT_ENABLE", "true")
    monkeypatch.setenv("MODULE2_WORD_COM_TIMEOUT_COMPLEXITY_TRIGGER", "10")
    monkeypatch.setenv("MODULE2_WORD_COM_TIMEOUT_BONUS_PER_SCORE_SEC", "8")
    monkeypatch.setenv("MODULE2_WORD_COM_TIMEOUT_MAX_SEC", "720")

    resolved_timeout, meta = office_pdf_module._resolve_word_conversion_timeout(
        file_name="complex.docx",
        file_bytes=_build_docx_bytes(media_count=20, drawing_count=48, section_count=18),
        timeout_sec=240.0,
    )

    assert resolved_timeout > 240.0
    assert resolved_timeout <= 720.0
    assert meta["word_com_dynamic_timeout_applied"] is True
    assert meta["word_com_timeout_complexity_score"] >= 10
    assert meta["word_com_timeout_resolved_sec"] == round(resolved_timeout, 3)


def test_resolve_cache_lock_stale_sec_caps_to_timeout_budget(monkeypatch) -> None:
    monkeypatch.setenv("MODULE2_OFFICE_CACHE_LOCK_STALE_SEC", "600")

    resolved = office_pdf_module._resolve_cache_lock_stale_sec(180.0)

    # Keep enough recovery budget for conversion retry before this request times out.
    assert resolved < 180.0
    assert resolved >= 12.0


def test_lock_file_owner_inactive_uses_pid_probe(tmp_path: Path, monkeypatch) -> None:
    lock_path = tmp_path / "convert.lock"
    lock_path.write_text(
        json.dumps({"token": "t", "pid": 12345, "created_at": 0}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(office_pdf_module, "_is_process_alive", lambda _pid: False)

    assert office_pdf_module._lock_file_owner_inactive(lock_path) is True

    monkeypatch.setattr(office_pdf_module, "_is_process_alive", lambda _pid: True)
    assert office_pdf_module._lock_file_owner_inactive(lock_path) is False
