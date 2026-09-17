"""Connectors package — import registry for convenience."""
from .registry import build_retrievers, available_connectors, describe_registry
from .base import Connector, SourceClaim, TaskType

__all__ = ["build_retrievers", "available_connectors", "describe_registry", "Connector", "SourceClaim", "TaskType"]
