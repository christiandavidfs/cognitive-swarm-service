#!/usr/bin/env python3
"""
Seed Databricks sample data for Cognitive Swarm Service.

Creates/refreshes:
  - testing.testing_schema.swarm_knowledge (factual knowledge, Tier 3)
  - testing.testing_schema.swarm_procedures (traces, procedure memory seed)

Uses the Statement Execution API via `databricks auth token` (U2M).
Warehouse defaults to $DATABRICKS_WAREHOUSE_ID (see .env.example).

Usage:
  python scripts/seed_databricks.py              # seed both tables (idempotent)
  python scripts/seed_databricks.py --clear      # drop and reseed
  python scripts/seed_databricks.py --query "When did the Western Roman Empire fall?"
  python scripts/seed_databricks.py --verify     # run the 3 curl-equivalent checks via SQL
  python scripts/seed_databricks.py --add "Q?|A?|source|reliability|category"  # quick add one row
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

HOST = os.getenv("DATABRICKS_HOST", "")
WAREHOUSE = os.getenv("DATABRICKS_WAREHOUSE_ID", "")
CATALOG = os.getenv("DATABRICKS_CATALOG", "testing")
SCHEMA = os.getenv("DATABRICKS_SCHEMA", "testing_schema")

KNOWLEDGE_TABLE = f"{CATALOG}.{SCHEMA}.swarm_knowledge"
PROCEDURES_TABLE = f"{CATALOG}.{SCHEMA}.swarm_procedures"

SAMPLE_KNOWLEDGE = [
    (1, "When did the Western Roman Empire fall?", "476 CE", "databricks:testing.swarm_knowledge:1", 0.95, "history"),
    (2, "What is the chemical formula of water?", "H2O", "databricks:testing.swarm_knowledge:2", 0.98, "science"),
    (3, "What is the speed of light in vacuum?", "299,792,458 metres per second", "databricks:testing.swarm_knowledge:3", 0.99, "science"),
    # contested pair — same question, two answers → service surfaces disagreement
    (4, "What caused the fall of the Roman Empire?", "economic decline", "databricks:testing.swarm_knowledge:4a", 0.80, "history"),
    (5, "What caused the fall of the Roman Empire?", "barbarian invasions", "databricks:testing.swarm_knowledge:5b", 0.80, "history"),
    (6, "Who discovered penicillin?", "Alexander Fleming", "databricks:testing.swarm_knowledge:6", 0.92, "history"),
    (7, "What is the capital of France?", "Paris", "databricks:testing.swarm_knowledge:7", 0.95, "geography"),
]

SAMPLE_PROCEDURES = [
    (1, "In a group of 47 people each shakes hands once", "handshake", '{"n":47}', "n=47, handshake = n*(n-1)/2 = 47*46/2 = 1081", "1081", True),
    (2, "Ten people can build a house in 20 days how many people needed to build it in 5 days?", "work_inverse", '{"n1":10,"t1":20,"t2":5}', "n1=10, t1=20, t2=5, n2 = n1*t1/t2 = 10*20/5 = 40", "40", True),
]


def get_token() -> str:
    tok = os.getenv("DATABRICKS_TOKEN")
    if tok:
        return tok
    out = subprocess.check_output(["databricks", "auth", "token", "--output", "json"], timeout=10)
    return json.loads(out.decode())["access_token"]


def _require_config():
    missing = [k for k, v in {"DATABRICKS_HOST": HOST, "DATABRICKS_WAREHOUSE_ID": WAREHOUSE}.items() if not v]
    if missing:
        raise SystemExit(f"Missing required env: {', '.join(missing)}. See .env.example.")


def run_sql(sql: str, wait: str = "20s") -> dict:
    tok = get_token()
    r = requests.post(
        f"{HOST}/api/2.0/sql/statements",
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
        json={"warehouse_id": WAREHOUSE, "statement": sql, "wait_timeout": wait},
        timeout=30,
    )
    r.raise_for_status()
    sid = r.json()["statement_id"]
    for _ in range(10):
        time.sleep(2)
        p = requests.get(f"{HOST}/api/2.0/sql/statements/{sid}", headers={"Authorization": f"Bearer {tok}"}, timeout=15)
        p.raise_for_status()
        j = p.json()
        state = j.get("status", {}).get("state")
        if state in ("SUCCEEDED", "FAILED", "CANCELED"):
            if state != "SUCCEEDED":
                raise RuntimeError(f"SQL failed {state}: {j}")
            return j
    raise TimeoutError(f"SQL still {state}: {sql[:200]}")


def seed(clear: bool = False):
    if clear:
        print("Dropping tables if exist...")
        run_sql(f"DROP TABLE IF EXISTS {KNOWLEDGE_TABLE}")
        run_sql(f"DROP TABLE IF EXISTS {PROCEDURES_TABLE}")

    print(f"Creating {KNOWLEDGE_TABLE}...")
    run_sql(
        f"CREATE TABLE IF NOT EXISTS {KNOWLEDGE_TABLE} "
        "(id INT, question STRING, answer STRING, source STRING, reliability DOUBLE, category STRING, created_at TIMESTAMP) USING DELTA"
    )
    print(f"Creating {PROCEDURES_TABLE}...")
    run_sql(
        f"CREATE TABLE IF NOT EXISTS {PROCEDURES_TABLE} "
        "(id INT, question STRING, pattern STRING, args STRING, trace STRING, answer STRING, verified BOOLEAN, created_at TIMESTAMP) USING DELTA"
    )

    # Idempotent: delete sample ids then reinsert
    print("Refreshing sample knowledge (7 rows)...")
    ids = ",".join(str(r[0]) for r in SAMPLE_KNOWLEDGE)
    run_sql(f"DELETE FROM {KNOWLEDGE_TABLE} WHERE id IN ({ids})")
    vals = []
    for r in SAMPLE_KNOWLEDGE:
        q = r[1].replace("'", "''")
        a = r[2].replace("'", "''")
        vals.append(f"({r[0]}, '{q}', '{a}', '{r[3]}', {r[4]}, '{r[5]}', current_timestamp())")
    values = ",\n  ".join(vals)
    run_sql(f"INSERT INTO {KNOWLEDGE_TABLE} VALUES\n  {values}")

    print("Refreshing sample procedures (2 rows)...")
    pids = ",".join(str(r[0]) for r in SAMPLE_PROCEDURES)
    run_sql(f"DELETE FROM {PROCEDURES_TABLE} WHERE id IN ({pids})")
    pvals = []
    for r in SAMPLE_PROCEDURES:
        q = r[1].replace("'", "''")
        args = r[3].replace("'", "''")
        tr = r[4].replace("'", "''")
        pvals.append(f"({r[0]}, '{q}', '{r[2]}', '{args}', '{tr}', '{r[5]}', {str(r[6]).lower()}, current_timestamp())")
    pvalues = ",\n  ".join(pvals)
    run_sql(f"INSERT INTO {PROCEDURES_TABLE} VALUES\n  {pvalues}")

    print("Done. Verifying...")
    for q in ["When did the Western Roman Empire fall?", "What caused the fall of the Roman Empire?", "What is the chemical formula of water?"]:
        qe = q.replace("'", "''")[:40]
        j = run_sql(f"SELECT answer, source FROM {KNOWLEDGE_TABLE} WHERE question ILIKE '%{qe}%' LIMIT 5")
        arr = j.get("result", {}).get("data_array", [])
        print(f"  {q[:45]} -> {arr}")


def query(question: str):
    q = question.replace("'", "''")
    j = run_sql(f"SELECT answer, source, reliability FROM {KNOWLEDGE_TABLE} WHERE question ILIKE '%{q}%' LIMIT 5")
    arr = j.get("result", {}).get("data_array", [])
    if not arr:
        print("(no rows)")
    for row in arr:
        print(f"answer={row[0]!r} source={row[1]!r} reliability={row[2]}")


def add_row(spec: str):
    # spec: "question|answer|source|reliability|category"
    parts = spec.split("|")
    if len(parts) != 5:
        print("Expected 5 pipe-separated fields: question|answer|source|reliability|category", file=sys.stderr)
        sys.exit(2)
    q, a, src, rel, cat = [p.strip() for p in parts]
    qe = q.replace("'", "''")
    ae = a.replace("'", "''")
    # pick next id
    j = run_sql(f"SELECT COALESCE(MAX(id),0)+1 FROM {KNOWLEDGE_TABLE}")
    nxt = j["result"]["data_array"][0][0]
    run_sql(
        f"INSERT INTO {KNOWLEDGE_TABLE} VALUES ({nxt}, '{qe}', '{ae}', '{src}', {float(rel)}, '{cat}', current_timestamp())"
    )
    print(f"Inserted id={nxt}")


def verify():
    # Mirrors your 3 curls but via SQL directly
    for q in [
        "When did the Western Roman Empire fall?",
        "What caused the fall of the Roman Empire?",
        "What is the chemical formula of water?",
    ]:
        print(f"\nQ: {q}")
        query(q)
    j = run_sql(f"SELECT 'knowledge' as tbl, count(*) FROM {KNOWLEDGE_TABLE} UNION ALL SELECT 'procedures', count(*) FROM {PROCEDURES_TABLE}")
    print("\ncounts:", j["result"]["data_array"])


def main():
    ap = argparse.ArgumentParser(description="Seed Databricks sample data for swarm service")
    ap.add_argument("--clear", action="store_true", help="drop and recreate tables")
    ap.add_argument("--query", type=str, help="query question ILIKE")
    ap.add_argument("--add", type=str, metavar="SPEC", help="add one knowledge row: 'question|answer|source|reliability|category'")
    ap.add_argument("--verify", action="store_true", help="verify sample queries")
    args = ap.parse_args()
    _require_config()
    if args.query:
        query(args.query)
    elif args.add:
        add_row(args.add)
    elif args.verify:
        verify()
    else:
        seed(clear=args.clear)
        verify()


if __name__ == "__main__":
    # Friendly hint when invoked as `python` on macOS where only `python3` exists
    if sys.version_info[0] < 3:
        print("Use python3, not python (macOS): python3 scripts/seed_databricks.py --verify", file=sys.stderr)
        sys.exit(1)
    main()
