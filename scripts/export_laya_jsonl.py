#!/usr/bin/env python3
"""Gate B step 0 — export labels to LAYA fine-tune JSONL.

Sources (any combination, flag per file):
  --from-preds  predictions JSONL from bench_laya_sdk.py (label + text already
                paired) — the cheapest way to bootstrap training data
  --from-csv    CSV with columns text,label (own pilot labels; >=400 rows
                recommended before ANY fine-tune)

Output shape is a POC GUESS of the fine-tune notebook's format — the vendor's
training loop defines the real schema. Verify against
github.com/NandhaKishorM/laya → notebooks/laya_finetune_typed_decisions_2xT4_kaggle.ipynb
BEFORE training; adapt the writer, not the data.

Monotonicity note: exported labels feed a versioned checkpoint candidate.
Fine-tuning never edits the served LTM — the ratchet is untouched regardless
of what training produces.

Usage:
  python scripts/export_laya_jsonl.py --from-preds data/laya_td_agnews.preds.jsonl \
      -o data/laya_ft_agnews.jsonl
  python scripts/export_laya_jsonl.py --from-csv labels.csv --text-col text --label-col label \
      -o data/laya_ft_own.jsonl
"""
import argparse
import csv
import json
from pathlib import Path


def _record(text: str, label: str, question: dict) -> dict:
    # POC shape: one state, one typed question, the observed answer.
    # VERIFY against the official fine-tune notebook before training.
    return {"state": text, "questions": {question["name"]: {
        "type": question["type"], "instructions": question["instructions"],
        "criteria": question["criteria"]}},
        "answers": {question["name"]: {"choice": label}}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-preds", help="bench_laya_sdk.py predictions JSONL")
    ap.add_argument("--from-csv", help="CSV with text,label columns")
    ap.add_argument("--text-col", default="text")
    ap.add_argument("--label-col", default="label")
    ap.add_argument("--question-name", default="desk")
    ap.add_argument("--instructions",
                    default="Which category does this belong to? Use the criteria definitions.")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()

    rows = []
    if args.from_preds:
        for line in Path(args.from_preds).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            rows.append((r["text"], r["label"]))
    if args.from_csv:
        with open(args.from_csv, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rows.append((row[args.text_col], row[args.label_col]))
    if not rows:
        raise SystemExit("nothing to export (pass --from-preds and/or --from-csv)")

    # Infer the choice space from the observed labels so criteria covers them.
    labels = sorted({label for _, label in rows})
    question = {"name": args.question_name, "type": "choice",
                "instructions": args.instructions,
                "criteria": {label: f"belongs to category '{label}'" for label in labels}}
    if len(labels) > 20:
        print(f"WARNING: {len(labels)} options — vendor recommends <20 per choice "
              "question; consider hierarchical coarse-to-fine export.")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(_record(t, l, question)) for t, l in rows),
                   encoding="utf-8")
    print(f"exported {len(rows)} records -> {out}")
    print(f"labels: {labels}")
    print("NEXT: verify the record shape against the official fine-tune notebook")
    print("(github.com/NandhaKishorM/laya) BEFORE training — this writer is a POC guess.")


if __name__ == "__main__":
    main()
