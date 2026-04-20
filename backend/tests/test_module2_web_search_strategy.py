from __future__ import annotations

from app.modules.module2.assistant_1.web_search_strategy import (
    build_retry_request,
    finalize_web_search_result,
    prepare_web_search_request,
    should_retry_web_search,
)


def test_prepare_web_search_request_marks_homepage_queries() -> None:
    question = "please search the web Tavily official homepage"

    prepared = prepare_web_search_request({"query": question, "max_results": 5}, origin_question=question)

    assert prepared.asks_official_source is True
    assert prepared.asks_homepage is True
    assert prepared.asks_blog_source is False
    assert prepared.asks_title is False
    assert prepared.query == "tavily official homepage"


def test_build_retry_request_for_homepage_adds_negative_filters() -> None:
    question = "please search the web Tavily official homepage"
    prepared = prepare_web_search_request({"query": question, "max_results": 5}, origin_question=question)

    retry = build_retry_request(prepared)

    assert retry.asks_homepage is True
    assert retry.query == "tavily official homepage -docs -help -blog -news -newsroom -developers"


def test_should_retry_web_search_when_homepage_query_hits_docs_page() -> None:
    question = "please search the web Tavily official homepage"
    prepared = prepare_web_search_request({"query": question, "max_results": 5}, origin_question=question)
    result = {
        "ok": True,
        "results": [
            {
                "title": "Product News Tracker - Tavily Docs",
                "url": "https://docs.tavily.com/examples/quick-tutorials/product-news-tracker",
                "content": "Docs example page.",
                "score": 0.92,
            }
        ],
    }

    assert should_retry_web_search(result, prepared) is True


def test_finalize_web_search_result_prefers_homepage_over_docs_page() -> None:
    question = "please search the web Tavily official homepage"
    prepared = prepare_web_search_request({"query": question, "max_results": 5}, origin_question=question)
    result = {
        "ok": True,
        "results": [
            {
                "title": "Product News Tracker - Tavily Docs",
                "url": "https://docs.tavily.com/examples/quick-tutorials/product-news-tracker",
                "content": "Docs example page.",
                "score": 0.95,
            },
            {
                "title": "Tavily",
                "url": "https://tavily.com/",
                "content": "Official homepage.",
                "score": 0.61,
            },
        ],
    }

    final = finalize_web_search_result(result, prepared=prepared, retry_result=None)

    assert final["preferred_url"] == "https://tavily.com/"
    assert final["recommended_response"] == "https://tavily.com/"
    assert final["answer"] == "https://tavily.com/"


def test_finalize_web_search_result_prefers_direct_article_over_newsroom_index() -> None:
    question = "please search the web OpenAI official blog latest article title"
    prepared = prepare_web_search_request({"query": question, "max_results": 5}, origin_question=question)
    result = {
        "ok": True,
        "results": [
            {
                "title": "Research - OpenAI Newsroom",
                "url": "https://openai.com/news/research/",
                "content": "Recent news and announcements.",
                "score": 0.97,
            },
            {
                "title": "OpenAI Newsroom | Recent news",
                "url": "https://openai.com/am-ET/news/company-announcements/",
                "content": "Recent news.",
                "score": 0.94,
            },
            {
                "title": "Introducing Codex improvements",
                "url": "https://openai.com/news/introducing-codex-improvements/",
                "content": "Introducing Codex improvements",
                "score": 0.71,
            },
        ],
    }

    final = finalize_web_search_result(result, prepared=prepared, retry_result=None)

    assert final["preferred_url"] == "https://openai.com/news/introducing-codex-improvements/"
    assert final["preferred_title"] == "Introducing Codex improvements"
    assert final["recommended_response"] == "Introducing Codex improvements"
    assert final["answer"] == "Introducing Codex improvements"


def test_prepare_web_search_request_current_title_queries_use_news_bias() -> None:
    question = "please search the web OpenAI official blog latest article title"

    prepared = prepare_web_search_request({"query": question, "max_results": 5}, origin_question=question)

    assert prepared.query == "openai official latest article title"
    assert prepared.topic == "news"
    assert prepared.time_range == "year"


def test_build_retry_request_for_current_title_queries_adds_site_bias() -> None:
    question = "please search the web OpenAI official blog latest article title"
    prepared = prepare_web_search_request({"query": question, "max_results": 5}, origin_question=question)

    retry = build_retry_request(prepared)

    assert retry.topic == "news"
    assert retry.query == "site:openai.com openai official latest article title -community -forum -docs -help"


def test_finalize_web_search_result_prefers_index_article_for_current_title_queries() -> None:
    question = "please search the web OpenAI official blog latest article title"
    prepared = prepare_web_search_request({"query": question, "max_results": 5}, origin_question=question)
    result = {
        "ok": True,
        "results": [
            {
                "title": "Research - OpenAI Newsroom",
                "url": "https://openai.com/news/research/",
                "content": "Recent news and announcements.",
                "score": 0.97,
            },
            {
                "title": "Statement on OpenAI's Nonprofit and PBC - OpenAI",
                "url": "https://openai.com/index/statement-on-openai-nonprofit-and-pbc/",
                "content": "OpenAI article page.",
                "score": 0.71,
            },
        ],
    }

    final = finalize_web_search_result(result, prepared=prepared, retry_result=None)

    assert final["preferred_url"] == "https://openai.com/index/statement-on-openai-nonprofit-and-pbc/"
    assert final["preferred_title"] == "Statement on OpenAI's Nonprofit and PBC"
    assert final["recommended_response"] == "Statement on OpenAI's Nonprofit and PBC"
    assert final["answer"] == "Statement on OpenAI's Nonprofit and PBC"


def test_should_not_retry_when_current_title_query_already_hits_article_page() -> None:
    question = "please search the web OpenAI official blog latest article title"
    prepared = prepare_web_search_request({"query": question, "max_results": 5}, origin_question=question)
    result = {
        "ok": True,
        "results": [
            {
                "title": "Introducing gpt-oss - OpenAI",
                "url": "https://openai.com/index/introducing-gpt-oss/",
                "content": "OpenAI article page.",
                "score": 0.95,
            }
        ],
    }

    assert should_retry_web_search(result, prepared) is False
