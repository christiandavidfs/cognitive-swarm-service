# Workflow — After Every Change, Update Agents & Docs (reproducible)

> Rule: no code lands without doc sync. **This repo is standalone** — no sibling checkouts, no `../` paths, no cross-repo imports (decisión 2026-09-30). The `cognitive_swarm` core is an *optional package* (pip / PYTHONPATH), never a path dependency. All details stay in `docs/ROADMAP_SERVICE_PRIVATE.md` + `AGENTS.md`.

## 1. How to proceed after every change (checklist)

Copy-paste for every PR/commit:

```bash
# 1. compile + unit (hermetic — no core package, no Databricks, no network)
python -m py_compile service/app.py service/contracts.py service/router.py service/corroboration.py \
  service/backends/*.py service/connectors/*.py service/memory/*.py service/models/*.py \
  service/jobs/*.py service/judgments/*.py service/orchestrator/*.py tests/*.py
BACKENDS=__none__ python -m pytest -q   # 56 passed (2026-09-30)

# 2. docs (mandatory — AGENTS.md hook checks this when service/ changes)
# - AGENTS.md — update state/session findings if branch, counts, or decisions changed
# - docs/ARCHITECTURE_JUDGMENTS.md — only if architecture moved (freeze rule: no new layer without a measurement)
# - docs/ROADMAP_SERVICE_PRIVATE.md — log phase status, counts, sigs (nothing public leaves this file)
# - README.md — update quickstart + Tests & validation if commands changed

# 3. optional, ONLY if the core package is installed locally (not CI, not hermetic):
#    deterministic 120/120 via POST /resolve + procedure-hit check on new numbers.
#    Steps: BACKENDS=cognitive_swarm + scripts/seed_procedures.py → curl /resolve → verify tier: procedure.
#    Distillation scripts (generate_procedures / distill_to_qwen) need the core package and print a
#    clear error without it. Paraphrase gate said NO (2026-09-30) — do not reopen distillation.
```

## 2. How to start (new task)

```bash
# from this repo root (standalone — nothing outside)
cd <service-repo-root>
# 1. read AGENTS.md + docs/ROADMAP_SERVICE_PRIVATE.md (phases + state) + plan/remediacion-hallazgos.md (open phases)
# 2. pick the phase / finding to close
# 3. branch: git checkout -b feat/<name>
# 4. code → checklist above → commit with `feat:`/`fix:` prefix
# 5. push: git push origin HEAD
```

## 3. Hook (enforces docs, optional but recommended)

Install once:

```bash
cat > .git/hooks/pre-commit <<'HOOK'
#!/bin/sh
set -e
# fail if AGENTS.md or ROADMAP_SERVICE_PRIVATE.md not touched with code changes
if git diff --cached --name-only | grep -qE "service/|tests/"; then
  if ! git diff --cached --name-only | grep -q "AGENTS.md"; then
    echo "✗ After every change, update AGENTS.md"; exit 1
  fi
  if ! git diff --cached --name-only | grep -q "docs/ROADMAP_SERVICE_PRIVATE.md"; then
    echo "✗ After every change, update docs/ROADMAP_SERVICE_PRIVATE.md"; exit 1
  fi
fi
HOOK
chmod +x .git/hooks/pre-commit
```

## 4. Private guard (business — nothing public)

* Private (nothing public, never push): `testing.testing_schema.swarm_knowledge` raw, `swarm_procedures` traces + `procedure_sig`, `quality_platform` bronze/silver, `DATABRICKS_HOST` / `DATABRICKS_TOKEN` / `DATABRICKS_WAREHOUSE_ID`, `data/verified_memory.json` (gitignored), `*.pkl`, `procedure:trace` in `POST /resolve sources[]`. Only env placeholders (`${VAR}`) in committed files — an unexpanded `${...}` fails closed.

## 5. Current doc map

* Private roadmap: `docs/ROADMAP_SERVICE_PRIVATE.md` (phase status + reproducible quickstart; env-only secrets).
* Architecture: `docs/ARCHITECTURE_JUDGMENTS.md` (layers, judgments, phases; public-safe).
* Business pipeline: `docs/BUSINESS_IMPLEMENTATIONS.md` (pipeline, not proof — no monetization claim without pilot numbers).
* Service state: `AGENTS.md` (branch, tests, measurements, operational facts).
* Open remediation work: `plan/remediacion-hallazgos.md` (fases 0–6; fase 0+1 done on `feat/remediation-phase-0-auth`).