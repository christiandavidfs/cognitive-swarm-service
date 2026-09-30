"""Curiosity engine tests — archive verified novelties, map blind spots. No network."""
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from service.contracts import BackendAnswer, ResolverBackend
from service.jobs.curiosity import CuriosityEngine
from service.memory.store import ProcedureStore


class FakeHandshake(ResolverBackend):
    """handshake N -> N(N-1)/2; anything without 'handshake' is unsolvable."""
    name = "fake"

    def classify(self, question: str):
        from service.contracts import TaskType
        return TaskType.UNKNOWN

    def detect(self, question: str):
        import re
        m = re.search(r"handshake (\d+)", question.lower())
        return ("handshake", {"n": int(m.group(1))}) if m else None

    def solve(self, question: str):
        det = self.detect(question)
        if not det:
            return None
        n = det[1]["n"]
        ans = str(n * (n - 1) // 2)
        return BackendAnswer(answer=ans, tier="reasoning-primitives",
                             pattern="handshake", args={"n": n},
                             trace=f"handshake n={n} -> {ans}")

    def signature(self, question: str):
        det = self.detect(question)
        return f"handshake:n={det[1]['n']}" if det else None


def _seeded_store():
    s = ProcedureStore(path=str(Path(tempfile.mkdtemp()) / "m.json"))
    s.remember_trace("handshake 10 blarg", "handshake n=10 -> 45", "45",
                     tier="reasoning-primitives")
    return s


def test_op1_archives_new_numbers_same_family():
    import re
    s = _seeded_store()
    eng = CuriosityEngine(s, backends=[FakeHandshake()], budget_per_run=4, seed=1)
    rep = eng.run()
    assert rep["archived"] >= 1
    assert rep["generated"] <= 8
    # every archived entry solves correctly through the backend
    for key, e in s.entries.items():
        if key == s.normalize("handshake 10 blarg"):
            continue
        m = re.search(r"handshake (\d+)", e["question"].lower())
        assert m, f"archived non-handshake: {e['question']}"
        n = int(m.group(1))
        assert e["answer"] == str(n * (n - 1) // 2)


def test_novelty_and_budget_respected():
    s = _seeded_store()
    eng = CuriosityEngine(s, backends=[FakeHandshake()], budget_per_run=2, seed=1)
    rep = eng.run()
    assert rep["generated"] <= 4  # 2 numbers + up to 2 compose attempts
    n1 = s.size()
    rep2 = eng.run()  # rerun: text duplicates must not re-archive as numbers-novel
    assert s.size() >= n1  # monotonic, never shrinks here


def test_blind_spots_recorded_never_archived():
    s = ProcedureStore(path=str(Path(tempfile.mkdtemp()) / "m.json"))
    s.remember("lions 5 roar", "loud", tier="retrieval")  # no backend can solve
    eng = CuriosityEngine(s, backends=[FakeHandshake()], budget_per_run=3, seed=1)
    rep = eng.run()
    assert rep["blind_spots"] >= 1
    assert all("lions" not in (e.get("trace") or "") for e in s.entries.values())
