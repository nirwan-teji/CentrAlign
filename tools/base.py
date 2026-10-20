"""
tools/base.py — Abstract BaseTool with Pydantic-validated I/O and timeout support.
"""
from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Dict

from core.state import ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)


class BaseTool(ABC):
    """
    Every tool in the registry extends this class.
    Subclasses implement `_run(**kwargs) -> ToolResult`.
    `execute()` wraps the call with timeout, logging, and error capture.
    """

    name: ClassVar[str]
    description: ClassVar[str]
    timeout_seconds: ClassVar[int] = 30

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Public interface — validates, runs with timeout, catches exceptions."""
        logger.info("[Tool:%s] Executing with args: %s", self.name, kwargs)
        t0 = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                self._run(**kwargs),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            elapsed = (time.perf_counter() - t0) * 1000
            logger.error("[Tool:%s] Timed out after %.0f ms", self.name, elapsed)
            result = ToolResult(
                tool_name=self.name,
                status=ToolResultStatus.ERROR,
                error_message=f"Tool timed out after {self.timeout_seconds}s",
            )
        except Exception as exc:  # noqa: BLE001
            elapsed = (time.perf_counter() - t0) * 1000
            logger.exception("[Tool:%s] Unexpected error: %s", self.name, exc)
            result = ToolResult(
                tool_name=self.name,
                status=ToolResultStatus.ERROR,
                error_message=str(exc),
            )

        result.duration_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "[Tool:%s] %s in %.0f ms",
            self.name,
            result.status.value,
            result.duration_ms,
        )
        return result

    @abstractmethod
    async def _run(self, **kwargs: Any) -> ToolResult:
        """Subclasses implement the actual work here."""
        ...

    def schema(self) -> Dict[str, Any]:
        """Return a human/LLM-readable description of this tool."""
        return {
            "name": self.name,
            "description": self.description,
            "timeout_seconds": self.timeout_seconds,
        }
