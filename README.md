# Cognitive Swarm Service

> POC: Cognitive Swarm as an API — patterns + truth hierarchy + procedure memory.
> Core stays in `../cognitive-swarm` (`TruthRouter` Tiers 0-4, deterministic primitives, `Corroborator`, `VerifiedMemory`). This service adds a modular connector layer (Wikidata, OpenAlex/Semantic Scholar, Databricks, Confluence, Postgres, generic HTTP), a pluggable model registry, and procedure memory (traces, not just answers).

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .                    # service
pip install -e ../cognitive-swarm  # core (or add to PYTHONPATH)

# run API (port 8000, hot path 65ms warm when L0/L2 hits, 0 model loads)
uvicorn service.app:app --reload --port 8000

# health + single resolve
curl http://localhost:8000/health
curl -X POST http://localhost:8000/resolve -H 'content-type: application/json' \
  -d '{"question":"What does print(2+3) output?"}'

# factual via Tier 3 — now live on Databricks + Wikidata + LocalDocs, corroborated with provenance
curl -X POST http://localhost:8000/resolve -H 'content-type: application/json' \
  -d '{"question":"When did the Western Roman Empire fall?"}'  # -> 476 CE, sources: local-docs + databricks:testing.swarm_knowledge:1

# contested — honest disagreement, no forced single answer
curl -X POST http://localhost:8000/resolve -H 'content-type: application/json' \
  -d '{"question":"What caused the fall of the Roman Empire?"}'  # -> null + disagreement: economic decline vs barbarian invasions vs Wikidata

# choose connectors and models per request
curl -X POST http://localhost:8000/resolve -H 'content-type: application/json' \
  -d '{"question":"When did the Western Roman Empire fall?","connectors":["databricks_sql","wikidata"]}'
curl -X POST http://localhost:8000/resolve -H 'content-type: application/json' \
  -d '{"question":"What is 2+2?","connectors":["wikidata","openalex"]}'  # still 4 — L2 wins before Tier 3

# jobs (thinking matrix, async, not on hot path)
curl -X POST http://localhost:8000/jobs/debate -H 'content-type: application/json' -d '{"question":"What is 2+2?"}'
```

## Databricks — live POC

Sample knowledge is seeded in `testing.testing_schema.swarm_knowledge` (7 rows) + `testing.testing_schema.swarm_procedures` (trace for handshake 47 → 1081). The service's `DatabricksSQLRetriever` (`service/connectors/databricks.py`) uses the Statement Execution API (`warehouses/2b2636d0ca412cdb` Serverless Starter, auto-start). No JDBC.

```bash
# check tables (needs `databricks auth login` or host/token via env)
databricks tables list quality_platform bronze  # quality_platform.bronze.* (api_endpoints, etc.)
databricks tables list testing testing_schema  # swarm_knowledge, swarm_procedures

# query via API (same as service)
curl -s -X POST "https://dbc-118c13a0-9998.cloud.databricks.com/api/2.0/sql/statements" \
  -H "Authorization: Bearer $(databricks auth token --output json | python3 -c 'import json,sys; print(json.load(sys.stdin)[\"access_token\"])')" \
  -H "Content-Type: application/json" \
  -d '{"warehouse_id":"2b2636d0ca412cdb","statement":"SELECT * FROM testing.testing_schema.swarm_knowledge LIMIT 10","wait_timeout":"10s"}' | python3 -m json.tool
```

Config: `config/service.yaml` `connectors.databricks_sql` is `enabled:true` (host + warehouse_id baked for POC, token auto-fetched via `databricks auth token` if `DATABRICKS_TOKEN` not set). Query: `SELECT answer, source, reliability FROM testing.testing_schema.swarm_knowledge WHERE question ILIKE '%{question}%' LIMIT 5` — returns up to 5 claims for contested demo. Reliability 1.0 weight + independence bonus in `Corroborator` so `476 CE` corroborated (local-docs + Databricks) while `economic decline` vs `barbarian invasions` surfaces as `disagreement`.

## Architecture (inherits `docs/ARCHITECTURE.md` truth hierarchy)

```
POST /resolve → TruthRouter (Tier 0 memory → 1 code → 2b string → 2d reasoning → 2c math → 2 calc → 3 retrieval → 4 debate)
              Tier 3 = pluggable Retrievers (registry, category-gated, reliability+independence weighted)
              L1 procedure memory = question → trace skeleton (verifiable steps, e.g. handshake n=47 → n*(n-1)/2)
              Tier 4 debate = async job queue (thinking matrix) — not on hot path
```

Connectors are modular: `service/connectors/` — add one file + one line in `config/service.yaml` → auto-registered. Same for models: `service/models/registry.py` — declare MLX or API model → choosable per request.

## Config

`config/service.yaml` controls default connectors, model defaults, memory `similarity_threshold: 0.85` (prevents fall vs cause-of-fall blur), and retriever enablement. Per-request `connectors`/`models` override defaults.

## Tests & validation

```bash
PYTHONPATH=../cognitive-swarm:$PYTHONPATH pytest -q  # 8/8, includes live Databricks
# 120/120 deterministic via service (0 loads, even with Databricks enabled)
PYTHONPATH=../cognitive-swarm:$PYTHONPATH python3 -c "from cognitive_swarm.evaluation.leveled_benchmark import LEVELED_PROBLEMS, check_answer; ...; print(f'{ok}/120')"
```

## Docker

```bash
docker build -t swarm-service .
docker run --rm -p 8000:8000 swarm-service
```

## Models — choosable per request

`GET /models` lists `phi`/`qwen` (MLX, sequential 8GB) + `minimax-m3` (API, needs `OPENROUTER_API_KEY`). `POST /resolve {models:["phi","qwen"]}` is honored by debate jobs; deterministic tiers never load a model.
