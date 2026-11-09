#!/usr/bin/env python3
"""Cost per decision — the operational claim, measured.

The thesis says process memory makes operations cheaper over time. That is
NOT the same as "the model zone shrinks" (measured 2026-11-05: escalation
sits at the irreducible floor). This instrument measures what a customer
actually pays per decision:

  network calls   retrieval invoked (external dependency)
  model calls     question reached the model tier (would need a model)
  cpu ms          local wall time per decision

Traffic mix per round (N decisions), simulating operational volume:
  recurring   same small pool asked again (the volume case: support, ops,
              repeated customer questions)
  fresh       new draws from the open pool (coverage must grow)
  proc        procedure instances with unseen numbers (code, free)
  open        contested/analysis (irreducible floor)

Counterfactual: model-on-everything = 100 model calls per 100 decisions.

Expected: external calls/100 DECAYS round over round on recurring volume and
approaches the open share (the floor). If it does not decay, the operational
claim loses — record it as a negative gate.

  python scripts/cost_per_decision.py --rounds 5 --n 100
  python scripts/cost_per_decision.py --memory /tmp/... --log /tmp/...   # probe
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

from service.backends import load_backends
from service.corroboration import Corroborator
from service.memory.store import ProcedureStore
from service.net import fetch_json
from service.router import Router
from scripts.rounds_continuous import (IRREDUCIBLE, PokeAPIConnector,
                                       procedure_questions, truth)


def sample_pool(rng, names, size):
    return rng.sample(list(names), size)


def build_round(rng, recurring_pool, fresh_pool, n_total, recurring_share=0.6,
                fresh_share=0.2, proc_share=0.1, open_share=0.1):
    """Compose one round's decisions. Shares must sum to 1.0.

    Returns [(cohort, question, expected_or_None)]. Expected values for facts
    are symbols resolved later (name, kind) to avoid network in stream build.
    """
    shares = recurring_share + fresh_share + proc_share + open_share
    if abs(shares - 1.0) > 1e-9:
        raise ValueError("cohort shares must sum to 1.0")
    n_rec = int(round(n_total * recurring_share))
    n_fresh = int(round(n_total * fresh_share))
    n_proc = int(round(n_total * proc_share))
    n_open = max(0, n_total - n_rec - n_fresh - n_proc)

    kinds = [("type", "What type is {}?"), ("height", "How tall is {}?")]
    out = []
    for _ in range(n_rec):
        name = rng.choice(recurring_pool)
        kind, tmpl = rng.choice(kinds)
        out.append(("recurring", tmpl.format(name), ("fact", name, kind)))
    for _ in range(n_fresh):
        name = rng.choice(fresh_pool)
        kind, tmpl = rng.choice(kinds)
        out.append(("fresh", tmpl.format(name), ("fact", name, kind)))
    for q, exp in procedure_questions(rng, n_proc):
        out.append(("proc", q, ("value", exp)))
    for i in range(n_open):
        q, _ = IRREDUCIBLE[i % len(IRREDUCIBLE)]
        out.append(("open", q, None))
    return out


def classify(res):
    if res.status == "memory":
        return "memory"
    if res.tier == "retrieval":
        return "retrieval"
    if res.tier == "conflict":
        return "conflict"
    if res.tier == "debate":
        return "model"
    return "deterministic"


def summarize(round_no, results, n_decisions):
    """results: [(cohort, bucket, ok, expected_known, latency_s)]."""
    per_100 = lambda k: round(100.0 * k / max(n_decisions, 1), 1)
    buckets = {}
    by_cohort = {}
    cpu = 0.0
    ok = scored = network = model = 0
    for cohort, bucket, correct, known, lat in results:
        cpu += lat
        buckets[bucket] = buckets.get(bucket, 0) + 1
        by_cohort.setdefault(cohort, {})
        by_cohort[cohort][bucket] = by_cohort[cohort].get(bucket, 0) + 1
        if known:
            scored += 1
            ok += int(correct)
        network += int(bucket in ("retrieval", "conflict"))
        model += int(bucket == "model")
    return {
        "round": round_no,
        "decisions": n_decisions,
        "network_per_100": per_100(network),
        "model_per_100": per_100(model),
        "external_per_100": per_100(network + model),
        "model_on_everything_per_100": 100.0,
        "cpu_ms_per_decision": round(1000.0 * cpu / max(n_decisions, 1), 1),
        "memory_share": round(buckets.get("memory", 0) / max(n_decisions, 1), 3),
        "deterministic_share": round(buckets.get("deterministic", 0) / max(n_decisions, 1), 3),
        "acc": round(ok / scored, 3) if scored else None,
        "by_cohort": by_cohort,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--recurring-pool", type=int, default=40)
    ap.add_argument("--seed", type=int, default=0,
                    help="0 = live seed from today's date")
    ap.add_argument("--memory", default="",
                    help="memory path (default: data/cost_memory.json — separate "
                         "from the longitudinal store)")
    ap.add_argument("--log", default="",
                    help="log path (default: data/cost_log.jsonl)")
    args = ap.parse_args()

    data = _REPO / "data"
    data.mkdir(exist_ok=True)
    mem = ProcedureStore(path=args.memory or (data / "cost_memory.json"))
    backends = load_backends(memory=mem)
    router = Router(memory=mem, corroborator=Corroborator(),
                    retrievers=[PokeAPIConnector()], backends=backends)

    names = [p["name"] for p in
             fetch_json("https://pokeapi.co/api/v2/pokemon?limit=151", timeout_s=15)["results"]]
    import datetime
    rng = random.Random(args.seed or int(datetime.date.today().strftime("%Y%m%d")))
    recurring_pool = sample_pool(rng, names, args.recurring_pool)
    fresh_pool = [n for n in names if n not in set(recurring_pool)]

    truth_cache = {}

    def expected_for(sym):
        if sym is None:
            return None
        if sym[0] == "value":
            return sym[1]
        _, name, kind = sym
        if name not in truth_cache:
            truth_cache[name] = truth(name)
        return truth_cache[name][kind]

    log_path = _P(args.log) if args.log else data / "cost_log.jsonl"
    for rnd in range(1, args.rounds + 1):
        items = build_round(rng, recurring_pool, fresh_pool, args.n)
        results = []
        for cohort, q, sym in items:
            exp = expected_for(sym)
            t0 = time.time()
            r = router.resolve(q)
            lat = time.time() - t0
            bucket = classify(r)
            correct = exp is not None and (r.answer or "").strip().lower() == exp.strip().lower()
            results.append((cohort, bucket, correct, exp is not None, lat))
        row = summarize(rnd, results, args.n)
        row["date"] = datetime.date.today().isoformat()
        row["backends"] = [b.name for b in backends]
        row["memory_entries"] = mem.size()
        print(f"round{rnd}: net/100={row['network_per_100']} "
              f"model/100={row['model_per_100']} "
              f"external/100={row['external_per_100']} "
              f"cpu={row['cpu_ms_per_decision']}ms mem={row['memory_share']} "
              f"det={row['deterministic_share']} acc={row['acc']} "
              f"entries={row['memory_entries']}")
        with open(log_path, "a") as f:
            f.write(json.dumps(row) + "\n")
    print(f"log -> {log_path}")
    print("counterfactual: model-on-everything = 100 model calls / 100 decisions")
    print("read: external/100 must DECAY on recurring volume and approach the "
          "open share (floor). Flat = the operational claim loses.")


if __name__ == "__main__":
    main()
