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


# Self-veto policy: enough attempts with a bad rate quarantines the entry.
# Quarantine is not deletion — the entry stays auditable but is never served.
VETO_MIN_ATTEMPTS = 3
VETO_MAX_FAILURE_RATE = 0.5


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
            # Quarantine survives re-archive: a bad answer is never resurrected
            # by a later remember() of the same question.
            "status": existing.get("status", "active"),
            "quarantine_reason": existing.get("quarantine_reason"),
            "quarantined_at": existing.get("quarantined_at"),
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
        """Register a verified outcome for a stored entry (learning signal).

        Self-veto: with enough evidence at a bad rate the entry is quarantined
        immediately, so a proven-wrong answer stops being served without
        waiting for a manual prune.
        """
        import time as _time
        key = self.normalize(question)
        entry = self.entries.get(key)
        if entry is None:
            return
        entry["attempts"] = entry.get("attempts", 0) + 1
        if success:
            entry["successes"] = entry.get("successes", 0) + 1
        entry["last_hit"] = _time.time()
        rate = self.success_rate(entry)
        if (rate is not None and entry["attempts"] >= VETO_MIN_ATTEMPTS
                and (1.0 - rate) > VETO_MAX_FAILURE_RATE
                and entry.get("status") != "quarantined"):
            self.quarantine(question, reason=f"self-veto: {entry['successes']}/"
                                            f"{entry['attempts']} successes")
            return
        self.save()

    # -- quarantine (integrity) -----------------------------------------
    def quarantine(self, question: str, reason: str = "failed verification") -> bool:
        """Stop serving an entry. Kept on disk for audit; never returned."""
        import time as _time
        entry = self.entries.get(self.normalize(question))
        if entry is None:
            return False
        entry["status"] = "quarantined"
        entry["quarantine_reason"] = reason
        entry["quarantined_at"] = _time.time()
        self.save()
        return True

    def requalify(self, question: str) -> bool:
        """Explicit human/measured rehabilitation (never automatic)."""
        entry = self.entries.get(self.normalize(question))
        if entry is None:
            return False
        entry["status"] = "active"
        entry["quarantine_reason"] = None
        entry["quarantined_at"] = None
        self.save()
        return True

    @staticmethod
    def is_servable(entry: dict) -> bool:
        return entry.get("status", "active") != "quarantined"

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
        outcome history — no data, no execution. Quarantined entries are
        already unservable, so they are dropped here too.
        """
        import time as _time
        now = _time.time()
        doomed = []
        for key, entry in self.entries.items():
            if entry.get("status") == "quarantined":
                doomed.append(key)
                continue
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

    def compact(self, max_per_sig: int = 3) -> int:
        """Bound one-off instance growth: keep at most N exemplars per procedure.

        A `procedure_sig` is the generalisation; extra operand instances add no
        truth (the oracle recomputes them for free) and grow the store without
        limit (measured 2026-11-14: 93/322 entries were dead one-off instances,
        immune to prune()). Only untested entries are dropped — anything with
        outcome history is evidence and stays.
        """
        groups: Dict[str, list] = {}
        for key, entry in self.entries.items():
            sig = entry.get("procedure_sig")
            if not sig or entry.get("attempts", 0) > 0:
                continue
            groups.setdefault(sig, []).append(key)
        doomed = []
        for sig, keys in groups.items():
            if len(keys) <= max_per_sig:
                continue
            keys.sort(key=lambda k: self.entries[k].get("last_hit")
                      or self.entries[k].get("first_seen") or 0, reverse=True)
            doomed.extend(keys[max_per_sig:])
        for key in doomed:
            del self.entries[key]
        if doomed:
            self.save()
        return len(doomed)

    def summary(self) -> dict:
        """Audit counters: what is in the store and what is unservable."""
        out = {"total": len(self.entries), "active": 0, "quarantined": 0,
               "with_sig": 0, "without_sig": 0, "tested": 0, "untested": 0,
               "by_tier": {}}
        for entry in self.entries.values():
            if self.is_servable(entry):
                out["active"] += 1
            else:
                out["quarantined"] += 1
            if entry.get("procedure_sig"):
                out["with_sig"] += 1
            else:
                out["without_sig"] += 1
            if entry.get("attempts", 0) > 0:
                out["tested"] += 1
            else:
                out["untested"] += 1
            tier = entry.get("tier") or "unknown"
            out["by_tier"][tier] = out["by_tier"].get(tier, 0) + 1
        return out

    def bump(self, question: str) -> None:
        key = self.normalize(question)
        if key in self.entries:
            self.entries[key]["hits"] = self.entries[key].get("hits", 0) + 1
            self.save()

    # -- read -----------------------------------------------------------
    def lookup(self, question: str, signature: Optional[str] = None) -> Optional[dict]:
        key = self.normalize(question)
        if key and key in self.entries:
            entry = self.entries[key]
            if self.is_servable(entry):
                self.bump(question)
                return entry
        # Signature-aware path: identical (op, operands) only, else no match.
        if signature is not None:
            for entry in self.entries.values():
                if not self.is_servable(entry):
                    continue
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
            if not self.is_servable(entry):
                continue
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
            if not self.is_servable(entry):
                continue
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
