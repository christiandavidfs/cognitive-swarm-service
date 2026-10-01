"""API tests — standalone, no external packages, no model loads, no network.

A stub ResolverBackend covers deterministic tiers; retrieval tests use only
local/grouped claims via the in-process Corroborator.
"""
import ast
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

os.environ["MEMORY_PATH"] = str(Path(tempfile.mkdtemp()) / "mem.json")
os.environ["BACKENDS"] = "__none__"  # force empty; tests inject a stub instead

from fastapi.testclient import TestClient  # noqa: E402

import service.app as appmod  # noqa: E402
from service.app import app  # noqa: E402
from service.contracts import BackendAnswer, ResolverBackend, TaskType  # noqa: E402


class StubBackend(ResolverBackend):
    name = "stub"

    def classify(self, question: str):
        q = question.lower()
        if "print(" in q or "def " in q:
            return TaskType.CODE
        if any(c in q for c in "+-*/") and any(c.isdigit() for c in q):
            return TaskType.MATH
        return TaskType.UNKNOWN

    def solve(self, question: str):
        q = question.strip()
        if q == "What does print(2+3) output?":
            return BackendAnswer(answer="5", tier="executor")
        if q == "What is 5+3?":
            return BackendAnswer(answer="8", tier="calculator")
        if "take away" in q.lower():
            return BackendAnswer(answer="2", tier="reasoning-primitives",
                                 pattern="take_away", args={"n": 2},
                                 trace="take_away {n: 2} -> 2")
        return None


appmod._memory = None
appmod._router = None
appmod._backends_cache = [StubBackend()]

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "memory" in r.json()["hierarchy"][0]


def test_connectors_registry():
    r = client.get("/connectors")
    assert r.status_code == 200
    names = [c["name"] for c in r.json()["connectors"]]
    for expected in ("wikidata", "openalex", "confluence", "databricks_sql", "postgres"):
        assert expected in names


def test_models_registry():
    r = client.get("/models")
    assert r.status_code == 200
    names = [m["name"] for m in r.json()["models"]]
    assert "phi" in names
    assert "qwen" in names


def test_resolve_code_no_model():
    r = client.post("/resolve", json={"question": "What does print(2+3) output?"})
    assert r.status_code == 200
    j = r.json()
    assert j["answer"] == "5"
    assert j["tier"] in ("executor", "memory")


def test_resolve_reasoning_no_external():
    r = client.post("/resolve", json={"question": "If you have 5 apples and you take away 2, how many do you have?"})
    assert r.status_code == 200
    assert r.json()["answer"] == "2"


def test_resolve_choose_connectors():
    r = client.post("/resolve", json={"question": "What is 5+3?", "connectors": ["wikidata", "openalex"]})
    assert r.status_code == 200
    assert r.json()["answer"] is not None


def test_resolve_memory_hit():
    client.post("/resolve", json={"question": "What is 5+3?"})
    r = client.post("/resolve", json={"question": "What is 5+3?"})
    # Exact memory hit, or L1 procedure reuse (same skeleton, trace in sources)
    assert r.json()["tier"] in ("memory", "procedure")
    assert r.json()["answer"] == "8"


def test_resolve_factual_no_500_without_backends_data():
    r = client.post("/resolve", json={"question": "When did the Western Roman Empire fall?"})
    assert r.status_code == 200
    j = r.json()
    assert "status" in j and "tier" in j and "sources" in j


def test_corroborator_conflict_surfaces_disagreement():
    from service.corroboration import Corroborator
    from service.contracts import SourceClaim
    v = Corroborator().corroborate([
        SourceClaim(source="a", answer="economic decline", reliability=0.8),
        SourceClaim(source="b", answer="barbarian invasions", reliability=0.8),
    ])
    assert v.status == "conflict"
    assert v.answer is None
    assert len(v.disagreement) == 1


def test_jobs_debate_enqueue():
    r = client.post("/jobs/debate", json={"question": "What is 2+2?"})
    assert r.status_code == 200
    jid = r.json()["job_id"]
    assert jid
    r2 = client.get(f"/jobs/{jid}")
    assert r2.status_code == 200
    assert r2.json()["status"] in ("queued", "running", "done", "failed")


def test_recency_breaks_ties_fresh_wins():
    from service.corroboration import Corroborator
    from service.contracts import SourceClaim
    # 1-vs-1 stays honest conflict (share can't reach 0.6) — recency must not coronate alone
    v = Corroborator().corroborate([
        SourceClaim(source="old-doc", answer="Alpha", reliability=0.8, recency=0.0),
        SourceClaim(source="new-doc", answer="Beta", reliability=0.8, recency=1.0),
    ])
    assert v.status == "conflict" and v.answer is None
    # 2 fresh vs 1 stale with equal reliability → fresh corroborates
    v2 = Corroborator().corroborate([
        SourceClaim(source="old-doc", answer="Alpha", reliability=0.8, recency=0.0),
        SourceClaim(source="new-doc", answer="Beta", reliability=0.8, recency=1.0),
        SourceClaim(source="new-doc-2", answer="Beta", reliability=0.8, recency=0.9),
    ])
    assert v2.status == "corroborated" and v2.answer == "Beta"


def test_recency_neutral_preserves_legacy():
    from service.corroboration import Corroborator
    from service.contracts import SourceClaim
    v = Corroborator().corroborate([
        SourceClaim(source="a", answer="Same", reliability=0.8),
        SourceClaim(source="b", answer="Same", reliability=0.8),
    ])
    assert v.status == "corroborated" and v.answer == "Same"


def test_pokeapi_registered_and_gated():
    from service.connectors.registry import build_retrievers, describe_registry
    names = [c["name"] for c in describe_registry()]
    assert "pokeapi" in names
    rs = build_retrievers(enabled_only=False, include=["pokeapi"])
    assert len(rs) == 1
    from service.contracts import TaskType
    assert rs[0].applies_to(TaskType.UNKNOWN) and not rs[0].applies_to(TaskType.CODE)
    assert rs[0].get_claims("tell me a story?") == []  # no network, no match
