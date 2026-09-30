"""Standalone verified + procedure memory. No external imports.

Persists ``question -> answer + trace`` with provenance to a single JSON file
(atomic replace). Lookup order: exact match -> backend signature identity
(prevents near-duplicate blur, e.g. handshake 47 vs 100) -> stoplist-filtered
token overlap above threshold.

Procedure reuse (L1): a stored reasoning skeleton (``procedure_sig``: trace
with numbers stripped) is reused for new numbers via a backend's
detect/solve — knowledge changes, reasoning stays.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Dict, List, Optional

# Generic words that carry no discrimination signal.
STOPWORDS = {
    "what", "does", "this", "the", "a", "an", "is", "of", "in", "on", "to",
    "and", "or", "for", "python", "code", "output", "print", "result", "with",
    "that", "from", "by", "its", "it", "if", "you", "can", "tell", "me",
    "about", "how", "much", "many", "which", "when", "who", "are", "was",
    "were", "be", "their", "they", "not", "do", "does", "did", "these", "those",
    "please", "question", "answer", "solve", "given", "following", "below",
}


def _tokens(s: str) -> List[str]:
    return re.findall(r"[a-z][a-z0-9']*", s.lower())


def _significant(tokens: List[str]) -> List[str]:
    return [t for t in tokens if t not in STOPWORDS]


def _procedure_sig(trace: str) -> str:
    """Hash of the trace skeleton (numbers stripped): same reasoning, new numbers -> same sig."""
    skeleton = re.sub(r"\d+", "N", trace.strip().lower())
    skeleton = re.sub(r"\s+", " ", skeleton)
    return hashlib.sha256(skeleton.encode()).hexdigest()[:16]


class ProcedureStore:
    """VerifiedMemory-compatible store with trace support. Drop-in for Router memory."""

    def __init__(self, path=None, similarity_threshold: float = 0.85):
        self.path = Path(path) if path else Path("./data/verified_memory.json")
        self.similarity_threshold = float(similarity_threshold)
        self.entries: Dict[str, dict] = {}
        self.load()

    # -- persistence ----------------------------------------------------
    def load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                if isinstance(data, dict):
                    self.entries = data
            except (ValueError, OSError):
                self.entries = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.entries, indent=2, ensure_ascii=False))
        tmp.replace(self.path)

    def size(self) -> int:
        return len(self.entries)

    @staticmethod
    def normalize(question: str) -> str:
        return re.sub(r"\s+", " ", question.strip().lower())

    # -- write ----------------------------------------------------------
    def remember(
        self,
        question: str,
        answer: str,
        source: str = "ground-truth",
        tier: str = "executor",
        confidence: float = 1.0,
        reliability: float = 1.0,
        sources: Optional[list] = None,
        disagreement: Optional[list] = None,
        verified: bool = True,
        trace: Optional[str] = None,
        procedure_sig: Optional[str] = None,
        signature: Optional[str] = None,
    ) -> None:
        key = self.normalize(question)
        if not key or not answer:
            return
        import time as _time
        existing = self.entries.get(key) or {}
        self.entries[key] = {
            "question": question,
            "answer": answer,
            "tier": tier,
            "confidence": float(confidence),
            "reliability": float(reliability),
            "sources": sources if sources is not None else [{"name": source, "reliability": reliability}],
            "disagreement": disagreement if disagreement is not None else [],
            "signature": signature if signature is not None else existing.get("signature"),
            "trace": trace if trace is not None else existing.get("trace"),
            "procedure_sig": procedure_sig or (_procedure_sig(trace) if trace else existing.get("procedure_sig")),
            "verified": verified,
            "hits": (existing.get("hits", 0) + 1),
            # Learning counters survive re-remember (never reset: monotonic ratchet).
            "attempts": existing.get("attempts", 0),
            "successes": existing.get("successes", 0),
            "first_seen": existing.get("first_seen", _time.time()),
            "last_hit": _time.time(),
        }
        self.save()

    def remember_trace(self, question: str, trace: str, answer: str, **kwargs) -> None:
        self.remember(question, answer, trace=trace, procedure_sig=_procedure_sig(trace), **kwargs)

    def record_outcome(self, question: str, success: bool) -> None:
        """Register a verified outcome for a stored entry (learning signal)."""
        import time as _time
        key = self.normalize(question)
        entry = self.entries.get(key)
        if entry is None:
            return
        entry["attempts"] = entry.get("attempts", 0) + 1
        if success:
            entry["successes"] = entry.get("successes", 0) + 1
        entry["last_hit"] = _time.time()
        self.save()

    @staticmethod
    def success_rate(entry: dict) -> Optional[float]:
        attempts = entry.get("attempts", 0)
        if not attempts:
            return None
        return round(entry.get("successes", 0) / attempts, 3)

    def prune(self, min_rate: float = 0.3, min_attempts: int = 5,
              max_age_days: Optional[float] = None) -> int:
        """Drop procedures proven bad (low success over enough attempts) or stale.

        Returns the number of removed entries. Never touches entries without
        outcome history — no data, no execution.
        """
        import time as _time
        now = _time.time()
        doomed = []
        for key, entry in self.entries.items():
            attempts = entry.get("attempts", 0)
            if attempts >= min_attempts:
                rate = (entry.get("successes", 0) / attempts) if attempts else 1.0
                if rate < min_rate:
                    doomed.append(key)
                    continue
            if max_age_days is not None:
                last = entry.get("last_hit") or entry.get("first_seen") or now
                if (now - last) > max_age_days * 86400:
                    doomed.append(key)
        for key in doomed:
            del self.entries[key]
        if doomed:
            self.save()
        return len(doomed)

    def bump(self, question: str) -> None:
        key = self.normalize(question)
        if key in self.entries:
            self.entries[key]["hits"] = self.entries[key].get("hits", 0) + 1
            self.save()

    # -- read -----------------------------------------------------------
    def lookup(self, question: str, signature: Optional[str] = None) -> Optional[dict]:
        key = self.normalize(question)
        if key and key in self.entries:
            self.bump(question)
            return self.entries[key]
        # Signature-aware path: identical (op, operands) only, else no match.
        if signature is not None:
            for entry in self.entries.values():
                if entry.get("signature") and entry["signature"] == signature:
                    self.bump(question)
                    return entry
            return None
        # Token-overlap path for plain rephrases.
        q_sig = _significant(_tokens(question))
        if not q_sig:
            return None
        best, best_score = None, 0.0
        for entry in self.entries.values():
            e_sig = _significant(_tokens(entry.get("question", "")))
            if not e_sig:
                continue
            overlap = len(set(q_sig) & set(e_sig)) / max(len(set(q_sig)), 1)
            if overlap > best_score:
                best, best_score = entry, overlap
        if best is not None and best_score >= self.similarity_threshold:
            self.bump(question)
            return best
        return None

    def lookup_procedure(self, skeleton: str) -> Optional[dict]:
        sig = _procedure_sig(skeleton)
        for entry in self.entries.values():
            if entry.get("procedure_sig") == sig:
                return entry
        return None

    # -- L1 procedure reuse ----------------------------------------------
    def resolve_via_procedure(self, question: str, backends: Optional[list] = None) -> Optional[dict]:
        """Reuse a stored reasoning skeleton for NEW numbers via any backend.

        Returns {answer, trace, pattern, args, procedure_sig, sources, reused}
        or None. ``reused`` is True only when the pattern was seen before
        (a stored entry carries the same pattern or procedure_sig family).
        """
        for backend in backends or []:
            try:
                detected = backend.detect(question) if hasattr(backend, "detect") else None
                solved = backend.solve(question)
                if solved is None or solved.answer is None:
                    continue
                pattern = (solved.pattern or (detected[0] if detected else None) or solved.tier)
                args = solved.args or (detected[1] if detected else None) or {}
                trace = solved.trace or f"{pattern} {args} -> {solved.answer}"
                sig = _procedure_sig(trace)
                pattern_seen = any(
                    (entry.get("trace") or "").startswith(pattern or "")
                    or (entry.get("procedure_sig") or "") == sig
                    for entry in self.entries.values()
                ) if pattern else False
                return {
                    "answer": solved.answer,
                    "trace": trace,
                    "pattern": pattern,
                    "args": args,
                    "procedure_sig": sig,
                    "sources": [{"name": f"procedure:{pattern}", "reliability": 1.0, "trace": trace}],
                    "reused": bool(pattern_seen),
                }
            except Exception:
                continue
        return None
