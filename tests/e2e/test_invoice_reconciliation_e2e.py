from __future__ import annotations

import pytest

from core.engine import AgentEngine
from core.planner import Planner
from core.state import Goal, ToolResult, ToolResultStatus
from tools.base import BaseTool
from tools.registry import ToolRegistry


class OfflineLLM:
    async def complete_json(self, **kwargs):
        raise RuntimeError("offline")


class SuccessTool(BaseTool):
    description = "test implementation"

    def __init__(self, name): self.name = name

    async def _run(self, **kwargs):
        return ToolResult(tool_name=self.name, status=ToolResultStatus.SUCCESS, data={"ok": True})


@pytest.mark.asyncio
async def test_offline_invoice_workflow_completes():
    tools = ToolRegistry()
    for name in ("list_files", "read_file", "calculate"):
        tools.register(SuccessTool(name))
    trace = await AgentEngine(planner=Planner(llm=OfflineLLM()), tool_registry=tools).run(Goal(raw_text="Process incoming invoices"))
    assert trace.verification and trace.verification.passed
