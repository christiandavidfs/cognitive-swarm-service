"""Emergent families tests — condensation, recognition, router integration."""
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from service.contracts import BackendAnswer, ResolverBackend, TaskType
from service.memory.families import FamilyStore
from service.orchestrator import Director
from service.router import Router


def test_unknowns_condense_into_family():
    f = FamilyStore(candidate_threshold=3)
    for i in range(3):
        f.observe(f"quantum flux Level {i} readings?", pattern="quant", sig="SIGQ", success=True)
    assert len(f.families) == 1
    fam = next(iter(f.families.values()))
    assert fam["pattern"] == "quant" and fam["attempts"] == 3


def test_no_success_no_family():
    f = FamilyStore(candidate_threshold=3)
    for i in range(5):
        f.observe(f"weird thing {i}?", pattern=None, sig=None, success=False)
    assert len(f.families) == 0  # failures never condense into categories


def test_recognize_known_and_genuinely_new():
    f = FamilyStore(candidate_threshold=2)
    f.observe("quantum flux Level 1 readings?", pattern="quant", sig="SIGQ", success=True)
    f.observe("quantum flux Level 2 readings?", pattern="quant", sig="SIGQ", success=True)
    rec = f.recognize("quantum flux Level 9 readings?", pattern="quant", sig="SIGQ")
    assert rec["family"] is not None and rec["confidence"] > 0.5
    new = f.recognize("completely unrelated baking recipe?", pattern=None, sig=None)
    assert new["family"] is None and new["confidence"] == 0.0


def test_naming_is_optional():
    f = FamilyStore(candidate_threshold=1)
    f.observe("q?", pattern="p", sig="s", success=True)
    fid = next(iter(f.families))
    assert f.families[fid]["name"] is None
    assert f.name(fid, "quantum-stuff") is True


class _PatBackend(ResolverBackend):
    name = "pat"

    def classify(self, question: str):
        return TaskType.UNKNOWN

    def solve(self, question: str):
        if question.startswith("flux"):
            return BackendAnswer(answer="42", tier="reasoning-primitives", pattern="quant")
        return None


def test_router_uses_family_group_over_type():
    d = Director(path=str(Path(tempfile.mkdtemp()) / "r.json"))
    r = Router(memory=None, retrievers=[], backends=[_PatBackend()], director=d)
    for i in range(4):
        res = r.resolve(f"flux reading {i}?")
        assert res.answer == "42"
    fams = r.families.families
    assert len(fams) == 1  # emergent family condensed from solves
    # director learned under the family group once it condensed
    fam_id = next(iter(fams))
    assert d.rate("pat", fam_id) is not None
