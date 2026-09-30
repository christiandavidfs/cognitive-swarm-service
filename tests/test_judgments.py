"""Judgment seam tests — same results as before, new interface. No network."""
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from service.contracts import TaskType
from service.judgments import choose, classify_question, noul, score_judgment
from service.router import Router


def test_choose_probs_sum_and_unknown_route():
    j = choose({"a": 0.0, "b": 0.0}, unknown_threshold=0.4)
    assert j.unknown is True and j.choice is None
    assert abs(sum(j.probs.values()) - 1.0) < 1e-9


def test_choose_confidence_peaked_beats_flat():
    peaked = choose({"a": 1.0, "b": 0.0, "c": 0.0})
    assert peaked.choice == "a" and peaked.confidence == 1.0


def test_score_and_noul_shapes():
    s = score_judgment({"low": 0.1, "mid": 0.2, "high": 0.7})
    assert 0.0 <= s.score <= 1.0 and abs(sum(s.probs.values()) - 1.0) < 1e-9
    n = noul(0.9)
    assert n.probs["true"] == 0.9 and n.confidence == 0.8


def test_classify_matches_legacy_behavior():
    t, j = classify_question("What does print(2+3) output?")
    assert t == TaskType.CODE and not j.unknown
    t, j = classify_question("What is 5+3?")
    assert t == TaskType.MATH
    t, j = classify_question("When did the Western Roman Empire fall?")
    assert t == TaskType.UNKNOWN and j.unknown


def test_router_uses_seam_without_backends():
    r = Router(memory=None, retrievers=[], backends=[])
    assert r.classify("What does print(2+3) output?") == TaskType.CODE
    assert r.classify(" utterly novel phrasing with no markers ") == TaskType.UNKNOWN
