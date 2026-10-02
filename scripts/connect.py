#!/usr/bin/env python3
"""Connector coach: guided onboarding for ANY connector (present or future).

Deterministic flow (credentials never pass through free text):
  1. list / show <name>      → required env + probe + current status
  2. connect <name>          → prompts for each missing value (getpass for secrets),
                               sets process env, runs a live probe resolve, reports green/red
  3. Future connectors work automatically: unknown names fall back to showing
     their `config/service.yaml` block fields as required values.

  python scripts/connect.py list
  python scripts/connect.py show confluence
  python scripts/connect.py connect confluence
  python scripts/connect.py connect zephyr   # spec-ready even before the connector lands
"""
import getpass
import os
import sys
from pathlib import Path as _P

_REPO = _P(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# name -> {env: [...], secret_env: [...], probe: str, hint: str}
SPECS = {
    "confluence": {
        "env": ["CONFLUENCE_BASE_URL"],
        "secret_env": ["CONFLUENCE_API_TOKEN"],
        "probe": "test warm reindex",
        "hint": "Atlassian Cloud: https://<site>.atlassian.net + API token from id.atlassian.com",
    },
    "zephyr": {
        "env": ["ZEPHYR_BASE_URL"],
        "secret_env": ["ZEPHYR_API_TOKEN"],
        "probe": "test warm reindex",
        "hint": "Zephyr Scale/Squad Cloud URL + API token (connectors: zephyr lands as its own file)",
    },
    "databricks_sql": {
        "env": ["DATABRICKS_HOST", "DATABRICKS_WAREHOUSE_ID"],
        "secret_env": ["DATABRICKS_TOKEN"],
        "probe": "test warm reindex",
        "hint": "databricks auth login, or host + warehouse id + token",
    },
    "postgres": {
        "env": ["POSTGRES_DSN"],
        "secret_env": [],
        "probe": "test warm reindex",
        "hint": "postgresql://user:pass@host/db",
    },
    "search": {
        "env": ["SEARCH_BASE_URL"],
        "secret_env": [],
        "probe": "test warm reindex",
        "hint": "any SearXNG instance base URL (self-hosted = free, no key)",
    },
    "pokeapi": {"env": [], "secret_env": [], "probe": "What type is pikachu?",
                "hint": "no credentials needed"},
    "wikidata": {"env": [], "secret_env": [], "probe": "What is the capital of France?",
                 "hint": "no credentials needed"},
}


def spec_for(name: str) -> dict:
    if name in SPECS:
        return SPECS[name]
    # Generic fallback: read the yaml block fields as required values.
    try:
        import yaml
        data = yaml.safe_load((_REPO / "config" / "service.yaml").read_text()) or {}
        block = (data.get("connectors", {}) or {}).get(name, {})
        envs = [v.strip("${}") for v in block.values()
                if isinstance(v, str) and v.startswith("${")]
        return {"env": envs, "secret_env": [], "probe": "test warm reindex",
                "hint": f"from config/service.yaml connectors.{name} (generic fallback)"}
    except Exception:
        return {"env": [], "secret_env": [], "probe": "test warm reindex", "hint": ""}


def cmd_list():
    from service.connectors.registry import describe_registry
    for c in describe_registry():
        print(f"{c['name']:16} enabled={c['enabled']!s:5} reliability={c['reliability']}")


def cmd_show(name: str):
    s = spec_for(name)
    print(f"connector: {name}")
    print(f"  hint: {s['hint']}")
    for v in s["env"]:
        print(f"  env    {v}={'SET' if os.getenv(v) else 'MISSING'}")
    for v in s["secret_env"]:
        print(f"  secret {v}={'SET' if os.getenv(v) else 'MISSING'}")


def cmd_connect(name: str):
    s = spec_for(name)
    for v in s["env"]:
        if not os.getenv(v):
            os.environ[v] = input(f"{v}: ").strip()
    for v in s["secret_env"]:
        if not os.getenv(v):
            os.environ[v] = getpass.getpass(f"{v} (hidden): ").strip()
    # Live probe: build ONLY this connector and resolve something through the router.
    from service.connectors.registry import build_retrievers
    from service.corroboration import Corroborator
    from service.memory.store import ProcedureStore
    from service.router import Router
    import tempfile
    mem = ProcedureStore(path=_P(tempfile.mkdtemp()) / "coach.json")
    rs = build_retrievers(enabled_only=False, include=[name])
    if not rs:
        print(f"RED: connector {name!r} unknown or failed to build")
        return False
    r = Router(memory=mem, corroborator=Corroborator(), retrievers=rs, backends=[])
    q = s["probe"] if s["probe"] != "test warm reindex" else "What is the capital of France?"
    res = r.resolve(q)
    ok = res.answer is not None or res.status in ("retrieval", "memory")
    print(f"{'GREEN' if ok else 'RED'}: probe {q!r} -> answer={res.answer!r} "
          f"status={res.status} tier={res.tier}")
    if ok:
        print(f"export {' '.join(f'{v}=...' for v in s['env'] + s['secret_env'])}  # persist to use again")
    return ok


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("list", "show", "connect"):
        print(__doc__)
        sys.exit(2)
    if sys.argv[1] == "list":
        cmd_list()
    elif len(sys.argv) < 3:
        print("need a connector name")
        sys.exit(2)
    elif sys.argv[1] == "show":
        cmd_show(sys.argv[2])
    else:
        ok = cmd_connect(sys.argv[2])
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
