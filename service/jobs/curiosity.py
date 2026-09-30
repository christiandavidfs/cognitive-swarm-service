"""Curiosity engine — operators 1 (numbers) and 2 (composition). No external imports.

Generates NEW questions from verified LTM entries, verifies each through a
backend, and archives only what verifies. Failures are recorded as detector
blind spots (the map of own ignorance), never as knowledge.

  Op1 numbers: swap integers in a verified question text → solve → same
      procedure_sig family? → archive as new-numbers instance.
  Op2 compose: inject a verified numeric answer as a number into another
      verified question → solve → archive if verified (genuine composition).

Targeting: source patterns with fewest archived instances go first
(ignorance-first). Budget caps every run. Redaction (op3) arrives with the
distilled reasoner — Qwen only rewords, never invents.
"""
from __future__ import annotations

import logging
import random
import re
from typing import Dict, List, Optional

from service.memory.store import _procedure_sig

logger = logging.getLogger(__name__)

_NUM_RE = re.compile(r"\d+")


def _swap_numbers(text: str, rng: random.Random) -> Optional[str]:
    nums = list(_NUM_RE.finditer(text))
    if not nums:
        return None
    out = text
    for m in reversed(nums):
        old = int(m.group())
        span = max(old, 10)
        new = rng.randint(max(2, old - span), old + span + 20)
        if new == old:
            new = old + rng.randint(1, 9)
        out = out[:m.start()] + str(new) + out[m.end():]
    return out if out != text else None


class CuriosityEngine:
    def __init__(self, store, backends=None, budget_per_run: int = 20, seed: int = 7):
        self.store = store
        self.backends = list(backends or [])
        self.budget = int(budget_per_run)
        self.rng = random.Random(seed)
        self.blind_spots: List[dict] = []

    # -- sourcing ------------------------------------------------------
    def _families(self) -> Dict[str, list]:
        """Group verified entries by procedure family (trace head or sig)."""
        fams: Dict[str, list] = {}
        for e in self.store.entries.values():
            if not e.get("verified", True):
                continue
            trace = e.get("trace") or ""
            key = trace.split()[0] if trace else (e.get("procedure_sig") or "?")
            fams.setdefault(key, []).append(e)
        # Ignorance-first: least-archived families first.
        return dict(sorted(fams.items(), key=lambda kv: len(kv[1])))

    def _solve(self, question: str):
        for b in self.backends:
            try:
                ans = b.solve(question)
            except Exception:
                continue
            if ans is not None and ans.answer is not None:
                return ans
        return None

    def _try_archive(self, question: str, source_sig: Optional[str],
                     report: dict, op: str) -> bool:
        if self.store.normalize(question) in self.store.entries:
            return False  # not novel as text
        solved = self._solve(question)
        if solved is None:
            self.blind_spots.append({"op": op, "question": question[:120]})
            report["blind_spots"] += 1
            return False
        trace = solved.trace or f"{solved.pattern or '?'} -> {solved.answer}"
        sig = _procedure_sig(trace)
        if source_sig and sig != source_sig:
            # Solved, but NOT the same process — interesting, not this family's child.
            self.blind_spots.append({"op": op, "question": question[:120], "note": "process drift"})
            report["blind_spots"] += 1
            return False
        self.store.remember_trace(question, trace, solved.answer,
                                  tier=solved.tier, confidence=0.99)
        try:
            self.store.record_outcome(question, True)
        except Exception:
            pass
        report["archived"] += 1
        return True

    # -- operators -----------------------------------------------------
    def op1_numbers(self, entry: dict, report: dict) -> None:
        new_q = _swap_numbers(entry.get("question", ""), self.rng)
        if not new_q:
            return
        report["generated"] += 1
        self._try_archive(new_q, entry.get("procedure_sig"), report, "numbers")

    def op2_compose(self, entry_a: dict, entry_b: dict, report: dict) -> None:
        """Inject A's numeric answer into B's first number slot."""
        try:
            seed_num = int(str(entry_a.get("answer", "")).strip().split()[0])
        except (ValueError, IndexError):
            return
        qb = entry_b.get("question", "")
        m = _NUM_RE.search(qb)
        if not m or seed_num < 2:
            return
        new_q = qb[:m.start()] + str(seed_num) + qb[m.end():]
        if new_q == qb:
            return
        report["generated"] += 1
        self._try_archive(new_q, None, report, "compose")  # family may legitimately change

    # -- run -----------------------------------------------------------
    def run(self) -> dict:
        report = {"generated": 0, "archived": 0, "blind_spots": 0, "ops": {"numbers": 0, "compose": 0}}
        fams = self._families()
        pool = [e for fam in fams.values() for e in fam]
        if not pool:
            return report
        spent = 0
        i = 0
        while spent < self.budget and i < len(pool) * 3:
            entry = pool[i % len(pool)]
            self.op1_numbers(entry, report)
            report["ops"]["numbers"] += 1
            spent += 1
            if spent < self.budget and len(pool) > 1:
                other = pool[(i + 1) % len(pool)]
                if other is not entry:
                    self.op2_compose(entry, other, report)
                    report["ops"]["compose"] += 1
                    spent += 1
            i += 1
        return report
