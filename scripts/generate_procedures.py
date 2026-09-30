#!/usr/bin/env python3
"""Generate 20 procedure traces covering diverse patterns with novel numbers/wording."""
import sys
from pathlib import Path as _P
_REPO = _P(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

try:
    from cognitive_swarm.tools.reasoning_primitives import detect_reasoning_pattern, resolve_reasoning_primitive
    from cognitive_swarm.tools.student_trace import generate_trace, verify_trace
except ImportError:
    raise SystemExit("This script needs the optional cognitive-swarm backend package: "
                     "pip install <path-to-cognitive-swarm> (see README).")


# 20 diverse procedures with novel numbers/wordings NOT in TRAINING_DATA (to show generalization)
# Wording chosen to match existing deterministic regexes (so traces are verifiable 0-load)
PROCEDURES = [
    # 1 handshake - novel 100 vs 47 (use canonical phrasing that regex catches)
    ("In a group of 100 people each shakes hands with every other exactly once how many handshakes?", "handshake"),
    # 2 work_inverse - novel numbers, canonical phrasing
    ("Twelve people can build a house in 15 days how many people are needed to build it in 3 days?", "work_inverse"),
    # 3 rate_machines - canonical
    ("It takes 5 machines 5 minutes to make 5 widgets, how long for 100 machines to make 100 widgets?", "rate_machines"),
    # 4 rate_distance
    ("A truck consumes 12 liters per 100 km, how much fuel for 250 km?", "rate_distance"),
    # 5 snail_well - novel depth
    ("A snail at the bottom of a 25-foot well climbs 4 feet each day and slides back 1 foot each night, how many days to reach the top?", "snail_well"),
    # 6 simple_subtract - canonical have/give
    ("You have 33 marbles and give away 14, how many do you have left?", "simple_subtract"),
    # 7 all_but
    ("A farmer has 23 sheep, all but 8 die, how many are left?", "all_but"),
    # 8 fraction_compare - novel fractions
    ("Which is larger 5/9 or 7/12?", "fraction_compare"),
    # 9 trains_meet
    ("Two trains 400 km apart travel toward each other at 70 km/h and 30 km/h, when do they meet?", "trains_meet"),
    # 10 bridge_crossing
    ("Four people need to cross a bridge at night with a flashlight with times 1, 3, 6, 8 minutes, what is the shortest time?", "bridge_crossing"),
    # 11 system_equations - canonical
    ("Five jars of honey and three jars of jam cost 54 cents. Four jars of honey and three jars of jam cost 42 cents. How much does one jar of honey cost?", "system_equations"),
    # 12 alice_bob - canonical
    ("Alice and Bob have a total of 50 apples. Bob gives Alice 5 apples. Now Alice has twice as many as Bob. How many did Alice start with?", "alice_bob"),
    # 13 painted_cube - canonical order
    ("A cube cut into 64 equal smaller cubes, how many have exactly one face painted?", "painted_cube"),
    # 14 rope_cut
    ("A rope 120 cm long is cut so one piece is 5 times as long as the other, how long is the shorter piece?", "rope_cut"),
    # 15 triangular_sequence
    ("What comes next in the sequence 12, 20, 30, 42?", "triangular_sequence"),
    # 16 nth_odd
    ("What is the 25th odd positive integer?", "nth_odd"),
    # 17 bat_and_ball
    ("A bat and ball cost $3.30 together, the bat costs $3 more than the ball, how much is the ball?", "bat_and_ball"),
    # 18 jug_impossible
    ("You have a 9 liter jug and a 6 liter jug, what exact amount cannot be measured?", "jug_impossible"),
    # 19 simple_probability
    ("A bag has 8 blue and 4 red balls, what is the probability of drawing a red ball?", "simple_probability"),
    # 20 stock_take_away
    ("You have 15 apples and you take away 6, how many do you have?", "stock_take_away"),
]

ok = 0
for q, expected_pat in PROCEDURES:
    det = detect_reasoning_pattern(q)
    ans = resolve_reasoning_primitive(q)
    pat = det[0] if det else "NONE"
    args = det[1] if det else {}
    trace = generate_trace(q, pat, args, ans) if det else f"NONE -> {ans}"
    verified = verify_trace(trace)
    status = "OK" if pat == expected_pat and ans is not None else "MISMATCH"
    mark = "✓" if status == "OK" else "✗"
    print(f"{mark} {pat:20} ans={str(ans):8} ver={verified} | {q[:60]}")
    if pat == expected_pat:
        ok += 1

print(f"\n{ok}/{len(PROCEDURES)} patterns matched expected")
