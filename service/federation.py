"""Federated process learning — minimal PoC contract.

Two instances (orgs) run the same service code but own DIFFERENT learned
procedure libraries. An org's library = discovered (pattern, formula,
procedure_sig) entries with success counters. Sharing is Q/A-data-free
(the thesis): exports carry pattern detection regexes + formula templates +
sigs + counters, never questions or connector facts.

Semantics (all versioned, all vetoable):
  export_library(...)      -> {"version", "entries": [...]}  (zero Q/A)
  import_library(payload)  -> Library of versioned PatternBlocks, weighted
  PatternBlock.solve(q)    -> {answer, trace, reliability} or None
  Local veto: outcomes decay weight; block revoked at <=50% after >=3 tries.

Safety: formula evaluation is AST-gated (digits, + - * / % ( ), declared
variables only); detection regexes compile-checked; unknown library
versions refuse loudly.
"""
from __future__ import annotations

import ast
import operator
import re
from typing import Dict, List, Optional

_FED_LIB_VERSION = "fed-1"


class PatternBlock:
    """A federated, executable procedure: detect -> extract -> evaluate."""

    def __init__(self, data: dict, origin: str = "imported"):
        self.name = data["pattern"]
        self.detect_re = re.compile(data["detect"])
        self.keys: List[str] = list(data.get("keys") or [])
        self.formula = data["formula"]
        self.trace_template = data.get("trace") or self.formula
        self.procedure_sig = data.get("procedure_sig")
        self.origin = origin
        self.attempts = int(data.get("attempts", 0))
        self.successes = int(data.get("successes", 0))
        self.base_reliability = float(data.get("reliability", 0.9))
        self.weight = self._weight()

    def _weight(self) -> float:
        rate = (self.successes / self.attempts) if self.attempts else None
        if rate is None:
            # Un-tried peer: provisional prior — never above a proven-good one.
            return round(self.base_reliability * 0.85, 3)
        # Trust is capped by the peer's claimed reliability, no matter what.
        return round(self.base_reliability * (0.3 + 0.7 * rate), 3)

    def revoked(self) -> bool:
        return self.attempts >= 3 and (self.successes / self.attempts) <= 0.5

    def solve(self, question: str) -> Optional[dict]:
        """Returns {answer, trace, procedure_sig, reliability} or None."""
        if self.revoked():
            return None
        text = question.strip().lower()
        segs = [mm.group(0) for mm in self.detect_re.finditer(text)]
        if not segs:
            return None
        # Numbers-fold, in textual order across segments; keys map positionally.
        vals: List[str] = []
        for seg in segs:
            vals.extend(re.findall(r"\d+(?:\.\d+)?", seg))
        if len(vals) < len(self.keys):
            return None
        args = dict(zip(self.keys, vals))
        ans = self._eval_args(args)
        if ans is None:
            return None
        args = {k: str(v) for k, v in args.items()}
        trace = self.trace_template.format(**args) + f" = {ans}"
        return {"answer": str(ans), "trace": trace,
                "procedure_sig": self.procedure_sig,
                "reliability": self.weight}

    def _eval_args(self, args: Dict[str, str]):
        try:
            prog = self.formula.format(**args)
            return safe_formula_eval(prog)
        except Exception:
            return None

    def record(self, success: bool) -> None:
        """Local outcome: cross-instance weighting decays on failure."""
        self.attempts += 1
        if success:
            self.successes += 1
        self.weight = self._weight()

    def export(self) -> dict:
        return {"pattern": self.name, "detect": self.detect_re.pattern,
                "keys": self.keys, "formula": self.formula,
                "trace": self.trace_template,
                "procedure_sig": self.procedure_sig,
                "attempts": self.attempts, "successes": self.successes,
                "reliability": self.base_reliability}


def export_library(pattern_blocks=None, attest_entries=None) -> dict:
    """Build a zero-Q/A library payload.

    pattern_blocks: executable procedures owned by this org (shared as code,
    detection regex included). attest_entries: deterministic LTM entries used
    as attestations only (pattern exists elsewhere, counters included) — they
    are NOT executable remotely (no keys/formula) and carry no Q/A data.
    """
    export = [b.export() for b in (pattern_blocks or [])]
    for e in attest_entries or []:
        if not _is_deterministic(e):
            continue
        export.append({"pattern": f"legacy:{e['procedure_sig']}", "detect": r"^$",
                       "keys": [], "formula": None, "trace": e.get("trace") or "",
                       "procedure_sig": e.get("procedure_sig"),
                       "attempts": e.get("attempts", 0),
                       "successes": e.get("successes", 0),
                       "reliability": 0.0})
    return {"version": _FED_LIB_VERSION, "entries": export}


def _is_deterministic(entry: dict) -> bool:
    tiers = {"executor", "math-primitives", "reasoning-primitives", "deterministic",
             "procedure"}
    rel = 0.0
    for s in entry.get("sources") or []:
        try:
            rel = max(rel, float(s.get("reliability", 0) or 0))
        except (TypeError, ValueError):
            continue
    return entry.get("tier") in tiers and bool(entry.get("procedure_sig")) and \
        bool(entry.get("trace")) and rel >= 0.999


def import_library(payload: dict, origin: str = "peer") -> "Library":
    """Validate + version-check + weight. Unknown versions refuse loudly."""
    ver = str(payload.get("version", ""))
    if ver != _FED_LIB_VERSION:
        raise ValueError(f"federation: refusing library version {ver!r} "
                         f"(this node speaks {_FED_LIB_VERSION})")
    blocks = []
    for e in payload.get("entries", []):
        if not e.get("formula"):
            continue  # attest-only entries are carried, not executable
        try:
            blocks.append(PatternBlock(e, origin=origin))
        except Exception as e2:
            raise ValueError(
                f"federation: refusing malformed entry {e.get('pattern')!r}: {e2}") from e2
    return Library(blocks)


class Library:
    """A local peer-procedure library with veto bookkeeping."""

    def __init__(self, blocks: List[PatternBlock]):
        self.blocks = [b for b in blocks if not b.revoked()]

    def solve(self, question: str) -> Optional[dict]:
        for b in self.blocks:
            r = b.solve(question)
            if r is not None:
                return r
        return None

    def find(self, name: str) -> Optional[PatternBlock]:
        for b in self.blocks:
            if b.name == name:
                return b
        return None

    def record(self, question: str, success: bool) -> None:
        for b in self.blocks:
            if b.solve(question) is not None:
                b.record(success)


# ---------------------------- formula evaluation ----------------------------

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Mod: operator.mod,
        ast.USub: operator.neg, ast.UAdd: operator.pos}


def safe_formula_eval(prog: str):
    """Raise-free AST-restricted arithmetic. Returns float or None."""
    try:
        if not re.fullmatch(r"[0-9+\-*/%().\s]+", prog):
            return None
        tree = ast.parse(prog, mode="eval")
        return _ev(tree.body)
    except Exception:
        return None


def _ev(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_ev(node.left), _ev(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_ev(node.operand))
    raise ValueError(f"unsupported node {type(node).__name__}")
