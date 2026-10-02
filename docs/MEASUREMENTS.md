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

## 2026-10-01 · Market longitudinal (`scripts/longitudinal_market.py`, Yahoo no-key)

* Static PokeAPI measures accumulation; market truth MOVES — this measures the UPDATE loop: stale memory detected, demoted via `record_outcome(False)`, corrected by fresh truth.
* Dry run 2× same day: cold acc=0.0 → populated acc=1.0, stale=0 (market static intraday — staleness appears across weeks, which is the point).
* Timer Wednesdays 06:00 (interleaved). Metric to watch: stale_rate decay with acc steady.

## 2026-10-01 · Formation predictions (`scripts/formations_market.py`, Yahoo no-key)

* Formation = 5-day sign skeleton + MA50 position. Separate books: OBSERVATIONS (always accumulate P(up|formation)) vs PREDICTIONS (gated: trials≥3, |P-0.5|>0.10). No signal → no prediction, never forced.
* First run: 3 families observed, 0 predictions (correct gating with no history). Paper P&L with cost assumption. Timer Fridays 18:00.
* Verdict rule: prediction hit-rate vs base rate net of costs over dozens of trials, or prune the family (and eventually the idea).

## 2026-10-01 · Laya zero-shot (local ONNX CPU, :8000 — ignores --port flag)

* Same slice `test[1000:1200]`, n=200: acc **0.915**, Brier **0.144**, auto@0.9 60/200 err=**0.000**. Sweep: T=0.7 → 113/200 (57%) err=0.009; T=0.8 → 92/200 err=0.000.
* Beats Kev-0.8B base (0.855/0.230) AND our fine-tune w/o temp (0.880/0.204) zero-shot. **Laya takes the routing-judge seat**; Kev-FT+T1.9 stays as fallback/ensemble candidate. Calibration: confidence here is well-behaved out of the box (their temp warning noted, our sweep confirms).
* Ops quirks: `laya-serve` binds :8000 regardless of flags (conflicts with demo API — run demo elsewhere); first run downloads ~421M checkpoint.

## 2026-10-02 · Mastery test (`--opponent minimax --opp-noise 0.5 --explore 0.3→0`)

* 200 games vs half-perfect: win=0.56 loss=0.16 draw=0.28 (unbeaten 0.84), agree=0.647, draws climbing 0.23→0.28 as explore decays.
* Reading: agreement understates strength (many non-losing moves ≠ minimax move); unbeaten rate is the honest metric. Gate: PASS → merged.

* v1 (buggy rotation): 200 games win=0.80 loss=0.14 agree=0.68→0.71, 176 entries.
* **Rotation bug found by a 5-game watch run** (agree 0.36 with 181 entries): canonical key rotated the board but moves stayed in original frame. Fixed (canonical-frame moves both ways) → user-measured agree 0.36→0.88.
* v2 (fixed, clean memory): 200 games win=**0.86** loss=**0.08** agree=0.66 (band noise + explore=0.3 cap; correctness fix proven by the 0.36→0.88 jump, not by the average).
* Watch mode: `--watch 0.4` live board + minimax ✓/✗ markers.

## 2026-10-02 · GBIF slow-domain pilot (`scripts/pilot_gbif.py`, Barn Swallow ES)

* Arrival month (5%-of-peak) 2015–2025, walk-forward per year: procedure/mean/persist MAE=**0.25/0.25/0.25** (tie over 8 years).
* Reading: task too stable to discriminate (wintering records flatten the signal) — pipeline validated end-to-end (fetch→procedure→verify→walk-forward), methods untied. Next: sharper species/region or stricter arrival definition (first steep increase, not 5% threshold).

## 2026-10-02 · Ask intermediary v1 (`scripts/ask.py`, Qwen2.5-1.5B local, read-only tools)

* NL → ReAct (budget 6) → service tools → answer. Measured: pikachu→electric 1 call; rounds board → NL summary 1 call. Fixes needed: fence-less tool syntax accepted, first-output-must-be-tool few-shots, forced-resolve safety net (1/3 clean without them).
* Division honored: model routes/translates, service knows. v2 = connector drafts for human approval.

## 2026-10-02 · StarGen (`scripts/stargen.py`, generate→verify→conserve)

* Qwen-1.5B temp 0.8, 40 traces (20 cases × 2): correct=**8/40**, novel skeletons 8/8 correct, 6 entries. Yield 20%.
* Reading: reasoning quality decent (right formulas), failures are format/arithmetic slips. Verdict: PARTIAL PASS as autonomous background feed (overnight accumulation of verified traces), FAIL as on-demand reasoner. Next levers: lower temp + best-of-N consensus, better format prompts.

## 2026-10-02 · Judge-as-verifier (`scripts/judge_verify.py`, 10 traces)

* Kev-0.8B Noul("is this arithmetic correct?"): agreement **5/10 = chance**, p≈0.80 to EVERYTHING right or wrong. The judge pattern-matches math-looking text, doesn't check it.
* Verdict: FAIL — small judges do NOT verify; debate-as-verifier dead at 0.8B. Formulas stay the only arithmetic oracle. (Retest gate: Laya/OpenDecider on same battery.)

## Open gates

* Escalation-decay CONTINUOUS (rounds exist; need scheduled rounds over time + curiosity).
* ~~Retrieval-at-scale with distractors~~ MEASURED (solo-voice hole fixed).
* **Longitudinal learning proof** (runner + v1 set + Mon timer DONE 2026-10-01, baseline acc=0.50): needs evolving ground-truth set + curve plot.
* **Market longitudinal** (runner + Wed timer DONE 2026-10-01): watch stale_rate decay with acc steady.
* **Paper-trading pilot** (PENDING): user-defined 2–3 setups, streaming loop, paper accounting (positions, costs, net P&L vs buy-and-hold), 4–8 weeks. Without costs it's fiction.
* Kev fine-tune v2 / temperature fitted during training (post-hoc T=1.9 works; native fit is cleaner).
* Laya fine-tune on own labels (export tooling exists on develop; 400+ rows needed) + Laya vs Kev-FT ensemble test.
* Jev-paid vs best local judge on OUR decisions (needs paid key; the script is ready).
* Federated process learning PoC (two local instances sharing only `procedure_sig`s).

## 2026-10-02 · Curiosity op3 chain (procedure synthesis)

* `op3_chain` builds A-THEN-B combined traces verified end-to-end, archived under NEW chain skeletons (`tier: chain`). Tested: chain archived with distinct sig from both parents. Run loop alternates compose/chain. `78/78` green.
