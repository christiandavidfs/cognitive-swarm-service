#!/usr/bin/env python3
"""Gate B step 1 — temperature fitting for LAYA on OUR domain.

The model card is explicit: base checkpoints ship over-confident (ECE 0.466
on laya, dropping to 0.081 after a per-(question-type, option-count) refit).
Do NOT trust raw probabilities — fit on our own labeled decisions first.

Offline by design (no live server needed): consumes a predictions JSONL with
one record per labeled decision:

  {"question_type": "choice", "n_options": 4,
   "probs": {"code": 0.6, "math": 0.2, "reasoning": 0.1, "unknown": 0.1},
   "label": "reasoning"}

  (produce it with scripts/bench_laya.py + --out, or any pilot run)

Grid-searches T per (question_type, option_count) minimizing ECE, reports
Brier alongside, and prints the env line to set. Gate B promotion rule stays
in docs/MEASUREMENTS.md: LAYA promoted only with err@theta <= Kev baseline at
coverage >= baseline — temperature fitting is a prerequisite, not a bonus.

Run:  python scripts/fit_laya_temperature.py predictions.jsonl
"""
import json
import math
import sys
from collections import defaultdict


def _shift(probs: dict, T: float) -> dict:
    """Same transform the adapter applies: p^(1/T), renormalized."""
    shifted = {k: max(0.0, v) ** (1.0 / T) for k, v in probs.items()}
    total = sum(shifted.values())
    if total <= 0:
        n = max(len(probs), 1)
        return {k: 1.0 / n for k in probs}
    return {k: v / total for k, v in shifted.items()}


def _ece(records, T, bins=10):
    """Expected Calibration Error (top-prob vs top-correctness)."""
    buckets = [(0, 0) for _ in range(bins)]  # (sum_conf, n, correct) via lists below
    sums = [0.0] * bins
    ns = [0] * bins
    correct = [0] * bins
    for r in records:
        probs = _shift(r["probs"], T)
        top = max(probs, key=probs.get)
        conf = probs[top]
        b = min(bins - 1, int(conf * bins))
        sums[b] += conf
        ns[b] += 1
        correct[b] += 1 if top == r["label"] else 0
    ece = 0.0
    n_total = sum(ns)
    for b in range(bins):
        if ns[b] == 0:
            continue
        ece += (ns[b] / n_total) * abs(sums[b] / ns[b] - correct[b] / ns[b])
    return ece


def _brier(records, T):
    """Multiclass Brier: mean over records of sum_k (p_k - y_k)^2."""
    total = 0.0
    for r in records:
        probs = _shift(r["probs"], T)
        total += sum((p - (1.0 if k == r["label"] else 0.0)) ** 2 for k, p in probs.items())
    return total / max(len(records), 1)


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: fit_laya_temperature.py predictions.jsonl")
    records = []
    with open(sys.argv[1], encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    if not records:
        raise SystemExit("no records found")

    groups = defaultdict(list)
    for r in records:
        n_opts = r.get("n_options") or len(r["probs"])
        groups[(r.get("question_type", "choice"), n_opts)].append(r)

    print(f"{'type':8} {'opts':5} {'n':5} {'T*':6} {'ECE@T*':8} {'Brier@T*':9} "
          f"{'ECE@1.0':8} {'Brier@1.0':9}")
    recs = []
    grid = [round(x, 2) for x in [i / 20 for i in range(2, 61)]]  # 0.10 .. 3.00
    for (qtype, n_opts), rs in sorted(groups.items()):
        best = min(grid, key=lambda T: (_ece(rs, T), _brier(rs, T)))
        ece_b, brier_b = _ece(rs, best), _brier(rs, best)
        print(f"{qtype:8} {n_opts:<5} {len(rs):<5} {best:<6} {ece_b:<8.3f} "
              f"{brier_b:<9.3f} {_ece(rs, 1.0):<8.3f} {_brier(rs, 1.0):<9.3f}")
        recs.append((qtype, n_opts, best, ece_b, brier_b))
    if recs:
        global_t = sum(t for _, _, t, _, _ in recs) / len(recs)
        print(f"\nRecommended env (per-group avg {global_t:.2f}; prefer per-group "
              f"once the adapter supports it):")
        print(f"  LAYA_TEMPERATURE={global_t:.2f}")
    print("\nRULE: refit on YOUR labeled decisions before trusting LAYA probs — "
          "never promote on the vendor's calibration numbers.")


if __name__ == "__main__":
    main()
