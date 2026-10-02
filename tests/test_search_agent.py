"""Search connector + sandbox tests — mocked network. Branch-only (not main)."""
import sys
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_search_disabled_without_base():
    from service.connectors.search import SearchConnector
    c = SearchConnector(base_url="")
    assert c.get_claims("anything?") == []


def test_search_hits_become_candidate_claims():
    from service.connectors.search import SearchConnector

    class _R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"results": [
                {"title": "Nobel list", "content": "Israel has 13 laureates",
                 "url": "https://example.test/nobel"}]}

    c = SearchConnector(base_url="http://x", reliability=0.6)
    with patch("service.connectors.search.requests.get", return_value=_R()):
        claims = c.get_claims("How many Nobel laureates does Israel have?")
    assert len(claims) == 1
    assert claims[0].reliability == 0.6 and claims[0].independent is False
    assert "13 laureates" in claims[0].answer


def test_search_registered():
    from service.connectors.registry import available_connectors
    assert "search" in available_connectors()


def test_sandbox_blocks_and_gates():
    from service.sandbox import run
    assert run("rm -rf /")["ok"] is False
    assert run("echo hi > f")["code"] == -2  # needs approval
    r = run("echo hi")
    assert r["ok"] and "hi" in r["out"]


def test_sandbox_scrubs_secrets(monkeypatch):
    import os
    from service.sandbox import _scrubbed_env
    monkeypatch.setenv("MY_API_KEY", "shh")
    env = _scrubbed_env()
    assert "MY_API_KEY" not in env
