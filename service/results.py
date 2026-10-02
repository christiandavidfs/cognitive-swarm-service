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


def verdict(name: str, data_dir=None) -> dict:
    """Automatic conclusion per board: on-track | watch | fail | thin-data.

    Thresholds are explicit and tunable (see constants). A verdict explains
    itself: status + message + the numbers behind it — early repair signal.
    """
    rows = _read(name, data_dir)
    if len(rows) < 2 and name in ("longitudinal", "market", "rounds"):
        return {"status": "thin-data", "message": "need ≥2 rows for a trend", "metrics": {"n": len(rows)}}
    if name == "longitudinal":
        accs = [r.get("acc", 0) for r in rows]
        slope = accs[-1] - accs[0]
        contested = all(r.get("contested_honest", 1) >= 1 for r in rows[-3:])
        metrics = {"acc_now": accs[-1], "acc_delta": round(slope, 3), "contested_ok": contested}
        if slope < -0.2 or not contested:
            return {"status": "fail", "message": "accuracy falling or honesty lost — investigate now",
                    "metrics": metrics}
        if slope >= 0:
            return {"status": "on-track", "message": "learning or stable, honesty intact", "metrics": metrics}
        return {"status": "watch", "message": "slight accuracy dip — next row decides", "metrics": metrics}
    if name == "market":
        stale = [r.get("stale_rate", 0) for r in rows]
        acc = [r.get("acc", 0) for r in rows]
        metrics = {"stale_now": stale[-1], "stale_delta": round(stale[-1] - stale[0], 3),
                   "acc_now": acc[-1]}
        if stale[-1] > 0.5:
            return {"status": "fail", "message": "memory mostly stale — update loop broken",
                    "metrics": metrics}
        if stale[-1] <= stale[0]:
            return {"status": "on-track", "message": "following a moving world", "metrics": metrics}
        return {"status": "watch", "message": "staleness rising — check feed/cadence", "metrics": metrics}
    if name == "formations":
        settled = sum(r.get("settled_pred", 0) for r in rows)
        won = sum(round(r.get("pred_acc", 0) * r.get("settled_pred", 0)) for r in rows)
        bases = [r.get("base_rate", 0) for r in rows if r.get("settled_pred", 0)]
        base = round(sum(bases) / len(bases), 3) if bases else 0.5
        metrics = {"settled": settled, "hit_rate": round(won / max(settled, 1), 3), "base_rate": base}
        if settled < 10:
            return {"status": "thin-data", "message": "need ≥10 settled predictions", "metrics": metrics}
        if metrics["hit_rate"] > base + 0.05:
            return {"status": "on-track", "message": "beating base rate net of noise", "metrics": metrics}
        return {"status": "fail", "message": "not beating base rate — prune families or idea",
                "metrics": metrics}
    if name == "rounds":
        mem = [r.get("memory_share", 0) for r in rows]
        metrics = {"memory_now": mem[-1], "memory_delta": round(mem[-1] - mem[0], 3)}
        if mem[-1] > mem[0]:
            return {"status": "on-track", "message": "retrieval cost decaying", "metrics": metrics}
        return {"status": "watch", "message": "memory not absorbing — check repeats", "metrics": metrics}
    return {"status": "thin-data", "message": "unknown board", "metrics": {}}


def render_html(data_dir=None) -> str:
    parts = ["<html><head><title>swarm results</title></head><body>",
             "<h1>swarm results — date → expected → actual</h1>"]
    for name in BOARDS:
        b = board(name, data_dir)
        v = verdict(name, data_dir)
        color = {"on-track": "green", "watch": "orange", "fail": "red"}.get(v["status"], "gray")
        parts.append(f"<h2>{name} (n={b['n']})"
                     + (f" trend_acc={b['trend_acc']}" if "trend_acc" in b else "") + "</h2>")
        parts.append(f"<p><b style='color:{color}'>{v['status'].upper()}</b> — {v['message']} "
                     f"<small>{v['metrics']}</small></p>")
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
