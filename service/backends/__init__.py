"""Backend loading — config-driven, all backends optional.

``config/service.yaml`` declares ``backends: [...]`` (or ``BACKENDS`` env,
comma-separated). Unknown or uninstallable backends are skipped with a
warning; the service always starts — memory + retrieval serve regardless.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List

from service.contracts import ResolverBackend

logger = logging.getLogger(__name__)

SERVICE_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "service.yaml"


def _configured_names(config_path=None) -> List[str]:
    env = os.getenv("BACKENDS")
    if env:
        return [n.strip() for n in env.split(",") if n.strip()]
    try:
        import yaml
        cfg_path = Path(config_path) if config_path else SERVICE_CONFIG_PATH
        data = yaml.safe_load(cfg_path.read_text()) or {}
        backends = data.get("backends", ["cognitive_swarm"])
        return [str(n) for n in backends] if isinstance(backends, list) else ["cognitive_swarm"]
    except Exception:
        return ["cognitive_swarm"]


def load_backends(memory=None, names=None, config_path=None) -> List[ResolverBackend]:
    out: List[ResolverBackend] = []
    for name in names if names is not None else _configured_names(config_path):
        try:
            if name in ("cognitive_swarm", "cognitive-swarm"):
                from .cognitive_swarm import CognitiveSwarmBackend, available
                if not available():
                    logger.warning("Backend %r skipped: cognitive_swarm not installed", name)
                    continue
                out.append(CognitiveSwarmBackend(memory=memory))
            else:
                logger.warning("Backend %r skipped: unknown backend", name)
        except Exception as e:
            logger.warning("Backend %r failed to init: %s", name, e)
    return out
