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

Two instrument safeguards (added 2026-11-14):
  --pool-file   the recurring pool is persisted (data/cost_pool.json) and reused,
                so week-to-week rows are comparable. Without it each run draws a
                new pool and the "curve" mixes learning with draw luck.
  warm round    a final all-warm round (pool only, nothing open) measures the
                ceiling the curve converges to. Fully warm recurring volume
                should reach 0 external calls.

  python scripts/cost_per_decision.py --rounds 5 --n 100
  python scripts/cost_per_decision.py --memory /tmp/... --log /tmp/...   # probe
"""
import argparse
import datetime
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


def load_or_create_pool(path, rng, names, size):
    """Persist the recurring pool so week-to-week rows are comparable.

    A customer's recurring traffic is roughly the *same* questions. If the pool
    is re-drawn every run, the weekly series measures draw luck plus fact
    overlap, not learning. Create once, reuse afterwards.
    """
    path = _P(path)
    if path.exists():
        try:
            data = json.loads(path.read_text())
            pool = data.get("recurring") if isinstance(data, dict) else None
            if pool:
                return list(pool)
        except (ValueError, OSError):
            pass
    pool = sample_pool(rng, names, size)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(
        {"created": datetime.date.today().isoformat(), "recurring": pool},
        indent=2,
    ))
    return pool


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


def build_warm_round(recurring_pool):
    """All-warm round: ask only the recurring set, both attributes.

    With the pool fully cached the only external call left is the open share
    (zero here), so this is the floor the weekly curve converges to.
    """
    kinds = [("type", "What type is {}?"), ("height", "How tall is {}?")]
    return [("recurring", tmpl.format(n), ("fact", n, kind))
            for n in recurring_pool for kind, tmpl in kinds]


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
    ap.add_argument("--pool-file", default="",
                    help="persisted recurring pool (default: data/cost_pool.json) "
                         "so weekly rows are comparable")
    ap.add_argument("--no-warm", action="store_true",
                    help="skip the all-warm ceiling round")
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
    rng = random.Random(args.seed or int(datetime.date.today().strftime("%Y%m%d")))
    recurring_pool = load_or_create_pool(
        args.pool_file or (data / "cost_pool.json"),
        rng, names, args.recurring_pool)
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

    def run_items(items):
        results = []
        for cohort, q, sym in items:
            exp = expected_for(sym)
            t0 = time.time()
            r = router.resolve(q)
            lat = time.time() - t0
            bucket = classify(r)
            correct = exp is not None and (r.answer or "").strip().lower() == exp.strip().lower()
            results.append((cohort, bucket, correct, exp is not None, lat))
        return results

    def archive(row, label):
        row["date"] = datetime.date.today().isoformat()
        row["backends"] = [b.name for b in backends]
        row["memory_entries"] = mem.size()
        print(f"{label}: net/100={row['network_per_100']} "
              f"model/100={row['model_per_100']} "
              f"external/100={row['external_per_100']} "
              f"cpu={row['cpu_ms_per_decision']}ms mem={row['memory_share']} "
              f"det={row['deterministic_share']} acc={row['acc']} "
              f"entries={row['memory_entries']}")
        with open(log_path, "a") as f:
            f.write(json.dumps(row) + "\n")

    for rnd in range(1, args.rounds + 1):
        items = build_round(rng, recurring_pool, fresh_pool, args.n)
        archive(summarize(rnd, run_items(items), args.n), f"round{rnd}")

    if not args.no_warm:
        # Ceiling round: pool fully warm, nothing open. external/100 here is the
        # floor the weekly curve converges to (memory/retrieval only).
        warm = build_warm_round(recurring_pool)
        row = summarize(args.rounds + 1, run_items(warm), len(warm))
        row["mode"] = "warm"
        archive(row, "warm ")

    print(f"log -> {log_path}")
    print("counterfactual: model-on-everything = 100 model calls / 100 decisions")
    print("read: external/100 must DECAY on recurring volume and approach the "
          "open share (floor). Flat = the operational claim loses.")


if __name__ == "__main__":
    main()
