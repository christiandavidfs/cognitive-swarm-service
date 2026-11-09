# Longitudinal tracker — 8 Mondays to verdict

> Timer runs Mondays 06:00 (`scripts/longitudinal.timer`). Each row appends to
> `data/longitudinal_log.jsonl`. Verdict at week 8 per `EMERGENCE.md`.

| # | Date | Focus | Row (filled on review) |
|---|------|-------|------------------------|
| 0 | 2026-10-01 (baseline, manual) | v1 set | acc=0.50 answered=0.50 contested_ok=1 |
| 1 | 2026-10-05 | first auto row | acc=0.50 answered=0.50 contested_ok=1 entries=59 (flat vs baseline, honesty intact; memory saturated on fixed set — expected) |
| 2 | 2026-10-12 | memory saturation check | acc=0.50 answered=0.50 contested_ok=1 entries=59 (flat again — set saturated; evolving set needed per plan week 3+) |
| 3 | 2026-10-19 | evolve set → v2 (anchors + 2 new generalization items, `evals/longitudinal_set.v2.json`) | design: 6 v1 anchors unchanged + 2 new items (handshake-20, print(7*6)). Baseline: acc=0.875 anchors=0.833 **new=1.0** contested_ok=1 entries=64. Anchors flat (stability), new pass day-one (primitives generalize over unseen numbers). |
| 4 | 2026-10-26 | slope reading (first trend) | **v2 gate recovered** (manual 11:35; the 06:00 auto row ran v1 by mistake — checkout was on an unmerged branch): acc=0.875 anchors=0.833 **new=1.0** contested_ok=1 entries=68 lat=1.25s. Flat vs v2 day-one (expected: saturated fixed set, new items enshrined day-one). The 06:00 v1 row (0.833) is NOT a curve point — reseed-repair artifact (pikachu+snorlax back), see MEASUREMENTS incident. |
| 5 | 2026-11-02 | curve reading (week 2 of v2) | acc=0.875 anchors=0.833 **new=1.0** contested_ok=1 entries=90 lat=0.81s (ran 10:38 — machine off at 06:00, systemd Persistent caught up). Third identical v2 point (10-19 → 10-26 → 11-02 all 0.875): 7/7 answerable correct + contested honest = **retention confirmed, learning unmeasurable** on a saturated set. See MEASUREMENTS 2026-10-29 for the decay-instrument flaw. |
| 6 | 2026-11-09 | curve reading (week 3 of v2) | acc=0.875 anchors=0.833 **new=1.0** contested_ok=1 entries=142 lat=0.89s. Fourth identical v2 point — set saturated by design (retention only). LTM is now 110 pokemon facts + 31 procedure instances + 1 other: a fact cache, not process memory — see MEASUREMENTS 2026-11-05. |
| 7 | 2026-11-16 | — | — |
| 8 | 2026-11-23 | VERDICT: curves moved or rhetoric | — |

Rules: never conclude before week 4; evolve the set at week 3+ (repeats alone measure cache); if flat at week 8, prune per freeze rule.
