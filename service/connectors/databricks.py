"""Databricks SQL retriever — modular, scalable.

Registered names: `databricks_sql` / `databricks` (enabled:false by default).
Wires to Databricks SQL Warehouse via Statement Execution API (no JDBC), so the
service stays stateless and doesn't need a Spark cluster.

Config in service.yaml:
  databricks_sql:
    enabled: false
    reliability: 1.0
    warehouse_id: ${DATABRICKS_WAREHOUSE_ID}
    catalog: my_catalog
    schema: my_schema
    query_template: "SELECT answer, source, reliability FROM my_table WHERE question ILIKE '%{question}%' LIMIT 1"
Env: DATABRICKS_HOST (https://...cloud.databricks.com), DATABRICKS_TOKEN.

Each row → one SourceClaim. For POC this is a thin passthrough; the
truth hierarchy treats it as a high-reliability structured source (DB).
"""
from __future__ import annotations

import os
import time
import logging
from typing import List, Optional, Sequence, Dict

import requests

from cognitive_swarm.orchestration.corroboration import SourceClaim
from cognitive_swarm.orchestration.prompt_optimizer import TaskType
from .base import Connector

logger = logging.getLogger(__name__)


class DatabricksSQLRetriever(Connector):
    name = "databricks_sql"
    categories: Optional[Sequence[TaskType]] = [TaskType.REASONING, TaskType.UNKNOWN]

    def __init__(
        self,
        warehouse_id: Optional[str] = None,
        reliability: float = 1.0,
        timeout_s: int = 10,
        cache_ttl_s: int = 60,
        host: Optional[str] = None,
        token: Optional[str] = None,
        catalog: Optional[str] = None,
        schema: Optional[str] = None,
        query_template: Optional[str] = None,
    ):
        self.warehouse_id = warehouse_id or os.getenv("DATABRICKS_WAREHOUSE_ID")
        self.reliability = float(reliability)
        self.timeout_s = int(timeout_s)
        self.cache_ttl_s = int(cache_ttl_s)
        self.host = (host or os.getenv("DATABRICKS_HOST") or "").rstrip("/")
        self.token = token or os.getenv("DATABRICKS_TOKEN")
        self.catalog = catalog
        self.schema = schema
        self.query_template = query_template
        self._cache: Dict[str, tuple] = {}

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def get_claims(self, question: str) -> List[SourceClaim]:
        if not self.host or not self.token or not self.warehouse_id:
            logger.debug("Databricks not configured (host/token/warehouse_id missing)")
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
        if not self.query_template:
            logger.debug("Databricks query_template not set — skipping")
            return []
        # Very small templating — caller controls SQL; we just inject escaped question
        import re as _re
        safe_q = question.replace("'", "''")[:500]
        sql = self.query_template.replace("{question}", safe_q)
        # Optional catalog/schema prefix if template uses bare table
        body = {"warehouse_id": self.warehouse_id, "statement": sql, "wait_timeout": f"{self.timeout_s}s"}
        if self.catalog:
            body["catalog"] = self.catalog
        if self.schema:
            body["schema"] = self.schema
        url = f"{self.host}/api/2.0/sql/statements"
        try:
            r = requests.post(url, json=body, headers=self._headers(), timeout=self.timeout_s + 2)
            r.raise_for_status()
            data = r.json()
            # Statement API returns result.data_array or manifest; handle both
            arr = None
            if "result" in data and "data_array" in data["result"]:
                arr = data["result"]["data_array"]
            elif "data_array" in data:
                arr = data["data_array"]
            if not arr:
                return []
            # Expect columns: answer, source, reliability (best-effort)
            for row in arr:
                ans = str(row[0]).strip() if row else ""
                if not ans:
                    continue
                src = str(row[1]).strip() if len(row) > 1 and row[1] else "databricks"
                rel = float(row[2]) if len(row) > 2 and row[2] else self.reliability
                return [SourceClaim(source=f"databricks:{src}", answer=ans, reliability=rel, independent=True, reason="Databricks SQL")]
            return []
        except Exception as e:
            logger.warning("Databricks SQL failed: %s", e)
            return []
