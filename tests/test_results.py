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
