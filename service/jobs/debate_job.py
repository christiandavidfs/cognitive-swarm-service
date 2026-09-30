"""Debate jobs — async thinking matrix, results archived as procedure memory.

In-process POC (no Redis). `POST /jobs/debate` enqueues; a background thread
tries deterministic backends first (no model load), falls back to configured
models, and archives verified candidates to the service memory store. The hot
path `/resolve` never blocks on this. No external imports.
"""
from __future__ import annotations

import uuid
import time
import threading
import logging
from pathlib import Path
from typing import Dict, List, Optional
import os

logger = logging.getLogger(__name__)

_JOBS: Dict[str, dict] = {}
_LOCK = threading.Lock()


def create_job(question: str, models: Optional[List[str]] = None) -> str:
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "question": question,
        "models": models or ["phi", "qwen"],
        "status": "queued",
        "created_at": time.time(),
        "result": None,
        "error": None,
    }
    with _LOCK:
        _JOBS[job_id] = job
    t = threading.Thread(target=_run_job, args=(job_id,), daemon=True)
    t.start()
    return job_id


def get_job(job_id: str) -> Optional[dict]:
    with _LOCK:
        return dict(_JOBS.get(job_id) or {})


def list_jobs() -> List[dict]:
    with _LOCK:
        return [dict(v) for v in _JOBS.values()]


def _service_memory():
    from service.memory.store import ProcedureStore

    p = os.getenv("MEMORY_PATH")
    path = Path(p) if p else Path(__file__).parent.parent.parent / "data" / "verified_memory.json"
    return ProcedureStore(path=path)


def _run_job(job_id: str):
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        job["status"] = "running"
    q = job["question"]
    models = job["models"]
    try:
        result = _run_debate(q, models)
        try:
            from service.router import Router
            from service.backends import load_backends

            mem = _service_memory()
            router = Router(memory=mem, backends=load_backends(memory=mem))
            for cand in result.get("candidates", []):
                if router.verify_candidate(q, cand):
                    mem.remember_trace(q, f"debate -> {cand} (verified)", cand,
                                       tier="debate", confidence=0.7)
                    break
        except Exception as e:
            logger.debug("Archive to procedure store failed: %s", e)
        with _LOCK:
            job["status"] = "done"
            job["result"] = result
    except Exception as e:
        logger.exception("Debate job %s failed", job_id)
        with _LOCK:
            job["status"] = "failed"
            job["error"] = str(e)


def _run_debate(question: str, models: List[str]) -> dict:
    try:
        from service.router import Router
        from service.backends import load_backends

        mem = _service_memory()
        router = Router(memory=mem, backends=load_backends(memory=mem))
        for backend in router.backends:
            try:
                ans = backend.solve(question)
            except Exception:
                continue
            if ans is not None and ans.answer is not None:
                return {"candidates": [ans.answer], "verdict": ans.answer,
                        "source": f"deterministic backend {backend.name} (no model load)"}
        if models:
            from service.models.registry import generate_with_model as gen
            cands = []
            for m in models[:2]:
                try:
                    prompt = f"Answer only the final value.\nQuestion: {question}\nANSWER:"
                    out = gen(m, prompt, max_tokens=16, temperature=0.7)
                    cand = out.strip().split("\n")[0].strip().split()[-1] if out.strip() else ""
                    if cand:
                        cands.append(cand.strip(".,:"))
                except Exception as e:
                    logger.debug("Model %s generate failed: %s", m, e)
            if cands:
                return {"candidates": cands, "verdict": cands[0], "source": f"models {models}"}
        return {"candidates": [], "verdict": None, "source": "no deterministic backend + no model"}
    except Exception as e:
        return {"candidates": [], "verdict": None, "source": f"error: {e}"}
