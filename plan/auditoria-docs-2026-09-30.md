# Auditoría docs ↔ repo (2026-09-30)

> Pregunta auditada: ¿el repo cumple con lo que dice su documentación?
> Método: lectura de `docs/` (4 archivos) + verificación contra el árbol real, `git`, `config/service.yaml`, `service/` y la suite (`BACKENDS=__none__ python -m pytest -q` → **56 passed**).
> Estado del repo al auditar: rama `feat/remediation-phase-0-auth` @ `decd100` (1 commit sin fusionar sobre `main` @ `0cb8cfd`).

## 1. Veredicto global

El **código cumple** con la arquitectura documentada: todos los módulos y mecanismos que los docs prometen existen y funcionan (judgments seam, Director, curiosidad, recencia, familias, conectores con fail-closed, auth fail-closed + rate-limit, LICENSE, 56 tests herméticos, CI). El problema era de **drift documental**: varios docs describían el repo de antes de la decisión standalone (2026-09-30). Todo el drift detectado **ya está reparado en esta auditoría**; los gaps funcionales restantes ya estaban planificados en `plan/remediacion-hallazgos.md`.

## 2. Hallazgos y reparaciones aplicadas

| # | Archivo | Hallazgo (incumplía docs / mentía) | Reparación |
|---|---------|-------------------------------------|------------|
| 1 | `AGENTS.md` | Decía `service/jobs/curiosity_job.py` — el archivo es `curiosity.py` | Corregido |
| 2 | `AGENTS.md` | "Recency is the missing corroboration weight… does not exist" — pero `RECENCY_BONUS` existe en `corroboration.py` (y el propio AGENTS decía "recencia DONE" en otra sección: contradicción interna) | Corregido: peso implementado; asiento Juicio 6 sigue pendiente |
| 3 | `AGENTS.md` | "Curiosity operators 1–2 unbuilt" contradecía "curiosidad DONE" y el código (op1/op2 implementados) | Corregido: op1–2 built, op3 paráfrasis pendiente |
| 4 | `AGENTS.md` | "Branch: main (merged `1c21fd5`)" — obsoleto | Corregido: `main` @ `0cb8cfd` + rama activa de remediación |
| 5 | `README.md` | Referencia rota `docs/ARCHITECTURE.md` (el archivo es `ARCHITECTURE_JUDGMENTS.md`) | Corregido |
| 6 | `README.md` | Bloque de arquitectura con el diagrama retirado "TruthRouter tiers 1–2c" — contradice `ARCHITECTURE_JUDGMENTS.md` y la Fase 2 del plan de remediación | Reemplazado por el flujo real (memoria → backends → corroboración → debate) |
| 7 | `README.md` | "hot path 65ms warm" sin fecha ni caveat | Corregido: etiquetado como medición de laboratorio pre-standalone, no reproducida en CI |
| 8 | `docs/WORKFLOW.md` | Entero desactualizado: rutas `../cognitive-swarm` (prohibidas por la regla standalone de AGENTS), `pytest 8/8` (hay 56), checklist con comandos del core, doc map apuntando a `../cognitive-swarm/AGENTS.md` y docs del core inexistentes aquí | Reescrito completo a standalone (checklist hermético `BACKENDS=__none__`, core marcado como opcional, hook corregido, doc map de este repo) |
| 9 | `docs/ROADMAP_SERVICE_PRIVATE.md` | "Current state 2026-09-18 feat/procedures-40" presentado como estado actual; fases 1→2→3 sin estado | Añadido bloque "State update 2026-09-30" (standalone, procedures-100 DONE, destilación DEFERRED por gate de paráfrasis, vector NOT STARTED); sección vieja marcada HISTORICAL |
| 10 | `docs/ARCHITECTURE_JUDGMENTS.md` | §2 estructura sin `procedure_store.py`, `families.py`, `curiosity.py`; §8 con "Fase 1 DONE (14 tests)" y Fase 2 sin marcar DONE pese a estar hecha | Árbol y §8 actualizados (estados alineados con AGENTS + gate de paráfrasis) |
| 11 | `docs/BUSINESS_IMPLEMENTATIONS.md` | Referencia `student_trace.py:25` — el archivo vive en el paquete core opcional, no en este repo | Corregido con la aclaración |
| 12 | `docs/BUSINESS_IMPLEMENTATIONS.md` | Referencia de línea `service/app.py:55` — el bloque auth se movió (hoy línea ~58+, helpers puros en 128–173) | Corregido: referencia por nombre de funciones, no de línea frágil |
| 13 | `plan/remediacion-hallazgos.md` | Sin marca de progreso | Añadido bloque de estado: Fase 0+1 hechas (`decd100`), parte documental de Fase 2 aplicada aquí |

## 3. Verificaciones positivas (docs ↔ código: CUMPLE)

* `contracts.py`: `TaskType`, `SourceClaim`, `Verdict`, `Resolution`, `Connector(ABC)`, `ResolverBackend(ABC)` ✓
* Primitivas Choice/Score/Noul en `judgments/primitives.py`; Juicio 1 configurable vía `judge.backend` (heuristic/Jev/Kev) ✓
* `orchestrator/director.py` + `tests/test_orchestrator.py` ✓
* `memory/store.py` (sig, attempts/successes, `record_outcome`, `prune`), `session.py` (STM), `procedure_store.py`, `families.py` ✓
* `jobs/curiosity.py` op1–2 con budget/novedad; `jobs/debate_job.py` fuera del hot path ✓
* Recencia como peso en `corroboration.py` (`RECENCY_BONUS`) ✓
* Conectores: wikidata/openalex/local_docs/databricks_sql activos; confluence/postgres/generic_http stubs; `${VAR}` sin expandir falla cerrado ✓
* Umbrales: memoria `0.85`, local_docs `0.35` en `config/service.yaml` ✓
* Auth fail-closed + bucket key + rate-limit 60/min; helpers puros `expand_api_keys`/`bucket_key`/`auth_decision` ✓
* `.env.example` sin secretos; sin host/warehouse reales en el repo (solo en la evaluación citándolos como hallazgo y en tests que afirman su ausencia) ✓
* LICENSE, `.gitignore` cubre `data/`, CI = `py_compile` + pytest hermético ✓
* Scripts mencionados existen: `ingest_corpus.py`, `bench_paraphrase.py`, `measure_jev_classify.py`, `pilot_agnews.py`, `seed_databricks.py` ✓
* 56/56 tests en `BACKENDS=__none__` ✓ (verificado en esta sesión)

## 4. Gaps restantes (ya planificados — no duplicar)

Fuente única de verdad: `plan/remediacion-hallazgos.md`. Estado al cerrar esta auditoría:

| Fase | Contenido | Estado |
|------|-----------|--------|
| 0 — Fail-closed + purga | auth, fugas, LICENSE | ✅ HECHA (`decd100`) |
| 1 — Tests de regresión | `tests/test_auth_ratelimit.py` | ✅ HECHA (mismo commit) |
| 2 — Verdad documental | README/AGENTS drift + claims fechados | ✅ HECHA (drift en auditoría + claims con caveat/fecha) |
| 3 — Extraer middleware | `app.py` → `http_guard.py` (move puro) | ✅ HECHA (factory + re-exports; 56/56 sin editar tests; app.py 464→287) |
| 4 — Tesis reproducible | Camino A (backend `local_primitives`) o B (honesto) — decisión del autor | ✅ HECHA — Camino B elegido (el fácil primero): `/health` `backends`, extra `backends=[]`, README honesto. Camino A abierto |
| 5 — Pesos como priors + CLI token opt-in | comentarios + flag `DATABRICKS_ALLOW_CLI_TOKEN` | ✅ HECHA (comentarios YAML/corroboration + gate en `databricks.py` + `tests/test_databricks_cli_gate.py` + alias documentado) |
| 6 — Persistencia | gated por medición (freeze) | ⛔ No empezar |

Gaps nuevos detectados en esta auditoría (menores, ya cubiertos por las reparaciones o por el plan):

* Ninguno funcional nuevo. El único gap "de contenido" es el bloque **State update** de `ROADMAP_SERVICE_PRIVATE.md`, que ahora requiere mantenimiento: cada cambio de fase debe actualizar ese bloque (lo pide el checklist de `WORKFLOW.md` §1).
* Recordatorio operativo: el contador de tests en docs ("56 passed") lleva fecha; si la suite crece, actualizar `AGENTS.md` + `WORKFLOW.md` + este plan en el mismo commit (el hook de `WORKFLOW.md` §3 lo exige).

## 5. Verificación posterior

Cambios de esta auditoría son solo `.md` — no tocan código. La suite ya corrida en la sesión da `56 passed` (`BACKENDS=__none__ python -m pytest -q`). Al fusionar `feat/remediation-phase-0-auth` a `main`, CI reproduce lo mismo.