# AGENTS.md — Cognitive Swarm Service

> Read this before changing code or running experiments. This is the service layer that turns the local swarm into a **monetizable API** with procedure memory and pluggable truth sources.

## What this service is

POC that wraps `../cognitive-swarm` (`TruthRouter` Tiers 0-4) into `FastAPI` at `service/app.py:141` — 65ms warm, 0 loads on deterministic tiers. Adds:

* **Procedure memory** `service/memory/procedure_store.py:12` — `question → trace → answer` with `procedure_sig` (numbers stripped), L1 `tier: procedure` on new numbers (same reasoning, e.g. handshake `100→88` same `6d8cef7d`). `40` traces seeded (`scripts/seed_procedures.py:1` `40/40` verifiable, `testing.testing_schema.swarm_procedures` `40` rows, `46` patterns `184` samples `CV 0.951`).
* **Pluggable connectors** `service/connectors/registry.py:29` — `config/service.yaml:37` declares `wikidata 0.8` + `openalex 0.9` + `databricks_sql` live (`testing.swarm_knowledge` 7 rows, `Statement API` `warehouses/2b2636d0ca412cdb` auto-start, token via `databricks auth token`), plus stubs `confluence`/`postgres`/`generic_http` (one file + one YAML line).
* **Model registry** `service/models/registry.py:1` — `phi`/`qwen` MLX sequential (8GB) + `minimax-m3` API, choosable per-request `POST /resolve {models:[...]}`.
* **Thinking matrix async** `service/jobs/debate_job.py:22` — not on hot path, verifies via `TruthRouter.verify_candidate` then `remember_trace`.

## Single most important finding (service)

Deterministic `120/120` still holds with all connectors `120/120 via HTTP` — retrieval never poisons L2 (gate `_has_math_structure` + `local_docs threshold 0.35` + `memory 0.85` `config/service.yaml:80`). Contested surfaces `disagreement` honestly (e.g. `What caused fall?` → `economic decline` vs `barbarian invasions` vs `wikidata 395 CE`). Procedure `88` same sig proves **process not data**.

## Architecture — truth hierarchy with procedure L1

```
POST /resolve → Tier 0 memory (exact, 0.85) → L1 procedure (reuse skeleton, 0.3ms TF-IDF, no load)
              → Tier 1 code → 2b string → 2d reasoning (give/take disambiguated before student) → 2c math → 2 calc → 3 retrieval (category-gated, reliability+independence) → 4 debate async
```
* `reasoning_primitives.py:42` `take_away` before student, `give away → simple_subtract` also before student (TF-IDF confuses them).
* `student_trace.py:25` `33` templates verifiable (`=` + digits, `20→33` with stock `moses/bear/race...`), `verify_trace` used by distill.
* Modules: `service/app.py:55` (FastAPI), `service/memory/procedure_store.py:40` (trace+sig), `service/connectors/databricks.py:36` (Statement API, `LIMIT 5` for contested), `service/models/registry.py:40` (MLX/API).

## Private — nothing public

| Data | Location | Visibility |
|------|----------|------------|
| `testing.swarm_knowledge` raw Q/A | `testing.testing_schema` `ISOLATED` | **Private** |
| `quality_platform` bronze/silver | `quality_platform.*` | **Private**, not queried |
| `swarm_procedures` traces | `testing...swarm_procedures` + `data/verified_memory.json` traces | **Private** (was shareable, now private per owner — nothing public) |
| `DATABRICKS_HOST/TOKEN` `warehouse 2b2636...` | `~/.databricks` `personal` | **Private**, `.gitignore` |

## Operational facts

* **Python**: `python3` (symlinked, `python` also works after `de875eb`), `swarm` venv `../swarm/cognitive-swarm-env/bin/python3` has `sklearn` for `student_router` train; service venv has `fastapi`.
* **Databricks**: `databricks auth login` `personal` `dbc-118c13a0-9998...`, `warehouses list` `2b2636...` `STOPPED` auto-start `10s`, `scripts/seed_databricks.py --verify` `7` rows.
* **Scripts**: `scripts/seed_databricks.py --verify` (knowledge) + `--add "Q|A|src|rel|cat"`, `scripts/seed_procedures.py` `20/20`, `scripts/generate_procedures.py` `20/20`, `scripts/distill_to_qwen.py` `CV 0.962` `33/36`.
* **Thresholds**: `memory 0.85` prevents `fall` vs `cause of fall` blur; `local_docs 0.35` prevents `5 machines` false hit.
* **Results non-deterministic** for debate only; deterministic tiers reproducible.

## Open items (turn into tasks)

* Phase 1 `40→60` `batch200` human (was `20→40` done), `40` traces live `46` patterns `CV 0.951`.
* Phase 2 Qwen LoRA `question→trace` `mlx_lm.lora --iters 150` on `40` traces.
* Phase 3 Vector Search hybrid for `1000+` docs.

## Conventions

* After **every** change: `python -m py_compile service/app.py service/connectors/*.py service/memory/*.py service/models/*.py`, `pytest -q` `8/8`, `curl` new-numbers `tier: procedure`, update `docs/ROADMAP_SERVICE_PRIVATE.md` + this file + `README.md`.
* No bare answer: `Resolution(answer, confidence, sources, disagreement, trace)`.
* Docs: `docs/ROADMAP_SERVICE_PRIVATE.md` (private, reproducible, nothing public), `README.md` private.
