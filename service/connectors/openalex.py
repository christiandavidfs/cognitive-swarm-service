"""OpenAlex (+ Semantic Scholar alt) retriever — primary scholarly, free, no key.

Registered names: `openalex` (default, reliability 0.9) and `semantic_scholar` alias.

Design: for factual/contested REASONING/UNKNOWN questions, query OpenAlex
works by title/abstract search, extract a short fact, emit one SourceClaim.
Because each paper is independent, two papers disagreeing naturally surface
`Verdict.status == conflict` via Corroborator — honest provenance (§4).

All HTTP has short timeouts + per-question cache (1h). Failure is silent
(one connector must not kill Tier 3).
"""
from __future__ import annotations

import re
import time
import logging
from typing import List, Optional, Sequence, Dict

import requests

from cognitive_swarm.orchestration.corroboration import SourceClaim
from cognitive_swarm.orchestration.prompt_optimizer import TaskType
from .base import Connector

logger = logging.getLogger(__name__)

OPENALEX_WORKS = "https://api.openalex.org/works"
S2_SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"


class OpenAlexRetriever(Connector):
    name = "openalex"
    categories: Optional[Sequence[TaskType]] = [TaskType.REASONING, TaskType.UNKNOWN]

    def __init__(
        self,
        reliability: float = 0.9,
        timeout_s: int = 6,
        cache_ttl_s: int = 3600,
        per_page: int = 3,
        user_agent: str = "cognitive-swarm-service/0.1 (openalex retriever)",
        mailto: Optional[str] = None,
    ):
        self.reliability = float(reliability)
        self.timeout_s = int(timeout_s)
        self.cache_ttl_s = int(cache_ttl_s)
        self.per_page = int(per_page)
        self.user_agent = user_agent
        self.mailto = mailto
        self._cache: Dict[str, tuple] = {}

    def get_claims(self, question: str) -> List[SourceClaim]:
        norm = question.strip().lower()
        cached = self._cache.get(norm)
        if cached and cached[0] > time.time():
            return cached[1]
        claims = self._search(question)
        ttl = self.cache_ttl_s if claims else 600
        self._cache[norm] = (time.time() + ttl, claims)
        return claims

    def _search(self, question: str) -> List[SourceClaim]:
        # Keep POC narrow: only fire on factual/contested shapes to avoid noise on puzzles.
        # The router's category gate already restricts us to REASONING/UNKNOWN, but we also
        # skip obvious puzzle phrasing ("handshake", "how many apples") — those are L2, not L3.
        ql = question.lower()
        if any(k in ql for k in ["handshake", "take away", "give away", "machines", "snail", "rope cut", "bridge"]):
            return []
        # Use OpenAlex title/abstract search
        params = {
            "filter": f"title_and_abstract.search:{question[:180]}",
            "per-page": self.per_page,
            "select": "id,display_name,publication_year,cited_by_count,abstract_inverted_index",
        }
        if self.mailto:
            params["mailto"] = self.mailto
        headers = {"User-Agent": self.user_agent}
        try:
            r = requests.get(OPENALEX_WORKS, params=params, headers=headers, timeout=self.timeout_s)
            r.raise_for_status()
            results = r.json().get("results", [])
        except Exception as e:
            logger.debug("OpenAlex search failed: %s", e)
            return []
        if not results:
            return []
        # Emit one claim per returned work (max per_page) — enables conflict demo with >1 paper.
        # Use the single best by cited_by_count for POC simplicity (one voice per connector),
        # but keep ability to emit 2 for contested questions.
        # For contested ("what caused the fall..."), we want 2 disagreeing papers — emit up to 2.
        contested = any(k in ql for k in ["what caused", "cause of", "why did", "historians disagree", "disputed"])
        claims: List[SourceClaim] = []
        sorted_results = sorted(results, key=lambda x: x.get("cited_by_count", 0) or 0, reverse=True)
        for w in sorted_results[: (2 if contested else 1)]:
            ans = self._extract_answer(w, question)
            if not ans:
                continue
            wid = w.get("id", "openalex")
            year = w.get("publication_year")
            claims.append(SourceClaim(
                source=f"{wid} ({w.get('display_name','')[:60]})",
                answer=ans,
                reliability=max(0.5, min(0.95, self.reliability + min(0.05, (w.get("cited_by_count", 0) or 0) / 10000))),
                independent=True,
                reason=f"OpenAlex {year}, cited {w.get('cited_by_count',0)}",
            ))
        return claims

    def _extract_answer(self, work: dict, question: str) -> Optional[str]:
        # Prefer inverted abstract (OpenAlex) — reconstruct text
        inv = work.get("abstract_inverted_index")
        if inv:
            # Reconstruct in word order
            words = {}
            for w, idxs in inv.items():
                for i in idxs:
                    words[i] = w
            text = " ".join(words[i] for i in sorted(words.keys()))
        else:
            text = work.get("display_name", "")
        if not text:
            return None
        # Lightweight extraction mirroring LocalDocsRetriever._extract_answer
        # Look for year CE, formula, etc.
        import re as _re
        m = _re.search(r"\b(\d{1,4}\s*(?:CE|AD|BCE|BC)\b)", text)
        if m:
            return _re.sub(r"\s+", " ", m.group(1)).strip()
        m = _re.search(r"\b(1[0-9]{3}|[0-9]{4})\b", text)
        if m and "when" in question.lower():
            return m.group(1)
        # Fallback: first sentence of abstract / title
        return _re.split(r"(?<=[.!?])\s+", text)[0].strip()[:200]


class SemanticScholarRetriever(Connector):
    """Alt to OpenAlex — set provider: semantic_scholar in service.yaml + SEMANTIC_SCHOLAR_API_KEY env."""
    name = "semantic_scholar"
    categories: Optional[Sequence[TaskType]] = [TaskType.REASONING, TaskType.UNKNOWN]

    def __init__(
        self,
        reliability: float = 0.9,
        timeout_s: int = 6,
        cache_ttl_s: int = 3600,
        per_page: int = 3,
        api_key: Optional[str] = None,
        user_agent: str = "cognitive-swarm-service/0.1 (s2 retriever)",
    ):
        import os
        self.reliability = float(reliability)
        self.timeout_s = int(timeout_s)
        self.cache_ttl_s = int(cache_ttl_s)
        self.per_page = int(per_page)
        self.api_key = api_key or os.getenv("SEMANTIC_SCHOLAR_API_KEY")
        self.user_agent = user_agent
        self._cache: Dict[str, tuple] = {}

    def get_claims(self, question: str) -> List[SourceClaim]:
        norm = question.strip().lower()
        cached = self._cache.get(norm)
        if cached and cached[0] > time.time():
            return cached[1]
        claims = self._search(question)
        ttl = self.cache_ttl_s if claims else 600
        self._cache[norm] = (time.time() + ttl, claims)
        return claims

    def _search(self, question: str) -> List[SourceClaim]:
        ql = question.lower()
        if any(k in ql for k in ["handshake", "take away", "give away"]):
            return []
        headers = {"User-Agent": self.user_agent}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        params = {"query": question[:180], "limit": self.per_page, "fields": "title,year,citationCount,abstract"}
        try:
            r = requests.get(S2_SEARCH, params=params, headers=headers, timeout=self.timeout_s)
            r.raise_for_status()
            data = r.json().get("data", [])
        except Exception as e:
            logger.debug("S2 search failed: %s", e)
            return []
        claims = []
        for p in data[:1]:
            ans = (p.get("abstract") or p.get("title") or "").split(".")[0].strip()[:200]
            if not ans:
                continue
            claims.append(SourceClaim(source=f"s2:{p.get('paperId','')}", answer=ans, reliability=self.reliability, independent=True, reason=f"S2 {p.get('year')} cited {p.get('citationCount',0)}"))
        return claims
