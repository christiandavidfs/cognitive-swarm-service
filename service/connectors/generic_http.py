"""Generic HTTP retriever — turn any JSON API into a SourceClaim.

Registered name: `generic_http` (enabled:false). Config-driven jmespath-ish extraction,
so Databricks/Confluence/any future source that doesn't deserve its own file can still
be plugged via YAML only:

  generic_http:
    enabled: false
    reliability: 0.6
    base_url: https://api.example.com/search
    method: GET
    params: {q: "{question}", limit: 1}
    headers: {Authorization: "Bearer ${API_TOKEN}"}
    answer_path: "results.0.answer"   # dotted path into JSON
    source_path: "results.0.source"
    reliability_path: "results.0.reliability"

Answer/source paths are dotted; result must resolve to a string. One claim per request.
"""
from __future__ import annotations

import os
import time
import logging
from typing import List, Optional, Sequence, Dict, Any

import requests

from .base import Connector, SourceClaim, TaskType

logger = logging.getLogger(__name__)

def _expand_env(obj):
    if isinstance(obj, str):
        return os.path.expandvars(obj)
    if isinstance(obj, dict):
        return {k: _expand_env(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env(v) for v in obj]
    return obj

def _get_path(data: Any, path: str) -> Any:
    cur = data
    for part in path.split("."):
        if part.isdigit() and isinstance(cur, list):
            idx = int(part)
            cur = cur[idx] if 0 <= idx < len(cur) else None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
        if cur is None:
            return None
    return cur

class GenericHTTPRetriever(Connector):
    name = "generic_http"
    categories: Optional[Sequence[TaskType]] = [TaskType.REASONING, TaskType.UNKNOWN]

    def __init__(
        self,
        base_url: Optional[str] = None,
        reliability: float = 0.6,
        timeout_s: int = 6,
        cache_ttl_s: int = 600,
        method: str = "GET",
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        answer_path: str = "answer",
        source_path: Optional[str] = None,
        reliability_path: Optional[str] = None,
    ):
        self.base_url = _expand_env(base_url or os.getenv("GENERIC_HTTP_BASE_URL") or "")
        if self.base_url.startswith("${"):
            self.base_url = ""  # unexpanded placeholder (var unset) -> disabled
        self.reliability = float(reliability)
        self.timeout_s = int(timeout_s)
        self.cache_ttl_s = int(cache_ttl_s)
        self.method = method.upper()
        self.params = _expand_env(params or {})
        self.headers = _expand_env(headers or {})
        self.answer_path = answer_path
        self.source_path = source_path
        self.reliability_path = reliability_path
        self._cache: Dict[str, tuple] = {}

    def get_claims(self, question: str) -> List[SourceClaim]:
        if not self.base_url:
            return []
        norm = question.strip().lower()
        cached = self._cache.get(norm)
        if cached and cached[0] > time.time():
            return cached[1]
        claims = self._fetch(question)
        ttl = self.cache_ttl_s if claims else 120
        self._cache[norm] = (time.time() + ttl, claims)
        return claims

    def _fetch(self, question: str) -> List[SourceClaim]:
        # Inject {question} into params
        rendered_params = {}
        for k, v in (self.params or {}).items():
            rendered_params[k] = v.replace("{question}", question) if isinstance(v, str) else v
        headers = {k: (v.replace("{question}", question) if isinstance(v, str) else v) for k, v in (self.headers or {}).items()}
        try:
            if self.method == "GET":
                r = requests.get(self.base_url, params=rendered_params, headers=headers, timeout=self.timeout_s)
            else:
                r = requests.request(self.method, self.base_url, json=rendered_params, headers=headers, timeout=self.timeout_s)
            r.raise_for_status()
            data = r.json() if r.headers.get("content-type","").startswith("application/json") else {}
        except Exception as e:
            logger.debug("GenericHTTP %s failed: %s", self.base_url, e)
            return []
        ans = _get_path(data, self.answer_path)
        if not ans or not str(ans).strip():
            return []
        src = _get_path(data, self.source_path) if self.source_path else self.base_url
        rel_raw = _get_path(data, self.reliability_path) if self.reliability_path else None
        try:
            rel = float(rel_raw) if rel_raw is not None else self.reliability
        except Exception:
            rel = self.reliability
        return [SourceClaim(source=str(src)[:120], answer=str(ans).strip()[:500], reliability=rel, independent=True, reason="generic_http")]
