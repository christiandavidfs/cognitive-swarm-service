"""Adapted judge-layer tests — reimplemented here, mocked network. No live servers."""
import sys
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from service.contracts import TaskType
from service.judgments import adjudicated_classify
from service.judgments.adjudicate import _load_judge_fn
from service.judgments.calibration import apply_temperature, ece, fit, fit_per_group, nll
from service.judgments.primitives import Judgment


def _rows():
    # 8 rows: confident model, 1 error — T>1 should win NLL by softening.
    rows = []
    for i in range(7):
        rows.append({"question_type": "choice", "label": "a",
                     "probs": {"a": 0.9, "b": 0.1}})
    rows.append({"question_type": "choice", "label": "b",
                 "probs": {"a": 0.9, "b": 0.1}})
    return rows


def test_apply_temperature_never_moves_argmax():
    probs = {"a": 0.7, "b": 0.2, "c": 0.1}
    for t in (0.5, 1.0, 2.0, 5.0):
        out = apply_temperature(probs, t)
        assert max(out, key=out.get) == "a"
        assert abs(sum(out.values()) - 1.0) < 1e-9


def test_fit_softens_overconfident_model():
    t = fit(_rows())
    assert t > 1.0
    assert nll(_rows(), t) <= nll(_rows(), 1.0)
    assert ece(_rows(), t) <= ece(_rows(), 1.0)


def test_fit_per_group_splits_geometry():
    rows = ([{"question_type": "choice", "label": "a", "probs": {"a": 0.9, "b": 0.1}}] * 6
            + [{"question_type": "noul", "label": "true",
                "probs": {"true": 0.6, "false": 0.4}}] * 6)
    m = fit_per_group(rows)
    assert ("choice", 2) in m and ("noul", 2) in m


def _judge(task, choice="a", conf=0.9, unknown=False):
    return task, Judgment(kind="choice", choice=None if unknown else choice,
                          probs={choice: conf}, confidence=conf, unknown=unknown)


def test_adjudicate_consensus_takes_min_conf():
    import service.judgments.adjudicate as adj
    with patch.object(adj, "_load_judge_fn",
                      side_effect=lambda n: (lambda q: _judge(TaskType.MATH, conf=0.9))
                      if n in ("p", "s") else None):
        r = adj.adjudicated_classify("q", primary_name="p", secondary_name="s",
                                     arbiter_name="nope")
        assert r.source == "consensus" and not r.disagreement and not r.escalated
        assert abs(r.judgment.confidence - 0.9) < 1e-9


def test_adjudicate_conflict_escalates_to_arbiter():
    import service.judgments.adjudicate as adj
    def p(q):
        return _judge(TaskType.MATH)
    def s(q):
        return _judge(TaskType.CODE)
    def arb(q):
        return _judge(TaskType.MATH, conf=0.7)
    with patch.object(adj, "_load_judge_fn",
                      side_effect=lambda n: {"p": p, "s": s, "arb": arb}.get(n)):
        r = adj.adjudicated_classify("q", primary_name="p", secondary_name="s",
                                     arbiter_name="arb")
        assert r.source == "arbiter" and r.disagreement and r.escalated


def test_adjudicate_arbiter_down_falls_to_heuristic():
    import service.judgments.adjudicate as adj
    def p(q):
        return _judge(TaskType.MATH)
    def s(q):
        return _judge(TaskType.CODE)
    with patch.object(adj, "_load_judge_fn",
                      side_effect=lambda n: {"p": p, "s": s}.get(n)):
        r = adj.adjudicated_classify("q", primary_name="p", secondary_name="s",
                                     arbiter_name="missing")
        assert r.source == "heuristic" and r.disagreement and not r.escalated


def test_adjudicate_unknown_names_resolve_none():
    assert _load_judge_fn("nope") is None
    assert _load_judge_fn("heuristic") is not None


def test_laya_unknown_route_and_mapping(monkeypatch):
    monkeypatch.delenv("LAYA_TEMPERATURE", raising=False)
    from service.judgments import laya

    class _R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"answers": {"task_type": {
                "choice": "reasoning",
                "probabilities": {"reasoning": 0.8, "unknown": 0.2},
                "confidence": 0.75}}}

    with patch.object(laya.requests, "post", return_value=_R()):
        t, j = laya.classify_question("some riddle")
        assert t == TaskType.REASONING and not j.unknown
