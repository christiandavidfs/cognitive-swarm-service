"""Memory integrity: quarantine, self-veto, replay drift, compaction.

Pins the 2026-10-19 incident class: a wrong answer enshrined with confidence
1.0 must stop being served, and must never be resurrected by a later write.
"""
import tempfile
from pathlib import Path

from service.contracts import BackendAnswer, Resolution, TaskType
from service.memory.store import ProcedureStore
from service.router import Router


def _tmp_store():
    return ProcedureStore(path=str(Path(tempfile.mkdtemp()) / "mem.json"))


class FakeOracle:
    """Deterministic backend: Paris for France, None elsewhere (fail-honest)."""
    name = "fake_oracle"

    def signature(self, question):
        return "capital:country=france" if "france" in question.lower() else None

    def solve(self, question):
        if "france" in question.lower():
            return BackendAnswer(answer="Paris", tier="primitives")
        return None

    def classify(self, question):
        return TaskType.UNKNOWN

    def detect(self, question):
        return None


def test_quarantined_entry_is_never_served():
    s = _tmp_store()
    s.remember("What is the capital of Japan?", "Paris", tier="executor")
    s.quarantine("What is the capital of Japan?", reason="test")
    assert s.lookup("What is the capital of Japan?") is None
    assert s.lookup("capital of japan?") is None          # similarity path too
    assert s.summary()["quarantined"] == 1
    assert s.summary()["active"] == 0


def test_quarantine_survives_a_later_remember():
    s = _tmp_store()
    s.remember("q?", "wrong", tier="executor")
    s.quarantine("q?", reason="incident")
    s.remember("q?", "wrong", tier="executor")            # re-archive
    assert s.lookup("q?") is None


def test_self_veto_after_enough_failures():
    s = _tmp_store()
    s.remember("q?", "x", tier="executor")
    s.record_outcome("q?", False)
    s.record_outcome("q?", False)
    assert s.lookup("q?") is not None                     # 2 fails: not enough
    s.record_outcome("q?", False)
    assert s.lookup("q?") is None                         # 3 fails: vetoed
    assert s.entries["q?"]["status"] == "quarantined"


def test_requalify_is_explicit():
    s = _tmp_store()
    s.remember("q?", "x")
    s.quarantine("q?", reason="test")
    assert s.requalify("q?")
    assert s.lookup("q?")["answer"] == "x"


def test_replay_drift_quarantines_and_serves_the_oracle():
    s = _tmp_store()
    s.remember("What is the capital of France?", "Paris", tier="primitives")
    # Simulate drift: cache now holds a wrong answer with full confidence.
    s.entries["what is the capital of france?"]["answer"] = "London"

    router = Router(memory=s, backends=[FakeOracle()], verify_memory_hits=True)
    res = router.resolve("What is the capital of France?")
    assert res.answer == "Paris"                          # truth beats cache
    assert s.entries["what is the capital of france?"]["status"] == "quarantined"

    # And the bad entry is not served afterwards, verification on or off.
    assert s.lookup("What is the capital of France?") is None


def test_replay_without_verification_serves_the_cache():
    s = _tmp_store()
    s.remember("What is the capital of France?", "Paris", tier="primitives")
    s.entries["what is the capital of france?"]["answer"] = "London"
    router = Router(memory=s, backends=[FakeOracle()], verify_memory_hits=False)
    assert router.resolve("What is the capital of France?").answer == "London"
    assert s.entries["what is the capital of france?"]["status"] == "active"


def test_compact_bounds_one_off_instances_only():
    s = _tmp_store()
    for i in range(6):
        s.remember(f"What does print({i}*2) output?", str(i * 2),
                   tier="primitives", procedure_sig="sig-print")
    s.remember("What type is pikachu?", "electric", tier="retrieval")   # no sig
    s.remember("What does print(9*9) output?", "81", tier="primitives",
               procedure_sig="sig-print")
    s.record_outcome("What does print(9*9) output?", True)              # tested

    dropped = s.compact(max_per_sig=3)
    assert dropped == 3                                   # 6 untested -> keep 3
    assert s.lookup("What type is pikachu?") is not None
    assert s.lookup("What does print(9*9) output?") is not None          # evidence kept
    left = [e for e in s.entries.values() if e.get("procedure_sig") == "sig-print"]
    assert len(left) == 4                                 # 3 newest untested + 1 tested


def test_compact_keeps_newest():
    s = _tmp_store()
    for i in range(5):
        s.remember(f"q{i}?", str(i), procedure_sig="sig")
        s.entries[f"q{i}?"]["first_seen"] = i              # deterministic order
        s.entries[f"q{i}?"]["last_hit"] = i
    s.compact(max_per_sig=2)
    assert set(s.entries) == {"q3?", "q4?"}


def test_one_off_deterministic_answers_are_not_enshrined():
    """No trace -> nothing reusable -> the oracle recomputes free. Don't cache."""
    s = _tmp_store()
    res = Router(memory=s, backends=[FakeOracle()]).resolve(
        "What is the capital of France?")
    assert res.answer == "Paris"
    assert s.size() == 0


def test_traced_answers_are_enshrined_with_a_procedure_sig():
    class Traced(FakeOracle):
        def solve(self, question):
            return BackendAnswer(answer="Paris", tier="primitives",
                                 trace="capital(country) -> Paris")

    s = _tmp_store()
    Router(memory=s, backends=[Traced()]).resolve("What is the capital of France?")
    assert s.entries["what is the capital of france?"]["procedure_sig"]
