# Emergencia: por qué el todo supera las partes

> Tesis operativa: ningún módulo aquí es brillante. La memoria es un JSON, los
> jueces son regresiones con confianza, la curiosidad muta strings. La
> capacidad está en los **loops entre ellos**: cada salida alimenta otra
> entrada, y el sistema mejora por composición, no por componentes.

## 1. Las partes (ninguna impresiona sola)

| Parte | Qué hace sola | Límite sola |
|---|---|---|
| Reflejos (primitivas+LTM exacta) | responde lo visto, gratis | nada nuevo |
| Juicios (Choice/Score/Noul) | clasifica con prob | taxonomía prestada |
| Curiosidad (mutar+componer) | genera candidatos | mayoria basura |
| Destilación (LoRA) | comprime lo sabido | techo del maestro |
| Corroboración | pesa fuentes | ciega a significado |
| Familias/director | agrupa y rutea | frío sin historia |

## 2. Los loops (aquí vive la emergencia)

```
(1) resolver → archivar → recordar
    Q → Tier0/backends/retrieval → LTM → próxima Q igual cuesta 0
    Medido: PokeAPI r1 0/60 → r2 60/60 memoria, lat 0.16s → 0.00s.

(2) outcome → política de ruteo
    cada resolve registra qué capa acertó (director, por grupo) →
    el orden futuro prefiere lo que funcionó.
    El sistema no solo recuerda respuestas: recuerda CÓMO responder.

(3) puntos ciegos → curiosidad → LTM
    lo que falla verificación se mapea (blind_spots), la curiosidad
    propone alrededor de la ignorancia, lo verificado entra.
    La ignorancia dirige su propia reducción.

(4) LTM → destilación → mejores jueces → mejor ruteo → mejor LTM
    0.855 → 0.880 acc, Brier 0.230 → 0.127 (con T=1.9).
    Primera vuelta cerrada; cada generación entrena con más experiencia.

(5) conflicto → fuentes → resolución
    el desacuerdo honesto de hoy es la respuesta corroborada de mañana
    cuando llega la tercera fuente. El tiempo resuelve.
```

## 3. Por qué la suma no explica el total

Cada loop produce el insumo de otro: (1) llena la memoria que (3) usa de semilla; (2) aprende con outcomes que (4) convierte en pesos; (5) resuelve lo que (1) archivó como conflicto. Ningún módulo "aprende" — **el grafo aprende**. Propiedades que ninguna parte tiene sola:

* **Curva de aprendizaje** (costo por query decae con uso) — medida 2 veces.
* **Holdouts auto-generados** (la curiosidad fabrica su propio examen).
* **Categorías emergentes** (familias sin ontología previa).
* **Automatización calibrada** (70% al 3.6% error — ningún juez solo la firma con esa evidencia).

## 4. Qué lo probaría del todo (falsable)

* Pendiente de cada lunes (timer longitudinal): acc↑ sostenida en set fijo.
* Destilación v2 > v1 en holdout fresco (compounding entre generaciones).
* Federación: instancia B arranca donde A terminó, sin ver sus datos.
* Si en 8 semanas ninguna curva se mueve, la emergencia era retórica. Escrito queda.
