"""Connector base — re-exports core Retriever ABC so every connector implements the same contract.

Every connector lives in `service/connectors/<name>.py` and exposes a subclass of `Connector`
(which is `cognitive_swarm.orchestration.retrievers.Retriever`). The service registry
discovers them by name; `config/service.yaml` decides which are enabled by default,
but callers can choose per-request via `POST /resolve {connectors: [...]}`.

Reliability scoring follows docs/ARCHITECTURE.md §4: Authority / Proximity / Recency / Independence
feeding Corroborator (reliability + independence bonus). Keep it media-agnostic: claims may carry
a `media` URI/path for future multimodal without routing changes.
"""
from cognitive_swarm.orchestration.retrievers import Retriever  # re-export
from cognitive_swarm.orchestration.corroboration import SourceClaim  # re-export
from cognitive_swarm.orchestration.prompt_optimizer import TaskType  # re-export

# Alias used across the service to make intent explicit.
Connector = Retriever

__all__ = ["Retriever", "Connector", "SourceClaim", "TaskType"]
