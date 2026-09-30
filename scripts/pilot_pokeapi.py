#!/usr/bin/env python3
"""Simulated-traffic pilot: PokeAPI as free ground truth (no key, exact answers).

Exercises the REAL stack (Router + retrieval + corroboration + memory) over
2 rounds of the same questions. Round 1 measures retrieval correctness;
round 2 must hit memory — the first direct measurement of the learning curve
(escalation/retrieval decay) the thesis predicts.

  python scripts/pilot_pokeapi.py --n 30

Metrics: accuracy vs API truth, memory-hit rate r1 vs r2, latency mean.
"""
import argparse
import re
import sys
import time
from pathlib import Path as _P

_REPO = _P(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import requests

from service.connectors.base import Connector, SourceClaim, TaskType
from service.corroboration import Corroborator
from service.memory.store import ProcedureStore
from service.router import Router


class PokeAPIConnector(Connector):
    """One-file connector demo: pokemon facts as SourceClaims."""

    name = "pokeapi"

    def __init__(self, reliability: float = 0.95):
        self.reliability = float(reliability)

    def get_claims(self, question: str):
        m = re.search(r"(type|tall|height|weigh|heavy).*?(\b[a-z-]+\b)\s*\?", question.lower())
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
                            reliability=self.reliability, independent=True,
                            reason="PokeAPI ground truth")]


def truth(name: str):
    d = requests.get(f"https://pokeapi.co/api/v2/pokemon/{name}", timeout=10).json()
    return {"type": d["types"][0]["type"]["name"],
            "height": str(d["height"]), "weight": str(d["weight"])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    args = ap.parse_args()

    names = [p["name"] for p in
             requests.get("https://pokeapi.co/api/v2/pokemon?limit=151", timeout=15).json()["results"]]
    import random
    rng = random.Random(11)
    chosen = rng.sample(names, min(args.n, len(names)))
    truths = {n: truth(n) for n in chosen}

    kinds = [("type", "What type is {}?"), ("height", "How tall is {}?")]
    mem = ProcedureStore(path=_P(f"/tmp/opencode/pilot/poke-mem-{int(time.time())}.json"))
    router = Router(memory=mem, corroborator=Corroborator(),
                    retrievers=[PokeAPIConnector()], backends=[])

    for rnd in (1, 2):
        ok = mem_hits = lat = total = 0
        t0 = time.time()
        for n in chosen:
            for key, tmpl in kinds:
                q = tmpl.format(n)
                r = router.resolve(q)
                total += 1
                ok += (r.answer or "").strip().lower() == truths[n][key].lower()
                mem_hits += r.status == "memory"
        dt = time.time() - t0
        print(f"round{rnd}: acc={ok}/{total}={ok / total:.3f} "
              f"memory_hits={mem_hits}/{total} latency_avg={dt / total:.2f}s")
    print("EXPECT: round2 acc same, memory_hits >> round1 (learning curve).")


if __name__ == "__main__":
    main()
