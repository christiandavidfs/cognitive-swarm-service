#!/usr/bin/env python3
"""LAYA Gate A/B — in-process SDK bench for GPU machines (no HTTP hop).

Mirrors pilot_agnews.py metrics exactly so numbers are comparable with the
Kev pilot (acc, Brier, auto@conf>=0.9 coverage/error, latency). Loads the
checkpoint DIRECTLY via the laya package — this is the path for the GPU box,
and the only reliable way to evaluate the already-fine-tuned subfolder.

Checkpoints (same HF repo, only the requested one downloads):
  english          convaiinnovations/laya (root, 421M, zero-shot weak)
  typed-decisions  convaiinnovations/laya subfolder — ALREADY FINE-TUNED
                   (vendor benchmark 0.766 vs 0.362 base) ← Gate B shortcut
  multilingual     mmBERT 322M (not the target for our English pilot)

Suites:
  taxonomy  the 12 paraphrase CASES (our code/math/reasoning taxonomy)
  agnews    AG News test slice, IDENTICAL questions to the Kev pilot

Writes predictions JSONL in fit_laya_temperature.py format (--save) so the
temperature refit (Gate B, mandatory — base ships over-confident, ECE 0.466)
runs offline right after.

Run (GPU box, see docs/LAYA_GPU_RUNBOOK.md):
  pip install laya datasets
  python scripts/bench_laya_sdk.py --suite agnews --n 200 \
      --checkpoint typed-decisions --save data/laya_td_agnews.preds.jsonl
  python scripts/fit_laya_temperature.py data/laya_td_agnews.preds.jsonl

Vendor gotcha: if TensorFlow is installed, run with USE_TF=0 (TF/abseil can
deadlock model construction in transformers).
"""
import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path as _P

_REPO = _P(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

AUTO_CONF = 0.9  # same automated-action threshold as the Kev pilot

AGNEWS_LABELS = ["world", "sports", "business", "scitech"]
AGNEWS_QUESTION = {
    "type": "choice",
    "instructions": "Which news desk wrote this article?",
    "criteria": {
        "world": "international news, politics, conflicts, disasters",
        "sports": "games, teams, athletes, scores",
        "business": "markets, companies, economy, money",
        "scitech": "science, technology, space, health research",
    },
}
TAXONOMY_QUESTION = {
    "type": "choice",
    "instructions": "Classify the question by what solves it. "
                    "code = running code answers it; math = PURE arithmetic expression "
                    "with no story (calculator alone suffices, e.g. 'What is 5+3?'); "
                    "reasoning = a story/word problem needing a procedure even when "
                    "numbers appear (rates, handshakes, work schedules, riddles, logic); "
                    "unknown = factual, contested, or unclear — no solver category fits.",
    "criteria": {
        "code": "question contains or asks about executable code output",
        "math": "question is arithmetic with explicit numbers and operators",
        "reasoning": "question needs a reasoning procedure (rates, handshakes, riddles, logic)",
        "unknown": "factual, contested, or unclear — no solver category fits",
    },
}
# All 12 CASES are reasoning word-problems per measure_jev_classify.EXPECTED_TASK
# (the Moses/race tricks are still reasoning tasks; 'unknown' is never expected there)
TAXONOMY_EXPECTED = ["reasoning"] * 12

# Same 12 CASES as bench_paraphrase (order matters for TAXONOMY_EXPECTED)
TAXONOMY_CASES = [
    "In a group of 47 people each shakes hands with every other exactly once how many handshakes?",
    "At a party with 30 guests every pair shakes hands once, how many handshakes in total?",
    "Sixty coworkers each shake hands with all others once, total handshakes?",
    "You have 5 apples and you take away 2, how many do you have?",
    "You have 7 oranges and you take away 3, how many do you have?",
    "If you have 100 marbles and give away 45, how many do you have left?",
    "A shopkeeper has 60 coins and hands out 17, how many remain?",
    "Twelve builders can build a house in 15 days, how many needed for 3 days?",
    "Eight painters paint a fence in 20 days, how many painters to finish in 8 days?",
    "How many animals of each kind did Moses take on the ark?",
    "In the biblical story how many animals of each kind did Moses take on the ark?",
    "If you overtake the second person in a race, what place are you in?",
]


def _load_agent(checkpoint: str):
    import laya  # noqa: PLC0415 — GPU-box only dependency, not in service deps
    subfolder = {"english": None, "multilingual": "multilingual",
                 "typed-decisions": "typed-decisions"}[checkpoint]
    if subfolder is None:
        return laya.load("convaiinnovations/laya")
    return laya.load("convaiinnovations/laya", subfolder=subfolder)


def _ask(agent, state, questions):
    t0 = time.time()
    result = agent.predict(state, questions)
    dt = round(time.time() - t0, 3)
    answers = result["answers"]
    name = next(iter(questions))
    ans = answers[name]
    return {
        "choice": ans.get("choice"),
        "probabilities": {k: float(v) for k, v in (ans.get("probabilities") or {}).items()},
        "confidence": float(ans.get("confidence", 0.0)),
    }, dt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", choices=["taxonomy", "agnews"], default="agnews")
    ap.add_argument("--checkpoint", choices=["english", "typed-decisions", "multilingual"],
                    default="english")
    ap.add_argument("--n", type=int, default=200, help="agnews slice size")
    ap.add_argument("--offset", type=int, default=0,
                    help="agnews offset (use >=1000 to avoid train contamination, "
                         "same slice as the Kev pilot)")
    ap.add_argument("--save", default="data/laya_preds.jsonl",
                    help="predictions JSONL for scripts/fit_laya_temperature.py")
    args = ap.parse_args()

    agent = _load_agent(args.checkpoint)
    preds, lats = [], []
    if args.suite == "taxonomy":
        cases = [(q, TAXONOMY_EXPECTED[i]) for i, q in enumerate(TAXONOMY_CASES)]
        print(f"checkpoint={args.checkpoint} suite=taxonomy n={len(cases)}")
        for q, expected in cases:
            try:
                ans, dt = _ask(agent, q, {"task_type": TAXONOMY_QUESTION})
            except Exception as e:
                print(f"call failed: {e}")
                return
            lats.append(dt)
            choice = ans["choice"] or "unknown"
            ok = choice == expected
            preds.append({"question_type": "choice", "n_options": 4,
                          "probs": ans["probabilities"], "label": expected,
                          "text": q, "choice": choice, "ok": ok})
            print(f"  {expected:9} -> {choice:9} {'OK ' if ok else 'MISS'} "
                  f"conf={ans['confidence']:.3f} {dt:.2f}s  {q[:50]}")
        n = len(cases)
    else:
        from datasets import load_dataset  # GPU-box dependency, like pilot_agnews
        ds = load_dataset("fancyzhx/ag_news", split=f"test[{args.offset}:{args.offset + args.n}]")
        print(f"checkpoint={args.checkpoint} suite=agnews n={len(ds)} offset={args.offset}")
        for i, ex in enumerate(ds):
            text, label = ex["text"][:800], AGNEWS_LABELS[ex["label"]]
            try:
                ans, dt = _ask(agent, text, {"desk": AGNEWS_QUESTION})
            except Exception as e:
                print(f"[{i}] call failed: {e}")
                continue
            lats.append(dt)
            choice = ans["choice"] or "unknown"
            ok = choice == label
            preds.append({"question_type": "choice", "n_options": 4,
                          "probs": ans["probabilities"], "label": label,
                          "text": text, "choice": choice, "ok": ok})
            if (i + 1) % 25 == 0:
                acc = sum(p["ok"] for p in preds) / len(preds)
                print(f"[{i + 1}/{len(ds)}] acc={acc:.3f}", flush=True)
        n = len(preds)

    # Metrics — identical definitions to pilot_agnews.py
    correct = sum(p["ok"] for p in preds)
    brier = sum(
        (1.0 - p["probs"].get(p["label"], 0.0)) ** 2
        + sum(v * v for k, v in p["probs"].items() if k != p["label"])
        for p in preds) / max(n, 1)
    auto = [p for p in preds if p["choice"] in p["probs"] and p["probs"][p["choice"]] >= AUTO_CONF]
    cov = len(auto) / max(n, 1)
    err = (sum(not p["ok"] for p in auto) / len(auto)) if auto else float("nan")
    lat = sorted(lats)
    print(f"\n== {args.checkpoint} @ {args.suite} ==")
    print(f"accuracy        {correct}/{n} = {correct / max(n, 1):.3f}")
    print(f"brier           {brier:.3f}")
    print(f"auto@{AUTO_CONF}        {len(auto)}/{n} coverage={cov:.0%} err={err:.3f}")
    print(f"latency mean    {statistics.mean(lats):.3f}s")
    print(f"latency p95     {lat[min(len(lat) - 1, int(len(lats) * 0.95))]:.3f}s")
    print(f"\nKev-0.8B baselines (AG News n=200): acc 0.900 brier 0.176 "
          f"auto@0.9 146/200 err 0.062")
    print(f"GATE RULE: promote LAYA iff err@{AUTO_CONF} <= 0.062 at coverage >= 73%")
    out = _P(args.save)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(p) for p in preds), encoding="utf-8")
    print(f"preds -> {out}  (next: python scripts/fit_laya_temperature.py {out})")


if __name__ == "__main__":
    main()
