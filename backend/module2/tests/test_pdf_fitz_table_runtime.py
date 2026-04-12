from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.core.parsers.native_document_parser import NativeDocumentParser


class _FakeFitzTable:
    def __init__(
        self,
        matrix: list[list[str]],
        bbox: tuple[float, float, float, float] = (0.0, 0.0, 100.0, 100.0),
    ) -> None:
        self._matrix = matrix
        self.bbox = bbox

    def extract(self) -> list[list[str]]:
        return self._matrix


class _FakeFitzFinder:
    def __init__(self, tables: list[_FakeFitzTable]) -> None:
        self.tables = tables


class _FakeFitzPage:
    def __init__(self, tables: list[_FakeFitzTable], text: str = "") -> None:
        self._tables = tables
        self._text = text
        self.rect = SimpleNamespace(width=100.0, height=100.0)

    def find_tables(self) -> _FakeFitzFinder:
        return _FakeFitzFinder(self._tables)

    def get_text(self, mode: str = "text") -> str:
        assert mode == "text"
        return self._text


class _FakeFitzDoc:
    def __init__(self, pages: list[_FakeFitzPage]) -> None:
        self._pages = pages

    def __len__(self) -> int:
        return len(self._pages)

    def load_page(self, index: int) -> _FakeFitzPage:
        return self._pages[index]

    def close(self) -> None:
        return None


def _build_parser() -> NativeDocumentParser:
    return NativeDocumentParser(max_pages=1)


def _extract_tables_from_fake_doc(pages: list[_FakeFitzPage]) -> list[dict[str, object]]:
    parser = _build_parser()
    fake_doc = _FakeFitzDoc(pages)
    original_fitz = sys.modules.get("fitz")
    sys.modules["fitz"] = SimpleNamespace(open=lambda stream, filetype: fake_doc)
    try:
        return parser._pdf_fitz_table_runtime.extract_pdf_tables_with_fitz(
            b"%PDF-1.7",
            page_count=len(pages),
            parts=[],
            bbox_map={},
        )
    finally:
        if original_fitz is None:
            sys.modules.pop("fitz", None)
        else:
            sys.modules["fitz"] = original_fitz


def _extract_tables_from_fake_pdf(matrix: list[list[str]]) -> list[dict[str, object]]:
    return _extract_tables_from_fake_doc([_FakeFitzPage([_FakeFitzTable(matrix)])])


def test_pdf_fitz_runtime_recovers_data_like_numeric_headers() -> None:
    tables = _extract_tables_from_fake_pdf(
        [
            ["\u98df\u54c1\u70df\u9152", "10482", "2.9"],
            ["\u8863\u7740", "2642", "1.6"],
            ["\u5c45\u4f4f", "5581", "0.8"],
        ]
    )

    assert len(tables) == 1
    assert tables[0]["headers"] == ["\u7c7b\u522b", "\u6570\u503c_1", "\u6570\u503c_2"]
    assert tables[0]["rows"][0]["cells"][0]["text"] == "\u98df\u54c1\u70df\u9152"
    assert tables[0]["rows"][1]["cells"][0]["text"] == "\u8863\u7740"


def test_pdf_fitz_runtime_promotes_temporal_header_row_after_caption_row() -> None:
    tables = _extract_tables_from_fake_pdf(
        [
            ["\u8868 1 2021 \u5e74\u5c45\u6c11\u6d88\u8d39\u548c\u5546\u54c1\u96f6\u552e\u4ef7\u683c\u6da8\u8dcc\u5e45\u5ea6\uff08\u5355\u4f4d\uff1a%\uff09", "", ""],
            ["\u6307\u6807\u540d\u79f0", "2020 \u5e74", "2021 \u5e74"],
            ["\u5c45\u6c11\u6d88\u8d39\u4ef7\u683c", "2.4", "1.7"],
        ]
    )

    assert len(tables) == 1
    assert tables[0]["headers"] == ["\u6307\u6807\u540d\u79f0", "2020 \u5e74", "2021 \u5e74"]
    assert len(tables[0]["rows"]) == 1
    assert tables[0]["rows"][0]["cells"][0]["header"] == "\u6307\u6807\u540d\u79f0"


def test_pdf_fitz_runtime_recovers_continuation_headers_from_previous_page_text() -> None:
    tables = _extract_tables_from_fake_doc(
        [
            _FakeFitzPage(
                [],
                text="\n".join(
                    [
                        "十一、人民生活和社会保障",
                        "表9 居民人均消费支出构成情况",
                        "指标",
                        "绝对值（元）",
                        "比上年增长（%）",
                        "居民人均消费支出",
                        "40313",
                        "3.1",
                    ]
                ),
            ),
            _FakeFitzPage(
                [
                    _FakeFitzTable(
                        [
                            ["食品烟酒", "10482", "2.9"],
                            ["衣着", "2642", "1.6"],
                            ["居住", "9300", "6.0"],
                        ],
                        bbox=(10.0, 5.0, 90.0, 30.0),
                    )
                ]
            ),
        ]
    )

    assert len(tables) == 1
    assert tables[0]["headers"] == ["指标", "绝对值（元）", "比上年增长（%）"]
    assert tables[0]["caption"] == "表9 居民人均消费支出构成情况"
    assert tables[0]["rows"][0]["cells"][0]["header"] == "指标"
