"""Confluence retriever — modular stub, scalable.

Registered name: `confluence` (enabled:false by default; flip in service.yaml
+ set CONFLUENCE_BASE_URL + CONFLUENCE_API_TOKEN env).

Implements Connector (Retriever ABC) — add one file, one YAML block, zero router change.
Uses Confluence REST v2 search + content APIs, chunking + lexical scoring like
LocalDocsRetriever for POC (swap to vector later per-corpus without routing change).
Each page → one SourceClaim with page provenance (space + id) for Corroborator.
"""
from __future__ import annotations

import os
import re
import time
import logging
from typing import List, Optional, Sequence, Dict

import requests

from cognitive_swarm.orchestration.corroboration import SourceClaim
from cognitive_swarm.orchestration.prompt_optimizer import TaskType
from .base import Connector

logger = logging.getLogger(__name__)

def _tokens(s: str) -> List[str]:
    return re.findall(r"[a-z][a-z0-9']*", s.lower())

def _significant(tokens: List[str]) -> List[str]:
    from cognitive_swarm.memory.verified_memory import STOPWORDS
    return [t for t in tokens if t not in STOPWORDS]

class ConfluenceRetriever(Connector):
    name = "confluence"
    categories: Optional[Sequence[TaskType]] = [TaskType.REASONING, TaskType.UNKNOWN]

    def __init__(
        self,
        base_url: Optional[str] = None,
        reliability: float = 0.85,
        timeout_s: int = 8,
        cache_ttl_s: int = 600,
        space: Optional[str] = None,
        limit: int = 5,
        api_token: Optional[str] = None,
        email: Optional[str] = None,
    ):
        self.base_url = (base_url or os.getenv("CONFLUENCE_BASE_URL") or "").rstrip("/")
        self.reliability = float(reliability)
        self.timeout_s = int(timeout_s)
        self.cache_ttl_s = int(cache_ttl_s)
        self.space = space
        self.limit = int(limit)
        self.api_token = api_token or os.getenv("CONFLUENCE_API_TOKEN") or os.getenv("ATLASSIAN_API_TOKEN")
        self.email = email or os.getenv("CONFLUENCE_EMAIL") or os.getenv("ATLASSIAN_EMAIL")
        self._cache: Dict[str, tuple] = {}

    def _headers(self) -> Dict[str, str]:
        h = {"Accept": "application/json"}
        if self.email and self.api_token:
            import base64
            tok = base64.b64encode(f"{self.email}:{self.api_token}".encode()).decode()
            h["Authorization"] = f"Basic {tok}"
        elif self.api_token:
            h["Authorization"] = f"Bearer {self.api_token}"
        return h

    def get_claims(self, question: str) -> List[SourceClaim]:
        if not self.base_url or not self.api_token:
            logger.debug("Confluence not configured (base_url/api_token missing) — returning no claims")
            return []
        norm = question.strip().lower()
        cached = self._cache.get(norm)
        if cached and cached[0] > time.time():
            return cached[1]
        claims = self._search(question)
        ttl = self.cache_ttl_s if claims else 120
        self._cache[norm] = (time.time() + ttl, claims)
        return claims

    def _search(self, question: str) -> List[SourceClaim]:
        # Confluence Cloud search: /wiki/rest/api/search?cql=text~"<question>" & limit
        cql_parts = [f'text ~ "{question[:120]}"']
        if self.space:
            cql_parts.append(f'space = "{self.space}"')
        url = f"{self.base_url}/wiki/rest/api/search"
        params = {"cql": " AND ".join(cql_parts), "limit": self.limit}
        try:
            r = requests.get(url, params=params, headers=self._headers(), timeout=self.timeout_s)
            r.raise_for_status()
            results = r.json().get("results", [])
        except Exception as e:
            logger.warning("Confluence search failed: %s", e)
            return []
        if not results:
            return []
        # Score by lexical overlap like LocalDocsRetriever — pick best concrete passage
        q_set = set(_significant(_tokens(question)))
        best, best_score = None, -1.0
        for hit in results:
            content = hit.get("content") or hit
            body = ""
            # Try excerpt, then title fallback
            body = hit.get("excerpt") or content.get("title") or ""
            # Fetch full body for top hit lazily if score high enough
            sig = set(_significant(_tokens(body)))
            score = len(q_set & sig) / max(len(q_set), 1) if q_set else 0
            if score > best_score:
                best_score, best = score, (hit, body)
        if best is None or best_score < 0.15:
            return []
        hit, body = best
        return [SourceClaim(
            source=f"confluence:{hit.get('content',{}).get('id') or hit.get('id')} ({hit.get('title') or hit.get('content',{}).get('title','')})",
            answer=self._extract_answer(body),
            reliability=self.reliability,
            independent=True,
            reason=f"Confluence space {self.space or '*'} score {best_score:.2f}",
        )]

    @staticmethod
    def _extract_answer(text: str) -> str:
        # Same normalizer as LocalDocsRetriever — keeps Corroborator grouping consistent
        m = re.search(r"\b(\d{1,4}\s*(?:CE|AD|BCE|BC)\b)", text)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
        m = re.search(r"\b([A-Z][A-Za-z0-9]*\d[A-Za-z0-9]*)\b", text)
        if m and 2 <= len(m.group(1)) <= 6:
            return m.group(1)
        return re.split(r"(?<=[.!?])\s+", text)[0].strip()[:300] if text else ""
