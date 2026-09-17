"""FastAPI app — Cognitive Swarm as a Service.

Exposes the truth hierarchy as HTTP, with modular connectors and pluggable models.

Endpoints:
  GET  /health                         → service + hierarchy status
  GET  /connectors                     → registry (enabled/disabled, categories, reliability)
  GET  /models                         → model registry (loaded flag, strengths)
  POST /resolve {question, connectors?, models?, provenance?} → Resolution (Tier 0-3 sync; Tier 4 async)
  POST /jobs/debate {question, models?} → {job_id} ; GET /jobs/{job_id}
  GET  /jobs
  GET  /memory, GET /memory/stats
  POST /connectors/{name}/reindex      → warm cache / reindex
"""
from __future__ import annotations

import os
import sys
import time
import logging
from pathlib import Path
from typing import List, Optional

# Ensure core is importable when running via `uvicorn service.app:app` from service repo
CORE_PATH = Path(__file__).parent.parent.parent / "cognitive-swarm"
if str(CORE_PATH) not in sys.path and CORE_PATH.exists():
    sys.path.insert(0, str(CORE_PATH))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Core
from cognitive_swarm.orchestration.truth_router import TruthRouter
from cognitive_swarm.orchestration.corroboration import Corroborator

# Service
from service.connectors.registry import build_retrievers, describe_registry
from service.memory.procedure_store import ProcedureStore
from service.jobs.debate_job import create_job, get_job, list_jobs
from service.models.registry import list_models, available_models

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Cognitive Swarm Service",
    description="Swarm as a Service — patterns + truth hierarchy + procedure memory, modular connectors, pluggable models",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Single shared memory + router for the hot path (ProcedureStore persists to ./data/verified_memory.json)
_memory: Optional[ProcedureStore] = None
_router: Optional[TruthRouter] = None
_start_time = time.time()

def get_memory() -> ProcedureStore:
    global _memory
    if _memory is None:
        # Resolve data path relative to service repo, allow override via MEMORY_PATH env
        p = os.getenv("MEMORY_PATH")
        if p:
            _memory = ProcedureStore(path=Path(p))
        else:
            data_path = Path(__file__).parent.parent / "data" / "verified_memory.json"
            data_path.parent.mkdir(parents=True, exist_ok=True)
            _memory = ProcedureStore(path=data_path)
    return _memory

def get_router() -> TruthRouter:
    global _router
    if _router is None:
        mem = get_memory()
        # Default retrievers per config/service.yaml (enabled:true) — gate by category inside router
        retrievers = build_retrievers(enabled_only=True)
        _router = TruthRouter(memory=mem, corroborator=Corroborator(), retrievers=retrievers)
    return _router

# --- Schemas

class ResolveRequest(BaseModel):
    question: str
    connectors: Optional[List[str]] = None  # override defaults; null = use config defaults
    models: Optional[List[str]] = None      # for future debate fallback; not used on L0-L3
    provenance: bool = True

class ResolveResponse(BaseModel):
    answer: Optional[str]
    confidence: float
    status: str
    tier: str
    sources: list = []
    disagreement: list = []
    trace: Optional[str] = None

class DebateRequest(BaseModel):
    question: str
    models: Optional[List[str]] = None

# --- Routes

@app.get("/health")
def health():
    mem = get_memory()
    return {
        "status": "ok",
        "uptime_s": round(time.time() - _start_time, 1),
        "memory_entries": mem.size(),
        "hierarchy": ["memory", "executor", "string-op", "reasoning-primitives", "math-primitives", "calculator", "retrieval (Wikidata/OpenAlex/LocalDocs/Confluence/Databricks/Postgres/generic_http)", "debate (async)"],
    }

@app.get("/connectors")
def connectors():
    return {"connectors": describe_registry()}

@app.get("/models")
def models():
    return {"models": list_models()}

@app.get("/memory")
def memory_list(limit: int = 20):
    mem = get_memory()
    items = list(mem.entries.values())[:limit]
    return {"total": mem.size(), "items": items}

@app.get("/memory/stats")
def memory_stats():
    mem = get_memory()
    by_tier: dict = {}
    for e in mem.entries.values():
        by_tier[e.get("tier", "unknown")] = by_tier.get(e.get("tier", "unknown"), 0) + 1
    return {"total_entries": mem.size(), "by_tier": by_tier, "path": str(mem.path)}

@app.post("/resolve", response_model=ResolveResponse)
def resolve(req: ResolveRequest):
    q = (req.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="question is required")
    # Per-request connector override: build a scoped router so caller can choose sources
    if req.connectors is not None:
        mem = get_memory()
        retrievers = build_retrievers(enabled_only=False, include=req.connectors)
        router = TruthRouter(memory=mem, corroborator=Corroborator(), retrievers=retrievers)
    else:
        router = get_router()
    resolution = router.resolve(q)
    # Attach trace if procedure memory has it
    trace = None
    if resolution.answer is not None:
        rec = get_memory().lookup(q)
        if rec and rec.get("trace"):
            trace = rec["trace"]
    return ResolveResponse(
        answer=resolution.answer,
        confidence=resolution.confidence,
        status=resolution.status,
        tier=resolution.tier,
        sources=resolution.sources,
        disagreement=resolution.disagreement,
        trace=trace,
    )

@app.post("/jobs/debate")
def debate(req: DebateRequest):
    q = (req.question or "").strip()
    if not q:
        raise HTTPException(400, detail="question is required")
    job_id = create_job(q, models=req.models)
    return {"job_id": job_id, "status": "queued"}

@app.get("/jobs/{job_id}")
def job_status(job_id: str):
    j = get_job(job_id)
    if not j:
        raise HTTPException(404, detail="job not found")
    return j

@app.get("/jobs")
def jobs():
    return {"jobs": list_jobs()}

@app.post("/connectors/{name}/reindex")
def reindex(name: str):
    # Warm the cache for this connector by probing it once (no-op if unknown)
    from service.connectors.registry import available_connectors
    if name not in available_connectors():
        raise HTTPException(404, detail=f"unknown connector {name!r}. Available: {available_connectors()}")
    # Build single retriever and trigger a dummy lookup to warm internal caches / indexes
    retrievers = build_retrievers(enabled_only=False, include=[name])
    if not retrievers:
        raise HTTPException(500, detail=f"failed to build connector {name!r}")
    # Touch with a harmless query to force index build (LocalDocs) or SPARQL warm
    try:
        retrievers[0].get_claims("test warm reindex")
    except Exception:
        pass
    return {"name": name, "status": "reindexed", "retrievers": 1}

# For `uvicorn service.app:app --reload` convenience, allow running as script
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
