#!/usr/bin/env python3
"""Gate B — temperature fitting for LAYA predictions (offline, no GPU needed).

The model card is explicit: base checkpoints ship over-confident (ECE 0.466
raw → 0.081 after a per-(question-type, option-count) refit). Trusting raw
probs violates our calibration-first policy — this refit is MANDATORY before
any promotion.

Input: predictions JSONL written by scripts/bench_laya_sdk.py (or any file
with {"question_type", "n_options", "probs", "label"} rows).

Method: per group (question_type, n_options), find the temperature T that
minimizes NLL (log-loss) on the group via coarse grid + refinement. T < 1
sharpens, T > 1 flattens. Same transform the adapter applies live
(service/judgments/laya.py: _apply_temperature).

Output: per-group table + the recommended single env line for the dominant
group, e.g.  LAYA_TEMPERATURE=1.20

Usage:
  python scripts/fit_laya_temperature.py data/laya_td_agnews.preds.jsonl
"""
import json
import math
import sys
from collections import defaultdict
from pathlib import Path


def apply_temperature(probs: dict, temperature: float) -> dict:
    shifted = {k: max(0.0, v) ** (1.0 / temperature) for k, v in probs.items()}
    total = sum(shifted.values())
    if total <= 0:
        n = max(len(probs), 1)
        return {k: 1.0 / n for k in probs}
    return {k: v / total for k, v in shifted.items()}


def nll(rows: list, temperature: float) -> float:
    total = 0.0
    for r in rows:
        p = apply_temperature(r["probs"], temperature)
        total -= math.log(max(p.get(r["label"], 0.0), 1e-12))
    return total / max(len(rows), 1)


def fit(rows: list) -> float:
    best_t, best_loss = 1.0, nll(rows, 1.0)
    for t in [0.3, 0.5, 0.7, 0.85, 1.0, 1.2, 1.5, 2.0, 3.0, 5.0]:
        loss = nll(rows, t)
        if loss < best_loss:
            best_t, best_loss = t, loss
    # refine around the winner
    lo, hi = max(0.05, best_t / 2), best_t * 2
    for _ in range(20):
        mid1, mid2 = lo + (hi - lo) / 3, lo + 2 * (hi - lo) / 3
        l1, l2 = nll(rows, mid1), nll(rows, mid2)
        if l1 < l2:
            hi = mid2
        else:
            lo = mid1
    best_t = round((lo + hi) / 2, 2)
    return best_t


def ece(rows: list, temperature: float, bins: int = 10) -> float:
    """Expected calibration error after applying T (confidence = top prob)."""
    bucket = defaultdict(list)
    for r in rows:
        p = apply_temperature(r["probs"], temperature)
        top = max(p, key=p.get)
        conf, ok = p[top], top == r["label"]
        bucket[min(int(conf * bins), bins - 1)].append((conf, ok))
    n = len(rows)
    return sum(len(v) / n * abs(sum(c for c, _ in v) / len(v) - sum(o for _, o in v) / len(v))
               for v in bucket.values() if v)


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    path = Path(sys.argv[1])
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise SystemExit(f"no rows in {path}")

    groups = defaultdict(list)
    for r in rows:
        groups[(r.get("question_type", "?"), r.get("n_options", len(r.get("probs", {}))))].append(r)

    print(f"rows={len(rows)} groups={len(groups)}  ({path.name})")
    print(f"{'question_type':14} {'n_options':>9} {'n':>6} {'T*':>6} "
          f"{'nll_raw':>8} {'nll_fit':>8} {'ece_raw':>8} {'ece_fit':>8}")
    fits = {}
    for key, g in sorted(groups.items()):
        t = fit(g)
        fits[key] = t
        print(f"{key[0]:14} {key[1]:>9} {len(g):>6} {t:>6.2f} "
              f"{nll(g, 1.0):>8.3f} {nll(g, t):>8.3f} "
              f"{ece(g, 1.0):>8.3f} {ece(g, t):>8.3f}")

    dominant = max(groups.items(), key=lambda kv: len(kv[1]))
    t = fits[dominant[0]]
    print(f"\nRECOMMENDED (dominant group {dominant[0]}, n={len(dominant[1])}):")
    print(f"  LAYA_TEMPERATURE={t}")
    print("\nNext: re-run the bench with this env set and evaluate the promotion")
    print("gate on the CALIBRATED numbers (err@0.9 <= 0.062 @ coverage >= 73%):")
    print("  LAYA_TEMPERATURE=%.2f python scripts/bench_laya_sdk.py ..." % t)


if __name__ == "__main__":
    main()
