#!/usr/bin/env python3
"""Layer usage report — the pruning instrument.

Reads Director routing stats + LTM tier distribution and flags prune
candidates: layers that almost never resolve anything over enough traffic.
Architecture is pruned by counts, never by opinion (freeze rule companion).

  python scripts/layer_report.py [--min-uses 20]

RULE: a layer with >=min uses and <5% solve share is a prune candidate.
Layers with <min uses are marked thin-data (not guilty yet).
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path as _P

_REPO = _P(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-uses", type=int, default=20)
    args = ap.parse_args()

    rpath = _REPO / "data" / "routing_memory.json"
    stats = json.loads(rpath.read_text()) if rpath.exists() else {}
    if not stats:
        print("no routing data yet (Director records on every resolve)")
        return

    print(f"{'layer':22} {'uses':>6} {'solved%':>8}  verdict")
    for layer, by_group in sorted(stats.items()):
        uses = sum(n for _, n in by_group.values())
        ok = sum(o for o, _ in by_group.values())
        share = ok / max(uses, 1)
        if uses < args.min_uses:
            verdict = "thin-data (not guilty yet)"
        elif share < 0.05:
            verdict = "PRUNE CANDIDATE"
        else:
            verdict = "keep"
        print(f"{layer:22} {uses:>6} {share:>7.1%}  {verdict}")

    mem_path = _REPO / "data" / "pilot_memory.json"
    if mem_path.exists():
        mem = json.loads(mem_path.read_text())
        tiers = Counter(e.get("tier", "?") for e in mem.values())
        print("\nLTM tiers:", dict(tiers))


if __name__ == "__main__":
    main()
