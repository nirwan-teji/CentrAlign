"""
memory/working_memory.py — In-run scratchpad for a single agent execution.

Tracks extracted facts, active invoice, discovered record IDs, and
a summarized action history for LLM context building.
"""
from __future__ import annotations

import logging
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MAX_HISTORY_ITEMS = 30  # prevent unbounded growth


class WorkingMemory:
    """Thread-safe in-memory scratchpad for one agent run."""

    def __init__(self) -> None:
        self._facts: Dict[str, Any] = {}
        self._history: Deque[Tuple[str, str, str]] = deque(maxlen=MAX_HISTORY_ITEMS)
        # (timestamp, tool_name, summary)

    # ── Facts ─────────────────────────────────────────────────────────────────

    def set(self, key: str, value: Any) -> None:
        """Store or overwrite a named fact."""
        self._facts[key] = value
        logger.debug("[Memory] SET %s = %r", key, value)

    def get(self, key: str, default: Any = None) -> Any:
        return self._facts.get(key, default)

    def update(self, facts: Dict[str, Any]) -> None:
        """Bulk-update facts from an observation dict."""
        for k, v in facts.items():
            self.set(k, v)

    def all_facts(self) -> Dict[str, Any]:
        return dict(self._facts)

    # ── Action history ────────────────────────────────────────────────────────

    def record_action(self, tool_name: str, summary: str) -> None:
        ts = datetime.utcnow().strftime("%H:%M:%S")
        self._history.append((ts, tool_name, summary))

    def history_summary(self, n: int = 10) -> str:
        """Return the last n actions as a plain-text string for LLM context."""
        recent = list(self._history)[-n:]
        if not recent:
            return "(no history yet)"
        lines = [f"[{ts}] {tool}: {summary}" for ts, tool, summary in recent]
        return "\n".join(lines)

    def full_history(self) -> List[Tuple[str, str, str]]:
        return list(self._history)

    # ── Reset ──────────────────────────────────────────────────────────────────

    def reset(self) -> None:
        self._facts.clear()
        self._history.clear()
        logger.debug("[Memory] Working memory reset")
