#!/usr/bin/env python3
"""Formation predictions: weekly direction from price skeletons (Yahoo, no key).

Formation = 5-day sign sequence + position vs MA50 (e.g. "++-++|above").
Two separate books (no deadlock, no double counting):

  OBSERVATIONS (always): each run records last week's formation per symbol;
      when a formation recorded >= 7 days ago can be scored, its family gains
      a trial: up_weeks/total. This accumulates whether or not we predicted.
  PREDICTIONS (gated): predict the majority class ONLY when trials >= MIN and
      |P(up) - 0.5| > MARGIN. Settled a week later into won/settled.

Paper P&L assumes COST per round trip. Verdict rule: prediction hit-rate must
beat base rate net of costs over dozens of trials, or the family (and
eventually the idea) gets pruned — learning includes learning to stop.

Timer: Fridays 18:00 (after close). State: data/formation_memory.json.
  python scripts/formations_market.py [--symbols AAPL,MSFT,SPY,QQQ]
"""
import argparse
import datetime
import json
import sys
from pathlib import Path as _P

_REPO = _P(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import requests

UA = {"User-Agent": "Mozilla/5.0"}
MIN_TRIALS = 3
MARGIN = 0.10
COST = 0.001  # round-trip fraction


def closes(sym: str):
    d = requests.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=4mo",
        headers=UA, timeout=20).json()["chart"]["result"][0]
    return [c for c in d["indicators"]["quote"][0]["close"] if c]


def formation(c: list) -> str:
    signs = "".join("+" if c[-5 + i] >= c[-6 + i] else "-" for i in range(5))
    ma = sum(c[-50:]) / 50
    pos = "above" if c[-1] >= ma else "below"
    return f"{signs}|{pos}"


def week_dir(c: list) -> str:
    return "up" if c[-1] >= c[-6] else "down"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="AAPL,MSFT,SPY,QQQ")
    ap.add_argument("--cost", type=float, default=COST)
    args = ap.parse_args()
    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    data = _REPO / "data"
    data.mkdir(exist_ok=True)
    mem_path = data / "formation_memory.json"
    mem = json.loads(mem_path.read_text()) if mem_path.exists() else {"fams": {}, "pending": []}
    today = datetime.date.today().isoformat()

    # (1) settle observations AND predictions older than 7 days
    settled_obs = settled_pred = won_pred = base_up = base_n = 0
    keep = []
    for p in mem["pending"]:
        age = (datetime.date.fromisoformat(today) - datetime.date.fromisoformat(p["date"])).days
        if age < 7:
            keep.append(p)
            continue
        try:
            c = closes(p["sym"])
        except Exception:
            keep.append(p)
            continue
        actual = week_dir(c)
        base_up += actual == "up"
        base_n += 1
        fam = mem["fams"].setdefault(p["formation"], {"up": 0, "n": 0, "pred_won": 0, "pred_n": 0})
        fam["n"] += 1
        fam["up"] += actual == "up"
        settled_obs += 1
        if p.get("predicted"):
            settled_pred += 1
            hit = p["predicted"] == actual
            fam["pred_won"] += hit
            fam["pred_n"] += 1
            won_pred += hit
    mem["pending"] = keep
    base_rate = round(base_up / max(base_n, 1), 3)

    # (2) record this week's formations; predict only with signal
    made = 0
    for sym in syms:
        try:
            c = closes(sym)
        except Exception as e:
            print(f"SKIP {sym}: {e}")
            continue
        f = formation(c)
        fam = mem["fams"].setdefault(f, {"up": 0, "n": 0, "pred_won": 0, "pred_n": 0})
        entry = {"sym": sym, "formation": f, "date": today}
        if fam["n"] >= MIN_TRIALS:
            p_up = fam["up"] / fam["n"]
            if abs(p_up - 0.5) > MARGIN:
                entry["predicted"] = "up" if p_up > 0.5 else "down"
                made += 1
        mem["pending"].append(entry)
    mem_path.write_text(json.dumps(mem, indent=1))

    pred_acc = round(won_pred / max(settled_pred, 1), 3)
    pnl = won_pred * 1.0 - (settled_pred - won_pred) * 1.0 - settled_pred * args.cost * 100 * 0.01
    print(f"{today}: settled_obs={settled_obs} settled_pred={settled_pred} pred_acc={pred_acc} "
          f"base={base_rate} made={made} pnl_units={round(pnl, 2)} fams={len(mem['fams'])}")
    for f, s in sorted(mem["fams"].items(), key=lambda kv: -kv[1]["n"])[:8]:
        if s["n"] >= 2:
            print(f"  {f:12} P(up)={s['up'] / s['n']:.2f} n={s['n']} "
                  f"pred={s['pred_won']}/{s['pred_n']}")
    with open(data / "formations_log.jsonl", "a") as fh:
        fh.write(json.dumps({"date": today, "settled_pred": settled_pred, "pred_acc": pred_acc,
                             "base_rate": base_rate, "made": made,
                             "pnl_units": round(pnl, 2),
                             "families": len(mem["fams"])}) + "\n")


if __name__ == "__main__":
    main()
