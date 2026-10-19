import pytest

from service.federation import (PatternBlock, Library, export_library,
                                import_library, safe_formula_eval)


def _block(fname="test", formula="{x} * {x}", keys=("x",)):
    return PatternBlock({"pattern": fname,
                         "detect": r"\d+\s*(?:units|apples?|workers?)",
                         "keys": list(keys), "formula": formula,
                         "trace": "t {x}", "procedure_sig": f"sig:{fname}"})


def test_safe_formula_eval_accepts_math_rejects_injection():
    assert safe_formula_eval("2 + 3*4") == 14
    assert safe_formula_eval("(8 - 2) / 3") == 2
    assert safe_formula_eval("__import__('os')") is None
    assert safe_formula_eval("1; drop table") is None
    assert safe_formula_eval("[x for x in []]") is None


def test_pattern_block_solves_and_maps_positional_keys():
    b = PatternBlock({"pattern": "lunchbreak",
                      "detect": r"\d+\s+workers?\s+start\s+at\s+\d+\s*h",
                      "keys": ["n", "t"], "formula": "8 + 16 / {n}",
                      "procedure_sig": "s1"})
    r = b.solve("17 workers start at 3 h. What time is the lunchbreak?")
    assert r and float(r["answer"]) == 8 + 16 / 17
    assert b.solve("no numbers here") is None


def test_library_version_and_malformed_entries_refused_loudly():
    with pytest.raises(ValueError, match="refusing library version"):
        import_library({"version": "fed-9", "entries": []})
    with pytest.raises(ValueError, match="malformed entry"):
        import_library({"version": "fed-1",
                        "entries": [{"pattern": "x", "formula": "{x}",  # uncompilable
                                     "keys": ["x"], "detect": r"(|unclosed"}]})


def test_export_has_no_question_or_answer_leak():
    b = _block()
    payload = export_library(pattern_blocks=[b])
    text = __import__("json").dumps(payload)
    assert "question" not in text and '"answer"' not in text
    # attest entries carry no executable formula
    attest = export_library(pattern_blocks=[], attest_entries=[
        {"tier": "math-primitives", "procedure_sig": "s2", "trace": "n*(n-1)/2",
         "sources": [{"reliability": 1.0}], "attempts": 2, "successes": 2}])
    assert "legacy:" in str(attest["entries"])  # carried as attestation only


def test_outcome_veto_revokes_failing_block():
    b = PatternBlock({"pattern": "p", "detect": r"\d+", "keys": ["x"],
                      "formula": "{x}", "procedure_sig": "s"})
    lib = Library([b])
    for _ in range(3):
        assert lib.solve("7 units") is not None
        lib.record("7 units", False)
    # 3 consecutive local failures -> revoked (attempts>=3, rate<=50%)
    assert b.revoked() and lib.solve("7 units") is None


def test_success_weighting_grows_and_bounds():
    b = _block()
    w0 = b.weight
    b.record(True)
    assert b.weight > w0
    for _ in range(20):
        b.record(True)
    assert b.weight <= b.base_reliability + 1e-9
