from __future__ import annotations

import pytest

from core.engine import AgentEngine
from core.hitl import HITLManager
from core.state import Goal, HITLDecision, TaskPlan, Milestone, ActionStep, ToolResult, ToolResultStatus
from tools.base import BaseTool
from tools.registry import ToolRegistry


class SubmitTool(BaseTool):
    name = "submit_invoice"
    description = "simulated submit"
    async def _run(self, **kwargs):
        return ToolResult(tool_name=self.name, status=ToolResultStatus.SUCCESS, data={"record_id": "INV-HITL"})


class ApprovalPlanner:
    async def create_plan(self, goal):
        return TaskPlan(goal_id=goal.id, milestones=[Milestone(title="approval", description="approval", steps=[ActionStep(description="submit high-value invoice", tool_name="submit_invoice", tool_args={"total_amount": 6000})])])


@pytest.mark.asyncio
async def test_high_value_invoice_waits_for_human_approval():
    async def approve(request): return HITLDecision.APPROVED
    tools = ToolRegistry(); tools.register(SubmitTool())
    trace = await AgentEngine(planner=ApprovalPlanner(), tool_registry=tools, hitl=HITLManager(approve)).run(Goal(raw_text="Submit high-value invoice"))
    assert trace.verification and trace.verification.passed
    assert len(trace.hitl_requests) == 1
