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

## 2026-09-30 · Fine-tune loop closed (AG News, unseen `test[1000:1200]`, n=200)

* Base Kev-0.8B: acc **0.855**, Brier **0.230**, auto@0.9 132/200 err=0.061
* Fine-tuned (800 rows, 2 epochs, lr 2e-5, 13.5min on RTX 3060): acc **0.880** (+2.5pts), Brier **0.204**, auto@0.9 173/200 err=0.087
* Reading: accuracy AND Brier improve, but automation error worsens (0.061→0.087) — temperature unfitted (1.00 vs base 2.35), i.e. overconfident. The recipe's prescribed next step (fit temperature on heldout) directly addresses it.
* **Verdict**: MIXED → PROMOTED after temperature refit. T=1.9 fitted on slice `test[1000:1200]`, validated on fresh `test[1200:1400]`: acc 0.925, Brier 0.127, operating point moved to T=0.7 → **139/200 automated (70%) err=0.036** (inside 5% budget). `judge.temperature: 1.9` in config. First complete learn→train→calibrate→measure loop: the machinery works end to end.

## 2026-10-01 · Retrieval-at-scale (`scripts/pilot_retrieval_scale.py`, 2000 distractors + 2 golden)

* Gold HIT+RIGHT 2/2 at every threshold 0.2–0.5 (buried gold is found).
* 1/2 negatives leaks at ALL thresholds: fictional-planet question hits a Saturn-moons article (overlap 0.60) — lexical ceiling, no threshold fixes meaning-blindness.
* **Fix shipped**: lone-voice corroboration now requires reliability ≥ 0.9 OR ≥2 independent voices (`SOLO_RELIABILITY`, `service/corroboration.py`). Lexical solo hits → `uncertain` (answer attached, unclaimed); exact solo sources (PokeAPI 0.95) still corroborate. `41/41` green.
* Threshold 0.35 stands. Semantic retrieval (vectors/rerank) remains the real fix — deferred per freeze rule until a gate demands it.

## 2026-10-01 · Continuous rounds (`scripts/rounds_continuous.py`, new+repeats, persistent memory)

* round1: acc=1.0 memory=0.00 retrieval=1.00 lat=0.147s · round2: 1.0 / 0.20 / 0.80 · round3: 1.0 / 0.36 / 0.64 (entries 20→40→56)
* The escalation-decay curve exists over time, not just r1-vs-r2: retrieval share falls as memory absorbs repeats. Accuracy never moves. Log in `data/rounds_log.jsonl` for plotting.

## 2026-10-01 · Longitudinal baseline (`scripts/longitudinal.py`, `evals/longitudinal_set.v1.json`)

* 2026-10-01 v1 (core backend, no network sources): acc=0.50 answered=0.50 contested_ok=1. Cron-ready (line in script docstring). Future runs must show acc↑ via memory+retrieval — that slope IS the "learn for real" proof.

## Open gates

* Escalation-decay CONTINUOUS (PokeAPI was 2 rounds; need rounds over time — HN stream or scheduled rounds + curiosity). The mother metric, still one-shot.
* **Longitudinal learning proof** (runner + v1 set DONE 2026-10-01, baseline acc=0.50): needs cron activation + evolving ground-truth set + curve plot.
* **Paper-trading pilot** (PENDING 2026-10-01): user-defined 2–3 setups, Yahoo Finance streaming loop, paper accounting (positions, costs, net P&L vs buy-and-hold), 4–8 weeks observation. Missing: streaming loop + accounting harness (real build) + setups (user). No shortcuts: without costs it's fiction.
* Kev fine-tune v2 / temperature fitted during training (post-hoc T=1.9 works; native fit is cleaner).
* Jev-paid vs Kev-finetuned on OUR decisions (needs paid key; the script is ready).

* Escalation-decay CONTINUOUS (PokeAPI was 2 rounds; need rounds over time — HN stream or scheduled rounds + curiosity). The mother metric, still one-shot.
* ~~Retrieval-at-scale with distractors~~ MEASURED (see above; solo-voice hole fixed).
* Kev fine-tune v2 / temperature fitted during training (post-hoc T=1.9 works; native fit is cleaner).
* Jev-paid vs Kev-finetuned on OUR decisions (needs paid key; the script is ready).
* Federated process learning PoC (two local instances sharing only `procedure_sig`s; needs partner or self-simulation).
* Serving persistence: demo :8000 + Kev :8019/:8020 run via nohup (die on restart); docker-compose doesn't include the judge; FT checkpoint lives only in `kev-local/runs/`. Promote judge defaults in `config/service.yaml` when ready. (one closed 2026-09-30)

* ~~Escalation-decay curve on live traffic~~ MEASURED (`scripts/pilot_pokeapi.py`, 30 Pokémon × 2 Qs × 2 rounds vs API truth): **round1 acc 60/60 memory_hits 0/60 @0.16s → round2 acc 60/60 memory_hits 60/60 @0.00s**. First direct learning-curve evidence: retrieval cost → 0 on repeat.
* Kev fine-tune on own labels (dataset `data/agnews_kev_1000.jsonl` ready, 1000 balanced rows)
* Jev-paid vs Kev-finetuned on OUR decisions (needs paid key; the script is ready)
