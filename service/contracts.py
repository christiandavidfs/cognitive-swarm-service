"""Service-owned contracts — the service repo depends on nothing but itself.

Every backend (cognitive-swarm, Jev, LLMs, ...) adapts to these types; every
connector implements :class:`Connector`. Field names mirror the original core
so adapters are trivial, but nothing here imports outside this repo.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence


class TaskType(str, Enum):
    REASONING = "reasoning"
    MATH = "math"
    CODE = "code"
    UNKNOWN = "unknown"


@dataclass
class SourceClaim:
    source: str
    answer: str
    reliability: float = 0.5
    independent: bool = True
    reason: str = ""


@dataclass
class Verdict:
    status: str  # "corroborated" | "conflict" | "uncertain"
    answer: Optional[str]
    confidence: float
    reliability: float
    clusters: Dict[str, dict] = field(default_factory=dict)
    disagreement: List[dict] = field(default_factory=list)
    provenance: List[dict] = field(default_factory=list)


@dataclass
class Resolution:
    """Structured answer: never a bare atom; always carries provenance."""
    answer: Optional[str]
    confidence: float
    status: str  # memory|executor|calculator|retrieval|debate|none (+ * primitives)
    tier: str
    sources: List[dict] = field(default_factory=list)
    disagreement: List[dict] = field(default_factory=list)


@dataclass
class BackendAnswer:
    """Deterministic answer from a resolver backend (Tiers 0-2 equivalent)."""
    answer: str
    tier: str
    confidence: float = 1.0
    pattern: Optional[str] = None
    args: Optional[dict] = None
    trace: Optional[str] = None


class Connector(ABC):
    """A single source from a question to candidate claims.

    ``categories`` gates retrieval: the router only queries a connector whose
    categories match the question's category (``None`` = any). One failing
    connector never takes down the tier — the router catches exceptions.
    """

    name: str = "connector"
    categories: Optional[Sequence[TaskType]] = None

    def applies_to(self, task_type: Optional[TaskType]) -> bool:
        if not self.categories:
            return True
        return task_type in self.categories

    @abstractmethod
    def get_claims(self, question: str) -> List[SourceClaim]:
        """Return the claims this source supports for the question."""

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<{type(self).__name__} {self.name!r} categories={self.categories}>"


class ResolverBackend(ABC):
    """Optional deterministic backend (Tier 0-2 equivalent). Zero or more.

    The service works with no backends (memory + retrieval still serve); each
    configured backend is tried in order until one solves the question.
    """

    name: str = "backend"

    @abstractmethod
    def classify(self, question: str) -> TaskType:
        """Classify the question; UNKNOWN when unsure."""

    @abstractmethod
    def solve(self, question: str) -> Optional[BackendAnswer]:
        """Deterministically solve, or None when not solvable here."""

    def signature(self, question: str) -> Optional[str]:
        """Stable (op, operands) signature to prevent near-duplicate blur."""
        return None

    def detect(self, question: str):
        """Optional (pattern, args) detection for procedure reuse. Default: none."""
        return None

    def verify(self, question: str, candidate: str) -> bool:
        """Confirm a candidate against ground-truth checks. Default: no."""
        return False
