"""Rounds metric tests: cohort buckets and row math (no network, no model).

The 2026-10-29 flaw: the old row counted "not memory and not retrieval" as
escalation, which with a live feed and no backends is structurally 0. These
tests pin the replaced semantics: buckets are explicit, escalation = reached
the model tier, and memory shares are per cohort.
"""
import random
import re

from service.contracts import Resolution
from scripts.rounds_continuous import (build_row, classify, new_cohort,
                                       procedure_questions)


def test_classify_buckets():
    assert classify(Resolution("electric", 1.0, "memory", "retrieval")) == "memory"
    assert classify(Resolution("1.0", 0.9, "retrieval", "retrieval")) == "retrieval"
    assert classify(Resolution(None, 0.4, "retrieval", "conflict")) == "conflict"
    assert classify(Resolution(None, 0.0, "none", "debate")) == "escalated"
    assert classify(Resolution("190", 1.0, "executor", "executor")) == "deterministic"


def test_build_row_cohort_math():
    cohorts = {c: new_cohort() for c in ("new", "rep", "proc", "irr")}
    # new: 2 memory, 1 retrieval, 1 escalated; one wrong (scored 4, ok 3)
    cohorts["new"].update(n=4, memory=2, retrieval=1, escalated=1,
                          abstain=1, scored=4, ok=3)
    cohorts["rep"].update(n=2, memory=2, scored=2, ok=2)
    cohorts["proc"].update(n=4, deterministic=4, scored=4, ok=4)
    cohorts["irr"].update(n=2, escalated=2, abstain=2)

    row = build_row(1, cohorts, lat=0.4, entries=90, backends=["cognitive_swarm"])

    assert row["n_total"] == 12
    assert row["acc"] == 0.9                 # 9/10 scored (irr excluded)
    assert row["memory_share_new"] == 0.5
    assert row["memory_share_rep"] == 1.0
    assert row["deterministic_share"] == round(4 / 12, 3)
    assert row["escalation_share"] == round(3 / 12, 3)   # 1 new + 2 irr
    assert row["honest_abstain_share"] == 1.0
    assert row["backends"] == ["cognitive_swarm"]


def test_escalation_is_zero_only_when_everything_is_local():
    """The old bug pinned: retrieval answers alone must NOT count as escalation."""
    cohorts = {c: new_cohort() for c in ("new", "rep", "proc", "irr")}
    cohorts["new"].update(n=4, retrieval=4, scored=4, ok=4)
    row = build_row(1, cohorts, lat=0.1, entries=0, backends=[])
    assert row["escalation_share"] == 0.0
    # and it moves when the model tier is actually reached
    cohorts["new"].update(n=4, retrieval=2, escalated=2, scored=4, ok=2)
    row2 = build_row(1, cohorts, lat=0.1, entries=0, backends=[])
    assert row2["escalation_share"] == 0.5


def test_procedure_questions_have_exact_truth():
    items = procedure_questions(random.Random(7), 20)
    assert len(items) == 20
    for q, expected in items:
        assert expected.isdigit()
        if "handshakes" in q:
            n = int(re.search(r"group of (\d+)", q).group(1))
            assert int(expected) == n * (n - 1) // 2
        else:
            a, b = map(int, re.search(r"print\((\d+)\*(\d+)\)", q).groups())
            assert int(expected) == a * b
