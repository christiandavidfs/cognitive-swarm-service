"""Connector base — re-exports service-owned contracts.

Every connector lives in `service/connectors/<name>.py` and subclasses
`Connector`. Nothing in this package imports outside the service repo.
"""
from service.contracts import Connector, Resolution, SourceClaim, TaskType

__all__ = ["Connector", "Resolution", "SourceClaim", "TaskType"]
