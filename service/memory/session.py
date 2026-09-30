"""Short-term memory: per-session working context. No external imports.

STM holds the current episode: recent states, decisions just taken and their
immediate outcomes. It dies with the session. Its jobs: avoid repeating the
mistake from 3 ticks ago, and give judges recent context without re-asking.

Promotion to LTM happens via :func:`consolidate` — async, off the hot path,
conditioned on verified outcomes. Nothing enters LTM without a result signal.
"""
from __future__ import annotations

import collections
import threading
import time
import uuid
from typing import Deque, Dict, List, Optional


class Session:
    """One episode: ordered ring buffer of (state, decision, outcome) steps."""

    def __init__(self, session_id: str, capacity: int = 50):
        self.id = session_id
        self.capacity = int(capacity)
        self.created_at = time.time()
        self.steps: Deque[dict] = collections.deque(maxlen=self.capacity)

    def record(self, question: str, answer: Optional[str], source: str = "",
               trace: Optional[str] = None, outcome: Optional[bool] = None,
               meta: Optional[dict] = None) -> dict:
        step = {
            "question": question,
            "answer": answer,
            "source": source,
            "trace": trace,
            "outcome": outcome,  # True/False once known, None while pending
            "ts": time.time(),
            "meta": meta or {},
        }
        self.steps.append(step)
        return step

    def set_outcome(self, index: int, success: bool) -> None:
        steps = list(self.steps)
        if 0 <= index < len(steps):
            steps[index]["outcome"] = bool(success)
            self.steps = collections.deque(steps, maxlen=self.capacity)

    def recent(self, n: int = 10) -> List[dict]:
        return list(self.steps)[-n:]

    def __len__(self) -> int:
        return len(self.steps)


class SessionStore:
    """Registry of live sessions (in-process; use sticky routing if scaled)."""

    def __init__(self, capacity: int = 50):
        self.capacity = capacity
        self._sessions: Dict[str, Session] = {}
        self._lock = threading.Lock()

    def create(self) -> Session:
        sid = uuid.uuid4().hex[:12]
        with self._lock:
            sess = Session(sid, capacity=self.capacity)
            self._sessions[sid] = sess
        return sess

    def get(self, session_id: str) -> Optional[Session]:
        with self._lock:
            return self._sessions.get(session_id)

    def drop(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def consolidate(self, session_id: str, store, min_outcome: bool = True) -> int:
        """Promote verified session steps to LTM. Returns steps archived.

        Only steps with a known outcome enter LTM — and only successes, unless
        the caller explicitly passes min_outcome=False (e.g. to archive
        instructive failures as `verified=False`). Each promotion also feeds
        the LTM learning counters via `record_outcome`, so rates reflect
        real episodes, not just archival.
        """
        sess = self.get(session_id)
        if sess is None or store is None:
            return 0
        archived = 0
        for step in sess.recent(len(sess)):
            outcome = step.get("outcome")
            if outcome is None:
                continue  # no signal → never archive
            if min_outcome and not outcome:
                # Failure with signal still teaches: count it, don't enshrine it.
                try:
                    store.record_outcome(step["question"], False)
                except Exception:
                    pass
                continue
            try:
                store.remember(
                    step["question"], step.get("answer") or "",
                    source=step.get("source") or "session",
                    tier="session", confidence=0.7,
                    trace=step.get("trace"), verified=bool(outcome),
                )
                store.record_outcome(step["question"], bool(outcome))
                archived += 1
            except Exception:
                continue
        return archived
