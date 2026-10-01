"""Corroboration: reliability-weighted agreement across multiple sources.

Service-owned (no external imports). Truth for non-deterministic domains
rarely comes from a single authority — it comes from source criticism:
reliability, independence, agreement.

  * CORROBORATED : independent sources converge.
  * CONFLICT     : reliable sources disagree -> surface disagreement honestly.
  * UNCERTAIN    : too little signal.
"""
from __future__ import annotations

from typing import Dict, List

from .contracts import SourceClaim, Verdict


class Corroborator:
    """Aggregate clashing source claims into an honest verdict."""

    INDEPENDENCE_BONUS = 0.5
    RECENCY_BONUS = 0.3  # anti-cutoff: fresh sources outvote stale ones on ties
    # A lone voice corroborates only when highly reliable (exact APIs, DBs).
    # Lexical single-hits (local-docs 0.8) stay uncertain — measured 2026-10-01:
    # a Saturn-moons article "answered" a fictional-planet question at 0.60 overlap.
    SOLO_RELIABILITY = 0.9

    def corroborate(self, claims: List[SourceClaim]) -> Verdict:
        if not claims:
            return Verdict("uncertain", None, 0.0, 0.0)

        clusters: Dict[str, dict] = {}
        for c in claims:
            key = self._norm(c.answer)
            if key not in clusters:
                clusters[key] = {
                    "answer": c.answer,
                    "weight": 0.0,
                    "best_reliability": 0.0,
                    "sources": [],
                    "independent_count": 0,
                }
            w = c.reliability
            if c.independent:
                w += self.INDEPENDENCE_BONUS
            w += (max(0.0, min(1.0, c.recency)) - 0.5) * self.RECENCY_BONUS
            clusters[key]["weight"] += w
            clusters[key]["best_reliability"] = max(clusters[key]["best_reliability"], c.reliability)
            clusters[key]["independent_count"] += 1 if c.independent else 0
            clusters[key]["sources"].append(c.source)

        total_weight = sum(cl["weight"] for cl in clusters.values())
        if total_weight <= 0:
            return Verdict("uncertain", None, 0.0, 0.0)

        best_key = max(clusters, key=lambda k: clusters[k]["weight"])
        best = clusters[best_key]
        majority_share = best["weight"] / total_weight if total_weight else 0.0

        corroborated = (
            best["independent_count"] >= 1
            and majority_share >= 0.6
            and (
                best["independent_count"] >= 2  # two independent voices agree
                or len(clusters) > 1  # contested but winner dominates
                or best["best_reliability"] >= self.SOLO_RELIABILITY  # lone exact source
            )
        )
        confidence = round(0.5 * majority_share + 0.5 * best["best_reliability"], 3)

        disagreement = [
            {
                "answer": cl["answer"],
                "sources": cl["sources"],
                "best_reliability": cl["best_reliability"],
                "weight_share": round(cl["weight"] / total_weight, 3),
            }
            for key, cl in clusters.items() if key != best_key
        ]
        provenance = [
            {
                "answer": cl["answer"],
                "sources": cl["sources"],
                "best_reliability": cl["best_reliability"],
                "weight_share": round(cl["weight"] / total_weight, 3),
            }
            for cl in clusters.values()
        ]

        if corroborated:
            return Verdict("corroborated", best["answer"], confidence,
                           best["best_reliability"], clusters, disagreement, provenance)
        if len(clusters) > 1:
            return Verdict("conflict", None, confidence,
                           best["best_reliability"], clusters, disagreement, provenance)
        return Verdict("uncertain", best["answer"], confidence,
                       best["best_reliability"], clusters, disagreement, provenance)

    @staticmethod
    def _norm(s: str) -> str:
        return s.strip().lower()
