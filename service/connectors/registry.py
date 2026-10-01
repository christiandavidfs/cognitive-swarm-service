"""Connector registry — modular, scalable, config-driven.

All connectors are discovered by name; `config/service.yaml` declares `connectors.<name>.enabled`
and per-connector options. The service builds retrievers via `build_retrievers()` at startup
(and per-request when `connectors` override is supplied).

Adding a new source:
  1. Create `service/connectors/my_source.py` with `class MySourceRetriever(Connector): ...`
  2. Register it in `_BUILTINS` below (one line).
  3. Add `my_source:` block in `config/service.yaml` (reliability, creds via env).
No change to the router.

Pattern is the same one used by the core `retrievers.py` gate: each retriever declares
`categories: Optional[Sequence[TaskType]]` and the router only queries it when
`retriever.applies_to(task_type)` is true — factual connectors never run on CODE/MATH.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import yaml


from .base import Connector, TaskType

SERVICE_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "service.yaml"

# Import built-ins lazily to avoid circular deps at module import time
def _load_builtins():
    from .wikidata import WikidataRetriever
    from .openalex import OpenAlexRetriever
    from .local_docs import LocalDocsConnector
    from .confluence import ConfluenceRetriever
    from .databricks import DatabricksSQLRetriever
    from .postgres import PostgresRetriever
    from .generic_http import GenericHTTPRetriever
    from .pokeapi import PokeAPIConnector

    return {
        "wikidata": WikidataRetriever,
        "openalex": OpenAlexRetriever,
        "semantic_scholar": OpenAlexRetriever,  # alias; config can set provider: semantic_scholar
        "local_docs": LocalDocsConnector,
        "confluence": ConfluenceRetriever,
        "databricks_sql": DatabricksSQLRetriever,
        "databricks": DatabricksSQLRetriever,
        "postgres": PostgresRetriever,
        "generic_http": GenericHTTPRetriever,
        "pokeapi": PokeAPIConnector,
    }

_BUILTINS: Optional[Dict[str, type]] = None

def available_connectors() -> List[str]:
    global _BUILTINS
    if _BUILTINS is None:
        _BUILTINS = _load_builtins()
    return sorted(_BUILTINS.keys())

def _read_config(path: Optional[Path] = None) -> dict:
    cfg_path = Path(path) if path else SERVICE_CONFIG_PATH
    if not cfg_path.exists():
        return {}
    try:
        data = yaml.safe_load(cfg_path.read_text()) or {}
        return data.get("connectors", {}) if isinstance(data, dict) else {}
    except Exception:
        return {}

def _expand_env(value):
    """Expand ${VAR} in strings via os.path.expandvars, recursively."""
    import os
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value

def build_retrievers(
    enabled_only: bool = True,
    include: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
    config_path: Optional[Path] = None,
) -> List[Connector]:
    """Instantiate retrievers per config, with optional include/exclude filter.

    - If `include` is set (per-request `connectors: [...]`), only those names are built
      even if they are `enabled:false` in config — caller explicitly asked for them.
    - `exclude` removes names from the selection.
    - Each retriever is constructed with its yaml block as kwargs (after env expansion).
    """
    global _BUILTINS
    if _BUILTINS is None:
        _BUILTINS = _load_builtins()

    raw_cfg = _read_config(config_path)
    cfg = {k: _expand_env(v) for k, v in raw_cfg.items()}

    # Determine which names to build
    if include is not None:
        names = [n for n in include if n in _BUILTINS]
    else:
        names = list(_BUILTINS.keys())
        if enabled_only:
            names = [n for n in names if cfg.get(n, {}).get("enabled", False)]

    if exclude:
        names = [n for n in names if n not in set(exclude)]

    retrievers: List[Connector] = []
    for name in names:
        cls = _BUILTINS[name]
        opts = cfg.get(name, {}) if isinstance(cfg.get(name), dict) else {}
        # Strip `enabled` — not a constructor arg
        opts = {k: v for k, v in opts.items() if k != "enabled"}
        try:
            # Special-case openalex provider switch
            if name in ("openalex", "semantic_scholar") and isinstance(opts, dict) and opts.get("provider") == "semantic_scholar":
                from .openalex import SemanticScholarRetriever
                retrievers.append(SemanticScholarRetriever(**{k: v for k, v in opts.items() if k != "provider"}))
            else:
                retrievers.append(cls(**opts))
        except Exception as e:
            # One broken connector must not kill the service — log and skip.
            import logging
            logging.getLogger(__name__).warning("Connector %s failed to init: %s", name, e)
            continue
    return retrievers

def describe_registry(config_path: Optional[Path] = None) -> List[dict]:
    """Return metadata for all known connectors (for GET /connectors)."""
    global _BUILTINS
    if _BUILTINS is None:
        _BUILTINS = _load_builtins()
    raw_cfg = _read_config(config_path)
    out = []
    for name, cls in sorted(_BUILTINS.items()):
        cfg = raw_cfg.get(name, {}) if isinstance(raw_cfg.get(name), dict) else {}
        out.append({
            "name": name,
            "class": cls.__name__,
            "module": cls.__module__,
            "enabled": bool(cfg.get("enabled", False)),
            "categories": getattr(cls, "categories", None) and [c.value if hasattr(c, "value") else str(c) for c in cls.categories] or None,
            "reliability": cfg.get("reliability"),
        })
    return out
