# Cognitive Swarm Service

> POC: Cognitive Swarm as an API — patterns + truth hierarchy + procedure memory.
> Standalone service (memory + retrieval run without a sibling checkout). Optional deterministic backends plug in via `cognitive_swarm` when that package is installed.
>
> License: [UNLICENSED](LICENSE) — all rights reserved until the author chooses terms.

## Installation

Requirements: Python 3.11 or newer. The service dependencies and the test runner are declared in `pyproject.toml`.

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

### Windows PowerShell

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

The `.[dev]` extra installs the runtime packages (`fastapi`, `uvicorn`, `pydantic`, `httpx`, `pyyaml`, `requests`) plus `pytest`, `pytest-asyncio`, and `black`. If `pytest` or `fastapi` is missing, run the same `python -m pip install -e ".[dev]"` command from the activated virtual environment.

### Quick start

```bash
# If you only need to run the API and not the tests, use: python -m pip install -e .

# Optional: enable the deterministic cognitive-swarm backend (Tiers 0-2).
# Without it the service still serves memory + retrieval.
# pip install -e <path-to-cognitive-swarm>   # provides `cognitive_swarm`
# BACKENDS=cognitive_swarm uvicorn service.app:app --reload --port 8000

# run API (port 8000; 0 model loads on deterministic tiers — "65ms warm" is a dated lab
#   measurement from before the standalone split, not reproduced by CI; see README §Private roadmap)
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

## Databricks

Optional Tier 3 source. Host, warehouse id, and token come from the environment (`DATABRICKS_HOST`, `DATABRICKS_WAREHOUSE_ID`, `DATABRICKS_TOKEN`) — see `.env.example`. They are not baked into `config/service.yaml`. An unexpanded `${...}` placeholder fails closed: the connector returns no claims.

`databricks auth token` is an operator convenience for a local CLI session, not a production default. Do not deploy assuming a Databricks CLI is installed. Gating that subprocess behind an explicit opt-in is phase 5 of `plan/remediacion-hallazgos.md`; until then, unset `DATABRICKS_TOKEN` can still trigger it.

Query template (the question is escaped): `SELECT answer, source, reliability FROM ${DATABRICKS_KNOWLEDGE_TABLE} WHERE question ILIKE '%{question}%' LIMIT 5`.

## Architecture (see `docs/ARCHITECTURE_JUDGMENTS.md` for the full vision)

```
POST /resolve
  → memoria (service/memory/store.py — LTM verificado + procedure_sig, 0ms si hit)
  → backends opcionales (service/backends/, orden fijo o del Director)
  → retrieval + Corroborator (reliability + independencia + recencia, conflict honesto)
  → none / POST /jobs/debate (async, fuera del hot path)
L1 procedure memory = question → trace skeleton (verifiable steps, e.g. handshake n=47 → n*(n-1)/2)
```

Nota: el diagrama histórico de “TruthRouter tiers 1–2c” está retirado; el flujo real es el de arriba.

Connectors are modular: `service/connectors/` — add one file + one line in `config/service.yaml` → auto-registered. Same for models: `service/models/registry.py` — declare MLX or API model → choosable per request.

## Config

`config/service.yaml` controls default connectors, model defaults, memory `similarity_threshold: 0.85` (prevents fall vs cause-of-fall blur), and retriever enablement. Per-request `connectors`/`models` override defaults.

## Private roadmap — reproducible 1→2→3

> Pipeline notes, not a public claim. See `docs/ROADMAP_SERVICE_PRIVATE.md`. Warehouse host and id belong in env, not in this README. Laboratory numbers (`120/120`, `65ms`) are not reproduced by CI.

## Business implementations — monetizable

> 10 private implementations using `POST /resolve` `procedure:trace` + `60/min` key — see **private** `docs/BUSINESS_IMPLEMENTATIONS.md` (investigation IA, test marketplace, fintech, legal, edtech, ops, catalog search, fraud, hiring). Nothing public.

## Tests & validation

The default suite is hermetic: it does not require Databricks, model downloads, the optional `cognitive_swarm` package, or network access.

```bash
# macOS / Linux / Git Bash
BACKENDS=__none__ python -m pytest -q

# Equivalent explicit form
python -m pytest -q
```

On Windows PowerShell, set the optional backend override before running tests:

```powershell
$env:BACKENDS = "__none__"
python -m pytest -q
```

The suite includes API, memory, judgment, curiosity, family, orchestration, and auth/rate-limit regression tests. If the command reports `No module named pytest` or `No module named fastapi`, activate the virtual environment and run:

```bash
python -m pip install -e ".[dev]"
```

Optional scripts that require the private `cognitive_swarm` package or external services are not part of the hermetic CI suite.

## Docker

```bash
docker build -t swarm-service .
docker run --rm -p 8000:8000 swarm-service
```

## Models — choosable per request

`GET /models` lists `phi`/`qwen` (MLX, sequential 8GB) + `minimax-m3` (API, needs `OPENROUTER_API_KEY`). `POST /resolve {models:["phi","qwen"]}` is honored by debate jobs; deterministic tiers never load a model.
