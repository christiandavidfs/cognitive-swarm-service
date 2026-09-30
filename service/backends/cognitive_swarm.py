"""Optional adapter: cognitive-swarm core as one resolver backend among many.

All core imports live inside this module and are lazy — if the package is not
installed, :func:`available` returns False and the service simply runs without
deterministic tiers (memory + retrieval still serve). The service never imports
this module unless ``cognitive_swarm`` resolves.
"""
from __future__ import annotations

import logging
from typing import Optional

from service.contracts import BackendAnswer, ResolverBackend, TaskType

logger = logging.getLogger(__name__)


def available() -> bool:
    try:
        import cognitive_swarm  # noqa: F401
        return True
    except Exception:
        return False


class _WriteThroughShim:
    """Core-facing memory: reads always miss, writes forward with signature.

    The service Router already checked Tier 0 (signature-aware) before the
    backend runs, so a core-side hit could only be a blur. Writes forward to
    the real store with the backend-computed signature attached.
    """

    def __init__(self, backend: "CognitiveSwarmBackend"):
        self._backend = backend

    @property
    def _store(self):
        return self._backend._memory

    def lookup(self, question: str):
        return None

    def remember(self, question: str, answer: str, **kwargs):
        store = self._store
        if store is None:
            return
        try:
            store.remember(question, answer, signature=self._backend.signature(question), **kwargs)
        except Exception:
            pass


class CognitiveSwarmBackend(ResolverBackend):
    """Wraps the core TruthRouter (deterministic tiers only, no retrieval).

    Retrieval stays service-side so all connectors share one gate and one
    corroborator regardless of backend. Memory reads stay service-side too:
    the core gets a write-forwarding shim whose lookup always misses, so the
    core can never blur near-duplicates through signature-less lookup —
    Tier 0 (signature-aware) belongs to the service Router.
    """

    name = "cognitive_swarm"

    def __init__(self, memory=None):
        self._memory = memory
        self._router = None

    def _core_router(self):
        if self._router is None:
            from cognitive_swarm.orchestration.truth_router import TruthRouter
            from cognitive_swarm.orchestration.corroboration import Corroborator
            self._router = TruthRouter(memory=_WriteThroughShim(self), corroborator=Corroborator(), retrievers=[])
        return self._router

    def classify(self, question: str) -> TaskType:
        try:
            from cognitive_swarm.orchestration.prompt_optimizer import PromptOptimizer, TaskType as CoreTask
            t = PromptOptimizer(use_llm=False).optimize(question).task_type
            return TaskType(t.value)
        except Exception:
            return TaskType.UNKNOWN

    def detect(self, question: str):
        try:
            from cognitive_swarm.tools.reasoning_primitives import detect_reasoning_pattern
            return detect_reasoning_pattern(question)
        except Exception:
            return None

    def signature(self, question: str) -> Optional[str]:
        det = self.detect(question)
        if not det:
            return None
        op, args = det
        try:
            return op + ":" + "|".join(f"{k}={v}" for k, v in sorted(args.items()))
        except Exception:
            return op

    def solve(self, question: str) -> Optional[BackendAnswer]:
        try:
            res = self._core_router().resolve(question)
        except Exception as e:
            logger.debug("cognitive-swarm backend solve failed: %s", e)
            return None
        if res.answer is None or res.status in ("none", "retrieval"):
            return None
        pattern = args = trace = None
        if res.tier == "reasoning-primitives":
            try:
                from cognitive_swarm.tools.student_trace import generate_trace, verify_trace
                det = self.detect(question)
                if det:
                    pattern, args = det
                    trace = generate_trace(question, pattern, args, res.answer)
                    if not verify_trace(trace):
                        trace = None
            except Exception:
                pass
        return BackendAnswer(answer=res.answer, tier=res.tier, confidence=res.confidence,
                             pattern=pattern, args=args, trace=trace)

    def verify(self, question: str, candidate: str) -> bool:
        try:
            return bool(self._core_router().verify_candidate(question, candidate))
        except Exception:
            return False
