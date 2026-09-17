# Workflow — After Every Change, Update Agents & Docs (reproducible)

> Rule: no code lands without doc sync. Both repos are private, so private details stay in `docs/ROADMAP_SERVICE_PRIVATE.md` + `AGENTS.md`; public shareable is `procedure:trace` only.

## 1. How to proceed after every change (checklist)

Copy-paste for every PR/commit:

```bash
# 1. compile + unit
python -m py_compile cognitive_swarm/tools/*.py cognitive_swarm/memory/*.py cognitive_swarm/orchestration/*.py  # core
python -m py_compile service/app.py service/connectors/*.py service/memory/*.py service/models/*.py  # service
PYTHONPATH=../cognitive-swarm:$PYTHONPATH pytest -q  # 8/8 service
PYTHONPATH=../cognitive-swarm:$PYTHONPATH python scripts/generate_procedures.py  # 20/20 (or 40/40)
python scripts/seed_procedures.py 2>&1 | tail -5  # Databricks 20 (or 40)

# 2. deterministic validation (0 loads)
PYTHONPATH=../cognitive-swarm:$PYTHONPATH python -c "from fastapi.testclient import TestClient; import service.app as am; am._memory=None; c=TestClient(am.app); from cognitive_swarm.evaluation.leveled_benchmark import LEVELED_PROBLEMS, check_answer; print(sum(1 for p in LEVELED_PROBLEMS if check_answer(c.post('/resolve', json={'question': p['q']}).json().get('answer'), p['a'])), '/120')"
# -> 120/120
# procedure hit on new numbers
curl -X POST http://localhost:8000/resolve -H 'content-type: application/json' -d '{"question":"In a group of 88 people each shakes hands with every other exactly once how many handshakes?"}' | python3 -m json.tool | grep -E "answer|tier|trace"

# 3. docs (mandatory)
# - AGENTS.md (core) — update Procedure/p primitive memory line if patterns/traces changed
# - AGENTS.md (service) — update hierarchy + procedure count + Databricks tables
# - docs/ROADMAP_SERVICE_PRIVATE.md — log phase, counts, warehouse, sig (e.g. 6d8cef7d)
# - README.md — update quickstart + Tests & validation if commands changed
# - docs/RESULTS.md / docs/FINDINGS_STUDENT.md (core) if benchmark numbers changed
```

## 2. How to start (new task)

```bash
# from service repo (build mode, not plan)
cd /Users/kaizen/repos/cognitive-swarm-service
# 1. read AGENTS.md (this file) + docs/ROADMAP_SERVICE_PRIVATE.md:3 (phases 1→2→3)
# 2. pick Phase 1 (20→40) or Phase 2 (Qwen) or Phase 3 (vector)
# 3. branch: git checkout -b feat/<name>
# 4. code → checklist above → commit with `feat:` + `python -> python3` note if macOS
# 5. push: git push origin HEAD
```

## 3. Hook (enforces docs, optional but recommended)

Install once:

```bash
cat > .git/hooks/pre-commit <<'HOOK'
#!/bin/zsh
set -e
# fail if AGENTS.md or ROADMAP_SERVICE_PRIVATE.md not touched with code changes
if git diff --cached --name-only | grep -qE "service/|cognitive_swarm/"; then
  if ! git diff --cached --name-only | grep -q "AGENTS.md"; then
    echo "✗ After every change, update AGENTS.md (service + core)"; exit 1
  fi
  if ! git diff --cached --name-only | grep -q "docs/ROADMAP_SERVICE_PRIVATE.md"; then
    echo "✗ After every change, update docs/ROADMAP_SERVICE_PRIVATE.md"; exit 1
  fi
fi
HOOK
chmod +x .git/hooks/pre-commit
# same for core repo: cp .git/hooks/pre-commit /Users/kaizen/repos/cognitive-swarm/.git/hooks/pre-commit
```

## 4. Private vs shareable guard (business)

* Private (never push to public): `testing.testing_schema.swarm_knowledge` raw, `quality_platform` bronze/silver, `DATABRICKS_HOST/TOKEN` `warehouse 2b2636...`, `data/verified_memory.json`, `*.pkl`.
* Shareable: `swarm_procedures` `trace` + `procedure_sig` via `POST /resolve sources[]`.

## 5. Current doc map

* Private roadmap: `docs/ROADMAP_SERVICE_PRIVATE.md:1` (20→40, 1→2→3, reproducible 65ms warm).
* Service AGENTS: `AGENTS.md:1` (procedure L1, Databricks live).
* Core AGENTS: `../cognitive-swarm/AGENTS.md:72` (20/20 POC, give/take fix).
