from app.modules.module3.services.source_dispatcher import (
    _extract_case_count_from_doc_text,
    _normalize_word_rows_for_structured_metrics,
)


def test_extract_case_count_from_doc_text_handles_case_qualifier_pattern() -> None:
    doc_text = (
        "\u4e2d\u56fd\u6e56\u5317\u7701 2020-08-01 \u65b0\u589e4\u4f8b\u672c\u571f\u786e\u8bca\u75c5\u4f8b\uff0c"
        "\u65b0\u589e1\u4f8b\u5883\u5916\u8f93\u5165\u75c5\u4f8b\u3002"
    )

    assert _extract_case_count_from_doc_text(doc_text, "\u6e56\u5317\u7701") == "4"


def test_extract_case_count_from_doc_text_does_not_bleed_into_next_paragraph() -> None:
    doc_text = (
        "\u5e7f\u897f\u58ee\u65cf\u81ea\u6cbb\u533a\u4eba\u53e3 5013 \u4e07\uff0c7 \u6708 27 \u65e5\u96f6\u65b0\u589e\u786e\u8bca\u75c5\u4f8b\uff0c"
        "\u68c0\u6d4b\u91cf\u7ea6 11.6 \u4e07\u4efd\u3002\n"
        "\u4e91\u5357\u7701\u4eba\u53e3 4721 \u4e07\uff0c7 \u6708 27 \u65e5\u62a5\u544a 1 \u4f8b\u5883\u5916\u8f93\u5165\u786e\u8bca\u75c5\u4f8b\uff0c"
        "\u5f53\u65e5\u6838\u9178\u68c0\u6d4b\u91cf\u7ea6 13.4 \u4e07\u4efd\u3002"
    )

    assert _extract_case_count_from_doc_text(doc_text, "\u5e7f\u897f\u58ee\u65cf\u81ea\u6cbb\u533a") == ""
    assert _extract_case_count_from_doc_text(doc_text, "\u4e91\u5357\u7701") == "1"


def test_normalize_word_rows_keeps_explicit_zero_case_counts() -> None:
    headers = [
        "\u56fd\u5bb6/\u5730\u533a",
        "\u5927\u6d32",
        "\u4eba\u5747GDP",
        "\u4eba\u53e3",
        "\u6bcf\u65e5\u68c0\u6d4b\u6570",
        "\u75c5\u4f8b\u6570",
    ]
    rows = [
        {
            "\u56fd\u5bb6/\u5730\u533a": "\u5e7f\u897f\u58ee\u65cf\u81ea\u6cbb\u533a",
            "\u5927\u6d32": "\u4e9a\u6d32",
            "\u4eba\u5747GDP": "4.4\u4e07\u5143",
            "\u4eba\u53e3": "5013\u4e07",
            "\u6bcf\u65e5\u68c0\u6d4b\u6570": "11.6\u4e07\u4efd",
            "\u75c5\u4f8b\u6570": "0",
        },
        {
            "\u56fd\u5bb6/\u5730\u533a": "\u4e91\u5357\u7701",
            "\u5927\u6d32": "\u4e9a\u6d32",
            "\u4eba\u5747GDP": "5.5\u4e07\u5143",
            "\u4eba\u53e3": "4721\u4e07",
            "\u6bcf\u65e5\u68c0\u6d4b\u6570": "13.4\u4e07\u4efd",
            "\u75c5\u4f8b\u6570": "1",
        },
    ]
    doc_text = (
        "\u5e7f\u897f\u58ee\u65cf\u81ea\u6cbb\u533a\u4eba\u53e3 5013 \u4e07\uff0c7 \u6708 27 \u65e5\u96f6\u65b0\u589e\u786e\u8bca\u75c5\u4f8b\uff0c"
        "\u68c0\u6d4b\u91cf\u7ea6 11.6 \u4e07\u4efd\u3002\n"
        "\u4e91\u5357\u7701\u4eba\u53e3 4721 \u4e07\uff0c7 \u6708 27 \u65e5\u62a5\u544a 1 \u4f8b\u5883\u5916\u8f93\u5165\u786e\u8bca\u75c5\u4f8b\uff0c"
        "\u5f53\u65e5\u6838\u9178\u68c0\u6d4b\u91cf\u7ea6 13.4 \u4e07\u4efd\u3002"
    )

    normalized = _normalize_word_rows_for_structured_metrics(rows, headers, doc_text=doc_text)

    assert normalized[0]["\u75c5\u4f8b\u6570"] == "0"
    assert normalized[1]["\u75c5\u4f8b\u6570"] == "1"


def test_normalize_word_rows_can_repair_zero_from_same_paragraph_case_count() -> None:
    headers = [
        "\u56fd\u5bb6/\u5730\u533a",
        "\u5927\u6d32",
        "\u4eba\u5747GDP",
        "\u4eba\u53e3",
        "\u6bcf\u65e5\u68c0\u6d4b\u6570",
        "\u75c5\u4f8b\u6570",
    ]
    rows = [
        {
            "\u56fd\u5bb6/\u5730\u533a": "\u5e7f\u4e1c\u7701",
            "\u5927\u6d32": "\u4e9a\u6d32",
            "\u4eba\u5747GDP": "9.6\u4e07\u5143",
            "\u4eba\u53e3": "1.26\u4ebf",
            "\u6bcf\u65e5\u68c0\u6d4b\u6570": "38.2\u4e07\u4efd",
            "\u75c5\u4f8b\u6570": "0",
        }
    ]
    doc_text = (
        "\u5e7f\u4e1c\u7701\u5e38\u4f4f\u4eba\u53e3\u7ea6 1.26 \u4ebf\uff0c7 \u6708 27 \u65e5\u65e0\u672c\u571f\u65b0\u589e\u786e\u8bca\u75c5\u4f8b\uff0c"
        "\u65b0\u589e 4 \u4f8b\u5883\u5916\u8f93\u5165\u65e0\u75c7\u72b6\u611f\u67d3\u8005\uff0c\u5f53\u65e5\u6838\u9178\u68c0\u6d4b\u91cf\u7ea6 38.2 \u4e07\u4efd\u3002\n"
        "\u6cb3\u5357\u7701\u4eba\u53e3\u7ea6 9605 \u4e07\uff0c7 \u6708 27 \u65e5\u65e0\u65b0\u589e\u75c5\u4f8b\u3002"
    )

    normalized = _normalize_word_rows_for_structured_metrics(rows, headers, doc_text=doc_text)

    assert normalized[0]["\u75c5\u4f8b\u6570"] == "4"
