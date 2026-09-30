"""LAYA-backed judge — open-weights decision model (Convai Innovations).

Why LAYA here: same typed-decision interface as the Jev seam (choice/score/
boolean), Apache 2.0, runs locally (~15ms, 421M ModernBERT). Zero-shot it is
weak (~0.36 on the vendor's own benchmark) — the value is POST fine-tuning
on our own labels. Vendor claims do not transfer: Gate A measures before
anything is promoted (docs/MEASUREMENTS.md).

Deployment: OFFICIAL `laya-serve` (pip install "laya[serve]"; LAYA_PRELOAD=1 laya-serve)
— it speaks the SAME POST /v1/systemone shape as TypeSafe Jev, so this client
and jev.py are near-twins by design. Env (never in repo):
  LAYA_BASE_URL   default http://127.0.0.1:8000 (laya-serve default port)
  LAYA_MODEL      default laya-en
  LAYA_TEMPERATURE  calibration knob applied to returned probs (default 1.0
                  = passthrough; <1 sharpens, >1 flattens — set from the
                  temperature-fitting step, not by hand). The model card is
                  explicit: ships over-confident (ECE 0.466 → 0.081 after
                  per-(type,option-count) refit) — do NOT trust raw probs.
  LAYA_UNKNOWN_THRESHOLD  top-prob below this routes `unknown` (default 0.15,
                  same spirit as primitives.choose). LAYA always returns a
                  forced distribution — WE impose the unknown route; typed
                  output prevents invalid answers, it does not guarantee
                  correct judgments.
  LAYA_HONOR_ESCALATE  default OFF. The act/escalate head carries NO usable
                  signal (vendor issue #185: act_probability reads 1.0 for
                  almost every input, AUROC 0.30) — gate on confidence only
                  unless explicitly overridden.

Any failure raises — the caller falls back (classify.py); a judge must never
take down the tier.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Dict, Optional

import requests

from service.contracts import TaskType
from .primitives import Judgment

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_MODEL = "laya-en"


def available() -> bool:
    """Cheap readiness probe: local sidecar is 'available' when a base URL is
    configured (default included). Real failures surface at call time and the
    caller falls back — never cached as hard-down here."""
    return bool(os.getenv("LAYA_BASE_URL", DEFAULT_BASE_URL))


def _config() -> dict:
    return {
        "base_url": os.getenv("LAYA_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        "model": os.getenv("LAYA_MODEL", DEFAULT_MODEL),
        "timeout_s": float(os.getenv("LAYA_TIMEOUT_S", "8")),
        "temperature": max(float(os.getenv("LAYA_TEMPERATURE", "1.0") or 1.0), 1e-6),
        "unknown_threshold": float(os.getenv("LAYA_UNKNOWN_THRESHOLD", "0.15")),
    }


def _apply_temperature(probs: Dict[str, float], temperature: float) -> Dict[str, float]:
    """Sharpen (T<1) or flatten (T>1) a distribution: p_i^(1/T), renormalized.
    This is the temperature-fitting seam for Gate B — post-hoc calibration on
    our domain, applied where the raw checkpoint's probs enter the pipeline."""
    if not probs:
        return {}
    shifted = {k: (max(0.0, v)) ** (1.0 / temperature) for k, v in probs.items()}
    total = sum(shifted.values())
    if total <= 0:
        n = max(len(probs), 1)
        return {k: 1.0 / n for k in probs}
    return {k: v / total for k, v in shifted.items()}


def system_one(state, questions: dict, timeout_s: Optional[float] = None) -> dict:
    """Raw evaluation call against the local LAYA sidecar. Returns the
    `answers` map. Raises on any failure (caller falls back)."""
    cfg = _config()
    url = f"{cfg['base_url']}/v1/systemone"
    r = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json={"model": cfg["model"], "state": state, "questions": questions},
        timeout=timeout_s or cfg["timeout_s"],
    )
    r.raise_for_status()
    return r.json().get("answers", r.json())


_CLASSIFY_QUESTIONS = {
    "task_type": {
        "type": "choice",
        "instructions": "Classify the question by what solves it. "
                        "code = running code answers it; math = PURE arithmetic expression "
                        "with no story (calculator alone suffices, e.g. 'What is 5+3?'); "
                        "reasoning = a story/word problem needing a procedure even when "
                        "numbers appear (rates, handshakes, work schedules, riddles, logic); "
                        "unknown = factual, contested, or unclear — no solver category fits.",
        "criteria": {
            "code": "question contains or asks about executable code output",
            "math": "question is arithmetic with explicit numbers and operators",
            "reasoning": "question needs a reasoning procedure (rates, handshakes, riddles, logic)",
            "unknown": "factual, contested, or unclear — no solver category fits",
        },
    }
}


def _to_judgment(ans: dict, cfg: dict) -> Judgment:
    """Server answer → our Judgment, imposing OUR semantics:
    temperature calibration first, then the unknown route LAYA doesn't have."""
    raw = {k: float(v) for k, v in (ans.get("probabilities") or {}).items()}
    probs = _apply_temperature(raw, cfg["temperature"])
    conf = float(ans.get("confidence", 0.0))
    top = max(probs, key=probs.get) if probs else None
    unknown = top is None or top == "unknown" or probs.get(top, 0.0) < cfg["unknown_threshold"]
    # act/escalate head: ignored by default (vendor issue #185 — no usable
    # signal). Opt-in only via LAYA_HONOR_ESCALATE=1.
    if os.getenv("LAYA_HONOR_ESCALATE") == "1" and ans.get("escalate"):
        unknown = True
    return Judgment(kind="choice", choice=None if unknown else top,
                    probs=probs, confidence=conf, unknown=unknown)


def classify_question(question: str) -> tuple:
    """Juicio 1 via LAYA Choice(code/math/reasoning/unknown). Raises on failure."""
    cfg = _config()
    answers = system_one(question, _CLASSIFY_QUESTIONS)
    ans = answers.get("task_type", {})
    j = _to_judgment(ans, cfg)
    if j.unknown:
        return TaskType.UNKNOWN, j
    mapping = {"code": TaskType.CODE, "math": TaskType.MATH, "reasoning": TaskType.REASONING}
    return mapping.get(j.choice, TaskType.UNKNOWN), j


def timed_classify(question: str) -> tuple:
    """(task_type, judgment, latency_s). For measurement scripts (Gate A)."""
    t0 = time.time()
    try:
        t, j = classify_question(question)
        return t, j, round(time.time() - t0, 3)
    except Exception as e:
        logger.debug("LAYA classify failed, caller falls back: %s", e)
        raise
