# Cognitive Swarm Service

> POC: Cognitive Swarm as an API — patterns + truth hierarchy + procedure memory.
> Core stays in `../cognitive-swarm` (`TruthRouter` Tiers 0-4, deterministic primitives, `Corroborator`, `VerifiedMemory`). This service adds a modular connector layer (Wikidata, OpenAlex/Semantic Scholar, DB/Confluence/Databricks stubs), a pluggable model registry, and procedure memory (traces, not just answers).

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

# choose connectors and models per request
curl -X POST http://localhost:8000/resolve -H 'content-type: application/json' \
  -d '{"question":"When did the Western Roman Empire fall?","connectors":["wikidata","openalex"],"models":["phi","qwen"]}'
```

## Architecture (inherits `docs/ARCHITECTURE.md` truth hierarchy)

```
POST /resolve → TruthRouter (Tier 0 memory → 1 code → 2b string → 2d reasoning → 2c math → 2 calc → 3 retrieval → 4 debate)
              Tier 3 = pluggable Retrievers (registry, category-gated, reliability+independence weighted)
              L1 procedure memory = question → trace skeleton (verifiable steps, e.g. handshake n=47 → n*(n-1)/2)
              Tier 4 debate = async job queue (thinking matrix) — not on hot path
```

Connectors are modular: `service/connectors/` — add one file + one line in `config/service.yaml` → auto-registered. Same for models: `service/models/registry.py` — declare MLX or API model → choosable per request.

## Config

`config/service.yaml` controls default connectors, model defaults, and retriever enablement. Per-request `connectors`/`models` override defaults.

## Docker

```bash
docker build -t swarm-service .
docker run --rm -p 8000:8000 swarm-service
# validates: py_compile + truth_router_test --fresh (120/120) before serving
```

## Tests

```bash
pytest -q
pytest tests/test_api_resolve.py -q   # 120/120 via HTTP (mocked external in CI)
```
