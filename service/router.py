"""Service-owned truth hierarchy. No external imports.

  Tier 0  memory (exact -> signature -> similarity)
  L1      procedure reuse is handled by the caller (app) via the store
  Tiers   resolver backends in order (deterministic, zero or more)
  Tier 3  retrieval: category-gated connectors -> corroboration
  Tier 4  none -> caller falls back to async debate jobs

With no backends installed the service still serves memory + retrieval.
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional

from .contracts import Connector, Resolution, ResolverBackend, SourceClaim, TaskType
from .corroboration import Corroborator

logger = logging.getLogger(__name__)

_CODE_MARKERS = ("print(", "def ", "import ", "```", "sorted(", "len(")
_MATH_RE = re.compile(r"\d\s*[-+*/^%]\s*\d|\d\s*(?:plus|minus|times|divided by)\s*\w+")


def classify_local(question: str) -> TaskType:
    """Heuristic classifier used when no backend classifies (or as fallback)."""
    q = question.lower()
    if any(m in q for m in _CODE_MARKERS):
        return TaskType.CODE
    if _MATH_RE.search(q):
        return TaskType.MATH
    return TaskType.UNKNOWN


def has_math_structure(question: str) -> bool:
    """Fuzzy lexical retrieval misfires on math-shaped text — refuse it there."""
    return bool(_MATH_RE.search(question.lower()))


class Router:
    def __init__(self, memory=None, corroborator: Optional[Corroborator] = None,
                 retrievers: Optional[List[Connector]] = None,
                 backends: Optional[List[ResolverBackend]] = None,
                 director=None, families=None):
        self.memory = memory
        self.corroborator = corroborator or Corroborator()
        self.retrievers: List[Connector] = list(retrievers or [])
        self.backends: List[ResolverBackend] = list(backends or [])
        if director is None:
            try:
                from .orchestrator import Director
                director = Director()
            except Exception:
                director = None
        self.director = director
        if families is None:
            try:
                from .memory.families import FamilyStore
                families = FamilyStore()
            except Exception:
                families = None
        self.families = families

    def classify(self, question: str) -> TaskType:
        for backend in self.backends:
            try:
                t = backend.classify(question)
                if t != TaskType.UNKNOWN:
                    return t
            except Exception:
                continue
        # Juicio 1 via the judgments seam (heuristic now, Jev later).
        try:
            from .judgments import classify_question
            t, _judgment = classify_question(question)
            if t != TaskType.UNKNOWN:
                return t
        except Exception:
            pass
        return classify_local(question)

    def _signature(self, question: str) -> Optional[str]:
        for backend in self.backends:
            try:
                sig = backend.signature(question)
                if sig:
                    return sig
            except Exception:
                continue
        return None

    def resolve(self, question: str) -> Resolution:
        # Tier 0: memory (signature-aware so near-duplicates never blur).
        if self.memory is not None:
            rec = self.memory.lookup(question, signature=self._signature(question))
            if rec is not None:
                return Resolution(
                    answer=rec["answer"], confidence=rec.get("confidence", 1.0),
                    status="memory", tier=rec.get("tier", "memory"),
                    sources=rec.get("sources", []),
                    disagreement=rec.get("disagreement", []),
                )

        task_type = self.classify(question)

        # Group: emergent family when recognized, else task type as prior.
        # Types are hints; families are measured. Unknown + unrecognized stays
        # ungrouped (genuinely new) and is observed for future condensation.
        group = self._group_for(question, task_type)

        # Director orders backends (stats policy; signal-free → config order).
        backends = self._order_backends(group)

        # Deterministic backends in order.
        for backend in backends:
            try:
                ans = backend.solve(question)
            except Exception:
                continue
            if ans is not None and ans.answer is not None:
                self._observe_solve(question, task_type, backend.name, ans)
                if self.memory is not None:
                    try:
                        self.memory.remember(
                            question, ans.answer, source=backend.name,
                            tier=ans.tier, confidence=ans.confidence,
                            trace=ans.trace,
                            signature=self._signature(question),
                        )
                    except Exception:
                        pass
                return Resolution(
                    ans.answer, ans.confidence, ans.tier, ans.tier,
                    sources=[{"name": f"{backend.name}:{ans.tier}", "reliability": 1.0}],
                )

        # Tier 3: retrieval refused on math-shaped questions.
        if has_math_structure(question):
            return Resolution(None, 0.0, "none", "debate", sources=[],
                              disagreement=[{"answer": "math-structured question; retrieval refused",
                                             "sources": ["local-docs"], "reliability": 0.0}])

        claims = self._collect_claims(question, task_type)
        if claims:
            verdict = self.corroborator.corroborate(claims)
            if verdict.status == "corroborated":
                self._record_routing("retrieval", group, True)
                if self.memory is not None:
                    try:
                        self.memory.remember(
                            question, verdict.answer, source="retrieval", tier="retrieval",
                            confidence=verdict.confidence, reliability=verdict.reliability,
                            sources=verdict.provenance, disagreement=verdict.disagreement,
                        )
                    except Exception:
                        pass
                return Resolution(verdict.answer, verdict.confidence, "retrieval", "retrieval",
                                  sources=verdict.provenance, disagreement=verdict.disagreement)
            self._record_routing("retrieval", group, False)
            sources = [{"name": cl["sources"], "reliability": cl["best_reliability"]}
                       for cl in verdict.clusters.values()]
            return Resolution(None, verdict.confidence, "retrieval", "conflict",
                              sources=sources, disagreement=verdict.disagreement)

        return Resolution(None, 0.0, "none", "debate")

    def _group_for(self, question: str, task_type: TaskType) -> str:
        if self.families is not None:
            try:
                rec = self.families.recognize(question)
                if rec["family"] is not None:
                    return rec["family"]
            except Exception:
                pass
        return task_type.value if isinstance(task_type, TaskType) else str(task_type)

    def _observe_solve(self, question: str, task_type: TaskType, layer: str, ans) -> None:
        sig = None
        try:
            sig = self._signature(question)
        except Exception:
            pass
        group = task_type.value if isinstance(task_type, TaskType) else str(task_type)
        if self.families is not None:
            try:
                fam = self.families.observe(question, getattr(ans, "pattern", None), sig, True)
                if fam:
                    group = fam
            except Exception:
                pass
        self._record_routing(layer, group, True)

    def _order_backends(self, group: str) -> list:
        if self.director is None:
            return list(self.backends)
        try:
            names = [b.name for b in self.backends]
            ordered = self.director.order(names, group)
            by_name = {b.name: b for b in self.backends}
            return [by_name[n] for n in ordered if n in by_name]
        except Exception:
            return list(self.backends)

    def _record_routing(self, layer: str, group: str, success: bool) -> None:
        if self.director is None:
            return
        try:
            self.director.record(layer, group, success)
        except Exception:
            pass

    def verify_candidate(self, question: str, candidate: str) -> bool:
        for backend in self.backends:
            try:
                if backend.verify(question, candidate):
                    return True
            except Exception:
                continue
        return False

    def _collect_claims(self, question: str, task_type: Optional[TaskType]) -> List[SourceClaim]:
        claims: List[SourceClaim] = []
        for retriever in self.retrievers:
            try:
                if not retriever.applies_to(task_type):
                    continue
                claims.extend(retriever.get_claims(question))
            except Exception:
                continue
        return claims
