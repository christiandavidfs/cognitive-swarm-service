#!/usr/bin/env python3
"""Longitudinal runner: same versioned set, re-asked on schedule.

Tracks accuracy + conflict-resolution over time — the "learn for real" proof:
answering today what was unanswerable, erring less tomorrow. Memory persists
in data/pilot_memory.json; every run appends a dated row to
data/longitudinal_log.jsonl (plot accuracy/conflicts vs date).

Cron (weekly):
  0 6 * * 1 cd /home/kaizen/repos/cognitive-swarm-service && BACKENDS=cognitive_swarm PYTHONPATH=/home/kaizen/repos/cognitive-swarm /home/linuxbrew/.linuxbrew/bin/python3 scripts/longitudinal.py >> data/longitudinal_cron.log 2>&1

  python scripts/longitudinal.py --set evals/longitudinal_set.v1.json
"""
import argparse
import datetime
import json
import sys
import time
from pathlib import Path as _P

_REPO = _P(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from service.connectors.registry import build_retrievers
from service.corroboration import Corroborator
from service.backends import load_backends
from service.memory.store import ProcedureStore
from service.router import Router


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="evals/longitudinal_set.v1.json")
    args = ap.parse_args()

    spec = json.loads((_REPO / args.set).read_text())
    data = _REPO / "data"
    data.mkdir(exist_ok=True)
    mem = ProcedureStore(path=data / "pilot_memory.json")
    backends = load_backends(memory=mem)
    router = Router(memory=mem, corroborator=Corroborator(),
                    retrievers=build_retrievers(enabled_only=True),
                    backends=backends)

    ok = conf = answered = total = 0
    lat = 0.0
    for item in spec["items"]:
        q, exp = item["q"], item.get("a")
        t0 = time.time()
        try:
            r = router.resolve(q)
        except Exception:
            total += 1
            continue
        lat += time.time() - t0
        total += 1
        if exp is None:
            conf += r.tier == "conflict"  # contested honesty tracked separately
            continue
        if r.answer is not None:
            answered += 1
            ok += r.answer.strip().lower() == exp.strip().lower()
    row = {"date": datetime.date.today().isoformat(),
           "set": spec.get("version"),
           "n": total, "acc": round(ok / max(total, 1), 3),
           "answered_share": round(answered / max(total, 1), 3),
           "contested_honest": conf, "lat_avg": round(lat / max(total, 1), 3),
           "memory_entries": mem.size()}
    print(f"{row['date']} v{row['set']}: acc={row['acc']} answered={row['answered_share']} "
          f"contested_ok={conf} lat={row['lat_avg']}s entries={row['memory_entries']}")
    with open(data / "longitudinal_log.jsonl", "a") as f:
        f.write(json.dumps(row) + "\n")


if __name__ == "__main__":
    main()
