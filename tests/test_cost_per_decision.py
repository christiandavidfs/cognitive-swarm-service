"""Cost-per-decision tests: stream composition + accounting (no network, no model)."""
import random

from service.contracts import Resolution
from scripts.cost_per_decision import build_round, classify, summarize


def test_build_round_composition():
    rng = random.Random(1)
    names = [f"p{i}" for i in range(100)]
    items = build_round(rng, names[:40], names[40:], 100)
    assert len(items) == 100
    cohorts = [c for c, _, _ in items]
    assert cohorts.count("recurring") == 60
    assert cohorts.count("fresh") == 20
    assert cohorts.count("proc") == 10
    assert cohorts.count("open") == 10
    # facts carry (name, kind) symbols; open carries None; proc carries truth
    for cohort, q, sym in items:
        assert isinstance(q, str) and q
        if cohort in ("recurring", "fresh"):
            assert sym[0] == "fact" and sym[2] in ("type", "height")
        if cohort == "open":
            assert sym is None
        if cohort == "proc":
            assert sym[0] == "value" and sym[1].isdigit()


def test_build_round_rejects_bad_shares():
    rng = random.Random(1)
    try:
        build_round(rng, ["a"], ["b"], 100, 0.5, 0.2, 0.1, 0.1)
    except ValueError:
        return
    raise AssertionError("shares that do not sum to 1.0 must raise")


def test_summarize_counts_and_per_100():
    results = [
        ("recurring", "memory", True, True, 0.001),
        ("recurring", "memory", True, True, 0.001),
        ("recurring", "retrieval", True, True, 0.050),
        ("fresh", "retrieval", True, True, 0.050),
        ("proc", "deterministic", True, True, 0.002),
        ("open", "model", False, False, 0.000),
    ]
    row = summarize(1, results, n_decisions=6)
    assert row["network_per_100"] == round(100 * 2 / 6, 1)
    assert row["model_per_100"] == round(100 * 1 / 6, 1)
    assert row["external_per_100"] == round(100 * 3 / 6, 1)
    assert row["memory_share"] == round(2 / 6, 3)
    assert row["deterministic_share"] == round(1 / 6, 3)
    assert row["acc"] == 1.0           # open excluded from scoring
    assert row["by_cohort"]["recurring"]["memory"] == 2
    assert row["model_on_everything_per_100"] == 100.0


def test_classify_cost_buckets():
    assert classify(Resolution("x", 1.0, "memory", "retrieval")) == "memory"
    assert classify(Resolution("x", 0.9, "retrieval", "retrieval")) == "retrieval"
    assert classify(Resolution(None, 0.4, "retrieval", "conflict")) == "conflict"
    assert classify(Resolution(None, 0.0, "none", "debate")) == "model"
    assert classify(Resolution("190", 1.0, "executor", "executor")) == "deterministic"
