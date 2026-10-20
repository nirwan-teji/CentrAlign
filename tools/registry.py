"""
tools/registry.py — Central tool registry; resolves tool names to instances.
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

from tools.base import BaseTool
from core.state import ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Singleton registry that maps tool names → BaseTool instances.
    The agent calls `registry.execute(tool_name, **kwargs)` and never
    instantiates tools directly — keeping it easy to mock in tests.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            logger.warning("Tool %r already registered; overwriting.", tool.name)
        self._tools[tool.name] = tool
        logger.debug("Registered tool: %s", tool.name)

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    async def execute(self, tool_name: str, **kwargs) -> ToolResult:
        tool = self.get(tool_name)
        if tool is None:
            logger.error("Unknown tool: %s", tool_name)
            return ToolResult(
                tool_name=tool_name,
                status=ToolResultStatus.ERROR,
                error_message=f"Unknown tool: {tool_name!r}. "
                              f"Available: {list(self._tools.keys())}",
            )
        return await tool.execute(**kwargs)

    def list_tools(self) -> list[dict]:
        return [t.schema() for t in self._tools.values()]


# Module-level singleton — populated by tools/__init__.py
registry = ToolRegistry()
