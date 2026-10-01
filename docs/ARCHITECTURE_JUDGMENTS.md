# Arquitectura: jerarquía de verdad + capa de juicios + memoria dual

> Tesis: la suma de modelos pequeños supera a los modelos enormes enfocándose en
> **patrones deterministas y memoria de razonamiento/procesos, no datos**.
> Lo determinista se computa (gratis). Solo la incertidumbre irreducible usa modelos.
> Y esa zona incierta se achica sola a medida que la memoria aprende.

## 1. Principios

1. **Código primero**: primitivas exactas, memoria exacta, corroboración matemática. Costo ~0, error ~0.
2. **Jev decide rutas, nunca respuestas**: `Choice`/`Score`/`Noul` solo en las costuras inciertas.
3. **Debate de procesos, no de información**: los modelos discuten *cómo* resolver y *quién* decide, no datos (los datos los dirime corroboración con fuentes).
4. **Memoria dual**: corto plazo (sesión, olvidar) + largo plazo (procedimientos verificados + tasa de éxito, podar).
5. **Destilación periódica**: la LTM verificada entrena reasoners pequeños (semanal, versionado, canario).
6. **Verificar antes de archivar**: sin señal de outcome, nada entra a LTM. Sin esto, la memoria aprende mal.
7. **Reflejos con bypass**: memoria exacta y primitivas corren ANTES que cualquier modelo (orquestador incluido). Como el cerebro: la mano se retira del fuego antes de sentir dolor. Ningún modelo puede estar en el hot path determinista.

## 1b. Capas cerebrales (el proyecto, renombrado)

Ya no es "una API de preguntas con memoria": es un **sistema cognitivo por capas**,
cada una con su tarea — `/resolve` es solo la primera instanciación:

* **Reptiliano (reflejos)**: primitivas + LTM exacta. Rápido, sin pensar, sin modelo.
* **Límbico (valoración)**: Jev. Juicios de ruta y confianza, no razonamiento ni ejecución.
* **Neocórtex (deliberación)**: debate + reasoners destilados. Lento, caro, último recurso.
* **Director (orquestador pequeño)**: modelo mínimo que no sabe datos — aprende
  **política de ruteo** (¿qué capa resuelve esto?) solo con outcomes de ruteo.
  Corre DESPUÉS de los reflejos (regla del bypass), con fallback a orden fijo y
  ruta `unknown`. Su training data es dominio cerrado y barato de destilar.

## 2. Estructura (repo standalone, sin dependencias cruzadas)

```
service/
  contracts.py        # TaskType, SourceClaim, Verdict, Resolution, Connector ABC, ResolverBackend ABC
  router.py           # Jerarquía: memoria → backends → retrieval+corroboración → none/debate
  corroboration.py    # Pesos reliability + bonus independencia; conflict honesto, nunca forzado
  judgments/          # [Fase 2 DONE] Capa de juicios: primitives.py (Choice/Score/Noul) + classify.py (heurística) + jev.py (Jev/Kev intercambiable, judge.backend) + laya.py (open-weights decision model sidecar, unknown impuesto por adaptador) + adjudicate.py (Juicio 3 spike: consenso dual-judge + árbitro en conflicto, OFF por defecto)
  orchestrator/       # [Fase 3, esqueleto] director.py: política de ruteo tras reflejos, fallback; política aprendida pendiente
  backends/           # Resolvedores deterministas opcionales (cognitive_swarm, reasoners destilados, …)
  memory/
    store.py          # LTM: question→trace→answer + procedure_sig + attempts/successes + prune
    procedure_store.py # Resolución por procedure (skeleton → nuevo números, mismo sig)
    families.py       # Familias emergentes (tipos degradados a priors, no truth)
    session.py        # STM: ring buffer por session_id, muere con la sesión
  connectors/         # Fuentes Tier 3 (wikidata, openalex, databricks, local_docs, …)
  jobs/
    debate_job.py     # Debate async + consolidación STM→LTM fuera del hot path
    curiosity.py      # Curiosidad: operadores 1–2 (mutación números/composición); op3 paráfrasis pendiente
  models/registry.py  # Modelos percepción/generación (visión, LLMs) como backends API
```

## 3. Flow principal (`POST /resolve`)

```
pregunta
  │ Tier 0: LTM exacta/firma/similaridad → hit? responde (0ms)
  ├─ JUICIO 1 · classify → Choice(code/math/reasoning/unknown)
  │     backends deterministas en orden → resuelve? responde + archiva traza
  ├─ JUICIO 2 · escalate → Score < threshold(riesgo)? → debate async
  ├─ Tier 3: conectores por categoría → corroboración
  │     └─ JUICIO 3 · adjudicate → Noul(dirigible?) si conflict
  ├─ JUICIO 4 · verify_trace → Noul(válida?) antes de archivar a LTM
  └─ JUICIO 5 · select_backend → Choice al haber N backends
```

## 4. Dónde va Jev (5 sillas, entre Tiers, nunca dentro)

| Juicio | Pregunta | Hoy | Con Jev |
|--------|----------|-----|---------|
| 1 classify | ¿qué tipo es? | regex | `Choice` calibrado |
| 2 escalate | ¿merece debate? | threshold fijo | `Score` por riesgo de acción |
| 3 adjudicate | ¿el conflicto se dirime? | siempre None | `Noul` → dirimir o humano |
| 4 verify_trace | ¿se archiva? | sintaxis | `Noul` semántico + outcome |
| 5 select_backend | ¿quién resuelve? | orden fijo | `Choice` por caso |

Regla: thresholds distintos por riesgo (rutear ticket ≠ autorizar irreversible).

## 5. Memoria dual

**STM (sesión)**: últimos N estados + decisiones + outcomes inmediatos. Evita repetir el error de hace 3 ticks y da contexto a Jev. Sin persistencia.

**LTM (procedimientos)**: `{procedure_sig, trace, pattern, attempts, successes}`.
Ciclo: sesión → consolidación async con outcome → promoción condicionada → poda
por éxito bajo o desuso. Sin olvido, la LTM es cementerio.

```
tick caliente: STM (rápido) + LTM por procedure_sig (0ms si hit)
                         └─ solo lo nuevo llega a Jev/modelos
episodio cerrado: STM → LTM en background (verificado) → tasa de escalación decae
```

La tasa de llamadas a modelo en el tiempo **es la curva de aprendizaje medible**.

## 6. Loop de destilación (semanal)

```
LTM verificada (trazas + outcomes)
  → destilación batch → reasoner pequeño vN+1 (question→trace, LoRA)
  → holdout (batch-style) + semana en sombra → releva a vN
  → reasoners proponen procedimientos, Jev juzga cuál/escalar
  → outcomes → LTM → próxima vuelta
```

Condiciones: solo destilar lo verificado (anti-colapso), versionado + canario,
core determinista siempre encendido detrás (si el reasoner propone mal, se
descarta y el fallo es dato). Cada vuelta achica los modelos necesarios:
lo razonado se vuelve memoria, y la memoria un modelo chico la recita.

## 7. Instancias del mismo patrón

**Juego (Tetris)**: código = board/reglas/features; Jev = `Choice(movimiento)` +
`Score(peligro)` + `Noul(seguro)` por tick; LTM = colocaciones verificadas por
`procedure_sig`; timeout con default heurístico. Métrica: líneas/hora vs heurística pura.

**Trading (papel primero)**: código = ejecución + límites de riesgo; Jev juzga
setups; STM = régimen de sesión; LTM = setups con éxito real + decaimiento
temporal agresivo (no-estacionario). Thresholds por tamaño de posición.
Caveat: errores correlacionados en crash; esto da disciplina, no alpha.

**Medicina (solo soporte, jamás autónomo)**: visión = percepción; debate async =
hipótesis + crítica; Jev = `Choice(ruta)` + `Noul(derivar)` + `Score(prioridad)`;
corroboración = convergencia o `conflict` honesto al humano; código = auditoría
regulatoria + evidencia preservada (regiones, quién dijo qué). Calibración en
cuarentena por sitio nuevo. Outcome lento → LTM de pocos casos, altísima calidad.

## 8. Roadmap (revisado: el proyecto es un sistema por capas)

* **Fase 1** — Memoria que aprende: `attempts/successes`, `session.py`, consolidación + poda. DONE (parte de la suite de 56 tests herméticos).
* **Fase 2** — `judgments/` con backend heurístico + Jev/Kev intercambiables (`judge.backend` en `config/service.yaml`). DONE.
* **Fase 3** — Orquestador pequeño tras los reflejos; training = outcomes de ruteo; fallback + `unknown`. Esqueleto DONE (`director.py` + tests); política aprendida con outcomes pendiente.
* **Fase 3b (extra-tesis)** — Curiosidad DONE (operadores 1–2), recencia DONE (peso), familias emergentes DONE (degradadas a priors).
* **Fase 4** — Jev solo en Juicio 1 (configurable vía `judge.seats`); medir agreement / p95 / calibración propia.
* **Fase LAYA (spike, `feat/laya-judge-adjudicate`)** — `judgments/laya.py` (backend open-weights Convai LAYA via sidecar SystemOne-shape, temperatura de calibración + route `unknown` impuesto por el adaptador — LAYA siempre devuelve probs forzadas) y `judgments/adjudicate.py` (Juicio 3: consenso LAYA+secundario, conflicto → árbitro, árbitro caído → heurística loud/safe; conf consenso = min, jamás inflada). Gate A: `scripts/bench_laya.py` + sidecar `scripts/laya_server.py`. Regla de promoción: err@θ ≤ 0.062 (baseline Kev) a coverage ≥ 0.73. Zero-shot LAYA esperado débil (~0.36 vendor) — el valor es post fine-tune sobre etiquetas propias (Gate B).
* **Fase 5** — Destilación semanal + piloto con outcome rápido (juego o papel); medicina solo como triaje tardío. Gate de paráfrasis dijo NO (2026-09-30, `scripts/bench_paraphrase.py`) — destilación diferida.
