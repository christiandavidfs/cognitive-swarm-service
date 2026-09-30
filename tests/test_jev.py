"""Jev judge tests — all network mocked. No key, no calls leave the box."""
import sys
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from service.contracts import TaskType
from service.judgments import classify_question


def _resp(choice, probs, conf=0.9):
    return {"task_type": {"type": "choice", "choice": choice,
                          "probabilities": probs, "confidence": conf}}


class _R:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return {"answers": self._p}


def test_jev_choice_maps_to_tasktype(monkeypatch):
    monkeypatch.setenv("JUDGE", "jev")
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    with patch("service.judgments.jev.requests.post",
               return_value=_R(_resp("reasoning", {"reasoning": 0.8, "unknown": 0.2}, 0.85))):
        t, j = classify_question("some handshake riddle phrasing")
        assert t == TaskType.REASONING and not j.unknown
        assert abs(j.confidence - 0.85) < 1e-9


def test_jev_unknown_routes_unknown(monkeypatch):
    monkeypatch.setenv("JUDGE", "jev")
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    with patch("service.judgments.jev.requests.post",
               return_value=_R(_resp("unknown", {"unknown": 0.9}, 0.9))):
        t, j = classify_question("When did the Western Roman Empire fall?")
        assert t == TaskType.UNKNOWN and j.unknown


def test_jev_failure_falls_back_to_heuristic(monkeypatch):
    monkeypatch.setenv("JUDGE", "jev")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    t, j = classify_question("What does print(2+3) output?")
    assert t == TaskType.CODE  # heuristic fallback, judge never breaks routing


def test_configure_maps_yaml_to_env(tmp_path, monkeypatch):
    for k in ("JUDGE", "JEV_VIA", "TYPESAFE_BASE_URL", "JEV_MODEL"):
        monkeypatch.delenv(k, raising=False)
    cfg = tmp_path / "service.yaml"
    cfg.write_text("judge:\n  backend: jev\n  jev_via: typesafe\n"
                   "  base_url: http://127.0.0.1:8019\n  model: kev-latest\n"
                   "  seats:\n    classify: jev\n")
    from service.judgments import configure
    eff = configure(config_path=cfg)
    import os
    assert eff["backend"] == "jev" and os.environ["TYPESAFE_BASE_URL"] == "http://127.0.0.1:8019"
    assert os.environ["JEV_MODEL"] == "kev-latest"


def test_explicit_env_wins_over_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("JUDGE", "heuristic")
    for k in ("JEV_VIA", "TYPESAFE_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    cfg = tmp_path / "service.yaml"
    cfg.write_text("judge:\n  backend: jev\n")
    from service.judgments import configure
    assert configure(config_path=cfg)["backend"] == "heuristic"
