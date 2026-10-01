"""PokeAPI connector — free ground-truth facts, no key. Proves the one-file pattern.

Registered name: `pokeapi` (enabled:false by default; per-request
`connectors:["pokeapi"]` or flip in service.yaml). Answers type/height/weight
questions with exact upstream facts as high-reliability claims.
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional, Sequence

import requests

from service.contracts import SourceClaim, TaskType
from .base import Connector

logger = logging.getLogger(__name__)

_Q_RE = re.compile(r"(type|tall|height|weigh|heavy).*?(\b[a-z-]+\b)\s*\?")


class PokeAPIConnector(Connector):
    name = "pokeapi"
    categories: Optional[Sequence[TaskType]] = [TaskType.REASONING, TaskType.UNKNOWN]

    def __init__(self, reliability: float = 0.95, timeout_s: int = 8):
        self.reliability = float(reliability)
        self.timeout_s = int(timeout_s)

    def get_claims(self, question: str) -> List[SourceClaim]:
        m = _Q_RE.search(question.lower())
        if not m:
            return []
        kind, name = m.group(1), m.group(2)
        try:
            d = requests.get(f"https://pokeapi.co/api/v2/pokemon/{name}",
                             timeout=self.timeout_s).json()
        except Exception as e:
            logger.debug("PokeAPI failed: %s", e)
            return []
        try:
            if kind == "type":
                ans = d["types"][0]["type"]["name"]
            elif kind in ("tall", "height"):
                ans = str(d["height"])
            else:
                ans = str(d["weight"])
        except (KeyError, IndexError):
            return []
        return [SourceClaim(source=f"pokeapi:{name}", answer=ans,
                            reliability=self.reliability, independent=True,
                            reason="PokeAPI ground truth")]
