#!/usr/bin/env python3
"""Judge-as-verifier: can a small judge check traces where NO formula exists?

Battery of arithmetic traces (correct + slips + format breaks) with known
truth. The judge answers Noul("Is the arithmetic in this trace correct?").
Metric: agreement judge-vs-truth. High agreement → debate can verify open
domains (analyses, paraphrases, research). Low → judges don't verify.

Needs a SystemOne judge up (Kev :8019 or Laya :8021):
  KEV_BASE_URL=http://127.0.0.1:8019 python scripts/judge_verify.py
"""
import os
import sys
from pathlib import Path as _P

_REPO = _P(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

CASES = [
    ("handshake n=20: pairs = 20*19/2 = 190. ANSWER: 190", True),
    ("handshake n=20: pairs = 20*19/2 = 180. ANSWER: 180", False),
    ("work: builders = 10*20/5 = 40. ANSWER: 40", True),
    ("work: builders = 10*20/5 = 400. ANSWER: 400", False),
    ("5 machines make 5 widgets in 5 minutes, so 100 machines need 100 minutes. ANSWER: 100", False),
    ("5 machines make 5 widgets in 5 minutes, so rate is 1 widget per machine per 5 min; "
     "100 machines make 100 widgets in 5 minutes. ANSWER: 5", True),
    ("2+2=5. ANSWER: 5", False),
    ("7*6=42. ANSWER: 42", True),
    ("cube 64: one-face cubes = 6*(4-2)^2 = 24. ANSWER: 24", True),
    ("cube 64: one-face cubes = 6*4^2 = 96. ANSWER: 96", False),
]


def main():
    os.environ.setdefault("JEV_VIA", "typesafe")
    os.environ.setdefault("TYPESAFE_BASE_URL", os.getenv("KEV_BASE_URL", "http://127.0.0.1:8019"))
    os.environ.setdefault("TYPESAFE_API_KEY", "local")
    from service.judgments.jev import system_one

    agree = n = 0
    for trace, truth in CASES:
        try:
            ans = system_one(
                state=trace,
                questions={"ok": {"type": "noul",
                                  "instructions": "Is every arithmetic step and the final answer correct?"}},
            )["ok"]
        except Exception as e:
            print(f"SKIP ({e})")
            continue
        p = float(ans.get("noul", 0.5))
        verdict = p >= 0.5
        ok = verdict == truth
        agree += ok
        n += 1
        print(f"{'OK ' if ok else 'MISS'} p={p:.2f} truth={truth} :: {trace[:70]}")
    print(f"\njudge-verifier agreement: {agree}/{n}={agree / max(n, 1):.2f}")
    print("READ: high → debate extends StarGen to formula-less domains; low → judges don't verify.")


if __name__ == "__main__":
    main()
