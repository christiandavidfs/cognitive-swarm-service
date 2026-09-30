"""Backward-compat alias: ProcedureStore now lives in service.memory.store.

Standalone — no external imports. Existing ``from service.memory.procedure_store
import ProcedureStore`` statements keep working.
"""
from .store import STOPWORDS, ProcedureStore, _procedure_sig, _significant, _tokens

__all__ = ["STOPWORDS", "ProcedureStore", "_procedure_sig", "_significant", "_tokens"]
