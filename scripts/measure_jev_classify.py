#!/usr/bin/env python3
"""Measure Jev Juicio 1 vs heuristic classify (the Jev experiment).

Runs the paraphrase CASES through both classifiers and reports:
agreement, per-question table, Jev latency (mean/p95), and cost if the
API reports usage. Needs TYPESAFE_API_KEY (env, never in repo).

  TYPESAFE_API_KEY=... python scripts/measure_jev_classify.py

Decision rule: extend Jev to Juicios 2-5 only if agreement is high AND
Jev fixes heuristic misses without silent wrongs AND p95 fits budget.
"""
import os
import sys
import statistics
from pathlib import Path as _P

_REPO = _P(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.bench_paraphrase import CASES
from service.judgments.classify import _heuristic_classify

EXPECTED_TASK = {
    "handshake": "reasoning", "stock_take_away": "reasoning",
    "simple_subtract": "reasoning", "work_inverse": "reasoning",
    "stock_moses": "reasoning", "stock_race": "reasoning",
}


def main():
    if not (os.getenv("TYPESAFE_API_KEY") or os.getenv("AI_GATEWAY_API_KEY")):
        raise SystemExit("Set TYPESAFE_API_KEY or AI_GATEWAY_API_KEY (+JEV_VIA=vercel) env first (see .env.example).")
    from service.judgments.jev import timed_classify

    # NOTE: the heuristic seam can only emit code/math/unknown (no pattern
    # knowledge); "reasoning" expected means Jev should see what heuristics can't.
    agree = heur_ok = jev_ok = jev_fixed = jev_regress = 0
    lat = []
    print(f"{'expected':10} {'heur':10} {'jev':10} {'conf':6} {'lat':6} question")
    for q, exp_pat in CASES:
        exp = EXPECTED_TASK.get(exp_pat, "unknown")
        ht, _ = _heuristic_classify(q)
        try:
            jt, jj, dt = timed_classify(q)
        except Exception as e:
            print(f"Jev call failed (fallback would engage): {e}")
            return
        lat.append(dt)
        h_ok, j_ok = ht.value == exp, jt.value == exp
        heur_ok += h_ok
        jev_ok += j_ok
        if not h_ok and j_ok:
            jev_fixed += 1
        if h_ok and not j_ok:
            jev_regress += 1
        mark = "AGREE" if ht.value == jt.value else "DIFF "
        print(f"{exp:10} {ht.value:10} {jt.value:10} {jj.confidence:<6} {dt:<6} {q[:45]} [{mark}]")
    n = len(CASES)
    print(f"\nheuristic correct: {heur_ok}/{n} | jev correct: {jev_ok}/{n} | agreement: {agree}/{n}")
    print(f"jev fixes: {jev_fixed} | jev regressions vs heuristic: {jev_regress}")
    print(f"latency mean {statistics.mean(lat):.2f}s p95 {sorted(lat)[min(len(lat)-1, int(len(lat)*0.95))]:.2f}s")
    print("RULE: extend iff jev_correct > heur_correct with ~zero regressions + p95 in budget.")


if __name__ == "__main__":
    main()
