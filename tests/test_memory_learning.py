"""Memory learning tests — LTM counters, pruning, STM consolidation. No network."""
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from service.memory.store import ProcedureStore
from service.memory.session import Session, SessionStore


def _tmp_store():
    return ProcedureStore(path=str(Path(tempfile.mkdtemp()) / "mem.json"))


def test_counters_survive_reremember():
    s = _tmp_store()
    s.remember("q1?", "a", tier="executor")
    s.record_outcome("q1?", True)
    s.record_outcome("q1?", False)
    s.remember("q1?", "a", tier="executor")  # re-archive must NOT reset learning
    e = s.lookup("q1?")
    assert e["attempts"] == 2 and e["successes"] == 1
    assert ProcedureStore.success_rate(e) == 0.5


def test_prune_drops_proven_bad_keeps_unknown():
    s = _tmp_store()
    s.remember("bad?", "x", tier="executor")
    for _ in range(5):
        s.record_outcome("bad?", False)
    s.remember("new?", "y", tier="executor")  # no history → immune
    removed = s.prune(min_rate=0.3, min_attempts=5)
    assert removed == 1
    assert s.lookup("bad?") is None
    assert s.lookup("new?")["answer"] == "y"


def test_session_consolidate_only_verified():
    s = _tmp_store()
    sessions = SessionStore()
    sess = sessions.create()
    sess.record("good?", "42", source="session", trace="t -> 42", outcome=True)
    sess.record("fail?", "xx", source="session", outcome=False)
    sess.record("pending?", "zz", source="session")  # no outcome → never archived
    n = sessions.consolidate(sess.id, s)
    assert n == 1
    assert s.lookup("good?")["answer"] == "42"
    assert ProcedureStore.success_rate(s.lookup("good?")) == 1.0
    assert s.lookup("pending?") is None


def test_session_ring_buffer():
    sess = Session("s", capacity=3)
    for i in range(5):
        sess.record(f"q{i}?", str(i))
    assert len(sess) == 3
    assert [st["question"] for st in sess.recent(3)] == ["q2?", "q3?", "q4?"]
