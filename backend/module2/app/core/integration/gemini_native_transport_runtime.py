from __future__ import annotations

import re
import urllib.parse
from typing import Callable, Dict


ResolveNativeApiUrl = Callable[[], str]


class GeminiNativeTransportRuntime:
    """Shared URL and header helpers for Gemini native transport calls."""

    def __init__(
        self,
        *,
        resolve_native_api_url: ResolveNativeApiUrl,
        user_agent: str,
        default_model: str,
        connection_close: bool = False,
    ) -> None:
        self._resolve_native_api_url = resolve_native_api_url
        self.user_agent = str(user_agent or "").strip() or "smart-doc-flow-module2/1.0"
        self.default_model = str(default_model or "").strip() or "gemini-2.5-flash"
        self.connection_close = bool(connection_close)

    def build_google_native_url(self, model: str) -> str:
        model_name = str(model or "").strip() or self.default_model
        return (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{urllib.parse.quote(model_name, safe='')}:generateContent"
        )

    @staticmethod
    def apply_model_to_native_url(url: str, model: str) -> str:
        raw_url = str(url or "").strip()
        model_name = str(model or "").strip()
        if not raw_url or not model_name:
            return raw_url
        quoted_model = urllib.parse.quote(model_name, safe="")
        return re.sub(r"(/models/)([^/?:]+)(:generateContent)", rf"\1{quoted_model}\3", raw_url, count=1)

    def resolve_native_url(self, model: str) -> str:
        raw = self._resolve_native_api_url()
        if not raw:
            return ""
        return self.apply_model_to_native_url(raw, model)

    def build_headers(self, url: str, api_key: str) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }
        if self.connection_close:
            headers["Connection"] = "close"

        url_lower = str(url or "").lower()
        key = str(api_key or "").strip()
        if "generativelanguage.googleapis.com" in url_lower and "key=" not in url_lower and key.startswith("AIza"):
            headers["x-goog-api-key"] = key
        else:
            headers["Authorization"] = f"Bearer {key}"
        return headers
