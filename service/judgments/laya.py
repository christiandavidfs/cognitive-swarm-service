"""Laya-backed judge — open-weights decision model (Convai Innovations).

Same SystemOne shape as jev.py (state+questions → typed answers), so judges
stay interchangeable behind `judge.backend`. Env (never in repo):
  LAYA_BASE_URL    default http://127.0.0.1:8000 (laya-serve default port)
  LAYA_MODEL       default laya-en
  LAYA_TEMPERATURE calibration knob, passthrough at 1.0 (fit, don't hand-tune)
  LAYA_UNKNOWN_THRESHOLD  top-prob below this routes `unknown` (default 0.15)

Caveats honored: raw probs ship over-confident (refit mandatory before
promotion); a forced distribution is not a correct judgment — WE impose the
unknown route. Any failure raises; the caller falls back.
STATUS: client implemented + mocked tests; no live Laya server here yet.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Dict, Optional

import requests

from service.contracts import TaskType
from .calibration import apply_temperature
from .primitives import Judgment

logger = logging.getLogger(__name__)


def available() -> bool:
    return True  # HTTP endpoint; health-checked per call with fallback


def _config() -> dict:
    try:
        threshold = float(os.getenv("LAYA_UNKNOWN_THRESHOLD", "0.15"))
    except ValueError:
        threshold = 0.15
    try:
        temperature = float(os.getenv("LAYA_TEMPERATURE", "1.0"))
    except ValueError:
        temperature = 1.0
    return {
        "base_url": os.getenv("LAYA_BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
        "model": os.getenv("LAYA_MODEL", "laya-en"),
        "timeout_s": float(os.getenv("LAYA_TIMEOUT_S", "8")),
        "temperature": temperature,
        "unknown_threshold": threshold,
    }


def system_one(state, questions: dict, timeout_s: Optional[float] = None) -> dict:
    cfg = _config()
    r = requests.post(
        f"{cfg['base_url']}/v1/systemone",
        headers={"Content-Type": "application/json"},
        json={"model": cfg["model"], "state": state, "questions": questions},
        timeout=timeout_s or cfg["timeout_s"],
    )
    r.raise_for_status()
    data = r.json()
    return data.get("answers", data)


def classify_question(question: str) -> tuple:
    """Juicio 1 via Laya Choice(code/math/reasoning/unknown). Raises on failure."""
    cfg = _config()
    answers = system_one(
        state=question,
        questions={
            "task_type": {
                "type": "choice",
                "instructions": "Classify the question by what solves it: code runs it, "
                                "pure arithmetic calculates it, story problems need a procedure, "
                                "else unknown.",
                "criteria": {
                    "code": "question contains or asks about executable code output",
                    "math": "PURE arithmetic expression with no story",
                    "reasoning": "story/word problem needing a procedure even with numbers",
                    "unknown": "factual, contested, or unclear",
                },
            }
        },
    )
    ans = answers.get("task_type", {})
    choice = ans.get("choice")
    probs = {k: float(v) for k, v in (ans.get("probabilities") or {}).items()}
    probs = apply_temperature(probs, cfg["temperature"])
    top = max(probs, key=probs.get) if probs else None
    conf = round(probs[top] if top else 0.0, 3)
    mapping = {"code": TaskType.CODE, "math": TaskType.MATH, "reasoning": TaskType.REASONING}
    if choice in mapping and top == choice and probs[top] >= cfg["unknown_threshold"]:
        return mapping[choice], Judgment(kind="choice", choice=choice, probs=probs,
                                         confidence=conf, unknown=False)
    return TaskType.UNKNOWN, Judgment(kind="choice", choice=None, probs=probs,
                                      confidence=conf, unknown=True)


def timed_classify(question: str) -> tuple:
    t0 = time.time()
    try:
        t, j = classify_question(question)
        return t, j, round(time.time() - t0, 3)
    except Exception as e:
        logger.debug("Laya classify failed, caller falls back: %s", e)
        raise
