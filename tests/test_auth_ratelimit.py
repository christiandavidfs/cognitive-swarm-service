"""Auth fail-closed and rate-limit identity. No network, no YAML required.

Phase 0/1 of plan/remediacion-hallazgos.md. Pure helpers are the contract;
TestClient checks the middleware still applies them.
"""
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO = Path(__file__).parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

os.environ.setdefault("BACKENDS", "__none__")

import service.app as appmod  # noqa: E402
from service.app import app, auth_decision, bucket_key, expand_api_keys  # noqa: E402

client = TestClient(app)

# Historical identifiers that must not return to public surfaces.
# This file is the allowed exception: it searches for them, it does not publish them as config.
_FORBIDDEN_DATABRICKS = (
    "dbc-118c13a0-9998.cloud.databricks.com",
    "2b2636d0ca412cdb",
)
_FORBIDDEN_PATHS = (
    "/Users/kaizen/repos",
    "/home/kaizen/repos",
)


@pytest.fixture(autouse=True)
def _isolated_buckets():
    appmod._rate_buckets.clear()
    yield
    appmod._rate_buckets.clear()


def test_expand_drops_unexpanded_placeholder(monkeypatch):
    monkeypatch.delenv("SERVICE_API_KEY", raising=False)
    assert expand_api_keys(["${SERVICE_API_KEY}"]) == set()


def test_expand_reads_env_and_splits_comma(monkeypatch):
    monkeypatch.setenv("SERVICE_API_KEY", "alpha,beta")
    assert expand_api_keys(["${SERVICE_API_KEY}"]) == {"alpha", "beta"}


def test_expand_keeps_literal_key():
    assert expand_api_keys(["literal-key"]) == {"literal-key"}


def test_auth_decision_empty_keys_no_header():
    assert auth_decision(True, set(), "", False) == 401


def test_auth_decision_empty_keys_any_header():
    assert auth_decision(True, set(), "anything", False) == 401


def test_auth_decision_correct_key():
    assert auth_decision(True, {"k"}, "k", False) == 200


def test_auth_decision_wrong_key():
    assert auth_decision(True, {"k"}, "other", False) == 401


def test_auth_decision_disabled_ignores_keys():
    assert auth_decision(False, set(), "", False) == 200


def test_auth_decision_exempt_path():
    assert auth_decision(True, set(), "", True) == 200


def test_bucket_key_prefers_provided_over_missing_client():
    assert bucket_key("k", None) == "k"


def test_bucket_key_anon_when_both_missing():
    assert bucket_key("", None) == "anon"


def test_bucket_key_falls_back_to_host():
    assert bucket_key("", "10.0.0.1") == "10.0.0.1"


def _enabled(keys):
    return {
        "enabled": True,
        "keys": set(keys),
        "limit": 60,
        "exempt": {"/health", "/docs", "/openapi.json", "/redoc"},
    }


def test_resolve_rejects_when_enabled_and_keys_empty(monkeypatch):
    monkeypatch.setattr(appmod, "_auth_config", lambda: _enabled(set()))
    bare = client.post("/resolve", json={"question": "x"})
    sent = client.post("/resolve", json={"question": "x"}, headers={"X-API-Key": "anything"})
    assert bare.status_code == 401
    assert sent.status_code == 401


def test_health_exempt_when_auth_enabled(monkeypatch):
    monkeypatch.setattr(appmod, "_auth_config", lambda: _enabled(set()))
    assert client.get("/health").status_code == 200


def test_resolve_accepts_configured_key(monkeypatch):
    monkeypatch.setattr(appmod, "_auth_config", lambda: _enabled({"secret"}))
    ok = client.post("/resolve", json={"question": "x"}, headers={"X-API-Key": "secret"})
    bad = client.post("/resolve", json={"question": "x"}, headers={"X-API-Key": "other"})
    assert ok.status_code == 200
    assert bad.status_code == 401


def test_distinct_keys_do_not_share_a_bucket():
    assert bucket_key("alpha", None) != bucket_key("beta", None)


def test_readme_and_config_omit_historical_databricks_ids():
    surfaces = [REPO / "README.md", * (REPO / "config").rglob("*"), REPO / "AGENTS.md"]
    surfaces.extend(p for p in (REPO / "docs").rglob("*") if p.is_file())
    blobs = []
    for path in surfaces:
        if path.is_file():
            blobs.append(path.read_text(encoding="utf-8", errors="replace"))
    text = "\n".join(blobs)
    for needle in _FORBIDDEN_DATABRICKS + _FORBIDDEN_PATHS:
        assert needle not in text, needle


def test_license_file_exists_and_readme_links_it():
    license_text = (REPO / "LICENSE").read_text(encoding="utf-8")
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "UNLICENSED" in license_text
    assert "LICENSE" in readme
