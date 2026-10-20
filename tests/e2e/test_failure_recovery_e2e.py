from __future__ import annotations

import pytest

from core.engine import AgentEngine
from core.state import Goal, TaskPlan, Milestone, ActionStep, ToolResult, ToolResultStatus
from tools.base import BaseTool
from tools.registry import ToolRegistry


class DateFormTool(BaseTool):
    name = "submit_invoice"
    description = "simulated ERP form"

    def __init__(self): self.calls = 0

    async def _run(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return ToolResult(tool_name=self.name, status=ToolResultStatus.ERROR, error_message="Invalid invoice date. Use YYYY-MM-DD format.")
        return ToolResult(tool_name=self.name, status=ToolResultStatus.SUCCESS, data={"record_id": "INV-RECOVERED"})


class OneStepPlanner:
    async def create_plan(self, goal):
        return TaskPlan(goal_id=goal.id, milestones=[Milestone(title="submit", description="submit", steps=[ActionStep(description="submit invoice", tool_name="submit_invoice", tool_args={"invoice_date": "09/25/2024"})])])


@pytest.mark.asyncio
async def test_validation_error_is_retried_and_recovered():
    tools = ToolRegistry(); tools.register(DateFormTool())
    trace = await AgentEngine(planner=OneStepPlanner(), tool_registry=tools).run(Goal(raw_text="Submit invoice"))
    assert trace.verification and trace.verification.passed
    assert len(trace.observations) == 2
