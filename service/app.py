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
import time
import logging
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Service-owned: contracts, router, corroboration, memory, backends.
from service.contracts import Resolution as _Resolution
from service.corroboration import Corroborator
from service.router import Router
from service.backends import load_backends

# Service
from service.connectors.registry import build_retrievers, describe_registry
from service.memory.store import ProcedureStore
from service.jobs.debate_job import create_job, get_job, list_jobs
from service.models.registry import list_models, available_models
from service.judgments import configure as configure_judge

configure_judge()  # [judge] in config/service.yaml → env (explicit env wins)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Cognitive Swarm Service",
    description="Swarm as a Service — patterns + truth hierarchy + procedure memory, modular connectors, pluggable models",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Auth + rate-limit: moved to service/http_guard.py (fase 3 of plan/remediacion-hallazgos.md).
# Re-exported here so existing callers/tests keep importing from service.app.
from service.http_guard import (  # noqa: E402,F401
    _auth_config,
    _rate_buckets,
    auth_decision,
    bucket_key,
    expand_api_keys,
    build_auth_rate_middleware,
)

# The lambda resolves _auth_config in THIS module's namespace at request time,
# so monkeypatching service.app._auth_config (tests) keeps working.
app.middleware("http")(build_auth_rate_middleware(lambda: _auth_config()))

# Single shared memory + router for the hot path (ProcedureStore persists to ./data/verified_memory.json)
_memory: Optional[ProcedureStore] = None
_router: Optional[Router] = None
_backends_cache = None
_start_time = time.time()

_mem_cache: dict = {"mtime": 0.0, "ts": 0.0, "config": None}

def _memory_config() -> dict:
    """Read memory.similarity_threshold from config/service.yaml (fallback 0.85). Cached 30s."""
    cfg_path = Path(__file__).parent.parent / "config" / "service.yaml"
    now = time.time()
    try:
        mtime = cfg_path.stat().st_mtime
        if _mem_cache.get("config") is not None and (now - _mem_cache.get("ts", 0)) < 30.0 and mtime == _mem_cache.get("mtime"):
            return _mem_cache["config"]
        import yaml
        data = yaml.safe_load(cfg_path.read_text()) or {}
        mem = data.get("memory", {}) if isinstance(data, dict) else {}
        # Env override wins: MEMORY_SIMILARITY_THRESHOLD
        thr_raw = os.getenv("MEMORY_SIMILARITY_THRESHOLD", mem.get("similarity_threshold", 0.85))
        cfg = {"similarity_threshold": float(thr_raw)}
        _mem_cache.update({"mtime": mtime, "ts": now, "config": cfg})
        return cfg
    except Exception:
        return _mem_cache.get("config") or {"similarity_threshold": 0.85}

def get_memory() -> ProcedureStore:
    global _memory
    if _memory is None:
        cfg = _memory_config()
        thr = cfg.get("similarity_threshold", 0.85)
        p = os.getenv("MEMORY_PATH")
        if p:
            _memory = ProcedureStore(path=Path(p), similarity_threshold=thr)
        else:
            data_path = Path(__file__).parent.parent / "data" / "verified_memory.json"
            data_path.parent.mkdir(parents=True, exist_ok=True)
            _memory = ProcedureStore(path=data_path, similarity_threshold=thr)
    return _memory

def get_backends(mem=None):
    """Load optional resolver backends once (missing backends are skipped)."""
    global _backends_cache
    if _backends_cache is None:
        _backends_cache = load_backends(memory=mem if mem is not None else get_memory())
    return _backends_cache


def get_router() -> Router:
    global _router
    if _router is None:
        mem = get_memory()
        # Default retrievers per config/service.yaml (enabled:true) — gate by category inside router
        retrievers = build_retrievers(enabled_only=True)
        _router = Router(memory=mem, corroborator=Corroborator(), retrievers=retrievers,
                         backends=get_backends(mem))
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

@app.get("/")
def root():
    return {
        "service": "cognitive-swarm-service",
        "docs": "/docs",
        "health": "/health",
        "resolve": "POST /resolve {question, connectors?, models?}",
        "jobs": "POST /jobs/debate",
    }


@app.get("/health")
def health():
    mem = get_memory()
    return {
        "status": "ok",
        "uptime_s": round(time.time() - _start_time, 1),
        "memory_entries": mem.size(),
        "backends": [b.name for b in get_backends(mem)],  # [] = no optional backend installed
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

@app.get("/results")
def results():
    from service.results import summary
    return summary()

@app.get("/results/{name}")
def results_board(name: str):
    from service.results import board, verdict, BOARDS
    if name not in BOARDS:
        raise HTTPException(404, detail=f"unknown board {name!r}. Available: {sorted(BOARDS)}")
    b = board(name)
    b["verdict"] = verdict(name)
    return b

@app.get("/board", response_class=None)
def board_html():
    from fastapi.responses import HTMLResponse
    from service.results import render_html
    return HTMLResponse(render_html())

@app.post("/resolve", response_model=ResolveResponse)
def resolve(req: ResolveRequest):
    q = (req.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="question is required")
    # --- L1 procedure memory: reuse stored reasoning skeleton with NEW numbers (0 loads, ~0.3ms) ---
    # This is the "process not data" tier: same pattern, different numbers -> same procedure_sig
    mem = get_memory()
    router = get_router()
    proc = mem.resolve_via_procedure(q, backends=router.backends)
    if proc and proc.get("reused"):
        # Reused a known procedure — knowledge changed (numbers) but reasoning stayed
        # Return as memory hit with trace in sources for paper story: POST /resolve hits trace in sources[]
        trace = proc["trace"]
        # Persist this new-numbers instance as well (so next identical hits exact memory)
        mem.remember_trace(q, trace, proc["answer"], tier="reasoning-primitives", confidence=0.99)
        return ResolveResponse(
            answer=proc["answer"],
            confidence=0.99,
            status="memory",
            tier="procedure",
            sources=[{"name": f"procedure:{proc['pattern']}", "reliability": 1.0, "trace": trace, "procedure_sig": proc["procedure_sig"]}],
            disagreement=[],
            trace=trace,
        )
    # Per-request connector override: build a scoped router so caller can choose sources
    if req.connectors is not None:
        retrievers = build_retrievers(enabled_only=False, include=req.connectors)
        router = Router(memory=mem, corroborator=Corroborator(), retrievers=retrievers,
                        backends=router.backends)
    resolution = router.resolve(q)
    # Attach trace if procedure memory has it (or store it now for future reuse)
    trace = None
    if resolution.answer is not None:
        rec = mem.lookup(q)
        if rec and rec.get("trace"):
            trace = rec["trace"]
        elif proc and proc.get("trace"):
            # First time for this pattern/numbers — we just computed proc, but it wasn't reused (new pattern)
            trace = proc["trace"]
            mem.remember_trace(q, trace, resolution.answer, tier=resolution.tier, confidence=resolution.confidence)
            # Also surface trace in sources for this cold hit
            return ResolveResponse(
                answer=resolution.answer,
                confidence=resolution.confidence,
                status=resolution.status,
                tier=resolution.tier,
                sources=resolution.sources + [{"name": f"procedure:{proc['pattern']}", "reliability": 1.0, "trace": trace}],
                disagreement=resolution.disagreement,
                trace=trace,
            )
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
    uvicorn.run(app, host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8000")))
