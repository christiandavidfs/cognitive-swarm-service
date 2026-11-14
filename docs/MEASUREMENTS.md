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

## 2026-10-19 · Judge-as-verifier retest with Laya (gate CLOSED)

* Same battery (`scripts/judge_verify.py`), Laya ONNX-CPU :8021 (`JEV_VIA=typesafe TYPESAFE_BASE_URL=:8021`): **agreement 6/10 = 0.60** (Kev-0.8B measured 5/10). Pattern identical: judges rate fluency, not math — p=0.94 to falsified "2+2=5", p=0.92 to cube-64 wrong variant. Only the machines/widgets trap was caught (p=0.43).
* Verdict: **FAIL, now doubly measured.** Small local judges (0.8B-1.5B scale) do NOT verify arithmetic — final verification stays with formulas/corroboration. Debate-as-verifier hypothesis dead at this scale; loop-judge stays only as cheap pruner (hybrid rerank 9/12 stands).

## 2026-10-19 · Feed-outage hardening (week 2 incident)

* 10-07 market + 10-10 formations hit DNS failures at 06:00 (no network) and logged empty `n=0` rows. Fixed: `service/net.py` shared fetch with backoff; scheduled scripts skip archiving empty rows (outage → cron log only, n=0 row purged). `79/79` green.

## 2026-10-19 · Decay instrument armed (`feat/decay-timer`)

* `rounds_continuous.py` upgraded: live seed (fresh pokemon draws each scheduled run; `--seed` overrides for repro), row gains `escalated_share` (share not served by memory/retrieval = the thesis's falsifiable decay metric), truth/list fetches via `service.net` backoff + no-row-on-total-outage (soup-week rule). Smoke: round1 acc=1.0 memory=0.556 retrieval=0.444 escalated=0.0 entries 64→68.
* Timer `rounds-decay.timer` THU 06:00 (first run 2026-10-22): `--rounds 2 --n 8 --repeats 4`, log `data/rounds_log.jsonl` + `data/rounds_cron.log`. Verdict shape: on the FALSE-THESIS case memory_share flatlines LOW and escalated stays high; on the TRUE case memory_share climbs and escalated share decays. Gate: read after ~4 Thursdays (2026-11-12).

## 2026-10-02 · Hybrid rerank (loop judge + formula, `feat/stargen-hybrid`)

* 12 cases × 4 candidates, Laya-CPU scores plausibility, top-2 verified by formula: **9/12 questions solved**, 9 novel skeletons archived.
* Reading: rerank can't create correctness, but raises precision-per-archive (only verified top-2 enters LTM). Full hybrid stack runs (Qwen GPU + Laya CPU + formula). Ops lesson: VRAM contention (Kev+Laya+Qwen) — Laya forced to CPU via CUDA_VISIBLE_DEVICES, Kev stopped during runs.

## Open gates

* Longitudinal set v2 (`feat/longitudinal-v2`, merged): week-4 row (Mon 2026-10-26) is the first v2 weekly gate; curve verdict week 8.
* Core bug (upstream `cognitive-swarm`): `reasoning_primitives.py:126` answers **"Paris" (conf 1.0) to ANY non-France capital** ("capital of Japan/Brazil"). ~~OPEN~~ **FIXED upstream 2026-10-19** (`hotfix/stock-factual-entity` → core main `f1d4df7`): executor guards Paris to France-only questions; student TF-IDF still misfiles "capital of X" → stock_factual (conf 0.105) but now falls through to `None` → honest retrieval/debate. Bench gate 120/120 unchanged; service 79/79. Capital-X may re-enter curves once a real capital source (corroboration/wikidata) answers them rather than None.
* Metric incident fixed: first v2 baseline row logged `acc_anchors` inflated (fed by anchor+new hits combined, 0.833→later corrected row 0.5 pre-reseed). Log kept append-only; bad row surgically removed and documented here (only removal to date).
* Memory-erasure incident: `pikachu`/`snorlax` entries absent from pilot_memory.json at week 3 (never in git; cause undetermined — possibly `prune()` with history). Reseeded from set gold (`pokeapi:pikachu`=electric, `pokeapi:snorlax`=21) with mirrors of the retrieval-entry schema. Every Monday run re-asks them — silent erasure would now surface as an anchor MISS.
* Probe hygiene: probing with backends on auto-enshrines (a Japan→Paris probe re-wrote a pruned bad entry, twice). Rule: probes run against scratch stores (clone of memory to /tmp), live-memory probes only when enshrinement is intended.
* Escalation-decay CONTINUOUS → instrument revised 2026-11-02 (`feat/decay-metric`): previous rows are NOT comparable (metric invalid). The valid curve starts **Thu 2026-11-05**; read after ~4 points → **2026-12-03**. Do not call 11-12 a verdict.
* ~~Retrieval-at-scale with distractors~~ MEASURED (solo-voice hole fixed).
* **Longitudinal learning proof** (runner + v2 evolving set + Mon timer DONE): v2 set merged 2026-10-26; curve plot + week-8 verdict pending.
* **Market longitudinal** (runner + Wed timer DONE 2026-10-01): watch stale_rate decay with acc steady.
* **Paper-trading pilot** (PENDING): user-defined 2–3 setups, streaming loop, paper accounting (positions, costs, net P&L vs buy-and-hold), 4–8 weeks. Without costs it's fiction.
* Kev fine-tune v2 / temperature fitted during training (post-hoc T=1.9 works; native fit is cleaner).
* Laya fine-tune on own labels (export tooling exists on develop; 400+ rows needed) + Laya vs Kev-FT ensemble test.
* Jev-paid vs best local judge on OUR decisions (needs paid key; the script is ready).
* Federated process learning — contract PoC measured (`feat/federation-poc`, unmerged): cold 0/12 → federated 12/12 zero-Q/A transfer, corrupted peer vetoed after 3 fails. Integration into Router tiers + versioned transport = next gate.

## 2026-10-02 · Curiosity op3 chain (procedure synthesis)

* `op3_chain` builds A-THEN-B combined traces verified end-to-end, archived under NEW chain skeletons (`tier: chain`). Tested: chain archived with distinct sig from both parents. Run loop alternates compose/chain. `78/78` green.

## 2026-10-19 · Search-agent gate PASS (SearXNG live)

* Live SearXNG (docker :8888, json limiter off): direct connector 5 real claims (Wikipedia/ESPN/FIFA, rel 0.6); through router — **answer=None, tier=conflict, 5 candidate clusters solo-voice** → search never judges, honest even with one real answer available. Sandbox live 4/4: cage cwd, write blocked -2 w/o approve, write OK approved, 0 secret leaks in env. Suite 84/84. `feat/search-agent` MERGED to main.
* Ops: local SearXNG needs custom settings.yml (json + limiter:false); container `searxng` persistent with `--restart unless-stopped`; `SEARCH_BASE_URL=http://127.0.0.1:8888` via env (connector fails closed without it, verified).

## 2026-10-26 · Ops incident: timers ran stale code (v1 row + missing decay row)

* **Symptom 1**: Monday 06:00 longitudinal ran **set v1** (acc=0.833) instead of v2, and the notify flashed a "jump" (0.5→0.833) that is NOT learning: pikachu+snorlax were reseeded on Oct 19 (erasure repair), so v1 went 3/6→5/6. Cause: the timer executes whatever is checked out in the repo dir; the repo sat on `feat/federation-poc` (forked from main), and the v2 default lives only on `feat/longitudinal-v2` — unmerged.
* **Symptom 2**: Thursday 2026-10-22 decay run **failed with DNS outage** (`Failed to resolve 'pokeapi.co'`) and left no row. Cause: same checkout issue — main still had the OLD rounds script (no backoff, no outage guard); the fixed version lived only on `feat/decay-timer` — unmerged.
* **Fix**: `feat/longitudinal-v2` + `feat/decay-timer` MERGED to main (docs conflicts resolved, 85/85). `longitudinal.service` now pins `--set evals/longitudinal_set.v2.json` explicitly (fails loud if the set is missing on an old checkout). Repo stays checked out on `main`; any branch switch changes timer behavior (ops rule recorded in AGENTS.md). v2 row re-ran manually today and is the official week-4 point (`docs/LONGITUDINAL.md`).
* **Lesson**: arming a timer whose code lives on an unmerged branch is a measurement bug, not just an ops bug — the row is invalid and must be marked as such. Timers are part of the measurement contract: merge first, then arm.

## 2026-10-29 · Decay instrument — first real row (and a metric flaw found)

* THU run recovered by Persistent after boot (07:02); no outage on the day (the ConnectionError traceback in `rounds_cron.log` is Oct-22 old-code residue — new code has backoff). Rows: round1 `n_new=16 n_rep=4 acc=1.0 memory=0.2 retrieval=0.8 escalated=0.0 entries=84`; round2 `acc=1.0 memory=0.7 retrieval=0.3 escalated=0.0 entries=90`.
* Within-run caching is real and visible: memory 0.2 → 0.7 once repeats hit (latency 0.124s → 0.040s). Cross-run comparable point: `round1 memory_share` on fresh draws = **0.2** (first of its kind; the curve to watch is its growth as the 151-pokemon pool gets covered).
* **Flaw found (important)**: `escalated_share` counts questions answered by neither memory nor retrieval. With `BACKENDS=__none__` and a live feed every question lands in memory or retrieval → structurally **0.0**; when it moves it moves because of *outages*, not models. It does NOT measure the thesis metric (escalation-to-models). The battery is also retrieval-solvable by construction, so a model tier could never be exercised.
* Fix (next branch, before the 2026-11-12 reading): split `memory_share_new` / `memory_share_rep`; rename `escalated_share` → `unanswered_share`; build a separate **model-escalation battery** (contested/analysis questions, debate tier ON) for the real curve. Until then read this instrument as *coverage + outage resilience*, not as the learning curve. Gate: do not claim decay/learning from a flat 0.0. **IMPLEMENTED 2026-11-02 — see below.**

## 2026-11-02 · Longitudinal week 5 (flat, set saturated)

* Row: `acc=0.875 anchors=0.833 new=1.0 contested_ok=1 entries=90 lat=0.81s`. Third identical v2 point (10-19 0.875 → 10-26 0.875 → 11-02 0.875). 7/7 answerable correct, contested stays `None` → **retention + honesty confirmed; no learning signal is possible** on a fixed saturated set (every answerable item is a memory hit).
* Ops: machine was off at 06:00; `Persistent=true` ran the probe at 10:38 on boot. The pinned `--set evals/longitudinal_set.v2.json` worked (correct set executed — the 10-26 incident fix holds).

## 2026-11-02 · Decay metric fixed (`feat/decay-metric`) — gate PASS

* Replaced the structural-zero metric. Old `escalated_share` = "not memory and not retrieval": 0 with a live feed, and with backends on it wrongly counted deterministic hits as escalation.
* New row: explicit buckets (memory / retrieval / deterministic / conflict / escalated), four cohorts — `new` (fresh facts), `rep` (LTM repeats), `proc` (unseen-number procedures), `irr` (irreducible contested/analysis) — per-cohort memory shares, and `escalation_share` = share that reached the model tier (status `none` / tier `debate`).
* Validation (scratch memory + log, live PokeAPI, same battery): `BACKENDS=__none__` → esc=0.571 (proc 6/6 + irr 2 escalated), acc=0.5; `BACKENDS=cognitive_swarm` → esc=0.143 (only the 2 irreducible), acc=1.0, det=0.429. The metric moves exactly with the tier it claims to measure, and retrieval answers do NOT move it (old bug pinned by test).
* Semantics recorded: escalation can only decay to the **irreducible floor** (contested/analysis); the gap to the floor is what procedures/determinism close. `memory_share_new` is the coverage curve; `memory_share_rep` is cache (~1.0 expected). Do not read a flat escalation share at the floor as "no learning" — read `memory_share_new` for coverage.
* Tests: 4 new (`tests/test_rounds_metrics.py`); suite **89/89**. Timer unit switched to `BACKENDS=cognitive_swarm --proc 8`; schema change is safe for `service/results.py` (reads `acc`, passes rows through).
* **Gate date reset**: rows before 2026-11-05 used the broken metric, so they are not curve points. Valid curve starts Thu 2026-11-05; read after ~4 points → **2026-12-03**. The 11-12 date from the 10-19 entry is void.

## 2026-11-05 · Decay first valid rows — escalation starts at the floor

* Rows (new schema, `BACKENDS=cognitive_swarm`): round1 `n=30 acc=1.0 esc=0.067 (2/30) mem_new=0.25 det=0.267 entries=116`; round2 `acc=1.0 esc=0.067 mem_new=0.125 det=0.267 entries=142`.
* Escalation equals **exactly the 2 irreducible items**. Everything answerable was served locally: proc 8/8 deterministic per round (unseen numbers), repeats 4/4 memory, fresh facts 12–14/16 retrieval.
* **Structural finding**: on this battery the model-escalation share has **no dynamic range**. Learnable questions go to determinism/retrieval; irreducible ones go to the model. LTM learning cannot move that floor. So "escalation decays as LTM learns" needs a mechanism that reclassifies tasks into the deterministic/decomposable zone (learned procedures: curiosity op3 / distillation / federation) — or the metric must be reframed as **cost-per-decision on operational volume** (network calls + model calls + CPU per 100 decisions), which is what the commercial claim actually needs.
* LTM composition (2026-11-09): **142 entries = 110 pokemon facts + 24 handshake + 7 print + 1 other**; 119 carry no `procedure_sig`. The cache is 77% facts, and the 31 procedure instances are mostly **dead one-off numeric instances** (random numbers never recur). Process memory is 23 sig-carrying entries. Do not call this "process memory" without a fix: stop enshrining one-off math instances, and schedule prune/audit.
* Open decision: reframe the battery/metric (cost-per-decision + open-evolving task mix) vs build the learned-procedure leg (curiosity op3 scheduled, federation integrated). The current 151-pokemon pool **must saturate** (finite), so it cannot prove indefinite learning.

## 2026-11-09 · Cost per decision (`feat/cost-per-decision`) — gate PASS

* Reframe chosen after the 11-05 structural finding: measure what operations actually pay, not a model zone that is fixed by task type. Metric: **network calls + model calls + CPU per 100 decisions**, on a mix with 60% recurring volume / 20% fresh facts / 10% procedures / 10% open (contested).
* Live run (`BACKENDS=cognitive_swarm`, scratch store, 5 rounds × 100 decisions, live PokeAPI):

| round | net/100 | model/100 | external/100 | CPU ms/dec | memory | acc |
|---|---|---|---|---|---|---|
| 1 | 65 | 10 | **75** | 169 | 0.15 | 1.0 |
| 2 | 37 | 10 | **47** | 66 | 0.43 | 1.0 |
| 3 | 22 | 10 | **32** | 73 | 0.59 | 1.0 |
| 4 | 17 | 10 | **27** | 59 | 0.64 | 1.0 |
| 5 | 16 | 10 | **26** | 46 | 0.65 | 1.0 |

* **External calls/100 decay 75 → 26 (−65%) on recurring volume**, CPU 169 → 46 ms/decision (memory hits bypass the core classifier), accuracy flat 1.0. Model calls pinned at the 10% open share — same irreducible floor measured on 11-05, now confirmed on a different battery.
* Counterfactual (arithmetic, not a measured big model): model-on-everything = **100 model calls / 100 decisions**. At round 5 the system uses 26 external calls total (10 model + 16 network residual from fresh facts). Savings come from memory + code, not from a smaller model.
* Honest caveats: (1) the CPU floor (~46 ms/decision) is real — code is free in money, not in latency; (2) the residual network 16/100 is fresh-fact coverage, finite pool (151) so it decays further then caps; (3) this is a simulated traffic mix, not customer data. The claim it supports is narrow and defensible: **on recurring operational volume, cost per decision decays with memory**.
* Tests: 4 new (`tests/test_cost_per_decision.py`); suite **93/93**. Store is separate (`data/cost_memory.json`) — probes do not touch the longitudinal LTM.

## 2026-11-14 · Cost instrument v2 — fixed pool + warm ceiling (gate PASS)

* Problem found reviewing the 11-12 rows: the recurring pool was re-drawn every run (date seed), so week-to-week rows mixed **learning** with **draw overlap**. The 11-09→11-12 drop (26→21) was partly accumulated facts catching a different pool — not a clean curve.
* Fix: the pool is persisted (`data/cost_pool.json`, created once, reused) and every run ends with an **all-warm round** (pool only, nothing open) that measures the ceiling.
* Measured live (`BACKENDS=cognitive_swarm`, scratch store, 3 rounds + warm):

| run | r1 | r2 | r3 | warm | warm CPU |
|---|---|---|---|---|---|
| A (fresh pool, empty memory) | 72 | 47 | 37 | 15 | 28 ms |
| B (same pool, warm memory) | 24 | 23 | 24 | **0** | **9 ms** |

* **Ceiling confirmed empirically: a fully warm recurring pool costs 0 external calls and ~9 ms/decision.** That is the number the commercial claim is about, and it is not an extrapolation.
* Steady state on the mixed battery = **24/100** (10 model = the open share + 14 network from the still-cold fresh pool). The within-run decay vanishes in run B precisely because the pool is already warm — the instrument now behaves as expected instead of decaying forever.
* Consequence for the weekly series: rows before **2026-11-19** used random pools and are not curve points. With the fixed pool from 11-19 the timer measures a real curve, and the target is stated in advance: external/100 → 24 on the mixed battery, → 0 on warm.
* Tests: 2 new (`test_warm_round_is_pool_only`, `test_pool_is_persisted_and_reused`); suite **95/95**.

## 2026-11-14 · Memory integrity built (`feat/memory-integrity`) — gate PASS

* Born from the 10-19 incident class (Japan→Paris enshrined at confidence 1.0) and from the cost-curve review (29% of the store was dead one-off instances). Four mechanisms, all local:
  1. **Quarantine + self-veto** (`service/memory/store.py`): an entry marked quarantined is never served by any lookup path (exact / signature / similarity) and is never resurrected by a later `remember`. `record_outcome` auto-vetoes after ≥3 attempts with >50% failures. `requalify()` exists but is explicit only.
  2. **Replay drift** (`Router(verify_memory_hits=True)`, **off by default**): a deterministic-tier memory hit is re-solved by the oracle; disagreement quarantines the cache and the oracle answer is served. Truth beats cache, at the cost of one solve per hit.
  3. **Compaction** (`store.compact(max_per_sig=3)`): bounds untested one-off instances per `procedure_sig`, never touches entries with outcome history or facts without a sig.
  4. **Root-cause fix**: the router no longer enshrines trace-less deterministic answers (nothing reusable, the oracle recomputes them free) — growth stops at the source, not just at cleanup.
* Applied to the live stores (backups in `data/backups/`): `pilot_memory` **178 → 156** (−22 dead instances), `cost_memory` **322 → 279** (−43). Facts intact (pikachu/snorlax still served).
* Replay over 36 deterministic entries found **1 mismatch**, and it was not staleness: a two-part question ("First: 20 people… Then: 190 people…") had the second half cached (`17955`) while the oracle answers the first (`190`). Both tiers answer *half* of an ambiguous question at confidence 1.0 → quarantined on live. Lesson recorded: **composed/multi-part questions are unsafe to cache or to serve from any single-answer tier**; the audit's naive equality cannot distinguish ambiguity from drift, so `--replay` is a dry run unless `--apply` is passed.
* Ops: `memory-audit.timer` (Sun 06:00, `Persistent=true`) runs replay `--apply` on the pilot store and compaction on the cost store; log at `data/memory_audit.log`.
* Tests: 10 new (`tests/test_memory_integrity.py`, incl. incident reproduction and composed-question cases); suite **105/105**.
