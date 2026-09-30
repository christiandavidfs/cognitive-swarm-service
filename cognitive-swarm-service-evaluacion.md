# Evaluación: `cognitive-swarm-service`

> **Repo:** https://github.com/christiandavidfs/cognitive-swarm-service
> **Re-evaluación:** 2026-09-30 sobre `HEAD` `0cb8cfd` (56 commits; último merge `feat/critique-mitigation`).
> **Sustituye** la evaluación del 2026-09-18 (1 commit). Esa foto ya no describe el código.
> **Método:** lectura de `AGENTS.md`, `README.md`, `Dockerfile`, CI, `config/service.yaml`, `service/app.py`, `service/router.py`, `service/corroboration.py`, conectores, jobs y tests. Sin re-ejecutar el analizador de calidad que produjo el 47/100 y el 89/100 de la v1 — esos números quedan históricos.

---

## 0. Qué cambió desde la v1

La v1 trataba el repo como un wrapper FastAPI imposible de arrancar sin un core privado en `../cognitive-swarm`. Eso ya no es cierto.

El servicio es standalone. Contratos, router, corroboración y memoria viven en este repo. `cognitive_swarm` es un backend opcional (`BACKENDS=cognitive_swarm`). Sin él, memoria + retrieval + API siguen sirviendo. CI (`.github/workflows/ci.yml`) corre `BACKENDS=__none__ pytest`. El Dockerfile construye desde la raíz de este repo.

Lo que la v1 no podía ver, y hoy es el diseño real:

```
POST /resolve
  → Tier 0 memoria (exacta → firma → similaridad)
  → backends deterministas opcionales, ordenados por el Director
  → Tier 3 conectores + corroboración (reliability + independencia + recencia)
  → none / debate async (no está en el hot path)

Al lado, no dentro de los tiers:
  juicios (Choice/Score/Noul — rutas, nunca respuestas)
  director (política de ruteo por outcomes)
  familias emergentes (tipos degradados a priors)
  curiosidad (ops 1–2) y STM/LTM con attempts/successes
```

La cadena fija “Tier 1 código → 2b string → 2d razonamiento → 2c matemática → 2 calculadora” ya no está en este repo. Vive, si acaso, dentro del backend opcional.

---

## 1. Qué propone ahora

POC FastAPI de jerarquía de verdad, ya no solo un Q&A con cache.

| Pieza | Dónde | Estado |
|---|---|---|
| Contratos (`Resolution`, `SourceClaim`, `ResolverBackend`) | `service/contracts.py` | Propio. Sin respuesta desnuda |
| Router | `service/router.py` | Propio. Memoria → backends → retrieval → debate |
| Corroboración | `service/corroboration.py` | Propia. Conflicto honesto. Bonus de independencia 0.5 y recencia 0.3 |
| Memoria de procedimientos | `service/memory/store.py` | `procedure_sig` (números fuera del trace), contadores monotónicos, `prune()` |
| STM | `service/memory/session.py` | Ring buffer por `session_id`; solo consolida outcomes conocidos |
| Juicios | `service/judgments/` | Heurística por defecto. Jev/Kev intercambiables. Juicio 1 cableado |
| Director | `service/orchestrator/director.py` | Ordena backends con stats; fallback al orden de config |
| Familias | `service/memory/families.py` | Categorías medidas; `TaskType` es prior, no verdad |
| Curiosidad | `service/jobs/curiosity.py` | Ops 1–2 hechas. Paráfrasis (op 3) no es el path por defecto |
| Conectores | `service/connectors/` | Wikidata, OpenAlex, Databricks SQL, `local_docs` vivos en config. Confluence / Postgres / HTTP genérico implementados y `enabled: false` |
| Modelos | `service/models/registry.py` | MLX phi/qwen (lazy) + APIs. No cargan en tiers deterministas |
| Debate | `service/jobs/debate_job.py` | Cola in-process + thread. No Redis |

Tesis (no relitigar sin medición, según `AGENTS.md`): modelos pequeños + patrones deterministas + memoria de *proceso* baten a modelos grandes en volumen operativo. La curva de aprendizaje es la tasa de escalado a modelos. Si no decae, la tesis pierde.

---

## 2. Utilidad

| Aspecto | v1 (2026-09-18) | Hoy |
|---|---|---|
| Idea | Sólida | Sigue sólida. Ahora hay capas medidas (juicios, director, familias, recencia) en vez de solo un diagrama |
| Reproducibilidad | Nula | **Parcial.** Un tercero clona, hace `pip install -e .`, `pytest` y `docker build` sin el core. No puede verificar la tesis determinista (handshake, primitivas, traces) sin instalar `cognitive_swarm`, que no está en `pyproject.toml` y sigue privado |
| Benchmarks del resolver | Auto-reporte `120/120`, `CV 0.962` | Esos números siguen en README/roadmap, sobre corpus propio. No hay GSM8K ni MMLU |
| Benchmarks nuevos | — | Paráfrasis medida (`scripts/bench_paraphrase.py`): regex 9/12 misses ruidosos, TF-IDF 9/12 + 1 error silencioso. **Gate: no destilar.** Piloto AG News n=200 del *juez de ruteo* (accuracy 0.900, Brier 0.176), no de `/resolve` |
| Monetización | Aspiracional | Sigue aspiracional. `docs/BUSINESS_IMPLEMENTATIONS.md` es pipeline, no prueba (`AGENTS.md`) |
| Conectores | Finos; Confluence/Postgres stubs | Wikidata / OpenAlex / Databricks / `local_docs` son reales. Los otros tres tienen código pero están apagados y sin tests de integración |

---

## 3. Madurez: TRL 3–4

Ya no es “un commit que no arranca”. Sigue siendo un POC experimental: un proceso, un JSON, un dict de jobs. CI verde no es un despliegue.

### 3.1 Cerrado desde la v1

| Hallazgo v1 | Evidencia de cierre |
|---|---|
| Core obligatorio para importar / pytest / Docker | `service/router.py` no importa `cognitive_swarm`. Dockerfile: contexto = este repo. CI: `BACKENDS=__none__` |
| YAML releído y parseado en cada request | `service/app.py` cachea auth y umbral de memoria 30 s, invalidando por mtime |
| CORS `*` + `allow_credentials=True` | `allow_credentials=False` (`service/app.py`) |
| SQL sin escape de `%` / `_` | `service/connectors/databricks.py` escapa `'`, `\`, `%`, `_` y trunca a 200 |
| Host y warehouse baked en `config/service.yaml` | YAML usa `${DATABRICKS_HOST}` / `${DATABRICKS_WAREHOUSE_ID}`. `.env.example` tiene placeholders |
| 1 archivo de tests, uno contra Databricks live | 7 archivos, 38 tests herméticos. Ninguno llama a Databricks |
| 1 commit, sin CI, sin versión | 56 commits, `.github/workflows/ci.yml`, `version = 0.1.0` |

### 3.2 Abierto — bloqueantes para que un tercero evalúe la tesis

1. **El diferencial determinista sigue opaco.** Scripts `seed_procedures.py`, `generate_procedures.py`, `distill_to_qwen.py`, `bench_paraphrase.py` importan `cognitive_swarm`. Sin ese paquete, `/resolve` no ejecuta código/matemática/primitivas: clasifica en local y, si no hay backend, cae a retrieval o a `debate`. La cáscara es reproducible; la tesis no.
2. **Sin LICENSE.** No hay términos para un clonador.
3. **Fugas que la v1 señaló y el README no purgó.** `config/service.yaml` ya no lleva el host, pero `README.md` (sección “Databricks — live POC”) publica host y `warehouse_id` reales y afirma que están “baked” en el YAML — eso es falso respecto al YAML actual. `docs/ROADMAP_SERVICE_PRIVATE.md`, `docs/BUSINESS_IMPLEMENTATIONS.md` y `docs/WORKFLOW.md` repiten identificadores y rutas personales (`/Users/kaizen/repos/...`). `AGENTS.md` cita `/home/kaizen/repos/cognitive-swarm`. “Nothing public” sigue contradicho por documentos que el repo distribuye.

### 3.3 Abierto — mayores

| # | Hallazgo | Detalle | ¿Sigue? |
|---|----------|---------|---------|
| 1 | Auth con keys vacías = sin auth | `service/app.py` ~149–152: si `auth.enabled` y `cfg["keys"]` está vacío, no hay 401. El comentario del propio código lo admite | Sí |
| 2 | Precedencia del rate-limiter | Línea `bucket_key = provided or request.client.host if request.client else "anon"` se parsea como `(provided or host) if client else "anon"`. Sin `request.client`, todo cae en `"anon"`. El límite solo corre si auth está enabled | Sí |
| 3 | `app.py` sigue mezclando responsabilidades | ~407 líneas: auth, rate-limit, cache de YAML, wiring del router, schemas HTTP. El router ya se extrajo; el middleware no | Parcial |
| 4 | Infra in-memory | Jobs: dict + `threading.Thread` (`debate_job.py`). Rate-limit: dict de proceso, tope 10k buckets. LTM: un JSON con replace atómico (`store.py`). No sobrevive reinicio de jobs ni varias instancias | Sí |
| 5 | Pesos sin calibración | YAML: wikidata 0.8, openalex 0.9, databricks 1.0, local_docs 0.8. Código: `INDEPENDENCE_BONUS = 0.5`, `RECENCY_BONUS = 0.3`. Recencia está documentada como anti-cutoff; los números siguen siendo priors, no mediciones | Sí, con recencia añadida |
| 6 | Token Databricks por subprocess | `databricks auth token` y `databricks auth profiles` en el conector. Fail-soft, pero depende del CLI local y puede dispararse en el path de una request | Sí |
| 7 | README describe el repo viejo | Primera línea de arquitectura: “Core stays in `../cognitive-swarm`”. El código y `AGENTS.md` dicen lo contrario. Quien lea el README evalúa un sistema que ya no es este | Nuevo, consecuencia del drift |
| 8 | Claims numéricos sin artefacto | `120/120`, `65ms`, `CV 0.962` siguen en README como si fueran el estado actual. El gate de paráfrasis (medido, en `AGENTS.md`) dice no destilar. Esas dos historias conviven sin etiqueta de fecha | Sí |

### 3.4 Abierto — menores

- Alias `semantic_scholar` → `OpenAlexRetriever` en `service/connectors/registry.py`. Confunde el registro.
- Debate: fallback a modelos configurados, pero phi/qwen son MLX (no portables) y el job no persiste.
- `AGENTS.md` se contradice: la sección de arquitectura dice que la recencia “no existe” y que curiosidad está en `curiosity_job.py`; el estado de resume dice recencia DONE y el archivo real es `service/jobs/curiosity.py`.
- No hay CHANGELOG. La versión `0.1.0` no distingue hitos.
- CI instala dependencias a mano y no corre el smoke del Dockerfile. No falla si el README miente.
- Plantilla SQL sigue viviendo en config. Quien edita el YAML controla el statement. Aceptable en POC; no es un conector de producción.
- Postgres declara `psycopg` opcional y hace no-op si falta. No está en `pyproject.toml`.

El score 47/100 de `app.py` y el 89/100 de calidad de la v1 **no se re-ejecutaron**. No citarlos como estado actual.

---

## 4. Veredicto

| Dimensión | v1 | Hoy | Por qué se movió |
|---|---|---|---|
| **Utilidad** | 5/10 | **6/10** | Se puede clonar y correr. El ahorro de LLM y el desacuerdo honesto son reales en el código propio. El diferencial determinista sigue sin poder auditarse |
| **Madurez** | 2/10 | **4/10** | CI, 38 tests herméticos, standalone, secretos fuera del YAML. Sigue POC de un proceso |
| **Seguridad** | 4/10 | **5/10** | CORS y escape SQL cerrados. Auth vacía, rate-limit y fugas del README no |
| **Potencial** | 7/10 | **7/10** | Igual. Hay mediciones que enfrían claims (paráfrasis, AG News del juez). No hay piloto de decay de escalado en tráfico real |

**Resumen:** demo de investigación que ya es un servicio arrancable, no un import roto. Sigue sin ser evaluable de punta a punta por un tercero, y no es desplegable en más de un proceso. El valor sigue en la idea de enrutar por capas y recordar procedimientos — ahora con juicios y un director — no en la API como producto.

---

## 5. Qué haría falta para subir de nota

El plan de ejecución está en `plan/remediacion-hallazgos.md`. Aquí solo el orden, para no duplicar tareas:

1. Cerrar auth fail-closed, el bug de precedencia, la LICENSE y las fugas de README/docs. Tests que fallen si eso regresa.
2. Hacer que README y `AGENTS.md` describan el router actual, y fechar o retirar `120/120` / `CV 0.962`.
3. Decidir cómo un tercero verifica la tesis sin el core privado: extraer un backend determinista mínimo público, o declarar el extra opcional y dejar de implicar que `/resolve` calcula handshakes out of the box.
4. Tratar los pesos como priors documentados. No inventar calibración.
5. No sustituir el JSON/dict por Redis/Postgres hasta que exista un objetivo de despliegue medido. La v1 pedía eso; el freeze de arquitectura de este repo dice que no se añade capa sin una medición de que la actual falla.

---

## 6. Utilidad real fuera de lo que el proyecto auto-atribuye

La sección 6 de la v1 aguanta. Se actualizan las condiciones, no la conclusión.

### 6.1 Cache de procedimientos como ahorro de LLM

Sigue siendo la pieza más aplicable. `procedure_sig` está implementado en `service/memory/store.py`, no solo descrito. La condición de la v1 no cambió: sin el backend que detecta estructura, la reutilización de números nuevos no ocurre en un checkout pelado. Curiosidad (ops 1–2) amplía números y composición *si hay un solver que verifique*. No generaliza a soporte o cláusulas legales.

### 6.2 Destilación desde trazos verificados

El script sigue existiendo y sigue necesitando el core. El gate de paráfrasis del 2026-09-30 dijo que no hay gap que justifique destilar. La salvedad de la v1 (CV sobre corpus propio no valida) queda reforzada: el propio repo aplazó el pipeline. No retomar sin una medición nueva.

### 6.3 Desacuerdo honesto

Implementado en `Corroborator` y cubierto por tests (`test_corroborator_conflict_surfaces_disagreement`, recencia). Útil como comparador de fuentes. No necesita el swarm. Recencia mejora el empate stale-vs-fresh; no convierte los pesos 0.8/0.9/1.0 en evidencia.

### 6.4 Donde no hay utilidad real

| Área | Por qué sigue sin haberla |
|---|---|
| API de pago por llamada | Rate-limit en memoria, jobs en threads, memoria en un JSON. Auth ni siquiera falla cerrado si faltan keys |
| Casos de negocio del doc privado | Siguen colgando de plantillas deterministas que este checkout no ejecuta solo |
| Tier 4 debate | Sigue siendo la pieza menos diferenciada y la menos operable |
| “120/120, 65 ms, 0 cargas” como claim externo | No hay artefacto reproducible en CI. Tratarlo como nota de laboratorio fechada, o quitarlo |

### 6.5 Síntesis

Dos ideas empaquetables, ahora con más código propio alrededor:

1. Cache de procedimientos — utilizable el día que el detector de estructura sea público o instalable.
2. Verificador determinista como filtro de datos — el repo midió que todavía no vale la destilación.

El repo completo es una referencia de diseño de jerarquía + juicios + memoria, ejecutable en la cáscara. No es una librería que un equipo de ML enchufaría mañana, ni un servicio que se pueda cobrar.

---

## 7. Historial de esta evaluación

| Fecha | Base | Nota |
|---|---|---|
| 2026-09-18 | 1 commit | v1. Bloqueante: core privado, import roto, fugas en YAML |
| 2026-09-30 | `0cb8cfd`, 56 commits | Esta revisión. Cáscara reproducible. Tesis y seguridad residual abiertas |
