"""Judgments package — Juicio 1 (classify) live, rest designed.

`configure()` maps `config/service.yaml [judge]` to env (explicit env wins).
Per-need switching without code changes:

  judge.backend: heuristic   → free local regex (offline default)
  judge.backend: jev + base_url http://127.0.0.1:8019 → local Kev (free, private)
  judge.backend: jev + jev_via vercel → Vercel gateway (paid credits)
  judge.backend: jev (defaults) → TypeSafe direct (paid, cents)
  judge.seats.classify → per-decision override (Fase 4+).
"""
from __future__ import annotations

import os
from pathlib import Path

from .adjudicate import Adjudication, adjudicated_classify
from .calibration import apply_temperature, ece, fit, fit_per_group, nll, temperature_for
from .classify import classify_question
from .primitives import Judgment, choose, noul, score_judgment

__all__ = ["Adjudication", "adjudicated_classify", "apply_temperature",
           "classify_question", "configure", "ece", "fit", "fit_per_group",
           "nll", "temperature_for", "Judgment", "choose", "noul", "score_judgment"]

SERVICE_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "service.yaml"


def configure(config_path=None) -> dict:
    """Apply [judge] config to env (explicit env always wins). Returns effective judge config."""
    cfg_path = Path(config_path) if config_path else SERVICE_CONFIG_PATH
    judge = {}
    try:
        import yaml
        data = yaml.safe_load(cfg_path.read_text()) or {}
        if isinstance(data, dict) and isinstance(data.get("judge"), dict):
            judge = data["judge"]
    except Exception:
        pass
    seats = judge.get("seats") or {}
    backend = os.getenv("JUDGE") or seats.get("classify") or judge.get("backend", "heuristic")
    os.environ.setdefault("JUDGE", str(backend))
    via = os.getenv("JEV_VIA") or judge.get("jev_via", "typesafe")
    os.environ.setdefault("JEV_VIA", str(via))
    for yaml_key, env_key in (("base_url", "TYPESAFE_BASE_URL"), ("model", "JEV_MODEL"),
                            ("temperature", "JUDGE_TEMPERATURE")):
        val = os.getenv(env_key) or judge.get(yaml_key)
        if val:
            os.environ.setdefault(env_key, str(val))
    api_key_env = os.getenv("JUDGE_API_KEY_ENV") or judge.get("api_key_env")
    if api_key_env and not os.getenv("TYPESAFE_API_KEY") and not os.getenv("AI_GATEWAY_API_KEY"):
        keyed = os.getenv(api_key_env, "")
        if keyed:
            target = "AI_GATEWAY_API_KEY" if via == "vercel" else "TYPESAFE_API_KEY"
            os.environ[target] = keyed
    return {"backend": os.environ["JUDGE"], "via": os.environ["JEV_VIA"],
            "seats": seats}
