#!/usr/bin/env python3
"""Pilot: AG News routing through the local Kev judge (free labeled data).

Measures Choice(world/sports/business/scitech) vs true labels:
accuracy, Brier score, automation share at 5% error budget — the same
yardstick Kev's author uses. Also writes Kev-format JSONL (train/heldout)
so a future fine-tune starts from measured data, not wishes.

Needs: Kev server up (default http://127.0.0.1:8019), `datasets` package.
  python scripts/pilot_agnews.py --n 200
  KEV_BASE_URL=http://127.0.0.1:8019 python scripts/pilot_agnews.py --n 50 --save data/agnews_kev.jsonl
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path as _P

_REPO = _P(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

LABELS = ["world", "sports", "business", "scitech"]

QUESTION = {
    "desk": {
        "type": "choice",
        "instructions": "Which news desk wrote this article?",
        "criteria": {
            "world": "international news, politics, conflicts, disasters",
            "sports": "games, teams, athletes, scores",
            "business": "markets, companies, economy, money",
            "scitech": "science, technology, space, health research",
        },
    }
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--save", default="data/agnews_kev.jsonl")
    args = ap.parse_args()

    os.environ.setdefault("JEV_VIA", "typesafe")
    os.environ.setdefault("TYPESAFE_BASE_URL", os.getenv("KEV_BASE_URL", "http://127.0.0.1:8019"))
    os.environ.setdefault("TYPESAFE_API_KEY", "local")
    from service.judgments.jev import system_one

    from datasets import load_dataset
    ds = load_dataset("fancyzhx/ag_news", split=f"test[:{args.n}]")

    correct = brier = auto_ok = auto_n = 0
    rows = []
    preds = []
    t0 = time.time()
    for i, ex in enumerate(ds):
        text, label = ex["text"][:800], LABELS[ex["label"]]
        try:
            ans = system_one(state=text, questions=QUESTION)["desk"]
        except Exception as e:
            print(f"[{i}] judge call failed: {e}")
            continue
        probs = {k: float(v) for k, v in (ans.get("probabilities") or {}).items()}
        choice = ans.get("choice")
        conf = float(ans.get("confidence", 0.0))
        p_true = probs.get(label, 0.0)
        brier += (1.0 - p_true) ** 2 + sum(p * p for k, p in probs.items() if k != label)
        correct += choice == label
        if conf >= 0.9:
            auto_n += 1
            auto_ok += choice == label
        preds.append({"text": text, "label": label, "choice": choice, "confidence": conf, "probs": probs})
        rows.append({"state": text, "questions": {
            "desk": {"type": "choice",
                     "instructions": QUESTION["desk"]["instructions"],
                     "criteria": QUESTION["desk"]["criteria"],
                     "label": label}}})
        if (i + 1) % 25 == 0:
            print(f"[{i + 1}/{len(ds)}] acc={(correct / (i + 1)):.3f}", flush=True)
    n = len(rows)
    Path = _P(args.save)
    Path.parent.mkdir(parents=True, exist_ok=True)
    Path.write_text("\n".join(json.dumps(r) for r in rows))
    _P(str(args.save).replace(".jsonl", ".preds.json")).write_text(json.dumps(preds))
    err51 = 1 - (auto_ok / auto_n) if auto_n else 1.0
    print(f"\naccuracy {correct}/{n}={correct / max(n, 1):.3f}  brier {brier / max(n, 1):.3f}")
    print(f"automated@conf>=0.9: {auto_n}/{n} err={err51:.3f} (author yardstick: 5% error budget)")
    print(f"dataset -> {args.save} ({n} rows, Kev train format) in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()

# NOTE appended: predictions dump for offline analysis (confusion, sweep).
