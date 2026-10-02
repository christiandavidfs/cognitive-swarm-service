"""Results board tests — JSON + HTML over fixture logs. No network."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from service.results import BOARDS, board, render_html, summary


def _logs(tmp_path):
    (tmp_path / "longitudinal_log.jsonl").write_text(
        "\n".join(json.dumps({"date": f"2026-10-0{d}", "acc": 0.5 + d * 0.1})
                       for d in (1, 2)))
    (tmp_path / "market_log.jsonl").write_text(
        json.dumps({"date": "2026-10-01", "stale_rate": 0.0}))
    return tmp_path


def test_summary_boards_and_trend(tmp_path):
    d = _logs(tmp_path)
    s = summary(data_dir=d)
    assert set(s) == set(BOARDS)
    assert s["longitudinal"]["n"] == 2
    assert s["longitudinal"]["trend_acc"] == 0.1
    assert s["market"]["n"] == 1
    assert s["formations"]["n"] == 0


def test_board_unknown_and_html(tmp_path):
    d = _logs(tmp_path)
    b = board("longitudinal", data_dir=d)
    assert b["rows"][-1]["acc"] == 0.7
    html = render_html(data_dir=d)
    assert "swarm results" in html and "0.7" in html and "no rows yet" in html


def _w(rows, name, tmp_path):
    from service.results import BOARDS
    (tmp_path / BOARDS[name]).write_text(
        "\n".join(__import__("json").dumps(r) for r in rows))
    return tmp_path


def test_verdict_longitudinal_on_track_and_fail(tmp_path):
    from service.results import verdict
    d = _w([{"date": "a", "acc": 0.5, "contested_honest": 1},
            {"date": "b", "acc": 0.6, "contested_honest": 1}], "longitudinal", tmp_path)
    assert verdict("longitudinal", data_dir=d)["status"] == "on-track"
    d2 = _w([{"date": "a", "acc": 0.9, "contested_honest": 1},
             {"date": "b", "acc": 0.5, "contested_honest": 1}], "longitudinal", tmp_path)
    assert verdict("longitudinal", data_dir=d2)["status"] == "fail"


def test_verdict_market_and_rounds(tmp_path):
    from service.results import verdict
    d = _w([{"date": "a", "acc": 1.0, "stale_rate": 0.4},
            {"date": "b", "acc": 1.0, "stale_rate": 0.1}], "market", tmp_path)
    assert verdict("market", data_dir=d)["status"] == "on-track"
    d2 = _w([{"memory_share": 0.0}, {"memory_share": 0.36}], "rounds", tmp_path)
    assert verdict("rounds", data_dir=d2)["status"] == "on-track"


def test_verdict_formations_thin_then_fail(tmp_path):
    from service.results import verdict
    d = _w([{"settled_pred": 2, "pred_acc": 0.5, "base_rate": 0.5}], "formations", tmp_path)
    assert verdict("formations", data_dir=d)["status"] == "thin-data"
    d2 = _w([{"settled_pred": 20, "pred_acc": 0.5, "base_rate": 0.55}], "formations", tmp_path)
    assert verdict("formations", data_dir=d2)["status"] == "fail"
