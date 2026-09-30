"""Wikidata retriever — structured SPARQL, free, no key.

Registered name: `wikidata` (enabled by default, reliability 0.8 from service.yaml).

Design: resolve question → search Wikidata entities → fetch a small set of
claims via SPARQL, emit one SourceClaim per matching claim. Each claim is
reliability+independence weighted by the Corroborator, so a single Wikidata
fact can corroborate a Scholar paper and vice versa — exactly the honest
provenance split from docs/ARCHITECTURE.md §4.

Robustness: all HTTP has short timeouts + 24h in-memory cache (stable facts).
One failing connector never kills Tier 3 (TruthRouter._collect_source_claims catches).
"""
from __future__ import annotations

import re
import time
import logging
from typing import List, Optional, Sequence, Dict

import requests

from .base import Connector, SourceClaim, TaskType

logger = logging.getLogger(__name__)

WD_SEARCH = "https://www.wikidata.org/w/api.php"
WD_SPARQL = "https://query.wikidata.org/sparql"

# Minimal question → property mapping (expand without touching router).
# For POC we cover the demo shapes; adding a property is one dict entry.
QUESTION_PATTERNS: List[Dict] = [
    # Fall of Western Roman Empire → dissolution date P576 or inception edge
    {"keywords": ["fall", "western roman empire"], "qid": "Q456", "props": ["P576", "P582"], "label": "Western Roman Empire dissolution"},
    {"keywords": ["fall", "roman empire"], "qid": "Q2277", "props": ["P576", "P582"], "label": "Roman Empire dissolution"},
    # Capitals: "capital of France" → P36
    {"keywords": ["capital", "france"], "qid": "Q142", "props": ["P36"], "label": "France capital"},
    # Speed of light, water formula etc. — extend as needed
]

# Property ID → human label for claim extraction (used in answer normalization)
PROP_LABELS = {
    "P36": "capital",
    "P576": "dissolved",
    "P582": "end time",
    "P571": "inception",
    "P274": "chemical formula",
    "P2534": "defining formula",
}


class WikidataRetriever(Connector):
    name = "wikidata"
    categories: Optional[Sequence[TaskType]] = [TaskType.REASONING, TaskType.UNKNOWN]

    def __init__(
        self,
        reliability: float = 0.8,
        timeout_s: int = 5,
        cache_ttl_s: int = 86400,
        user_agent: str = "cognitive-swarm-service/0.1 (wikidata retriever)",
    ):
        self.reliability = float(reliability)
        self.timeout_s = int(timeout_s)
        self.cache_ttl_s = int(cache_ttl_s)
        self.user_agent = user_agent
        self._cache: Dict[str, tuple] = {}  # key -> (expiry, claims)

    def get_claims(self, question: str) -> List[SourceClaim]:
        norm = question.strip().lower()
        # cheap exact cache (24h) — stable facts don't change per request
        cached = self._cache.get(norm)
        if cached and cached[0] > time.time():
            return cached[1]
        # Quick gate: if no pattern matches, try generic entity search fallback
        matched = self._match_patterns(norm)
        if matched:
            claims = self._fetch_claims(matched)
        else:
            # Generic fallback: search Wikidata for the most relevant entity + try P36/P571/P576
            claims = self._generic_search(question)
        # cache even empty (negative cache) for 10m to avoid hammering
        ttl = self.cache_ttl_s if claims else 600
        self._cache[norm] = (time.time() + ttl, claims)
        return claims

    def _match_patterns(self, norm: str) -> Optional[Dict]:
        for pat in QUESTION_PATTERNS:
            if all(k in norm for k in pat["keywords"]):
                return pat
        return None

    def _fetch_claims(self, pat: Dict) -> List[SourceClaim]:
        qid = pat["qid"]
        props = pat["props"]
        claims: List[SourceClaim] = []
        for prop in props:
            ans = self._sparql_value(qid, prop)
            if ans:
                claims.append(SourceClaim(
                    source=f"wikidata:{qid}:{prop} ({pat['label']})",
                    answer=ans,
                    reliability=self.reliability,
                    independent=True,
                    reason=f"Wikidata SPARQL {qid} {prop} via WDQS",
                ))
        # dedup by answer
        seen = set()
        uniq = []
        for c in claims:
            k = c.answer.strip().lower()
            if k not in seen:
                seen.add(k)
                uniq.append(c)
        return uniq

    def _sparql_value(self, qid: str, prop: str) -> Optional[str]:
        # SELECT ?v WHERE { wd:Q142 wdt:P36 ?v }  → follow labels
        # For dates, prefer year CE formatting consistent with _extract_answer norms.
        query = f"SELECT ?v ?vLabel WHERE {{ wd:{qid} wdt:{prop} ?v . SERVICE wikibase:label {{ bd:serviceParam wikibase:language 'en'. }} }} LIMIT 1"
        headers = {"User-Agent": self.user_agent, "Accept": "application/sparql-results+json"}
        try:
            r = requests.get(WD_SPARQL, params={"query": query, "format": "json"}, headers=headers, timeout=self.timeout_s)
            r.raise_for_status()
            data = r.json()
            bindings = data.get("results", {}).get("bindings", [])
            if not bindings:
                return None
            b = bindings[0]
            # value may be uri (entity) or literal
            label = b.get("vLabel", {}).get("value")
            raw = b.get("v", {}).get("value", label)
            if not label:
                label = raw
            if not label:
                return None
            # Normalize date-ish: keep "476" or "476 CE" etc. consistent with core _extract_answer
            return self._normalize_wikidata_answer(label, raw)
        except Exception as e:
            logger.debug("Wikidata SPARQL %s %s failed: %s", qid, prop, e)
            return None

    def _normalize_wikidata_answer(self, label: str, raw: str) -> str:
        s = label.strip()
        # Date literals come as 0476-01-01T00:00:00Z — extract year
        m = re.search(r"(\d{3,4})-\d{2}-\d{2}T", raw)
        if m:
            year = m.group(1).lstrip("0") or "0"
            # Most history answers expect "476 CE" — keep CE suffix for corroboration grouping
            # The core extractor already handles "476 CE" vs "476".
            return f"{year} CE"
        # Entity labels already human (e.g., "Paris")
        return s

    def _generic_search(self, question: str) -> List[SourceClaim]:
        # Lightweight: search Wikidata for top entity, then try P36 (capital) / P571 etc.
        # Keep POC narrow — only trigger on explicit patterns to avoid false positives.
        ql = question.lower()
        # Capital pattern generic
        m = re.search(r"capital of ([a-z ]{3,30})\??", ql)
        if m:
            country = m.group(1).strip()
            qid = self._search_qid(country)
            if qid:
                ans = self._sparql_value(qid, "P36")
                if ans:
                    return [SourceClaim(source=f"wikidata:{qid}:P36 (capital of {country})", answer=ans, reliability=self.reliability, independent=True, reason=f"Wikidata generic capital {qid}")]
        return []

    def _search_qid(self, term: str) -> Optional[str]:
        try:
            r = requests.get(WD_SEARCH, params={"action": "wbsearchentities", "search": term, "language": "en", "format": "json", "limit": 1}, headers={"User-Agent": self.user_agent}, timeout=self.timeout_s)
            r.raise_for_status()
            hits = r.json().get("search", [])
            if hits:
                return hits[0].get("id")
        except Exception as e:
            logger.debug("Wikidata search %r failed: %s", term, e)
        return None
