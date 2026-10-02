#!/usr/bin/env python3
"""Slow-domain pilot: bird arrival weeks from GBIF (free, no key).

Barn Swallow (Hirundo rustica) in Spain: for each year, the arrival month =
first month with records >= 5% of that year's peak (facet query, cheap).
Procedure under test: median-of-past arrival (a reasoning skeleton with new
numbers — years change, process stays). Baselines: persistence (last year)
and global mean. Metric: MAE in months + hit-within-±0 error band.

Slow-moving truth is where memory should shine: calibration doesn't decay,
every year of data counts forever.

  python scripts/pilot_gbif.py [--species "Hirundo rustica"] [--country ES]
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path as _P

import requests

BASE = "https://api.gbif.org/v1/occurrence/search"


def monthly_counts(species: str, country: str, year: int):
    r = requests.get(BASE, params={"scientificName": species, "country": country,
                                   "year": year, "limit": 0, "facet": "month",
                                   "facetLimit": 12},
                     timeout=30).json()
    facets = {int(f["name"]): f["count"] for f in r.get("facets", [{}])[0].get("counts", [])}
    return [facets.get(m, 0) for m in range(1, 13)]


def arrival_month(counts, frac: float = 0.05):
    peak = max(counts)
    if peak <= 0:
        return None
    for i, c in enumerate(counts):
        if c >= peak * frac:
            return i + 1
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--species", default="Hirundo rustica")
    ap.add_argument("--country", default="ES")
    ap.add_argument("--years", default="2015,2024")
    ap.add_argument("--test-year", type=int, default=2025)
    args = ap.parse_args()
    y0, y1 = (int(x) for x in args.years.split(","))
    years = list(range(y0, y1 + 1))

    arrivals = {}
    for y in years + [args.test_year]:
        counts = monthly_counts(args.species, args.country, y)
        a = arrival_month(counts)
        arrivals[y] = a
        print(f"{y}: arrival month={a} peak={max(counts)}", flush=True)
        time.sleep(0.5)
    hist = [a for y, a in arrivals.items() if y != args.test_year and a]
    actual = arrivals[args.test_year]
    if not hist or not actual:
        print("insufficient data")
        return
    pred_med = int(round(statistics.median(hist)))
    pred_mean = int(round(statistics.mean(hist)))
    pred_persist = hist[-1]
    print(f"\nmedian-of-past={pred_med} mean={pred_mean} persist={pred_persist} actual={actual}")
    for name, p in (("procedure(median)", pred_med), ("mean", pred_mean), ("persist", pred_persist)):
        print(f"  {name:18} err={abs(p - actual)} month(s)")

    # Walk-forward: every year as test (2018+), predicted only from its past.
    print("\nwalk-forward (predict ty from years < ty):")
    wf = {"procedure": [], "mean": [], "persist": []}
    syears = sorted(arrivals)
    for ty in syears:
        past = [arrivals[y] for y in syears if y < ty and arrivals[y]]
        if len(past) < 3 or not arrivals[ty]:
            continue
        wf["procedure"].append(abs(int(round(statistics.median(past))) - arrivals[ty]))
        wf["mean"].append(abs(int(round(statistics.mean(past))) - arrivals[ty]))
        wf["persist"].append(abs(past[-1] - arrivals[ty]))
    for name, errs in wf.items():
        mae = sum(errs) / len(errs) if errs else float("nan")
        print(f"  {name:18} MAE={mae:.2f} months over {len(errs)} years")
    out = {"species": args.species, "country": args.country, "test_year": args.test_year,
           "pred_median": pred_med, "pred_mean": pred_mean, "pred_persist": pred_persist,
           "actual": actual, "history": hist, "walk_forward_mae": {k: (sum(v) / len(v) if v else None) for k, v in wf.items()}}
    (_P("/tmp/opencode/pilot") ).mkdir(parents=True, exist_ok=True)
    (_P("/tmp/opencode/pilot/gbif.json")).write_text(json.dumps(out, indent=1))
    print("saved /tmp/opencode/pilot/gbif.json")


if __name__ == "__main__":
    main()
