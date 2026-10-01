"""Per-group temperature calibration — fitted on held-out, never train.

One global temperature (JUDGE_TEMPERATURE) is a blunt instrument: different
decision geometries need different softening. This module fits T per
(question_type, n_options) minimizing NLL, with ECE reporting, and applies
per-group maps at serving time (JUDGE_TEMPERATURES_JSON). Global T remains
as fallback. Choice (argmax) never moves under temperature — only sharpness.
"""
from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from typing import Dict, List, Tuple


def apply_temperature(probs: dict, temperature: float) -> dict:
    if not probs or temperature <= 0:
        return dict(probs)
    shifted = {k: max(0.0, v) ** (1.0 / temperature) for k, v in probs.items()}
    total = sum(shifted.values())
    if total <= 0:
        n = max(len(probs), 1)
        return {k: 1.0 / n for k in probs}
    return {k: v / total for k, v in shifted.items()}


def nll(rows: List[dict], temperature: float) -> float:
    total = 0.0
    for r in rows:
        p = apply_temperature(r["probs"], temperature)
        total -= math.log(max(p.get(r["label"], 0.0), 1e-12))
    return total / max(len(rows), 1)


def ece(rows: List[dict], temperature: float, bins: int = 10) -> float:
    """Expected calibration error after T (confidence = top prob)."""
    bucket: Dict[int, list] = defaultdict(list)
    for r in rows:
        p = apply_temperature(r["probs"], temperature)
        top = max(p, key=p.get)
        bucket[min(int(p[top] * bins), bins - 1)].append((p[top], top == r["label"]))
    n = len(rows)
    return sum(len(v) / n * abs(sum(c for c, _ in v) / len(v) - sum(o for _, o in v) / len(v))
               for v in bucket.values() if v)


def fit(rows: List[dict]) -> float:
    best_t, best_loss = 1.0, nll(rows, 1.0)
    for t in [0.3, 0.5, 0.7, 0.85, 1.0, 1.2, 1.5, 2.0, 3.0, 5.0]:
        loss = nll(rows, t)
        if loss < best_loss:
            best_t, best_loss = t, loss
    lo, hi = max(0.05, best_t / 2), best_t * 2
    for _ in range(20):
        m1, m2 = lo + (hi - lo) / 3, lo + 2 * (hi - lo) / 3
        if nll(rows, m1) < nll(rows, m2):
            hi = m2
        else:
            lo = m1
    return round((lo + hi) / 2, 2)


def fit_per_group(rows: List[dict]) -> Dict[Tuple[str, int], float]:
    """Group key: (question_type, n_options). Returns {(type, n): T}."""
    groups: Dict[Tuple[str, int], list] = defaultdict(list)
    for r in rows:
        groups[(r.get("question_type", "?"), len(r.get("probs", {})))].append(r)
    return {k: fit(v) for k, v in groups.items() if len(v) >= 5}


def load_map() -> Dict[str, float]:
    """JUDGE_TEMPERATURES_JSON: e.g. '{"choice:4": 1.9}'. Empty → {}."""
    try:
        data = json.loads(os.getenv("JUDGE_TEMPERATURES_JSON", "") or "{}")
        return {str(k): float(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def temperature_for(question_type: str, n_options: int, default: float = 1.0) -> float:
    m = load_map()
    return m.get(f"{question_type}:{n_options}", default)
