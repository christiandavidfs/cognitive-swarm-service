"""LAYA judge + Juicio 3 adjudication tests — all network mocked.

No sidecar, no keys, nothing leaves the box. Same rules as test_jev.py:
a judge that errors must never break routing, and the unknown route is
imposed by US (LAYA always returns a forced distribution).
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO = Path(__file__).parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from service.contracts import TaskType
from service.judgments import classify_question
from service.judgments import adjudicate as adj_mod
from service.judgments.adjudicate import adjudicated_classify
from service.judgments.laya import _apply_temperature


def _resp(probs, conf=0.9, escalate=False):
    return {"task_type": {"type": "choice", "choice": None,
                          "probabilities": probs, "confidence": conf,
                          "escalate": escalate}}


class _R:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return {"answers": self._p}


def test_laya_choice_maps_to_tasktype(monkeypatch):
    monkeypatch.setenv("JUDGE", "laya")
    monkeypatch.delenv("JUDGE_ADJUDICATE", raising=False)
    with patch("service.judgments.laya.requests.post",
               return_value=_R(_resp({"reasoning": 0.8, "unknown": 0.2}, 0.85))):
        t, j = classify_question("some handshake riddle phrasing")
    assert t == TaskType.REASONING and not j.unknown
    assert abs(j.confidence - 0.85) < 1e-9


def test_laya_unknown_imposed_below_threshold(monkeypatch):
    monkeypatch.setenv("JUDGE", "laya")
    monkeypatch.delenv("JUDGE_ADJUDICATE", raising=False)
    # LAYA returns a forced distribution — WE impose unknown when top prob
    # is below the threshold even though the model picked a winner.
    with patch("service.judgments.laya.requests.post",
               return_value=_R(_resp({"math": 0.12, "unknown": 0.44, "code": 0.44}, 0.9))):
        t, j = classify_question("When did the Western Roman Empire fall?")
    assert t == TaskType.UNKNOWN and j.unknown


def test_laya_escalate_ignored_by_default_gated_when_optin(monkeypatch):
    monkeypatch.setenv("JUDGE", "laya")
    monkeypatch.delenv("JUDGE_ADJUDICATE", raising=False)
    # Vendor issue #185: act/escalate head carries no signal → ignored by default
    with patch("service.judgments.laya.requests.post",
               return_value=_R(_resp({"reasoning": 0.95}, 0.95, escalate=True))):
        t, j = classify_question("anything")
    assert t == TaskType.REASONING and not j.unknown
    # Opt-in restores the gate
    monkeypatch.setenv("LAYA_HONOR_ESCALATE", "1")
    with patch("service.judgments.laya.requests.post",
               return_value=_R(_resp({"reasoning": 0.95}, 0.95, escalate=True))):
        t, j = classify_question("anything")
    assert t == TaskType.UNKNOWN and j.unknown


def test_laya_temperature_sharpens(monkeypatch):
    raw = {"reasoning": 0.6, "unknown": 0.4}
    sharp = _apply_temperature(raw, 0.5)
    flat = _apply_temperature(raw, 2.0)
    assert sharp["reasoning"] > raw["reasoning"] / (raw["reasoning"] + raw["unknown"])
    assert flat["reasoning"] < raw["reasoning"] / (raw["reasoning"] + raw["unknown"])
    assert abs(sum(sharp.values()) - 1.0) < 1e-9
    assert abs(sum(flat.values()) - 1.0) < 1e-9


def test_laya_failure_falls_back_to_heuristic(monkeypatch):
    monkeypatch.setenv("JUDGE", "laya")
    monkeypatch.delenv("JUDGE_ADJUDICATE", raising=False)

    def _boom(*a, **k):
        raise ConnectionError("sidecar down")

    with patch("service.judgments.laya.requests.post", side_effect=_boom):
        t, j = classify_question("What does print(2+3) output?")
    assert t == TaskType.CODE  # heuristic fallback, judge never breaks routing


# ── Juicio 3: adjudicate-on-conflict ─────────────────────────────────────────

def _fake_judge(task_value, conf, unknown=False):
    from service.judgments.primitives import Judgment

    def fn(_q):
        j = Judgment(kind="choice", choice=None if unknown else task_value,
                     probs={task_value: conf} if not unknown else {},
                     confidence=conf, unknown=unknown)
        return TaskType(task_value), j
    return fn


def test_adjudicate_consensus_uses_min_confidence(monkeypatch):
    monkeypatch.setitem(adj_mod.__dict__, "_load_judge_fn",
                        lambda name: {"laya": _fake_judge("reasoning", 0.9),
                                      "jev": _fake_judge("reasoning", 0.7),
                                      "arbiter": lambda n: (_ for _ in ()).throw(AssertionError("no arbiter"))}.get(name))
    out = adjudicated_classify("q", primary_name="laya", secondary_name="jev")
    assert out.task_type == TaskType.REASONING
    assert out.source == "consensus" and not out.disagreement and not out.escalated
    assert abs(out.judgment.confidence - 0.7) < 1e-9  # conservative min


def test_adjudicate_disagreement_goes_to_arbiter(monkeypatch):
    calls = []

    def arbiter(q):
        calls.append(q)
        return _fake_judge("math", 0.88)(q)

    monkeypatch.setitem(adj_mod.__dict__, "_load_judge_fn",
                        lambda name: {"laya": _fake_judge("reasoning", 0.9),
                                      "jev": _fake_judge("math", 0.8),
                                      "jev2": arbiter}.get(name))
    out = adjudicated_classify("q", primary_name="laya",
                               secondary_name="jev", arbiter_name="jev2")
    assert calls, "arbiter must be consulted on conflict"
    assert out.task_type == TaskType.MATH and out.source == "arbiter"
    assert out.disagreement and out.escalated


def test_adjudicate_arbiter_failure_falls_to_heuristic(monkeypatch):
    def broken_arbiter(q):
        raise RuntimeError("arbiter down")

    monkeypatch.setitem(adj_mod.__dict__, "_load_judge_fn",
                        lambda name: {"laya": _fake_judge("reasoning", 0.9),
                                      "jev": _fake_judge("math", 0.8),
                                      "jev2": broken_arbiter,
                                      "heuristic": _fake_judge("unknown", 0.25, unknown=True)}.get(name))
    out = adjudicated_classify("q", primary_name="laya",
                               secondary_name="jev", arbiter_name="jev2")
    assert out.source == "heuristic" and out.disagreement and not out.escalated


def test_adjudicate_both_unknown_no_theater(monkeypatch):
    def no_arbiter(q):
        raise AssertionError("arbiter must not fire when both judges agree on unknown")

    monkeypatch.setitem(adj_mod.__dict__, "_load_judge_fn",
                        lambda name: {"laya": _fake_judge("unknown", 0.2, unknown=True),
                                      "jev": _fake_judge("unknown", 0.3, unknown=True),
                                      "jev2": no_arbiter}.get(name))
    out = adjudicated_classify("q", primary_name="laya",
                               secondary_name="jev", arbiter_name="jev2")
    assert out.task_type == TaskType.UNKNOWN and not out.escalated


def test_adjudicate_primary_down_secondary_survives(monkeypatch):
    def dead_primary(q):
        raise ConnectionError("laya down")

    monkeypatch.setitem(adj_mod.__dict__, "_load_judge_fn",
                        lambda name: {"laya": dead_primary,
                                      "jev": _fake_judge("reasoning", 0.8),
                                      "jev2": lambda n: (_ for _ in ()).throw(AssertionError("no arbiter"))}.get(name))
    out = adjudicated_classify("q", primary_name="laya", secondary_name="jev")
    assert out.task_type == TaskType.REASONING and out.source == "secondary"
    assert not out.disagreement and not out.escalated


def test_judge_laya_with_adjudication_end_to_end(monkeypatch):
    monkeypatch.setenv("JUDGE", "laya")
    monkeypatch.setenv("JUDGE_ADJUDICATE", "1")
    # secondary heuristic agrees with laya's answer → consensus, no arbiter call
    with patch("service.judgments.laya.requests.post",
               return_value=_R(_resp({"code": 0.9, "unknown": 0.1}, 0.9))):
        with patch("service.judgments.adjudicate._load_judge_fn") as load:
            def fake_load(name):
                if name == "laya":
                    from service.judgments import laya as laya_mod
                    return laya_mod.classify_question
                from service.judgments.classify import _heuristic_classify
                return _heuristic_classify
            load.side_effect = fake_load
            t, j = classify_question("What does print(2+3) output?")
    assert t == TaskType.CODE and not j.unknown
