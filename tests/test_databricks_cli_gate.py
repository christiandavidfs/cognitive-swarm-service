"""Fase 5 of plan/remediacion-hallazgos.md: Databricks CLI subprocess is opt-in.

With DATABRICKS_ALLOW_CLI_TOKEN unset, no `databricks` subprocess is ever
spawned — missing token/host fails soft to [] exactly like missing env.
No network: subprocess and requests are mocked.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

REPO = Path(__file__).parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

os.environ.setdefault("BACKENDS", "__none__")

from service.connectors.databricks import DatabricksSQLRetriever  # noqa: E402


def _retriever(monkeypatch):
    monkeypatch.delenv("DATABRICKS_TOKEN", raising=False)
    monkeypatch.delenv("DATABRICKS_ALLOW_CLI_TOKEN", raising=False)
    monkeypatch.setenv("DATABRICKS_HOST", "https://example.cloud.databricks.com")
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "wh-123")
    return DatabricksSQLRetriever(reliability=1.0)


def test_no_cli_subprocess_by_default(monkeypatch):
    r = _retriever(monkeypatch)
    assert r.token is None
    with patch("subprocess.check_output") as m:
        claims = r.get_claims("anything")
        m.assert_not_called()
    assert claims == []  # fail soft: missing token behaves like missing env


def test_cli_gate_blocks_refresh_and_host_sweep(monkeypatch):
    r = _retriever(monkeypatch)
    with patch("subprocess.check_output") as m:
        r._refresh_token_if_needed()
        m.assert_not_called()
    assert r.token is None


def test_optin_flag_enables_cli_fetch(monkeypatch):
    r = _retriever(monkeypatch)
    monkeypatch.setenv("DATABRICKS_ALLOW_CLI_TOKEN", "1")
    with patch("subprocess.check_output", return_value=b'{"access_token":"tok-1"}') as m:
        r._refresh_token_if_needed()
        m.assert_called_once()
    assert r.token == "tok-1"


def test_optin_flag_enables_host_sweep(monkeypatch):
    monkeypatch.setenv("DATABRICKS_ALLOW_CLI_TOKEN", "1")
    monkeypatch.delenv("DATABRICKS_TOKEN", raising=False)
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "wh-123")
    monkeypatch.delenv("DATABRICKS_HOST", raising=False)
    r = DatabricksSQLRetriever(reliability=1.0)
    profiles = b'[{"name":"personal","host":"https://cli.example.cloud.databricks.com/","valid":true}]'
    with patch("subprocess.check_output", return_value=profiles) as m:
        r.get_claims("anything")
        assert m.call_count >= 1
    assert r.host == "https://cli.example.cloud.databricks.com"


def test_get_claims_no_network_without_query_template(monkeypatch):
    """Sanity: a misconfigured template also fails soft with zero HTTP calls."""
    r = _retriever(monkeypatch)
    r.query_template = None
    with patch("requests.post") as m:
        assert r.get_claims("anything") == []
        m.assert_not_called()