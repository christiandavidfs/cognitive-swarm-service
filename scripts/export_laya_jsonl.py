#!/usr/bin/env python3
"""Gate B step 0 — export labeled decisions to LAYA fine-tune JSONL.

Sources accepted (order-free, any combination):
  --from-jsonl file.jsonl   records with {"text": ..., "label": ...}
  --from-csv file.csv       columns: text,label (header required)
  --from-memory             LTM trace store, when populated (verified Q/A)

Output record shape is the POC contract; the OFFICIAL fine-tuning notebook
(github.com/NandhaKishorM/laya, notebooks/laya_finetune_typed_decisions_*.ipynb)
defines the real training format — verify against it before training and
adapt here if it differs. We do not guess training formats into production.

Guards (from the model card's honest limits):
  - <= 20 distinct labels per question type (LAYA degrades hard beyond that;
    larger taxonomies need coarse-to-fine hierarchical choices)
  - label mapping to our TaskType families is explicit and versioned
  - never includes private trace CONTENT — labels + text only come from
    sources the caller points at (nothing is read from private stores unless
    --from-memory is explicitly passed)

Run:  python scripts/export_laya_jsonl.py --from-csv pilot_labels.csv -o laya_ft.jsonl
"""
import argparse
import csv
import json
import sys

MAX_OPTIONS = 20  # vendor limit: choice degrades hard beyond ~20 options

TYPE_QUESTION = {
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
VALID_LABELS = set(TYPE_QUESTION["criteria"])  # our taxonomy = the question's criteria


def _read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            yield row.get("text", ""), row.get("label", "")


def _read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            yield r.get("text", ""), r.get("label", "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-csv", action="append", default=[])
    ap.add_argument("--from-jsonl", action="append", default=[])
    ap.add_argument("--from-memory", action="store_true",
                    help="LTM traces (needs a populated verified store; POC)")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()

    rows, skipped = [], []
    for p in args.from_csv:
        rows.extend(_read_csv(p))
    for p in args.from_jsonl:
        rows.extend(_read_jsonl(p))
    if args.from_memory:
        raise SystemExit("--from-memory: no populated verified store yet — collect "
                         "labels from the pilot first (AG News script / live traffic).")

    for text, label in rows:
        if not text or label not in VALID_LABELS:
            skipped.append((text[:40], label))
            continue
        record = {
            "state": text,
            "questions": {"task_type": TYPE_QUESTION},
            "answer": {"task_type": {"choice": label}},
            "meta": {"question_type": "choice", "n_options": len(VALID_LABELS)},
        }
        with open(args.out, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    n = len(rows) - len(skipped)
    print(f"exported {n} records -> {args.out}")
    if skipped:
        print(f"skipped {len(skipped)} (missing text or label outside {sorted(VALID_LABELS)}); "
              f"first few: {skipped[:3]}")
    print("NEXT: verify record shape against the official fine-tuning notebook "
          "before training — we do not guess training formats into production.")


if __name__ == "__main__":
    main()
