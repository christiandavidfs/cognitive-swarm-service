#!/usr/bin/env python3
"""Continuous rounds: the learning curve over time (the mother metric).

Each round mixes NEW questions (unseen Pokemon, retrieval must work),
REPEATS (memory must serve, cost → 0) and CURIOSITY items (engine proposes
from verified LTM). Memory persists in data/pilot_memory.json across runs;
every round appends to data/rounds_log.jsonl for curve plotting.

  python scripts/rounds_continuous.py --rounds 3 --n 10 --repeats 5

EXPECT: accuracy flat ~1.0, retrieval/escalation share decaying as repeats
and curiosity instances hit memory/procedure instead of the network.
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path as _P

_REPO = _P(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import requests

from service.connectors.base import Connector, SourceClaim
from service.corroboration import Corroborator
from service.jobs.curiosity import CuriosityEngine
from service.memory.store import ProcedureStore
from service.router import Router
import re as _re


class PokeAPIConnector(Connector):
    name = "pokeapi"

    def get_claims(self, question: str):
        m = _re.search(r"(type|tall|height|weigh|heavy).*?(\b[a-z-]+\b)\s*\?", question.lower())
        if not m:
            return []
        kind, name = m.group(1), m.group(2)
        try:
            d = requests.get(f"https://pokeapi.co/api/v2/pokemon/{name}", timeout=10).json()
        except Exception:
            return []
        if kind == "type":
            ans = d["types"][0]["type"]["name"]
        elif kind in ("tall", "height"):
            ans = str(d["height"])
        else:
            ans = str(d["weight"])
        return [SourceClaim(source=f"pokeapi:{name}", answer=ans,
                            reliability=0.95, independent=True, reason="ground truth")]


def truth(name: str):
    d = requests.get(f"https://pokeapi.co/api/v2/pokemon/{name}", timeout=10).json()
    return {"type": d["types"][0]["type"]["name"],
            "height": str(d["height"]), "weight": str(d["weight"])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--repeats", type=int, default=5)
    args = ap.parse_args()

    data = _REPO / "data"
    data.mkdir(exist_ok=True)
    mem = ProcedureStore(path=data / "pilot_memory.json")
    router = Router(memory=mem, corroborator=Corroborator(),
                    retrievers=[PokeAPIConnector()], backends=[])
    curios = CuriosityEngine(mem, backends=[], budget_per_run=6)

    names = [p["name"] for p in
             requests.get("https://pokeapi.co/api/v2/pokemon?limit=151", timeout=15).json()["results"]]
    rng = random.Random(20261001)
    kinds = [("type", "What type is {}?"), ("height", "How tall is {}?")]
    log_path = data / "rounds_log.jsonl"

    for rnd in range(1, args.rounds + 1):
        fresh = rng.sample([n for n in names], args.n)
        truths = {n: truth(n) for n in fresh}
        new_qs = [(tmpl.format(n), truths[n][key]) for n in fresh for key, tmpl in kinds]
        old_keys = [k for k in mem.entries.keys()]
        rep_qs = [(mem.entries[k]["question"], mem.entries[k]["answer"])
                  for k in rng.sample(old_keys, min(args.repeats, len(old_keys)))] if old_keys else []
        # curiosity proposes from verified LTM (mostly no-ops here: poke Qs unsolvable by backends=[]).
        curios.run()

        ok = mem_hits = retr = total = 0
        lat = 0.0
        for q, exp in new_qs + rep_qs:
            t0 = time.time()
            r = router.resolve(q)
            lat += time.time() - t0
            total += 1
            ok += (r.answer or "").strip().lower() == (exp or "").strip().lower()
            if r.status == "memory":
                mem_hits += 1
            elif r.tier == "retrieval":
                retr += 1
        row = {"round": rnd, "n_new": len(new_qs), "n_rep": len(rep_qs),
               "acc": round(ok / max(total, 1), 3),
               "memory_share": round(mem_hits / max(total, 1), 3),
               "retrieval_share": round(retr / max(total, 1), 3),
               "lat_avg": round(lat / max(total, 1), 3),
               "memory_entries": mem.size()}
        print(f"round{rnd}: acc={row['acc']} memory={row['memory_share']} "
              f"retrieval={row['retrieval_share']} lat={row['lat_avg']}s entries={row['memory_entries']}")
        with open(log_path, "a") as f:
            f.write(json.dumps(row) + "\n")
    print(f"log -> {log_path} (plot memory_share/retrieval_share over rounds)")


if __name__ == "__main__":
    main()
