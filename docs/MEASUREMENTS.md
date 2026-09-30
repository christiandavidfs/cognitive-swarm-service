# Measurement log — every architectural decision backed by numbers

> Rule: no layer is built, extended, or crowned without a gate measurement.
> A negative gate is a result, not a failure — it is recorded the same way.

## 2026-09-30 · Paraphrase gate (distillation decision)

* **Script**: `scripts/bench_paraphrase.py` · **Task**: 12 same-semantics rewordings → pattern
* **Regex**: 9/12 correct, 3 misses (loud), 0 silent wrongs
* **TF-IDF student**: 9/12 correct — fixes 1 miss ("Sixty coworkers…"), adds 1 silent wrong (`simple_subtract→take_away`, would answer the trick 17 instead of 43)
* **Verdict**: GATE SAYS NO — weekly distillation pipeline deferred. Loud misses are safe; silent wrongs are not. Revisit only if student shows ~zero silent wrongs.

## 2026-09-30 · Juicio 1 vs our taxonomy (Kev-0.8B zero-shot)

* **Script**: `scripts/measure_jev_classify.py` · 12 cases, expected code/math/reasoning/unknown
* **Setup**: Kev-0.8B local, RTX 3060 6GB, `KEV_CUDA_GRAPHS=0`, :8019
* **Result**: 0/12 — lumps every story-with-numbers into `math` (conf 0.18 hard → 0.88 canonical)
* **Reading**: calibration signal is real but labels mismatch OUR taxonomy (is a handshake "math"? fuzzy even for humans). The exam was wrong, not necessarily the student.
* **Verdict**: no extend zero-shot on our taxonomy. Path = fine-tune on own labels (documented Kev recipe, needs ≥400 rows).

## 2026-09-30 · AG News pilot (natural routing, free labels)

* **Script**: `scripts/pilot_agnews.py --judge` · n=200 test rows · Choice(world/sports/business/scitech)
* **Kev-0.8B zero-shot**: accuracy **0.900**, Brier **0.176**, automated@conf≥0.9 **146/200 err=0.062**, 41s, $0
* **Operating point**: T=0.95 → 91/200 automated err=0.044 (inside the 5% budget)
* **Error autopsy**: misses concentrate scitech↔business (tech companies) and ambiguous labels ("wildfire forecast": science or world?) — ground truth is fuzzy too, another vote for distributions over labels
* **Caveats**: n=200 (±4pts); possible pretraining contamination (AG News public since 2004)

## 2026-09-30 · Judge shootout (same 200 rows)

| Judge | acc | Brier | auto@0.9 (err) | time | cost |
|---|---|---|---|---|---|
| Kev-0.8B (GPU) | **0.900** | **0.176** | 146 (0.062) | 41s | $0 |
| OpenDecider-nano (CPU) | 0.815 | 0.302 | 84 (0.095) | 10s | $0 |

* **Verdict**: Kev keeps the judge seat; OpenDecider relegated to cheap bulk pre-screen (20× faster, worse calibration — err 0.095 unfit for auto-routing). Vendor claim (OD > Jev) does not transfer to our tasks.
* **Method lesson**: `--judge` harness accepts any future candidate with zero new code. Measure, don't trust.

## Open gates (one closed 2026-09-30)

* ~~Escalation-decay curve on live traffic~~ MEASURED (`scripts/pilot_pokeapi.py`, 30 Pokémon × 2 Qs × 2 rounds vs API truth): **round1 acc 60/60 memory_hits 0/60 @0.16s → round2 acc 60/60 memory_hits 60/60 @0.00s**. First direct learning-curve evidence: retrieval cost → 0 on repeat.
* Kev fine-tune on own labels (dataset `data/agnews_kev_1000.jsonl` ready, 1000 balanced rows)
* Jev-paid vs Kev-finetuned on OUR decisions (needs paid key; the script is ready)
