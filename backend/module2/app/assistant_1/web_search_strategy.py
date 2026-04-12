from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List
from urllib.parse import urlparse

from .text_utils import normalize_text


_SITE_TOKEN_RE = re.compile(r"(?:^|\s)site:([a-z0-9.-]+\.[a-z]{2,})(?=\s|$)", re.IGNORECASE)
_ASCII_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9._-]{2,}")
_OFFICIAL_MARKERS = ("官方", "官网", "official")
_BLOG_MARKERS = ("博客", "blog", "newsroom", "developer blog")
_TITLE_MARKERS = ("标题", "title", "文章", "post", "article", "headline")
_CURRENT_MARKERS = ("今天", "最新", "最近", "当前", "实时", "today", "latest", "recent", "current", "news")
_PATH_HINTS = (
    "blog",
    "news",
    "newsroom",
    "research",
    "release",
    "releases",
    "announcement",
    "announcements",
    "developers",
    "developer",
)
_STRIP_PREFIX_PATTERNS = (
    r"^\s*please\s+search\s+the\s+web\s+",
    r"^\s*search\s+the\s+web\s+",
    r"^\s*请(?:帮我)?(?:联网)?(?:搜索|查询|查一下|查找)\s*",
    r"^\s*(?:联网)?(?:搜索|查询|查一下|查找)\s*",
    r"^\s*please\s+(?:search|look up)\s+",
    r"^\s*(?:search|look up)\s+",
)
_META_SPLIT_MARKERS = (
    "并告诉我",
    "并说是否",
    "并确认",
    "顺便告诉我",
    "同时告诉我",
    "and tell me",
    "and confirm",
)
_GENERIC_TOKENS = {
    "official",
    "blog",
    "latest",
    "recent",
    "today",
    "current",
    "news",
    "title",
    "article",
    "post",
    "search",
    "please",
    "query",
    "look",
    "lookup",
    "site",
    "web",
    "online",
    "internet",
    "the",
    "and",
    "or",
    "to",
    "of",
    "for",
    "from",
    "with",
    "based",
    "tell",
    "show",
    "what",
    "which",
    "used",
    "use",
    "mainly",
    "materials",
    "material",
    "please",
    "into",
    "draft",
    "convert",
    "design",
    "document",
    "fields",
    "exist",
    "current",
    "database",
    "execute",
    "anything",
    "about",
}
_GENERIC_PAGE_TITLES = {
    "blog",
    "developer blog",
    "official blog",
    "research blog",
    "news",
    "recent news",
    "newsroom",
    "research",
}
_GENERIC_CONTENT_LINES = {
    "search the blog",
    "suggested",
    "get started",
    "core concepts",
    "resources",
    "guides",
    "topics",
    "categories",
    "recent",
    "learn",
    "contribute",
    "events",
    "programs",
}
_MONTH_PATTERN = (
    r"(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|"
    r"oct|october|nov|november|dec|december)"
)
_DATE_ONLY_RE = re.compile(rf"^\s*{_MONTH_PATTERN}\s+\d{{1,2}}(?:,\s*\d{{4}})?\s*$", re.IGNORECASE)
_DATE_SUFFIX_RE = re.compile(rf"\s*[|·-]\s*{_MONTH_PATTERN}\s+\d{{1,2}}(?:,\s*\d{{4}})?\s*$", re.IGNORECASE)
_URLISH_RE = re.compile(r"^https?://", re.IGNORECASE)
_HEADING_PREFIX_RE = re.compile(r"^[#>*\-\d\.\)\(\[\]\s]+")
_BRACKET_NOISE_RE = re.compile(r"\[\.\.\.\]|\[[^\]]{0,40}\]")
_NON_TEXT_RE = re.compile(r"[A-Za-z\u4e00-\u9fff]")
_LOCALE_PATH_RE = re.compile(r"^/[a-z]{2}(?:-[a-z]{2})?(?:/|$)", re.IGNORECASE)


@dataclass(frozen=True)
class WebSearchPreparedRequest:
    query: str
    topic: str
    search_depth: str
    max_results: int
    include_domains: List[str]
    time_range: str
    days: int | None
    asks_official_source: bool
    asks_blog_source: bool
    asks_title: bool
    wants_current: bool
    anchor_tokens: List[str]
    origin_question: str
    derived_from_site_token: bool


def prepare_web_search_request(arguments: Dict[str, Any], *, origin_question: str = "") -> WebSearchPreparedRequest:
    raw_query = normalize_text(arguments.get("query"))
    origin = normalize_text(origin_question)
    include_domains = _normalize_domain_list(arguments.get("include_domains"))
    site_domains = _extract_site_domains(raw_query)
    merged_text = " ".join(part for part in (origin, raw_query) if part).strip()

    asks_official_source = _contains_any(merged_text.lower(), _OFFICIAL_MARKERS)
    asks_blog_source = _contains_any(merged_text.lower(), _BLOG_MARKERS)
    asks_title = _contains_any(merged_text.lower(), _TITLE_MARKERS)
    wants_current = (
        _contains_any(merged_text.lower(), _CURRENT_MARKERS)
        or bool(arguments.get("time_range"))
        or isinstance(arguments.get("days"), int)
    )

    cleaned_origin = _strip_search_meta(origin)
    cleaned_query = _strip_search_meta(_strip_site_tokens(raw_query))
    focus_text = cleaned_origin or cleaned_query or origin or raw_query
    anchor_tokens = _extract_anchor_tokens(focus_text or merged_text)

    prepared_domains = list(dict.fromkeys([*include_domains, *site_domains]))
    if (asks_official_source or asks_blog_source) and not prepared_domains:
        prepared_domains = _infer_soft_official_domains(anchor_tokens)
    expanded_domains = _expand_domain_families(prepared_domains) if prepared_domains else []

    query = _build_query_text(
        focus_text=focus_text,
        anchor_tokens=anchor_tokens,
        asks_official_source=asks_official_source,
        asks_blog_source=asks_blog_source,
        asks_title=asks_title,
        wants_current=wants_current,
    )

    topic = normalize_text(arguments.get("topic")).lower() or "general"
    if topic not in {"general", "news"}:
        topic = "general"
    if wants_current and not (asks_official_source or asks_blog_source) and topic == "general":
        topic = "news"
    if asks_official_source or asks_blog_source:
        topic = "general"

    search_depth = normalize_text(arguments.get("search_depth")).lower() or "basic"
    if search_depth not in {"basic", "advanced"}:
        search_depth = "basic"
    if asks_official_source or asks_blog_source or asks_title:
        search_depth = "advanced"

    max_results = arguments.get("max_results") if isinstance(arguments.get("max_results"), int) else 0
    max_results = max(1, min(10, max_results or 0))
    if asks_official_source or asks_blog_source or asks_title:
        max_results = max(5, max_results or 0)
    if max_results <= 0:
        max_results = 5 if (asks_official_source or asks_blog_source or asks_title) else 3

    time_range = normalize_text(arguments.get("time_range")).lower()
    if time_range not in {"day", "week", "month", "year"}:
        time_range = ""
    days = arguments.get("days") if isinstance(arguments.get("days"), int) else None
    if asks_official_source or asks_blog_source or asks_title:
        time_range = ""
        days = None

    return WebSearchPreparedRequest(
        query=query,
        topic=topic,
        search_depth=search_depth,
        max_results=max_results,
        include_domains=expanded_domains,
        time_range=time_range,
        days=days,
        asks_official_source=asks_official_source,
        asks_blog_source=asks_blog_source,
        asks_title=asks_title,
        wants_current=wants_current,
        anchor_tokens=anchor_tokens,
        origin_question=origin,
        derived_from_site_token=bool(site_domains),
    )


def should_retry_web_search(result: Dict[str, Any], prepared: WebSearchPreparedRequest) -> bool:
    if not bool(result.get("ok")):
        return False
    if not (prepared.asks_official_source or prepared.asks_blog_source):
        return False
    if not prepared.include_domains:
        return False

    primary_results = result.get("results") if isinstance(result.get("results"), list) else []
    reranked = _rerank_results(primary_results, prepared=prepared)
    preferred_result = _select_preferred_result(reranked, prepared=prepared)
    if not isinstance(preferred_result, dict):
        return True

    domain = _domain_from_url(preferred_result.get("url"))
    if not _domain_is_preferred(domain, prepared.include_domains):
        return True
    if _has_locale_path(preferred_result):
        return True
    if prepared.asks_blog_source and not _is_blog_forward_result(preferred_result):
        return True
    if prepared.asks_title and not _derive_answer_title_from_result(preferred_result, prepared=prepared):
        return True
    return False


def build_retry_request(prepared: WebSearchPreparedRequest) -> WebSearchPreparedRequest:
    retry_query = prepared.query
    if prepared.anchor_tokens:
        if prepared.asks_blog_source or prepared.asks_title:
            retry_parts: List[str] = [" ".join(prepared.anchor_tokens)]
            if prepared.asks_official_source:
                retry_parts.append("official")
            if prepared.asks_blog_source:
                retry_parts.extend(["blog", "newsroom"])
            if prepared.wants_current:
                retry_parts.extend(["latest", "recent"])
            if prepared.asks_title:
                retry_parts.extend(["article", "title"])
            retry_parts.extend(["-community", "-forum", "-docs", "-help"])
            retry_query = normalize_text(" ".join(retry_parts))
    return WebSearchPreparedRequest(
        query=retry_query,
        topic="general",
        search_depth="advanced",
        max_results=max(5, prepared.max_results),
        include_domains=list(prepared.include_domains),
        time_range=prepared.time_range,
        days=prepared.days,
        asks_official_source=prepared.asks_official_source,
        asks_blog_source=prepared.asks_blog_source,
        asks_title=prepared.asks_title,
        wants_current=prepared.wants_current,
        anchor_tokens=list(prepared.anchor_tokens),
        origin_question=prepared.origin_question,
        derived_from_site_token=prepared.derived_from_site_token,
    )


def finalize_web_search_result(
    result: Dict[str, Any],
    *,
    prepared: WebSearchPreparedRequest,
    retry_result: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    merged_results = _merge_results(
        result.get("results") if isinstance(result.get("results"), list) else [],
        retry_result.get("results") if isinstance(retry_result, dict) and isinstance(retry_result.get("results"), list) else [],
    )
    reranked = _rerank_results(merged_results, prepared=prepared)
    preferred_result = _select_preferred_result(reranked, prepared=prepared)
    derived_title = _derive_answer_title_from_result(preferred_result, prepared=prepared)

    payload: Dict[str, Any] = dict(result)
    if isinstance(retry_result, dict) and retry_result.get("answer"):
        payload["answer"] = retry_result.get("answer")
    payload["results"] = reranked
    payload["result_count"] = len(reranked)
    payload["preferred_result"] = preferred_result

    if isinstance(preferred_result, dict):
        preferred_url = normalize_text(preferred_result.get("url"))
        if preferred_url:
            payload["preferred_url"] = preferred_url

    if derived_title:
        payload["preferred_title"] = derived_title
        payload["recommended_response"] = derived_title
        if prepared.asks_title:
            payload["answer"] = derived_title
    elif isinstance(preferred_result, dict):
        fallback_title = _clean_page_title(normalize_text(preferred_result.get("title")))
        if fallback_title and not _looks_like_generic_page_title(fallback_title):
            payload["preferred_title"] = fallback_title
            payload["recommended_response"] = fallback_title
            if prepared.asks_title:
                payload["answer"] = fallback_title
    elif prepared.asks_title and (prepared.asks_official_source or prepared.asks_blog_source):
        payload["recommended_response"] = "未能稳定定位到官方发布页上的最新文章标题，建议继续核验。"
        payload["needs_more_verification"] = True
        payload["answer"] = ""

    payload["search_strategy"] = {
        "asks_official_source": prepared.asks_official_source,
        "asks_blog_source": prepared.asks_blog_source,
        "asks_title": prepared.asks_title,
        "wants_current": prepared.wants_current,
        "include_domains": list(prepared.include_domains),
        "query": prepared.query,
        "retry_used": bool(retry_result),
        "anchor_tokens": list(prepared.anchor_tokens),
    }
    return payload


def _build_query_text(
    *,
    focus_text: str,
    anchor_tokens: List[str],
    asks_official_source: bool,
    asks_blog_source: bool,
    asks_title: bool,
    wants_current: bool,
) -> str:
    if anchor_tokens and asks_official_source:
        suffix_parts: List[str] = ["official"]
        if asks_blog_source:
            suffix_parts.extend(["blog", "newsroom"])
        elif wants_current:
            suffix_parts.extend(["use cases", "product", "api"])
        if asks_title:
            suffix_parts.append("title")
        return normalize_text(" ".join([" ".join(anchor_tokens), *suffix_parts]))
    if anchor_tokens and (asks_blog_source or asks_title):
        suffix_parts: List[str] = []
        if asks_official_source:
            suffix_parts.append("official")
        if asks_blog_source or asks_official_source:
            suffix_parts.extend(["blog", "newsroom"])
        if wants_current:
            suffix_parts.extend(["latest", "post"])
        if asks_title:
            suffix_parts.append("title")
        suffix_parts.extend(["-community", "-forum", "-discourse"])
        return normalize_text(" ".join([" ".join(anchor_tokens), *suffix_parts]))
    return normalize_text(focus_text)


def _rerank_results(results: List[Dict[str, Any]], *, prepared: WebSearchPreparedRequest) -> List[Dict[str, Any]]:
    reranked: List[Dict[str, Any]] = []
    preferred_domains = set(prepared.include_domains)
    for item in results:
        if not isinstance(item, dict):
            continue
        enriched = dict(item)
        url = str(item.get("url") or "").strip()
        domain = _domain_from_url(url)
        path = _path_from_url(url)
        title = normalize_text(item.get("title"))
        content = normalize_text(item.get("content"))
        domain_root = _root_domain(domain)

        score = float(item.get("score") or 0.0)
        overlap_bonus = 0.0
        if prepared.anchor_tokens:
            overlap_bonus += sum(0.35 for token in prepared.anchor_tokens if token in title.lower())
            overlap_bonus += sum(0.15 for token in prepared.anchor_tokens if token in content.lower())
            overlap_bonus += sum(0.6 for token in prepared.anchor_tokens if token in domain)
            overlap_bonus += sum(0.2 for token in prepared.anchor_tokens if token in domain_root)

        official_bonus = 0.0
        if preferred_domains and domain in preferred_domains:
            official_bonus += 2.5
        elif preferred_domains and domain_root and any(domain_root == _root_domain(candidate) for candidate in preferred_domains):
            official_bonus += 0.9

        if prepared.asks_blog_source or prepared.asks_official_source:
            path_has_release_signal = any(marker in path for marker in _PATH_HINTS)
            title_has_release_signal = any(marker in title.lower() for marker in ("blog", "news", "release", "announcement"))
            if path_has_release_signal:
                official_bonus += 1.0
            if domain.startswith(("developers.", "blog.", "www.")):
                official_bonus += 0.6
            if _looks_like_community_result(domain, path, title):
                official_bonus -= 2.0
            if _looks_like_help_or_docs_result(domain, path):
                official_bonus -= 1.4
            if prepared.asks_blog_source:
                if path_has_release_signal or title_has_release_signal:
                    official_bonus += 0.8
                else:
                    official_bonus -= 0.9
                if domain.startswith(("developers.", "docs.")) and not path_has_release_signal:
                    official_bonus -= 0.5
            if preferred_domains and domain and not _domain_is_preferred(domain, prepared.include_domains):
                official_bonus -= 0.4

        if prepared.asks_title:
            derived_title = _derive_answer_title_from_result(enriched, prepared=prepared)
            if derived_title:
                official_bonus += 0.9
            if _is_index_like_result(enriched):
                official_bonus += 0.45
            if _is_article_like_result(enriched):
                official_bonus += 0.55
            if _has_locale_path(enriched):
                official_bonus -= 0.9
            if title and not _looks_like_generic_page_title(_clean_page_title(title)):
                official_bonus += 0.25

        enriched["_debug_domain"] = domain
        enriched["_debug_root_domain"] = domain_root
        enriched["_debug_rank_score"] = round(score + overlap_bonus + official_bonus, 6)
        reranked.append(enriched)

    reranked.sort(key=lambda item: float(item.get("_debug_rank_score") or 0.0), reverse=True)
    return reranked


def _select_preferred_result(results: List[Dict[str, Any]], *, prepared: WebSearchPreparedRequest) -> Dict[str, Any] | None:
    if not results:
        return None
    if prepared.asks_title:
        if prepared.asks_blog_source:
            for exact_domain_only in (True, False):
                for allow_locale in (False, True):
                    for predicate in (_is_blog_forward_result, _looks_like_blog_result):
                        for item in results:
                            if _has_locale_path(item) != allow_locale:
                                continue
                            if not _matches_domain_scope(item, prepared.include_domains, exact_domain_only=exact_domain_only):
                                continue
                            if not predicate(item):
                                continue
                            if _derive_answer_title_from_result(item, prepared=prepared):
                                return item
        for exact_domain_only in (True, False):
            for allow_locale in (False, True):
                for item in results:
                    if _has_locale_path(item) != allow_locale:
                        continue
                    if not _matches_domain_scope(item, prepared.include_domains, exact_domain_only=exact_domain_only):
                        continue
                    if _derive_answer_title_from_result(item, prepared=prepared):
                        return item
    if prepared.asks_blog_source:
        for exact_domain_only in (True, False):
            for allow_locale in (False, True):
                for predicate in (_is_blog_forward_result, _looks_like_blog_result):
                    for item in results:
                        if _has_locale_path(item) != allow_locale:
                            continue
                        if not _matches_domain_scope(item, prepared.include_domains, exact_domain_only=exact_domain_only):
                            continue
                        if predicate(item):
                            return item
        return None
    return results[0]


def _merge_results(primary: Iterable[Dict[str, Any]], secondary: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen_urls: set[str] = set()
    for item in [*list(primary), *list(secondary)]:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        dedupe_key = url or f"title::{normalize_text(item.get('title'))}"
        if not dedupe_key or dedupe_key in seen_urls:
            continue
        seen_urls.add(dedupe_key)
        merged.append(dict(item))
    return merged


def _derive_answer_title_from_result(item: Dict[str, Any] | None, *, prepared: WebSearchPreparedRequest) -> str:
    if not isinstance(item, dict):
        return ""
    if prepared.asks_title:
        extracted = _extract_latest_article_title(item)
        if extracted:
            return extracted
    title = _clean_page_title(normalize_text(item.get("title")))
    if title and not _looks_like_generic_page_title(title):
        return title
    return ""


def _extract_latest_article_title(item: Dict[str, Any]) -> str:
    title = _clean_page_title(normalize_text(item.get("title")))
    if title and not _looks_like_generic_page_title(title) and not _is_index_like_result(item):
        return title

    content = normalize_text(item.get("content"))
    if not content:
        return ""

    candidates: List[str] = []
    for raw in _split_content_candidates(content):
        cleaned = _clean_candidate_title(raw)
        if not cleaned:
            continue
        if cleaned not in candidates:
            candidates.append(cleaned)

    for candidate in candidates:
        if _looks_like_article_title(candidate):
            return candidate
    return ""


def _split_content_candidates(content: str) -> List[str]:
    normalized = str(content or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = _BRACKET_NOISE_RE.sub(" ", normalized)
    fragments = re.split(r"(?:\n|;)+", normalized)
    candidates: List[str] = []
    for fragment in fragments:
        value = normalize_text(fragment)
        if not value:
            continue
        candidates.append(value)
    return candidates


def _clean_candidate_title(value: str) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    text = _HEADING_PREFIX_RE.sub("", text)
    text = text.replace("Frame.", "").replace("Frame ", "")
    text = text.replace("## ", "").replace("# ", "")
    text = _DATE_SUFFIX_RE.sub("", text)
    text = normalize_text(text.strip(" .,:;|"))
    for separator in (" | ", " — ", " – ", " - "):
        if separator in text:
            first_part = normalize_text(text.split(separator, 1)[0])
            if first_part and not _looks_like_generic_page_title(first_part):
                text = first_part
                break
    return normalize_text(text.strip(" .,:;|\"'“”‘’`"))


def _looks_like_article_title(text: str) -> bool:
    value = normalize_text(text)
    if not value or len(value) < 6:
        return False
    lowered = value.lower().strip(" .,:;|")
    if lowered in _GENERIC_CONTENT_LINES or lowered in _GENERIC_PAGE_TITLES:
        return False
    if lowered.startswith("title:"):
        return False
    if lowered.startswith(("search the blog", "recent news", "openai developers", "informal updates")):
        return False
    if lowered.startswith(("topic ", "topics ", "category ", "categories ", "resource ", "resources ")):
        return False
    if any(
        marker in lowered
        for marker in (
            "opens in a new window",
            "try chatgpt",
            "log in",
            "pricing",
            "download",
            "documentation",
            "developer forum",
            "help center",
        )
    ):
        return False
    if ">" in value:
        return False
    if any(marker in lowered for marker in ("art card", "cover image", " 1x1", "image 1x1")):
        return False
    if _DATE_ONLY_RE.fullmatch(value):
        return False
    if _URLISH_RE.match(value):
        return False
    if not _NON_TEXT_RE.search(value):
        return False
    return True


def _clean_page_title(title: str) -> str:
    value = normalize_text(title)
    if not value:
        return ""
    for separator in (" | ", " — ", " – ", " - "):
        if separator not in value:
            continue
        first_part = normalize_text(value.split(separator, 1)[0])
        if first_part and not _looks_like_generic_page_title(first_part):
            return first_part
    return value


def _looks_like_generic_page_title(title: str) -> bool:
    lowered = normalize_text(title).lower().strip(" .,:;|")
    if not lowered:
        return True
    if lowered in _GENERIC_PAGE_TITLES:
        return True
    return any(lowered.endswith(marker) for marker in _GENERIC_PAGE_TITLES)


def _is_index_like_result(item: Dict[str, Any]) -> bool:
    url = str(item.get("url") or "").strip()
    path = _path_from_url(url).strip("/")
    title = normalize_text(item.get("title"))
    lowered_title = title.lower()
    segments = [segment for segment in path.split("/") if segment]
    if _looks_like_generic_page_title(title):
        return True
    if any(marker in lowered_title for marker in ("developer blog", "recent news", "newsroom")):
        return True
    if segments and segments[-1] in {"blog", "news", "newsroom", "research"}:
        return True
    if len(segments) <= 2 and any(segment in {"blog", "news", "developers"} for segment in segments):
        return True
    return False


def _is_article_like_result(item: Dict[str, Any]) -> bool:
    url = str(item.get("url") or "").strip()
    path = _path_from_url(url).strip("/")
    segments = [segment for segment in path.split("/") if segment]
    if len(segments) < 2:
        return False
    parent_segments = segments[:-1]
    return any(segment in {"blog", "news", "newsroom", "research", "release", "releases", "announcement", "announcements"} for segment in parent_segments)


def _looks_like_blog_result(item: Dict[str, Any]) -> bool:
    url = str(item.get("url") or "").strip()
    domain = _domain_from_url(url)
    path = _path_from_url(url)
    title = normalize_text(item.get("title")).lower()
    if _looks_like_community_result(domain, path, title):
        return False
    if _looks_like_help_or_docs_result(domain, path):
        return False
    return any(marker in path for marker in _PATH_HINTS) or any(
        marker in title for marker in ("blog", "news", "release", "announcement", "newsroom")
    )


def _is_blog_forward_result(item: Dict[str, Any]) -> bool:
    url = str(item.get("url") or "").strip()
    path = _path_from_url(url)
    title = normalize_text(item.get("title")).lower()
    domain = _domain_from_url(url)
    if _looks_like_community_result(domain, path, title) or _looks_like_help_or_docs_result(domain, path):
        return False
    if "blog" in path or "blog" in title:
        return True
    return "newsroom" in path or "newsroom" in title


def _looks_like_community_result(domain: str, path: str, title: str) -> bool:
    return domain.startswith(("community.", "forum.")) or "/t/" in path or " community " in f" {title.lower()} "


def _looks_like_help_or_docs_result(domain: str, path: str) -> bool:
    return (
        domain.startswith(("help.", "docs."))
        or path.startswith("/docs")
        or path.startswith("/help")
        or "/docs/" in path
        or path.startswith("/api/docs")
    )


def _domain_is_preferred(domain: str, include_domains: List[str]) -> bool:
    if not domain:
        return False
    normalized_domain = _normalize_domain(domain)
    preferred = {_normalize_domain(item) for item in include_domains if _normalize_domain(item)}
    if normalized_domain in preferred:
        return True
    root = _root_domain(normalized_domain)
    return any(root and root == _root_domain(candidate) for candidate in preferred)


def _matches_domain_scope(item: Dict[str, Any], include_domains: List[str], *, exact_domain_only: bool) -> bool:
    domain = _domain_from_url(item.get("url"))
    normalized_include_domains = {_normalize_domain(value) for value in include_domains if _normalize_domain(value)}
    if exact_domain_only:
        return domain in normalized_include_domains
    return _domain_is_preferred(domain, include_domains)


def _has_locale_path(item: Dict[str, Any]) -> bool:
    url = str(item.get("url") or "").strip()
    path = _path_from_url(url)
    return bool(_LOCALE_PATH_RE.match(path))


def _extract_site_domains(text: str) -> List[str]:
    return list(dict.fromkeys(_normalize_domain(match) for match in _SITE_TOKEN_RE.findall(str(text or "")) if _normalize_domain(match)))


def _extract_anchor_tokens(text: str) -> List[str]:
    tokens: List[str] = []
    for match in _ASCII_TOKEN_RE.findall(str(text or "")):
        normalized = str(match or "").strip().strip(".,;:!?()[]{}\"'")
        lowered = normalized.lower()
        if lowered in _GENERIC_TOKENS:
            continue
        if lowered.endswith((".com", ".cn", ".org", ".net", ".ai", ".io")):
            lowered = lowered.split(".", 1)[0]
        if lowered in _GENERIC_TOKENS or len(lowered) < 3:
            continue
        if lowered not in tokens:
            tokens.append(lowered)
    return tokens[:4]


def _infer_soft_official_domains(anchor_tokens: List[str]) -> List[str]:
    candidates: List[str] = []
    if len(anchor_tokens) == 1:
        token = anchor_tokens[0]
        if len(token) >= 4 and not token.isdigit():
            candidates.append(f"{token}.com")
    return candidates


def _expand_domain_families(domains: List[str]) -> List[str]:
    expanded: List[str] = []
    for domain in domains:
        root = _root_domain(domain)
        family = [
            domain,
            root,
            f"www.{root}",
            f"developers.{root}",
            f"docs.{root}",
            f"help.{root}",
            f"blog.{root}",
        ]
        for item in family:
            normalized = _normalize_domain(item)
            if normalized and normalized not in expanded:
                expanded.append(normalized)
    return expanded


def _strip_site_tokens(text: str) -> str:
    return normalize_text(_SITE_TOKEN_RE.sub(" ", str(text or "")))


def _strip_search_meta(text: str) -> str:
    value = normalize_text(text)
    if not value:
        return ""
    lowered = value.lower()
    for marker in _META_SPLIT_MARKERS:
        marker_lower = marker.lower()
        index = lowered.find(marker_lower)
        if index > 0:
            head = value[:index].strip(" ,，。；;")
            tail = value[index + len(marker) :].strip(" ,，。；;")
            if _looks_like_generic_search_stub(head) and tail:
                value = tail
            else:
                value = head
            break
    for pattern in _STRIP_PREFIX_PATTERNS:
        value = re.sub(pattern, "", value, flags=re.IGNORECASE).strip()
    if value.lower().startswith("the web "):
        value = value[8:].strip(" ,，。；;")
    if value.lower() == "the web":
        return ""
    return normalize_text(value)


def _looks_like_generic_search_stub(text: str) -> bool:
    lowered = normalize_text(text).lower()
    if not lowered:
        return True
    return lowered in {
        "the web",
        "web",
        "online",
        "internet",
        "the internet",
        "web search",
        "search the web",
    }


def _contains_any(text: str, markers: Iterable[str]) -> bool:
    lowered = str(text or "").lower()
    return any(str(marker or "").lower() in lowered for marker in markers if marker)


def _normalize_domain_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    items: List[str] = []
    for item in value:
        normalized = _normalize_domain(item)
        if normalized and normalized not in items:
            items.append(normalized)
    return items


def _normalize_domain(value: Any) -> str:
    raw = normalize_text(value).lower()
    if not raw:
        return ""
    raw = raw.removeprefix("https://").removeprefix("http://")
    return raw.strip("/")


def _domain_from_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    return _normalize_domain(parsed.netloc)


def _path_from_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    return normalize_text(parsed.path).lower()


def _root_domain(domain: str) -> str:
    normalized = _normalize_domain(domain)
    if not normalized:
        return ""
    parts = normalized.split(".")
    if len(parts) <= 2:
        return normalized
    return ".".join(parts[-2:])
