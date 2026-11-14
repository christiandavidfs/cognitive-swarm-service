#!/usr/bin/env python3
"""Memory audit: what is in the store, what is dead, what drifted.

Read-only by default. Uses only the local store (no network).

  python scripts/memory_audit.py                          # summary (pilot LTM)
  python scripts/memory_audit.py --memory data/cost_memory.json
  python scripts/memory_audit.py --replay                  # needs BACKENDS on
  python scripts/memory_audit.py --replay --apply           # quarantine mismatches
  python scripts/memory_audit.py --compact 3 --apply       # trim one-off instances

Why:
  * 2026-11-14 measured 93/322 entries as dead one-off numeric instances. They
    never recur, the oracle recomputes them free, and prune() cannot touch them
    (no outcome history). `--compact` bounds them per procedure_sig.
  * A wrong answer once enshrined is served with confidence 1.0 (incident
    2026-10-19: Japan -> Paris). `--replay` re-runs the oracle against cached
    deterministic answers and quarantines any drift (truth beats cache).
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path as _P

_REPO = _P(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from service.memory.store import ProcedureStore


def print_summary(store) -> dict:
    s = store.summary()
    print(f"entries        : {s['total']}")
    print(f"active         : {s['active']}")
    print(f"quarantined    : {s['quarantined']}")
    print(f"with procedure : {s['with_sig']}   without: {s['without_sig']}")
    print(f"tested         : {s['tested']}   untested: {s['untested']}")
    print(f"by tier        : {json.dumps(s['by_tier'], sort_keys=True)}")

    sigs = Counter(e.get("procedure_sig") for e in store.entries.values()
                   if e.get("procedure_sig"))
    if sigs:
        print(f"procedure sigs : {len(sigs)}  (top: {sigs.most_common(3)})")
    dead = sum(n - 3 for n in sigs.values() if n > 3)
    print(f"trim-able      : {max(dead, 0)} untested one-off instances "
          f"(keep 3 per sig)")
    return s


def replay(store, apply: bool = False) -> int:
    """Re-solve deterministic-tier entries and report disagreements.

    Dry run by default: a mismatch is only quarantined with --apply, because
    some mismatches are ambiguous questions (a two-part question where cache and
    oracle answer different halves), not stale cache.
    """
    from service.backends import load_backends
    from service.router import Router

    backends = load_backends(memory=store)
    if not backends:
        print("replay: no backends installed — nothing to verify against "
              "(run with BACKENDS=cognitive_swarm and PYTHONPATH set)")
        return 1
    router = Router(memory=store, backends=backends)

    def oracle_answer(question):
        for backend in backends:
            try:
                if not backend.signature(question):
                    continue
                ans = backend.solve(question)
            except Exception:
                continue
            if ans is not None and ans.answer is not None:
                return str(ans.answer)
        return None

    checked = mismatch = 0
    for key, entry in list(store.entries.items()):
        if entry.get("status") == "quarantined":
            continue
        question = entry.get("question") or key
        if not router._signature(question):
            continue                       # facts have no oracle to replay
        checked += 1
        verdict = router._replay_check(question, entry)
        if verdict is False:
            mismatch += 1
            print(f"MISMATCH {question!r}\n  cached={entry.get('answer')!r} "
                  f"oracle={oracle_answer(question)!r}")
            if apply:
                store.record_outcome(question, False)
                store.quarantine(question, reason="replay mismatch")
    print(f"replay: checked={checked} mismatches={mismatch} "
          f"({'quarantined' if apply else 'dry run — use --apply to quarantine'})")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--memory", default="",
                    help="memory path (default: data/pilot_memory.json)")
    ap.add_argument("--replay", action="store_true",
                    help="re-run the oracle against cached deterministic answers")
    ap.add_argument("--compact", type=int, default=0, metavar="N",
                    help="keep at most N untested exemplars per procedure_sig")
    ap.add_argument("--apply", action="store_true",
                    help="apply the action (compact drops, replay quarantines); "
                         "default is a dry run")
    args = ap.parse_args()

    path = _P(args.memory) if args.memory else (_REPO / "data" / "pilot_memory.json")
    if not path.exists():
        print(f"no memory at {path}")
        return 2
    store = ProcedureStore(path=path)
    print(f"store: {path}")
    print_summary(store)

    if args.compact:
        if not args.apply:
            sigs = Counter(e.get("procedure_sig") for e in store.entries.values()
                           if e.get("procedure_sig") and not e.get("attempts"))
            would = sum(max(n - args.compact, 0) for n in sigs.values())
            print(f"compact: would drop {would} entries (dry run; use --apply)")
        else:
            dropped = store.compact(max_per_sig=args.compact)
            print(f"compact: dropped {dropped} entries → {store.size()} left")

    if args.replay:
        return replay(store, apply=args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
