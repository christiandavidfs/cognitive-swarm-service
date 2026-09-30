"""Emergent families — categories the system creates by itself. No external imports.

A family is `{id, pattern, sigs, successes, attempts, members}`: questions that
get solved the same way, grouped by shared backend pattern or signature
overlap. Nobody declares families; they condense out of verified experience:

  unknown + similar signature, K times → candidate family
  candidate + N verified instances → first-class family (own routing stats)
  the name is optional decoration — routing needs sig + stats, not words.

A new subject tomorrow (quantum physics, xeno-law, whatever) doesn't need a
category to exist first: its questions land as unknowns, cluster by how they
get solved, and become a family with measured success rates. Recognition
(`recognize`) tells the router where things go and what to try, with
confidence — low confidence means "genuinely new", not "misfit".
"""
from __future__ import annotations

import hashlib
import re
import time
from typing import Dict, List, Optional


def _tokens(s: str) -> List[str]:
    return re.findall(r"[a-z][a-z0-9']*", s.lower())


class FamilyStore:
    """In-memory family registry. Persist via to_dict/from_dict if needed."""

    def __init__(self, candidate_threshold: int = 3, promote_threshold: int = 5):
        self.candidate_threshold = int(candidate_threshold)
        self.promote_threshold = int(promote_threshold)
        self.families: Dict[str, dict] = {}
        # unknowns waiting to condense: key -> {pattern, sig, questions, hits}
        self._seeds: Dict[str, dict] = {}

    # -- identity ------------------------------------------------------
    @staticmethod
    def _seed_key(pattern: Optional[str], sig: Optional[str]) -> str:
        raw = (pattern or "") + "|" + (sig or "")
        return hashlib.sha256(raw.encode()).hexdigest()[:12]

    @staticmethod
    def _overlap(a: str, b: str) -> float:
        ta, tb = set(_tokens(a)), set(_tokens(b))
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / max(len(ta), len(tb))

    # -- observe -------------------------------------------------------
    def observe(self, question: str, pattern: Optional[str], sig: Optional[str],
                success: bool) -> Optional[str]:
        """Feed one verified outcome. Returns the family id if it belongs to one."""
        fam = self._match(question, pattern, sig)
        if fam is not None:
            fam["attempts"] += 1
            fam["successes"] += 1 if success else 0
            fam["last_seen"] = time.time()
            return fam["id"]
        if success:
            self._seed(question, pattern, sig)
        return None

    def _match(self, question: str, pattern: Optional[str], sig: Optional[str]) -> Optional[dict]:
        for fam in self.families.values():
            if pattern and pattern == fam.get("pattern"):
                return fam
            if sig and sig in fam.get("sigs", []):
                return fam
        return None

    def _seed(self, question: str, pattern: Optional[str], sig: Optional[str]) -> None:
        key = self._seed_key(pattern, sig)
        seed = self._seeds.setdefault(key, {"pattern": pattern, "sig": sig,
                                            "questions": [], "hits": 0})
        if len(seed["questions"]) < 8:
            seed["questions"].append(question[:140])
        seed["hits"] += 1
        if seed["hits"] >= self.candidate_threshold:
            self._promote(key, seed)

    def _promote(self, key: str, seed: dict) -> str:
        fam_id = f"fam_{key[:8]}"
        if fam_id not in self.families:
            self.families[fam_id] = {
                "id": fam_id, "pattern": seed["pattern"],
                "sigs": [seed["sig"]] if seed["sig"] else [],
                "successes": seed["hits"], "attempts": seed["hits"],
                "members": list(seed["questions"]),
                "born_at": time.time(), "last_seen": time.time(),
                "name": None,  # humans may name it later; routing doesn't care
            }
        else:
            fam = self.families[fam_id]
            if seed["sig"] and seed["sig"] not in fam["sigs"]:
                fam["sigs"].append(seed["sig"])
        del self._seeds[key]
        return fam_id

    # -- recognize -----------------------------------------------------
    def recognize(self, question: str, pattern: Optional[str] = None,
                  sig: Optional[str] = None) -> dict:
        """Where does this go / what to use? Returns {family, confidence, stats}.

        Confidence blends identity strength (exact pattern/sig match) with the
        family's measured success. No match → {family: None, confidence: 0.0}:
        genuinely new, route by fallback, observe the outcome.
        """
        fam = self._match(question, pattern, sig)
        if fam is None:
            # Soft match: overlap with member questions.
            best, best_score = None, 0.0
            for f in self.families.values():
                for m in f.get("members", [])[:8]:
                    s = self._overlap(question, m)
                    if s > best_score:
                        best, best_score = f, s
            if best is None or best_score < 0.5:
                return {"family": None, "confidence": 0.0, "stats": None}
            fam, soft = best, True
        else:
            soft = False
        attempts = fam.get("attempts", 0)
        rate = (fam.get("successes", 0) / attempts) if attempts else 0.5
        identity = 0.6 if soft else 1.0
        confidence = round(identity * (0.5 + 0.5 * rate), 3)
        return {"family": fam["id"], "confidence": confidence,
                "stats": {"successes": fam.get("successes", 0), "attempts": attempts,
                          "pattern": fam.get("pattern"), "name": fam.get("name")}}

    # -- naming (optional, human comfort only) --------------------------
    def name(self, family_id: str, name: str) -> bool:
        if family_id in self.families:
            self.families[family_id]["name"] = name
            return True
        return False

    def to_dict(self) -> dict:
        return {"families": self.families}

    def load_dict(self, data: dict) -> None:
        if isinstance(data, dict) and isinstance(data.get("families"), dict):
            self.families = data["families"]
