"""LocalDocs connector — standalone lexical file search. No external imports.

Reads ``*.txt``/``*.md`` under ``source_dir`` (default ``./retrieval_corpus``,
override via YAML or ``LOCAL_DOCS_DIR`` env), scores chunks by significant
token overlap, emits one claim for the best chunk above threshold.
"""
from __future__ import annotations

import os
import re
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from service.contracts import SourceClaim, TaskType
from service.memory.store import STOPWORDS, _significant, _tokens
from .base import Connector

logger = logging.getLogger(__name__)


def _chunks(text: str, size: int) -> List[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paras:
        return []
    out: List[str] = []
    for i in range(0, len(paras), max(size, 1)):
        out.append("\n".join(paras[i:i + max(size, 1)]))
    return out


def _extract_answer(text: str) -> str:
    m = re.search(r"\b(\d{1,4}\s*(?:CE|AD|BCE|BC)\b)", text)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    first = re.split(r"(?<=[.!?])\s+", text.strip())
    return first[0].strip()[:300] if first and first[0].strip() else ""


class LocalDocsConnector(Connector):
    """Registered name: `local_docs`."""

    name = "local_docs"
    categories: Optional[Sequence[TaskType]] = [TaskType.REASONING, TaskType.UNKNOWN]

    def __init__(
        self,
        source_dir: Optional[str] = None,
        name: str = "local-docs",
        chunk_size: int = 3,
        match_threshold: float = 0.35,
        reliability: float = 0.8,
        categories: Optional[Sequence[TaskType]] = None,
    ):
        raw = source_dir or os.getenv("LOCAL_DOCS_DIR") or "./retrieval_corpus"
        if raw.startswith("${"):
            # Unexpanded env placeholder (var unset) -> fall back to repo-local default
            raw = os.getenv("LOCAL_DOCS_DIR") or "./retrieval_corpus"
        p = Path(raw)
        if not p.is_absolute():
            candidate = Path.cwd() / raw
            p = candidate if candidate.exists() else Path(__file__).parent.parent.parent / raw
        self.source_dir = p
        self.name = name
        self.chunk_size = int(chunk_size)
        self.match_threshold = float(match_threshold)
        self.reliability = float(reliability)
        if categories is not None:
            self.categories = categories
        self._cache: Dict[str, tuple] = {}
        self._index: Optional[List[tuple]] = None  # (path, chunk)

    def _load_index(self) -> List[tuple]:
        if self._index is not None:
            return self._index
        docs: List[tuple] = []
        if self.source_dir.exists():
            for fp in sorted(self.source_dir.rglob("*")):
                if fp.suffix.lower() not in (".txt", ".md"):
                    continue
                try:
                    text = fp.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for ch in _chunks(text, self.chunk_size):
                    docs.append((str(fp), ch))
        self._index = docs
        return docs

    def get_claims(self, question: str) -> List[SourceClaim]:
        norm = question.strip().lower()
        cached = self._cache.get(norm)
        if cached and cached[0] > time.time():
            return cached[1]
        claims = self._search(question)
        self._cache[norm] = (time.time() + (3600 if claims else 120), claims)
        return claims

    def _search(self, question: str) -> List[SourceClaim]:
        q_set = set(_significant(_tokens(question)))
        if not q_set:
            return []
        best, best_score, best_path = None, 0.0, ""
        for path, chunk in self._load_index():
            sig = set(_significant(_tokens(chunk)))
            if not sig:
                continue
            score = len(q_set & sig) / max(len(q_set), 1)
            if score > best_score:
                best, best_score, best_path = chunk, score, path
        if best is None or best_score < self.match_threshold:
            return []
        ans = _extract_answer(best)
        if not ans:
            return []
        return [SourceClaim(
            source=f"local-docs:{Path(best_path).name}",
            answer=ans,
            reliability=self.reliability,
            independent=True,
            reason=f"lexical overlap {best_score:.2f}",
        )]
