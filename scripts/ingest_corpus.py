#!/usr/bin/env python3
"""First-ingestion ritual: index a corpus dir and report coverage.

Walks <dir> for *.txt/*.md, builds the local_docs index, and prints:
  files, chunks, avg chunk size, plus per-probe-query best match scores.

Usage:
  python scripts/ingest_corpus.py ./retrieval_corpus
  python scripts/ingest_corpus.py ./docs --probe "When did..." --probe "What caused..."
  LOCAL_DOCS_DIR=./docs python scripts/ingest_corpus.py  # same via env

Exit 0 always (report, not gate); coverage gaps are for the operator to judge.
"""
import argparse
import os
import sys
from pathlib import Path as _P

_REPO = _P(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from service.connectors.local_docs import LocalDocsConnector


def main():
    ap = argparse.ArgumentParser(description="Ingest a corpus dir into local_docs and report coverage")
    ap.add_argument("dir", nargs="?", default=os.getenv("LOCAL_DOCS_DIR", "./retrieval_corpus"))
    ap.add_argument("--probe", action="append", default=[], help="probe question (repeatable)")
    ap.add_argument("--threshold", type=float, default=0.35)
    args = ap.parse_args()

    conn = LocalDocsConnector(source_dir=args.dir, match_threshold=args.threshold)
    index = conn._load_index()
    files = sorted({p for p, _ in index})
    total_chars = sum(len(c) for _, c in index)
    print(f"source_dir : {conn.source_dir} (exists={conn.source_dir.exists()})")
    print(f"files      : {len(files)}")
    print(f"chunks     : {len(index)}")
    print(f"avg chunk  : {total_chars // max(len(index), 1)} chars")
    for f in files[:20]:
        print(f"  - {f}")
    if len(files) > 20:
        print(f"  ... +{len(files) - 20} more")

    probes = args.probe or [
        "When did the Western Roman Empire fall?",
        "What caused the fall of the Roman Empire?",
    ]
    print("\nprobes (best lexical score vs threshold "
          f"{args.threshold}):")
    for q in probes:
        claims = conn.get_claims(q)
        if claims:
            print(f"  HIT  {claims[0].answer[:60]!r} <- {claims[0].source} ({claims[0].reason})")
        else:
            print(f"  MISS {q[:70]!r} — no chunk above threshold (ingest more or lower it)")


if __name__ == "__main__":
    main()
