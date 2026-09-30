"""Director tests — stats policy, unknown route, router integration. No network."""
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from service.contracts import BackendAnswer, ResolverBackend, TaskType
from service.orchestrator import Director
from service.router import Router


def _tmp_director():
    return Director(path=str(Path(tempfile.mkdtemp()) / "r.json"))


def test_no_signal_preserves_input_order():
    d = _tmp_director()
    assert d.order(["b", "a"], TaskType.MATH) == ["b", "a"]


def test_success_rate_reorders():
    d = _tmp_director()
    for _ in range(4):
        d.record("slow", TaskType.MATH, True)
    for _ in range(4):
        d.record("fast", TaskType.MATH, False)
    # slow: (4+1)/(4+2)=0.83 ; fast: (0+1)/(4+2)=0.17 → slow first
    assert d.order(["fast", "slow"], TaskType.MATH)[0] == "slow"
    # per-type isolation: MATH signal must not leak into CODE
    assert d.order(["fast", "slow"], TaskType.CODE) == ["fast", "slow"]


def test_export_dataset_rows():
    d = _tmp_director()
    d.record("b", TaskType.CODE, True)
    rows = d.export_dataset()
    assert rows and rows[0]["layer"] == "b" and rows[0]["attempts"] == 1


class _Solver(ResolverBackend):
    name = "solver"

    def classify(self, question: str):
        return TaskType.UNKNOWN

    def solve(self, question: str):
        if question == "solve me":
            return BackendAnswer(answer="done", tier="executor")
        return None


def test_router_records_routing_outcome():
    d = _tmp_director()
    r = Router(memory=None, retrievers=[], backends=[_Solver()], director=d)
    res = r.resolve("solve me")
    assert res.answer == "done"
    assert d.rate("solver", TaskType.UNKNOWN) is not None
