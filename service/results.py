"""Results board — every scheduled proof renders itself. No external imports.

Reads the JSONL logs the timers append (longitudinal, market, formations,
rounds) plus the gate table, and serves date → expected → actual rows with
trend deltas. If it isn't on this board, it didn't happen.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

DATA_DIR = Path(__file__).parent.parent / "data"

BOARDS = {
    "longitudinal": "longitudinal_log.jsonl",
    "market": "market_log.jsonl",
    "formations": "formations_log.jsonl",
    "rounds": "rounds_log.jsonl",
}


def _read(name: str, data_dir=None) -> List[dict]:
    d = Path(data_dir) if data_dir else DATA_DIR
    fp = d / BOARDS[name]
    if not fp.exists():
        return []
    rows = []
    for line in fp.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def board(name: str, data_dir=None) -> dict:
    rows = _read(name, data_dir)
    out = {"board": name, "n": len(rows), "rows": rows[-12:]}
    if len(rows) >= 2 and "acc" in rows[-1] and "acc" in rows[-2]:
        out["trend_acc"] = round(rows[-1]["acc"] - rows[-2]["acc"], 3)
    return out


def summary(data_dir=None) -> dict:
    return {name: board(name, data_dir) for name in BOARDS}


def render_html(data_dir=None) -> str:
    parts = ["<html><head><title>swarm results</title></head><body>",
             "<h1>swarm results — date → expected → actual</h1>"]
    for name in BOARDS:
        b = board(name, data_dir)
        parts.append(f"<h2>{name} (n={b['n']})"
                     + (f" trend_acc={b['trend_acc']}" if "trend_acc" in b else "") + "</h2>")
        if not b["rows"]:
            parts.append("<p>no rows yet</p>")
            continue
        keys = sorted({k for r in b["rows"] for k in r.keys()})
        parts.append("<table border=1><tr>" + "".join(f"<th>{k}</th>" for k in keys) + "</tr>")
        for r in b["rows"]:
            parts.append("<tr>" + "".join(f"<td>{r.get(k, '')}</td>" for k in keys) + "</tr>")
        parts.append("</table>")
    parts.append("</body></html>")
    return "\n".join(parts)
