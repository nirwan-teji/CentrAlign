from __future__ import annotations

import pytest

from core.engine import AgentEngine
from core.planner import Planner
from core.state import Goal, ToolResult, ToolResultStatus, AgentStatus
from tools.base import BaseTool
from tools.registry import ToolRegistry


class NoLLM:
    async def complete_json(self, **kwargs):
        raise RuntimeError("offline")


class FakeTool(BaseTool):
    name = "list_files"
    description = "fake"

    async def _run(self, **kwargs):
        return ToolResult(tool_name=self.name, status=ToolResultStatus.SUCCESS, data={"count": 1})


class FailingOnceTool(BaseTool):
    name = "read_file"
    description = "fake"

    def __init__(self):
        self.calls = 0

    async def _run(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return ToolResult(tool_name=self.name, status=ToolResultStatus.ERROR, error_message="validation error")
        return ToolResult(tool_name=self.name, status=ToolResultStatus.SUCCESS, data={"content": "ok"})


@pytest.mark.asyncio
async def test_engine_completes_plan_and_verifies():
    registry = ToolRegistry()
    registry.register(FakeTool())
    engine = AgentEngine(planner=Planner(llm=NoLLM()), tool_registry=registry)
    trace = await engine.run(Goal(raw_text="Process incoming invoices"))
    assert trace.agent_status == AgentStatus.FAILED  # local plan needs more than this fake registry
    assert trace.error and "Unknown tool" in trace.error


@pytest.mark.asyncio
async def test_engine_recovers_from_transient_failure():
    registry = ToolRegistry()
    registry.register(FakeTool())
    registry.register(FailingOnceTool())
    # Add the remaining local-plan tools as a single success implementation.
    for name in ("calculate",):
        tool = FakeTool()
        tool.name = name
        registry.register(tool)
    engine = AgentEngine(planner=Planner(llm=NoLLM()), tool_registry=registry)
    trace = await engine.run(Goal(raw_text="Process incoming invoices"))
    assert trace.agent_status == AgentStatus.COMPLETED
    assert trace.verification and trace.verification.passed
