#!/usr/bin/env python3
"""Paraphrase benchmark — the distillation gate (Fase 5 decision).

Compares regex detectors vs TF-IDF student on SAME-semantics rewordings
(new numbers, new phrasing, trick preserved). Reports per-question:
regex pattern vs student pattern vs expected.

Needs the optional cognitive-swarm package (clear error otherwise).
Run: PYTHONPATH=<core> python scripts/bench_paraphrase.py

Decision rule: build the weekly distillation pipeline only if the student
covers a real regex gap (misses that matter) without adding silent errors.
"""
import sys
from pathlib import Path as _P

_REPO = _P(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# CASES is plain domain data — importable WITHOUT the optional cognitive-swarm
# package (bench_laya.py reuses it). The heavy imports live inside main().
try:
    from cognitive_swarm.tools.reasoning_primitives import detect_reasoning_pattern  # noqa: F401
    from cognitive_swarm.tools.student_router import predict  # noqa: F401
except ImportError:
    detect_reasoning_pattern = predict = None

# (question, expected_pattern) — rewordings preserve semantics (incl. tricks).
CASES = [
    ("In a group of 47 people each shakes hands with every other exactly once how many handshakes?", "handshake"),
    ("At a party with 30 guests every pair shakes hands once, how many handshakes in total?", "handshake"),
    ("Sixty coworkers each shake hands with all others once, total handshakes?", "handshake"),
    ("You have 5 apples and you take away 2, how many do you have?", "stock_take_away"),
    ("You have 7 oranges and you take away 3, how many do you have?", "stock_take_away"),
    ("If you have 100 marbles and give away 45, how many do you have left?", "simple_subtract"),
    ("A shopkeeper has 60 coins and hands out 17, how many remain?", "simple_subtract"),
    ("Twelve builders can build a house in 15 days, how many needed for 3 days?", "work_inverse"),
    ("Eight painters paint a fence in 20 days, how many painters to finish in 8 days?", "work_inverse"),
    ("How many animals of each kind did Moses take on the ark?", "stock_moses"),
    ("In the biblical story how many animals of each kind did Moses take on the ark?", "stock_moses"),
    ("If you overtake the second person in a race, what place are you in?", "stock_race"),
]


def main():
    print(f"{'expected':16} {'regex':16} {'tfidf(conf)':22} question")
    reg_ok = stu_ok = reg_miss = stu_wrong = 0
    for q, exp in CASES:
        det = detect_reasoning_pattern(q)
        reg = det[0] if det else None
        try:
            sp = predict(q)
            stu, conf = sp if sp else (None, 0.0)
        except Exception:
            stu, conf = None, 0.0
        reg_hit = "OK " if reg == exp else ("MISS" if reg is None else "WRONG")
        stu_hit = "ok " if stu == exp else ("miss" if stu is None else "WRONG")
        reg_ok += reg_hit == "OK "
        stu_ok += stu_hit == "ok "
        reg_miss += reg_hit == "MISS"
        stu_wrong += stu_hit == "WRONG"
        stu_s = f"{stu}({conf:.2f})"
        print(f"{exp:16} {str(reg):16} {stu_s:22} {q[:55]}  [{reg_hit}/{stu_hit}]")
    n = len(CASES)
    print(f"\nregex:   {reg_ok}/{n} correct, {reg_miss} miss (loud), {n - reg_ok - reg_miss} wrong (silent)")
    print(f"tf-idf:  {stu_ok}/{n} correct, {stu_wrong} wrong (silent)")
    print("GATE: distill iff student fixes regex misses with ~zero silent wrongs.")


if __name__ == "__main__":
    main()
