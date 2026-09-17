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
