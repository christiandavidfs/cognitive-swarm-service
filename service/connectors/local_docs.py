"""LocalDocs connector — thin wrapper over core LocalDocsRetriever, config-driven."""
from pathlib import Path
from typing import Optional, Sequence

from cognitive_swarm.orchestration.retrievers import LocalDocsRetriever
from cognitive_swarm.orchestration.prompt_optimizer import TaskType


class LocalDocsConnector(LocalDocsRetriever):
    """Registered name: `local_docs`. Enabled by default in service.yaml."""

    def __init__(
        self,
        source_dir: str = "../cognitive-swarm/retrieval_corpus",
        name: str = "local-docs",
        chunk_size: int = 3,
        match_threshold: float = 0.20,
        reliability: float = 0.8,
        categories: Optional[Sequence[TaskType]] = None,
    ):
        # Resolve relative to service root if needed
        p = Path(source_dir)
        if not p.is_absolute():
            # try relative to repo root then to cwd
            candidate = Path(__file__).parent.parent.parent / source_dir
            if candidate.exists():
                p = candidate
        if categories is None:
            categories = [TaskType.REASONING, TaskType.UNKNOWN]
        super().__init__(source_dir=p, name=name, chunk_size=chunk_size, match_threshold=match_threshold, reliability=reliability, categories=categories)
