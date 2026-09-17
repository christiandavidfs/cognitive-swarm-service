"""Postgres retriever — generic structured DB as truth source.

Registered name: `postgres` (enabled:false by default). Same pattern as Databricks:
one row → one SourceClaim, high reliability, query template controlled by service.yaml.

Config:
  postgres:
    enabled: false
    reliability: 1.0
    dsn: ${POSTGRES_DSN}  # postgresql://user:pass@host/db
    query: "SELECT answer, source, reliability FROM knowledge WHERE question ILIKE '%%{question}%%' LIMIT 1"
Uses psycopg if available; otherwise falls back to no-op (service stays up).
"""
from __future__ import annotations

import os
import time
import logging
from typing import List, Optional, Sequence, Dict

from cognitive_swarm.orchestration.corroboration import SourceClaim
from cognitive_swarm.orchestration.prompt_optimizer import TaskType
from .base import Connector

logger = logging.getLogger(__name__)


class PostgresRetriever(Connector):
    name = "postgres"
    categories: Optional[Sequence[TaskType]] = [TaskType.REASONING, TaskType.UNKNOWN]

    def __init__(
        self,
        dsn: Optional[str] = None,
        reliability: float = 1.0,
        query: Optional[str] = None,
        query_template: Optional[str] = None,
        timeout_s: int = 5,
        cache_ttl_s: int = 60,
    ):
        self.dsn = dsn or os.getenv("POSTGRES_DSN") or ""
        self.reliability = float(reliability)
        self.query = query or query_template
        self.timeout_s = int(timeout_s)
        self.cache_ttl_s = int(cache_ttl_s)
        self._cache: Dict[str, tuple] = {}
        self._available = None
        try:
            import psycopg  # psycopg 3
            self._available = True
        except ImportError:
            try:
                import psycopg2
                self._available = True
            except ImportError:
                self._available = False
                logger.debug("psycopg not installed — Postgres retriever will no-op until installed")

    def get_claims(self, question: str) -> List[SourceClaim]:
        if not self.dsn or not self.query or not self._available:
            return []
        norm = question.strip().lower()
        cached = self._cache.get(norm)
        if cached and cached[0] > time.time():
            return cached[1]
        claims = self._query(question)
        ttl = self.cache_ttl_s if claims else 30
        self._cache[norm] = (time.time() + ttl, claims)
        return claims

    def _query(self, question: str) -> List[SourceClaim]:
        safe_q = question.replace("'", "''")[:500]
        sql = self.query.replace("{question}", safe_q)
        try:
            # Try psycopg3 first, fallback to psycopg2
            try:
                import psycopg
                conn = psycopg.connect(self.dsn, connect_timeout=self.timeout_s)
            except ImportError:
                import psycopg2
                conn = psycopg2.connect(self.dsn, connect_timeout=self.timeout_s)
            with conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    row = cur.fetchone()
                    if not row:
                        return []
                    ans = str(row[0]).strip()
                    if not ans:
                        return []
                    src = str(row[1]).strip() if len(row) > 1 and row[1] else "postgres"
                    rel = float(row[2]) if len(row) > 2 and row[2] else self.reliability
                    return [SourceClaim(source=f"postgres:{src}", answer=ans, reliability=rel, independent=True, reason="Postgres")]
        except Exception as e:
            logger.warning("Postgres retriever failed: %s", e)
        return []
