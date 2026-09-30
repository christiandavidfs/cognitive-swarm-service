"""Director — routing policy over layers. No external imports.

Fase 3 heuristic/stats implementation (no model yet): learns from routing
OUTCOMES, not data. Each resolve records which layer solved which task type;
`order()` prefers layers with the best observed success rate per task type,
with Laplace smoothing so untried layers stay explorable. No signal anywhere
→ fixed config order (the `unknown` route: never force a ranking).

The learned director (small model on routing outcomes) will drop behind
`load_director()` with zero caller change. Training data is already being
collected by `record()` — that file IS the future dataset.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Optional

from service.contracts import TaskType


class Director:
    """Stats-based routing policy persisted to a small JSON file."""

    def __init__(self, path=None):
        self.path = Path(path) if path else Path("./data/routing_memory.json")
        # layer -> task_type value -> [successes, attempts]
        self.stats: Dict[str, Dict[str, list]] = {}
        self.load()

    # -- persistence ---------------------------------------------------
    def load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                if isinstance(data, dict):
                    self.stats = data
            except (ValueError, OSError):
                self.stats = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.stats, indent=2, ensure_ascii=False))
        tmp.replace(self.path)

    # -- learning ------------------------------------------------------
    def record(self, layer: str, task_type: TaskType, success: bool) -> None:
        tt = task_type.value if isinstance(task_type, TaskType) else str(task_type)
        bucket = self.stats.setdefault(layer, {}).setdefault(tt, [0, 0])
        bucket[1] += 1
        if success:
            bucket[0] += 1
        self.save()

    def rate(self, layer: str, task_type: TaskType) -> Optional[float]:
        tt = task_type.value if isinstance(task_type, TaskType) else str(task_type)
        bucket = (self.stats.get(layer) or {}).get(tt)
        if not bucket or bucket[1] == 0:
            return None
        # Laplace smoothing: untried layers stay near 0.5, never 0/1 on thin data.
        return round((bucket[0] + 1) / (bucket[1] + 2), 3)

    # -- policy --------------------------------------------------------
    def order(self, layers: List[str], task_type: TaskType) -> List[str]:
        """Order candidate layers best-first. Stable + signal-free → input order."""
        if len(layers) <= 1:
            return list(layers)
        scored = []
        for i, layer in enumerate(layers):
            r = self.rate(layer, task_type)
            scored.append((r if r is not None else 0.5, -i, layer))
        # All None → all 0.5 → tie broken by original index → input order preserved.
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        return [layer for _, _, layer in scored]

    def export_dataset(self) -> List[dict]:
        """Routing outcomes as training rows for the future learned director."""
        rows = []
        for layer, by_tt in self.stats.items():
            for tt, (ok, n) in by_tt.items():
                rows.append({"layer": layer, "task_type": tt,
                             "successes": ok, "attempts": n, "ts": time.time()})
        return rows
