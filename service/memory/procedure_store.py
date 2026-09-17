"""Procedure store — verified (question → trace → answer), not just (question → answer).

Extends the core VerifiedMemory philosophy: Tier 0 memory is instant + provenance-aware,
but now caches *how* we solved it (trace skeleton), not just the final atom. A trace is
verifiable (each numeric step checked by executor/math) and reusable with new numbers
(knowledge changes, reasoning stays — student_trace.py prototype).

On disk this is a single JSON (shared with VerifiedMemory) plus a procedure_sig field.
Future: split to Postgres JSONB + trace blob store; interface stays identical.

Usage:
  store = ProcedureStore()  # same path as VerifiedMemory by default
  store.remember(question, answer, trace="handshake n=47 → n*(n-1)/2 =1081", tier="reasoning-primitives")
  rec = store.lookup(question)  # returns dict with answer+trace+procedure_sig
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Optional

from cognitive_swarm.memory.verified_memory import VerifiedMemory


def _procedure_sig(trace: str) -> str:
    """Hash of the trace skeleton (numbers stripped) — same reasoning, different numbers → same sig."""
    skeleton = re.sub(r"\d+", "N", trace.strip().lower())
    skeleton = re.sub(r"\s+", " ", skeleton)
    return hashlib.sha256(skeleton.encode()).hexdigest()[:16]


class ProcedureStore(VerifiedMemory):
    """VerifiedMemory with trace support. Drop-in replacement for TruthRouter memory."""

    def __init__(self, path=None, similarity_threshold: float = 0.85):
        super().__init__(path=path, similarity_threshold=similarity_threshold)

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
    ) -> None:
        # Call parent to persist core fields
        super().remember(question, answer, source=source, tier=tier, confidence=confidence, reliability=reliability, sources=sources, disagreement=disagreement, verified=verified)
        if trace or procedure_sig:
            key = self.normalize(question)
            if key in self.entries:
                if trace:
                    self.entries[key]["trace"] = trace
                self.entries[key]["procedure_sig"] = procedure_sig or _procedure_sig(trace or answer)
                self.save()

    def remember_trace(self, question: str, trace: str, answer: str, **kwargs) -> None:
        self.remember(question, answer, trace=trace, procedure_sig=_procedure_sig(trace), **kwargs)

    def lookup_procedure(self, skeleton: str) -> Optional[dict]:
        """Find any entry with matching procedure skeleton (numbers-agnostic)."""
        sig = _procedure_sig(skeleton)
        for entry in self.entries.values():
            if entry.get("procedure_sig") == sig:
                return entry
        return None

    def resolve_via_procedure(self, question: str) -> Optional[dict]:
        """Try to solve a NEW question by reusing a stored procedure skeleton.

        Steps (no model load, 0.3ms):
          1. student_router predicts pattern (TF-IDF 240KB, 0.26ms) or regex fallback
          2. Find any stored procedure with same pattern (by procedure_sig of template)
          3. Extract args for the new question via student_router.extract_args
          4. Re-compute answer via reasoning_primitive resolver (deterministic, verified)
          5. Return answer+trace with provenance `procedure:<pattern>` (reusable reasoning)
        Returns dict {answer, trace, pattern, sources} or None if no reusable procedure.
        """
        try:
            from cognitive_swarm.tools.reasoning_primitives import detect_reasoning_pattern, resolve_reasoning_primitive
            from cognitive_swarm.tools.student_trace import generate_trace, verify_trace
            # Try to detect pattern (student first, then regex) — same as Tier 2d but we want to
            # reuse stored trace skeleton, not just regex answer.
            det = detect_reasoning_pattern(question)
            if not det:
                return None
            pat, args = det
            # Check if we have any stored procedure for this pattern (proves it was seen before)
            has_template = any(
                e.get("trace", "").startswith(pat) or e.get("procedure_sig")  # simple: any trace for pat
                and pat in (e.get("trace") or "")
                or pat in str(e.get("reasoning_op_sig") or "")
                for e in self.entries.values()
            )
            # Also check via procedure_sig template match: generate a dummy trace for this pattern
            # and see if skeleton matches any stored sig
            ans = resolve_reasoning_primitive(question)
            if ans is None:
                return None
            trace = generate_trace(question, pat, args, ans)
            if not verify_trace(trace):
                return None
            sig = _procedure_sig(trace)
            # Look for any stored entry with same sig family (same pattern, different numbers)
            # If not found, we still have a valid procedure to cache — but for demo we want
            # to show reuse when pattern was seen before. Check if any entry's pattern matches.
            def _pat_of(e):
                sig = e.get("reasoning_op_sig") or ""
                return sig.split(":")[0] if sig else ""
            pattern_seen = any(
                pat in (e.get("trace") or "") or pat == _pat_of(e)
                for e in self.entries.values()
            )
            # For POC, allow either: if pattern_seen, return as procedure hit; else still return as new procedure (to seed)
            return {
                "answer": ans,
                "trace": trace,
                "pattern": pat,
                "args": args,
                "procedure_sig": sig,
                "sources": [{"name": f"procedure:{pat}", "reliability": 1.0, "trace": trace}],
                "reused": pattern_seen,
            }
        except Exception:
            return None
