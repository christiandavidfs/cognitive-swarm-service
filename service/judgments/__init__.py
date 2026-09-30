"""Judgments package — Juicio 1 (classify) live, rest designed.

`load_judge()` is the seam: returns the heuristic implementation now, a
Jev-backed one later (e.g. `service/judgments/jev.py`) with zero caller change.
"""
from .classify import classify_question
from .primitives import Judgment, choose, noul, score_judgment

__all__ = ["classify_question", "Judgment", "choose", "noul", "score_judgment"]
