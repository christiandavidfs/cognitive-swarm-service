# Plan: cerrar hallazgos de la evaluación

> **Estado (2026-09-30):** Fase 0 + Fase 1 HECHAS en `feat/remediation-phase-0-auth` (`decd100`: auth fail-closed, bucket key, purge de fugas, LICENSE, `tests/test_auth_ratelimit.py`). Fase 2 HECHA: drift documental cerrado en la auditoría (`plan/auditoria-docs-2026-09-30.md`) + claims fechados/caveats en README. Fase 3 HECHA: middleware extraído a `service/http_guard.py` (move puro, 56/56 tests sin editar assertions, `app.py` 464→287 líneas). Fase 4 HECHA — Camino B (honesto): `/health` expone `backends`, extra `backends = []` en `pyproject.toml`, README sin promesas de tiers sin backend; Camino A (`local_primitives`) queda abierto para subir utilidad. Pendiente: Fase 5 (pesos como priors + CLI token opt-in), Fase 6 (gated por medición).
>
> **Fuente:** `cognitive-swarm-service-evaluacion.md` (re-evaluación 2026-09-30, `HEAD` `0cb8cfd`).
> **Tipo:** plan de remediación. No implementa. No añade capa cognitiva.
> **Reglas del repo que este plan no puede saltarse** (`AGENTS.md`):
> - Freeze: ninguna capa o módulo nuevo sin una medición de que lo existente falla.
> - Tras cada cambio de código: `py_compile` de lo tocado + `BACKENDS=__none__ pytest -q` (debe seguir ≥ 38) + actualizar `AGENTS.md` si el estado de resume cambia.
> - Sin secretos baked, sin imports cruzados, sin paths `../`.
> - Evidencia antes de claims. No reabrir destilación ni monetización.

## Objetivo

Subir el servicio de “POC arrancable cuya tesis no se puede auditar y cuya auth falla abierta” a “POC honesto, fail-closed, sin fugas, con la tesis o bien reproducible o bien explícitamente opcional”.

No es el objetivo desplegar multi-instancia, calibrar pesos con datos que no existen, ni publicar el core privado desde este plan.

## Fuera de alcance

- Redis, Postgres de producción, workers externos. Diferido a la fase 6, y solo si aparece un fallo medido.
- Retomar `scripts/distill_to_qwen.py`. El gate de paráfrasis dijo que no.
- GSM8K / MMLU como requisito de esta remediación. Sin solver público, el número no significaría nada.
- Nuevos juicios, familias, conectores o asientos de Jev.
- Borrar `docs/BUSINESS_IMPLEMENTATIONS.md`. Se etiqueta como pipeline; no se reescribe como prueba.

## Orden

```
Fase 0  seguridad y fugas          bloqueante, diff pequeño, sin diseño nuevo
Fase 1  tests que fijan la fase 0  mismo PR que la fase 0, o el siguiente inmediato
Fase 2  verdad documental          README + AGENTS + claims fechados
Fase 3  extraer middleware         refactor de app.py, cero cambio de comportamiento
Fase 4  tesis reproducible         decisión de producto, un solo camino
Fase 5  pesos como priors          documentación + constante nombrada, no calibración falsa
Fase 6  persistencia               NO empezar. Gate al final
```

Fases 0–2 son el mínimo para que la evaluación deje de marcar bloqueantes de higiene. La 4 es la única que mueve la nota de utilidad.

---

## Fase 0 — Fail-closed y purga

**Problema.** Auth enabled + keys vacías deja pasar. Rate-limit colapsa a `"anon"` si no hay `request.client`. README y docs privados publican host Databricks, warehouse id y rutas de `/Users/kaizen` y `/home/kaizen`. No hay LICENSE.

**Archivos.**

| Archivo | Cambio |
|---|---|
| `service/app.py` | Auth y bucket key. No mover todavía el middleware (eso es fase 3) |
| `README.md` | Quitar host, warehouse id y el curl con URL real. Decir que Databricks sale de env y está disabled si `${...}` no expande |
| `docs/ROADMAP_SERVICE_PRIVATE.md` | Sustituir host, warehouse y rutas absolutas por env y “ruta local del operador” |
| `docs/BUSINESS_IMPLEMENTATIONS.md` | Igual. No repetir el id de warehouse |
| `docs/WORKFLOW.md` | Quitar `/Users/kaizen/repos/...` |
| `AGENTS.md` | Quitar path absoluto del core. Dejar “paquete opcional vía `PYTHONPATH` / pip, no commiteado” |
| `LICENSE` | Añadir una. Si no hay decisión del autor, no inventar MIT: dejar el archivo como `UNLICENSED` explícito o parar y preguntar. Un repo público sin términos es peor que uno que dice “todos los derechos reservados” |

**Cambio de auth** (`service/app.py`, bloque ~149–154).

Comportamiento requerido:

1. `auth.enabled: false` → sin 401 y sin rate-limit (igual que hoy; el POC local no se rompe).
2. `auth.enabled: true` y cero keys tras expandir env → **401 en toda ruta no exenta**, aunque el cliente mande una key. Fail closed. El comentario actual (“allow any key?”) se borra.
3. `auth.enabled: true` y keys no vacías → 401 si falta o no coincide. Igual que hoy cuando las keys sí existen.
4. Bucket key, solo si se llegó a rate-limit:

```python
if provided:
    bucket_key = provided
elif request.client is not None and request.client.host:
    bucket_key = request.client.host
else:
    bucket_key = "anon"
```

No dejar el ternario mezclado con `or`. La precedencia es el bug.

**Purga.** No reemplazar el host real por otro host real. Placeholder `<workspace>.cloud.databricks.com` y `<warehouse-id>`, como ya hace `.env.example`. Buscar en el árbol (incluido este plan y la evaluación) que no quede el host ni el warehouse id literales. La evaluación ya no los repite; el README sí.

**Token CLI.** En esta fase no se rediseña el conector. Sí se documenta en README que `databricks auth token` es opt-in de operador y no un default de producción. El corte del subprocess es fase 5 si se toca el conector; no mezclarlo aquí para mantener el diff de seguridad pequeño. Si se quiere cerrarlo ya: `_fetch_cli_token` solo corre si `DATABRICKS_ALLOW_CLI_TOKEN=1`. Default off. Una request sin token devuelve `[]`, que ya es el fail-soft.

**Hecho cuando.**

- Con auth enabled y `SERVICE_API_KEY` vacío, `POST /resolve` sin key y con key cualquiera → 401.
- Con auth enabled, key válida, y un `Request` cuyo `client` es `None`, dos keys distintas no comparten bucket. (Test de unidad de la función de bucket, no hace falta un socket.)
- `rg` del host y del warehouse id históricos en el repo → 0 hits, salvo un test que afirme que no están en `README.md` / `config/`.
- `LICENSE` existe y el README lo enlaza.
- `BACKENDS=__none__ pytest -q` verde.

**Riesgo.** Apagar el CLI token por defecto rompe el POC de quien dependía de `databricks auth` sin env. Mitigación: el flag opt-in, mencionado en README en la misma frase que se borra el curl.

---

## Fase 1 — Tests que impiden la regresión

Van en el mismo cambio que la fase 0, o en el commit siguiente si el diff de docs es grande. No dejar la fase 0 sin test.

**Archivo nuevo:** `tests/test_auth_ratelimit.py`.

No levantar red. Usar `TestClient` como `tests/test_api_resolve.py`, pero con el cache de auth invalidado (`_auth_cache_ts = 0`, `_auth_cache["config"] = None`) para que lea el YAML del tmp o, mejor, extraer las dos funciones puras y testearlas sin YAML:

- `expand_api_keys(raw_keys) -> set`
- `bucket_key(provided, client_host) -> str`
- `auth_decision(enabled, keys, provided, exempt) -> 200 | 401`

Si esas funciones no existen, la fase 0 las crea *dentro* de `app.py` (funciones de módulo). La fase 3 las mueve. No hace falta un paquete nuevo.

Casos mínimos:

| Caso | Esperado |
|---|---|
| enabled, keys vacío, sin header | 401 |
| enabled, keys vacío, header cualquiera | 401 |
| enabled, key correcta | pasa auth |
| enabled, key incorrecta | 401 |
| disabled | pasa, no mira keys |
| path `/health` exento | pasa aunque enabled y sin key |
| `bucket_key("k", None)` | `"k"`, no `"anon"` |
| `bucket_key("", None)` | `"anon"` |
| `bucket_key("", "10.0.0.1")` | `"10.0.0.1"` |

**Hecho cuando.** Esos casos están en CI (`pytest -q` ya los recoge; no hace falta tocar el workflow si el archivo vive en `tests/`).

---

## Fase 2 — Documentos que describen este repo

**Problema.** `README.md` abre diciendo que el core vive en `../cognitive-swarm` y que el hot path es el TruthRouter de tiers 1–2c. `AGENTS.md` dice standalone y, unas secciones más abajo, que la recencia no existe y que curiosidad está en `curiosity_job.py`. Los claims `120/120`, `65ms`, `CV 0.962` no tienen fecha ni artefacto en CI.

**Archivos.** `README.md`, `AGENTS.md`. No reescribir `docs/ARCHITECTURE_JUDGMENTS.md` salvo una línea de “el diagrama de tiers fijos del README está retirado” si ese doc aún apunta al diagrama viejo. Comprobar antes de editar.

**README, reemplazar el bloque de arquitectura** por el flujo real:

```
POST /resolve
  → memoria (store.py)
  → backends opcionales (service/backends/, orden del Director)
  → retrieval + Corroborator
  → none / POST /jobs/debate
```

Quick start debe decir, en este orden:

1. `pip install -e .` arranca memoria + retrieval. `print(2+3)` **no** está garantizado sin backend.
2. Backend determinista: opcional, paquete `cognitive_swarm`, `BACKENDS=cognitive_swarm`. No hay path `../`.
3. Databricks: env, no URL de ejemplo real. Si no hay env, el conector devuelve vacío.

**Claims.** Cada número de laboratorio lleva fecha y script, o sale del README:

- `120/120`, `65ms`, `CV 0.962` → “medición de laboratorio anterior al standalone; no reproducida en CI. No usar como claim.” O borrarlos del README y dejarlos solo en el roadmap privado, fechados.
- Paráfrasis 9/12 y AG News 0.900 se quedan donde ya están (`AGENTS.md`), con la etiqueta que ya tienen (gate no / juez de ruteo, no resolver).

**AGENTS.md, contradicciones a cerrar en el mismo paso** (son drift, no features):

- Recencia: existe (`RECENCY_BONUS` en `corroboration.py`). Quitar “recency does not”.
- Path de curiosidad: `service/jobs/curiosity.py`, no `curiosity_job.py`.
- “Branch: main (merged `1c21fd5`)” está viejo. Apuntar a cómo se resume, no a un SHA intermedio, o actualizar el SHA a `0cb8cfd` y la fecha.

**Hecho cuando.** Un lector del README no concluye que hace falta un checkout hermano para `uvicorn`. `rg "\.\./cognitive-swarm" README.md` → 0. `rg curiosity_job AGENTS.md` → 0.

---

## Fase 3 — Sacar el middleware de `app.py`

**Problema.** La evaluación v1 llamó a `app.py` módulo dios. El router ya salió. Quedan auth, rate-limit y lectura de YAML en el mismo archivo que los endpoints (~407 líneas).

**No es una capa nueva.** Es un move.

**Destino sugerido:** `service/http_guard.py` (o `service/auth.py` si solo se mueve auth+rate-limit). Contiene:

- cache de YAML de auth
- `expand_api_keys`, `bucket_key`, `auth_decision` (las de la fase 1)
- el middleware registrado desde `app.py` con una línea

`app.py` conserva endpoints, `get_memory`, `get_router`. No cambiar status codes ni headers (`429`, `Retry-After`, `X-RateLimit-Limit`).

**Hecho cuando.** Los tests de la fase 1 siguen verdes sin editar assertions. `app.py` baja de forma visible (objetivo: el middleware ya no está inline; no perseguir un número de líneas). `py_compile` de `app.py` y del módulo nuevo.

**No hacer.** No unificar el cache de memoria y el de auth en un framework de config. Dos caches de 30 s están bien. Un loader nuevo sería alcance de más.

---

## Fase 4 — Tesis verificable por un tercero

**Problema.** Utilidad 6/10 y no 8 porque handshake / primitivas / traces verificables no corren en un clone. Este es el único ítem que cambia esa nota.

**Decisión, una de dos. No las dos.**

### Camino A — backend mínimo público en este repo (preferido si el autor puede soltar patrones)

Añadir `service/backends/local_primitives.py`, registrado como `local_primitives`, **apagado por default** para no cambiar el comportamiento de quien ya pone `BACKENDS=cognitive_swarm`.

Alcance máximo, para no violar el freeze con un solver nuevo disfrazado:

- Un backend que implementa `ResolverBackend`.
- Cubre solo los casos que los tests del servicio ya nombran o que el README promete hoy: `print(2+3)` → `5`, aritmética `a+b` trivial, y **un** patrón de procedimiento con `procedure_sig` (handshake), copiado como dato de dominio, no como import del core.
- Tests en `tests/test_local_primitives.py` con `BACKENDS` apuntando a ese nombre.
- README: “sin extras, este backend opcional demuestra process-not-data. El core completo sigue siendo otro paquete.”

Si el patrón handshake es código del repo privado y no se puede copiar, no copiarlo. Camino B.

### Camino B — honesto y opcional (si A no se puede)

- `pyproject.toml` optional-dependency `backends = []` con un comentario de que el paquete no está en PyPI, más `docs` de cómo se activa por path.
- README y `/health` dejan claro `backends: []` cuando no está instalado.
- Ningún ejemplo del README afirma `3828` / `tier: procedure` sin la frase “requiere el backend opcional”.
- No vender el camino B como “tesis reproducible”. La nota de utilidad no sube. La de honestidad sí.

**Hecho cuando (A).** `BACKENDS=local_primitives pytest -q` muestra un hit de procedimiento con números distintos y el mismo `procedure_sig`, sin importar `cognitive_swarm`. CI puede correr ese archivo; no hace falta el core.

**Hecho cuando (B).** Ningún ejemplo de quick start miente. CI sigue en `__none__`.

**No hacer.** No vender el core. No añadir TF-IDF ni Qwen a este backend. Regex antes que cualquier similitud silenciosa, como ya decidió el repo.

---

## Fase 5 — Pesos y CLI token, sin teatro

**Problema.** 0.8 / 0.9 / 1.0 y los bonus 0.5 / 0.3 parecen calibrados. No lo están. El subprocess de Databricks sigue en el path de request.

**Pesos.**

- En `config/service.yaml`, un comentario de tres líneas: estos reliability son priors de POC, no frecuencias medidas. Cambiarlos no es un tuning.
- En `service/corroboration.py`, el comentario de `INDEPENDENCE_BONUS` y `RECENCY_BONUS` dice lo mismo: constantes de desempate, no estimadores.
- No añadir un script de calibración. No hay dataset de conflictos etiquetados. Inventar uno para “cerrar el hallazgo” falsea la evaluación.

**CLI token.** Si no se cerró en la fase 0:

- `_fetch_cli_token` y el barrido de profiles solo si `DATABRICKS_ALLOW_CLI_TOKEN=1`.
- Default: no subprocess. Sin token → `[]` y log debug, como cuando faltan host/warehouse.
- Test: con la env ausente, `get_claims` no llama a `subprocess` (mock). Ya hay patrón de tests sin red.

**Alias.** Renombrar no. En `registry.py`, el comentario de `semantic_scholar` debe decir “alias histórico, no es Semantic Scholar”. Una línea. Opcional: `logger.info` una vez si alguien pide ese nombre. No un conector nuevo.

**Hecho cuando.** Un lector del YAML no puede citar 0.9 como “OpenAlex es 90 % fiable” sin leer que es un prior. Test del conector Databricks no spawnea CLI.

---

## Fase 6 — Persistencia (no empezar)

**Por qué está aquí.** La evaluación v1 y la actual dicen que jobs + rate-limit + JSON no escalan. Cierto. También es cierto que no hay un despliegue que lo esté fallando.

**Gate para abrirla.** Una de estas mediciones, escrita en `AGENTS.md`, no una preferencia:

- se pierde un job de debate en un reinicio que alguien necesitaba, o
- dos procesos detrás de un proxy se pisan el rate-limit o la memoria, o
- el JSON de LTM pasa un tamaño que `remember()` ya no aguanta en el hot path (medir, no adivinar).

Hasta entonces, no SQLite, no Redis, no cola. El freeze lo prohíbe y la evaluación no pide infraestructura de producto: pide no fingir que el deque es un billing system. La fase 2 ya quita ese fingimiento del README.

Si el gate se abre, el cambio mínimo es un solo store (SQLite para LTM **o** para jobs, no los dos a la vez) detrás de la interfaz que ya existe (`ProcedureStore` / `create_job`). Sin servicio nuevo.

---

## Criterio de cierre del plan

| Nota de la evaluación | Sube si |
|---|---|
| Seguridad 5 → 7 | Fases 0 y 1 hechas, fugas en 0 hits, CLI token opt-in |
| Madurez 4 → 5 | Fases 0–3. Sigue siendo un proceso; no prometer más |
| Utilidad 6 → 7 | Solo con fase 4 camino A y tests de `procedure_sig` en CI |
| Potencial 7 | No se mueve con este plan. Se mueve con tráfico real y decay de escalado, que este plan no fabrica |

Cuando 0–3 estén en `main`, actualizar la tabla de la sección 4 de la evaluación y tachar los hallazgos cerrados en la sección 3. No reescribir la evaluación entera otra vez.

## Qué no mezclar en el primer PR

El primer PR es fase 0 + fase 1, nada más.

- No incluye el rewrite largo del README (fase 2 puede ir en el segundo).
- No mueve archivos (fase 3).
- No añade backend (fase 4).
- No toca corroboración (fase 5).

Un PR que “arregla la evaluación” entera no se puede revisar. El bug de auth y la fuga del README sí.
