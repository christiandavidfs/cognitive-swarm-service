#!/usr/bin/env python3
"""Gate L-1 (pre-registered 2026-11-14): does the system learn PROCEDURES?

FROZEN. Thresholds below were written before any learned-procedure code
existed and must not change after seeing results. See docs/MEASUREMENTS.md.

Battery: 30 items in 5 families the deterministic core does NOT serve today
(percent, hours->seconds, km->m, Celsius->Fahrenheit, date difference).
Each family is split:
  train    curiosity/learning may consume these (not scored by the gate)
  heldout  never shown to any learning mechanism; the gate reads only these

Truth is recomputed from operands (see `TRUTH`), so the answer key cannot
silently drift; `tests/test_learning_gate.py` re-derives every expected value.

Usage:
  python3 scripts/learning_gate.py --emit-battery evals/learning_gate_battery.json
  BACKENDS=cognitive_swarm python3 scripts/learning_gate.py --label baseline \
      --save data/learning_gate_baseline.json
  BACKENDS=cognitive_swarm python3 scripts/learning_gate.py --label cycle-4 \
      --baseline data/learning_gate_baseline.json

Offline by construction: no retrievers, no network. Memory is a scratch file
by default so a probe never writes to the live LTM.
"""
import argparse
import datetime
import json
import random
import re
import sys
from pathlib import Path as _P

_REPO = _P(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# -- frozen thresholds (gate L-1) --------------------------------------------
PASS_REL_DROP = 0.30      # escalation must fall >= 30% relative on held-out
FAIL_REL_DROP = 0.20      # less than 20% relative drop at the deadline = refuted
MIN_ACC = 0.70            # absolute floor: it must answer correctly, not just abstain
FAIL_ACC = 0.50           # below this the leg is refuted outright
MIN_CODE_SHARE = 0.30     # held-out must be genuinely acquired, not lucky
GATE_CYCLES = 4           # the verdict is only readable after 4 learning cycles


# -- families: build -> [(question, expected, operands, split)] --------------
# Chosen from a live probe (2026-11-14): these five escalate today. Rejected:
# percent and gcd (core answers correctly) and anything date-shaped (the core
# parses "2026-03-14" as 2026-3-14 = 2009 — silent wrong answers, gate-void).
def _split(i: int) -> str:
    return "train" if i % 2 == 0 else "heldout"


ROMAN = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
         (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
         (5, "V"), (4, "IV"), (1, "I")]


def to_roman(n: int) -> str:
    out = ""
    for value, sym in ROMAN:
        while n >= value:
            out += sym
            n -= value
    return out


def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a


def _next_prime(n: int) -> int:
    cand = n + 1
    while True:
        if cand > 2 and all(cand % d for d in range(2, int(cand ** 0.5) + 1)):
            return cand
        cand += 1


def family_roman(rng):
    out = []
    for i in range(6):
        n = rng.randrange(4, 200)
        out.append((f"Convert the Roman numeral {to_roman(n)} to a number",
                    n, [n], _split(i)))
    return out


def family_binary_to_decimal(rng):
    out = []
    for i in range(6):
        n = rng.randrange(5, 1024)
        out.append((f"What is the binary number {n:b} in decimal?", n, [n], _split(i)))
    return out


def family_median(rng):
    out = []
    for i in range(6):
        vals = sorted(rng.sample(range(3, 90), 5))
        median = vals[2]
        joined = ", ".join(str(v) for v in vals)
        out.append((f"What is the median of {joined}?", median, [vals], _split(i)))
    return out


def family_lcm(rng):
    out = []
    for i in range(6):
        a = rng.randrange(4, 40)
        b = rng.randrange(4, 40)
        out.append((f"What is the least common multiple of {a} and {b}?",
                    a * b // _gcd(a, b), [a, b], _split(i)))
    return out


def family_next_prime(rng):
    out = []
    for i in range(6):
        n = rng.randrange(10, 300)
        out.append((f"What is the smallest prime number greater than {n}?",
                    _next_prime(n), [n], _split(i)))
    return out


FAMILIES = {
    "roman_to_int": family_roman,
    "binary_to_decimal": family_binary_to_decimal,
    "median": family_median,
    "lcm": family_lcm,
    "next_prime": family_next_prime,
}

TRUTH = {
    "roman_to_int": lambda n: n,
    "binary_to_decimal": lambda n: n,
    "median": lambda vals: sorted(vals)[len(vals) // 2],
    "lcm": lambda a, b: a * b // _gcd(a, b),
    "next_prime": lambda n: _next_prime(n),
}

BATTERY_SEED = 20261114


def build_battery(seed: int = BATTERY_SEED):
    rng = random.Random(seed)
    items = []
    for family, builder in FAMILIES.items():
        for question, expected, operands, split in builder(rng):
            items.append({
                "family": family,
                "question": question,
                "expected": expected,
                "operands": operands,
                "split": split,
            })
    return items


# -- scoring ----------------------------------------------------------------
_NUM = re.compile(r"-?\d+(?:[.,]\d+)?")


def parse_answer(text):
    """First number in the answer, comma or dot decimal."""
    if text is None:
        return None
    m = _NUM.search(str(text))
    if not m:
        return None
    return float(m.group(0).replace(",", "."))


def classify(res):
    if res.status == "memory":
        return "memory"
    if res.tier == "retrieval":
        return "retrieval"
    if res.tier == "conflict":
        return "conflict"
    if res.tier == "debate":
        return "model"
    return "deterministic"


def gate_status(before: dict, after: dict, cycle: int) -> str:
    """No verdict before the deadline: early runs cannot be FAIL by definition."""
    if cycle < GATE_CYCLES:
        return "IN PROGRESS"
    return verdict(before, after)


def count_leakage(items, store) -> int:
    """Held-out questions must never be pre-enshrined (no memorisation path)."""
    n = 0
    for item in items:
        if item["split"] != "heldout":
            continue
        entry = store.entries.get(store.normalize(item["question"]))
        if entry is not None and store.is_servable(entry):
            n += 1
    return n


def verdict(before: dict, after: dict) -> str:
    """Arithmetic on the frozen thresholds. No interpretation allowed."""
    b_esc = before["escalated_share"]
    a_esc = after["escalated_share"]
    if b_esc <= 0:
        return "VOID"                       # nothing to improve
    if after["leakage"] != 0:
        return "FAIL"                       # memorisation path open: run invalid
    rel = (b_esc - a_esc) / b_esc
    if (rel >= PASS_REL_DROP and after["acc"] >= MIN_ACC
            and after["code_share"] >= MIN_CODE_SHARE):
        return "PASS"
    if rel < FAIL_REL_DROP or after["acc"] < FAIL_ACC:
        return "FAIL"
    return "INCONCLUSIVE"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit-battery", default="",
                    help="write the battery JSON and exit")
    ap.add_argument("--battery", default="",
                    help="battery path (default: evals/learning_gate_battery.json)")
    ap.add_argument("--label", default="run")
    ap.add_argument("--memory", default="",
                    help="memory path (default: data/learning_gate_memory.json)")
    ap.add_argument("--log", default="",
                    help="row log (default: data/learning_gate_log.jsonl)")
    ap.add_argument("--save", default="", help="also write this row to a JSON file")
    ap.add_argument("--baseline", default="", help="baseline row JSON to compare")
    ap.add_argument("--cycle", type=int, default=0,
                    help=f"learning cycle number this row belongs to "
                         f"(verdict only from cycle {GATE_CYCLES})")
    args = ap.parse_args()

    if args.emit_battery:
        path = _P(args.emit_battery)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(build_battery(), indent=2, ensure_ascii=False))
        print(f"battery -> {path} ({len(build_battery())} items)")
        return 0

    from service.backends import load_backends
    from service.memory.store import ProcedureStore
    from service.router import Router

    battery_path = _P(args.battery) if args.battery else (
        _REPO / "evals" / "learning_gate_battery.json")
    items = json.loads(battery_path.read_text())

    data = _REPO / "data"
    data.mkdir(exist_ok=True)
    mem = ProcedureStore(path=args.memory or (data / "learning_gate_memory.json"))
    backends = load_backends(memory=mem)
    router = Router(memory=mem, retrievers=[], backends=backends)

    rows = []
    leakage = count_leakage(items, mem)
    for item in items:
        key = ProcedureStore.normalize(item["question"])
        res = router.resolve(item["question"])
        bucket = classify(res)
        got = parse_answer(res.answer)
        ok = got is not None and abs(got - float(item["expected"])) < 1e-6
        entry = mem.entries.get(key) or {}
        rows.append({"family": item["family"], "split": item["split"],
                     "question": item["question"], "bucket": bucket,
                     "got": res.answer, "expected": item["expected"], "ok": ok,
                     "procedure_sig": entry.get("procedure_sig")})

    def agg(sel):
        sub = [r for r in rows if sel(r)]
        n = len(sub)
        if not n:
            return {"n": 0, "acc": 0.0, "escalated_share": 0.0, "code_share": 0.0}
        esc = sum(1 for r in sub if r["bucket"] == "model")
        code = sum(1 for r in sub if r["bucket"] in ("deterministic", "memory"))
        return {"n": n,
                "acc": round(sum(1 for r in sub if r["ok"]) / n, 3),
                "escalated_share": round(esc / n, 3),
                "code_share": round(code / n, 3)}

    heldout = agg(lambda r: r["split"] == "heldout")
    row = {
        "label": args.label,
        "date": datetime.date.today().isoformat(),
        "battery": str(battery_path.name),
        "all": agg(lambda r: True),
        "train": agg(lambda r: r["split"] == "train"),
        "heldout": heldout,
        # top-level mirrors heldout (that is what the gate reads)
        "n": heldout["n"],
        "acc": heldout["acc"],
        "escalated_share": heldout["escalated_share"],
        "code_share": heldout["code_share"],
        "leakage": leakage,
        "by_family": {f: agg(lambda r, f=f: r["family"] == f) for f in FAMILIES},
        "battery_sigs": sorted({r["procedure_sig"] for r in rows if r["procedure_sig"]}),
        "backends": [b.name for b in backends],
        "memory_entries": mem.size(),
    }

    log_path = _P(args.log) if args.log else data / "learning_gate_log.jsonl"
    with open(log_path, "a") as f:
        f.write(json.dumps(row) + "\n")
    if args.save:
        _P(args.save).write_text(json.dumps(row, indent=2))

    print(f"[{row['label']}] heldout n={row['n']} acc={row['acc']} "
          f"escalated={row['escalated_share']} code={row['code_share']} "
          f"leakage={row['leakage']}")
    for fam, m in row["by_family"].items():
        print(f"   {fam:<24} n={m['n']} acc={m['acc']} esc={m['escalated_share']} "
              f"code={m['code_share']}")

    if args.baseline:
        before = json.loads(_P(args.baseline).read_text())
        v = gate_status(before, row, args.cycle)
        rel = 0.0 if not before["escalated_share"] else round(
            (before["escalated_share"] - row["escalated_share"]) / before["escalated_share"], 3)
        print(f"\nGATE L-1 (cycle {args.cycle}/{GATE_CYCLES}): {v}  "
              f"(escalated {before['escalated_share']} -> {row['escalated_share']}, "
              f"rel drop {rel}, acc {before['acc']} -> {row['acc']}, "
              f"code {row['code_share']}, leakage {row['leakage']})")
        new_sigs = set(row["battery_sigs"]) - set(before.get("battery_sigs", []))
        print(f"   new procedure_sigs on the battery: {len(new_sigs)} "
              f"(evidence, not a criterion)")
        if v == "FAIL":
            print("   consequence: the 'learns capabilities' claim is refuted; "
                  "reposition as deterministic gateway + audited cache")
    return 0


if __name__ == "__main__":
    sys.exit(main())
