from __future__ import annotations

from typing import Any

import requests
from requests import HTTPError

from .config import Assistant1Settings
from .text_utils import normalize_text


def _normalize_time_range(value: Any) -> str:
    normalized = normalize_text(value).lower()
    if normalized in {"day", "week", "month", "year", "d", "w", "m", "y"}:
        return normalized
    return ""


def _time_range_from_days(days: int | None) -> str:
    if not isinstance(days, int) or days <= 0:
        return ""
    if days <= 1:
        return "day"
    if days <= 7:
        return "week"
    if days <= 31:
        return "month"
    return "year"


class TavilySearchClient:
    def __init__(self, settings: Assistant1Settings | None = None) -> None:
        self.settings = settings or Assistant1Settings.from_env()
        self.api_key = str(self.settings.tavily_api_key or "").strip()
        self.search_url = str(self.settings.tavily_search_url or "").strip()
        self.timeout_sec = float(self.settings.tavily_timeout_sec)
        self.max_results = int(self.settings.tavily_max_results)

    @property
    def ready(self) -> bool:
        return bool(self.api_key and self.search_url)

    def search(
        self,
        query: str,
        *,
        topic: str = "general",
        search_depth: str = "basic",
        max_results: int | None = None,
        include_domains: list[str] | None = None,
        time_range: str = "",
        days: int | None = None,
    ) -> dict[str, Any]:
        text = normalize_text(query)
        if not text:
            return {"ok": False, "error": "query is required"}
        if not self.ready:
            return {"ok": False, "error": "Tavily is not configured"}

        safe_topic = str(topic or "general").strip().lower()
        if safe_topic not in {"general", "news"}:
            safe_topic = "general"
        safe_depth = str(search_depth or "basic").strip().lower()
        if safe_depth not in {"basic", "advanced"}:
            safe_depth = "basic"
        safe_max_results = max(1, min(10, int(max_results or self.max_results)))
        safe_time_range = _normalize_time_range(time_range) or _time_range_from_days(days)

        payload: dict[str, Any] = {
            "query": text,
            "topic": safe_topic,
            "search_depth": safe_depth,
            "max_results": safe_max_results,
            "include_answer": True,
            "include_raw_content": False,
        }
        domains = [normalize_text(item) for item in (include_domains or []) if normalize_text(item)]
        if domains:
            payload["include_domains"] = domains
        if safe_time_range:
            payload["time_range"] = safe_time_range

        try:
            response = requests.post(
                self.search_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                timeout=self.timeout_sec,
            )
            response.raise_for_status()
            data = response.json()
        except HTTPError as exc:
            detail = ""
            if exc.response is not None:
                detail = normalize_text(exc.response.text)
            raise RuntimeError(detail or str(exc)) from exc
        results = []
        for item in data.get("results", []) if isinstance(data.get("results"), list) else []:
            if not isinstance(item, dict):
                continue
            results.append(
                {
                    "title": normalize_text(item.get("title")),
                    "url": str(item.get("url") or "").strip(),
                    "content": normalize_text(item.get("content")),
                    "score": float(item.get("score") or 0.0),
                }
            )
        return {
            "ok": True,
            "query": text,
            "topic": safe_topic,
            "search_depth": safe_depth,
            "max_results": safe_max_results,
            "time_range": safe_time_range,
            "answer": normalize_text(data.get("answer")),
            "results": results,
            "response_time": data.get("response_time"),
        }
