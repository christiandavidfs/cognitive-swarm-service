#!/usr/bin/env python3
"""Market longitudinal: truth that MOVES (Yahoo Finance, no key).

Unlike PokeAPI (static facts → accumulation curve), market answers flip:
this measures the UPDATE loop — stale memory detected, demoted via
record_outcome(False), corrected. Metrics: accuracy, stale-hit rate,
corrections. A falling stale rate with steady accuracy = the system
following a moving world instead of worshipping old answers.

Cron (weekly, Wednesdays to interleave with Monday probe):
  0 6 * * 3 cd ... && BACKENDS=__none__ .../python3 scripts/longitudinal_market.py

  python scripts/longitudinal_market.py
"""
import datetime
import json
import sys
import time
from pathlib import Path as _P

_REPO = _P(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import requests

from service.corroboration import Corroborator
from service.memory.store import ProcedureStore
from service.router import Router

UA = {"User-Agent": "Mozilla/5.0"}


def closes(sym: str, rng: str = "3mo"):
    d = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range={rng}",
                     headers=UA, timeout=15).json()["chart"]["result"][0]
    return [c for c in d["indicators"]["quote"][0]["close"] if c]


def truth_direction(sym: str) -> str:
    c = closes(sym, "8d")
    return "yes" if c[-1] >= c[-6] else "no"


def truth_above_ma50(sym: str) -> str:
    c = closes(sym, "3mo")
    ma = sum(c[-50:]) / min(50, len(c))
    return "yes" if c[-1] >= ma else "no"


TRUTH = {"direction": truth_direction, "above_ma50": truth_above_ma50}


def main():
    spec = json.loads((_REPO / "evals" / "market_set.v1.json").read_text())
    data = _REPO / "data"
    data.mkdir(exist_ok=True)
    mem = ProcedureStore(path=data / "market_memory.json")
    router = Router(memory=mem, corroborator=Corroborator(), retrievers=[], backends=[])

    ok = stale = from_mem = 0
    total = 0
    for sym in spec["symbols"]:
        for t in spec["templates"]:
            q = t["q"].format(sym=sym)
            try:
                fresh = TRUTH[t["kind"]](sym)
            except Exception as e:
                print(f"SKIP {q} (feed error: {e})")
                continue
            total += 1
            r = router.resolve(q)
            hit = (r.answer or "") == fresh
            ok += hit
            if r.status == "memory":
                from_mem += 1
                if not hit:
                    stale += 1
                    try:
                        mem.record_outcome(q, False)  # demote the stale entry
                    except Exception:
                        pass
            # Market truth always wins: correct the record (update loop).
            mem.remember(q, fresh, source="yahoo-finance", tier="retrieval",
                         confidence=0.9, reliability=0.9)
            try:
                mem.record_outcome(q, True)
            except Exception:
                pass
    row = {"date": datetime.date.today().isoformat(), "set": spec.get("version"),
           "n": total, "acc": round(ok / max(total, 1), 3),
           "stale_hits": stale, "from_memory": from_mem,
           "stale_rate": round(stale / max(from_mem, 1), 3),
           "memory_entries": mem.size()}
    print(f"{row['date']} v{row['set']}: n={total} acc={row['acc']} from_mem={from_mem} "
          f"stale={stale} stale_rate={row['stale_rate']} entries={row['memory_entries']}")
    with open(data / "market_log.jsonl", "a") as f:
        f.write(json.dumps(row) + "\n")


if __name__ == "__main__":
    main()
