"""Juicio 3 · adjudicate-on-conflict — dual-judge consensus behind the seat.

Two independent judges turn DISAGREEMENT into signal:

  both agree (confident)      → consensus, confidence = min (never inflate)
  one judge down              → survivor decides alone (no disagreement exists)
  both unknown/dead           → unknown, no escalation theater
  conflict                    → arbiter (high-consequence seat); arbiter down
                                → deterministic heuristic ground layer (loud, safe)

Default OFF (`JUDGE_ADJUDICATE=1` to enable). Judges resolved by name
(heuristic | jev | laya); unknown names resolve to None (safe skip).
A judge that fails never takes down the tier.
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
    source: str          # "consensus" | "primary" | "secondary" | "arbiter" | "heuristic"
    disagreement: bool   # True when judges conflicted and someone was consulted
    escalated: bool      # True when the arbiter seat was invoked


def _call(fn, question: str):
    try:
        return fn(question)
    except Exception as e:
        logger.debug("judge %s failed: %s", getattr(fn, "__name__", fn), e)
        return None


def _load_judge_fn(name: str):
    if name == "laya":
        from . import laya
        return laya.classify_question
    if name == "jev":
        from . import jev
        return jev.classify_question
    if name == "heuristic":
        return _heuristic_classify
    return None


def adjudicated_classify(question: str, primary_name: str = "heuristic",
                         secondary_name: str = None,
                         arbiter_name: str = None) -> Adjudication:
    """Env overrides: JUDGE_PRIMARY, JUDGE_SECONDARY (default jev), JUDGE_ARBITER (default jev)."""
    secondary_name = secondary_name or os.getenv("JUDGE_SECONDARY", "jev")
    arbiter_name = arbiter_name or os.getenv("JUDGE_ARBITER", "jev")

    primary = _load_judge_fn(primary_name)
    secondary = _load_judge_fn(secondary_name)
    p = _call(primary, question) if primary else None
    s = _call(secondary, question) if secondary else None

    if p and s and not p[1].unknown and not s[1].unknown and p[0] == s[0]:
        conf = min(p[1].confidence, s[1].confidence)
        consensus = Judgment(kind="choice", choice=p[1].choice, probs=p[1].probs,
                             confidence=conf, unknown=False)
        return Adjudication(p[0], consensus, source="consensus",
                            disagreement=False, escalated=False)

    if p and not p[1].unknown and s is None:
        return Adjudication(p[0], p[1], source="primary", disagreement=False, escalated=False)
    if s and not s[1].unknown and p is None:
        return Adjudication(s[0], s[1], source="secondary", disagreement=False, escalated=False)

    if (p is None or p[1].unknown) and (s is None or s[1].unknown):
        if p and p[1].unknown:
            return Adjudication(p[0], p[1], source="primary", disagreement=False, escalated=False)
        if s and s[1].unknown:
            return Adjudication(s[0], s[1], source="secondary", disagreement=False, escalated=False)
        return Adjudication(TaskType.UNKNOWN, Judgment(kind="choice", choice=None,
                            probs={}, confidence=0.0, unknown=True),
                            source="heuristic", disagreement=False, escalated=False)

    arbiter = _load_judge_fn(arbiter_name)
    a = _call(arbiter, question) if arbiter else None
    if a is not None:
        return Adjudication(a[0], a[1], source="arbiter", disagreement=True, escalated=True)

    h = _heuristic_classify(question)
    return Adjudication(h[0], h[1], source="heuristic", disagreement=True, escalated=False)
