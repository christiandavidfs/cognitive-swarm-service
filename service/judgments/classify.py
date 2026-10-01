"""Juicio 1 · classify — heuristic implementation behind the seam.

Same regexes the router used before (Fase 2 = same results, new seam):
code markers → CODE, arithmetic shape → MATH, else UNKNOWN with the
`unknown` route set. A Jev-backed classifier replaces `classify_question`
without touching the router.
"""
from __future__ import annotations

import os

from service.contracts import TaskType
from .primitives import Judgment, choose

_CODE_MARKERS = ("print(", "def ", "import ", "```", "sorted(", "len(")

import re as _re
_MATH_RE = _re.compile(r"\d\s*[-+*/^%]\s*\d|\d\s*(?:plus|minus|times|divided by)\s*\w+")


def classify_question(question: str) -> tuple:
    """Return (TaskType, Judgment). UNKNOWN comes with unknown=True set.

    `JUDGE=laya` (+ local LAYA_BASE_URL sidecar) routes to the open-weights
    decision model; with JUDGE_ADJUDICATE=1 the dual-judge consensus + Juicio 3
    arbitration wraps it (service/judgments/adjudicate.py, default OFF).
    `JUDGE=jev` (plus TYPESAFE_API_KEY) routes to the Jev-backed classifier;
    any judge failure falls back to heuristics — a judge must never break
    routing.
    """
    judge = os.getenv("JUDGE", "heuristic").lower()
    if judge == "laya":
        if os.getenv("JUDGE_ADJUDICATE") == "1":
            try:
                from .adjudicate import adjudicated_classify
                adj = adjudicated_classify(question)
                return adj.task_type, adj.judgment
            except Exception:
                pass  # fall through — adjudication never breaks routing
        try:
            from .laya import classify_question as _laya_classify
            return _laya_classify(question)
        except Exception:
            pass
    if judge == "jev":
        try:
            from .jev import classify_question as _jev_classify
            return _jev_classify(question)
        except Exception:
            pass
    return _heuristic_classify(question)


def _heuristic_classify(question: str) -> tuple:
    q = question.lower()
    scores = {"code": 0.0, "math": 0.0, "reasoning": 0.0, "unknown": 0.25}
    if any(m in q for m in _CODE_MARKERS):
        scores["code"] = 1.0
    if _MATH_RE.search(q):
        scores["math"] = 1.0 if scores["code"] < 1.0 else 0.4
    j = choose(scores, unknown_threshold=0.4)
    if j.unknown or j.choice in (None, "unknown"):
        import dataclasses as _dc
        j = _dc.replace(j, choice=None, unknown=True)
        return TaskType.UNKNOWN, j
    mapping = {"code": TaskType.CODE, "math": TaskType.MATH, "reasoning": TaskType.REASONING}
    return mapping.get(j.choice, TaskType.UNKNOWN), j
