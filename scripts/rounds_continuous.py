#!/usr/bin/env python3
"""Continuous rounds: cost decomposition + would-escalate curve.

Each round mixes four cohorts (the old row conflated them and its
`escalated_share` could only ever be 0 — measured 2026-10-29):

  new  unseen Pokemon facts        -> retrieval must work; memory_share_new
                                      is the cross-run coverage curve
  rep  repeats sampled from LTM    -> memory must serve (cost -> 0)
  proc procedure instances with    -> deterministic must catch them; with the
       unseen numbers                 core installed this is the ceiling, not
                                      a learning signal
  irr  irreducible questions       -> nothing can answer them; they ARE the
       (contested/analysis)           escalation floor

Metrics:
  escalation_share   share that reached the model tier (status none/tier
                     debate = would need a model). THE thesis metric.
  memory_share_new   coverage of fresh facts (grows as LTM learns)
  memory_share_rep   cache hit rate on repeats (should be ~1.0)
  deterministic_share  share resolved by code (free)
  honest_abstain     irreducible items answered None (honesty)

`escalated_share` (singular, old rows) counted "not memory and not
retrieval" — with a live feed and no backends that is structurally 0.
Renamed to `unanswered_share` in prose; new rows log `escalation_share`.

  python scripts/rounds_continuous.py --rounds 3 --n 8 --repeats 4 --proc 8
  BACKENDS=cognitive_swarm python3 scripts/rounds_continuous.py   # real curve
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

from service.backends import load_backends
from service.connectors.base import Connector, SourceClaim
from service.corroboration import Corroborator
from service.jobs.curiosity import CuriosityEngine
from service.memory.store import ProcedureStore
from service.net import fetch_json
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
    d = fetch_json(f"https://pokeapi.co/api/v2/pokemon/{name}", timeout_s=10)
    return {"type": d["types"][0]["type"]["name"],
            "height": str(d["height"]), "weight": str(d["weight"])}


def procedure_questions(rng, n: int):
    """Unseen-number instances of patterns the core knows (truth is exact)."""
    out = []
    for _ in range(n):
        if rng.random() < 0.5:
            k = rng.randint(12, 400)
            out.append((f"In a group of {k} people each shakes hands with every "
                        f"other exactly once how many handshakes?",
                        str(k * (k - 1) // 2)))
        else:
            a, b = rng.randint(2, 99), rng.randint(2, 99)
            out.append((f"What does print({a}*{b}) output?", str(a * b)))
    return out


IRREDUCIBLE = [
    ("What caused the fall of the Roman Empire?", None),
    ("Why did the 2008 financial crisis happen?", None),
]


def classify(res) -> str:
    """Route outcome -> cohort bucket. Order matters (memory first)."""
    if res.status == "memory":
        return "memory"
    if res.tier == "retrieval":
        return "retrieval"
    if res.tier == "conflict":
        return "conflict"
    if res.tier == "debate":
        return "escalated"          # status "none": would need a model
    return "deterministic"          # executor / primitives / any backend tier


def share(k: int, n: int) -> float:
    return round(k / n, 3) if n else 0.0


def new_cohort() -> dict:
    return {"n": 0, "memory": 0, "retrieval": 0, "deterministic": 0,
            "conflict": 0, "escalated": 0, "abstain": 0, "ok": 0, "scored": 0}


def build_row(rnd: int, cohorts: dict, lat: float, entries: int,
              backends: list) -> dict:
    total = sum(c["n"] for c in cohorts.values())
    ok = sum(c["ok"] for c in cohorts.values())
    scored = sum(c["scored"] for c in cohorts.values())
    det = sum(c["deterministic"] for c in cohorts.values())
    esc = sum(c["escalated"] for c in cohorts.values())
    irr = cohorts.get("irr", new_cohort())
    return {
        "round": rnd,
        "cohorts": cohorts,
        "n_total": total,
        "acc": share(ok, scored),
        "memory_share_new": share(cohorts.get("new", new_cohort())["memory"],
                                  cohorts.get("new", new_cohort())["n"]),
        "memory_share_rep": share(cohorts.get("rep", new_cohort())["memory"],
                                  cohorts.get("rep", new_cohort())["n"]),
        "deterministic_share": share(det, total),
        "escalation_share": share(esc, total),
        "honest_abstain_share": share(irr["abstain"], irr["n"]),
        "lat_avg": round(lat / max(total, 1), 3),
        "memory_entries": entries,
        "backends": list(backends),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--proc", type=int, default=8,
                    help="unseen-number procedure instances per round")
    ap.add_argument("--seed", type=int, default=0,
                    help="0 = live seed from today's date (fresh draws each run); "
                         "fixed seed reproduces a specific run")
    ap.add_argument("--memory", default="",
                    help="memory path (default: data/pilot_memory.json). Use a "
                         "scratch copy for probe validation.")
    ap.add_argument("--log", default="",
                    help="log path (default: data/rounds_log.jsonl)")
    args = ap.parse_args()

    data = _REPO / "data"
    data.mkdir(exist_ok=True)
    mem = ProcedureStore(path=args.memory or (data / "pilot_memory.json"))
    backends = load_backends(memory=mem)
    router = Router(memory=mem, corroborator=Corroborator(),
                    retrievers=[PokeAPIConnector()], backends=backends)
    curios = CuriosityEngine(mem, backends=backends, budget_per_run=6)

    names = [p["name"] for p in
             fetch_json("https://pokeapi.co/api/v2/pokemon?limit=151", timeout_s=15)["results"]]
    import datetime
    rng = random.Random(args.seed or int(datetime.date.today().strftime("%Y%m%d")))
    kinds = [("type", "What type is {}?"), ("height", "How tall is {}?")]
    log_path = _P(args.log) if args.log else data / "rounds_log.jsonl"

    for rnd in range(1, args.rounds + 1):
        fresh = rng.sample([n for n in names], args.n)
        truths = {n: truth(n) for n in fresh}
        if not truths:
            print(f"round{rnd}: feed outage — all truth fetches failed, NO row archived")
            continue

        cohorts = {c: new_cohort() for c in ("new", "rep", "proc", "irr")}
        batches = {
            "new": [(tmpl.format(n), truths[n][key]) for n in fresh
                    for key, tmpl in kinds],
            "proc": procedure_questions(rng, args.proc),
            "irr": list(IRREDUCIBLE),
        }
        old_keys = [k for k in mem.entries.keys()]
        batches["rep"] = [(mem.entries[k]["question"], mem.entries[k]["answer"])
                          for k in rng.sample(old_keys, min(args.repeats, len(old_keys)))] \
            if old_keys else []
        # Curiosity may propose/verify from LTM; with backends on it can add entries.
        curios.run()

        lat = 0.0
        for cohort, items in batches.items():
            for q, exp in items:
                t0 = time.time()
                r = router.resolve(q)
                lat += time.time() - t0
                c = cohorts[cohort]
                c["n"] += 1
                c[classify(r)] += 1
                if r.answer is None:
                    c["abstain"] += 1
                if exp is not None:
                    c["scored"] += 1
                    c["ok"] += (r.answer or "").strip().lower() == exp.strip().lower()

        row = build_row(rnd, cohorts, lat, mem.size(), [b.name for b in backends])
        print(f"round{rnd}: acc={row['acc']} esc={row['escalation_share']} "
              f"mem_new={row['memory_share_new']} mem_rep={row['memory_share_rep']} "
              f"det={row['deterministic_share']} lat={row['lat_avg']}s "
              f"entries={row['memory_entries']} backends={row['backends']}")
        for name, c in cohorts.items():
            if c["n"]:
                print(f"   {name:>4}: n={c['n']} mem={c['memory']} ret={c['retrieval']} "
                      f"det={c['deterministic']} conf={c['conflict']} esc={c['escalated']}")
        with open(log_path, "a") as f:
            f.write(json.dumps(row) + "\n")
    print(f"log -> {log_path} (plot escalation_share / memory_share_new over rounds)")


if __name__ == "__main__":
    main()
