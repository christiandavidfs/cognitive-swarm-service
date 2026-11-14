"""Gate L-1 tests: battery integrity and verdict arithmetic (no network).

The gate is pre-registered: these tests pin the answer key and the pass/fail
arithmetic so neither can drift after results are seen.
"""
import datetime
import json
import tempfile
from pathlib import Path

from scripts.learning_gate import (FAIL_REL_DROP, FAMILIES, MIN_ACC, PASS_REL_DROP,
                                   TRUTH, build_battery, count_leakage,
                                   parse_answer, verdict)

REPO = Path(__file__).parent.parent
BATTERY = REPO / "evals" / "learning_gate_battery.json"


def test_battery_shape():
    items = build_battery()
    assert len(items) == 30
    assert set(FAMILIES) == {i["family"] for i in items}
    for fam in FAMILIES:
        sub = [i for i in items if i["family"] == fam]
        assert len(sub) == 6
        assert sum(1 for i in sub if i["split"] == "train") == 3
        assert sum(1 for i in sub if i["split"] == "heldout") == 3


def test_answer_key_recomputes_from_operands():
    for item in build_battery():
        expected = TRUTH[item["family"]](*item["operands"])
        assert abs(float(item["expected"]) - float(expected)) < 1e-9, item


def test_committed_battery_matches_the_generator():
    committed = json.loads(BATTERY.read_text())
    assert committed == build_battery()


def test_no_duplicate_questions():
    qs = [i["question"] for i in build_battery()]
    assert len(qs) == len(set(qs))


def test_parse_answer_handles_units_and_commas():
    assert parse_answer("3000") == 3000
    assert parse_answer("7,5") == 7.5
    assert parse_answer("about 3000 seconds") == 3000
    assert parse_answer(None) is None
    assert parse_answer("no idea") is None


def test_leakage_counts_only_servable_heldout():
    from service.memory.store import ProcedureStore
    store = ProcedureStore(path=str(Path(tempfile.mkdtemp()) / "m.json"))
    items = build_battery()
    held = [i for i in items if i["split"] == "heldout"][:2]
    train = [i for i in items if i["split"] == "train"][:1]
    for i in held + train:
        store.remember(i["question"], str(i["expected"]))
    assert count_leakage(items, store) == 2
    store.quarantine(held[0]["question"], reason="test")
    assert count_leakage(items, store) == 1


def _row(esc, acc, code=0.5, leakage=0):
    return {"escalated_share": esc, "acc": acc, "code_share": code,
            "leakage": leakage}


def test_verdict_pass_needs_all_three():
    assert verdict(_row(1.0, 0.0), _row(0.6, 0.8)) == "PASS"      # -40%, acc 0.8
    assert verdict(_row(1.0, 0.0), _row(0.6, 0.65)) == "INCONCLUSIVE"  # acc < 0.70
    assert verdict(_row(1.0, 0.0), _row(0.6, 0.8, code=0.1)) == "INCONCLUSIVE"
    assert verdict(_row(1.0, 0.0), _row(0.6, 0.8, leakage=1)) == "FAIL"


def test_verdict_fail_and_inconclusive():
    assert verdict(_row(1.0, 0.0), _row(0.85, 0.9)) == "FAIL"     # -15% < 20%
    assert verdict(_row(1.0, 0.0), _row(0.75, 0.9)) == "INCONCLUSIVE"
    assert verdict(_row(1.0, 0.0), _row(0.6, 0.4)) == "FAIL"      # acc floor
    assert verdict(_row(0.0, 0.0), _row(0.0, 0.9)) == "VOID"


def test_thresholds_are_frozen_values():
    # If someone edits these, the gate stops being pre-registered.
    assert (PASS_REL_DROP, FAIL_REL_DROP, MIN_ACC) == (0.30, 0.20, 0.70)


def test_no_verdict_before_the_deadline():
    from scripts.learning_gate import GATE_CYCLES, gate_status
    assert GATE_CYCLES == 4
    assert gate_status(_row(1.0, 0.0), _row(1.0, 0.0), 0) == "IN PROGRESS"
    assert gate_status(_row(1.0, 0.0), _row(1.0, 0.0), 3) == "IN PROGRESS"
    assert gate_status(_row(1.0, 0.0), _row(1.0, 0.0), 4) == "FAIL"
    assert gate_status(_row(1.0, 0.0), _row(0.6, 0.8), 4) == "PASS"
