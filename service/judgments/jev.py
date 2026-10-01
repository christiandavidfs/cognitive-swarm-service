"""Jev-backed judge — native SystemOne typed API (Choice/Score/Noul).

Why native, not the OpenRouter chat wrapper: `typesafe/jev-router` on
OpenRouter is chat-completions text (no distributions, no confidence) — using
it would defeat the purpose. This client speaks SystemOne
(`POST {base}/v1/systemone` with state+questions) so probabilities and
confidence survive end to end.

Auth: `TYPESAFE_API_KEY` env (never in repo). `TYPESAFE_BASE_URL` overrides
the endpoint (TypeSafe direct or a compatible gateway). `JEV_MODEL`
defaults to `jev-latest`. Any failure → caller falls back to heuristics;
a judge that errors must never take down the tier.
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


def available() -> bool:
    via = os.getenv("JEV_VIA", "typesafe").lower()
    if via == "vercel":
        return bool(os.getenv("AI_GATEWAY_API_KEY"))
    return bool(os.getenv("TYPESAFE_API_KEY"))


def _config() -> dict:
    via = os.getenv("JEV_VIA", "typesafe").lower()
    if via == "vercel":
        return {
            "via": "vercel",
            "api_key": os.getenv("AI_GATEWAY_API_KEY", ""),
            "base_url": os.getenv("GATEWAY_BASE_URL", "https://ai-gateway.vercel.sh").rstrip("/"),
            "model": os.getenv("JEV_MODEL", "typesafe-ai/jev"),
            "timeout_s": float(os.getenv("JEV_TIMEOUT_S", "15")),
        }
    return {
        "via": "typesafe",
        "api_key": os.getenv("TYPESAFE_API_KEY", ""),
        "base_url": os.getenv("TYPESAFE_BASE_URL", "https://api.typesafe.ai").rstrip("/"),
        "model": os.getenv("JEV_MODEL", "jev-latest"),
        "timeout_s": float(os.getenv("JEV_TIMEOUT_S", "8")),
    }


def _gateway_type(qtype: str) -> str:
    # Vercel gateway names: boolean/choice/score (native TypeSafe: noul/choice/score).
    return {"noul": "boolean"}.get(qtype, qtype)


def system_one(state, questions: dict, timeout_s: Optional[float] = None) -> dict:
    """Raw evaluation call. Returns the `answers` map. Raises on any failure."""
    cfg = _config()
    if not cfg["api_key"]:
        raise RuntimeError("judge API key not set (TYPESAFE_API_KEY or AI_GATEWAY_API_KEY)")
    if cfg["via"] == "vercel":
        url = f"{cfg['base_url']}/v1/evaluate"
        body = {"model": cfg["model"], "state": state, "questions": questions}
    else:
        url = f"{cfg['base_url']}/v1/systemone"
        body = {"model": cfg["model"], "state": state, "questions": questions}
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"},
        json=body,
        timeout=timeout_s or cfg["timeout_s"],
    )
    r.raise_for_status()
    data = r.json()
    return data.get("answers", data)


def classify_question(question: str) -> tuple:
    """Juicio 1 via Jev Choice(code/math/reasoning/unknown). Raises on failure."""
    answers = system_one(
        state=question,
        questions={
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
        },
    )
    ans = answers.get("task_type", {})
    choice = ans.get("choice")
    probs = {k: float(v) for k, v in (ans.get("probabilities") or {}).items()}
    conf = float(ans.get("confidence", 0.0))
    # Post-hoc temperature (JUDGE_TEMPERATURE, fitted on held-out): rescale the
    # distribution and recompute confidence from concentration. Choice never moves.
    t = _judge_temperature()
    if probs and abs(t - 1.0) > 1e-9:
        from .primitives import _concentration
        probs = _rescale(probs, t)
        conf = _concentration(probs)
        top = max(probs, key=probs.get)
        if choice not in probs:
            choice = top
    mapping = {"code": TaskType.CODE, "math": TaskType.MATH, "reasoning": TaskType.REASONING}
    if choice in mapping:
        return mapping[choice], Judgment(kind="choice", choice=choice, probs=probs,
                                         confidence=conf, unknown=False)
    return TaskType.UNKNOWN, Judgment(kind="choice", choice=None, probs=probs,
                                      confidence=conf, unknown=True)


def _rescale(probs: Dict[str, float], temperature: float) -> Dict[str, float]:
    """Post-hoc temperature scaling (fitted on held-out, never train).
    Choice (argmax) never changes — only the distribution sharpness."""
    if not probs or temperature <= 0:
        return probs
    qs = {k: max(v, 1e-12) ** (1.0 / temperature) for k, v in probs.items()}
    z = sum(qs.values()) or 1.0
    return {k: v / z for k, v in qs.items()}


def _judge_temperature() -> float:
    try:
        return float(os.getenv("JUDGE_TEMPERATURE", "1.0"))
    except ValueError:
        return 1.0


def timed_classify(question: str) -> tuple:
    """(task_type, judgment, latency_s). For measurement scripts."""
    t0 = time.time()
    try:
        t, j = classify_question(question)
        return t, j, round(time.time() - t0, 3)
    except Exception as e:
        logger.debug("Jev classify failed, caller falls back: %s", e)
        raise
