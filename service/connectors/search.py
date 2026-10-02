"""Web search connector — SearXNG-compatible (self-hostable, no key).

Works against any SearXNG instance (local or public): GET {base}/search
with q + format=json. Each hit becomes a claim (title+snippet); the
Corroborator + Wikidata crossing do the truth work downstream — this
connector only FETCHES candidates, never judges.

Registered name: `search` (enabled:false; needs SEARCH_BASE_URL).
Per-request `connectors:["search"]` or flip in service.yaml.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Dict, List, Optional, Sequence

import requests

from service.contracts import SourceClaim, TaskType
from .base import Connector

logger = logging.getLogger(__name__)


class SearchConnector(Connector):
    name = "search"
    categories: Optional[Sequence[TaskType]] = [TaskType.REASONING, TaskType.UNKNOWN]

    def __init__(
        self,
        base_url: Optional[str] = None,
        reliability: float = 0.6,  # search hits are candidates, not authorities
        timeout_s: int = 8,
        cache_ttl_s: int = 600,
        per_page: int = 5,
    ):
        self.base_url = (base_url or os.getenv("SEARCH_BASE_URL") or "").rstrip("/")
        if self.base_url.startswith("${"):
            self.base_url = ""
        self.reliability = float(reliability)
        self.timeout_s = int(timeout_s)
        self.cache_ttl_s = int(cache_ttl_s)
        self.per_page = int(per_page)
        self._cache: Dict[str, tuple] = {}

    def get_claims(self, question: str) -> List[SourceClaim]:
        if not self.base_url:
            return []
        norm = question.strip().lower()
        cached = self._cache.get(norm)
        if cached and cached[0] > time.time():
            return cached[1]
        claims = self._search(question)
        self._cache[norm] = (time.time() + (self.cache_ttl_s if claims else 120), claims)
        return claims

    def _search(self, question: str) -> List[SourceClaim]:
        try:
            r = requests.get(f"{self.base_url}/search",
                             params={"q": question[:200], "format": "json",
                                     "pageno": 1, "language": "all"},
                             headers={"Accept": "application/json"},
                             timeout=self.timeout_s)
            r.raise_for_status()
            hits = r.json().get("results", [])[: self.per_page]
        except Exception as e:
            logger.debug("Search %s failed: %s", self.base_url, e)
            return []
        claims = []
        for h in hits:
            title = (h.get("title") or "").strip()
            snippet = (h.get("content") or "").strip()
            url = h.get("url", "")
            ans = f"{title} — {snippet[:200]}".strip(" —")
            if not ans:
                continue
            claims.append(SourceClaim(source=f"search:{url[:80]}", answer=ans,
                                      reliability=self.reliability, independent=False,
                                      reason="web hit (uncorroborated candidate)"))
        return claims
