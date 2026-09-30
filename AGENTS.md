# AGENTS.md — Cognitive Swarm Service

> Read this before changing code or running experiments. Standalone repo (no sibling checkouts, no cross-imports). This is becoming a **layered cognitive system** (reflexes → judgments → deliberation → external truth), not just a Q&A API. Full vision: `docs/ARCHITECTURE_JUDGMENTS.md`.

## What this service is

POC that exposes a truth hierarchy as `FastAPI` — fully standalone. Contracts in `service/contracts.py`, orchestration in `service/router.py`, corroboration in `service/corroboration.py`, memory in `service/memory/store.py`. Optional deterministic backends plug in via `service/backends/` (`BACKENDS=cognitive_swarm` when that package is installed; service runs without it — memory + retrieval still serve). Adds:

* **Procedure memory** `service/memory/store.py` — `question → trace → answer` with `procedure_sig` (numbers stripped), L1 `tier: procedure` on new numbers. Entries carry learning counters `attempts/successes/first_seen/last_hit` (monotonic — re-remember never resets) + `record_outcome()` + `prune()` (only executes with history).
* **STM sessions** `service/memory/session.py` — per-`session_id` ring buffer `(question, answer, source, trace, outcome)`; `consolidate(session_id, store)` archives only steps with known outcome (failures count via `record_outcome` but aren't enshrined).
* **Pluggable connectors** `service/connectors/registry.py` — `wikidata` + `openalex` + `databricks_sql` (env-driven, no baked secrets; unexpanded `${VAR}` fails closed to disabled) + `local_docs` standalone lexical index (`LOCAL_DOCS_DIR`, default `./retrieval_corpus`) + stubs `confluence`/`postgres`/`generic_http`.
* **First-ingestion ritual** `scripts/ingest_corpus.py` — indexes a corpus dir, reports files/chunks/probe HIT-MISS vs threshold. Kills the *knowledge* cold start day one (procedure cold start remains: curiosity/network).
* **Model registry** `service/models/registry.py` — `phi`/`qwen` MLX (lazy, optional) + `minimax-m3` API, choosable per-request.
* **Thinking matrix async** `service/jobs/debate_job.py` — not on hot path, verifies via backends then `remember_trace`.
* **Hardened API** `service/app.py` + `service/http_guard.py` (fase 3 del plan de remediación: middleware extraído, app.py 464→287 líneas) — Auth (`X-API-Key`/`Bearer`, exempt `/health /docs`) + rate-limit 60/min per key (`429` + `Retry-After`, bounded buckets, cached YAML config), `auth.enabled:false` for POC. When enabled, an empty key set fails closed (401), including callers who sent a key. Rate-limit identity prefers the API key over the client host. CORS `*` with `allow_credentials=False`.

## Thesis (decided, do not relitigate without measurements)

Small models + deterministic patterns + **process memory (not data)** beat big models on operational volume. Code computes (free), models only see irreducible uncertainty, and that zone shrinks as LTM learns. Escalation-rate-to-models over time **is the learning curve** — if it doesn't decay, the thesis loses (falsifiable by design).

## Architecture — layered, brain-mapped

```
POST /resolve → Tier 0 memory → backends (deterministic, in order) → Tier 3 retrieval+corroboration → none/debate
Reflejos (reptiliano: primitivas+LTM exacta, bypass — ningún modelo en el hot path determinista)
Juicios (límbico: service/judgments/ Choice/Score/Noul — solo rutas, nunca respuestas)
Deliberación (neocórtex: debate + reasoners destilados, último recurso)
Director (orquestador pequeño: aprende política de ruteo con outcomes, tras los reflejos, con fallback+unknown)
```

* **Jev placement (5 seats, between tiers, never inside)**: 1 classify, 2 escalate, 3 adjudicate-on-conflict, 4 verify_trace-before-archive, 5 select_backend. Thresholds differ per action risk. Jev is interchangeable — layer works on heuristics.
* **Recency DONE (as weight; Juicio 6 seat still pending)**: `RECENCY_BONUS` in `service/corroboration.py` weights recent claims (anti-cutoff). It is a tie-break constant, not a calibrated estimator.
* **Curiosity (operators 1–2 built; op3 paraphrase unbuilt)**: `service/jobs/curiosity.py` — mutate (numbers/entities, composition) + paraphrase (Qwen only rewords, pending); novelty filter by `procedure_sig`; verification gate (failures = detector blind-spot map); daily budget; ignorance-targeting via `attempts/successes`. Expansion curiosity (BFS over sources) is weaker-grade, lives in retrieval corpus, never contaminates deterministic LTM.
* **Weekly distillation (designed, pipeline unbuilt)**: LTM-export → LoRA → holdout gate (agreement vs deterministic core) → shadow week → promote/rollback. Distillation compresses cache + generalizes phrasing; it never raises the reasoning ceiling.
* **Federated process learning (next-level bet)**: `procedure_sig`s carry zero data → instances can pool libraries across orgs without leaking facts. Kills procedure cold start; creates network-effect moat. Requires versioning + cross-instance success weighting + local veto (all unbuilt).
* **Monotonicity guarantee**: versioned LTM never forgets/regresses (ratchet); model releases do. Never break this.

## Session findings 2026-09-30 (decisions taken)

* Standalone > coupled: repos must never depend on each other (was: `CORE_PATH` hack, `../cognitive-swarm` paths, Dockerfile context `..`). Verified: `10/10` tests with no backends; adapter live-tested vs real core (`print(2+3)→5`, handshake `88→3828`).
* Nothing hardcoded except patterns: secrets/paths via env + `.env.example`; `QUESTION_PATTERNS`/reasoning patterns stay as domain data.
* Regex stays BEFORE TF-IDF: regex fails loud (safe), TF-IDF fails silent (needs signatures). Never invert.
* Retraining verdict: improves latency + paraphrase robustness + cost, NOT reasoning ceiling. Build pipeline only if paraphrase benchmark (TF-IDF/regex vs Qwen on unseen rewordings) shows a real gap.
* Fake-news fit: claim extraction → per-claim corroboration → honest conflict; narrative `procedure_sig`s catch recycled hoaxes. Assistive + human-in-loop only, never autonomous arbiter.
* Commercial: sellable in verticals with measurable ROI (cost/decision + human-escalation rate), not as general AI API. Needs customer-data evals, SLAs, SOC2. Next value unlock = paid pilot with real data, not more architecture.
* Cold start split: knowledge cold start dies day one via ingestion; procedure cold start needs curiosity/network.

## State / how to resume

* **Fase 5 DONE** (2026-09-30): pesos etiquetados como priors de POC, no calibrados (comentario en `config/service.yaml` connectors + `INDEPENDENCE_BONUS`/`RECENCY_BONUS` en `corroboration.py` — constantes de desempate, sin script de calibración). CLI token de Databricks OPT-IN vía `DATABRICKS_ALLOW_CLI_TOKEN=1` — default nunca lanza subprocess, sin token → `get_claims` → `[]` (tests en `tests/test_databricks_cli_gate.py`, subprocess mockeado). Alias `semantic_scholar` documentado como alias histórico (sin `provider:` da OpenAlex) + `logger.info` una vez.
* **Fase 4 = Camino B DONE** (2026-09-30, decisión: el fácil primero): `/health` expone `backends: []` cuando no hay backend opcional; `pyproject.toml` extra `backends = []` documentado (core no está en PyPI, activación solo por path local); README no promete tiers deterministas sin backend. Camino A (`local_primitives`) queda como opción para subir utilidad 6→7 cuando se decida.
* **Branch**: `feat/laya-judge-adjudicate` (desde `main` @ `0464544`).
* **Gate A/B en GPU**: TODO lo necesario está en `docs/LAYA_GPU_RUNBOOK.md` — bench SDK directo (`scripts/bench_laya_sdk.py`, soporta `--checkpoint typed-decisions`, mismas métricas que el piloto Kev, escribe preds JSONL), ruta HTTP del ensemble (`laya-serve` + `bench_laya.py` + `JUDGE_ADJUDICATE=1`), temperature fitting (`fit_laya_temperature.py`, obligatorio) y fine-tune opcional (`export_laya_jsonl.py`). Regla de cierre: err@θ ≤ 0.062 @ coverage ≥ 0.73, resultado a `docs/MEASUREMENTS.md`. Spike Fase LAYA + Juicio 3: `service/judgments/laya.py` (backend open-weights contra el `laya-serve` OFICIAL, SystemOne-shape idéntico a Jev; temperatura de calibración + `unknown` impuesto por el adaptador; `escalate` ignorado por defecto — issue vendor #185, `act_probability` sin señal), `service/judgments/adjudicate.py` (consenso dual-judge min-conf, conflicto → árbitro, árbitro caído → heurística; juez único sobreviviente NO es conflicto; **OFF por defecto** `JUDGE_ADJUDICATE=1`), `scripts/bench_laya.py` (Gate A: mismo harness que measure_jev_classify + coverage/err@θ por juez), `scripts/export_laya_jsonl.py` (Gate B step 0) + `scripts/fit_laya_temperature.py` (Gate B: refit ECE por tipo/opciones, obligatorio — base ships over-confident ECE 0.466). Gate A PARCIAL medido en CPU: LAYA zero-shot 2/12 en nuestra taxonomía (≈ 0.362 vendor en typed-decisions — base near-chance confirmada), latencia CPU 11–42s/call en esta máquina (veredicto de hardware, no de modelo; re-medir en GPU). Atajo Gate B: checkpoint `laya-typed-decisions` ya fine-tuned en el mismo repo HF. Tests: 72/72 (11 nuevos en `tests/test_laya.py`, todo mockeado). Pendiente: Gate A en GPU + evaluar subfolder typed-decisions + temperature-fit sobre labels propias; promoción solo si err@θ ≤ 0.062 a coverage ≥ 0.73 (baseline Kev).
* **Tests**: `BACKENDS=__none__ python -m pytest -q` → **56 passed** locally on 2026-09-30 (prior suite 38 + 18 in `tests/test_auth_ratelimit.py`). The auth suite covers fail-closed keys, bucket identity, public-surface leak guards, and LICENSE presence. With core installed: `BACKENDS=cognitive_swarm`.
* **Roadmap**: Fase 1 DONE (learning memory), Fase 2 DONE (judgments seam), curiosidad DONE, recencia DONE, familias emergentes DONE (tipos degradados a priors). Next: Kev fine-tune on own labels (needs dataset ≥400) → pilot.
* **Pending measurements**: paraphrase gap MEASURED 2026-09-30 (`scripts/bench_paraphrase.py`): regex 9/12 (3 loud misses, 0 silent) vs tfidf 9/12 (fixes 1 miss, adds 1 silent wrong). GATE SAYS NO — distillation deferred. Kev-0.8B local (RTX 3060 6GB, KEV_CUDA_GRAPHS=0, :8019) Juicio 1 MEASURED (`scripts/measure_jev_classify.py`): 0/12 vs our taxonomy — lumps story+numbers into math (conf tracks difficulty). VERDICT: no extend zero-shot on OUR taxonomy. **AG News pilot MEASURED (`scripts/pilot_agnews.py --judge`, n=200, free labels): Kev-0.8B zero-shot accuracy 0.900, Brier 0.176, automated@conf≥0.9 146/200 err=0.062** (author yardstick 5% budget — just above). **Shootout MEASURED 2026-09-30: OpenDecider-nano CPU accuracy 0.815, Brier 0.302, auto@0.9 84/200 err=0.095, 10s/200 calls.** VERDICT: Kev-0.8B keeps the judge seat; OpenDecider relegated to cheap bulk pre-screen (20× faster, worse calibration). Vendor claims (OD> Jev) do not transfer to our tasks — measure, don't trust. Local judges WORK on natural routing tasks; fine-tune JSONL regenerable via the script. Remaining: escalation-decay curve on live traffic.

## Private — nothing public

| Data | Location | Visibility |
|------|----------|------------|
| `testing.swarm_knowledge` raw Q/A | `testing.testing_schema` `ISOLATED` | **Private** |
| `quality_platform` bronze/silver | `quality_platform.*` | **Private**, not queried |
| `swarm_procedures` traces | `testing...swarm_procedures` + `data/verified_memory.json` traces | **Private** (nothing public) |
| `DATABRICKS_HOST/TOKEN` warehouse | env only (`.env.example` has placeholders) | **Private**, never baked |

## Operational facts

* **Python**: brew `python3` (3.14) where available; `python -m pytest` is enough. `cognitive-swarm` is an optional package via `PYTHONPATH` or pip, not committed and not a sibling path in this repo.
* **Scripts**: `seed_databricks.py --verify` (needs env, fails fast), `ingest_corpus.py <dir>` (report only), `seed_procedures.py`/`generate_procedures.py`/`distill_to_qwen.py` need core package (clear error otherwise).
* **Thresholds**: `memory 0.85` (env `MEMORY_SIMILARITY_THRESHOLD`), `local_docs 0.35`, LIKE `%,_,\` escaped + 200-char clamp in databricks queries.
* **Results non-deterministic** for debate only; deterministic tiers reproducible.

## Conventions

* After **every** change: `py_compile` all touched packages + `pytest -q` (must stay `38/38`+) + update this file + `docs/ARCHITECTURE_JUDGMENTS.md` if architecture moved. CI (`.github/workflows/ci.yml`) runs the same on push.
* **Architecture freeze**: no new layer/module without a measurement showing existing layers fail it. Dogfood first (this repo's own issues/traffic as pilot data).
* **Ontology stability**: `TaskType`/families are versioned priors, not truth. Taxonomy changes require re-running all gates; sig-based identity never breaks.
* **Vendor independence**: Kev pinned by revision + checksums where served; judge seam keeps Heuristic/Jev/Kev interchangeable (`judge.backend`). No single-vendor code paths — ever.
* **Evidence before claims**: no monetization or superiority claim without pilot numbers on real data. `docs/BUSINESS_IMPLEMENTATIONS.md` is pipeline, not proof.
* No bare answer: `Resolution(answer, confidence, sources, disagreement, trace)`.
* No cross-repo imports, no `../` paths, no baked secrets — ever. CI-check mentally on each diff.
* Docs: `docs/ARCHITECTURE_JUDGMENTS.md` (vision, public-safe), `docs/MEASUREMENTS.md` (gate log — read before proposing builds), `docs/ROADMAP_SERVICE_PRIVATE.md` (private), `README.md`.
