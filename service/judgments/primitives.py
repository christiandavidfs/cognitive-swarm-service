"""Judgment primitives — Choice / Score / Noul with calibrated-style outputs.

Heuristic backend (Fase 2): same decisions the router made before, now behind
the seam a model like Jev will implement. Every primitive returns a
distribution + confidence derived from concentration, plus an explicit
`unknown` route — probabilities must never be forced onto broken options.

A Jev-backed implementation will drop into `service/judgments/jev.py` behind
`load_judge()` without touching callers.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Judgment:
    kind: str  # "choice" | "score" | "noul"
    choice: Optional[str] = None
    probs: Dict[str, float] = field(default_factory=dict)
    score: Optional[float] = None
    confidence: float = 0.0
    unknown: bool = False  # True when no option earned the mass (broken question route)


def _normalize(scores: Dict[str, float]) -> Dict[str, float]:
    total = sum(max(0.0, v) for v in scores.values())
    if total <= 0:
        n = max(len(scores), 1)
        return {k: 1.0 / n for k in scores}
    return {k: max(0.0, v) / total for k, v in scores.items()}


def _concentration(probs: Dict[str, float]) -> float:
    """Confidence from distribution shape: 0 (flat) → 1 (peaked)."""
    n = len(probs)
    if n <= 1:
        return 1.0
    entropy = -sum(p * math.log(p) for p in probs.values() if p > 0)
    return round(1.0 - entropy / math.log(n), 3)


def choose(scores: Dict[str, float], unknown_threshold: float = 0.15) -> Judgment:
    """Pick from declared alternatives. `unknown` when top mass is too weak
    or there was no positive signal at all (flat by default, not by evidence)."""
    has_signal = sum(max(0.0, v) for v in scores.values()) > 0
    probs = _normalize(scores)
    top = max(probs, key=probs.get) if probs else None
    conf = _concentration(probs)
    unknown = (not has_signal) or top is None or probs[top] < unknown_threshold
    return Judgment(kind="choice", choice=None if unknown else top,
                    probs=probs, confidence=conf, unknown=unknown)


def score_judgment(level_scores: Dict[str, float]) -> Judgment:
    """Ordered levels → continuous score in [0,1] + distribution + confidence."""
    probs = _normalize(level_scores)
    levels = sorted(probs.keys())
    score = round(sum(i / max(len(levels) - 1, 1) * probs[lvl] for i, lvl in enumerate(levels)), 3)
    return Judgment(kind="score", probs=probs, score=score, confidence=_concentration(probs))


def noul(prob_true: float) -> Judgment:
    """Binary proposition → P(true), clipped to [0,1]."""
    p = max(0.0, min(1.0, float(prob_true)))
    conf = round(abs(p - 0.5) * 2, 3)  # distance from maximal uncertainty
    return Judgment(kind="noul", probs={"true": p, "false": 1.0 - p}, confidence=conf)
