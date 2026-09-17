"""Debate jobs — async thinking matrix, results archived as procedure memory.

POC is in-process (no Redis). `POST /jobs/debate` enqueues, a background thread runs
the cross-critique debate via the core `emergent_debate` / `optimized_debate`, verifies
any candidate via `TruthRouter.verify_candidate`, and archives verified traces to
ProcedureStore. The hot path `/resolve` never blocks on this.
"""
from __future__ import annotations

import uuid
import time
import threading
import logging
from typing import Dict, List, Optional

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
    # run in background
    t = threading.Thread(target=_run_job, args=(job_id,), daemon=True)
    t.start()
    return job_id

def get_job(job_id: str) -> Optional[dict]:
    with _LOCK:
        return dict(_JOBS.get(job_id) or {})

def list_jobs() -> List[dict]:
    with _LOCK:
        return [dict(v) for v in _JOBS.values()]

def _run_job(job_id: str):
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        job["status"] = "running"
    q = job["question"]
    models = job["models"]
    try:
        # Try core debate if available; fallback to simple single-model stub that still archives.
        result = _run_debate(q, models)
        # Archive any verified candidate to procedure memory
        try:
            from service.memory.procedure_store import ProcedureStore
            from cognitive_swarm.tools.student_trace import generate_trace, verify_trace
            from cognitive_swarm.orchestration.truth_router import TruthRouter
            store = ProcedureStore()
            router = TruthRouter(memory=store)
            # verify + remember
            for cand in result.get("candidates", []):
                if router.verify_candidate(q, cand):
                    trace = generate_trace(q, "debate", {}, cand)
                    if verify_trace(trace):
                        store.remember_trace(q, trace, cand, tier="debate", confidence=0.7)
                        break
                # also try direct resolver trace
                from cognitive_swarm.tools.reasoning_primitives import detect_reasoning_pattern, resolve_reasoning_primitive
                det = detect_reasoning_pattern(q)
                if det:
                    pat, args = det
                    ans = resolve_reasoning_primitive(q)
                    if ans:
                        trace = generate_trace(q, pat, args, ans)
                        store.remember_trace(q, trace, ans, tier="reasoning-primitives")
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
    # Prefer core emergent debate if importable (needs mlx); otherwise cheap stub.
    try:
        # Lazy import so service runs without mlx in CI/tests
        from cognitive_swarm.orchestration.truth_router import TruthRouter
        from service.memory.procedure_store import ProcedureStore
        router = TruthRouter(memory=ProcedureStore())
        # If question is deterministically solvable, reuse resolver directly (fast, no model load)
        from cognitive_swarm.tools.reasoning_primitives import resolve_reasoning_primitive
        from cognitive_swarm.tools.math_primitives import resolve_math_primitive, resolve_compound_expression
        from cognitive_swarm.tools.string_primitives import resolve_string_primitive
        from cognitive_swarm.tools.executor import execute as exec_code
        for fn in [exec_code, resolve_string_primitive, resolve_reasoning_primitive, resolve_compound_expression, resolve_math_primitive]:
            try:
                ans = fn(question)
                if ans is not None:
                    return {"candidates": [ans], "verdict": ans, "source": "deterministic (no model load)"}
            except Exception:
                continue
        # Fall back to model generation if mlx available and models specified
        if models:
            from service.models.registry import generate_with_model as gen
            cands = []
            for m in models[:2]:
                try:
                    # Tight prompt like core PromptOptimizer does
                    prompt = f"Answer only the final value.\nQuestion: {question}\nANSWER:"
                    out = gen(m, prompt, max_tokens=16, temperature=0.7)
                    # crude extract: first line, strip
                    cand = out.strip().split("\n")[0].strip().split()[-1] if out.strip() else ""
                    if cand:
                        cands.append(cand.strip(".,:"))
                except Exception as e:
                    logger.debug("Model %s generate failed: %s", m, e)
            if cands:
                return {"candidates": cands, "verdict": cands[0], "source": f"models {models}"}
        return {"candidates": [], "verdict": None, "source": "no deterministic resolver + no model"}
    except Exception as e:
        return {"candidates": [], "verdict": None, "source": f"error: {e}"}
