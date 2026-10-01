#!/usr/bin/env python3
"""Retrieval-at-scale pilot: golden facts buried in real distractors.

Builds a corpus of AG News texts (noise) + a handful of golden docs with
known answers, then probes both kinds: golden questions must HIT with the
right answer, unrelated questions must MISS (no false hit). Sweeps the match
threshold to recommend an operating point with numbers, not taste.

  python scripts/pilot_retrieval_scale.py --n 2000
"""
import argparse
import sys
import tempfile
import time
from pathlib import Path as _P

_REPO = _P(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from service.connectors.local_docs import LocalDocsConnector

GOLDEN = [
    ("golden_rome.txt",
     "The Western Roman Empire fell in 476 CE. Historians debate the causes: "
     "economic decline, barbarian invasions, and administrative division.",
     [("When did the Western Roman Empire fall?", "476 CE")]),
    ("golden_water.txt",
     "The chemical formula of water is H2O. Water boils at 100 degrees Celsius "
     "at sea level and covers 71 percent of Earth.",
     [("What is the chemical formula of water?", "H2O")]),
]

# Must MISS (no chunk should claim these with confidence).
NEGATIVES = [
    "What is the airspeed velocity of an unladen swallow?",
    "How many moons orbit the fictional planet Zorg?",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--thresholds", default="0.2,0.25,0.3,0.35,0.4,0.45,0.5")
    args = ap.parse_args()
    ths = [float(t) for t in args.thresholds.split(",")]

    from datasets import load_dataset
    ds = load_dataset("fancyzhx/ag_news", split=f"train[:{args.n}]")
    corpus = _P(tempfile.mkdtemp(prefix="corpus-"))
    for i, ex in enumerate(ds):
        (corpus / f"news_{i:04d}.txt").write_text(ex["text"][:1500])
    for fname, text, _ in GOLDEN:
        (corpus / fname).write_text(text)
    n_files = len(list(corpus.glob("*.txt")))
    print(f"corpus: {n_files} files ({args.n} distractors + {len(GOLDEN)} golden)")

    gold_qs = [(q, a) for _, _, qs in GOLDEN for q, a in qs]
    print(f"{'thr':>5} {'gold HIT':>9} {'gold RIGHT':>10} {'neg MISS':>9}")
    for th in ths:
        conn = LocalDocsConnector(source_dir=str(corpus), match_threshold=th)
        t0 = time.time()
        hits = right = 0
        for q, a in gold_qs:
            claims = conn.get_claims(q)
            if claims:
                hits += 1
                right += a.lower() in claims[0].answer.lower()
        miss = sum(1 for q in NEGATIVES if not conn.get_claims(q))
        print(f"{th:>5} {hits:>2}/{len(gold_qs):<6} {right:>2}/{len(gold_qs):<7} {miss:>2}/{len(NEGATIVES)} "
              f"({time.time() - t0:.1f}s)")
    print("RULE: highest thr with gold RIGHT == all and neg MISS == all.")


if __name__ == "__main__":
    main()
