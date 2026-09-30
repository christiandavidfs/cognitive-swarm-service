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
* **Verdict**: MIXED — promote accuracy, fail calibration gate. No promotion until temperature refit. First complete learn→train→measure loop: the machinery works end to end.

## Open gates (one closed 2026-09-30)

* ~~Escalation-decay curve on live traffic~~ MEASURED (`scripts/pilot_pokeapi.py`, 30 Pokémon × 2 Qs × 2 rounds vs API truth): **round1 acc 60/60 memory_hits 0/60 @0.16s → round2 acc 60/60 memory_hits 60/60 @0.00s**. First direct learning-curve evidence: retrieval cost → 0 on repeat.
* Kev fine-tune on own labels (dataset `data/agnews_kev_1000.jsonl` ready, 1000 balanced rows)
* Jev-paid vs Kev-finetuned on OUR decisions (needs paid key; the script is ready)

## 2026-10-XX · LAYA Gate A (partial, CPU, zero-shot) + Gate B tooling

* **Setup**: official `laya-serve` 0.3.22 (venv `C:\venvs\laya` — Windows long-path
  breaks torch install under the WindowsApps Python), CPU-only, checkpoint
  `convaiinnovations/laya` (english, 421M) downloaded on first use.
* **Harness**: `scripts/bench_laya.py` — same 12 paraphrase CASES as
  `measure_jev_classify.py`, plus coverage@0.9 / err@0.9 per judge.
* **Measured (zero-shot, n=12, partial before CPU latency blew the budget)**:
  heuristic 0/12 · **LAYA zero-shot 2/12** · ensemble 2/12 (secondary=jev
  unavailable without key → single-survivor policy, no arbiter calls fired).
* **Latency on this box: 11–42 s/call on CPU** (vendor claims 193–464 ms on a
  capable CPU; this machine is far below that class). Latency verdict is a
  HARDWARE verdict, not a model verdict — re-measure on RTX 3060 or T4-class.
* **Accuracy verdict**: matches the model card's own honest limits — base
  checkpoints sit near chance zero-shot on typed-decisions (0.362 vendor
  measured; we got 2/12 on OUR harder taxonomy). LAYA is a base to specialise,
  not a zero-shot judge. **Gate A says: do not promote zero-shot** (same shape
  as Kev's 0/12 on our taxonomy — local zero-shot judges only work on natural
  routing tasks like AG News).
* **Vendor claims CONFIRMED live during the run**: `act_probability: 1.0` on
  every answer (issue #185 — no signal; adapter ignores it by default).
* **Gate B tooling landed** (offline, no live server needed):
  - `scripts/export_laya_jsonl.py` — labeled CSV/JSONL → LAYA fine-tune
    records (state + taxonomy question + answer). Record shape is POC; verify
    against the official notebook before training.
  - `scripts/fit_laya_temperature.py` — grid-search T per
    (question_type, option_count) minimizing ECE on a predictions JSONL;
    emits `LAYA_TEMPERATURE=` recommendation. Smoke-tested on synthetic rows.
* **Gate B shortcut discovered**: checkpoint `laya-typed-decisions` is already
  fine-tuned (0.766 vs 0.362 base on the vendor benchmark) and ships in the
  same HF repo (`subfolder="typed-decisions"`). Evaluate IT before spending
  our own fine-tune budget; our own labels (dataset ≥400) still required for
  our taxonomy.
* **Open**: re-run Gate A on GPU hardware; evaluate `typed-decisions`
  subfolder zero-shot; then temperature-fit on OUR labels; promotion rule
  unchanged: err@θ ≤ 0.062 at coverage ≥ 0.73 (Kev baseline).
