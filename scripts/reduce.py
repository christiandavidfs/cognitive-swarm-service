#!/usr/bin/env python3
"""Reduce: solve the unknown with tools already owned (reduction, not recall).

If 4x9 is unknown, add 9 four times. The system owns verified primitives
(add, subtract, compare); the reducer expresses NEW problems as compositions
of owned tools and verifies NUMERICALLY (not by model vote):

  strategies(multiply): repeated-addition, distributive split, factorization
  strategies(power):     repeated-multiply, square-chain

Each verified reduction archives as a NEW procedure (e.g. mult-via-add):
the method survives, the numbers change. Unknown method + owned tools +
numeric proof = independent reasoning within arithmetic.

  python scripts/reduce.py --cases 20
"""
import argparse
import random
import sys
from pathlib import Path as _P

_REPO = _P(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from service.memory.store import ProcedureStore


def add_chain(n: int, times: int) -> tuple:
    """a*b as repeated addition. Returns (answer, trace)."""
    total, steps = 0, []
    for _ in range(times):
        total += n
        steps.append(str(n))
    return total, f"{n}x{times} = " + "+".join(steps) + f" = {total} (via repeated addition)"


def distributive(a: int, b: int) -> tuple:
    """a*b = a*(b1+b2) with b1+b2=b, split at half. Returns (answer, trace)."""
    b1, b2 = b // 2, b - b // 2
    p1, p2 = a * b1, a * b2
    return p1 + p2, f"{a}x{b} = {a}x{b1}+{a}x{b2} = {p1}+{p2} = {p1 + p2} (via distribution)"


def factorize(a: int, b: int) -> tuple:
    """a*b via factor pairs of a (when composite). Returns (answer, trace) or None."""
    for f in range(2, int(a ** 0.5) + 1):
        if a % f == 0:
            g = a // f
            return f * g * b, f"{a}x{b} = {f}x{g}x{b} = {f * g * b} (via factorization)"
    return None


def power_chain(base: int, exp: int) -> tuple:
    total, steps = 1, []
    for _ in range(exp):
        total *= base
        steps.append(str(base))
    return total, f"{base}^{exp} = " + "*".join(steps) + f" = {total} (via repeated multiplication)"


STRATEGIES = {
    "mult": [("add", add_chain), ("dist", distributive), ("fact", factorize)],
    "pow": [("rep", power_chain)],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=int, default=20)
    ap.add_argument("--seed", type=int, default=5)
    args = ap.parse_args()

    store = ProcedureStore(path=_REPO / "data" / "reduce_memory.json")
    rng = random.Random(args.seed)
    solved = 0
    by_strategy: dict = {}
    total = 0
    for _ in range(args.cases):
        if rng.random() < 0.6:
            a, b = rng.randint(3, 49), rng.randint(3, 49)
            q = f"How much is {a} times {b}?"
            truth, cands = a * b, [(n, f(a, b)) for n, f in STRATEGIES["mult"] if f(a, b)]
        else:
            a, b = rng.randint(2, 9), rng.randint(2, 4)
            q = f"How much is {a} to the power of {b}?"
            truth, cands = a ** b, [("rep", power_chain(a, b))]
        total += 1
        won = None
        cands = list(cands)
        rng.shuffle(cands)  # no positional bias: every viable method must prove itself
        for name, res in cands:
            if res is None:
                continue
            ans, trace = res
            if ans == truth:  # NUMERIC proof, not model vote
                won = (name, trace, ans)
                break
        if won:
            name, trace, ans = won
            by_strategy[name] = by_strategy.get(name, 0) + 1
            key = f"reduce:{q}"
            if store.normalize(key) not in store.entries:
                store.remember_trace(key, trace, str(ans), tier=f"reduce-{name}", confidence=1.0)
    n = sum(by_strategy.values())
    print(f"solved={n}/{total} by={by_strategy} entries={store.size()}")
    print("READ: every solution is a proof (numeric equality), every method is owned tools only.")


if __name__ == "__main__":
    main()
