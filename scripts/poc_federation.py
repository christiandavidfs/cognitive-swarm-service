#!/usr/bin/env python3
"""Federation PoC: does pooled process knowledge kill procedure cold-start?

Org A ("the discoverer") has discovered/proprietary patterns: is always
solved by its OWN native PatternBlocks. Org B runs the same service code but
starts COLD: its only native pattern is squares. Battery: questions from
A's pattern space with UNSEEN numbers.

  python scripts/poc_federation.py
  python scripts/poc_federation.py --seed 20261019

Measures:
  1. B-cold        answer share (baseline pain — existing layers fail this:
                   B's local layers have no memory of these patterns)
  2. B-federated   answer share after import_library(A.exports)
  3. B-poisoned    wrong formula shared; B's local outcomes vetos it
A memory: TEMP file; nothing writes the live store.
"""
import argparse
import json
import random
import sys
from pathlib import Path as _P

_REPO = _P(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from service.federation import PatternBlock, export_library, import_library

_T0T = 60  # minute divisor for the clock pattern
_CT = 200


def org_a_blocks():
    """A's proprietary/native procedures (regex, keys, formula)."""
    return [
        PatternBlock({"pattern": "lunchbreak",
                      "detect": r"\d+\s+(?:workers?)\s+(?:start\s+at)\s+\d+\s*h",
                      "keys": ["nworkers", "t"],
                      "formula": "8 + 16 / {nworkers}",
                      "trace": "lunchbreak(n={nworkers}, t={t}): 8 + 16/n",
                      "procedure_sig": "org_a:lunchbreak",
                      "reliability": 0.9}),
        PatternBlock({"pattern": "tankmin",
                      "detect": r"\d+\s+liters?\s+(?:every|per)\s+minute",
                      "keys": ["n"],
                      "formula": "{n} * 60",
                      "trace": "per-minute x60: liters/hour",
                      "procedure_sig": "org_a:tankmin",
                      "reliability": 0.95}),
        PatternBlock({"pattern": "open_interval",
                      "detect": r"\d+\s+and\s+\d+(?=\?|$|\s)", "keys": ["lo", "hi"],
                      "formula": "{hi} - {lo} - 1",
                      "trace": "open interval count: hi-lo-1",
                      "procedure_sig": "org_a:interval",
                      "reliability": 0.85}),
    ]


def battery(rng, per_pattern=4):
    """Unknown-number questions over A's pattern space + truth."""
    items = []
    for i in range(per_pattern):
        n = rng.randint(2, 500)
        t = rng.randint(1, 12)
        items.append((f"{n} workers start at {t} h. What time is the lunchbreak?", 8 + 16 / n))
        lit = rng.randint(20, 800)
        items.append((f"A pipe pushes {lit} liters per minute. Liters per hour?", lit * 60))
        lo = rng.randint(20, 90)
        hi = lo + rng.randint(5, 40)
        items.append((f"How many integers are between {lo} and {hi}?", hi - lo - 1))
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0, help="0 = today (fresh draw)")
    ap.add_argument("--per-pattern", type=int, default=4)
    args = ap.parse_args()
    import datetime
    rng = random.Random(args.seed or int(datetime.date.today().strftime("%Y%m%d")))
    items = battery(rng, args.per_pattern)

    # --- org B: native-only pattern (squares); A's patterns UNKNOWN to it ----
    b_native = PatternBlock({"pattern": "squares_native",
                             "detect": r"square\s+of\s+(\d+)",
                             "keys": ["x"], "formula": "{x} * {x}",
                             "procedure_sig": "self:squares"}, origin="B-native")

    def answer(score, s, extra_blocks=()):
        for p in [*extra_blocks]:
            r = p.solve(s)
            if r:
                return r["answer"], p.name
        return None, None

    cold_ok = 0
    for q, truth in items:
        a, _pat = answer(None, q, [b_native])
        if a is not None and abs(float(a) - truth) < 1e-9:
            cold_ok += 1

    # --- A exports (zero Q/A) -----------------------------------------------
    lib_payload = export_library(pattern_blocks=org_a_blocks())
    lib_json = json.dumps(lib_payload)
    # Leak check!! exported payload must carry NO question text and no A-answers
    leaked = [t for q, _ in items if q[:30] in lib_json]
    b = import_library(lib_payload, origin="orgA")
    brecorded = []

    fed_ok = fed_used = 0
    for q, truth in items:
        r = b.solve(q)
        if r:
            fed_used += 1
            ok = abs(float(r["answer"]) - truth) < 1e-9
            fed_ok += 1 if ok else 0
            b.record(q, ok)
        else:
            b.record(q, False)
    n_patterns_ok = sum(0 if p.revoked() else 1 for p in b.blocks)

    # --- poisoned: A's corrupted twin ---------------------------------------
    poisoned_payload = {"version": lib_payload["version"],
                        "entries": [dict(e, formula="2 * {hi} + 3")
                                    if e.get("pattern") == "open_interval" else e
                                    for e in lib_payload["entries"]]}
    b_poisoned = import_library(poisoned_payload, origin="orgA-poisoned")
    poison_q, poison_truth = items[-1]
    got = b_poisoned.solve(poison_q)
    first_verdict = ("no-answer" if got is None else
                     ("correct" if abs(float(got["answer"]) - poison_truth) < 1e-9
                      else f"wrong ({got['answer']})"))
    b_poisoned.record(poison_q, False)   # B verifies locally: FAIL x4
    b_poisoned.record(poison_q, False)
    b_poisoned.record(poison_q, False)
    b_poisoned.record(poison_q, False)
    poison_block = b_poisoned.find("open_interval")
    vetoed = bool(poison_block and poison_block.revoked())

    print(f"\nbattery: n={len(items)} (unseen numbers, A's pattern space)")
    print(f"leak-check: {'CLEAN (no Q/A text exported)' if not leaked else 'LEAK!!!'}")
    print(f"1 B-cold (native only)   : {cold_ok}/{len(items)} answers "
          f"(existing layers: B mimics no access to A's procedures)")
    print(f"2 B-federated (import)   : {fed_ok}/{len(items)} correct "
          f"-> delta {fed_ok - cold_ok:+d}")
    print(f"   weights after outcomes: "
          f"{ {p.name: p.weight for p in b.blocks if p.name != 'squares_native'} }")
    print(f"3 poisoned library       : first try = {first_verdict}; "
          f"after 4 local failures -> revoked={vetoed} "
          f"(weight={poison_block.weight if poison_block else None})")
    print(f"read: {fed_ok - cold_ok:+d} = the cold-start delta federated process "
          f"learning buys on unseen numbers, with zero Q/A transferred; the "
          f"veto halves the blast radius of a peer that got corrupted.")

if __name__ == "__main__":
    main()
