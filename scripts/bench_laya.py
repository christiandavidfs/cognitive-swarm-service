#!/usr/bin/env python3
"""Gate A — measure LAYA (and the dual-judge ensemble) vs heuristic classify.

Same harness as measure_jev_classify.py so numbers are comparable:
  accuracy per judge | agreement | disagreements→escalations | coverage@0.9
  | err@conf>=0.9 | latency mean/p95.

Needs the OFFICIAL laya server up (pip install "laya[serve]"; LAYA_PRELOAD=1 laya-serve)
and, for the secondary/arbiter legs, the usual Jev config (local Kev on :8019 or TypeSafe).

  LAYA_BASE_URL=http://127.0.0.1:8000 python scripts/bench_laya.py
  # optional: LAYA_SECONDARY=jev + TYPESAFE_API_KEY / Kev base_url

Decision rule (Gate A, docs/MEASUREMENTS.md):
  promote LAYA to seat 1 (with adjudication) only if
    err@theta <= Kev's 0.062 at coverage >= Kev's 73%
  — otherwise LAYA stays documented as not-fit-for-seat-1 and the debate
  ends with a number, not a blog post.
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
AUTO_CONF = 0.9  # same automated-action threshold as the Kev/AG-News pilot


def _err_at_threshold(rows, label):
    """coverage@0.9 and err@0.9 for one judge's rows."""
    auto = [r for r in rows if not r["unknown"] and r["conf"] >= AUTO_CONF]
    cov = len(auto) / max(len(rows), 1)
    err = (sum(not r["ok"] for r in auto) / len(auto)) if auto else float("nan")
    print(f"  {label:12} coverage@{AUTO_CONF}: {len(auto)}/{len(rows)} "
          f"({cov:.0%})  err@{AUTO_CONF}: {err:.3f}")
    return cov, err


def main():
    if not os.getenv("LAYA_BASE_URL"):
        os.environ.setdefault("LAYA_BASE_URL", "http://127.0.0.1:8000")
    from service.judgments.laya import timed_classify
    from service.judgments.adjudicate import adjudicated_classify

    rows = []
    print(f"{'expected':10} {'heur':10} {'laya':10} {'adj':12} {'conf':6} "
          f"{'lat':6} {'src':10} question")
    for q, exp_pat in CASES:
        exp = EXPECTED_TASK.get(exp_pat, "unknown")
        ht, _ = _heuristic_classify(q)
        try:
            lt, lj, dt = timed_classify(q)
        except Exception as e:
            print(f"laya-serve call failed (is `laya-serve` up?): {e}")
            return
        try:
            adj = adjudicated_classify(q)
            at, aj, src = adj.task_type, adj.judgment, adj.source
        except Exception:
            at, aj, src = lt, lj, "laya(fallback)"
        rows.append({"q": q, "exp": exp, "h": ht.value, "l": lt.value,
                     "a": at.value, "conf": aj.confidence, "unknown": aj.unknown,
                     "src": src, "lat": dt, "ok": at.value == exp})
        mark = "AGREE" if ht.value == lt.value else "DIFF "
        print(f"{exp:10} {ht.value:10} {lt.value:10} {at.value:12} "
              f"{aj.confidence:<6} {dt:<6} {src:10} {q[:38]} [{mark}]")

    n = len(rows)
    h_ok = sum(r["h"] == r["exp"] for r in rows)
    l_ok = sum(r["l"] == r["exp"] for r in rows)
    a_ok = sum(r["ok"] for r in rows)
    dis = sum(r["h"] != r["l"] for r in rows)
    esc = sum(r["src"] == "arbiter" for r in rows)
    lat = [r["lat"] for r in rows]
    print(f"\nn={n}  heuristic {h_ok}/{n}  laya {l_ok}/{n}  ensemble {a_ok}/{n}")
    print(f"heuristic-vs-laya disagreements: {dis}  arbiter escalations: {esc}")
    print(f"latency mean {statistics.mean(lat):.3f}s "
          f"p95 {sorted(lat)[min(n - 1, int(n * 0.95))]:.3f}s")
    print("coverage/err at automated threshold:")
    for label, key in (("heuristic", "h"), ("laya", "l"), ("ensemble", "a")):
        sub = [{"ok": r[key] == r["exp"], "conf": r["conf"], "unknown": r["unknown"]}
               for r in rows]
        _err_at_threshold(sub, label)
    print("\nGATE A RULE: promote iff ensemble err@theta <= 0.062 "
          "at coverage >= 0.73 (Kev baseline). Else: not fit for seat 1.")


if __name__ == "__main__":
    main()
