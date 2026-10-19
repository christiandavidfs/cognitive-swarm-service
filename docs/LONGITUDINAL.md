# Longitudinal tracker — 8 Mondays to verdict

> Timer runs Mondays 06:00 (`scripts/longitudinal.timer`). Each row appends to
> `data/longitudinal_log.jsonl`. Verdict at week 8 per `EMERGENCE.md`.

| # | Date | Focus | Row (filled on review) |
|---|------|-------|------------------------|
| 0 | 2026-10-01 (baseline, manual) | v1 set | acc=0.50 answered=0.50 contested_ok=1 |
| 1 | 2026-10-05 | first auto row | acc=0.50 answered=0.50 contested_ok=1 entries=59 (flat vs baseline, honesty intact; memory saturated on fixed set — expected) |
| 2 | 2026-10-12 | steady row | acc=0.50 answered=0.50 contested_ok=1 entries=59 (flat again — set saturated; evolving set needed per plan week 3+) |
| 3 | 2026-10-19 | set v2 day-one | design: 6 v1 anchors unchanged + 2 new generalization items (handshake-20, print(7*6)). Baseline row: acc=0.875, anchors=0.833, **new=1.0**, contested_ok=1, entries=64. Anchors flat (stability), new pass day-one (primitives generalize over unseen numbers). Gate: curve verdict week 8 on evolving set. |
| 2 | 2026-10-12 | memory saturation check | — |
| 3 | 2026-10-19 | evolve set → v2 (new contested items) | — |
| 4 | 2026-10-26 | slope reading (first trend) | — |
| 5 | 2026-11-02 | — | — |
| 6 | 2026-11-09 | — | — |
| 7 | 2026-11-16 | — | — |
| 8 | 2026-11-23 | VERDICT: curves moved or rhetoric | — |

Rules: never conclude before week 4; evolve the set at week 3+ (repeats alone measure cache); if flat at week 8, prune per freeze rule.
