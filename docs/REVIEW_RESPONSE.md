# Response to review.md (2026-10-01, main @ current)

> review.md is sharp but stale: it predates recency, curiosity, families,
> the fine-tune loop, and all pilots. Point-by-point status below.

## Already resolved since the review

* **Recency**: shipped (`RECENCY_BONUS`, mtime-fed, solo-voice gate). Sources can no longer be reliable-and-stale without penalty.
* **Curiosity**: built (`service/jobs/curiosity.py`, budget + novelty filter + blind-spot map), not a design.
* **Distillation**: loop closed end-to-end (AG News fine-tune 0.855→0.880, Brier 0.230→0.204, temperature refit → 70% automation @3.6% err). The 2-week-loop concern stands for cadence, not existence.
* **Cold start (knowledge)**: `ingest_corpus.py` ritual + PokeAPI/local connectors; procedure cold start remains (federation).

## Open questions — answered directly

* **Learning vs distribution shift**: fair and still open. Mitigation in place: longitudinal fixed-set design (same questions weekly — shift shows as set drift, learning as slope), plus per-family rates (shift moves families unevenly; uniform improvement smells like learning). Not solved, instrumented.
* **Baseline escalation rate**: PokeAPI rounds (1.00→0.64 retrieval share), longitudinal v1, rounds_log.jsonl. Baselines exist per pilot; no global number yet — needs live traffic.
* **Heuristic thresholds (why not adaptive?)**: intentional conservatism, but already evolving — Director learns routing order from outcomes, families learn group stats, temperature is fitted. Static: the corroboration weights (0.5/0.3/0.9) and 0.85/0.35 match thresholds. Next adaptive candidate: match_threshold per corpus density.
* **Urgent fixes vs 2-week loop**: direct LTM patch (remember/record_outcome) bypasses distillation entirely — the loop is for compression, never for correction. Correction is instant by design.
* **Outcome labeling**: three sources, precedence order — (1) backend verification (deterministic proof, strongest), (2) fresh ground truth feeds (Yahoo/market update loop), (3) user/session outcomes. Heuristics never label alone.
* **Model selection per-request**: operator-chosen today (`connectors`/`models` params + `judge.backend` config); Director stats already rank backends by observed success — automatic selection when N>1 backends with history.

## Still genuinely open (agree with review)

* Federation unbuilt (design only) — the moat is still a bet.
* No third-party traffic — everything measured is self-play.
* Execution velocity on remaining pieces is indeed the biggest risk.

## Verdict on the review

Keep its bottom line, update its inventory: monotonicity + tier discipline remain the moats, and two former "unbuilt" items are now measured loops. The review's best contribution is its questions — adopted as gates in `docs/MEASUREMENTS.md`.
