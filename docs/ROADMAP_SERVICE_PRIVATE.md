# ROADMAP Service — Private, Reproducible, Implementable

> Private doc. Contains warehouse/host/table names and monetization notes. Nothing public. Do not publish as-is.

## 0. Current state (2026-09-18, feat/procedures-40)

* Service repo `cognitive-swarm-service` private `https://github.com/christiandavidfs/cognitive-swarm-service` `feat/procedures-40` (next merge to `main`), build mode.
* Core `cognitive-swarm` private `1972313` + `feat/procedures-40` (give/take fix + `33` templates `40/40`, `46` patterns `184` samples `CV 0.951`).
* Tiers: `service/app.py:141` L0 `ProcedureStore` `service/memory/procedure_store.py:7` `similarity_threshold 0.85` `config/service.yaml:80` → L1 `procedure` tier on new numbers (same `procedure_sig 6d8cef7d`, TF-IDF `0.26ms`, no load) → L2 deterministic `reasoning_primitives.py`/`student_trace.py` `40/40` verifiable → L3 `Wikidata 0.8` + `OpenAlex 0.9` + **Databricks live** `service/connectors/databricks.py:36` Statement API `warehouses/2b2636d0ca412cdb` Serverless Starter `dbc-118c13a0-9998.cloud.databricks.com`.
* Databricks: `testing.testing_schema.swarm_knowledge` 7 rows, `testing.testing_schema.swarm_procedures` `40` rows (Delta), `quality_platform` bronze (`api_endpoints` etc.) + silver remain but not queried by default (scoped to `testing.swarm_*`).
* Verified: `120/120` via `POST /resolve` `0 loads`, `POST /resolve` new numbers `88` hits `tier: procedure, trace in sources[]`, stock `moses/bear/race` `13` new `46` patterns.

## 1. Private — nothing public (business)

| Data | Location | Visibility | How service uses it |
|------|----------|------------|---------------------|
| `testing.*` sample (`swarm_knowledge` raw Q/A) | `testing.testing_schema.swarm_knowledge` `ISOLATED` `658fac0b` | **Private** — only via `databricks_sql` `query_template` `config/service.yaml:37` | Tier 3 source, `reliability 1.0`, `LIMIT 5` for contested `disagreement` |
| `quality_platform` bronze/silver (`api_endpoints`, `coverage_*`) | `quality_platform.*` `OPEN` `ae811f5e` | **Private** — not in `databricks_sql` query, future `Confluence`/`Postgres` stubs | Not on hot path, for internal quality dashboards |
| `swarm_procedures` trace lake | `testing.testing_schema.swarm_procedures` `20` rows, also `data/verified_memory.json` traces | **Private** — nothing public, `POST /resolve` returns `{sources:[{name: procedure:handshake, trace, procedure_sig}]}` internally | Procedure reuse, monetizable internally |
| `data/verified_memory.json`, `*.pkl`, `.env`, `DATABRICKS_TOKEN` | `cognitive-swarm-service/data/` + `~/.databricks` `personal` `host=dbc-118c...` `warehouse=2b2636...` | **Private** | `.gitignore` already |

Monetize options (undecided, IA for investigation / market, all private):
* **IA investigation** — `POST /resolve` tier `procedure` + `retrieval` with provenance as private API (investigation teams query private `swarm_knowledge` + get private `trace`).
* **Market** — `swarm_procedures` `procedure_sig` marketplace: license skeleton (`6d8cef7d`) — also private until licensed.

## 2. Reproducible quickstart (copy-paste)

```bash
# 0. env (macOS: python → python3 already symlinked)
cd /Users/kaizen/repos/cognitive-swarm-service
python3 -m venv .venv 2>&1 | tail -1; source .venv/bin/activate 2>&1 | head -1
pip install -e . 2>&1 | tail -1
pip install -e ../cognitive-swarm 2>&1 | tail -1
# or: PYTHONPATH=../cognitive-swarm:$PYTHONPATH python3 -m pytest -q  # 8/8

# 1. Databricks seed (needs `databricks auth login` personal, warehouse auto-start)
python3 scripts/seed_databricks.py --verify          # swarm_knowledge 7 + procedures 1
python3 scripts/seed_procedures.py                   # swarm_procedures 20 verifiable, local 21 entries, 20/20

# 2. Service (hot path 65ms warm, 0 loads on L0-L2)
uvicorn service.app:app --reload --port 8000 &
curl -X POST http://localhost:8000/resolve -H 'content-type: application/json' -d '{"question":"In a group of 100 people each shakes hands with every other exactly once how many handshakes?"}' | python3 -m json.tool
# -> 4950 tier: procedure (or reasoning-primitives first time) trace: n=100, handshake = n*(n-1)/2 = 4950 sig: 6d8cef7d
curl -X POST http://localhost:8000/resolve -H 'content-type: application/json' -d '{"question":"In a group of 88 people each shakes hands with every other exactly once how many handshakes?"}' | python3 -m json.tool
# -> 3828 tier: procedure trace: n=88, handshake = n*(n-1)/2 = 88*87/2 = 3828 same sig (knowledge changed, reasoning stayed)

# 3. Contested honest disagreement (Databricks 2 rows + Wikidata + LocalDocs)
curl -X POST http://localhost:8000/resolve -H 'content-type: application/json' -d '{"question":"What caused the fall of the Roman Empire?"}' | python3 -m json.tool
# -> null + disagreement: economic decline vs barbarian invasions vs 395 CE

# 4. Validation
PYTHONPATH=../cognitive-swarm:$PYTHONPATH python3 -m pytest tests/test_api_resolve.py -q  # 8/8
PYTHONPATH=../cognitive-swarm:$PYTHONPATH python3 -c "from cognitive_swarm.evaluation.leveled_benchmark import LEVELED_PROBLEMS, check_answer; from fastapi.testclient import TestClient; import service.app as am; am._memory=None; c=TestClient(am.app); print(sum(1 for p in LEVELED_PROBLEMS if check_answer(c.post('/resolve', json={'question': p['q']}).json().get('answer'), p['a'])), '/120')"
# -> 120/120 even with Databricks enabled

# 5. TF-IDF + Qwen distill view
python3 scripts/distill_to_qwen.py  # CV 0.962, 33/36 routing, 20/20 novel, Qwen LoRA command
python3 scripts/generate_procedures.py  # 20/20 verifiable
```

## 3. Phases — 1→2→3 (smartest order)

### Phase 1 — 20→40 procedures + 200-human (5-7d, first, unlocks 2-3)
* Files: `scripts/generate_procedures.py:20` `40/40` now `33` templates `40/40` `46` patterns `184` `CV 0.951` → next `40→60` add `batch200` human, `scripts/seed_procedures.py:1` `--clear` reseed `testing.swarm_procedures` `40→60`.
* Acceptance: `POST /resolve` new numbers `tier: procedure` on 3 variants (handshake `88`, stock `moses`, `bear`), `batch200_final.json` `>85%`, Databricks `select count(*) =40` now `40`.
* Why first: DONE `20→40`, next is `40→60`; fixes `66%→47%` `docs/FINDINGS_STUDENT.md:33` without GPU; 2-3 need fresh verified traces to avoid collapse `THESIS.md:7.5`.

### Phase 2 — Distill to Qwen question→trace (parallel day 3, 1d train)
* Files: `scripts/distill_to_qwen.py:1` (TF-IDF `0.26ms` already reuses `40/40`) + `cognitive_swarm/tools/qwen_router.py:50` + `qwen_lora_finetune.py`.
* Command (M1 8GB, ~12min, 150 iters, peak 0.73GB): `python -m mlx_lm.lora --model mlx-community/Qwen2.5-0.5B-Instruct-4bit --data /tmp/qwen_trace_data --train --batch-size 2 --iters 150 --adapter-path cognitive_swarm/tools/qwen_router_lora --r 8 --alpha 16`
* Data: JSONL `question→trace→answer` from private `swarm_procedures` `40` + synthetic `184` samples.
* Acceptance: `CV ≥0.95`, `40/40` now, latency `TF-IDF <1ms` vs `Qwen <500ms`, `DUAL_ROUTER_BENCHMARK.md:1` apples-to-apples.

### Phase 3 — Vector scale (last, 3d)
* Files: `service/connectors/databricks.py:36` `I LIKE` → Databricks Vector Search `vector_search_indexes` hybrid lexical→reranker, keep `procedure_sig` exact for `65ms warm`.
* Why last: `local_docs threshold 0.35` + `memory 0.85` fine for `200` docs; vectors only for `1000+` Confluence.
* Acceptance: `confluence` `service/connectors/confluence.py:1` `enabled:true` with `1000` docs, `+50ms` vs `I LIKE`, no `120/120` regression.

## 4. Implementable checklist (per phase, no assumption)

* Phase 1: create `15` tests in `batch200_final.json:1` for new stock, `python scripts/generate_procedures.py` `40/40`, `python scripts/seed_procedures.py`, `pytest -q`, `curl` new numbers variant.
* Phase 2: `python scripts/distill_to_qwen.py` with `swarm` venv `scikit-learn`, `mlx_lm.lora` train, `python -m cognitive_swarm.tools.qwen_router` smoke `predict('handshake 88')`.
* Phase 3: `databricks vector-search-indexes create` + `service.yaml` `vector_search_endpoint` + `postgres` `POSTGRES_DSN` if needed.

## 5. Private notes (keep in this doc only)

* Warehouse `2b2636d0ca412cdb` Serverless Starter `STOPPED` auto-start `10s` `PENDING→SUCCEEDED`, host `dbc-118c13a0-9998.cloud.databricks.com`, token via `databricks auth token --output json` (`gho_*` not in env). `DATABRICKS_WAREHOUSE_ID`, `DATABRICKS_HOST`, `DATABRICKS_TOKEN` (1h TTL) not committed.
* Catalogs: `dbacademy`, `testing` `ISOLATED` `658fac0b`, `quality_platform` `ae811f5e`, `system`. `testing.testing_schema` private sample, `quality_platform.bronze/silver` private platform.
* All `curl` from `~` need `python3 /Users/.../scripts/...` (zsh `python` not found before symlink fix `de875eb`).
