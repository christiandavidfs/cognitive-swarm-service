"""Juicio 3 · adjudicate-on-conflict — dual-judge consensus behind the seat.

Why: with two independent judges in the escalation ladder, DISAGREEMENT is a
measurable signal, not noise. This seat makes it actionable:

  both agree (confident)      → consensus, confidence = min(a, b) (conservative,
                                 never fabricated confidence inflation)
  conflict or one is unknown  → arbiter (high-consequence seat: Jev TypeSafe)
  arbiter unavailable/fails   → deterministic heuristic regex (loud, safe —
                                 the ground layer that never breaks routing)
  one judge errored           → the surviving judge's answer alone (its own
                                 fallback rules already applied)

Default OFF (`JUDGE_ADJUDICATE=1` to enable) — architecture freeze: this is
the Fase A spike, promoted only if the pilot shows the ensemble's final-error
≤ single-judge error at meaningful coverage.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from service.contracts import TaskType
from .classify import _heuristic_classify
from .primitives import Judgment

logger = logging.getLogger(__name__)


@dataclass
class Adjudication:
    task_type: TaskType
    judgment: Judgment
    source: str          # "consensus" | "secondary" | "arbiter" | "heuristic" | "primary"
    disagreement: bool   # True when judges conflicted and someone was consulted
    escalated: bool      # True when the arbiter seat was invoked


def _call(fn, question: str):
    """Run a judge fn; a judge that fails never takes down the tier."""
    try:
        return fn(question)
    except Exception as e:
        logger.debug("judge %s failed: %s", getattr(fn, "__name__", fn), e)
        return None


def _load_judge_fn(name: str):
    """Resolve a judge backend name to its classify fn. Unknown name → None."""
    if name == "laya":
        from . import laya
        return laya.classify_question
    if name == "jev":
        from . import jev
        return jev.classify_question
    if name == "heuristic":
        return _heuristic_classify
    return None


def adjudicated_classify(question: str,
                         primary_name: str = "laya",
                         secondary_name: str = None,
                         arbiter_name: str = None) -> Adjudication:
    """Juicio 1 + Juicio 3 in one pass. Env overrides:
      LAYA_SECONDARY (default 'jev' = local Kev / managed Jev endpoint)
      LAYA_ARBITER   (default 'jev')"""
    secondary_name = secondary_name or os.getenv("LAYA_SECONDARY", "jev")
    arbiter_name = arbiter_name or os.getenv("LAYA_ARBITER", "jev")

    primary = _load_judge_fn(primary_name)
    secondary = _load_judge_fn(secondary_name)
    p = _call(primary, question) if primary else None
    s = _call(secondary, question) if secondary else None

    # Both alive and agreeing with confidence → consensus (conservative min-conf)
    if p and s and not p[1].unknown and not s[1].unknown and p[0] == s[0]:
        conf = min(p[1].confidence, s[1].confidence)
        consensus = Judgment(kind="choice", choice=p[1].choice, probs=p[1].probs,
                             confidence=conf, unknown=False)
        return Adjudication(p[0], consensus, source="consensus",
                            disagreement=False, escalated=False)

    # One judge down, the other alive with a confident answer → single-source
    # result. No disagreement exists, so the arbiter seat must NOT fire.
    if p and not p[1].unknown and s is None:
        return Adjudication(p[0], p[1], source="primary", disagreement=False,
                            escalated=False)
    if s and not s[1].unknown and p is None:
        return Adjudication(s[0], s[1], source="secondary", disagreement=False,
                            escalated=False)

    # Both unknown (or both dead) → unknown, no escalation theater
    if (p is None or p[1].unknown) and (s is None or s[1].unknown):
        if p and p[1].unknown:
            return Adjudication(p[0], p[1], source="primary", disagreement=False,
                                escalated=False)
        if s and s[1].unknown:
            return Adjudication(s[0], s[1], source="secondary", disagreement=False,
                                escalated=False)
        return Adjudication(TaskType.UNKNOWN, Judgment(kind="choice", choice=None,
                            probs={}, confidence=0.0, unknown=True),
                            source="heuristic", disagreement=False, escalated=False)

    # Conflict (or one-unknown disagreement) → Juicio 3: arbiter decides
    arbiter = _load_judge_fn(arbiter_name)
    a = _call(arbiter, question) if arbiter else None
    if a is not None:
        return Adjudication(a[0], a[1], source="arbiter", disagreement=True,
                            escalated=True)

    # Arbiter down → deterministic heuristic ground layer (loud, safe)
    h = _heuristic_classify(question)
    return Adjudication(h[0], h[1], source="heuristic", disagreement=True,
                        escalated=False)
