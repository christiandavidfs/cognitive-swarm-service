"""API tests — deterministic tiers via HTTP, no external keys, no model loads."""
import sys
from pathlib import Path

# Ensure service import works when pytest runs from repo root
REPO = Path(__file__).parent.parent
CORE = Path(__file__).parent.parent.parent / "cognitive-swarm"
for p in [str(REPO), str(CORE)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi.testclient import TestClient
import tempfile, os
from pathlib import Path
import service.app as appmod
from service.app import app

# Isolate VerifiedMemory to a temp file so tests don't pollute prod data/verified_memory.json
_tmp = Path(tempfile.mktemp(suffix=".json"))
os.environ["MEMORY_PATH"] = str(_tmp)
appmod._memory = None
appmod._router = None

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
    assert "wikidata" in names
    assert "openalex" in names
    assert "confluence" in names
    assert "databricks_sql" in names
    assert "postgres" in names

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
    assert j["tier"] in ("executor", "memory", "math-primitives", "string-op", "reasoning-primitives")

def test_resolve_reasoning_no_external():
    # Pure L2 — should not need Wikidata/OpenAlex, 0 model loads
    r = client.post("/resolve", json={"question": "If you have 5 apples and you take away 2, how many do you have?"})
    assert r.status_code == 200
    assert r.json()["answer"] == "2"

def test_resolve_choose_connectors():
    # Explicit per-request connectors — still deterministic for L2 question
    r = client.post("/resolve", json={"question": "What is 5+3?", "connectors": ["wikidata", "openalex"]})
    assert r.status_code == 200
    assert r.json()["answer"] is not None

def test_resolve_factual_uses_retrieval_path():
    # Factual without L2 pattern → hits Tier 3 path (may be None without live data, but must not 500)
    r = client.post("/resolve", json={"question": "When did the Western Roman Empire fall?"})
    assert r.status_code == 200
    j = r.json()
    # Could be "476 CE" if Wikidata live, or None (conflict/uncertain) — both ok for POC
    assert "status" in j and "tier" in j and "sources" in j

def test_jobs_debate_enqueue():
    r = client.post("/jobs/debate", json={"question": "What is 2+2?"})
    assert r.status_code == 200
    jid = r.json()["job_id"]
    assert jid
    r2 = client.get(f"/jobs/{jid}")
    assert r2.status_code == 200
    assert r2.json()["status"] in ("queued", "running", "done", "failed")
